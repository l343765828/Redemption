"""
分布式 cugraph.dask BFS + 佣金计算（基于 JOIN 连接）—— 按批次聚合版本。

执行逻辑:
- 对每个买家批次:
    - 针对每个源节点运行分布式 BFS，将 BFS 结果合并为 df_bfs_batch
    - join df_bfs_batch with purchases (distributed)
    - 计算每笔交易的详细信息（费率、佣金）
    - 计算每批次聚合结果（祖先节点，层级）→（总金额，总佣金）

Usage:
  python cugraph_dask_distributed_bfs_join_agg_by_batch.py --scheduler tcp://<SCHED_IP>:8786 \
      --model-dir /mnt --out-dir /mnt/out --batch-size 32 --npartitions 4
"""
from typing import List
import dask
import dask_cudf
import cudf
import cugraph
from cugraph.dask.traversal import bfs as dask_bfs
import numpy as np
from deltalake import DeltaTable
from dask.distributed import Client, Lock, get_client, wait as dask_wait, futures_of
from Model.Order.OrderPayload import OrderPayload
from decimal import Decimal
import cugraph.dask.comms.comms as Comms
import gc
import cupy as cp
from distributed import Future
import pandas as pd
from Model.User.ChangeUserMsg import ChangeUserMsg
from Until.Common import read_delta_snapshot_files
from Rates.RatesService import RatesService
import logging


def futures_flatten(*collections) -> List[Future]:
    """
    将若干 dask collection（或 futures 列表）扁平化为 List[Future]。
    兼容 futures_of() 返回单个 Future 或 list[Future] 的情况。
    """
    out = []
    for c in collections:
        f = futures_of(c)  # 可能返回 Future 或 List[Future]
        # 兼容单个 Future 的情况
        if isinstance(f, (list, tuple, set)):
            out.extend(list(f))
        else:
            out.append(f)
    return out


def wait_collections(*collections, timeout=None):
    """
    方便用法：等待若干 dask collection（或 futures 列表）在集群上 materialize 完成。
    使用示例： wait_collections(df_bfs_batch, ddf_pur)
    """
    futures = futures_flatten(*collections)
    if not futures:
        return
    dask_wait(futures, timeout=timeout)


def _worker_cleanup_existing_graph_service():
    """
    在 worker 上清理“真实存在的资源”，而不是新建一个 GraphService()。
    使用顺序：
    1. 如果 worker 上存在持久的 GraphService 实例（globals 里），调用它的 cleanup()
    2. 否则 fallback：直接销毁 cugraph comms + cupy memory pool（强制回收）
    """

    # 1) 尝试清理已有 GraphService 实例
    try:
        gs = globals().get("_graph_service_instance", None)
        if isinstance(gs, GraphService):
            try:
                gs.cleanup()
                print("Worker: existing GraphService.cleanup() called")
                return
            except Exception as e:
                print("Worker: existing GraphService.cleanup() failed:", e)
    except Exception as e:
        print("Worker: checking existing GraphService failed:", e)

    # 2) fallback：强制销毁底层资源
    try:
        if Comms.is_initialized():
            Comms.destroy()
            print("Worker: Comms.destroy() called (fallback)")
    except Exception as e:
        print("Worker: Comms.destroy() failed (fallback):", e)

    try:
        gc.collect()
        cp.get_default_memory_pool().free_all_blocks()
        print("Worker: cupy memory pool freed (fallback)")
    except Exception as e:
        print("Worker: cupy cleanup failed (fallback):", e)


def chunk_list(lst: List[int], chunk_size: int) -> List[List[int]]:
    if chunk_size <= 0:
        return [lst]
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


# 根据本地的版本号和消息的版本号对比是否需要重新加载数据
def need_reload(model_dir, msg_version):
    dt = DeltaTable(model_dir)
    print(f"dt.version():{dt.version()},parse_args().msg_version:{int(msg_version)}")
    return dt.version() >= int(msg_version)


# 给小表分区，并增加删除标志
def to_broadcast_ddf(small_df: cudf.DataFrame, flag_col=None) -> cudf.DataFrame:
    if flag_col:
        small_df[flag_col] = 1
    return small_df


INF = np.iinfo(np.int32).max
users_cdc_version = "users_cdc_version"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
LOG = logging.getLogger("User.GraphService")


