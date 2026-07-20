from Redishelper.BaseRedisModel import BaseRedisModel
from redis_om import Field
from typing import Optional


# 历史最高数据
class UserPeriodHighestRank(BaseRedisModel, index=True):
    id: str
    period: str = Field(index=True)
    user_id: Optional[str] = None
    current_rank: Optional[int] = 0
    prev_highest_rank: Optional[int] = 0
    highest_rank: Optional[int] = 0
    prev_period: Optional[str] = None
    settled_run_id: str = ""
    settled_at: int = 0
