import logging
import time
from typing import List, Dict, Set
from Model.User.UserStats import UserStats
import Model.User.UserLevel as UserLevel
from dask.distributed import Client

# 复用父类的常量
from User.UserStatsService import (
    UserStatsService,
    BusyLockError,
    StaleLockError,
    LOCK_MAX_RETRIES,
    LOCK_RETRY_BASE_SLEEP,
    SCHEDULE_ADDRESS
)

logger = logging.getLogger(__name__)


class TopologyMutationService(UserStatsService):
    """
    拓扑变更事务编排器 + 受影响链路重算器。
    处理跳线、团队重组等父子关系变更，并修复上下游的 GPV 与合格线状态。
    """

    def orchestrate_topology_mutation(self, target_node_id: str, cdc_version: int, change_list: list):
        """
        拓扑变更全局编排器。
        ⚠️【前提】：必须全局封板；图更新不可回滚，若重算失败必须告警转人工处理。
        """
        target_node_id = str(target_node_id)

        # 整个长事务生命周期内，只开启一次 Client
        client = Client(SCHEDULE_ADDRESS)

        try:
            dataset = client.get_dataset("graph_actor")
            actor = dataset.result()

            # 1. 前置校验：CDC 幂等性拦截
            try:
                current_cdc_version = int(client.get_dataset("users_cdc_version"))
                if cdc_version <= current_cdc_version:
                    logger.info(f"CDC Version {cdc_version} 已被处理，跳过拓扑重算。")
                    return
            except Exception as e:
                logger.warning(f"获取当前 CDC 版本失败 (可能是首次运行)，继续执行: {e}")

            # 2. 图更新前，提取旧链路 (复用 actor)
            logger.info(f"提取节点 {target_node_id} 的旧祖先链路...")
            old_ancestors_info = self._load_ancestors_info(target_node_id, graph_actor=actor)

            # 3. 触发底层图结构更新
            logger.info(f"触发图拓扑更新，CDC Version: {cdc_version}...")
            actor.run_update(version=cdc_version, changList=change_list, npartitions=1, renumber_disable=False).result()

            # 4. 图更新后，提取新链路 (复用 actor)
            logger.info(f"提取节点 {target_node_id} 的新祖先链路...")
            new_ancestors_info = self._load_ancestors_info(target_node_id, graph_actor=actor)

            # 5. 构造合并去重且排好序的执行链 (根据在树中的绝对深度)
            depth_map: Dict[str, int] = {}
            old_len = len(old_ancestors_info)
            new_len = len(new_ancestors_info)

            # 处理旧链路
            for idx, row in enumerate(old_ancestors_info):
                anc = str(row["descendant"])
                distance = int(row.get("level", idx + 1))
                depth_map[anc] = old_len - distance

            # 处理新链路
            for idx, row in enumerate(new_ancestors_info):
                anc = str(row["descendant"])
                distance = int(row.get("level", idx + 1))
                depth_map[anc] = new_len - distance

            # 按绝对深度降序排序：深度值越大的（越靠近树的叶子端），越先计算
            sorted_ancestors = sorted(depth_map.keys(), key=lambda k: -depth_map[k])

            if not sorted_ancestors:
                logger.info("未发现受影响的祖先链路，操作结束。")
                return

            self._heal_topology_mutation(target_node_id, sorted_ancestors, actor)

        finally:
            client.close()

    def _heal_topology_mutation(self, target_node_id: str, sorted_ancestors: List[str], graph_actor):
        """执行 Redis 状态重构"""

        lock_user_ids = [target_node_id] + sorted_ancestors
        redis_conn = UserStats.db()
        last_error = None

        # 【性能优化】：将 RPC 批量拉取提到重试循环外
        children_map_future = graph_actor.get_direct_children_batch(sorted_ancestors)
        children_map = children_map_future.result()
        if children_map is None:
            raise RuntimeError("Graph Actor 返回的直推下级映射为 None，请检查底层图服务状态。")

        for attempt in range(1, LOCK_MAX_RETRIES + 1):
            locks = []
            try:
                # 1. 批量上锁
                locks = self._acquire_locks(redis_conn, lock_user_ids)
                self._refresh_locks(locks)

                # 2. 剥夺受影响祖先的派生状态
                nodes_map: Dict[str, UserStats] = {}

                # Target 节点提供数据，绝不清零状态
                target_node = self._get_or_init_user(target_node_id)
                nodes_map[target_node_id] = target_node

                for uid in sorted_ancestors:
                    node = self._get_or_init_user(uid)
                    node.gpv = node.pv or 0
                    node.is_elite = False
                    node.rank = UserLevel.NOTHING
                    node.qualified_legs = set()
                    node.virtual_width = 0
                    node.contrib = 0
                    nodes_map[uid] = node

                # 3. 基于绝对深度，自底向上单次聚合
                for uid in sorted_ancestors:
                    self._recalculate_node_state(
                        node=nodes_map[uid],
                        children_ids=children_map.get(uid, []),
                        nodes_map=nodes_map
                    )

                # 4. 集中事务落库
                self._refresh_locks(locks)
                self._assert_locks_owned(locks)

                models_to_save = [nodes_map[uid] for uid in sorted_ancestors]
                self._save_models_pipeline(redis_conn, models_to_save)

                logger.info(f"✅ 节点 {target_node_id} 相关的拓扑重算成功落库。")
                return

            except (BusyLockError, StaleLockError) as e:
                last_error = e
                logger.warning(f"抢锁/验证失败，准备重试 ({attempt}/{LOCK_MAX_RETRIES}): {e}")
                time.sleep(LOCK_RETRY_BASE_SLEEP * (2 ** (attempt - 1)))
            except Exception as e:
                last_error = e
                break
            finally:
                self._release_locks(locks)

        raise RuntimeError(f"❌ 拓扑重算事务失败，产生脏数据风险！请研发介入。Error: {last_error}")

    def _recalculate_node_state(self, node: UserStats, children_ids: List[str], nodes_map: Dict[str, UserStats]):
        """单节点的本地纯内存聚合运算 (完全无外部 IO)"""

        current_gpv = node.pv or 0
        qualified_legs = set()

        for child_id in children_ids:
            if child_id in nodes_map:
                child_node = nodes_map[child_id]
            else:
                child_node = self._get_or_init_user(child_id)

            current_gpv += (child_node.contrib or 0)

            if self._is_leg_qualified(child_node):
                qualified_legs.add(child_node.id)

        node.gpv = current_gpv
        node.qualified_legs = qualified_legs

        # 高水位 highest_rank 保留
        self._recalc_rank(node)
        node.contrib = self._calc_contrib(node)