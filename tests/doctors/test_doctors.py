import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.doctors.schemas import DoctorCreate
from app.doctors.service import create_doctor, list_doctor_options
from app.users.models import User, UserRoleEnum


@pytest.mark.asyncio
class TestDoctorService:
    async def test_create_doctor(self, seeded_db: AsyncSession):
        result = await seeded_db.execute(
            select(User).where(User.role == UserRoleEnum.SUPERADMIN)
        )
        actor = result.scalars().first()

        doctor = await create_doctor(
            seeded_db,
            actor=actor,
            data=DoctorCreate(
                first_name="Ali",
                last_name="Karimov",
                specialty="Cardio",
            ),
        )

        assert doctor.id is not None
        assert doctor.first_name == "Ali"
        assert doctor.last_name == "Karimov"
        assert doctor.specialty == "Cardio"

    async def test_list_doctor_options(self, seeded_db: AsyncSession):
        # Get superadmin
        result = await seeded_db.execute(
            select(User).where(User.username == "CHANGE_ME_ADMIN_USERNAME")
        )
        actor = result.scalars().first()

        # Create a doctor
        await create_doctor(
            seeded_db,
            actor=actor,
            data=DoctorCreate(
                first_name="Zarina",
                last_name="Uzbekova",
                specialty="Pediatrics",
            ),
        )

        options = await list_doctor_options(seeded_db)

        assert len(options) == 1
        # list_doctor_options returns Doctor objects
        assert f"{options[0].last_name} {options[0].first_name}" == "Uzbekova Zarina"
