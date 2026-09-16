import pytest
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.staff.models import StaffRoleEnum
from app.staff.schemas import StaffCreate
from app.staff.service import create_staff
from app.finance.schemas import RoomCreate, RoomUpdate
from app.finance.service import create_room, void_room, update_room
from app.users.models import User, UserRoleEnum


@pytest.mark.asyncio
class TestRoomService:
    async def test_create_room(self, seeded_db: AsyncSession):
        result = await seeded_db.execute(
            select(User).where(User.role == UserRoleEnum.SUPERADMIN)
        )
        actor = result.scalars().first()

        doctor = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(
                role=StaffRoleEnum.DOCTOR,
                first_name="Dr.",
                last_name="Room",
                specialty="General",
            ),
        )

        room = await create_room(
            seeded_db,
            actor=actor,
            data=RoomCreate(
                amount=Decimal("200000"),
                doctor_percent=Decimal("20"),
                doctor_id=doctor.id,
            ),
        )

        assert room.id is not None
        assert room.amount == Decimal("200000")
        assert room.doctor_percent == Decimal("20")
        assert room.is_voided is False

    async def test_update_room(self, seeded_db: AsyncSession):
        result = await seeded_db.execute(
            select(User).where(User.role == UserRoleEnum.SUPERADMIN)
        )
        actor = result.scalars().first()

        doctor = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(
                role=StaffRoleEnum.DOCTOR,
                first_name="Dr.",
                last_name="RoomUpdate",
                specialty="General",
            ),
        )

        room = await create_room(
            seeded_db,
            actor=actor,
            data=RoomCreate(
                amount=Decimal("300000"),
                doctor_percent=Decimal("15"),
                doctor_id=doctor.id,
            ),
        )

        updated = await update_room(
            seeded_db,
            actor=actor,
            room=room,
            data=RoomUpdate(amount=Decimal("350000")),
        )

        assert updated.amount == Decimal("350000")

    async def test_void_room(self, seeded_db: AsyncSession):
        result = await seeded_db.execute(
            select(User).where(User.role == UserRoleEnum.SUPERADMIN)
        )
        actor = result.scalars().first()

        doctor = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(
                role=StaffRoleEnum.DOCTOR,
                first_name="Dr.",
                last_name="RoomVoid",
                specialty="General",
            ),
        )

        room = await create_room(
            seeded_db,
            actor=actor,
            data=RoomCreate(
                amount=Decimal("400000"),
                doctor_percent=Decimal("18"),
                doctor_id=doctor.id,
            ),
        )

        voided = await void_room(
            seeded_db,
            actor=actor,
            room=room,
        )

        assert voided.is_voided is True
