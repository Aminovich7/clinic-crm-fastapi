import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.finance.mixins import TimestampMixin, VoidableMixin


class SalaryPaymentType(str, enum.Enum):
    FULL = "full"
    AVANS = "avans"


class SalaryPayment(Base, TimestampMixin, VoidableMixin):
    """Oyliklar — a recorded salary/avans payment for a staff member.

    The amount is always manager-free-typed; it is never validated against
    the computed "earned" figure (see app.salary.service.compute_earned_amount).
    """

    __tablename__ = "salary_payments"

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_salary_payments_amount_non_negative"),
        CheckConstraint(
            "period_start <= period_end",
            name="ck_salary_payments_period_valid",
        ),
        Index("ix_salary_payments_staff_id", "staff_id"),
        Index(
            "ix_salary_payments_period",
            "staff_id",
            "period_start",
            "period_end",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    staff_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff.id", ondelete="SET NULL"),
        nullable=True,
    )

    # When this payment was actually recorded/disbursed.
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # The pay period this payment is meant to cover.
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    payment_type: Mapped[SalaryPaymentType] = mapped_column(
        Enum(
            SalaryPaymentType,
            name="salary_payment_type",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 0), nullable=False)

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
