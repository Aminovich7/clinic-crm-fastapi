import enum
import uuid

from datetime import datetime
from decimal import Decimal
from app.finance.mixins import TimestampMixin, VoidableMixin

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)


from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class ConsultationType(str, enum.Enum):
    KORIK = "korik"
    QAYTAKORIK = "qaytakorik"

class Consultation(Base, TimestampMixin, VoidableMixin):
    __tablename__ = "consultations"
    __table_args__ = (

        CheckConstraint(
            "amount >= 0",
            name = "ck_consultations_amount_non_negative",
        ),
        CheckConstraint (
            "doctor_percent >= 0 AND doctor_percent <= 100",
            name = "ck_consultation_doctor_percent_range",
        ),
        CheckConstraint(
            "minus_beshming >= 0",
            name = "ck_consultation_minusbeshming_non_negative",
        ),
    )


    id: Mapped[int] = mapped_column(
        primary_key = True,
        autoincrement=True,
    )

    type: Mapped[ConsultationType] = mapped_column(
        Enum(
            ConsultationType,
            name="consultation_type",
        ),
        nullable=False,
    )

    receipt_number: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )

    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12,0),
        nullable=False,

    )

    doctor_percent: Mapped[Decimal] = mapped_column(
        Numeric(5,2), nullable=False,

    )

    # No model-level default and no server_default here on purpose — the
    # default value comes from the dynamic SystemSetting row (see below)
    # and is applied in the service layer at create time only.
    minus_beshming: Mapped[Decimal | None] = mapped_column(
        Numeric(12,0),
        nullable=True,
    )

    doctor_id: Mapped[int | None] = mapped_column(ForeignKey(
        "staff.id",
        ondelete="SET NULL",
    ),
    nullable=True,
    )


    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )



class Surgery(Base, TimestampMixin, VoidableMixin):
    __tablename__ = "surgeries"


    __table_args__ =(
        CheckConstraint(
            "amount>=0",
            name="ck_surgeries_amount_non_negative",
        ),
        CheckConstraint(
            "doctor_percent >= 0 AND doctor_percent <= 100",
            name="ck_surgeries_doctor_percent_range",
        ),
        CheckConstraint(
            "surgery_expense >= 0",
            name="ck_surgeries_expense_non_negative",
        ),

    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )


    receipt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12,0),
        nullable=False,
    )

    surgery_expense: Mapped[Decimal] = mapped_column(
        Numeric(12,0),
        nullable=False,
    )

    doctor_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )

    doctor_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "staff.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )


class Room(Base, TimestampMixin, VoidableMixin):
    __tablename__ = "rooms"

    __table_args__ = (
        CheckConstraint(
            "amount >= 0",
            name="ck_rooms_amount_non_negative",
        ),
        CheckConstraint(
            "doctor_percent >= 0 AND doctor_percent <= 100",
            name="ck_rooms_doctor_percent_range",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    receipt_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12,0),
        nullable=False,
    )

    doctor_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )

    doctor_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "staff.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )


class SystemSetting(Base):
    """Singleton row (id is always 1) holding clinic-wide finance defaults."""

    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(primary_key=True)

    default_minus_beshming: Mapped[Decimal] = mapped_column(
        Numeric(12, 0),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
