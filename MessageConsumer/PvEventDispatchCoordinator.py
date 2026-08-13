"""将同一 NormalizedPvEvent 投递到三条增量链并在全部成功后确认。"""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from MessageConsumer.PvEventNormalizer import PvEventNormalizer
from Model.Order.NormalizedPvEvent import (
    NormalizedPvEvent,
    require_normalized_pv_event,
)


class UserStatsIncrementalStage(Protocol):
    def update_elite_performance(
        self,
        *,
        user_id: str,
        normalized_event: NormalizedPvEvent,
    ) -> Any:
        ...


class PlacementIncrementalStage(Protocol):
    def update_placement_performance(
        self,
        *,
        user_id: str,
        normalized_event: NormalizedPvEvent,
    ) -> Any:
        ...


class EliteBonusIncrementalStage(Protocol):
    def update_elite_bonus_incremental(
        self,
        *,
        user_id: str,
        normalized_event: NormalizedPvEvent,
    ) -> Any:
        ...


class PvEventDispatchCoordinator:
    """生产编排边界；网络消费者只需在外层负责消息拉取与提交。"""

    def __init__(
        self,
        normalizer: PvEventNormalizer,
        *,
        user_stats_service: UserStatsIncrementalStage,
        placement_service: PlacementIncrementalStage,
        elite_bonus_service: EliteBonusIncrementalStage,
    ) -> None:
        # region 参数验证
        if not isinstance(normalizer, PvEventNormalizer):
            raise TypeError("normalizer must be PvEventNormalizer")
        if user_stats_service is None:
            raise TypeError("user_stats_service is required")
        if placement_service is None:
            raise TypeError("placement_service is required")
        if elite_bonus_service is None:
            raise TypeError("elite_bonus_service is required")
        # endregion
        self._normalizer = normalizer
        self._user_stats_service = user_stats_service
        self._placement_service = placement_service
        self._elite_bonus_service = elite_bonus_service

    def dispatch_order(self, payload: Mapping[str, Any]) -> NormalizedPvEvent:
        event = self._normalizer.normalize_order(payload)
        return self._dispatch(event)

    def dispatch_refund(self, payload: Mapping[str, Any]) -> NormalizedPvEvent:
        event = self._normalizer.normalize_refund(payload)
        return self._dispatch(event)

    def _dispatch(self, normalized_event: NormalizedPvEvent) -> NormalizedPvEvent:
        event = require_normalized_pv_event(normalized_event)

        # region 已完成事件短路
        if event.disposition == "DUPLICATE_NOOP":
            return event
        # endregion

        # region 同一事件投递三条增量链
        # 任一 stage 抛错都会阻止 ack；重试继续读取 PENDING，并由各 stage 的事件幂等键补齐。
        self._user_stats_service.update_elite_performance(
            user_id=event.user_id,
            normalized_event=event,
        )
        self._placement_service.update_placement_performance(
            user_id=event.user_id,
            normalized_event=event,
        )
        self._elite_bonus_service.update_elite_bonus_incremental(
            user_id=event.user_id,
            normalized_event=event,
        )
        # endregion

        # region 三链成功后确认投递
        # ack 必须位于最后；即使 Redis 已提交后连接断开，重试也会读取 DISPATCHED 并安全短路。
        self._normalizer.acknowledge_dispatched(event)
        # endregion
        return event
