import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.common.types import Money
from app.common.validators import reject_explicit_null
from app.salary.models import SalaryPaymentType
from app.staff.models import StaffRoleEnum


class SalaryPaymentCreate(BaseModel):
    staff_id: int
    # Omitted -> defaults to now (Asia/Tashkent) in the service layer.
    paid_at: datetime | None = None
    period_start: date
    period_end: date
    payment_type: SalaryPaymentType
    amount: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def _validate_period(self) -> "SalaryPaymentCreate":
        if self.period_start > self.period_end:
            raise ValueError("period_start cannot be after period_end")
        return self


class SalaryPaymentUpdate(BaseModel):
    staff_id: int | None = None
    paid_at: datetime | None = None
    period_start: date | None = None
    period_end: date | None = None
    payment_type: SalaryPaymentType | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    _no_nulls = reject_explicit_null(
        "paid_at", "period_start", "period_end", "payment_type", "amount"
    )


class SalaryPaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    staff_id: int | None
    paid_at: datetime
    period_start: date
    period_end: date
    payment_type: SalaryPaymentType
    amount: Money
    created_by_id: uuid.UUID
    is_voided: bool
    voided_at: datetime | None
    voided_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class StaffEarnedPaidSummary(BaseModel):
    staff_id: int
    name: str
    role: StaffRoleEnum
    earned: Money
    paid: Money
    remaining: Money


class StaffLifetimeSummary(BaseModel):
    staff_id: int
    name: str
    role: StaffRoleEnum
    lifetime_earned: Money
    lifetime_paid: Money
    lifetime_remaining: Money
