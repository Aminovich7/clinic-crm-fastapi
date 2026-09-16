import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.staff.models import StaffRoleEnum
from app.staff.schemas import StaffCreate
from app.staff.service import create_staff, list_staff_options
from app.users.models import User, UserRoleEnum
from app.users.schemas import AssistantCreate
from app.users.service import create_assistant


@pytest.mark.asyncio
class TestStaffOptions:
    async def test_assistant_forced_to_doctor_role(self, seeded_db: AsyncSession):
        result = await seeded_db.execute(select(User).where(User.role == UserRoleEnum.SUPERADMIN))
        superadmin = result.scalars().first()

        await create_staff(
            seeded_db,
            actor=superadmin,
            data=StaffCreate(role=StaffRoleEnum.DOCTOR, first_name="D", last_name="One", specialty="X"),
        )
        await create_staff(
            seeded_db,
            actor=superadmin,
            data=StaffCreate(role=StaffRoleEnum.NURSE, first_name="N", last_name="Two"),
        )

        assistant = await create_assistant(
            seeded_db,
            superadmin,
            AssistantCreate(username="assistant-x", full_name="Assistant X", password="Pass$1234"),
        )

        # Even asking for NURSE explicitly, an assistant only ever gets doctors.
        options = await list_staff_options(seeded_db, role=StaffRoleEnum.NURSE, actor=assistant)

        assert len(options) == 1
        assert options[0].role == StaffRoleEnum.DOCTOR

    async def test_manager_can_request_any_role(self, seeded_db: AsyncSession):
        result = await seeded_db.execute(select(User).where(User.role == UserRoleEnum.SUPERADMIN))
        superadmin = result.scalars().first()

        await create_staff(
            seeded_db,
            actor=superadmin,
            data=StaffCreate(role=StaffRoleEnum.NURSE, first_name="N", last_name="Two"),
        )

        options = await list_staff_options(seeded_db, role=StaffRoleEnum.NURSE, actor=superadmin)
        assert len(options) == 1
        assert options[0].role == StaffRoleEnum.NURSE
