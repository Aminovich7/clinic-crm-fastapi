from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.common.types import Money
from app.staff.models import StaffRoleEnum, StaffStatusEnum


class StaffCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    role: StaffRoleEnum
    specialty: str | None = Field(default=None, max_length=50)
    fixed_salary: Decimal | None = Field(default=None, ge=0)
    hire_date: date | None = None

    @model_validator(mode="after")
    def _validate_role_fields(self) -> "StaffCreate":
        if self.role == StaffRoleEnum.DOCTOR:
            if not self.specialty or not self.specialty.strip():
                raise ValueError("specialty is required for doctors")
            if self.fixed_salary is not None:
                raise ValueError("fixed_salary is not applicable to doctors")
        return self


class StaffUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=50)
    last_name: str | None = Field(default=None, min_length=1, max_length=50)
    role: StaffRoleEnum | None = None
    specialty: str | None = Field(default=None, max_length=50)
    fixed_salary: Decimal | None = Field(default=None, ge=0)
    hire_date: date | None = None


class StaffRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    specialty: str | None
    role: StaffRoleEnum
    fixed_salary: Money | None
    status: StaffStatusEnum
    hire_date: date | None
    created_at: datetime
    updated_at: datetime


class StaffOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: StaffRoleEnum
