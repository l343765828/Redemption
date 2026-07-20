# -*- coding: utf-8 -*-
"""
PE 奖金计算 —— 独立运行入口（测试环境用）。

它做四件事：
  1. 连到已有 Dask 集群（graph_actor / userinfo_actor 已 publish 在上面）
  2. 组装 execute_batch 需要的 4 个输入
       ddf_users      <- graph_actor.get_ddf_users()      （含根全量，src/dst 原始 id）
       ddf_user       <- userinfo_actor.get_ddf_userinfo() （id/country_id/user_name/real_name）
       ddf_stats      <- 从 Redis 批量读当期 UserStats
       ddf_user_perf  <- None（按 UserStats.pv>=30 派生 IS_ACTIVE）
  3. 调 PEBonusBatchServiceGPU().execute_batch(...)
  4. 把两张结果表拉回本地打印 + 落 CSV 备查

== 运行前必须满足的前提 ==
  [A] UserService.loadAllUser() 已经跑过：集群上已 publish "graph_actor" / "userinfo_actor"。
  [B] 本期 GlobalRecalculationService().settle_period(period) 已经跑完：
      UserStats 已写入 Redis。注意 UserStats 是“当期草稿本”带 TTL，务必在过期前跑本脚本。
  [C] 需要给两个 Service 各加一行 getter，并【重建 actor】（不能热更新已有 actor，
      必须改完类后重新跑 loadAllUser 重新 publish）：
        # GraphService（注意 UserService 实际 import 的是 GraphService_bak，加到真正被实例化的那个类里）
        def get_ddf_users(self):
            return self.ddf_users          # 含根全量；get_ddf_edges() 过滤了 dst!="0" 会丢顶层用户
        # UserInfoService
        def get_ddf_userinfo(self):
            return self.ddf_userinfo
      （不加 get_ddf_users 会回退到 get_ddf_edges——顶层 Elite/PE/SE 会漏发，仅供临时跑通；
        不加 get_ddf_userinfo 则直接报错。）
  [D] 运行本脚本的机器（driver）需装好 cudf / dask_cudf 且有 GPU
      （execute_batch 自身就有 driver 侧 cudf 操作，这是硬要求）。

用法：
    python pe_bonus_main.py --period 5 --month 202504
    python3 -m User.PEBonusService_Main --period 202605 --month 202605 --mget
    # 或改下面 __main__ 里的默认值直接运行
"""

import argparse
import logging

import cudf
import dask_cudf
from dask.distributed import Client

# —— 按你们的包路径调整下面两个 import ——
from Model.User.UserStats import UserStats
from User.PEBonusService import PEBonusService

SCHEDULE_ADDRESS = "tcp://192.168.18.149:38786"   # 与 UserService.SCHEDULE_ADDRESS 保持一致

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
log = logging.getLogger("pe_bonus_main")

# 奖金只需要这几个字段
_STATS_FIELDS = ["user_id", "rank", "is_elite", "gpv_real", "gpv_unreal", "pv"]


# ============================================================
# ddf_stats：从 Redis 批量读当期 UserStats（整期全量）
# ============================================================
def build_ddf_stats_from_redis(period_num, npartitions: int = 8) -> dask_cudf.DataFrame:
    """
    用 redis_om 的 RediSearch 索引（period 字段带索引）整期取出。
    简单直观，适合测试 / 中小规模。超大规模请改用下面的 _build_ddf_stats_via_mget。
    """
    period = str(period_num)
    rows = []
    for s in UserStats.find(UserStats.period == period).all():
        rows.append({
            "user_id":    int(s.user_id if s.user_id is not None else s.id),  # Redis 里是字符串 -> int64
            "rank":       int(s.rank or 0),
            "is_elite":   bool(s.is_elite),
            "gpv_real":   int(s.gpv_real or 0),     # 都是整数 BV
            "gpv_unreal": int(s.gpv_unreal or 0),
            "pv":         int(s.pv or 0),
        })

    if not rows:
        log.warning("period=%s 没有读到任何 UserStats（是否已 settle_period？是否已过 TTL？）", period)
        return _empty_stats_ddf()
    print("打印数据")
    print(rows)
    log.info("从 Redis 读到 %d 条 UserStats（period=%s）", len(rows), period)
    gdf = cudf.DataFrame(rows)
    return dask_cudf.from_cudf(gdf, npartitions=npartitions)


