import pytest
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.doctors.schemas import DoctorCreate
from app.doctors.service import create_doctor
from app.finance.schemas import SurgeryCreate, SurgeryUpdate
from app.finance.service import create_surgery, void_surgery, update_surgery
from app.users.models import User, UserRoleEnum


@pytest.mark.asyncio
class TestSurgeryService:
    async def test_create_surgery(self, seeded_db: AsyncSession):
        result = await seeded_db.execute(
            select(User).where(User.role == UserRoleEnum.SUPERADMIN)
        )
        actor = result.scalars().first()

        doctor = await create_doctor(
            seeded_db,
            actor=actor,
            data=DoctorCreate(
                first_name="Dr.",
                last_name="Surgery",
                specialty="Surgeon",
            ),
        )

        surgery = await create_surgery(
            seeded_db,
            actor=actor,
            data=SurgeryCreate(
                receipt_number=200,
                amount=Decimal("500000"),
                surgery_expense=Decimal("50000"),
                doctor_percent=Decimal("40"),
                doctor_id=doctor.id,
            ),
        )

        assert surgery.id is not None
        assert surgery.receipt_number == 200
        assert surgery.amount == Decimal("500000")
        assert surgery.surgery_expense == Decimal("50000")
        assert surgery.is_voided is False

    async def test_surgery_expense_exceeds_amount(self, seeded_db: AsyncSession):
        from fastapi import HTTPException

        result = await seeded_db.execute(
            select(User).where(User.role == UserRoleEnum.SUPERADMIN)
        )
        actor = result.scalars().first()

        doctor = await create_doctor(
            seeded_db,
            actor=actor,
            data=DoctorCreate(
                first_name="Dr.",
                last_name="SurgeryExpense",
                specialty="Surgeon",
            ),
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_surgery(
                seeded_db,
                actor=actor,
                data=SurgeryCreate(
                    receipt_number=201,
                    amount=Decimal("1000"),
                    surgery_expense=Decimal("5000"),
                    doctor_percent=Decimal("40"),
                    doctor_id=doctor.id,
                ),
            )

        assert exc_info.value.status_code == 422

    async def test_update_surgery(self, seeded_db: AsyncSession):
        result = await seeded_db.execute(
            select(User).where(User.role == UserRoleEnum.SUPERADMIN)
        )
        actor = result.scalars().first()

        doctor = await create_doctor(
            seeded_db,
            actor=actor,
            data=DoctorCreate(
                first_name="Dr.",
                last_name="SurgeryUpdate",
                specialty="Surgeon",
            ),
        )

        surgery = await create_surgery(
            seeded_db,
            actor=actor,
            data=SurgeryCreate(
                receipt_number=202,
                amount=Decimal("500000"),
                surgery_expense=Decimal("50000"),
                doctor_percent=Decimal("40"),
                doctor_id=doctor.id,
            ),
        )

        updated = await update_surgery(
            seeded_db,
            actor=actor,
            surgery=surgery,
            data=SurgeryUpdate(amount=Decimal("600000")),
        )

        assert updated.amount == Decimal("600000")

    async def test_void_surgery(self, seeded_db: AsyncSession):
        result = await seeded_db.execute(
            select(User).where(User.role == UserRoleEnum.SUPERADMIN)
        )
        actor = result.scalars().first()

        doctor = await create_doctor(
            seeded_db,
            actor=actor,
            data=DoctorCreate(
                first_name="Dr.",
                last_name="SurgeryVoid",
                specialty="Surgeon",
            ),
        )

        surgery = await create_surgery(
            seeded_db,
            actor=actor,
            data=SurgeryCreate(
                receipt_number=203,
                amount=Decimal("500000"),
                surgery_expense=Decimal("50000"),
                doctor_percent=Decimal("40"),
                doctor_id=doctor.id,
            ),
        )

        voided = await void_surgery(
            seeded_db,
            actor=actor,
            surgery=surgery,
        )

        assert voided.is_voided is True
