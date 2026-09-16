import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.types import Money


class ExpenseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    amount: Decimal = Field(ge=0)
    # Omitted -> defaults to now (Asia/Tashkent) in the service layer.
    date: datetime | None = None


class ExpenseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    amount: Decimal | None = Field(default=None, ge=0)
    date: datetime | None = None


class ExpenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    amount: Money
    date: datetime
    created_by_id: uuid.UUID
    is_voided: bool
    voided_at: datetime | None
    voided_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ExpenseSummary(BaseModel):
    total_amount: Money
    count: int
