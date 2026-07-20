from pydantic import BaseModel
from typing import Optional


class ChangeUserMsg(BaseModel):
    id: str
    user: Optional[str] = None
    parent: Optional[str] = None
    op: Optional[str] = None
    updatetime: Optional[int] = None
    event_ts: Optional[str] = None
    placementId: Optional[str] = None
    placementLeg: Optional[str] = None
