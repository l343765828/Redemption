import logging
from dask.distributed import get_client, Lock, futures_of, wait as dask_wait
import dask_cudf
import cudf
from typing import List
from Model.Config import DELTA_UNSERINFO
from Model.User import ChangeUserInfoMsg
from Until.Common import read_delta_snapshot_files
import pandas as pd

LOG = logging.getLogger("User.UserInfoService")


class UserInfoService:
    def __init__(self):
        self.userinfo_version = None
        self.ddf_userinfo = None
        self._lock_name = "userinfo_cdc_lock"

    def get_ddf_userinfo(self):
        """
        供外部（如 PEBonusBatchService）直接获取常驻显存的维表 Dask-cuDF。
        """
        return self.ddf_userinfo

    def load_userinfo(self, userinfo_dir: str, npartitions: int = 0):
        """
        从 Delta 表加载用户信息维表,常驻 GPU 显存,只做最终 join 使用,不参与图构建。

        关联键约定:
          user_id (int64) - 内部一致,与图谱 source/ancestor 列同型
          user_id_str (string) - 供外部 API/Redis 直接 join,免 cast
        建议通过 lookup_user_info(user_ids) helper 访问,统一类型边界。
        """

        # region 初始化
        client = get_client()
        n_workers = len(client.scheduler_info().get("workers", {}))
        nparts = npartitions if npartitions > 0 else max(1, n_workers)

        LOG.info("Loading user info from %s ...", userinfo_dir)
        old_ddf = getattr(self, "ddf_userinfo", None)
        # endregion

        try:
            # region 读取delta 并加载到GPU中
            new_ddf, version = read_delta_snapshot_files(
                userinfo_dir,
                cols=["id", "user_name", "real_name", "country_id", "updatetime"],
                npartitions=nparts,
            )
            new_ddf = new_ddf[new_ddf["id"].notnull()]
            new_ddf["id"] = new_ddf["id"].astype("int64")
            new_ddf["id_str"] = new_ddf["id"].astype("str")
            new_ddf = new_ddf.repartition(npartitions=nparts)
            # 持久化到各 Worker 的 GPU 显存中
            new_ddf = new_ddf.persist()
            dask_wait(futures_of(new_ddf))
            # endregion

            # region 验证 并赋值给self
            # 【安全检查空表】极速探针检查，只要能拿出 1 行说明就不为空
            if len(new_ddf.head(1)) == 0:
                raise RuntimeError(f"用户维表加载结果为空: {userinfo_dir}")

            self.ddf_userinfo = new_ddf
            self.userinfo_version = version
            # endregion

            # region 释放旧数据
            if old_ddf is not None:
                try:
                    client.cancel(futures_of(old_ddf))
                except Exception as e:
                    LOG.warning("释放旧 ddf_userinfo 失败: %s", e)
                del old_ddf
            # endregion

            # 原本的代码里，你把 total_rows 打印出来了
            LOG.info("User info loaded successfully. version=%s nparts=%d", version, nparts)

            # --- 插入调试代码 ---
            print(self.ddf_userinfo.compute().to_string())

        except Exception:
            LOG.exception("Failed to load user info from %s", userinfo_dir)
            if old_ddf is None:
                self.ddf_userinfo = None
                self.userinfo_version = -1
            raise

    def lookup_user_info(self, user_ids):
        """
        维表批量查询的统一入口。强制 int64,缺失项 warning 但不静默丢弃。

        :param user_ids: list[int] / list[str] / Iterable,内部统一 cast int64
        :return: cudf.DataFrame,行数 == 去重后的 user_ids 行数(缺失项字段为 NaN)
                 含字段: user_id, user_id_str, user_name, real_name, country_id
        """

        if self.ddf_userinfo is None:
            raise RuntimeError("用户维表未加载,请先调用 load_userinfo")

        if not user_ids:
            # 空输入直接返回空 DataFrame,避免触发 dask 计算
            return cudf.DataFrame({
                "id": cudf.Series([], dtype="int64"),
                "id_str": cudf.Series([], dtype="str"),
                "user_name": cudf.Series([], dtype="str"),
                "real_name": cudf.Series([], dtype="str"),
                "country_id": cudf.Series([], dtype="str"),
            })

        # 类型转换,失败时给清晰错误
        try:
            keys = cudf.Series(list(user_ids)).astype("int64")
        except Exception as e:
            raise ValueError(f"user_ids 含无法转 int64 的值: {e}") from e

        # 输入去重,避免重复请求把结果膨胀
        keys_df = cudf.DataFrame({"id": keys}).drop_duplicates()
        keys_ddf = dask_cudf.from_cudf(keys_df, npartitions=1)

        # right join: 保留所有请求的 keys,缺失项填 null
        # 加 broadcast=True 让 dask-cudf 广播小表,避免对维表大 shuffle
        try:
            result = self.ddf_userinfo.merge(
                keys_ddf, on="id", how="right", broadcast=True,
            ).compute()
        except TypeError:
            # 旧版本 dask-cudf 不支持 broadcast 参数,降级
            result = self.ddf_userinfo.merge(
                keys_ddf, on="id", how="right",
            ).compute()

        # 缺失项 warning
        missing_mask = result["user_name"].isnull()
        if missing_mask.any():
            missing_ids = result[missing_mask]["id"].to_pandas().tolist()
            LOG.warning(
                "用户维表缺失 %d 个 id (示例前10): %s",
                len(missing_ids), missing_ids[:10],
            )

        return result

    def run_update_userinfo(self, version: int, change_list: List[ChangeUserInfoMsg], npartitions: int = 1):
        """
        用户信息维表内存级增量更新 (In-Memory Patching)。

        并发约定：
            - 写路径串行（由 self._lock_name 控制）。
            - 读路径必须遵循"取引用 → 立即 compute"的模式，不可长期持有
              self.ddf_userinfo 的旧引用，否则可能被本函数 cancel 旧 futures 时打断。
        """
        # region 数据验证
        if self.ddf_userinfo is None:
            LOG.warning("维表尚未加载，无法执行增量更新。")
            return False
        # endregion

        # region 上锁
        client = get_client()
        lock = Lock(self._lock_name)
        acquired = lock.acquire(timeout=15)

        if not acquired:
            LOG.warning(f"获取 UserInfo 增量更新锁超时，version={version}")
            return False
        # endregion

        patch_ddf = None  # 提前声明，防 finally NameError

        try:
            # region 验证
            # 1. 版本顺序校验
            if version <= self.userinfo_version:
                LOG.info(f"版本 {version} 已处理过，跳过。")
                return True

            # 2. 空批次极速返回
            if not change_list:
                self.userinfo_version = version
                LOG.info(f"UserInfo 空增量更新成功。新版本: {version}")
                return True
            # endregion

            # region 数据效验
            # 3. CPU 端预处理与严格校验
            rows = [m.model_dump() for m in change_list]
            pdf = pd.DataFrame(rows)

            required_cols = ["id", "op", "user_name", "real_name", "country_id", "updatetime"]
            for col in required_cols:
                if col not in pdf.columns:
                    pdf[col] = None

            if pdf["id"].isnull().any():
                raise ValueError("CDC 数据中存在空 id 的行")
            if pdf["op"].isnull().any():
                raise ValueError("CDC 数据中存在空 op 的行")

            valid_ops = {"c", "u", "d"}
            bad_ops = set(pdf["op"].unique()) - valid_ops
            if bad_ops:
                raise ValueError(f"未知 UserInfo CDC op: {bad_ops}")
            # endregion

            # region 数据去重
            # 批次内严格去重，按到达顺序保留最后一次操作
            # --- 批次内严格去重 (毫秒级 Event Time 语义) ---
            # 1. 强制将 updatetime 转为 int64，防范空值被推断为 float 导致大数精度丢失
            #    如果有异常空值，默认给 0，这样它在升序排序时会被排在最前面，优先被淘汰掉
            pdf["updatetime"] = pdf["updatetime"].fillna(0).astype("int64")

            # 2. 构造物理到达顺序兜底
            # 毫秒级精度已经极高，但在极端情况（如一个大事务在同一毫秒内更新了用户的多个状态）
            # 同一个 id 可能有相同的 updatetime，此时依然依靠 _seq（Kafka 消息顺序）打破平局
            pdf["_seq"] = range(len(pdf))

            # 3. 联合排序与去重
            pdf = (
                # 升序排列优先级：id -> updatetime (毫秒时间戳) -> _seq (到达顺序)
                pdf.sort_values(["id", "updatetime", "_seq"], ascending=[True, True, True])
                .drop_duplicates(subset=["id"], keep="last")
                .drop(columns=["_seq"])
            )

            pdf["id"] = pdf["id"].astype("int64")
            pdf["id_str"] = pdf["id"].astype("str")
            # endregion

            # region 4. 送入 GPU
            gdf = cudf.from_pandas(pdf)
            patch_ddf = dask_cudf.from_cudf(
                gdf,
                npartitions=max(1, npartitions)
            ).persist()
            dask_wait(patch_ddf)
            # endregion

            # region 根据增量数据的id 从现有数据中删除需要更改的数据
            curr_ddf = self.ddf_userinfo
            target_cols = curr_ddf.columns.tolist()
            target_dtypes = curr_ddf.dtypes.to_dict()

            # 5. 杀旧：CDC 中出现过的 id 先从原表移除
            # 用 assign 是更符合 dask 惰性图风格的写法
            # （patch_ddf 已在 CPU 端按 id 去重，无需再 dedupe）
            delete_ids = patch_ddf[["id"]].assign(_is_del=1)

            merged = curr_ddf.merge(delete_ids, on="id", how="left")
            curr_ddf = merged[merged["_is_del"].isnull()].drop(columns=["_is_del"])
            # endregion

            # region 新数据：取出增量删除需要插入和更新的数据
            # 6. 迎新：先筛 c/u，再做严格 schema 对齐
            new_rows = patch_ddf[patch_ddf["op"].isin(["c", "u"])]

            # ---- 批量 schema 对齐，压缩 Dask 任务图层级 ----

            # 6a. 批量 cast 已有列的 dtype（单次 DAG 节点）
            cast_dict = {col: dt for col, dt in target_dtypes.items() if col in new_rows.columns}
            if cast_dict:
                new_rows = new_rows.astype(cast_dict)
            # endregion

            # region 补漏
            # 6b. 批量补齐缺失列（单次 map_partitions）
            missing_cols = {col: dt for col, dt in target_dtypes.items() if col not in new_rows.columns}
            if missing_cols:
                def _add_missing_cols(part, missing=missing_cols):
                    part = part.copy()
                    for c, d in missing.items():
                        part[c] = cudf.NA  # GPU 端标量广播，避免 [NA]*N 性能坑
                        part[c] = part[c].astype(d)  # 修正 dtype
                    return part

                # 显式传 meta，避免 dask 跑样本去推断 schema
                _meta = new_rows._meta.copy()
                for c, d in missing_cols.items():
                    _meta[c] = cudf.Series(dtype=d)

                new_rows = new_rows.map_partitions(_add_missing_cols, meta=_meta)

            # 此时 new_rows 必然包含 target_cols 的全部列，按 curr_ddf 列序裁剪并丢弃 op 等多余列
            new_rows = new_rows[target_cols]
            # endregion

            # region 将新数据合并到现有数据中
            # 7. 追加
            curr_ddf = dask_cudf.concat([curr_ddf, new_rows])

            # 8. 持久化新快照
            curr_ddf = curr_ddf.persist()
            dask_wait(curr_ddf)
            # endregion

            # region 释放旧数据
            # 原子切换 + 推进版本号
            old_ddf = self.ddf_userinfo
            self.ddf_userinfo = curr_ddf
            self.userinfo_version = version

            # 9. 释放旧快照
            # --- 插入调试代码 ---
            LOG.info("准备打表")
            LOG.info(self.ddf_userinfo.compute().to_string())
            LOG.info("准备打表")
            try:
                client.cancel(old_ddf)
            except Exception as e:
                LOG.warning(f"释放旧版本维表失败: {e}")

            LOG.info(f"UserInfo 增量更新成功。新版本: {version}")
            return True
            # endregion
        except Exception:
            LOG.exception(f"UserInfo 增量更新失败，version={version}")
            return False

        finally:
            lock.release()
            # 无论成败都释放增量补丁，防显存泄漏
            # 注意：此时 curr_ddf 已 persist 完毕，cancel patch_ddf 不会影响新快照
            if patch_ddf is not None:
                try:
                    client.cancel(patch_ddf)
                except Exception:
                    pass


