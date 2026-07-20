"""
分布式 cugraph.dask BFS + 双网图服务（工业防御最终版）

本文件是在旧版 GraphService_bak3.py 的“分布式 BFS + JOIN 批次聚合”基础上扩展而来：
- 旧版主线：推荐网 src -> parent，用 cugraph.dask BFS 找上级，再与订单表 JOIN 计算层级返利。
- 新版主线：同时维护推荐网 Sponsor Tree 与安置网 Placement Tree。
- 双轨制主线：基于 placementId / placementLeg 展开安置网闭包表，对应 CALC_PV.sql 的 MID4 明细生成。
- 汇总主线：对闭包表 + 用户 PV 做集中 GROUP BY，得到 MID5 口径的 PV_1L / PV_2L。
- 工程防线：完整性校验、CDC 防 Schema 漂移、PV 双计绝缘、显存/Comms 清理与分页稳定性保护。

业务规则已确认：
- 安置网是严格树结构：每个用户最多一个 placementId。
- 同一个上级的同一个 placementLeg 只能有一个直接下级。
- 双轨 leg 采用“大腿包小腿”继承语义：后代相对某个祖先的 1L/2L 归属，由路径第一跳决定。
- 二元去重 ancestor + descendant 只作为性能与脏数据容错防线，不改变合法树结构下的业务结果。
"""
from typing import List, Dict, Optional, Any, Tuple
import dask
import dask_cudf
import cudf
import cugraph
from cugraph.dask.traversal import bfs as dask_bfs
import numpy as np
from deltalake import DeltaTable
from dask.distributed import Client, Lock, get_client, wait as dask_wait, futures_of, Future
import gc
import cupy as cp
import pandas as pd
import logging
from decimal import Decimal

# ⚠️ 注意: 请务必确保 ChangeUserMsg 模型中包含了 placementId (str) 和 placementLeg (int) 字段
from Model.User.ChangeUserMsg import ChangeUserMsg
from Model.Order.OrderPayload import OrderPayload
from Rates.RatesService import RatesService
from Until.Common import read_delta_snapshot_files
import cugraph.dask.comms.comms as Comms

INF = np.iinfo(np.int32).max
users_cdc_version = "users_cdc_version"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
LOG = logging.getLogger("User.GraphService")


def futures_flatten(*collections) -> List[Future]:
    """
    将若干 dask collection 或 futures 列表扁平化为 List[Future]。

    兼容 futures_of() 的不同返回形式：
    - 单个 Future
    - List[Future]
    - tuple / set 等可迭代 Future 集合

    旧版 GraphService_bak3.py 中该工具用于统一等待 df_bfs_batch、ddf_pur、detail_ddf 等
    Dask-cuDF 计算图物化；新版沿用该模式，避免后续 JOIN / groupby 重复触发前置任务。
    """
    out = []
    for c in collections:
        f = futures_of(c)
        if isinstance(f, (list, tuple, set)):
            out.extend(list(f))
        else:
            out.append(f)
    return out


def wait_collections(*collections, timeout=None):
    """
    方便用法：等待若干 Dask collection 或 futures 列表在集群上 materialize 完成。

    典型调用：
        wait_collections(df_bfs_batch, ddf_pur)

    注意：
    - 这里不直接 compute()，只是等待 persist 后的分布式任务完成。
    - 适合在 JOIN、groupby、concat 之前压实任务图，减少重复计算。
    """
    futures = futures_flatten(*collections)
    if not futures:
        return
    dask_wait(futures, timeout=timeout)


def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """
    将长列表切分为固定大小的 batch。

    旧版用于把买家列表按 batch_size_param 拆分后逐批 BFS；
    新版仍用于推荐网返利计算，避免一次性对所有订单用户触发过多 BFS 任务。
    """
    if chunk_size <= 0: return [lst]
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def _worker_cleanup_existing_graph_service():
    """
    在 worker 上清理真实存在的 GraphService 资源，而不是临时 new 一个 GraphService。

    清理顺序：
    1. 如果 worker globals 中存在持久 GraphService 实例，则调用它的 cleanup()。
    2. 否则 fallback：直接销毁 cugraph.dask Comms，并释放 cupy 默认显存池。
    3. 最后触发 Python GC。

    这样可以避免 reload / CDC 重建图时残留旧图、旧 Dask collection 或 Comms 状态。
    """
    try:
        gs = globals().get("_graph_service_instance", None)
        if isinstance(gs, GraphService):
            gs.cleanup()
    except Exception:
        pass
    try:
        if Comms.is_initialized(): Comms.destroy()
    except Exception:
        pass
    try:
        gc.collect()
        cp.get_default_memory_pool().free_all_blocks()
    except Exception:
        pass


def need_reload(model_dir, msg_version):
    """
    根据 Delta Lake 快照版本和消息版本判断是否允许 reload。

    含义：
    - dt.version() 是当前模型目录的 Delta 最新版本。
    - msg_version 是消息要求加载的目标版本。
    - 返回 True 表示本地快照版本足以支撑该消息版本，允许进入双重锁后的构图流程。
    """
    dt = DeltaTable(model_dir)
    return dt.version() >= int(msg_version)


def to_broadcast_ddf(small_df: cudf.DataFrame, flag_col=None) -> cudf.DataFrame:
    """
    给用于 broadcast / 小表 JOIN 的 cudf DataFrame 增加标记列。

    典型用途：
    - CDC 删除/更新时，把待删除 id 打上 _is_del=1。
    - 与全量用户表 left join 后，通过 _is_del 是否为空过滤掉旧记录。
    """
    if flag_col: small_df[flag_col] = 1
    return small_df