def _build_ddf_stats_via_mget(period_num, key_chunk: int = 5000, npartitions: int = 8) -> dask_cudf.DataFrame:
    """
    （可选）高吞吐版：SCAN 期前缀 + RedisJSON JSON.MGET 分批拉取，镜像
    GlobalRecalculationService._mget_users_with_exists 的读法，不依赖 RediSearch 索引。
    若 find().all() 因索引/内存问题不可用，把 main 里的调用换成这个即可。
    """
    period = str(period_num)
    rc = UserStats.db()
    pattern = UserStats.make_key(f"{period}:*")   # 确认 make_key 对通配符的拼接位置正确
    keys = list(rc.scan_iter(match=pattern, count=10000))

    parts = []
    for i in range(0, len(keys), key_chunk):
        docs = rc.json().mget(keys[i:i + key_chunk], ".")   # 一组 dict
        rows = []
        for d in docs:
            if d is None:                                   # 过期/缺失，跳过（缺失节点紧缩时按 rank 0 处理，正确）
                continue
            rows.append({
                "user_id":    int(d.get("user_id") or d.get("id")),
                "rank":       int(d.get("rank") or 0),
                "is_elite":   bool(d.get("is_elite")),
                "gpv_real":   int(d.get("gpv_real") or 0),
                "gpv_unreal": int(d.get("gpv_unreal") or 0),
                "pv":         int(d.get("pv") or 0),
            })
        if rows:
            parts.append(cudf.DataFrame(rows))
    print("批量获取redis")
    print(parts)
    if not parts:
        log.warning("period=%s 没有扫到任何 UserStats key。", period)
        return _empty_stats_ddf()

    gdf = cudf.concat(parts, ignore_index=True)
    log.info("JSON.MGET 读到 %d 条 UserStats（period=%s）", len(gdf), period)
    return dask_cudf.from_cudf(gdf, npartitions=npartitions)


def _empty_stats_ddf() -> dask_cudf.DataFrame:
    empty = cudf.DataFrame({
        "user_id":    cudf.Series([], dtype="int64"),
        "rank":       cudf.Series([], dtype="int64"),
        "is_elite":   cudf.Series([], dtype="bool"),
        "gpv_real":   cudf.Series([], dtype="int64"),
        "gpv_unreal": cudf.Series([], dtype="int64"),
        "pv":         cudf.Series([], dtype="int64"),
    })
    return dask_cudf.from_cudf(empty, npartitions=1)


# ============================================================
# 从已发布的 actor 取 ddf_users / ddf_user
# ============================================================
def fetch_ddf_users(graph_actor) -> dask_cudf.DataFrame:
    """含根全量边表（src=下级, dst=上级, 原始 id 字符串；bonus 内部会转 int64）。"""
    if hasattr(graph_actor, "get_ddf_users"):
        ddf = graph_actor.get_ddf_users().result()
        log.info("ddf_users 来自 get_ddf_users()，列=%s", list(ddf.columns))
        return ddf
    # 回退：get_ddf_edges 过滤了 dst!="0"，顶层(根)用户被删 -> 顶层 Elite/PE/SE 会漏发！
    log.warning("GraphService 缺 get_ddf_users()，回退到 get_ddf_edges()。"
                "顶层用户(根)会被丢弃、顶层奖金会漏发——生产务必补 get_ddf_users()！")
    ddf = graph_actor.get_ddf_edges().result()
    log.info("ddf_users(回退 edges) 列=%s", list(ddf.columns))
    return ddf


def fetch_ddf_user(userinfo_actor) -> dask_cudf.DataFrame:
    """用户信息维表 id/country_id/user_name/real_name（id 已是 int64）。"""
    if hasattr(userinfo_actor, "get_ddf_userinfo"):
        ddf = userinfo_actor.get_ddf_userinfo().result()
        log.info("ddf_user 来自 get_ddf_userinfo()，列=%s", list(ddf.columns))
        return ddf
    raise RuntimeError(
        "UserInfoService 缺 get_ddf_userinfo()（请加：def get_ddf_userinfo(self): return self.ddf_userinfo，"
        "并重建 userinfo_actor），或改用 lookup_user_info 按 id 取。"
    )


