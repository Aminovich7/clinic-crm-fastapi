from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class VoidedRecordRead(BaseModel):
    """One voided record, normalised across the seven voidable tables."""

    resource_type: str
    resource_label: str
    id: int
    summary: str
    date: datetime | None
    amount: Decimal | None
    voided_at: datetime | None
    voided_by_name: str | None
