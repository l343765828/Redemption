from typing import Optional, Set
from Redishelper.BaseRedisModel import BaseRedisModel
from redis_om import Field


# 用户状态模型
class UserStats(BaseRedisModel, index=True):
    id: str
    period: str = Field(index=True)
    user_id: Optional[str] = None
    pv: Optional[int] = 0
    gpv: Optional[int] = 0
    # PE/SE 晋级口径下拆分后的真实业绩：
    # - GPV < 2000 时，不产生虚拟宽度，真实业绩等于当前 GPV；
    # - GPV >= 2000 时，真实业绩封顶为 1000，超出部分进入 gpv_unreal。
    gpv_real: Optional[int] = 0
    # PE/SE 晋级口径下由高 GPV 折算出来的虚拟业绩金额/BV。
    # 注意：virtual_width 是“虚拟宽度数量”，gpv_unreal 是“虚拟业绩数值”，两者不能混用。
    gpv_unreal: Optional[int] = 0
    contrib: Optional[int] = 0
    # 使用 Field 设置默认值并开启索引
    is_elite: Optional[bool] = Field(default=False, index=True)
    # 虚拟宽度下级的数量
    virtual_width: Optional[int] = 0
    # 记录当前级别: 0=普通, 10=Elite, 20=Pro Elite, 30=Super Elite
    rank: Optional[int] = 0
    # 记录哪些"直属下线"是合格线
    qualified_legs: Set[str] = Field(default_factory=set)
    # ==========================================
    # 双轨制 (安置网) 业绩与结转字段
    # ==========================================
    # 1. 本期新增业绩 (对应 SQL MID5)
    pv_1l: Optional[int] = 0
    pv_2l: Optional[int] = 0

    # 2. 期初历史结余 (从 N-1 期的 remain_surplus 跨期拉取)
    pre_surplus_1l: Optional[int] = 0
    pre_surplus_2l: Optional[int] = 0

    # 3. 本期对碰总结余 (对应 SQL MID8: TOTAL = 新增 PV + 期初结余)
    total_1l: Optional[int] = 0
    total_2l: Optional[int] = 0

    # 4. 期末剩余结余 (零活动过桥备用，及供下游对碰模块扣减后回写)
    remain_surplus_1l: Optional[int] = 0
    remain_surplus_2l: Optional[int] = 0
    # 本期 remain_surplus 是否已由下游对碰模块结算写入；True 后增量服务不再桥接 remain
    placement_initialized: Optional[bool] = False
    placement_settled: Optional[bool] = False
    placement_revision: Optional[int] = 0
    settled_revision: Optional[int] = 0

    class Meta:
        global_key_prefix = "user_stats"
