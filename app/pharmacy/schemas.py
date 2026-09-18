import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.common.types import Money
from app.common.validators import reject_explicit_null


class PharmacyEntryCreate(BaseModel):
    # Omitted -> defaults to now (Asia/Tashkent) in the service layer.
    date: datetime | None = None
    medicine_cost: Decimal | None = Field(default=None, ge=0)
    amount_paid: Decimal | None = Field(default=None, ge=0)
    comment: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _require_one_value(self) -> "PharmacyEntryCreate":
        if self.medicine_cost is None and self.amount_paid is None:
            raise ValueError("At least one of medicine_cost or amount_paid is required")
        return self


class PharmacyEntryUpdate(BaseModel):
    date: datetime | None = None
    medicine_cost: Decimal | None = Field(default=None, ge=0)
    amount_paid: Decimal | None = Field(default=None, ge=0)
    comment: str | None = Field(default=None, max_length=500)
    # medicine_cost, amount_paid and comment are all nullable; the
    # "at least one of the two amounts" rule is enforced in the service.
    _no_nulls = reject_explicit_null("date")


class PharmacyEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: datetime
    medicine_cost: Money | None
    amount_paid: Money | None
    comment: str | None
    created_by_id: uuid.UUID
    is_voided: bool
    voided_at: datetime | None
    voided_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class PharmacyBalance(BaseModel):
    total_paid: Money
    total_medicine_cost: Money
    balance: Money