class GraphService:

    def __init__(self):
        self.msg_version = -1
        self.dg = None
        self.dg_rev = None
        self.ddf_users = None
        self.ddf_edges = None
        self._global_lock_name = "graph_service_lock"

    # 获取当前用户数据的版本
    @staticmethod
    def get_current_published_version(client) -> int:
        try:
            return int(client.get_dataset("users_version"))
        except Exception:
            return -1

    # 获取CDC的version
    @staticmethod
    def get_current_published_cdc_version(client) -> int:
        try:
            return int(client.get_dataset(users_cdc_version))
        except Exception:
            return -1

    def cleanup(self):
        """ Cleanup method to destroy comms and release memory """

        # region 释放Comms
        try:
            self.dg = None
            self.dg_rev = None
            # 包含所有用户的关系表
            self.ddf_users = None
            # 剔除没有上级的关系表
            self.ddf_edges = None
            self.msg_version = -1
            if Comms.is_initialized():
                Comms.destroy()  # 清理 comms，防止内存泄漏
                print("Comms destroyed during cleanup.")
        except Exception as e:
            print("Failed to destroy comms during cleanup:", e)
        # endregion

        # 手动触发 GC 清理内存
        gc.collect()

        # region 释放GPU的内存
        try:
            # try freeing cupy memory pool to release GPU memory
            cp.get_default_memory_pool().free_all_blocks()
            print("Worker: cupy memory pool freed.")
        except Exception as e:
            print("Worker: freeing cupy memory pool failed: %s", e)
        # endregion

    def cleanup_cluster(self, client=None):
        """
        对整个集群执行 cleanup（外部调用场景）
        - driver 调用
        - 实际 cleanup 在各 worker 上执行
        """
        if client is None:
            client = get_client()

        client.run(_worker_cleanup_existing_graph_service)

    # 将delta数据加载至GPU，创建分布式图（有向图、反向图）
    def run(self, msg_version: int, model_dir: str, npartitions: int = 0,
            renumber_disable: bool = True):
        client = get_client()
        runLock = Lock(self._global_lock_name, client=client)
        if runLock.acquire(timeout=15):

            # region 初始化前销毁旧资源
            try:
                # 在所有 worker 上执行 cleanup 来销毁已有的 comms 和清理内存
                client.run(_worker_cleanup_existing_graph_service)
                print("Comms destroyed and cleanup completed before initialization.")
            except Exception as e:
                print("Warning: failed to destroy comms during pre-initialization:", e)
            # endregion

            # region 基础参数赋值
            isReload = False
            current_version = self.get_current_published_version(client)
            msg_version = int(msg_version)
            lock_name = f"reload:{msg_version}"
            lock = Lock(lock_name, client=client)
            # endregion

            # region double check:first 上锁成功 并且 second check成功 才reload
            print(f"current_version: {current_version},msg_version:{msg_version}")
            # first：判断schedule中的版本号低于消息的版本号
            if current_version < msg_version:
                print("first check is ok")
                if lock.acquire(timeout=15):
                    print("上锁成功")
                    # double check:second
                    # 判断schedule中的版本号低于消息的版本号
                    # 判断本地delta的版本号是否大于等于消息的版本号
                    if self.get_current_published_version(client) < msg_version and need_reload(model_dir,
                                                                                                msg_version):
                        isReload = True
                    else:
                        lock.release()
            print(f"是否reload：{isReload}")
            # endregion

            if isReload:

                # region 0）获取工作节点的数量
                sched_info = client.scheduler_info()
                # 避免 dict_keys 序列化问题
                worker_addrs = list(sched_info.get("workers", {}).keys())
                n_workers = len(worker_addrs)
                print(f"Detected {n_workers} workers")
                # endregion

                # region 1) Read edge list as dask_cudf
                print("Reading edge list with dask_cudf.read_parquet ...")
                ddf_users, current_version_local = read_delta_snapshot_files(model_dir,
                                                                             cols=["id", "user", "parent",
                                                                                   "updatetime"],
                                                                             npartitions=npartitions)
                # 过滤出有上级的用户
                ddf_edges = ddf_users[ddf_users["parent"] != "0"].rename(columns={"user": "src", "parent": "dst"})
                ddf_users = ddf_users.rename(columns={"user": "src", "parent": "dst"})

                # region partitioning 当没设置npartitions时，将ddf_edges重新分区，分区数为GPU的数量
                nparts = npartitions if npartitions > 0 else max(1, n_workers)
                try:
                    if getattr(ddf_edges, "npartitions", 1) != nparts:
                        print(f"Repartitioning edges to {nparts} partitions (one per GPU/worker)")
                        ddf_edges = ddf_edges.repartition(npartitions=nparts)
                        ddf_users = ddf_users.repartition(npartitions=nparts)
                except Exception as e:
                    print("Warning: repartition failed:", e)
                print("ddf_edges npartitions:", getattr(ddf_edges, "npartitions", None))
                # endregion

                # region 触发计算并将结果缓存到分布式内存中
                ddf_users = ddf_users.persist()
                ddf_edges = ddf_edges.persist()
                dask.distributed.wait(ddf_edges)
                dask.distributed.wait(ddf_users)
                # endregion

                # region init cugraph dask comms
                client.wait_for_workers(max(1, n_workers))
                try:
                    Comms.initialize()
                    print("cugraph.dask Comms initialized")
                except Exception as e:
                    print("Warning: failed to initialize cugraph.dask Comms:", e)
                # endregion
                # endregion

                # region 2) Build distributed cugraph Graph
                import time
                # 记录开始时间
                start_time = time.perf_counter()

                # region 创建有向图、反向图、用户List
                print("Building distributed Graph from dask_cudf edgelist ...")
                dg = cugraph.Graph(directed=True)
                dg.from_dask_cudf_edgelist(ddf_edges, source="src", destination="dst", renumber=(not renumber_disable))
                self.dg = dg

                print("Building reversed distributed Graph from dask_cudf edgelist ...")
                dg_rev = cugraph.Graph(directed=True)
                # 这里把 source/destination 互换：parent -> user
                dg_rev.from_dask_cudf_edgelist(ddf_edges, source="dst", destination="src",
                                               renumber=(not renumber_disable))
                self.dg_rev = dg_rev
                self.ddf_users = ddf_users
                self.ddf_edges = ddf_edges
                # endregion

                # 记录结束时间
                end_time = time.perf_counter()

                # 计算并打印耗时
                elapsed = end_time - start_time
                print(f"图构建耗时: {elapsed:.4f} 秒")
                print("Distributed Graph built.")
                # endregion

                # region 验证数据
                # 注意：如果表很大，不要立刻 persist 全表
                ddf_users = ddf_users.persist()
                dask.distributed.wait(ddf_users)

                full_df = ddf_users.compute()
                print(f"\n==== FULL DATA ({len(full_df)} ROWS) ====")
                print(full_df.to_string())  # cuDF 的 to_string() 方法
                total = ddf_users.map_partitions(len).sum().compute()
                print("total rows (dask,sum):", total)
                # endregion

                # region 3）将版本号发布到schedule
                print("client start")
                print(f"current_version_local: {current_version_local}")
                # 在 publish 前确保同名 dataset 不存在
                ds_version = "users_version"
                try:
                    # 尝试显式取消已有 dataset（若不存在会抛异常）
                    client.unpublish_dataset(ds_version)
                    print(f"Unpublished existing dataset: {ds_version}")
                except Exception:
                    # 忽略找不到或其它小错误
                    pass
                client.publish_dataset(**{ds_version: current_version_local})
                # endregion

                try:
                    lock.release()
                except Exception:
                    pass
                finally:
                    try:
                        runLock.release()
                    except Exception as e:
                        print("Warning: client.close() failed:", e)

                print("Done.")

    # 根据订单用户计算所有上级的返利
    def run_bfs(self, orderList: List[OrderPayload], batch_size_param: int = 16, nparts: int = 1):
        """
        对给定订单列表按 batch 做 BFS 并聚合返利结果。
        IMPROVEMENT: 使用整数 ppm 防止浮点误差；加强内存释放；异常安全的锁释放。
        """
        client = get_client()
        runLock = Lock(self._global_lock_name, client=client)
        gotLock = runLock.acquire(timeout=15)
        agg_meta = cudf.DataFrame({
            "user_id": cudf.Series(dtype="int64"),
            "level": cudf.Series(dtype="int32"),
            "rate": cudf.Series(dtype="int64"),
            "total_amount": cudf.Series(dtype="int64"),
            "total_commission": cudf.Series(dtype="int64"),
        })

        if not gotLock:
            print("WARNING: failed to acquire runLock, another run may be in progress")
            return agg_meta.head(0)

        if gotLock:
            try:

                # region 初始化，并将浮点费率转换为整数 ppm（parts-per-million），以便进行整数运算避免浮点误差
                # 计算方法：rate_ppm = int(round(rate_float * 1_000_000))
                # 例如：0.05 -> 0.05 * 1_000_000 = 50000 => 50000 ppm
                # rates = {1: 0.05, 2: 0.02, 3: 0.01}
                # RATE_PPM = {level: int(round(rate * 1_000_000)) for level, rate in rates.items()}
                RATE_PPM = RatesService().get_rates_ppm_cached_strict(client)
                print(f"打印PPM：", RATE_PPM)
                buyers = []
                rows = []
                # endregion

                for idx, o in enumerate(orderList):
                    rows.append({"purchase_id": idx, "buyer": int(o.userid), "amount": int(Decimal(o.amount) * 100),
                                 "orderid": o.orderid})
                    buyers.append(int(o.userid))

                # region 用 cudf 创建 DataFrame
                cudf_orders = cudf.DataFrame(rows)
                ddf_orders = dask_cudf.from_cudf(cudf_orders, npartitions=nparts)
                ddf_orders = client.persist(ddf_orders)
                dask_wait(futures_of(ddf_orders))
                # endregion

                # region 将待处理的用户ID列表按指定大小分割成多个批次
                # 买家ID列表buyers = [1001, 1002, 1003, 1004, 1005, 1006, 1007]
                # self.chunk_list(buyers, 3) → [[1001, 1002, 1003], [1004, 1005, 1006], [1007]]
                batch_size = batch_size_param
                buyer_batches = chunk_list(buyers, batch_size)
                # endregion

                batch_agg_parts = []
                for i, batch in enumerate(buyer_batches):
                    print(f"Processing batch {i + 1}/{len(buyer_batches)} (sources: {len(batch)})")

                    # region 为本 batch 构造 ddf_pur（基于 ddf_orders 过滤）
                    try:
                        ddf_pur = ddf_orders[ddf_orders["buyer"].isin(batch)]
                        # 如果想只保留特定列：
                        ddf_pur = ddf_pur[["purchase_id", "buyer", "amount"]]
                    except Exception as e:
                        print("WARNING: ddf_orders filtering failed, attempting fallback local filter:", e)
                    # endregion

                    # region 如果没有购买行，则跳过
                    try:
                        total_pur = int(ddf_pur.map_partitions(len).sum().compute())
                    except Exception:
                        total_pur = 0
                    if total_pur == 0:
                        print(f"  No purchases for this batch, skipping.")
                        continue
                    # endregion

                    # region 获取当前批次的用户关系数据
                    bfs_parts = []
                    for src in batch:

                        # region 计算当前用户和上级的距离
                        print(f"  BFS for source: {src}")
                        try:
                            df_bfs = dask_bfs.bfs(self.dg, src)
                        except Exception as e:
                            print(f"  BFS failed for source {src}: {e}")
                            continue
                        # endregion

                        # region 过滤出有上级的数据
                        df_bfs = df_bfs[df_bfs["distance"].notnull()]
                        df_bfs = df_bfs[df_bfs["distance"] != INF]
                        df_bfs = df_bfs[
                            (df_bfs["distance"] >= 1) & (df_bfs["distance"] < INF) & (df_bfs["distance"] != INF) & (
                                df_bfs["distance"].notnull())]
                        # endregion

                        # region 整理列名
                        df_bfs = df_bfs.assign(source=src)
                        df_bfs = df_bfs.rename(columns={"vertex": "ancestor", "distance": "level"})
                        df_bfs = df_bfs[["ancestor", "level", "source"]]
                        print(df_bfs.head(50))
                        # endregion

                        bfs_parts.append(df_bfs)

                    if len(bfs_parts) == 0:
                        print("  No BFS results in this batch, skipping.")
                        continue
                    # endregion

                    # region 将订单表 用户关系表分配到个worker的内存中
                    # concat batch bfs
                    df_bfs_batch = dask_cudf.concat(bfs_parts)

                    # Diagnostics & robustness: ensure dtypes and persist
                    df_bfs_batch["source"] = df_bfs_batch["source"].astype("int64")
                    df_bfs_batch["ancestor"] = df_bfs_batch["ancestor"].astype("int64")
                    ddf_pur["buyer"] = ddf_pur["buyer"].astype("int64")

                    df_bfs_batch = client.persist(df_bfs_batch)
                    ddf_pur = client.persist(ddf_pur)
                    wait_collections(df_bfs_batch, ddf_pur)
                    # endregion

                    # region join (distributed)
                    print("  Performing distributed join between batch-bfs and purchases ...")
                    joined = df_bfs_batch.merge(ddf_pur, left_on="source", right_on="buyer", how="inner")

                    # quick check joined count
                    try:
                        jc = int(joined["purchase_id"].count().compute())
                        print(f"  joined rows for batch {i}: {jc}")
                    except Exception as e:
                        print("  failed counting joined rows:", e)

                    # endregion

                    # region 根据订单金额、汇率，计算出返利金额，并重整表格
                    def _add_rate_and_comm(df_part: cudf.DataFrame) -> cudf.DataFrame:
                        if df_part.shape[0] == 0:
                            return cudf.DataFrame({
                                "purchase_id": cudf.Series(dtype="int64"),
                                "buyer": cudf.Series(dtype="int64"),
                                "amount": cudf.Series(dtype="int64"),
                                "ancestor": cudf.Series(dtype="int64"),
                                "level": cudf.Series(dtype="int32"),
                                "rate": cudf.Series(dtype="int64"),
                                "commission": cudf.Series(dtype="int64"),
                            })
                        try:
                            df_part["level"] = df_part["level"].astype("int32")
                        except Exception:
                            pass
                        df_part["rate"] = df_part["level"].map(RATE_PPM).fillna(0).astype("int64")
                        # 整数实现 (四舍五入): (amount_cents * rate_ppm + 500_000) // 1_000_000
                        df_part["commission"] = ((df_part["amount"] * df_part["rate"]) + 500_000) // 1_000_000
                        return df_part[["purchase_id", "buyer", "amount", "ancestor", "level", "rate", "commission"]]

                    # endregion

                    # region 重新定义数据结构，并在每个分区执行计算
                    meta = cudf.DataFrame({
                        "purchase_id": cudf.Series(dtype="int64"),
                        "buyer": cudf.Series(dtype="int64"),
                        "amount": cudf.Series(dtype="int64"),
                        "ancestor": cudf.Series(dtype="int64"),
                        "level": cudf.Series(dtype="int32"),
                        "rate": cudf.Series(dtype="int64"),
                        "commission": cudf.Series(dtype="int64"),
                    })

                    detail_ddf = joined.map_partitions(_add_rate_and_comm, meta=meta)

                    # persist detail_ddf to materialize before further ops
                    detail_ddf = client.persist(detail_ddf)
                    dask_wait(futures_of(detail_ddf))

                    print("打印detail_ddf")
                    print(detail_ddf.head(100))
                    # endregion

                    # region 在Worker节点上执行按批次聚合，并写入聚合分区结果
                    # 按祖先节点（ancestor）和层级（level）分组，计算金额（amount）总和与佣金（commission）总和
                    try:
                        agg_ddf = detail_ddf.groupby(["ancestor", "level"]).agg(
                            {"amount": "sum", "commission": "sum"}).reset_index()
                    except Exception as e:
                        # fallback: compute via map_partitions if groupby fails unexpectedly
                        print("  WARNING: groupby on detail_ddf failed, attempting fallback aggregation:", e)

                    # endregion

                    # region 重新定义数据格式 并将表格字段重命名
                    def _attach_rate_and_rename(df_part: cudf.DataFrame) -> cudf.DataFrame:
                        try:
                            df_part["level"] = df_part["level"].astype("int32")
                        except Exception:
                            pass
                        df_part["rate"] = df_part["level"].map(RATE_PPM).fillna(0).astype("int64")
                        df_part = df_part.rename(
                            columns={"ancestor": "user_id", "amount": "total_amount", "commission": "total_commission"})
                        return df_part[["user_id", "level", "rate", "total_amount", "total_commission"]]

                    agg_out = agg_ddf.map_partitions(_attach_rate_and_rename, meta=agg_meta)

                    # persist then write per-batch aggregate
                    agg_out = client.persist(agg_out)
                    dask_wait(futures_of(agg_out))
                    # endregion

                    batch_agg_parts.append(agg_out)

                    # region 数据验证
                    try:
                        # columns / dtypes (meta-level)
                        print(f"DEBUG: agg_out.columns (batch {i}):", list(agg_out.columns))
                        print(f"DEBUG: agg_out.dtypes (batch {i}):\n", agg_out.dtypes)
                        # head: 5 rows from distributed frame (should be cheap)
                        try:
                            head = agg_out.head(50)
                            print(f"DEBUG: agg_out.head (batch {i}):\n", head)
                        except Exception as e:
                            print(f"DEBUG: agg_out.head failed for batch {i}: {e}")
                    except Exception as e:
                        print("DEBUG: overall agg_out inspection failed:", e)
                    # endregion

                # region 数据检查
                if len(batch_agg_parts) == 0:
                    print("No batch aggregates produced; returning empty result.")
                    # 返回空的 cudf DataFrame，保持返回类型一致
                    empty = cudf.DataFrame({
                        "user_id": cudf.Series(dtype="int64"),
                        "level": cudf.Series(dtype="int32"),
                        "rate": cudf.Series(dtype="int64"),
                        "total_amount": cudf.Series(dtype="int64"),
                        "total_commission": cudf.Series(dtype="int64"),
                    })
                    return empty
                print("Merging per-batch aggregate parts into final aggregate...")
                # endregion

                # region loop 结束后，合并所有 batch 的 agg parts 并做最终 reduce（按 user_id, level 聚合）
                # region 将多个节点dask dataframe组合
                if len(batch_agg_parts) == 0:
                    print("No batch aggregates produced; returning empty result.")
                    return agg_meta.head(0)

                try:
                    full_agg_concat = dask_cudf.concat(batch_agg_parts, interleave_partitions=False)
                except Exception as e:
                    # 异常时打印关键信息并中断执行（向上抛出异常）
                    print(f"ERROR: Failed to concat batch aggregates: {e}")
                    print(f"Batch agg parts count: {len(batch_agg_parts)}")
                    print(f"First batch schema: {batch_agg_parts[0].dtypes if batch_agg_parts else 'None'}")
                    raise  #

                # 尝试强制一致的 dtypes（best-effort）
                for col, dtype in agg_meta.dtypes.items():
                    try:
                        full_agg_concat[col] = full_agg_concat[col].astype(dtype)
                    except Exception:
                        # 如果转换失败，忽略（说明某些分区有不一致的类型，建议检查具体 batch）
                        pass
                # endregion

                # region 最终 reduce：按 user_id, level 聚合
                final_agg_ddf = (
                    full_agg_concat
                    .groupby(["user_id", "level"])
                    .agg({
                        "total_amount": "sum",
                        "total_commission": "sum"
                    })
                    .reset_index()
                )

                final_agg_ddf = client.persist(final_agg_ddf)
                dask_wait(futures_of(final_agg_ddf))
                # endregion
                # endregion

                # region 打印结果
                try:
                    total_rows = int(final_agg_ddf.map_partitions(len).sum().compute())
                    print(f"Final aggregate rows: {total_rows}")
                    print("Final aggregate dtypes:\n", final_agg_ddf.dtypes)
                    print("Final aggregate sample:")
                    print(final_agg_ddf.head(100))
                except Exception as e:
                    print("Warning: diagnostics on final_agg_ddf failed:", e)

                print("end")
                # endregion

                # 返回 final_agg_ddf（dask_cudf.DataFrame），调用方可以 .compute() 或继续并行操作 / 写出 parquet
                return final_agg_ddf.compute()
            finally:
                try:
                    runLock.release()
                except Exception:
                    pass

    def run_update(self, version: int, changList: List[ChangeUserMsg], npartitions: int = 1,
                   renumber_disable: bool = True):
        """
        更改self.ddf_edages的数据，重新创建图
        """

        # region 将模型转换成dask_cudf
        # 把每个 model 转成 dict
        print("展示参数：")
        print(changList)
        rows = [m.model_dump() for m in changList]
        print("展示rows：")
        print(rows)
        # pandas -> cudf -> dask_cudf
        pdf = pd.DataFrame(rows)
        print("展示数据：")
        print(pdf)
        cudf_df = cudf.from_pandas(pdf)
        ddf = dask_cudf.from_cudf(cudf_df, npartitions=npartitions)
        ddf = ddf.rename(columns={"user": "src", "parent": "dst"})
        ddf = ddf.persist()
        dask.distributed.wait(ddf)
        print("展示数据2-1：")
        print(ddf.head(5))
        # endregion

        # region 过滤出insert、update、delete的list
        inserts = ddf[ddf["op"] == "c"]
        updates = ddf[ddf["op"] == "u"]
        deletes = ddf[ddf["op"] == "d"]

        # materialize small partitions for existence checks
        inserts_local = inserts.compute()
        updates_local = updates.compute()
        deletes_local = deletes.compute()
        print("展示数据插入：")
        print(inserts_local.head(5))
        print("展示数据更新：")
        print(updates_local.head(5))
        print("展示数据删除：")
        print(deletes_local.head(5))
        LOG.info(f"Type of inserts (Dask cuDF):{type(inserts)}")
        LOG.info(f"Type of inserts_local (cuDF):{type(inserts_local)}")
        # endregion

        # region 初始化参数
        ddf_edges = self.ddf_users
        delete_parts = []
        parts = []
        to_insert_df = None
        to_delete_df = None
        client = get_client()
        lock_name = "cdc_lock"
        lock = Lock(lock_name, client=client)
        lock_acquired = False
        # endregion

        # region 整理出需要删除和新增的list--> 更新和删除加入delete_parts，更新和新增加入parts
        if len(deletes_local) > 0:
            delete_parts.append(to_broadcast_ddf(deletes_local[["id"]].copy(), flag_col="_is_del"))
        if len(updates_local) > 0:
            delete_parts.append(to_broadcast_ddf(updates_local[["id"]].copy(), flag_col="_is_del"))
            parts.append(updates_local[["id", "src", "dst", "updatetime"]].copy())
        if len(inserts_local) > 0:
            parts.append(inserts_local[["id", "src", "dst", "updatetime"]].copy())
        # endregion

        # region pre-check 对比版本号是否一致 验证消息幂等
        if version == self.get_current_published_version(client):
            print("消息已经被处理过")
            return
        # endregion

        try:
            # region double check
            # first check 上锁
            lock_acquired = lock.acquire(timeout=15)
            if not lock_acquired:
                print("未能获取到锁")
                return
            # second check 对比版本号是否一致 验证消息幂等 有问题直接返回
            if version == self.get_current_published_version(client):
                print("消息已经被处理过")
                return
            # endregion

            # region 左联ddf_edges标记出_is_del并过滤
            if delete_parts:
                to_delete_df = cudf.concat(delete_parts, ignore_index=True)
            if to_delete_df is not None and len(to_delete_df) > 0:
                del_ddf = dask_cudf.from_cudf(to_delete_df, npartitions=npartitions)
                print("展示临时数据0")
                print(del_ddf.compute().to_string())
                merged = ddf_edges.merge(del_ddf, on=["id"], how="left")
                print("展示临时数据1")
                print(merged.compute().to_string())
                ddf_edges = merged[merged["_is_del"].isnull()].drop(columns=["_is_del"])
                full_df_tmp = ddf_edges.compute()
                print("展示临时数据2")
                print(full_df_tmp.to_string())
            # endregion

            # region 新增parts
            # --- 把新行并入（只 concat 一次，并在 concat 时用当前 ddf_edges） ---
            if parts:
                to_insert_df = cudf.concat(parts, ignore_index=True)
            if to_insert_df is not None and len(to_insert_df) > 0:
                ins_ddf = dask_cudf.from_cudf(to_insert_df, npartitions=npartitions)
                ddf_edges = dask_cudf.concat([ddf_edges, ins_ddf])
            # endregion

            # region 去重
            try:
                ddf_edges = ddf_edges.drop_duplicates(subset=["src", "dst"])
            except Exception:
                # 一些 cudf/dask 版本的兼容处理
                pass
            # endregion

            # region ddf_edges重新分区，并赋值self.ddf_users，过滤出无上级的用户列表ddf_new_edges，并重新分区
            ddf_new_edges = None
            try:
                ddf_edges = ddf_edges.repartition(npartitions=npartitions)
                self.ddf_users = ddf_edges
                ddf_new_edges = ddf_edges[ddf_edges["dst"] != "0"]
                ddf_new_edges = ddf_new_edges.repartition(npartitions=npartitions)
            except Exception as e:
                print("Warning: repartition failed:", e)
            print("ddf_edges npartitions:", getattr(ddf_edges, "npartitions", None))
            # endregion

            # region init cugraph dask comms
            client.wait_for_workers(npartitions)
            try:
                Comms.initialize()
                print("cugraph.dask Comms initialized")
            except Exception as e:
                print("Warning: failed to initialize cugraph.dask Comms:", e)
            # endregion

            # region Build distributed cugraph Graph
            import time
            # 记录开始时间
            start_time = time.perf_counter()

            # region 创建有向图、反向图
            print("Building distributed Graph from dask_cudf edgelist ...")
            dg = cugraph.Graph(directed=True)
            dg.from_dask_cudf_edgelist(ddf_new_edges, source="src", destination="dst", renumber=(not renumber_disable))
            self.dg = dg

            print("Building reversed distributed Graph from dask_cudf edgelist ...")
            dg_rev = cugraph.Graph(directed=True)
            # 这里把 source/destination 互换：parent -> user
            dg_rev.from_dask_cudf_edgelist(ddf_new_edges, source="dst", destination="src",
                                           renumber=(not renumber_disable))
            self.dg_rev = dg_rev
            # endregion

            # 记录结束时间
            end_time = time.perf_counter()

            # 计算并打印耗时
            elapsed = end_time - start_time
            print(f"图构建耗时: {elapsed:.4f} 秒")
            print("Distributed Graph built.")
            # endregion

            # region 将版本号发布到schedule
            # 在 publish 前确保同名 dataset 不存在
            try:
                # 尝试显式取消已有 dataset（若不存在会抛异常）
                client.unpublish_dataset(users_cdc_version)
                print(f"Unpublished existing dataset: {users_cdc_version},version:{version}")
            except Exception:
                # 忽略找不到或其它小错误
                pass
            client.publish_dataset(**{users_cdc_version: version})
            # endregion

            # region 验证数据
            # 注意：如果表很大，不要立刻 persist 全表
            ddf_edges = ddf_edges.persist()
            dask.distributed.wait(ddf_edges)

            full_df = ddf_edges.compute()
            print(f"\n==== FULL DATA ({len(full_df)} ROWS) ====")
            print(full_df.to_string())  # cuDF 的 to_string() 方法
            total = ddf_edges.map_partitions(len).sum().compute()
            print("total rows (dask,sum):", total)
            # endregion
        finally:
            if lock_acquired:
                try:
                    lock.release()
                    LOG.info("释放锁")
                except Exception as e:
                    print("Warning: release lock failed:", e)
            else:
                print("lock 未被获取，跳过 release")

    # 计算该用户每级子节点的数量
    def descendant_counts_via_bfs(self, src: int, max_depth: int = None):
        """
        返回一个 pandas DataFrame：columns = ['level', 'count']
        level = 1,2,3... 表示代数（distance），count 表示该代的用户数。
        如果 max_depth 非 None，则只统计到该最大深度。
        """
        # 1) 执行分布式 BFS
        df_bfs = dask_bfs.bfs(self.dg_rev, src)

        # region 2) 过滤无穷/空距离，并把列改名
        df_bfs = df_bfs[df_bfs["distance"].notnull()]
        df_bfs = df_bfs[df_bfs["distance"] != INF]
        df_bfs = df_bfs[df_bfs["distance"] > 0]  # 排除自己（distance==0）
        df_bfs = df_bfs.rename(columns={"vertex": "descendant", "distance": "level"})
        # endregion

        # region 3) 如需限制深度
        if max_depth is not None:
            df_bfs = df_bfs[df_bfs["level"] <= int(max_depth)]
        # endregion

        # 4) 按 level 分组计数
        agg = df_bfs.groupby("level").agg({"descendant": "count"}).reset_index()

        # region 5) materialize 到本地 pandas 以便查看
        result = agg.compute().sort_values("level").rename(columns={"descendant": "count"})
        result["level"] = result["level"].astype(int)
        result["count"] = result["count"].astype(int)
        # endregion

        return result

    def get_allparent(self, src):
        # 1) 执行分布式 BFS
        df_bfs = dask_bfs.bfs(self.dg, src)

        # region 2) 过滤无穷/空距离，并把列改名
        df_bfs = df_bfs[df_bfs["distance"].notnull()]
        df_bfs = df_bfs[df_bfs["distance"] != INF]
        df_bfs = df_bfs[df_bfs["distance"] > 0]  # 排除自己（distance==0）
        df_bfs = df_bfs.rename(columns={"vertex": "descendant", "distance": "level"})
        # endregion

        pdf = df_bfs.compute()  # 这里一定会变成 pandas（或 cudf）
        print("computed type =", type(pdf))
        print(pdf.head(10))  # 打印真实数据

        return df_bfs.compute().to_pandas()

    def get_ddf_edges(self):
        return self.ddf_edges
