import pytest
from datetime import date
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.duty.schemas import DutyEntryCreate, DutyEntryUpdate
from app.duty.service import create_duty_entry, list_duty_entries, void_duty_entry
from app.staff.models import StaffRoleEnum
from app.staff.schemas import StaffCreate
from app.staff.service import create_staff
from app.users.models import User, UserRoleEnum


async def _get_superadmin(db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.role == UserRoleEnum.SUPERADMIN))
    return result.scalars().first()


@pytest.mark.asyncio
class TestDutyEntries:
    async def test_create_and_list(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)
        staff = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(role=StaffRoleEnum.NURSE, first_name="N", last_name="One"),
        )

        entry = await create_duty_entry(
            seeded_db,
            actor=actor,
            data=DutyEntryCreate(staff_id=staff.id, date=date(2026, 3, 5), amount=50000),
        )
        assert entry.amount == 50000

        items, total = await list_duty_entries(
            seeded_db, staff_id=staff.id, date_from=None, date_to=None, page=1, page_size=20
        )
        assert total == 1
        assert items[0].id == entry.id

    async def test_multiple_entries_same_day_allowed(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)
        staff = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(role=StaffRoleEnum.OTHER, first_name="O", last_name="Two"),
        )

        await create_duty_entry(
            seeded_db,
            actor=actor,
            data=DutyEntryCreate(staff_id=staff.id, date=date(2026, 3, 5), amount=10000),
        )
        await create_duty_entry(
            seeded_db,
            actor=actor,
            data=DutyEntryCreate(staff_id=staff.id, date=date(2026, 3, 5), amount=20000),
        )

        items, total = await list_duty_entries(
            seeded_db, staff_id=staff.id, date_from=None, date_to=None, page=1, page_size=20
        )
        assert total == 2

    async def test_void_twice_conflict(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)
        staff = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(role=StaffRoleEnum.OTHER, first_name="O", last_name="Three"),
        )
        entry = await create_duty_entry(
            seeded_db,
            actor=actor,
            data=DutyEntryCreate(staff_id=staff.id, amount=10000),
        )

        await void_duty_entry(seeded_db, actor=actor, duty_entry=entry)

        with pytest.raises(HTTPException) as exc_info:
            await void_duty_entry(seeded_db, actor=actor, duty_entry=entry)
        assert exc_info.value.status_code == 409

    async def test_voided_entries_excluded_from_list(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)
        staff = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(role=StaffRoleEnum.OTHER, first_name="O", last_name="Four"),
        )
        entry = await create_duty_entry(
            seeded_db,
            actor=actor,
            data=DutyEntryCreate(staff_id=staff.id, amount=10000),
        )
        await void_duty_entry(seeded_db, actor=actor, duty_entry=entry)

        items, total = await list_duty_entries(
            seeded_db, staff_id=staff.id, date_from=None, date_to=None, page=1, page_size=20
        )
        assert total == 0