# ============================================================
# 主流程
# ============================================================
def main(period_num: int, calc_month: int, schedule_address: str = SCHEDULE_ADDRESS,
         use_mget: bool = False, dump_dir: str = "/tmp"):
    client = Client(schedule_address)   # 注册为本进程默认 client，execute_batch 内部 get_client() 会拿到它
    log.info("已连接 Dask: %s", schedule_address)
    try:
        # 1) 取已发布的 actor（publish 的是 actor future，要 .result() 拿 actor 代理）
        graph_actor    = client.get_dataset("graph_actor").result()
        userinfo_actor = client.get_dataset("userinfo_actor").result()
        log.info("已获取 graph_actor / userinfo_actor")

        # 2) 组装 4 个输入
        ddf_users = fetch_ddf_users(graph_actor)
        ddf_user  = fetch_ddf_user(userinfo_actor)
        ddf_stats = (_build_ddf_stats_via_mget(period_num) if use_mget
                     else build_ddf_stats_from_redis(period_num))
        print("打印ddf_stats")
        print(ddf_stats.head(200))
        ddf_user_perf = None   # None -> 按 UserStats.pv>=30 内部派生 IS_ACTIVE

        # 3) 跑奖金
        svc = PEBonusService()
        result = svc.execute_batch(
            period_num=period_num,
            calc_month=calc_month,
            ddf_users=ddf_users,
            ddf_stats=ddf_stats,
            ddf_user=ddf_user,
            ddf_user_perf=ddf_user_perf,
        )
        ar_pe        = result["AR_CALC_BONUS_PE"]
        ar_pe_source = result["AR_CALC_BONUS_PE_SOURCE"]

        # 4) 拉回本地查看 + 落盘
        pe_pdf     = ar_pe.compute().to_pandas()
        source_pdf = ar_pe_source.compute().to_pandas()

        total_bonus = float(pe_pdf["BONUS_PE"].sum()) if len(pe_pdf) else 0.0
        log.info("AR_CALC_BONUS_PE 行数=%d，BONUS_PE 合计=%.2f", len(pe_pdf), total_bonus)
        log.info("AR_CALC_BONUS_PE_SOURCE 行数=%d", len(source_pdf))

        print("\n=== AR_CALC_BONUS_PE (head 20) ===")
        print(pe_pdf.head(20).to_string(index=False))
        print("\n=== AR_CALC_BONUS_PE_SOURCE (head 20) ===")
        print(source_pdf.head(20).to_string(index=False))

        pe_path = f"{dump_dir}/ar_calc_bonus_pe_{period_num}_{calc_month}.csv"
        src_path = f"{dump_dir}/ar_calc_bonus_pe_source_{period_num}_{calc_month}.csv"
        pe_pdf.to_csv(pe_path, index=False)
        source_pdf.to_csv(src_path, index=False)
        log.info("已写出：%s / %s", pe_path, src_path)

        return pe_pdf, source_pdf

    finally:
        # 只关本脚本自己的 client；不要 unpublish actor（别的流程还要用）
        try:
            client.close()
            log.info("Dask client 已关闭")
        except Exception as e:
            log.warning("client.close() 失败：%s", e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run PE bonus (execute_batch).")
    parser.add_argument("--period", type=int, default=5, help="期数（必须与 Redis 里 UserStats 的 period 一致）")
    parser.add_argument("--month", type=int, default=202504, help="计算月份 CALC_MONTH")
    parser.add_argument("--addr", type=str, default=SCHEDULE_ADDRESS, help="Dask scheduler 地址")
    parser.add_argument("--mget", action="store_true", help="用 JSON.MGET 分批读 UserStats（大规模时）")
    args = parser.parse_args()

    main(period_num=args.period, calc_month=args.month, schedule_address=args.addr, use_mget=args.mget)
