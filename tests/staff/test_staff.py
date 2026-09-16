import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.staff.models import StaffRoleEnum, StaffStatusEnum
from app.staff.schemas import StaffCreate, StaffUpdate
from app.staff.service import (
    activate_staff,
    create_staff,
    deactivate_staff,
    delete_staff,
    get_staff_or_404,
    list_staff,
    update_staff,
)
from app.users.models import User, UserRoleEnum


async def _get_superadmin(db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.role == UserRoleEnum.SUPERADMIN))
    return result.scalars().first()


@pytest.mark.asyncio
class TestStaffService:
    async def test_create_doctor(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)

        staff = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(
                role=StaffRoleEnum.DOCTOR,
                first_name="Ali",
                last_name="Karimov",
                specialty="Cardio",
            ),
        )

        assert staff.id is not None
        assert staff.role == StaffRoleEnum.DOCTOR
        assert staff.fixed_salary is None
        assert staff.status == StaffStatusEnum.ACTIVE

    async def test_create_nurse_with_fixed_salary(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)

        staff = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(
                role=StaffRoleEnum.NURSE,
                first_name="Zarina",
                last_name="Uzbekova",
                fixed_salary=3_000_000,
            ),
        )

        assert staff.role == StaffRoleEnum.NURSE
        assert staff.fixed_salary == 3_000_000

    async def test_create_doctor_without_specialty_rejected(self, seeded_db: AsyncSession):
        with pytest.raises(ValueError):
            StaffCreate(role=StaffRoleEnum.DOCTOR, first_name="Ali", last_name="Karimov")

    async def test_create_doctor_with_fixed_salary_rejected(self, seeded_db: AsyncSession):
        with pytest.raises(ValueError):
            StaffCreate(
                role=StaffRoleEnum.DOCTOR,
                first_name="Ali",
                last_name="Karimov",
                specialty="Cardio",
                fixed_salary=1000,
            )

    async def test_update_doctor_add_fixed_salary_rejected(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)

        staff = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(
                role=StaffRoleEnum.DOCTOR,
                first_name="Ali",
                last_name="Karimov",
                specialty="Cardio",
            ),
        )

        with pytest.raises(HTTPException) as exc_info:
            await update_staff(
                seeded_db,
                actor=actor,
                staff=staff,
                data=StaffUpdate(fixed_salary=1000),
            )
        assert exc_info.value.status_code == 422

    async def test_activate_deactivate(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)

        staff = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(role=StaffRoleEnum.OTHER, first_name="Farrukh", last_name="Yusupov"),
        )

        deactivated = await deactivate_staff(seeded_db, actor=actor, staff=staff)
        assert deactivated.status == StaffStatusEnum.INACTIVE

        activated = await activate_staff(seeded_db, actor=actor, staff=staff)
        assert activated.status == StaffStatusEnum.ACTIVE

    async def test_delete_staff_without_history(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)

        staff = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(role=StaffRoleEnum.OTHER, first_name="Temp", last_name="Worker"),
        )
        staff_id = staff.id

        await delete_staff(seeded_db, actor=actor, staff=staff)

        with pytest.raises(HTTPException) as exc_info:
            await get_staff_or_404(seeded_db, staff_id)
        assert exc_info.value.status_code == 404

    async def test_delete_staff_with_history_blocked(self, seeded_db: AsyncSession):
        from app.duty.schemas import DutyEntryCreate
        from app.duty.service import create_duty_entry

        actor = await _get_superadmin(seeded_db)

        staff = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(role=StaffRoleEnum.OTHER, first_name="Has", last_name="History"),
        )

        await create_duty_entry(
            seeded_db,
            actor=actor,
            data=DutyEntryCreate(staff_id=staff.id, amount=10000),
        )

        with pytest.raises(HTTPException) as exc_info:
            await delete_staff(seeded_db, actor=actor, staff=staff)
        assert exc_info.value.status_code == 409

    async def test_list_staff_role_filter(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)

        await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(role=StaffRoleEnum.DOCTOR, first_name="D", last_name="One", specialty="X"),
        )
        await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(role=StaffRoleEnum.NURSE, first_name="N", last_name="Two"),
        )

        items, total = await list_staff(
            seeded_db, role=StaffRoleEnum.DOCTOR, status_=None, search=None, page=1, page_size=20
        )
        assert total == 1
        assert items[0].role == StaffRoleEnum.DOCTOR
