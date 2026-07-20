import logging
import time
from typing import Dict, List, Optional, Set, Tuple
import redis
from dask.distributed import Client
from redis_om import NotFoundError
import Model.User.UserLevel as UserLevel
from Model.User.UserStats import UserStats

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [UserStatsService] %(message)s'
)
logger = logging.getLogger(__name__)

ELITE_MARK = 1000
VIRTUAL_MARK = 2000
SCHEDULE_ADDRESS = "tcp://127.0.0.1:8786"

# ---------- 锁配置 ----------
LOCK_TIMEOUT = 300  # 锁 TTL (秒)
LOCK_BLOCKING_TIMEOUT = 10  # 单把锁的等待上限 (秒)
LOCK_MAX_RETRIES = 5  # 整批拿锁失败的重试次数
LOCK_RETRY_BASE_SLEEP = 0.2  # 重试退避基线 (秒)
LOCK_REFRESH_INTERVAL = 50  # 长链路时每多少层续约一次锁


# =====================================================================
# 异常分类
# =====================================================================
class BusyLockError(RuntimeError):
    """获取锁失败 (争用), 可重试。"""


class StaleLockError(RuntimeError):
    """锁已经丢失/过期, 可重试。"""


class UserStatsService:
    """
    ⚠️【架构前提声明】:
    由于无锁查图 (Dask BFS) 与获取 Redis 锁之间存在时间差, 本模块假设:
    父子树状关系变更 (如跳线、团队重组) 属于低频高优操作。
    业务系统必须在全局维度进行排他隔离 (例如: 重组时全局封板),
    禁止与日常订单的 BV 冒泡并发, 否则极小概率下可能导致向旧的祖先链错误传导业绩。
    """

    # =================================================================
    # 辅助方法
    # =================================================================
    @staticmethod
    def _bump_highest_rank(user: UserStats) -> None:
        """高水位维护: 只升不降。"""
        cur = user.rank or 0
        hist = user.highest_rank or 0
        if cur > hist:
            user.highest_rank = cur

    def _get_or_init_user(self, user_id: str) -> UserStats:
        """
        获取用户 stats; Redis 中不存在时返回零值的新对象 (不在此处落库,
        由后续 _save_models_pipeline 统一写回).

        本服务把 Redis 视为按月重置的缓存层: 月初被清空, 真正的持久存储
        在下游系统. 月内第一次拿到该用户的订单时, Redis 里必然查不到,
        这是"该用户本月零业绩起点"的正常语义, 不是数据异常.
        """
        user_id = str(user_id)
        try:
            u = UserStats.get(user_id)
        except NotFoundError:
            u = UserStats(
                pk=user_id,
                id=user_id,
                user_id=user_id,
                pv=0,
                gpv=0,
                contrib=0,
                is_elite=False,
                virtual_width=0,
                rank=UserLevel.NOTHING,
                highest_rank=UserLevel.NOTHING,  # 见下文 §三
                qualified_legs=set(),
            )
        self._normalize_qualified_legs(u)
        return u

    @staticmethod
    def _lock_sort_key(user_id: str):
        """全局一致的拿锁顺序, 避免死锁。"""
        s = str(user_id)
        try:
            return 0, int(s)
        except Exception:
            return 1, s

    @staticmethod
    def _normalize_qualified_legs(user: UserStats) -> Set[str]:
        """防止 Redis 反序列化后 qualified_legs 格式异常。"""
        legs = user.qualified_legs
        if legs is None:
            legs = set()
        elif not isinstance(legs, set):
            legs = set(legs)
        user.qualified_legs = legs
        return legs

    @staticmethod
    def _calc_virtual_width(gpv: int) -> int:
        if gpv >= VIRTUAL_MARK:
            return gpv // ELITE_MARK
        return 0

    @staticmethod
    def _recalc_rank(user: UserStats) -> None:
        """重新计算 rank 状态。同时维护 is_elite, virtual_width, highest_rank。"""
        gpv = user.gpv or 0
        legs = UserStatsService._normalize_qualified_legs(user)

        is_self_elite = gpv >= ELITE_MARK
        user.is_elite = is_self_elite
        user.virtual_width = UserStatsService._calc_virtual_width(gpv)

        total_elite_width = len(legs) + (user.virtual_width or 0)

        if total_elite_width >= 3:
            user.rank = UserLevel.SUPER_ELITE
        elif (is_self_elite and total_elite_width >= 1) or (
                not is_self_elite and total_elite_width >= 2
        ):
            user.rank = UserLevel.PRO_ELITE
        elif is_self_elite:
            user.rank = UserLevel.ELITE
        else:
            user.rank = UserLevel.NOTHING

        UserStatsService._bump_highest_rank(user)

    @staticmethod
    def _calc_contrib(user: UserStats) -> int:
        """临时贡献度: 达标截断, 向上贡献为 0。"""
        gpv = user.gpv or 0
        return gpv if gpv < ELITE_MARK else 0

    @staticmethod
    def _is_leg_qualified(leg_node: UserStats) -> bool:
        """文档定义的合格线判定:
        - 直属下线本人达到 Elite, 或
        - 直属下线本人未达标但其下方拥有 >= 1 条合格线 (即未断链)
        注: virtual_width > 0 必然伴随 rank >= ELITE, 所以无需重复检查.
        """
        rank = leg_node.rank or 0
        if rank >= UserLevel.ELITE:
            return True
        legs = leg_node.qualified_legs
        if legs is None:
            return False
        return len(legs) > 0

    def _load_ancestors_info(self, user_id: str) -> List[Dict[str, str]]:
        """无锁查图。

        注: 这是一个快照式查询, 调用时不持有任何 Redis 锁.
        如果在查图与拿锁之间发生父子关系变更 (CDC 重建图),
        本次返回的祖先链可能已经过时. MLM 业务中 parent 变更
        极少发生, 但若上层架构允许并发改 parent, 则需要在更高
        一层加全局闸门, 仅靠本服务的锁无法兜底这种场景.
        """

        client = Client(SCHEDULE_ADDRESS)
        try:
            dataset = client.get_dataset("graph_actor")
            actor = dataset.result()

            fut = actor.get_allparent(str(user_id))
            df_bfs = fut.result()

            if df_bfs is None or len(df_bfs) == 0:
                return []

            pdf = df_bfs.sort_values("level", ascending=True)
            # 将pdf 按行转换 每行为一个字典，例如：
            # [
            #     {'descendant': '1001', 'predecessor': '1002'}, # 第一行变成的第一个字典
            #     {'descendant': '1000', 'predecessor': '1001'}  # 第二行变成的第二个字典
            # ]
            rows = pdf[["descendant", "predecessor"]].astype(str).to_dict("records")
            seen = set()
            out = []
            for row in rows:
                # 父级节点
                ancestor_id = str(row["descendant"])
                # 当前节点
                leg_id = str(row["predecessor"])
                key = (ancestor_id, leg_id)
                if key in seen:
                    continue
                seen.add(key)
                out.append({"descendant": ancestor_id, "predecessor": leg_id})

            return out
        finally:
            client.close()

    def _acquire_locks(self, redis_conn, user_ids: List[str]):
        """有序批量拿锁。"""
        unique_ids = sorted(set(str(x) for x in user_ids), key=self._lock_sort_key)
        acquired = []

        try:
            for uid in unique_ids:
                # 提示: 如果使用 Redis Cluster, 此处的 key 可能会被路由到不同 slot
                lock = redis_conn.lock(
                    f"us_lock:{uid}",
                    timeout=LOCK_TIMEOUT,
                    blocking_timeout=LOCK_BLOCKING_TIMEOUT,
                    thread_local=True,
                )
                ok = lock.acquire(blocking=True)
                if not ok:
                    raise BusyLockError(f"获取用户锁失败: {uid}")
                acquired.append(lock)
            return acquired
        except Exception:
            self._release_locks(acquired)
            raise

    @staticmethod
    def _release_locks(locks) -> None:
        """逆序释放锁。"""
        for lock in reversed(locks):
            try:
                lock.release()
            except Exception:
                pass

    @staticmethod
    def _assert_locks_owned(locks) -> None:
        """写入前防并发覆盖检查。"""
        for lock in locks:
            try:
                if not lock.owned():
                    raise StaleLockError("锁已过期或不再属于当前任务")
            except StaleLockError:
                raise
            except Exception as e:
                raise StaleLockError(f"检查锁状态失败: {e}")

    @staticmethod
    def _refresh_locks(locks) -> None:
        for lock in locks:
            try:
                lock.extend(LOCK_TIMEOUT, replace_ttl=True)
            except Exception as e:
                raise StaleLockError(f"刷新锁 TTL 失败, 禁止继续写入: {e}")

    def _save_models_pipeline(self, redis_conn, models: List[UserStats]) -> None:
        """去重后通过 Pipeline 批量保存。"""
        if not models:
            logger.info("无变更, 跳过写入。")
            return

        dedup: Dict[str, UserStats] = {}
        for model in models:
            dedup[str(model.id)] = model

        pipe = redis_conn.pipeline(transaction=True)
        for model in dedup.values():
            model.save(pipeline=pipe)
        pipe.execute()
        logger.info("=== 集中写入完成: 批量更新 %d 个节点 ===", len(dedup))

    # =================================================================
    # 核心更新逻辑
    # =================================================================
    def update_elite_performance(self, user_id: str, bv: int):
        # region 初始化
        user_id = str(user_id)
        bv = int(bv)
        # endregion

        # region 数据验证
        if bv == 0:
            logger.info("增量 BV 为 0, 跳过处理: user_id=%s", user_id)
            return
        # endregion

        # region 1. 获取该用户所有上级的关系表
        logger.info("开始处理用户 %s 的增量 BV: %d", user_id, bv)
        ancestors_info = self._load_ancestors_info(user_id)
        # endregion

        # region 2. 收集所有可能参与计算的节点 (源 + 祖先)
        lock_user_ids = [user_id]
        for row in ancestors_info:
            lock_user_ids.append(str(row["descendant"]))
            lock_user_ids.append(str(row["predecessor"]))

        redis_conn = UserStats.db()
        last_error: Optional[Exception] = None
        # endregion

        # 3. 带重试的抢锁逻辑
        for attempt in range(1, LOCK_MAX_RETRIES + 1):
            locks = []
            try:
                # region 所有id上锁，并设定时间
                locks = self._acquire_locks(redis_conn, lock_user_ids)
                self._refresh_locks(locks)
                # endregion

                # region 参数初始化
                models_to_save: List[UserStats] = []
                processed_nodes: Dict[str, UserStats] = {}
                # endregion

                # ---------------------------------------------------------
                # Step 1: 处理源用户
                # ---------------------------------------------------------
                # region 获取当前用户
                try:
                    current_user = self._get_or_init_user(user_id)
                except NotFoundError:
                    logger.error("找不到源用户 %s, 终止计算。", user_id)
                    return

                self._normalize_qualified_legs(current_user)
                # endregion

                # region 获取当前用户状态以及等级
                prev_is_elite = current_user.is_elite
                prev_rank = current_user.rank
                # endregion

                # region 计算当前elite等级
                current_user.pv = (current_user.pv or 0) + bv
                current_user.gpv = (current_user.gpv or 0) + bv

                self._recalc_rank(current_user)
                # endregion

                # region 计算新的贡献度以及贡献差值
                old_contrib = current_user.contrib or 0
                # 计算临时贡献度，如果当前gpv小于1000，临时贡献度为当前gpv，否则为0
                new_contrib = self._calc_contrib(current_user)
                # 计算贡献差值：临时贡献度 - 当前贡献度
                delta_update = new_contrib - old_contrib
                current_user.contrib = new_contrib
                # endregion

                # region 源用户的 gpv 一定变了 (bv != 0), 将源用户信息添加到保存列表中
                models_to_save.append(current_user)
                processed_nodes[user_id] = current_user
                # endregion

                # region 判断自身资格是否有变化
                status_changed = (
                        prev_is_elite != current_user.is_elite
                        or prev_rank != current_user.rank
                )
                # endregion

                # region 早停: 贡献差值为 0 且自身资格未变 -> 不需要向上传导
                if delta_update == 0 and not status_changed:
                    logger.info(
                        "用户 %s 的 delta_update=0 且资格未变, 停止向上冒泡。", user_id
                    )
                    self._refresh_locks(locks)
                    self._assert_locks_owned(locks)
                    self._save_models_pipeline(redis_conn, models_to_save)
                    return
                # endregion

                # ---------------------------------------------------------
                # Step 2: 自底向上处理祖先
                # ---------------------------------------------------------
                for idx, row in enumerate(ancestors_info):

                    # region 获取父级节点的信息
                    ancestor_id = str(row["descendant"])
                    leg_id = str(row["predecessor"])
                    ancestor = self._get_or_init_user(ancestor_id)
                    # endregion

                    # region 记录父级节点的当前信息
                    legs = self._normalize_qualified_legs(ancestor)

                    prev_anc_is_elite = ancestor.is_elite
                    prev_anc_rank = ancestor.rank
                    prev_anc_width = len(legs)
                    # endregion

                    # 计算父级节点gpv：当前gpv+下级的贡献差值
                    ancestor.gpv = (ancestor.gpv or 0) + delta_update

                    # region 获取直推下级的信息
                    # 评估"本条分支"是否合格 -- 优先用 processed_nodes 里
                    # 已被本次事务修改过的最新内存态; 否则现读 Redis
                    # (该 leg 在 lock_user_ids 中, 我们持有它的锁).
                    leg_node = processed_nodes.get(leg_id)
                    if leg_node is None:
                        leg_node = self._get_or_init_user(leg_id)
                        self._normalize_qualified_legs(leg_node)
                    # endregion

                    # region 判断直属下级这条线是否合格，这条线合格的条件是：
                    # 1. 前驱节点自己是 Elite (rank >= 1)
                    # 2. 或者前驱节点自己不是 Elite，但他底下的子孙有 Elite (leg_total_width > 0)
                    is_leg_qualified = self._is_leg_qualified(leg_node)

                    # 维护本祖先的 qualified_legs 只动当前这条分支条目;
                    # 兄弟分支由它们各自的更新流程串行修改 (它们也要锁这个祖先).
                    if is_leg_qualified:
                        legs.add(leg_id)
                    else:
                        legs.discard(leg_id)

                    ancestor.qualified_legs = legs
                    # endregion

                    # region 重新评定祖先 rank (内部会同步更新 is_elite, virtual_width, highest_rank)
                    self._recalc_rank(ancestor)
                    # endregion

                    # region 计算贡献差值：临时贡献度-当前贡献度
                    old_ancestor_contrib = ancestor.contrib or 0
                    # 计算临时贡献度，如果当前gpv小于1000，临时贡献度为当前gpv，否则为0
                    new_ancestor_contrib = self._calc_contrib(ancestor)
                    next_delta_update = new_ancestor_contrib - old_ancestor_contrib
                    ancestor.contrib = new_ancestor_contrib
                    # endregion

                    # region 判断自身资格是否有变化
                    anc_status_changed = (
                            prev_anc_is_elite != ancestor.is_elite
                            or prev_anc_rank != ancestor.rank
                            or prev_anc_width != len(ancestor.qualified_legs)
                    )
                    # endregion

                    # region 根据条件判断 是否保存父节点
                    # gpv_changed: 入站 delta != 0 时本祖先 gpv 一定变了;
                    # 状态变化或 gpv 变化任一为真都需要保存.
                    # 注: virtual_width 跨过 0 必然伴随 rank 变化 (>= ELITE_MARK),
                    # 因此 anc_status_changed 已经覆盖 virtual_width 的有效变化.
                    gpv_changed = (delta_update != 0)
                    should_save = gpv_changed or anc_status_changed

                    processed_nodes[ancestor_id] = ancestor
                    if should_save:
                        models_to_save.append(ancestor)
                    # endregion

                    # region 链路过长时周期性续约, 防过期
                    if idx > 0 and idx % LOCK_REFRESH_INTERVAL == 0:
                        self._refresh_locks(locks)
                    # endregion

                    # region 早停: 上传业绩差值=0 且 本祖先资格状态未改变
                    # 把本层算出的 next_delta 作为给上层的输入
                    delta_update = next_delta_update

                    if delta_update == 0 and not anc_status_changed:
                        logger.info("到达上级用户 %s 时, 传导安全停止。", ancestor_id)
                        break
                    # endregion

                # ---------------------------------------------------------
                # Step 3: 落库前再续约 + 验锁, 把 TOCTOU 窗口压到最小
                # ---------------------------------------------------------
                self._refresh_locks(locks)
                self._assert_locks_owned(locks)
                self._save_models_pipeline(redis_conn, models_to_save)
                return

            except (BusyLockError, StaleLockError,
                    redis.exceptions.ConnectionError,
                    redis.exceptions.TimeoutError) as e:
                # 锁错误 / Redis 瞬断 -> 退避重试
                last_error = e
                logger.warning(
                    "第 %d/%d 次尝试失败 (锁/网络异常): %s",
                    attempt, LOCK_MAX_RETRIES, e
                )
                sleep_seconds = LOCK_RETRY_BASE_SLEEP * (2 ** (attempt - 1))
                time.sleep(sleep_seconds)

            # BrokenAncestorChainError 不在此处吞掉, 直接抛出让上层告警/转人工,
            # 因为重试不会自愈 (它是数据断层而非并发问题).

            finally:
                self._release_locks(locks)

        # 超出最大重试次数
        raise RuntimeError(
            f"并发抢锁重试失败, 订单可能未处理: "
            f"user_id={user_id}, bv={bv}, last_error={last_error}"
        )
