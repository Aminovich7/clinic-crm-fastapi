import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StaffRoleEnum(str, enum.Enum):
    DOCTOR = "doctor"
    NURSE = "nurse"
    OTHER = "other"


class StaffStatusEnum(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Staff(Base):
    __tablename__ = "staff"

    __table_args__ = (
        CheckConstraint(
            "role != 'doctor' OR fixed_salary IS NULL",
            name="ck_staff_fixed_salary_doctor_null",
        ),
        CheckConstraint(
            "fixed_salary IS NULL OR fixed_salary >= 0",
            name="ck_staff_fixed_salary_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)

    # Only meaningful for role=DOCTOR — nullable so nurse/other rows can
    # omit it.
    specialty: Mapped[str | None] = mapped_column(String(50), nullable=True)

    role: Mapped[StaffRoleEnum] = mapped_column(
        Enum(StaffRoleEnum, name="staff_role", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )

    # Only meaningful for role in (NURSE, OTHER) — see
    # ck_staff_fixed_salary_doctor_null.
    fixed_salary: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 0),
        nullable=True,
    )

    status: Mapped[StaffStatusEnum] = mapped_column(
        Enum(StaffStatusEnum, name="staff_status", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=StaffStatusEnum.ACTIVE,
    )

    # Optional; used as the lifetime-earnings proration start for
    # nurse/other staff when set. Falls back to created_at.date() if null.
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
