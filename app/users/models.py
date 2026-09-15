import enum
import uuid
from datetime import date, datetime

from typing import Optional
from sqlalchemy import func, Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserRoleEnum(str, enum.Enum):
    SUPERADMIN = "superadmin"
    MANAGER = "manager"
    ASSISTANT = "assistant"


class UserStatusEnum(str, enum.Enum):
    APPROVED = "approved"
    BLOCKED = "blocked"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True, 
        default=uuid.uuid4)

    username: Mapped[str]=mapped_column(String(64), 
    unique=True, 
    index=True,
    nullable=False)

    full_name: Mapped[str] = mapped_column(String(50))
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRoleEnum] = mapped_column(Enum(UserRoleEnum, name="user_role"),
    nullable=False)

    status: Mapped[UserStatusEnum] = mapped_column(Enum(UserStatusEnum, name="user_status"), 
    default=UserStatusEnum.APPROVED, nullable=False)

    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"),
        nullable=True
    )
    created_by: Mapped[Optional["User"]] = relationship(remote_side=[id])
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())









# class TimestampMixin:
#     """Yozuv qachon yaratilgani va oxirgi marta qachon o'zgargani."""

#     created_at: Mapped[datetime] = mapped_column(
#         DateTime(timezone=True), server_default=func.now()
#     )
#     updated_at: Mapped[datetime] = mapped_column(
#         DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
#     )



# class UuidPrimaryKeyMixin:
#     """Har bir jadvalning birlamchi kaliti — UUID."""

#     id: Mapped[uuid.UUID] = mapped_column(
#         Uuid, primary_key=True, default=uuid.uuid4
#     )
