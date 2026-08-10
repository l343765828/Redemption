"""
EliteBonusStats - Elite Bonus 增量结算的状态实体

职责: 持有单个 (period_num, user_id) 在本期内的增量结算上下文。
对应 SQL 中的 AR_CALC_BE_E_NET 行,但语义是事件驱动维护、而非每期重铺。

key 形态: pk = "{period_num}:{user_id}",由 EliteBonusService 统一生成。

⚠️ 与 UserStats 的边界: 那个实体维护的是用户长效晋级状态(rank / highest_rank);
本实体维护的是周期性奖金结算的临时状态。两者必须物理分离,详见架构决策记录。
"""

from typing import Optional, Set
from Redishelper.BaseRedisModel import BaseRedisModel
from redis_om import Field


class EliteBonusStats(BaseRedisModel, index=True):
    id: str= Field(primary_key=True)
    user_id: str
    period_num: int = Field(index=True)  # 索引必须有,期末快照走 find 查询

    # region PVAM 金额编码版本（legacy/unknown 默认不写 2）
    amount_encoding_version: Optional[int] = None
    # endregion

    # ---- 基础业绩(财务口径) ----
    pv_pcs: Optional[int] = 0    # 个人消费(本期累计,可被退单负向调整)
    gpv: Optional[int] = 0       # 原始累计 GPV,含下线临时上贡(用于路径 A 阈值判定)
    gpv_real: Optional[int] = 0  # 真实计奖 GPV;合格时 = gpv,不合格时 = 0

    # ---- 增量状态机核心 ----
    contrib_to_parent: Optional[int] = 0  # 当前向上贡献值(合格后截断为 0)
    qualified_downlines: Set[str] = Field(default_factory=set)  # 本期已合格的直属下线

    # ---- 资格状态 ----
    is_qualified: Optional[bool] = Field(default=False, index=True)  # 等价 SQL 的 ELITE_CALC_ID = 10
    # 合格路径：
    # 'A' = 自身 GPV>=1000;
    # 'B' = 被动连带合格;
    # None = 未合格
    qualifying_path: Optional[str] = None  # 'A' = 自身 GPV>=1000;'B' = 被动连带合格;None = 未合格

    # ---- 奖金预估(实时跳动,期末快照固化) ----
    estimated_bonus: Optional[float] = 0.0
    # region PVAM additive V2 空白载体（不由 legacy float 折算）
    estimated_bonus_cents: Optional[int] = None
    # endregion

    class Meta:
        global_key_prefix = "elite_bonus_stats"
