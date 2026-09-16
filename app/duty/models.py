import uuid
from datetime import date as date_
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.finance.mixins import TimestampMixin, VoidableMixin


class DutyEntry(Base, TimestampMixin, VoidableMixin):
    """Navbatchilik — overtime-duty entitlement. Not itself a payment."""

    __tablename__ = "duty_entries"

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_duty_entries_amount_non_negative"),
        Index("ix_duty_entries_staff_id", "staff_id"),
        Index("ix_duty_entries_date", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    staff_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff.id", ondelete="SET NULL"),
        nullable=True,
    )

    date: Mapped[date_] = mapped_column(Date, nullable=False)

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 0), nullable=False)

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
