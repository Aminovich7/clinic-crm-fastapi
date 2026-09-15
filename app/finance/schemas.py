import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PaginatedResponse, PaginationParams
from app.common.types import Money
from app.finance.models import ConsultationType

__all__ = [
    "PaginationParams",
    "PaginatedResponse",
    "ConsultationCreate",
    "ConsultationUpdate",
    "ConsultationRead",
    "SurgeryCreate",
    "SurgeryUpdate",
    "SurgeryRead",
    "RoomCreate",
    "RoomUpdate",
    "RoomRead",
    "FinanceSettingsRead",
    "FinanceSettingsUpdate",
    "DoctorShareReport",
    "ConsultationTypeSummary",
    "ConsultationReport",
    "SurgeryReport",
    "RoomReport",
    "TotalReport",
]


class ConsultationCreate(BaseModel):
    type: ConsultationType
    receipt_number: int = Field(gt=0)
    # Omitted -> defaults to "now" (Asia/Tashkent) in the service layer.
    # Always explicit/editable so an assistant/manager can backdate it.
    date: datetime | None = None
    amount: Decimal = Field(ge=0)
    doctor_percent: Decimal = Field(ge=0, le=100)
    # Omitted (None) -> the service applies the dynamic SystemSetting
    # default. An explicit value here is always respected as-is.
    minus_beshming: Decimal | None = Field(default=None, ge=0)
    doctor_id: int | None = None


class ConsultationUpdate(BaseModel):
    type: ConsultationType | None = None
    receipt_number: int | None = Field(default=None, gt=0)
    date: datetime | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    doctor_percent: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
    )
    minus_beshming: Decimal | None = Field(
        default=None,
        ge=0,
    )
    doctor_id: int | None = None


class ConsultationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: ConsultationType
    receipt_number: int
    date: datetime
    amount: Money
    doctor_percent: Money
    minus_beshming: Money | None
    doctor_id: int | None
    created_by_id: uuid.UUID
    is_voided: bool
    voided_at: datetime | None
    voided_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class SurgeryCreate(BaseModel):
    receipt_number: int = Field(gt=0)
    date: datetime | None = None
    amount: Decimal = Field(ge=0)
    surgery_expense: Decimal = Field(ge=0)
    doctor_percent: Decimal = Field(ge=0, le=100)
    doctor_id: int | None = None


class SurgeryUpdate(BaseModel):
    receipt_number: int | None = Field(default=None, gt=0)
    date: datetime | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    surgery_expense: Decimal | None = Field(default=None, ge=0)
    doctor_percent: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
    )
    doctor_id: int | None = None


class SurgeryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_number: int
    date: datetime
    amount: Money
    surgery_expense: Money
    doctor_percent: Money
    doctor_id: int | None
    created_by_id: uuid.UUID
    is_voided: bool
    voided_at: datetime | None
    voided_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class RoomCreate(BaseModel):
    receipt_number: int | None = Field(
        default=None,
        gt=0,
    )
    date: datetime | None = None
    amount: Decimal = Field(ge=0)
    doctor_percent: Decimal = Field(ge=0, le=100)
    doctor_id: int | None = None


class RoomUpdate(BaseModel):
    receipt_number: int | None = Field(
        default=None,
        gt=0,
    )
    date: datetime | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    doctor_percent: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
    )
    doctor_id: int | None = None


class RoomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_number: int | None
    date: datetime
    amount: Money
    doctor_percent: Money
    doctor_id: int | None
    created_by_id: uuid.UUID
    is_voided: bool
    voided_at: datetime | None
    voided_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class FinanceSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    default_minus_beshming: Money
    updated_at: datetime
    updated_by_id: uuid.UUID | None


class FinanceSettingsUpdate(BaseModel):
    default_minus_beshming: Decimal = Field(ge=0)


class DoctorShareReport(BaseModel):
    doctor_id: int
    name: str
    total_share: Money
    count: int


class ConsultationTypeSummary(BaseModel):
    total: Money
    count: int


class ConsultationReport(BaseModel):
    korik: ConsultationTypeSummary
    qayta_korik: ConsultationTypeSummary

    total_income: Money
    total_doctor_share: Money
    total_clinic_profit: Money
    total_consultation_expense: Money

    doctor_shares: list[DoctorShareReport]


class SurgeryReport(BaseModel):
    surgery_total_income: Money
    surgery_total_doctor_share: Money
    surgery_total_clinic_profit: Money
    surgery_total_expense: Money

    surgery_doctor_shares: list[DoctorShareReport]


class RoomReport(BaseModel):
    room_total_income: Money
    room_total_doctor_share: Money
    room_total_clinic_profit: Money

    room_doctor_shares: list[DoctorShareReport]


class TotalReport(BaseModel):
    consultation_income: Money
    consultation_doctor_share: Money
    consultation_expense: Money
    consultation_clinic_profit: Money

    surgery_income: Money
    surgery_doctor_share: Money
    surgery_expense: Money
    surgery_clinic_profit: Money

    room_income: Money
    room_doctor_share: Money
    room_clinic_profit: Money

    total_income: Money
    total_doctor_share: Money
    total_expense: Money
    total_clinic_profit: Money
