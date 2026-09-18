import uuid
from datetime import date as date_
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.types import Money
from app.common.validators import reject_explicit_null


class DutyEntryCreate(BaseModel):
    staff_id: int
    # Omitted -> defaults to today (Asia/Tashkent) in the service layer.
    date: date_ | None = None
    amount: Decimal = Field(ge=0)


class DutyEntryUpdate(BaseModel):
    staff_id: int | None = None
    date: date_ | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    _no_nulls = reject_explicit_null("date", "amount")


class DutyEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    staff_id: int | None
    date: date_
    amount: Money
    created_by_id: uuid.UUID
    is_voided: bool
    voided_at: datetime | None
    voided_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
