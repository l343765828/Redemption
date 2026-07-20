from dataclasses import dataclass
from decimal import Decimal

@dataclass
class OrderPayload:
    orderid: str
    userid: int
    amount: Decimal
