from pydantic import BaseModel
from typing import Optional


class ChangeUserInfoMsg(BaseModel):
    id: int
    user_name: Optional[str] = None
    real_name: Optional[str] = None
    country_id: Optional[int] = None
    op: Optional[str] = None
    updatetime: Optional[int] = None
    event_ts: Optional[str] = None
