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
from typing import List, Dict, Optional, Any
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

        # 全量用户关系表：columns 至少包含 src=user, dst=parent
        self.ddf_users = None

        # 有效边表：过滤 dst != "0" 后的 src -> dst
        self.ddf_edges = None

        # 全局重算用 Root-Depth 索引：columns = ["src", "depth"]
        self.ddf_depths = None

        # 全局重算用 child 索引：columns = ["src", "dst"]，按 dst/src 预处理
        self.ddf_users_by_dst = None

        # src/dst 是否已经规范化为 str，并且已 persist
        self._columns_normalized = False

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
            self.ddf_users = None
            self.ddf_edges = None
            self.ddf_depths = None
            self.ddf_users_by_dst = None
            self._columns_normalized = False
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
        """
        将 Delta 用户关系快照加载至 GPU / Dask-cuDF，并构建：
        - self.ddf_users：全量用户关系表，columns = id, src, dst, updatetime
        - self.ddf_edges：有效边表，过滤 dst != "0"
        - self.dg：src -> dst，用于向上查祖先
        - self.dg_rev：dst -> src，用于向下查子孙

        注意：
        - 此方法只在检测到 Delta 版本需要 reload 时重建图。
        - 无论是否 reload，都必须释放 runLock。
        - 生产环境不应 compute() 全量表打印，只打印 count/head。
        """
        client = get_client()
        runLock = Lock(self._global_lock_name, client=client)
        got_run_lock = False
        reload_lock = None
        reload_lock_acquired = False

        try:
            got_run_lock = runLock.acquire(timeout=15)
            if not got_run_lock:
                print("未能获取 graph_service_lock，跳过 run。")
                return

            # 初始化前销毁旧资源
            try:
                client.run(_worker_cleanup_existing_graph_service)
                print("Comms destroyed and cleanup completed before initialization.")
            except Exception as e:
                print("Warning: failed to destroy comms during pre-initialization:", e)

            current_version = self.get_current_published_version(client)
            msg_version = int(msg_version)
            print(f"current_version: {current_version}, msg_version:{msg_version}")

            if current_version >= msg_version:
                print("无需 reload：当前已发布版本不低于消息版本。")
                return

            reload_lock = Lock(f"reload:{msg_version}", client=client)
            reload_lock_acquired = reload_lock.acquire(timeout=15)
            if not reload_lock_acquired:
                print("未能获取 reload lock，跳过 reload。")
                return

            # double check
            if not (self.get_current_published_version(client) < msg_version and need_reload(model_dir, msg_version)):
                print("double check 未通过，无需 reload。")
                return

            sched_info = client.scheduler_info()
            worker_addrs = list(sched_info.get("workers", {}).keys())
            n_workers = len(worker_addrs)
            print(f"Detected {n_workers} workers")

            print("Reading edge list with dask_cudf.read_parquet ...")
            ddf_users, current_version_local = read_delta_snapshot_files(
                model_dir,
                cols=["id", "user", "parent", "updatetime"],
                npartitions=npartitions,
            )

            ddf_edges = ddf_users[ddf_users["parent"] != "0"].rename(
                columns={"user": "src", "parent": "dst"}
            )
            ddf_users = ddf_users.rename(columns={"user": "src", "parent": "dst"})

            nparts = npartitions if npartitions > 0 else max(1, n_workers)
            try:
                if getattr(ddf_edges, "npartitions", 1) != nparts:
                    print(f"Repartitioning edges/users to {nparts} partitions")
                    ddf_edges = ddf_edges.repartition(npartitions=nparts)
                    ddf_users = ddf_users.repartition(npartitions=nparts)
            except Exception as e:
                print("Warning: repartition failed:", e)

            ddf_users = ddf_users.persist()
            ddf_edges = ddf_edges.persist()
            dask.distributed.wait(ddf_edges)
            dask.distributed.wait(ddf_users)

            client.wait_for_workers(max(1, n_workers))
            try:
                Comms.initialize()
                print("cugraph.dask Comms initialized")
            except Exception as e:
                print("Warning: failed to initialize cugraph.dask Comms:", e)

            import time
            start_time = time.perf_counter()

            print("Building distributed Graph from dask_cudf edgelist ...")
            dg = cugraph.Graph(directed=True)
            dg.from_dask_cudf_edgelist(
                ddf_edges,
                source="src",
                destination="dst",
                renumber=(not renumber_disable),
            )

            print("Building reversed distributed Graph from dask_cudf edgelist ...")
            dg_rev = cugraph.Graph(directed=True)
            dg_rev.from_dask_cudf_edgelist(
                ddf_edges,
                source="dst",
                destination="src",
                renumber=(not renumber_disable),
            )

            self.dg = dg
            self.dg_rev = dg_rev
            self.ddf_users = ddf_users
            self.ddf_edges = ddf_edges
            self._invalidate_global_recalc_indexes()

            elapsed = time.perf_counter() - start_time
            print(f"图构建耗时: {elapsed:.4f} 秒")
            print("Distributed Graph built.")

            # 生产安全诊断：不拉全量，只看 count/head。
            try:
                total = int(ddf_users.map_partitions(len).sum().compute())
                print("total rows (dask,sum):", total)
                print("ddf_users sample:")
                print(ddf_users.head(20).to_string())
            except Exception as e:
                print("Warning: diagnostics failed:", e)

            ds_version = "users_version"
            try:
                client.unpublish_dataset(ds_version)
                print(f"Unpublished existing dataset: {ds_version}")
            except Exception:
                pass
            client.publish_dataset(**{ds_version: current_version_local})
            print(f"Published dataset {ds_version}: {current_version_local}")
            print("Done.")

        finally:
            if reload_lock_acquired and reload_lock is not None:
                try:
                    reload_lock.release()
                except Exception as e:
                    print("Warning: release reload lock failed:", e)
            if got_run_lock:
                try:
                    runLock.release()
                except Exception as e:
                    print("Warning: release graph_service_lock failed:", e)

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
        根据用户 CDC 更新 self.ddf_users / self.ddf_edges，并重新创建正向图、反向图。

        注意：
        - CDC 后必须让 ddf_depths / ddf_users_by_dst / _columns_normalized 失效。
        - 生产环境不应 compute() 全量表打印。
        """
        print("展示参数：")
        print(changList)

        rows = [m.model_dump() for m in changList]
        pdf = pd.DataFrame(rows)
        print("CDC rows sample:")
        print(pdf.head(20))

        cudf_df = cudf.from_pandas(pdf)
        ddf = dask_cudf.from_cudf(cudf_df, npartitions=npartitions)
        ddf = ddf.rename(columns={"user": "src", "parent": "dst"})
        ddf = ddf.persist()
        dask.distributed.wait(ddf)

        inserts = ddf[ddf["op"] == "c"]
        updates = ddf[ddf["op"] == "u"]
        deletes = ddf[ddf["op"] == "d"]

        inserts_local = inserts.compute()
        updates_local = updates.compute()
        deletes_local = deletes.compute()

        LOG.info("Type of inserts (Dask cuDF): %s", type(inserts))
        LOG.info("Type of inserts_local (cuDF): %s", type(inserts_local))
        print("展示数据插入：")
        print(inserts_local.head(20))
        print("展示数据更新：")
        print(updates_local.head(20))
        print("展示数据删除：")
        print(deletes_local.head(20))

        ddf_edges = self.ddf_users
        if ddf_edges is None:
            raise RuntimeError("GraphService 尚未加载 ddf_users，无法执行 run_update。")

        delete_parts = []
        parts = []
        to_insert_df = None
        to_delete_df = None
        client = get_client()
        lock_name = "cdc_lock"
        lock = Lock(lock_name, client=client)
        lock_acquired = False

        if len(deletes_local) > 0:
            delete_parts.append(to_broadcast_ddf(deletes_local[["id"]].copy(), flag_col="_is_del"))
        if len(updates_local) > 0:
            delete_parts.append(to_broadcast_ddf(updates_local[["id"]].copy(), flag_col="_is_del"))
            parts.append(updates_local[["id", "src", "dst", "updatetime"]].copy())
        if len(inserts_local) > 0:
            parts.append(inserts_local[["id", "src", "dst", "updatetime"]].copy())

        if version == self.get_current_published_cdc_version(client):
            print("消息已经被处理过")
            return

        try:
            lock_acquired = lock.acquire(timeout=15)
            if not lock_acquired:
                print("未能获取到锁")
                return

            if version == self.get_current_published_cdc_version(client):
                print("消息已经被处理过")
                return

            if delete_parts:
                to_delete_df = cudf.concat(delete_parts, ignore_index=True)

            if to_delete_df is not None and len(to_delete_df) > 0:
                del_ddf = dask_cudf.from_cudf(to_delete_df, npartitions=npartitions)
                merged = ddf_edges.merge(del_ddf, on=["id"], how="left")
                ddf_edges = merged[merged["_is_del"].isnull()].drop(columns=["_is_del"])

            if parts:
                to_insert_df = cudf.concat(parts, ignore_index=True)

            if to_insert_df is not None and len(to_insert_df) > 0:
                ins_ddf = dask_cudf.from_cudf(to_insert_df, npartitions=npartitions)
                ddf_edges = dask_cudf.concat([ddf_edges, ins_ddf])

            try:
                ddf_edges = ddf_edges.drop_duplicates(subset=["src", "dst"])
            except Exception:
                pass

            try:
                ddf_edges = ddf_edges.repartition(npartitions=npartitions)
                self.ddf_users = ddf_edges
                ddf_new_edges = ddf_edges[ddf_edges["dst"] != "0"]
                ddf_new_edges = ddf_new_edges.repartition(npartitions=npartitions)
            except Exception as e:
                raise RuntimeError(f"CDC 后 repartition / 过滤有效边失败: {e}") from e

            print("ddf_edges npartitions:", getattr(ddf_edges, "npartitions", None))

            client.wait_for_workers(npartitions)
            try:
                Comms.initialize()
                print("cugraph.dask Comms initialized")
            except Exception as e:
                print("Warning: failed to initialize cugraph.dask Comms:", e)

            import time
            start_time = time.perf_counter()

            print("Building distributed Graph from dask_cudf edgelist ...")
            dg = cugraph.Graph(directed=True)
            dg.from_dask_cudf_edgelist(
                ddf_new_edges,
                source="src",
                destination="dst",
                renumber=(not renumber_disable),
            )
            self.dg = dg

            print("Building reversed distributed Graph from dask_cudf edgelist ...")
            dg_rev = cugraph.Graph(directed=True)
            dg_rev.from_dask_cudf_edgelist(
                ddf_new_edges,
                source="dst",
                destination="src",
                renumber=(not renumber_disable),
            )
            self.dg_rev = dg_rev

            self.ddf_edges = ddf_new_edges
            self._invalidate_global_recalc_indexes()

            elapsed = time.perf_counter() - start_time
            print(f"图构建耗时: {elapsed:.4f} 秒")
            print("Distributed Graph built.")

            try:
                client.unpublish_dataset(users_cdc_version)
                print(f"Unpublished existing dataset: {users_cdc_version}, version:{version}")
            except Exception:
                pass
            client.publish_dataset(**{users_cdc_version: version})

            try:
                ddf_edges = ddf_edges.persist()
                dask.distributed.wait(ddf_edges)
                total = int(ddf_edges.map_partitions(len).sum().compute())
                print("total rows (dask,sum):", total)
                print("ddf_edges sample:")
                print(ddf_edges.head(20).to_string())
            except Exception as e:
                print("Warning: diagnostics failed:", e)

        finally:
            if lock_acquired:
                try:
                    lock.release()
                    LOG.info("释放锁")
                except Exception as e:
                    print("Warning: release lock failed:", e)
            else:
                print("lock 未被获取，跳过 release")

    def get_direct_children_batch(self, parent_ids: List[str]) -> Dict[str, List[str]]:
        """
        批量返回多个父节点的直推下级 {parent_id: [direct_children_ids]}
        利用 cudf merge(内连接) 直接过滤边表，大幅提升性能。
        """
        if self.ddf_users is None or not parent_ids:
            return {str(p): [] for p in parent_ids}

        # self.ddf_users 中的结构：src=user(下级), dst=parent(上级)
        pids = cudf.DataFrame({"dst": [str(p) for p in parent_ids]})
        pids_ddf = dask_cudf.from_cudf(pids, npartitions=1)

        # 进行过滤，取出这些父节点的所有儿子
        edges = self.ddf_users.merge(pids_ddf, on=["dst"], how="inner")

        # 拉取计算并转为 pandas DataFrame 本地处理
        pdf = edges[["dst", "src"]].compute().to_pandas()
        pdf["dst"] = pdf["dst"].astype(str)
        pdf["src"] = pdf["src"].astype(str)

        # 组装结果字典
        out: Dict[str, List[str]] = {str(p): [] for p in parent_ids}
        for _, row in pdf.iterrows():
            out[row["dst"]].append(row["src"])

        return out

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

    # 获取该用户所有层级的祖先
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

    # =====================================================================
    # GlobalRecalculationService 支撑接口
    # =====================================================================

    def _ensure_graph_loaded(self) -> None:
        """确保 GraphService 已经加载了全量用户关系表。"""
        if self.ddf_users is None:
            raise RuntimeError("GraphService 尚未加载 ddf_users，请先执行 run() 构建图。")

        required_cols = {"src", "dst"}
        missing = required_cols - set(self.ddf_users.columns)
        if missing:
            raise RuntimeError(f"ddf_users 缺少必要列: {missing}")

    def _count_ddf_rows(self, ddf) -> int:
        """安全统计 dask_cudf DataFrame 行数。"""
        if ddf is None:
            return 0
        return int(ddf.map_partitions(len).sum().compute())

    def _invalidate_global_recalc_indexes(self) -> None:
        """
        图数据变更后，统一失效全局重算相关索引。
        run() / run_update() 更新 self.ddf_users 后应调用或等价执行。
        """
        self.ddf_depths = None
        self.ddf_users_by_dst = None
        self._columns_normalized = False

    def _normalize_graph_columns(self) -> None:
        """
        统一 src/dst 类型为 str，避免 int64 / str 混用导致分页和 join 异常。

        dask_cudf astype 是 lazy 的。如果每次接口调用都重复 astype，
        会不断叠加计算图。因此这里必须幂等，并在规范化后 persist。
        """
        self._ensure_graph_loaded()

        if getattr(self, "_columns_normalized", False):
            return

        try:
            self.ddf_users["src"] = self.ddf_users["src"].astype("str")
            self.ddf_users["dst"] = self.ddf_users["dst"].astype("str")
            self.ddf_users = self.ddf_users.persist()
            dask.distributed.wait(self.ddf_users)
        except Exception as e:
            self._columns_normalized = False
            raise RuntimeError(f"规范化 ddf_users src/dst 类型失败: {e}") from e

        if self.ddf_edges is not None:
            try:
                self.ddf_edges["src"] = self.ddf_edges["src"].astype("str")
                self.ddf_edges["dst"] = self.ddf_edges["dst"].astype("str")
                self.ddf_edges = self.ddf_edges.persist()
                dask.distributed.wait(self.ddf_edges)
            except Exception as e:
                self._columns_normalized = False
                raise RuntimeError(f"规范化 ddf_edges src/dst 类型失败: {e}") from e

        self._columns_normalized = True

    def _validate_no_virtual_root_in_users(self) -> None:
        """
        校验业务用户中不能出现 src == '0'。
        '0' 只能作为 parent 哨兵值使用，不能作为真实用户进入全局重算。
        """
        bad = self.ddf_users[self.ddf_users["src"] == "0"][["src", "dst"]]
        bad_count = self._count_ddf_rows(bad)

        if bad_count > 0:
            sample = bad.head(20)
            raise RuntimeError(
                f"图数据非法：ddf_users 中存在 src='0' 的虚拟根节点，"
                f"'0' 只能作为 parent 哨兵使用。count={bad_count}, sample={sample}"
            )

    def _validate_unique_user_parent(self) -> None:
        """校验每个用户只能有一条 parent 记录。"""
        users = self.ddf_users[["src", "dst"]]

        grouped = users.groupby("src").agg({"dst": "count"}).reset_index()
        dup = grouped[grouped["dst"] > 1]

        dup_count = self._count_ddf_rows(dup)
        if dup_count > 0:
            sample = dup.head(20)
            raise RuntimeError(
                f"图数据非法：存在 {dup_count} 个用户拥有多条 parent 记录。sample={sample}"
            )

    def _validate_parent_exists(self) -> None:
        """校验 parent != '0' 的 parent 必须存在于用户全集。"""
        users_src = (
            self.ddf_users[["src"]]
            .drop_duplicates()
            .assign(_exists=1)
        )

        parents = (
            self.ddf_users[self.ddf_users["dst"] != "0"][["dst"]]
            .rename(columns={"dst": "src"})
            .drop_duplicates()
        )

        checked = parents.merge(users_src, on=["src"], how="left")
        missing = checked[checked["_exists"].isnull()][["src"]]

        missing_count = self._count_ddf_rows(missing)
        if missing_count > 0:
            sample = missing.head(20)
            raise RuntimeError(
                f"图数据非法：存在 {missing_count} 个 parent 不在用户全集中。sample={sample}"
            )

    def _build_children_index(self) -> None:
        """
        构建直属子节点分页索引。

        目标：避免 get_direct_children_page 每次都直接全表过滤 self.ddf_users。
        结果：self.ddf_users_by_dst，columns = ["src", "dst"]。
        """
        self._ensure_graph_loaded()
        self._normalize_graph_columns()

        if self.ddf_users_by_dst is not None:
            return

        base = self.ddf_users[["src", "dst"]].drop_duplicates()

        # 关键正确性前提：shuffle + 分区内 sort 必须成功，否则 get_direct_children_page
        # 返回的分页顺序不是 src 升序，cursor 会跳行、漏行或重复。
        # 任何降级都会让 GRS 静默算错，所以这里只能 fail-fast。
        try:
            indexed = base.shuffle(on="dst")
        except Exception as e:
            raise RuntimeError(
                f"ddf_users_by_dst shuffle(on='dst') 失败，无法保证分页正确性: {e}"
            ) from e

        try:
            indexed = indexed.map_partitions(lambda df: df.sort_values(["dst", "src"]))
        except Exception as e:
            raise RuntimeError(
                f"ddf_users_by_dst 分区内按 [dst, src] 排序失败，无法保证分页正确性: {e}"
            ) from e

        self.ddf_users_by_dst = indexed.persist()
        dask.distributed.wait(self.ddf_users_by_dst)

    def _ensure_children_index(self) -> None:
        """确保直属子节点分页索引可用。"""
        if self.ddf_users_by_dst is None:
            self._build_children_index()

    def _build_root_depth_index(self) -> None:
        """
        构建 Root-Depth 索引。

        规则：
        - dst == '0' 的用户为根，depth = 0。
        - 子节点 depth = parent.depth + 1。
        - 如果最终 depth 覆盖数 != 用户全集数，说明存在环、无根子图或断裂数据。

        结果：self.ddf_depths，columns = ["src", "depth"]。
        """

        # region 验证 并对users中的src和dst去重
        self._ensure_graph_loaded()
        self._normalize_graph_columns()

        users = self.ddf_users[["src", "dst"]].drop_duplicates()
        # endregion

        # region 统计出users的src一共有人多少人
        total_users = int(
            users[["src"]]
            .drop_duplicates()
            .map_partitions(len)
            .sum()
            .compute()
        )

        if total_users <= 0:
            raise RuntimeError("图数据非法：ddf_users 为空。")
        # endregion

        # region 找出最顶层节点并新增“depth”为0 和 统计出这些节点的数量
        roots = (
            users[users["dst"] == "0"][["src"]]
            .drop_duplicates()
            .assign(depth=np.int32(0))
        )

        root_count = self._count_ddf_rows(roots)
        if root_count <= 0:
            raise RuntimeError(
                "图数据非法：没有任何 dst == '0' 的根节点，可能存在全网环或根数据缺失。"
            )
        # endregion

        depth_parts = [roots]

        # region 创造visited和frontier
        visited = roots[["src"]].drop_duplicates().persist()
        dask.distributed.wait(visited)

        frontier = roots[["src"]].drop_duplicates().persist()
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
            if current_depth > max_possible_depth:
                raise RuntimeError(
                    f"构建 Root-Depth 超过最大理论深度 {max_possible_depth}，疑似存在环。"
                )
            # endregion

            # region 创造parent_frontier -> 将frontier的src重命名为dst
            parent_frontier = frontier.rename(columns={"src": "dst"})
            # endregion

            # region 创造children -> 通过dst，parent_frontier联查user，找出它的所有下级
            children = (
                users.merge(parent_frontier, on=["dst"], how="inner")[["src"]]
                .drop_duplicates()
            )
            # endregion

            # region 创造visited_flag 新增一列_visited=1
            visited_flag = visited.assign(_visited=1)
            # endregion

            # region 创造next_frontier -> 通过src children联查visited_flag，过滤_visited为null的数据
            next_frontier = children.merge(visited_flag, on=["src"], how="left")
            next_frontier = (
                next_frontier[next_frontier["_visited"].isnull()][["src"]]
                .drop_duplicates()
            )
            # endregion

            # region 创造next_count -> 算出next_frontier的数量 等于0时跳出循环
            next_count = self._count_ddf_rows(next_frontier)
            if next_count == 0:
                break
            # endregion

            # region 在next_frontier新增一列current_depth，将新增后的数据集添加到depth_parts
            layer = next_frontier.assign(depth=np.int32(current_depth))
            depth_parts.append(layer)
            # endregion

            # region 将next_frontier添加到visited，并将visited重新发布dask
            visited = (
                dask_cudf.concat([visited, next_frontier], interleave_partitions=False)
                .drop_duplicates(subset=["src"])
                .persist()
            )
            dask.distributed.wait(visited)
            # endregion

            # region 将next_frontier赋值给frontier
            frontier = next_frontier.persist()
            dask.distributed.wait(frontier)
            # endregion

            # region 重新赋值visited_count
            visited_count = self._count_ddf_rows(visited)
            # endregion

        # region 创造ddf_depths -> 将depth_parts按src去重，发布到dask，连续合并 并生成DataFrame
        ddf_depths = (
            dask_cudf.concat(depth_parts, interleave_partitions=False)
            .drop_duplicates(subset=["src"])
        )
        # endregion

        # region 创造depth_total -> 统计ddf_depths的数量
        depth_total = self._count_ddf_rows(ddf_depths)

        if depth_total != total_users:
            missing_count = total_users - depth_total

            reached = ddf_depths[["src"]].assign(_reached=1)
            all_users = users[["src"]].drop_duplicates()
            missing = all_users.merge(reached, on=["src"], how="left")
            missing = missing[missing["_reached"].isnull()][["src"]]

            sample = missing.head(20)

            raise RuntimeError(
                f"图数据非法：Root-Depth 覆盖用户数 {depth_total} != 用户全集数 {total_users}。"
                f"未覆盖数量={missing_count}。可能存在环、无根子图或断裂数据。sample={sample}"
            )
        # endregion

        # region 将ddf_depths重新分区 并按照"depth", "src"排序
        nparts = getattr(self.ddf_users, "npartitions", 1) or 1
        try:
            ddf_depths = ddf_depths.repartition(npartitions=nparts)
        except Exception:
            pass

        try:
            ddf_depths = ddf_depths.sort_values(["depth", "src"])
        except Exception as e:
            # 排序失败 = 后续 get_nodes_at_depth_page 的"预排序前提"不成立，
            # 分页将返回错乱结果。这里必须 fail-fast，不能只 warning 继续。
            raise RuntimeError(
                f"ddf_depths 按 [depth, src] 排序失败，无法保证分页正确性: {e}"
            ) from e
        # endregion

        # region 将ddf_depths发布到dask
        self.ddf_depths = ddf_depths.persist()
        dask.distributed.wait(self.ddf_depths)
        # endregion

        # region 获取最大深度
        max_depth = self.ddf_depths["depth"].max().compute()
        max_depth_int = 0 if max_depth is None or pd.isna(max_depth) else int(max_depth)

        LOG.info(
            "Root-Depth 索引构建完成: total_users=%s, max_depth=%s",
            total_users,
            max_depth_int,
        )
        # endregion

    def _ensure_depth_index(self) -> None:
        """确保 Root-Depth 索引可用。"""
        if self.ddf_depths is None:
            self._build_root_depth_index()

    def validate_graph_integrity(self) -> bool:
        """
        全局图完整性校验。

        校验项：
        1. self.ddf_users 不为空。
        2. self.ddf_users 是用户全集。
        3. src == '0' 不能作为业务用户出现。
        4. 每个 src/user 只能有一条 parent 记录。
        5. parent != '0' 的 dst 必须存在于用户全集。
        6. Root-Depth 能覆盖所有用户；否则判定存在环、断裂或无根子图。
        """
        self._ensure_graph_loaded()
        self._normalize_graph_columns()

        total_users = self._count_ddf_rows(self.ddf_users)
        if total_users <= 0:
            raise RuntimeError("图数据非法：ddf_users 为空。")

        self._validate_no_virtual_root_in_users()
        self._validate_unique_user_parent()
        self._validate_parent_exists()

        self._build_root_depth_index()
        self._build_children_index()

        return True

    def get_max_root_depth(self) -> int:
        """
        返回最大 Root-Depth。

        Root-Depth 定义：
        - 根节点 depth = 0
        - 根的子节点 depth = 1
        - 叶子节点 depth 最大
        """
        self._ensure_depth_index()

        max_depth = self.ddf_depths["depth"].max().compute()

        if max_depth is None or pd.isna(max_depth):
            return 0

        return int(max_depth)

    def _normalize_cursor(self, cursor: Optional[Any]) -> Optional[str]:
        """
        统一 cursor 类型。
        GraphService 自己产出 cursor，理论上会是 str。
        这里额外兼容 bytes，避免 str(b'xxx') 变成 "b'xxx'"。
        """
        if cursor is None:
            return None

        if isinstance(cursor, bytes):
            return cursor.decode("utf-8")

        return str(cursor)

    def _page_items_by_src_presorted(self, ddf, cursor: Optional[Any], limit: int) -> Dict[str, Any]:
        """
        基于已预排序数据的 keyset 分页工具。

        输入 ddf 必须：
        - 有 src 列。
        - 已经按照 src 升序排序，或在同一 parent/depth 范围内等价有序。
        """
        # region 验证
        if limit <= 0:
            raise ValueError("limit 必须大于 0。")
        # endregion

        # region page_ddf -> 取出cursor之后的所有数据
        cursor = self._normalize_cursor(cursor)

        if cursor is not None:
            ddf = ddf[ddf["src"] > cursor]

        page_ddf = ddf[["src"]]
        # endregion

        # region 从page_ddf取出limit+1条数据
        # 关键：必须用 npartitions=-1。
        # ddf_depths / ddf_users_by_dst 已经按 src 全局有序，但 filter 之后
        # 目标行可能不在 partition 0（被 filter 清空）。默认 npartitions=1 只看
        # partition 0，会返回空 → GRS 误判该 depth/parent 没有 child → 静默跳过整层。
        # npartitions=-1 让 dask 各 partition 各取前 N，concat 后再取前 N，
        # 配合预排序得到全局最小 N 行。
        pdf = page_ddf.head(limit + 1, npartitions=-1).to_pandas()

        if pdf is None or len(pdf) == 0:
            return {"items": [], "next_cursor": None}

        raw_items = [str(x) for x in pdf["src"].tolist()]
        # endregion
        # region 取出当前页的数据 和 下一页的第一条数据
        has_more = len(raw_items) > limit

        items = raw_items[:limit]
        next_cursor = items[-1] if has_more and items else None
        # endregion

        return {"items": items, "next_cursor": next_cursor}

    def get_nodes_at_depth_page(self, depth: int, cursor: Optional[Any], limit: int) -> Dict[str, Any]:
        """
        按 Root-Depth 分页返回节点。
        GlobalRecalculationService 会从 max_depth 倒序调用该方法。
        """
        self._ensure_depth_index()

        # region 取出depth深度的数据
        depth = int(depth)
        ddf = self.ddf_depths[self.ddf_depths["depth"] == depth][["src"]]
        # endregion

        return self._page_items_by_src_presorted(ddf=ddf, cursor=cursor, limit=limit)

    def get_direct_children_page(self, parent_id: str, cursor: Optional[Any], limit: int) -> Dict[str, Any]:
        """
        按 parent_id 分页返回直属 child。

        关键：
        - 不返回 parent 的全部 children。
        - 每次最多返回 limit 个 child id。
        - 使用 self.ddf_users_by_dst，避免每次直接扫 self.ddf_users。
        """
        self._ensure_children_index()

        parent_id = str(parent_id)
        ddf = self.ddf_users_by_dst[self.ddf_users_by_dst["dst"] == parent_id][["src"]]

        return self._page_items_by_src_presorted(ddf=ddf, cursor=cursor, limit=limit)
