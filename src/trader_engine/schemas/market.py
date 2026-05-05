from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class MarketOutcome(str, Enum):
    YES = "YES"
    NO = "NO"


class PricePoint(BaseModel):
    timestamp: int  # unix seconds
    price: float = Field(ge=0.0, le=1.0)


class Market(BaseModel):
    condition_id: str
    question: str
    category: str
    start_date: datetime
    end_date: datetime
    volume_usd: float
    outcome: MarketOutcome
    price_t1: float | None = None
    price_t7: float | None = None
    price_t30: float | None = None

    @property
    def resolved_yes(self) -> bool:
        return self.outcome == MarketOutcome.YES
