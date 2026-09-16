import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.finance.mixins import TimestampMixin, VoidableMixin


class PharmacyEntry(Base, TimestampMixin, VoidableMixin):
    """Dorixona — pharmacy running-balance ledger.

    Never referenced by any report or the dashboard — standalone feature.
    """

    __tablename__ = "pharmacy_entries"

    __table_args__ = (
        CheckConstraint(
            "medicine_cost IS NULL OR medicine_cost >= 0",
            name="ck_pharmacy_entries_cost_non_negative",
        ),
        CheckConstraint(
            "amount_paid IS NULL OR amount_paid >= 0",
            name="ck_pharmacy_entries_paid_non_negative",
        ),
        CheckConstraint(
            "medicine_cost IS NOT NULL OR amount_paid IS NOT NULL",
            name="ck_pharmacy_entries_not_both_null",
        ),
        Index("ix_pharmacy_entries_date", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    medicine_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 0), nullable=True)
    amount_paid: Mapped[Decimal | None] = mapped_column(Numeric(12, 0), nullable=True)

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