class GraphService:

    def __init__(self):
        self.msg_version = -1
        # 旧逻辑与推荐网视图（保持向下兼容）
        self.dg = None
        self.dg_rev = None
        self.ddf_users = None
        self.ddf_edges = None
        self.ddf_depths = None
        self.ddf_users_by_dst = None

        # 显式推荐网（Sponsor Tree）
        self.dg_sponsor = None
        self.dg_sponsor_rev = None
        self.ddf_sponsor_edges = None

        # 显式安置网（Placement Tree / 双轨制）
        self.dg_placement = None
        self.dg_placement_rev = None
        self.ddf_placement_edges = None
        self.ddf_placement_users = None

        # 批量闭包表结果缓存，避免重复迭代自连接引发算力浪费
        self.ddf_placement_closure = None

        self.ddf_users_raw = None
        self._columns_normalized = False
        self._global_lock_name = "graph_service_lock"

    @staticmethod
    def get_current_published_version(client) -> int:
        try:
            return int(client.get_dataset("users_version"))
        except Exception:
            return -1

    @staticmethod
    def get_current_published_cdc_version(client) -> int:
        try:
            return int(client.get_dataset(users_cdc_version))
        except Exception:
            return -1

    def cleanup(self):
        """
        销毁当前 GraphService 挂载的所有图对象、Dask-cuDF 缓存引用和底层通信资源。

        对应旧版 cleanup 的职责：
        - 释放 cugraph.dask Comms，防止通信层残留。
        - 将 dg / dg_rev / ddf_users / ddf_edges 等引用置空。
        - 触发 gc.collect() 与 cupy memory pool 释放，降低 GPU OOM 风险。

        新版额外清理：
        - 推荐网显式对象 dg_sponsor / dg_sponsor_rev / ddf_sponsor_edges。
        - 安置网显式对象 dg_placement / dg_placement_rev / ddf_placement_edges。
        - 双轨制闭包表缓存 ddf_placement_closure。
        """
        try:
            self.dg = None
            self.dg_rev = None
            self.ddf_users = None
            self.ddf_edges = None
            self.ddf_depths = None
            self.ddf_users_by_dst = None
            self.dg_sponsor = None
            self.dg_sponsor_rev = None
            self.ddf_sponsor_edges = None
            self.dg_placement = None
            self.dg_placement_rev = None
            self.ddf_placement_edges = None
            self.ddf_placement_users = None
            self.ddf_users_raw = None
            self.ddf_placement_closure = None
            self._columns_normalized = False
            self.msg_version = -1
            if Comms.is_initialized(): Comms.destroy()
        except Exception as e:
            LOG.error(f"Cleanup failed: {e}")
        gc.collect()
        try:
            cp.get_default_memory_pool().free_all_blocks()
        except Exception:
            pass

    def cleanup_cluster(self, client=None):
        """
        对整个 Dask 集群执行 cleanup（外部调用场景）。

        - driver 调用本方法。
        - 实际 cleanup 在各 worker 上执行。
        - 用于全量重建或 CDC 重建前后清理旧图、旧 Comms 和 cupy 显存池。
        """
        if client is None: client = get_client()
        client.run(_worker_cleanup_existing_graph_service)

    def run(self, msg_version: int, model_dir: str, npartitions: int = 0, renumber_disable: bool = True):
        """
        将 Delta 用户关系快照加载至 GPU / Dask-cuDF，并构建“推荐网 + 安置网”双拓扑。

        推荐网 Sponsor Tree：
        - parent 字段重命名为 dst。
        - ddf_sponsor_edges: src -> dst，用于原有 BFS 层级返利。
        - dg_sponsor: src -> dst，用于向上查祖先。
        - dg_sponsor_rev: dst -> src，用于向下查子孙。

        安置网 Placement Tree：
        - placementId 字段重命名为 dst。
        - ddf_placement_edges: src -> dst + placementLeg，用于双轨制 1L/2L。
        - dg_placement: src -> dst，用于向上查安置祖先。
        - dg_placement_rev: dst -> src，用于向下查安置子孙。

        注意：
        - 本方法只在检测到 Delta 版本需要 reload 时重建图。
        - 无论是否 reload，都必须释放 graph_service_lock / reload lock。
        - 构图失败时必须 cleanup，避免留下半初始化图或 GPU 通信资源。
        """
        # region 初始化
        client = get_client()

        # 【冷启动保护】 防止空集群永久阻塞，加 timeout
        client.wait_for_workers(1, timeout=60)

        runLock = Lock(self._global_lock_name, client=client)
        got_run_lock = False
        reload_lock = None
        reload_lock_acquired = False
        # endregion

        try:
            # region 上锁
            # 全局互斥：防止多个线程/任务同时重建图，导致 Comms 或显存对象互相覆盖。
            got_run_lock = runLock.acquire(timeout=15)
            if not got_run_lock: return

            # 初始化前销毁旧资源；先清理再构图。
            try:
                client.run(_worker_cleanup_existing_graph_service)
            except Exception:
                pass
            # endregion

            # region 验证消息版本号是否为最新 不是的话 不更新
            # 已发布版本不低于消息版本时，说明当前内存图已经足够新，直接跳过。
            current_version = self.get_current_published_version(client)
            msg_version = int(msg_version)
            if current_version >= msg_version: return

            # 版本级互斥：同一个 msg_version 只允许一个任务真正 reload。
            reload_lock = Lock(f"reload:{msg_version}", client=client)
            reload_lock_acquired = reload_lock.acquire(timeout=15)
            if not reload_lock_acquired: return
            # endregion

            # region  double check：拿到 reload lock 后再次校验，避免锁等待期间其他任务已经完成构图。
            if not (self.get_current_published_version(client) < msg_version and need_reload(model_dir, msg_version)):
                return
            # endregion

            # region 获取n_workers数量
            sched_info = client.scheduler_info()
            worker_addrs = list(sched_info.get("workers", {}).keys())
            n_workers = len(worker_addrs)
            # endregion

            # region ddf_users_raw、current_version_local -> 读取 Wide Table 完整属性（同时包含推荐网与安置网字段）
            ddf_users_raw, current_version_local = read_delta_snapshot_files(
                model_dir,
                cols=["id", "user", "parent", "placementId", "placementLeg", "updatetime"],
                npartitions=npartitions,
            )
            # endregion

            # region 将ddf_users_raw的 user -> src，并加载到内存中
            # 统一把业务用户字段 user 改名为 src，方便后续两张图共享同一套边表命名。
            ddf_users_raw = ddf_users_raw.rename(columns={"user": "src"})

            # 分区数优先使用外部指定值；否则按 worker 数兜底。
            nparts = npartitions if npartitions > 0 else max(1, n_workers)

            # persist 全量宽表，避免 sponsor / placement 两路拆分时重复读取 Delta。
            ddf_users_raw = ddf_users_raw.repartition(npartitions=nparts).persist()
            dask.distributed.wait(ddf_users_raw)
            # endregion

            # 创造ddf_sponsor_users -> 分离推荐网 (Sponsor) 别名映射 parent->dst
            # region 创造ddf_sponsor_edges -> 过滤出有上级的数据
            ddf_sponsor_users = ddf_users_raw.rename(columns={"parent": "dst"})
            ddf_sponsor_edges = ddf_sponsor_users[ddf_sponsor_users["dst"] != "0"][["src", "dst"]]
            # endregion

            # 创造ddf_placement_users -> 分离安置网 (Placement) 别名映射 placementId->dst
            # region 创造ddf_placement_edges -> 过滤出有上级的数据 关键：必须带出 placementLeg 用于双轨区位划分
            ddf_placement_users = ddf_users_raw.rename(columns={"placementId": "dst"})
            ddf_placement_edges = ddf_placement_users[ddf_placement_users["dst"] != "0"][["src", "dst", "placementLeg"]]
            # endregion

            # region 将ddf_sponsor_edges、ddf_placement_edges加载到内存中
            # 两张有效边表均提前 persist，确保 from_dask_cudf_edgelist 读取的是稳定物化后的边。
            ddf_sponsor_edges = ddf_sponsor_edges.persist()
            ddf_placement_edges = ddf_placement_edges.persist()
            dask.distributed.wait([ddf_sponsor_edges, ddf_placement_edges])
            # endregion

            # region 初始化Comms
            # cugraph.dask 构图依赖 Comms；重复 initialize 可能报错，因此只在未初始化时执行。
            if not Comms.is_initialized(): Comms.initialize()

            self.dg = self.dg_rev = self.dg_sponsor = self.dg_sponsor_rev = None
            self.dg_placement = self.dg_placement_rev = None
            gc.collect()
            # endregion

            # 【裸奔态防御】 拦截 from_dask_cudf_edgelist 崩溃，若抛错自动清理垃圾对象，避免内存泄漏与僵尸图
            try:
                # region 创建dg_sponsor、dg_sponsor_rev -> 根据ddf_sponsor_edges创建推荐网的正向图、反向图
                dg_sponsor = cugraph.Graph(directed=True)
                dg_sponsor.from_dask_cudf_edgelist(ddf_sponsor_edges, source="src", destination="dst",
                                                   renumber=(not renumber_disable))
                dg_sponsor_rev = cugraph.Graph(directed=True)
                dg_sponsor_rev.from_dask_cudf_edgelist(ddf_sponsor_edges, source="dst", destination="src",
                                                       renumber=(not renumber_disable))
                # endregion

                # region 创建dg_placement、dg_placement_rev -> 根据ddf_placement_edges创建安置网的正向图、反向图
                # 注意：建图严禁传入 placementLeg 第三列，避免引起底层不可知的数据偏置错误
                dg_placement = cugraph.Graph(directed=True)
                dg_placement.from_dask_cudf_edgelist(ddf_placement_edges[["src", "dst"]], source="src",
                                                     destination="dst", renumber=(not renumber_disable))
                dg_placement_rev = cugraph.Graph(directed=True)
                dg_placement_rev.from_dask_cudf_edgelist(ddf_placement_edges[["src", "dst"]], source="dst",
                                                         destination="src", renumber=(not renumber_disable))
                # endregion

                # region 安全挂载
                self.dg = dg_sponsor
                self.dg_rev = dg_sponsor_rev
                self.ddf_users = ddf_sponsor_users
                self.ddf_edges = ddf_sponsor_edges
                self.dg_sponsor = dg_sponsor
                self.dg_sponsor_rev = dg_sponsor_rev
                self.ddf_sponsor_edges = ddf_sponsor_edges
                self.dg_placement = dg_placement
                self.dg_placement_rev = dg_placement_rev
                self.ddf_placement_edges = ddf_placement_edges
                self.ddf_placement_users = ddf_placement_users
                self.ddf_users_raw = ddf_users_raw
                # endregion

            except Exception as e:
                self.cleanup()
                LOG.error(f"图加载过程遭遇异常，为避免显存泄漏已强制清理对象: {e}")
                raise RuntimeError("构图失败，已清理对象。请重试。") from e

            self._invalidate_global_recalc_indexes()

            # region 将版本号发布到schedule
            ds_version = "users_version"
            try:
                client.unpublish_dataset(ds_version)
            except Exception:
                pass
            client.publish_dataset(**{ds_version: current_version_local})
            LOG.info("全量双网构建成功。")
            # endregion

        finally:
            # region 解锁
            if reload_lock_acquired and reload_lock is not None:
                try:
                    reload_lock.release()
                except Exception:
                    pass
            if got_run_lock:
                try:
                    runLock.release()
                except Exception:
                    pass
            # endregion

    def run_update(self, version: int, changList: List[ChangeUserMsg], npartitions: int = 1,
                   renumber_disable: bool = True):
        """
        根据用户 CDC 消息更新内存中的全量用户宽表，并重新创建推荐网、安置网正反双图。

        与旧版 GraphService_bak3.py 的差异：
        - 旧版只维护 parent -> 推荐网边。
        - 新版必须同时维护 parent 与 placementId / placementLeg。
        - CDC 后必须让 Root-Depth 索引、children 索引、placement closure 全部失效。
        - 对 placementLeg 做强类型规整与脏数据隔离，避免双轨 PV 因非法 leg 静默蒸发。

        注意：
        - version <= 已发布 CDC version 时直接跳过，防止乱序旧消息覆盖新图。
        - 构图失败会 cleanup 并抛错，不允许半更新状态继续对外服务。
        """
        # region 初始化
        client = get_client()
        current_cdc_version = self.get_current_published_cdc_version(client)
        # 防止旧版本消息乱序覆盖新拓扑
        if int(version) <= current_cdc_version: return

        lock = Lock("cdc_lock", client=client)
        lock_acquired = False
        # endregion

        try:
            # region 上锁
            lock_acquired = lock.acquire(timeout=15)
            if not lock_acquired: return
            if int(version) <= self.get_current_published_cdc_version(client): return
            # endregion

            # region 创造pdf -> 将changList转成Pydantic
            # 将 Pydantic CDC 消息转换为 pandas，方便做入口级数据清洗和 schema 防漂移。
            rows = [m.model_dump() for m in changList]
            pdf = pd.DataFrame(rows)
            # endregion

            # region 验证
            # 【CDC 柔性海关拦截与防 Schema 漂移】
            # 显式填补空值并强转类型，拦截 Pydantic 将 None 转为 float64 的灾难
            if "placementLeg" in pdf.columns:
                pdf["placementLeg"] = pdf["placementLeg"].fillna(0).astype("int32")
            if "placementId" in pdf.columns:
                pdf["placementId"] = pdf["placementId"].fillna("0").astype("str")

            if "placementId" in pdf.columns and "placementLeg" in pdf.columns:
                # 强校验：未安置(placementId=="0")，或者已安置的 Leg 必须是 1或2
                valid_mask = (pdf["placementId"] == "0") | (pdf["placementLeg"].isin([1, 2]))
                invalid_cdc = pdf[~valid_mask]

                # 若发现脏数据（如 leg=0 或 null 洗成的 0），直接拦截隔离
                if len(invalid_cdc) > 0:
                    LOG.error(
                        f"⚠️ 拦截到 {len(invalid_cdc)} 条脏 CDC 数据 (已安置但 placementLeg 错误)。"
                        f"已将脏数据剔除以保护双轨账目，剩余合法数据继续更新。"
                    )
                    pdf = pdf[valid_mask]

                    if len(pdf) == 0:
                        LOG.warning("当前 CDC 批次全部为脏数据，过滤后为空，已跳过。")
                        try:
                            client.unpublish_dataset(users_cdc_version)
                        except Exception:
                            pass
                        client.publish_dataset(**{users_cdc_version: version})
                        return
            # endregion

            # region 创造ddf_cdc -> 将pdf的列重命名user->src 并放至内存中
            # 转回 GPU DataFrame；后续插入/更新/删除分支均在 cuDF/Dask-cuDF 上完成。
            cudf_df = cudf.from_pandas(pdf)
            ddf_cdc = dask_cudf.from_cudf(cudf_df, npartitions=npartitions)
            ddf_cdc = ddf_cdc.rename(columns={"user": "src"}).persist()
            dask.distributed.wait(ddf_cdc)
            # endregion

            # region 将ddf_cdc按c、u、d过滤出三套数据
            # CDC 三类操作：
            # c = create，直接追加；
            # u = update，先按 id 删除旧行，再追加新行；
            # d = delete，只删除旧行。
            inserts = ddf_cdc[ddf_cdc["op"] == "c"].compute()
            updates = ddf_cdc[ddf_cdc["op"] == "u"].compute()
            deletes = ddf_cdc[ddf_cdc["op"] == "d"].compute()
            # endregion

            # region 验证
            if self.ddf_users_raw is None: raise RuntimeError("系统尚未加载全集")
            # endregion

            # region 将删除和更改的放入delete_parts 将新增和更改的放入parts
            delete_parts = []
            parts = []
            if len(deletes) > 0: delete_parts.append(to_broadcast_ddf(deletes[["id"]].copy(), "_is_del"))
            if len(updates) > 0:
                delete_parts.append(to_broadcast_ddf(updates[["id"]].copy(), "_is_del"))
                parts.append(updates[["id", "src", "parent", "placementId", "placementLeg", "updatetime"]].copy())
            if len(inserts) > 0:
                parts.append(inserts[["id", "src", "parent", "placementId", "placementLeg", "updatetime"]].copy())
            # endregion

            # region 从当前内存中的全量宽表出发，按 CDC 语义做增删改合并。
            ddf_raw = self.ddf_users_raw
            if delete_parts:
                to_delete = cudf.concat(delete_parts, ignore_index=True)
                del_ddf = dask_cudf.from_cudf(to_delete, npartitions=npartitions)
                merged = ddf_raw.merge(del_ddf, on=["id"], how="left")
                # _is_del为空的属于 保留数据
                ddf_raw = merged[merged["_is_del"].isnull()].drop(columns=["_is_del"])

            if parts:
                to_insert = cudf.concat(parts, ignore_index=True)
                ins_ddf = dask_cudf.from_cudf(to_insert, npartitions=npartitions)
                ddf_raw = dask_cudf.concat([ddf_raw, ins_ddf])
            # endregion

            # region 将ddf_raw重新发到内存中 并且重新赋值self.ddf_users_raw
            # 业务约束：每个用户只有一条最新记录。这里按 src 去重后重新物化为新的全量宽表。
            ddf_raw = ddf_raw.drop_duplicates(subset=["src"]).repartition(npartitions=npartitions).persist()
            dask.distributed.wait(ddf_raw)
            self.ddf_users_raw = ddf_raw
            # endregion

            # region 重新赋值推荐网和安置网 并发到内存中
            # 重新赋值ddf_sponsor_users、ddf_sponsor_edges、ddf_placement_users、ddf_placement_edges
            ddf_sponsor_users = ddf_raw.rename(columns={"parent": "dst"})
            ddf_sponsor_edges = ddf_sponsor_users[ddf_sponsor_users["dst"] != "0"][["src", "dst"]].persist()

            ddf_placement_users = ddf_raw.rename(columns={"placementId": "dst"})
            ddf_placement_edges = ddf_placement_users[ddf_placement_users["dst"] != "0"][
                ["src", "dst", "placementLeg"]].persist()
            dask.distributed.wait([ddf_sponsor_edges, ddf_placement_edges])
            # endregion

            # region Comms初始化
            if not Comms.is_initialized(): Comms.initialize()

            self.dg = self.dg_rev = self.dg_sponsor = self.dg_sponsor_rev = None
            self.dg_placement = self.dg_placement_rev = None
            gc.collect()
            # endregion

            # 【裸奔态防御】 CDC 增量构建防卡死，失败直接清空重置
            try:
                # region 创建dg_sponsor、dg_sponsor_rev -> 根据ddf_sponsor_edges创建推荐网的正向图、反向图
                dg_sponsor = cugraph.Graph(directed=True)
                dg_sponsor.from_dask_cudf_edgelist(ddf_sponsor_edges, source="src", destination="dst",
                                                   renumber=(not renumber_disable))
                dg_sponsor_rev = cugraph.Graph(directed=True)
                dg_sponsor_rev.from_dask_cudf_edgelist(ddf_sponsor_edges, source="dst", destination="src",
                                                       renumber=(not renumber_disable))
                # endregion

                # region 创建dg_placement、dg_placement_rev -> 根据ddf_placement_edges创建安置网的正向图、反向图
                dg_placement = cugraph.Graph(directed=True)
                dg_placement.from_dask_cudf_edgelist(ddf_placement_edges[["src", "dst"]], source="src",
                                                     destination="dst", renumber=(not renumber_disable))
                dg_placement_rev = cugraph.Graph(directed=True)
                dg_placement_rev.from_dask_cudf_edgelist(ddf_placement_edges[["src", "dst"]], source="dst",
                                                         destination="src", renumber=(not renumber_disable))
                # endregion

                # region 安全挂载
                self.dg = dg_sponsor
                self.dg_rev = dg_sponsor_rev
                self.ddf_users = ddf_sponsor_users
                self.ddf_edges = ddf_sponsor_edges
                self.dg_sponsor = dg_sponsor
                self.dg_sponsor_rev = dg_sponsor_rev
                self.ddf_sponsor_edges = ddf_sponsor_edges
                self.dg_placement = dg_placement
                self.dg_placement_rev = dg_placement_rev
                self.ddf_placement_edges = ddf_placement_edges
                self.ddf_placement_users = ddf_placement_users
                # endregion
            except Exception as e:
                self.cleanup()
                LOG.error(f"CDC更新构图过程遭遇异常，已强制清理对象: {e}")
                raise RuntimeError("增量构图失败，已清理对象。") from e

            self._invalidate_global_recalc_indexes()

            # region 将版本号发布到schedule
            try:
                client.unpublish_dataset(users_cdc_version)
            except Exception:
                pass
            client.publish_dataset(**{users_cdc_version: version})
            # endregion
        finally:
            # region 解锁
            if lock_acquired:
                try:
                    lock.release()
                except Exception:
                    pass
            # endregion

    # =====================================================================
    # 双轨制 1L/2L (MID4/MID5) 核心批处理引擎
    # =====================================================================
    # def build_placement_closure_table(self, max_depth: int = 5000) -> dask_cudf.DataFrame:
    #     """
    #     批量闭包表展开 (即 CALC_PV.sql 中的 MID4 事实表极速生成器)
    #     利用 GPU 自顶向下迭代 Self-Join，将扁平边缘表转化为全树祖先-子孙关系表。
    #     """
    #     # region 复用已缓存的闭包表，避免在同一期重复展树
    #     if self.ddf_placement_closure is not None:
    #         return self.ddf_placement_closure
    #     # endregion
    #
    #     # region 验证
    #     if self.ddf_placement_edges is None:
    #         raise RuntimeError("系统尚未加载安置网基础结构。")
    #     # endregion
    #
    #     # region 创造标尺
    #     edges_raw = self.ddf_placement_edges[["dst", "src"]].persist()
    #     # endregion
    #
    #     # region 取出第一代距离
    #     # 初始第一步，将父级作为祖先，子级作为后代，携带上最顶层的 placementLeg (左右区)
    #     edges = self.ddf_placement_edges[["dst", "src", "placementLeg"]].rename(
    #         columns={"dst": "ancestor", "src": "descendant", "placementLeg": "leg"}
    #     ).persist()
    #     dask.distributed.wait([edges_raw, edges])
    #     # endregion
    #
    #     # region 验证
    #     # 【PV静默蒸发终极防御】：绝不允许连线上的 Leg 是空或者 0/3 等非法值。
    #     # 否则该节点的下游 PV 既进不了左区也进不了右区，将导致业绩断档蒸发。
    #     bad_legs = self._count_ddf_rows(edges[(edges["leg"].isnull()) | (~edges["leg"].isin([1, 2]))])
    #     if bad_legs > 0:
    #         raise RuntimeError(f"安置边表存在 {bad_legs} 条 leg 为空或不为 1/2 的连线，1L/2L 无法归属，已中止计算。")
    #     # endregion
    #
    #     # region parts将第一代添加进去 curr被赋值第一代 converged被赋值false
    #     parts, curr, converged = [edges], edges, False
    #     # endregion
    #
    #     # region 循环拓展深度：每次拿当层子节点去查它的下级节点，但 Leg 归属永远继承自顶级！(大腿包小腿)
    #     for _ in range(max_depth):
    #         # 造next_level -> curr inner edges_raw 获取curr子节点的子节点 并将ancestor的leg代入
    #         # 取ancestor节点Id、孙子节点Id（src->descendant）、leg
    #         # region 取ancestor节点Id、孙子节点Id（src->descendant）、leg
    #         next_level = curr.merge(
    #             edges_raw, left_on="descendant", right_on="dst", how="inner"
    #         )[["ancestor", "src", "leg"]].rename(columns={"src": "descendant"})
    #         # endregion
    #
    #         # region ancestor、descendant去重
    #         # 【核心护城河：强二元去重】：针对极端情况或底层引擎的重复分区切断冗余膨胀
    #         # 业务已确认：安置网为严格单父树状结构，绝对不存在合法菱形网络（多路径贡献）。
    #         # 这里的强去重斩断了任何因脏数据导致的 O(D^2) 内存爆炸，并且保证一个人绝不给同一个祖先贡献两次 PV。
    #         next_level = next_level.drop_duplicates(subset=["ancestor", "descendant"]).persist()
    #         dask.distributed.wait(next_level)
    #         # endregion
    #
    #         # region next_level为空时退出
    #         if self._count_ddf_rows(next_level) == 0:
    #             converged = True
    #             break
    #         # endregion
    #
    #         # region parts添加next_level curr被赋值next_level
    #         parts.append(next_level)
    #         curr = next_level
    #         # endregion
    #     # endregion
    #
    #     # region 验证
    #     if not converged:
    #         raise RuntimeError(
    #             f"安置网闭包在 {max_depth} 层内未收敛：网络过深或存在死循环环路，"
    #             f"双轨制 1L/2L 归属将不完整，已中止计算。"
    #         )
    #     # endregion
    #
    #     # region 将parts生成dask表放至内存中
    #     # 全局合并后的最终保底：跨层强二元去重，keep="first" 确保节点归属只按照顶端最短路径为准。
    #     self.ddf_placement_closure = dask_cudf.concat(parts, ignore_index=True).drop_duplicates(
    #         subset=["ancestor", "descendant"], keep="first").persist()
    #     dask.distributed.wait(self.ddf_placement_closure)
    #     # endregion
    #     return self.ddf_placement_closure

    def calculate_batch_placement_pv(self, df_pv: dask_cudf.DataFrame) -> cudf.DataFrame:
        """
        批量聚合 PV_1L / PV_2L (对应 CALC_PV.sql 中的 MID5 聚合)
        入参 df_pv: 必须包含 [user_id, pv] 且必须是按期汇总过的活跃单用户总计。
        """

        # region 将df_pv 按userId分组 对pv求和
        # 【防御性拷贝与预聚合】：杜绝原地修改调用方的 DF 导致意外污染，同时做一把 groupby.sum 兜底防传入订单明细双计
        df_pv = df_pv[["user_id", "pv"]].copy()
        df_pv["user_id"] = df_pv["user_id"].astype("str")
        df_pv = df_pv.groupby("user_id").agg({"pv": "sum"}).reset_index()
        # endregion

        # region 创造closure -> 获取安置图谱
        closure = self.build_placement_closure_table()
        # endregion

        # region 创造joined -> closure inner df_pv 得到需要派发的业绩
        # 将产生业绩的后代与闭包表连接，瞬间得到该业绩需派发给所有的上层祖先及区位
        joined = closure.merge(
            df_pv, left_on="descendant", right_on="user_id", how="inner"
        )
        # endregion

        # region # 分流左区与右区，直接利用向量化判断进行赋值
        joined["PV_1L"] = joined["pv"].where(joined["leg"] == 1, 0)
        joined["PV_2L"] = joined["pv"].where(joined["leg"] == 2, 0)
        # endregion

        # region 创造agg_ddf -> joined对上级进行分组 对PV_1L、PV_2L求和
        # 终极聚合：一步算出全网所有祖先的双轨当期总业绩
        agg_ddf = joined.groupby("ancestor").agg({
            "PV_1L": "sum",
            "PV_2L": "sum"
        }).reset_index()
        # endregion

        return agg_ddf.compute()

    def get_placement_leg_path(self, src: str) -> pd.DataFrame:
        """查询特定节点的安置祖先链及双轨区位（排错、审计使用）"""
        if self.dg_placement is None or self.ddf_placement_edges is None:
            raise RuntimeError("系统尚未初始化安置网对象。")

        src = str(src)
        edges = self.ddf_placement_edges
        if self._count_ddf_rows(edges[(edges["src"] == src) | (edges["dst"] == src)]) == 0:
            return pd.DataFrame(columns=["descendant", "ancestor", "level", "placementLeg"])

        df_bfs = dask_bfs.bfs(self.dg_placement, str(src))
        df_bfs = df_bfs[df_bfs["distance"].notnull() & (df_bfs["distance"] > 0) & (df_bfs["distance"] != INF)]

        # 【性能优化】：立刻 persist 阻断 Dask 遇到 compute 与 count 时重新跑 BFS
        df_bfs = df_bfs.persist()
        dask.distributed.wait(df_bfs)

        edges = self.ddf_placement_edges[["src", "dst", "placementLeg"]]
        df_bfs = df_bfs.rename(columns={"vertex": "ancestor_dst", "predecessor": "child_src"})

        # 极速内连接查区位：利用 BFS 产出的 predecessor (前驱子节点) 和 vertex(该层祖先)，回表查找 leg
        joined = df_bfs.merge(
            edges,
            left_on=["child_src", "ancestor_dst"],
            right_on=["src", "dst"],
            how="inner"
        )

        joined_local = joined.compute()
        joined_len = len(joined_local)
        bfs_len = self._count_ddf_rows(df_bfs)

        # 防止强转类型异常或边丢失引起的静默吞行
        if joined_len != bfs_len:
            raise RuntimeError(
                f"安置区位归属严重异常: BFS解析出 {bfs_len} 个祖先节点，但匹配到的腿位仅 {joined_len} 个，可能存在脏连线。")

        joined_local["descendant"] = str(src)
        joined_local = joined_local.rename(columns={"ancestor_dst": "ancestor", "distance": "level"})

        return joined_local[["descendant", "ancestor", "level", "placementLeg"]].to_pandas()

    # =====================================================================
    # 防线与底图分页索引校验
    # =====================================================================
    def _ensure_graph_loaded(self) -> None:
        """
        确保 GraphService 已经加载了全量推荐网用户关系表。

        GlobalRecalculationService 依赖 self.ddf_users 做 Root-Depth 与 children 分页索引；
        如果 run() 或 run_update() 尚未成功构图，这里必须 fail-fast。
        """
        if self.ddf_users is None:
            raise RuntimeError("GraphService 尚未初始化加载 ddf_users。")

    def _count_ddf_rows(self, ddf) -> int:
        """
        安全统计 dask_cudf DataFrame 行数。
        """
        return 0 if ddf is None else int(ddf.map_partitions(len).sum().compute())

    def _dedup_with_multipath_guard(self, ddf: dask_cudf.DataFrame, stage: str) -> Tuple[dask_cudf.DataFrame, int]:
        """
        带多路径熔断的去重防线。
        前提：合法安置网(每节点至多一个安置父)中 (ancestor, descendant) 至多一条路径，
        去重前后行数必然相等；不等 ⟺ 多路径/重复边 ⟹ 熔断，绝不静默取其一。
        """
        raw = ddf.persist()
        before = self._count_ddf_rows(raw)

        deduped = raw.drop_duplicates(subset=["ancestor", "descendant"]).persist()
        dask_wait(deduped)
        after = self._count_ddf_rows(deduped)

        if before != after:
            detail = ""
            try:
                dup = raw.groupby(["ancestor", "descendant"]).size().compute()
                dup = dup[dup > 1]
                detail = f"，样本(≤20)：{dup.head(20).to_pandas().to_dict()}"
            except Exception:
                pass
            raise RuntimeError(
                f"非法安置网络：{stage} 存在 {before - after} 条 (ancestor, descendant) "
                f"多路径/重复记录，为防止双轨业绩被静默改写(SQL双计 vs 随机取一)，停止计算{detail}"
            )
        return deduped, after

    def build_placement_closure_table(self, max_depth: int = 5000) -> dask_cudf.DataFrame:
        """
        批量闭包表展开 (即 CALC_PV.sql 中的 MID4 事实表极速生成器)
        利用 GPU 自顶向下迭代 Self-Join，将扁平边缘表转化为全树祖先-子孙关系表。
        """
        if self.ddf_placement_closure is not None:
            return self.ddf_placement_closure

        if self.ddf_placement_edges is None:
            raise RuntimeError("系统尚未加载安置网基础结构。")

        edges = self.ddf_placement_edges[["dst", "src", "placementLeg"]].rename(
            columns={"dst": "ancestor", "src": "descendant", "placementLeg": "leg"}
        )

        edges["leg"] = edges["leg"].fillna(0).astype("int32")
        bad_legs = self._count_ddf_rows(edges[(edges["leg"] == 0) | (~edges["leg"].isin([1, 2]))])
        if bad_legs > 0:
            raise RuntimeError(f"安置边表存在 {bad_legs} 条 leg 为空或不为 1/2 的连线，1L/2L 无法归属，已中止计算。")

        # 基础边表防线
        edges, _ = self._dedup_with_multipath_guard(edges, stage="基础边表")

        edges_raw = self.ddf_placement_edges[["dst", "src"]].persist()
        dask.distributed.wait([edges_raw, edges])

        parts, curr, converged = [edges], edges, False

        for i in range(max_depth):
            next_level = curr.merge(
                edges_raw, left_on="descendant", right_on="dst", how="inner"
            )[["ancestor", "src", "leg"]].rename(columns={"src": "descendant"})

            # 闭包展开循环防线
            next_level, level_rows = self._dedup_with_multipath_guard(
                next_level, stage=f"闭包展开·路径长度 {i + 2}"
            )

            if level_rows == 0:
                converged = True
                break

            parts.append(next_level)
            curr = next_level

        if not converged:
            raise RuntimeError(
                f"安置网闭包在 {max_depth} 层内未收敛：网络过深或存在死循环环路，"
                f"双轨制 1L/2L 归属将不完整，已中止计算。"
            )

        # 闭包全表防线
        self.ddf_placement_closure, closure_rows = self._dedup_with_multipath_guard(
            dask_cudf.concat(parts, ignore_index=True), stage="闭包全表合并"
        )
        LOG.info("闭包表构建完成，共 %d 条祖先-后代关系", closure_rows)

        return self.ddf_placement_closure

    def _invalidate_global_recalc_indexes(self) -> None:
        """
        图数据变更后统一失效所有派生索引和缓存。

        必须在 run() / run_update() 成功更新底图后调用：
        - ddf_depths：推荐网 Root-Depth 索引。
        - ddf_users_by_dst：推荐网按父节点分页的 children 索引。
        - _columns_normalized：src/dst 字符串规范化状态。
        - ddf_placement_closure：安置网 ancestor-descendant 闭包缓存。
        """
        self.ddf_depths = None
        self.ddf_users_by_dst = None
        self._columns_normalized = False
        self.ddf_placement_closure = None

    def _normalize_graph_columns(self) -> None:
        """
        统一 src/dst 类型为 str，避免 int64 / str 混用导致分页、BFS 或 JOIN 异常。

        dask_cudf astype 是 lazy 的，如果每次接口调用都重复 astype，会不断叠加计算图。
        因此这里必须幂等，并在规范化后 persist。
        """
        self._ensure_graph_loaded()
        if getattr(self, "_columns_normalized", False): return
        try:
            self.ddf_users["src"] = self.ddf_users["src"].astype("str")
            self.ddf_users["dst"] = self.ddf_users["dst"].astype("str")
            self.ddf_users = self.ddf_users.persist()
            dask.distributed.wait(self.ddf_users)

            if self.ddf_placement_users is not None:
                self.ddf_placement_users["src"] = self.ddf_placement_users["src"].astype("str")
                self.ddf_placement_users["dst"] = self.ddf_placement_users["dst"].astype("str")
                self.ddf_placement_users = self.ddf_placement_users.persist()
                dask.distributed.wait(self.ddf_placement_users)
        except Exception as e:
            self._columns_normalized = False
            raise RuntimeError(f"规范化节点字段类型失败: {e}")
        self._columns_normalized = True

    def _validate_no_virtual_root_in_users(self) -> None:
        """
        校验业务用户中不能出现 src == '0'。

        '0' 只能作为 parent / placementId 的哨兵根值使用，不能作为真实用户进入重算。
        """
        bad = self.ddf_users[self.ddf_users["src"] == "0"][["src", "dst"]]
        if (bad_count := self._count_ddf_rows(bad)) > 0:
            raise RuntimeError(f"图数据非法：存在 {bad_count} 个 src='0' 的虚拟推荐根节点。")

    def _validate_unique_user_parent(self) -> None:
        """
        校验推荐网中每个用户只能有一条 parent 记录。

        如果同一个 src 出现多条 parent，会导致 Root-Depth 构建与推荐网返利路径不唯一。
        """
        users = self.ddf_users[["src", "dst"]]
        grouped = users.groupby("src").agg({"dst": "count"}).reset_index()
        dup = grouped[grouped["dst"] > 1]
        if (dup_count := self._count_ddf_rows(dup)) > 0:
            raise RuntimeError(f"图数据非法：存在 {dup_count} 个用户拥有多条推荐网 parent 记录。")

    def _validate_parent_exists(self) -> None:
        """
        校验推荐网 parent != '0' 的父节点必须存在于用户全集。

        该校验用于发现断裂数据：某人指向了不存在的上级，会导致 Root-Depth 覆盖不完整。
        """
        users_src = self.ddf_users[["src"]].drop_duplicates().assign(_exists=1)
        parents = self.ddf_users[self.ddf_users["dst"] != "0"][["dst"]].rename(columns={"dst": "src"}).drop_duplicates()
        checked = parents.merge(users_src, on=["src"], how="left")
        missing = checked[checked["_exists"].isnull()][["src"]]
        if (missing_count := self._count_ddf_rows(missing)) > 0:
            raise RuntimeError(f"图数据非法：存在 {missing_count} 个推荐 parent 不在用户全集中。")

    def _validate_placement_integrity(self) -> None:
        """
        安置网（双轨制）排他性原则强校验！必须遵守铁律，否则直接熔断！
        """
        if self.ddf_placement_edges is None: return
        edges = self.ddf_placement_edges

        # 1. 腿位约束：不为空且只能在 1, 2 之中。
        invalid_legs = edges[(~edges["placementLeg"].isin([1, 2])) | (edges["placementLeg"].isnull())]
        if (bad_legs := self._count_ddf_rows(invalid_legs)) > 0:
            raise RuntimeError(f"安置图非法：存在 {bad_legs} 条连线的 placementLeg 为空或不是 1/2。")

        # 2. 单父级约束：一个人的头顶只能挂在唯一一个节点下。
        grouped_src = edges.groupby("src").agg({"dst": "count"}).reset_index()
        dup_src = grouped_src[grouped_src["dst"] > 1]
        if (dup_src_count := self._count_ddf_rows(dup_src)) > 0:
            raise RuntimeError(f"安置图非法：存在 {dup_src_count} 个用户被安置在了多个父节点下。")

        # 3. 坑位排他性：防“三头六臂”，一个上级的 Leg=1 只能容纳一个人！
        grouped_slot = edges.groupby(["dst", "placementLeg"]).agg({"src": "count"}).reset_index()
        dup_slot = grouped_slot[grouped_slot["src"] > 1]
        if (dup_slot_count := self._count_ddf_rows(dup_slot)) > 0:
            raise RuntimeError(f"安置图非法：双轨制冲突！存在 {dup_slot_count} 个坑位 (同祖先, 同Leg) 被多人霸占。")

        users_src_raw = self.ddf_users_raw[["src"]].copy()
        users_src_raw["src"] = users_src_raw["src"].astype("str")
        users_src = users_src_raw.drop_duplicates().assign(_exists=1)

        parents = edges[["dst"]].rename(columns={"dst": "src"}).drop_duplicates()
        parents["src"] = parents["src"].astype("str")

        checked = parents.merge(users_src, on=["src"], how="left")
        missing = checked[checked["_exists"].isnull()]
        if (missing_count := self._count_ddf_rows(missing)) > 0:
            raise RuntimeError(f"安置图非法：存在 {missing_count} 个安置父节点 (placementId) 根本不在用户表中。")

    def _build_children_index(self) -> None:
        """
        构建直属子节点分页索引。

        目标：
        - 避免 get_direct_children_page 每次都直接全表扫描 self.ddf_users。
        - 结果 self.ddf_users_by_dst 的列为 ["src", "dst"]。
        - 通过 shuffle(on="dst") 把同一父节点的数据尽量聚到相关分区。
        - 分区内按 ["dst", "src"] 排序，配合 keyset cursor 防止分页跳行、漏行或重复。

        注意：
        任何降级都会让 GlobalRecalculationService 静默算错，所以这里必须 fail-fast。
        """
        self._ensure_graph_loaded()
        self._normalize_graph_columns()
        if self.ddf_users_by_dst is not None: return
        try:
            # 先按父节点 dst 洗牌，再按 dst/src 做分区内排序。
            indexed = self.ddf_users[["src", "dst"]].drop_duplicates().shuffle(on="dst")
            self.ddf_users_by_dst = indexed.map_partitions(lambda df: df.sort_values(["dst", "src"])).persist()
            dask.distributed.wait(self.ddf_users_by_dst)
        except Exception as e:
            raise RuntimeError(f"构建分区分页子节点降级失败: {e}")

    def _build_root_depth_index(self) -> None:
        """
        构建推荐网 Root-Depth 索引。

        规则：
        - dst == '0' 的用户是根节点，depth = 0。
        - 子节点 depth = parent.depth + 1。
        - 如果最终 depth 覆盖数 != 用户全集数，说明存在环、无根子图或断裂数据。

        结果：
        - self.ddf_depths，columns = ["src", "depth"]。
        - GlobalRecalculationService 可从最大 depth 倒序分页处理用户，保证先处理子节点再处理父节点。
        """
        # region 验证 并对users中的src和dst去重
        self._ensure_graph_loaded()
        self._normalize_graph_columns()

        # 只保留推荐网必要字段，并去重避免脏重复边影响层级展开。
        users = self.ddf_users[["src", "dst"]].drop_duplicates()
        # endregion

        # region 统计出users的src一共有人多少人
        # 统计用户全集数量，后续用于判断 Root-Depth 是否覆盖全网。
        total_users = int(users[["src"]].drop_duplicates().map_partitions(len).sum().compute())
        if total_users <= 0: raise RuntimeError("系统全量节点总数异常为 0")
        # endregion

        # region 找出所有根节点：推荐网 parent/dst 为 '0'。
        roots = users[users["dst"] == "0"][["src"]].drop_duplicates().assign(depth=np.int32(0))
        if self._count_ddf_rows(roots) <= 0: raise RuntimeError("未检测到任何 parent=='0' 的根节点。")
        # endregion

        # region 创造visited和frontier
        # visited 保存已经分配 depth 的节点；frontier 保存当前层节点。
        depth_parts = [roots]
        visited = roots[["src"]].drop_duplicates().persist()
        frontier = roots[["src"]].drop_duplicates().persist()
        dask.distributed.wait(visited)
        dask.distributed.wait(frontier)
        # endregion

        # region 初始化
        visited_count = self._count_ddf_rows(visited)
        current_depth = 0
        max_possible_depth = total_users + 1
        # endregion

        while visited_count < total_users:
            current_depth += 1

            # region 验证
            # 理论上树的最大深度不可能超过 total_users；超过则大概率存在环。
            if current_depth > max_possible_depth: raise RuntimeError("拓扑结构产生环路，层级计算发生阻断")
            # endregion

            # region 创造parent_frontier -> 将frontier的src重命名为dst
            # 把当前 frontier 的 src 改名为 dst，用于和 users 表按 parent 匹配，找下一层 children。
            parent_frontier = frontier.rename(columns={"src": "dst"})
            # endregion

            # region 创造children -> 通过dst，parent_frontier联查user，找出它的所有下级
            children = users.merge(parent_frontier, on=["dst"], how="inner")[["src"]].drop_duplicates()
            # endregion

            # region 创造next_frontier -> 通过src children联查visited_flag，过滤_visited为null的数据
            # 过滤掉已经访问过的节点，防止重复层级或环导致无限扩展。
            visited_flag = visited.assign(_visited=1)
            next_frontier = children.merge(visited_flag, on=["src"], how="left")
            next_frontier = next_frontier[next_frontier["_visited"].isnull()][["src"]].drop_duplicates()
            # endregion

            # region 算出next_frontier的数量 等于0时跳出循环
            # 当前层没有新节点时跳出；后面会通过覆盖数检查判断是否存在断裂/无根子图。
            if self._count_ddf_rows(next_frontier) == 0: break
            # endregion

            # region 在next_frontier新增一列current_depth，将新增后的数据集添加到depth_parts
            # 给新层节点打 depth，并加入总的 depth_parts。
            depth_parts.append(next_frontier.assign(depth=np.int32(current_depth)))
            # endregion

            # region 将next_frontier添加到visited，并将visited重新发布dask
            # 更新 visited 与 frontier，并立即 persist，阻断 Dask 任务图无限叠加。
            visited = dask_cudf.concat([visited, next_frontier], interleave_partitions=False).drop_duplicates(
                subset=["src"]).persist()
            dask.distributed.wait(visited)
            # endregion

            # region 将next_frontier赋值给frontier
            frontier = next_frontier.persist()
            dask.distributed.wait(frontier)
            # endregion

            # region 重新赋值visited_count
            visited_count = self._count_ddf_rows(visited)
            # endregion

        # region 创造ddf_depths -> 将depth_parts按src去重，取第一次出现的depth，发布到dask
        # 合并所有层级结果，并按 src 去重，得到 Root-Depth 索引候选表。
        ddf_depths = dask_cudf.concat(depth_parts, interleave_partitions=False).drop_duplicates(subset=["src"])
        # endregion

        # region 验证
        # 覆盖数必须等于用户全集数；否则说明图中存在环、断裂或无根子图。
        depth_total = self._count_ddf_rows(ddf_depths)
        if depth_total != total_users:
            raise RuntimeError(f"图数据非法：Root-Depth 覆盖用户数 {depth_total} != 用户全集数 {total_users}。")
        # endregion

        # region 将ddf_depths重新分区 并按照"depth", "src"排序
        # 重新分区并按 depth/src 排序，为 get_nodes_at_depth_page 的稳定分页提供前提。
        nparts = getattr(self.ddf_users, "npartitions", 1) or 1
        try:
            self.ddf_depths = ddf_depths.repartition(npartitions=nparts).sort_values(["depth", "src"]).persist()
        except Exception as e:
            raise RuntimeError(f"深度矩阵排序崩溃: {e}")
        dask.distributed.wait(self.ddf_depths)
        # endregion

    def validate_graph_integrity(self) -> bool:
        """
        全局重算前的图数据校验入口。

        校验项：
        1. self.ddf_users 不为空，且 src/dst 类型已统一。
        2. src == '0' 不能作为真实业务用户出现。
        3. 推荐网每个 src 只能有一条 parent/dst 记录。
        4. parent != '0' 的父节点必须存在于用户全集。
        5. 安置网 placementLeg 必须合法、单父级、单坑位、安置父节点存在。
        6. Root-Depth 必须覆盖所有推荐网用户。
        7. children 分页索引必须能成功构建。
        """
        self._ensure_graph_loaded()
        self._normalize_graph_columns()
        self._validate_no_virtual_root_in_users()
        self._validate_unique_user_parent()
        self._validate_parent_exists()
        self._validate_placement_integrity()
        self._build_root_depth_index()
        self._build_children_index()
        return True

    def get_max_root_depth(self) -> int:
        """
        返回推荐网最大 Root-Depth。

        Root-Depth 定义：
        - 根节点 depth = 0。
        - 根的子节点 depth = 1。
        - 叶子节点 depth 最大。

        GlobalRecalculationService 通常从最大 depth 向 0 倒序重算。
        """
        if self.ddf_depths is None: self._build_root_depth_index()
        max_depth = self.ddf_depths["depth"].max().compute()
        return 0 if max_depth is None or pd.isna(max_depth) else int(max_depth)

    def _page_items_by_src_presorted(self, ddf, cursor: Optional[Any], limit: int) -> Dict[str, Any]:
        """
        基于已预排序数据的 keyset 分页工具。

        输入 ddf 必须：
        - 有 src 列。
        - 已经按照 src 升序排序，或在同一 parent/depth 范围内等价有序。

        关键点：
        - cursor 表示上一页最后一个 src。
        - 本页查询 src > cursor。
        - head(limit + 1, npartitions=-1) 用于判断是否还有下一页。
        - npartitions=-1 很重要：过滤 cursor 后目标行可能不在第 0 分区，默认只看第 0 分区会导致误判为空。
        """
        if limit <= 0: raise ValueError("limit 必须大于 0。")

        # 兼容 bytes cursor，避免 str(b'xxx') 变成 "b'xxx'"。
        if cursor is not None:
            cursor = str(cursor.decode("utf-8") if isinstance(cursor, bytes) else cursor)
            ddf = ddf[ddf["src"] > cursor]

        # 从所有分区取候选头部，再合并得到全局前 limit+1 条。
        pdf = ddf[["src"]].head(limit + 1, npartitions=-1).to_pandas()
        if pdf is None or len(pdf) == 0: return {"items": [], "next_cursor": None}

        raw_items = [str(x) for x in pdf["src"].tolist()]
        has_more = len(raw_items) > limit
        items = raw_items[:limit]
        next_cursor = items[-1] if has_more and items else None

        return {"items": items, "next_cursor": next_cursor}

    def get_nodes_at_depth_page(self, depth: int, cursor: Optional[Any], limit: int) -> Dict[str, Any]:
        """
        按 Root-Depth 分页返回节点。

        GlobalRecalculationService 会从 max_depth 倒序调用该方法；
        每次只拿一页，避免一次性把某层所有用户拉到 driver。
        """
        if self.ddf_depths is None: self._build_root_depth_index()
        return self._page_items_by_src_presorted(self.ddf_depths[self.ddf_depths["depth"] == int(depth)][["src"]],
                                                 cursor, limit)

    def get_direct_children_page(self, parent_id: str, cursor: Optional[Any], limit: int) -> Dict[str, Any]:
        """
        按 parent_id 分页返回直属 child。

        关键：
        - 不返回 parent 的全部 children。
        - 每次最多返回 limit 个 child id。
        - 使用 self.ddf_users_by_dst，避免每次直接扫 self.ddf_users。
        """
        if self.ddf_users_by_dst is None: self._build_children_index()
        return self._page_items_by_src_presorted(
            self.ddf_users_by_dst[self.ddf_users_by_dst["dst"] == str(parent_id)][["src"]], cursor, limit)

    def get_allparent(self, src):
        """
        兼容旧接口：返回推荐网所有祖先。

        旧版 get_allparent 直接基于 self.dg 做 BFS；
        新版 self.dg 等价于 dg_sponsor，因此委托给 get_all_parents_sponsor。
        """
        return self.get_all_parents_sponsor(src)

    def get_ddf_edges(self):
        """返回当前推荐网有效边表，columns 通常为 ["src", "dst"]。"""
        return self.ddf_edges

    # 在 GraphService.py 中补充此方法：
    def get_placement_edges(self) -> dask_cudf.DataFrame:
        """提供安置网有效边表供外部计算使用"""
        if self.ddf_placement_edges is None:
            raise RuntimeError("安置网尚未初始化。")
        return self.ddf_placement_edges

    def get_all_parents_sponsor(self, src) -> pd.DataFrame:
        """
        查询指定节点在推荐网 Sponsor Tree 中的全部祖先。

        输出列：
        - ancestor：祖先节点 id。
        - level：与 src 的距离，1 表示直接 parent。
        """
        # 执行分布式 BFS
        df_bfs = dask_bfs.bfs(self.dg_sponsor, str(src))
        # 过滤无穷/空距离，并把列改名
        df_bfs = df_bfs[df_bfs["distance"].notnull() & (df_bfs["distance"] > 0) & (df_bfs["distance"] != INF)]
        return df_bfs.rename(columns={"vertex": "ancestor", "distance": "level"}).compute().to_pandas()

    def get_all_parents_placement(self, src) -> pd.DataFrame:
        """
        查询指定节点在安置网 Placement Tree 中的全部祖先。

        该方法只返回 BFS 层级，不计算 leg；
        如需查看每层祖先对应的 placementLeg，请使用 get_placement_leg_path。
        """
        df_bfs = dask_bfs.bfs(self.dg_placement, str(src))
        df_bfs = df_bfs[df_bfs["distance"].notnull() & (df_bfs["distance"] > 0) & (df_bfs["distance"] != INF)]
        return df_bfs.rename(columns={"vertex": "ancestor", "distance": "level"}).compute().to_pandas()

    def get_direct_children_batch(self, parent_ids: List[str]) -> Dict[str, List[str]]:
        """
        批量返回多个父节点的直属下级。

        返回格式：
            {parent_id: [direct_child_id, ...]}

        旧版实现使用 cudf merge 内连接过滤边表；新版保持该方式以便一次性查询多个 parent。
        """
        if self.ddf_users is None or not parent_ids: return {str(p): [] for p in parent_ids}
        pids = cudf.DataFrame({"dst": [str(p) for p in parent_ids]})
        pids_ddf = dask_cudf.from_cudf(pids, npartitions=1)
        edges = self.ddf_users.merge(pids_ddf, on=["dst"], how="inner")
        pdf = edges[["dst", "src"]].compute().to_pandas()
        pdf["dst"] = pdf["dst"].astype(str)
        pdf["src"] = pdf["src"].astype(str)
        out: Dict[str, List[str]] = {str(p): [] for p in parent_ids}
        for _, row in pdf.iterrows(): out[row["dst"]].append(row["src"])
        return out

    # =====================================================================
    # 订单处理与返利分配接口 (兼容极差与代数逻辑) demo
    # =====================================================================
    def run_bfs(self, orderList: List[OrderPayload], batch_size_param: int = 16, nparts: int = 1):
        """
        根据订单用户计算所有推荐网上级的层级返利。

        旧版 GraphService_bak3.py 的执行逻辑：
        - 对每个买家 batch，针对每个源节点执行分布式 BFS。
        - 合并 batch 内 BFS 结果为 df_bfs_batch。
        - 与订单表 ddf_orders / ddf_pur 做分布式 JOIN。
        - 按层级匹配 RATE_PPM，使用整数 ppm 计算佣金，避免浮点误差。
        - 每个 batch 内先按 ancestor + level 聚合，再将所有 batch 做最终 reduce。

        新版保持该接口向下兼容：
        - self.dg 仍指向推荐网 dg_sponsor。
        - user_id 最终转回 int64，保持旧下游接口契约。
        - 该方法不参与双轨制 1L/2L，它只负责推荐网层级返利。
        """
        client = get_client()
        runLock = Lock(self._global_lock_name, client=client)
        gotLock = runLock.acquire(timeout=15)

        agg_meta = cudf.DataFrame({
            "user_id": cudf.Series(dtype="int64"), "level": cudf.Series(dtype="int32"),
            "rate": cudf.Series(dtype="int64"), "total_amount": cudf.Series(dtype="int64"),
            "total_commission": cudf.Series(dtype="int64"),
        })

        # 【空订单拦截】 直接阻断空数组，防止下文 cudf.DataFrame(rows) 产生无列报错
        if not orderList:
            if gotLock:
                try:
                    runLock.release()
                except Exception:
                    pass
            return agg_meta.head(0)

        if not gotLock: return agg_meta.head(0)

        # 【静默空跑拦截】 坚决杜绝因图加载失败、dg为None导致的静默吞单（返回零佣金）
        if self.dg is None:
            if gotLock:
                try:
                    runLock.release()
                except Exception:
                    pass
            raise RuntimeError("推荐网图尚未加载（可能上次构图失败已被清理），拒绝计算返利！")

        try:
            RATE_PPM = RatesService().get_rates_ppm_cached_strict(client)
            buyers, rows = [], []
            for idx, o in enumerate(orderList):
                # 【全链路字符化】将订单的 userid 转为字符串，避免与底图 str 顶点类型错位导致 BFS 查无此人
                rows.append({"purchase_id": idx, "buyer": str(o.userid), "amount": int(Decimal(o.amount) * 100),
                             "orderid": o.orderid})
                buyers.append(str(o.userid))

            ddf_orders = dask_cudf.from_cudf(cudf.DataFrame(rows), npartitions=nparts)
            ddf_orders = client.persist(ddf_orders)
            dask_wait(futures_of(ddf_orders))

            # 将待处理用户拆成多个 batch，避免一次性 BFS 源节点过多造成调度压力。
            buyer_batches = chunk_list(buyers, batch_size_param)
            batch_agg_parts = []

            for i, batch in enumerate(buyer_batches):
                try:
                    ddf_pur = ddf_orders[ddf_orders["buyer"].isin(batch)][["purchase_id", "buyer", "amount"]]
                except Exception:
                    continue

                try:
                    total_pur = int(ddf_pur.map_partitions(len).sum().compute())
                except Exception:
                    total_pur = 0
                if total_pur == 0: continue

                # 对 batch 内每个买家分别跑推荐网上行 BFS，取出所有祖先及距离 level。
                bfs_parts = []
                for src in batch:
                    try:
                        df_bfs = dask_bfs.bfs(self.dg, str(src))
                    except Exception:
                        continue
                    df_bfs = df_bfs[
                        df_bfs["distance"].notnull() & (df_bfs["distance"] != INF) & (df_bfs["distance"] >= 1)]
                    df_bfs = df_bfs.assign(source=str(src)).rename(columns={"vertex": "ancestor", "distance": "level"})
                    bfs_parts.append(df_bfs[["ancestor", "level", "source"]])

                if not bfs_parts: continue

                # 合并本 batch 的 BFS 结果，并统一 join key 类型，避免 int/str 混用导致 join 为空。
                df_bfs_batch = dask_cudf.concat(bfs_parts)
                df_bfs_batch["source"] = df_bfs_batch["source"].astype("str")
                df_bfs_batch["ancestor"] = df_bfs_batch["ancestor"].astype("str")
                ddf_pur["buyer"] = ddf_pur["buyer"].astype("str")

                df_bfs_batch = client.persist(df_bfs_batch);
                ddf_pur = client.persist(ddf_pur)
                wait_collections(df_bfs_batch, ddf_pur)

                # 分布式极速内连接，计算提成
                joined = df_bfs_batch.merge(ddf_pur, left_on="source", right_on="buyer", how="inner")

                def _add_rate_and_comm(df_part: cudf.DataFrame) -> cudf.DataFrame:
                    # 空分区必须返回与 meta 完全一致的 schema，防止 Dask-cuDF 推断失败。
                    if df_part.shape[0] == 0: return cudf.DataFrame(
                        {"purchase_id": cudf.Series(dtype="int64"), "buyer": cudf.Series(dtype="str"),
                         "amount": cudf.Series(dtype="int64"), "ancestor": cudf.Series(dtype="str"),
                         "level": cudf.Series(dtype="int32"), "rate": cudf.Series(dtype="int64"),
                         "commission": cudf.Series(dtype="int64")})
                    try:
                        df_part["level"] = df_part["level"].astype("int32")
                    except Exception:
                        pass
                    df_part["rate"] = df_part["level"].map(RATE_PPM).fillna(0).astype("int64")
                    # 整数实现四舍五入：
                    # amount 单位为分，rate 单位为 ppm；(amount * ppm + 500000) // 1000000。
                    df_part["commission"] = ((df_part["amount"] * df_part["rate"]) + 500_000) // 1_000_000
                    return df_part[["purchase_id", "buyer", "amount", "ancestor", "level", "rate", "commission"]]

                meta = cudf.DataFrame({"purchase_id": cudf.Series(dtype="int64"), "buyer": cudf.Series(dtype="str"),
                                       "amount": cudf.Series(dtype="int64"), "ancestor": cudf.Series(dtype="str"),
                                       "level": cudf.Series(dtype="int32"), "rate": cudf.Series(dtype="int64"),
                                       "commission": cudf.Series(dtype="int64")})
                detail_ddf = client.persist(joined.map_partitions(_add_rate_and_comm, meta=meta))
                dask_wait(futures_of(detail_ddf))

                try:
                    agg_ddf = detail_ddf.groupby(["ancestor", "level"]).agg(
                        {"amount": "sum", "commission": "sum"}).reset_index()
                except Exception:
                    continue

                def _attach_rate_and_rename(df_part: cudf.DataFrame) -> cudf.DataFrame:
                    try:
                        df_part["level"] = df_part["level"].astype("int32")
                    except Exception:
                        pass
                    df_part["rate"] = df_part["level"].map(RATE_PPM).fillna(0).astype("int64")
                    df_part = df_part.rename(
                        columns={"ancestor": "user_id", "amount": "total_amount", "commission": "total_commission"})

                    try:
                        # 【底层强转容错与日志告警】: 绝不静默丢弃，而是保留异常信息并切为安全值(0)，保障 cudf.astype() 不因包含字母宕机
                        if df_part["user_id"].dtype == "object" or str(df_part["user_id"].dtype) == "string":
                            is_numeric_mask = df_part["user_id"].str.isnumeric().fillna(False)
                            invalid_count = (~is_numeric_mask).sum()
                            if invalid_count > 0:
                                print(
                                    f"WARNING: Detected {invalid_count} non-numeric user_id records. Casting to 0 to prevent pipeline crash.")

                            # 托底方案：非法字母账号转为 "0"，交由下游发佣服务处理。
                            df_part["user_id"] = df_part["user_id"].where(is_numeric_mask, "0")

                        # 返回给下游时，将最终的 user_id 转回 int64 保持原版输出结构契约
                        df_part["user_id"] = df_part["user_id"].astype("int64")
                    except Exception as e:
                        print(f"ERROR: Cast failed in attach_rate: {e}")

                    return df_part[["user_id", "level", "rate", "total_amount", "total_commission"]]

                agg_out = client.persist(agg_ddf.map_partitions(_attach_rate_and_rename, meta=agg_meta))
                dask_wait(futures_of(agg_out))
                batch_agg_parts.append(agg_out)

            if not batch_agg_parts: return agg_meta.head(0)

            # loop 结束后，合并所有 batch 的聚合结果，再做一次全局 reduce。
            full_agg_concat = dask_cudf.concat(batch_agg_parts, interleave_partitions=False)
            for col, dtype in agg_meta.dtypes.items():
                try:
                    full_agg_concat[col] = full_agg_concat[col].astype(dtype)
                except Exception:
                    pass

            final_agg_ddf = full_agg_concat.groupby(["user_id", "level"]).agg(
                {"total_amount": "sum", "total_commission": "sum"}).reset_index()
            final_agg_ddf = client.persist(final_agg_ddf)
            dask_wait(futures_of(final_agg_ddf))

            return final_agg_ddf.compute()
        finally:
            try:
                runLock.release()
            except Exception:
                pass

    def descendant_counts_via_bfs(self, src, max_depth: int = None):
        """
        计算指定用户在推荐网中每一代子孙数量。

        返回 pandas DataFrame：
        - level：代数 / BFS distance，1 表示直属子节点。
        - count：该代节点数量。

        如果 max_depth 非 None，则只统计到指定最大深度。
        """
        df_bfs = dask_bfs.bfs(self.dg_rev, str(src))
        df_bfs = df_bfs[df_bfs["distance"].notnull() & (df_bfs["distance"] != INF) & (df_bfs["distance"] > 0)]
        df_bfs = df_bfs.rename(columns={"vertex": "descendant", "distance": "level"})
        if max_depth is not None: df_bfs = df_bfs[df_bfs["level"] <= int(max_depth)]
        agg = df_bfs.groupby("level").agg({"descendant": "count"}).reset_index()
        result = agg.compute().sort_values("level").rename(columns={"descendant": "count"})
        result["level"] = result["level"].astype(int);
        result["count"] = result["count"].astype(int)
        return result