if __name__ == "__main__":
    from dask.distributed import Client
    import logging

    # 【加上这一行配置】
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

    # ==========================================
    # 1. 启动或连接 Dask 分布式集群
    # ==========================================
    # 如果你在本地单机带 GPU 环境测试，可以直接用 Client()
    # 如果连接远端集群，请改成 Client("tcp://192.168.18.149:38786")
    try:
        print(">>> 正在连接 Dask 集群...")
        client = Client()
        print(f">>> 集群连接成功! 仪表盘地址: {client.dashboard_link}")
    except Exception as e:
        print(f"!!! 集群连接失败: {e}")
        exit(1)

    # ==========================================
    # 2. 实例化服务并加载数据
    # ==========================================
    # 【请替换为你真实的 Delta 表路径】
    TEST_DELTA_DIR = DELTA_UNSERINFO

    user_service = UserInfoService()

    try:
        print(f"\n>>> 开始加载用户信息维表从: {TEST_DELTA_DIR}")
        user_service.load_userinfo(userinfo_dir=TEST_DELTA_DIR, npartitions=2)
        print(">>> 维表加载完成！")
    except Exception as e:
        print(f"!!! 加载维表失败，请检查路径或数据是否正确: {e}")
        client.close()
        exit(1)

    # ==========================================
    # 3. 模拟业务场景：图计算得到了结果，需要查名字
    # ==========================================
    print("\n>>> 开始测试 lookup_user_info...")

    # 构造测试 ID 列表 (混合类型、并故意加上一个不存在的 ID 看警告)
    # 假设 1001, 1002 是存在的，99999999 是不存在的
    test_user_ids = [1, 2, 99999999]

    print(f"查询的 ID 列表: {test_user_ids}")

    try:
        # 执行批量查询
        result_cudf = user_service.lookup_user_info(test_user_ids)

        # 将 GPU 中的 DataFrame 拉回内存供打印展示
        result_pdf = result_cudf.to_pandas()

        print("\n>>> 最终合并结果:")
        # 优化打印展示效果
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        print(result_pdf)

    except Exception as e:
        print(f"!!! 查询维表测试失败: {e}")

    # ==========================================
    # 4. 资源清理
    # ==========================================
    print("\n>>> 测试结束，关闭 Dask 客户端...")
    client.close()
