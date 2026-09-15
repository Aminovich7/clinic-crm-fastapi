from datetime import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, declared_attr


class TimestampMixin:
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


class VoidableMixin:
    is_voided: Mapped[bool] = mapped_column(
        default=False,
        server_default="false",
        nullable=False,
    )

    voided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    @declared_attr
    def voided_by_id(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(
            ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        )