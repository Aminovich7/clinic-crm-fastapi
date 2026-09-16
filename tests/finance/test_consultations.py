import pytest
from datetime import datetime
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.staff.models import StaffRoleEnum
from app.staff.schemas import StaffCreate
from app.staff.service import create_staff
from app.finance.models import ConsultationType
from app.finance.schemas import ConsultationCreate, ConsultationUpdate
from app.finance.service import (
    create_consultation,
    get_consultation_or_404,
    list_consultations,
    update_consultation,
    void_consultation,
)
from app.users.models import User, UserRoleEnum


@pytest.mark.asyncio
class TestConsultationService:
    async def test_create_consultation(self, seeded_db: AsyncSession):
        # Get superadmin
        result = await seeded_db.execute(
            select(User).where(User.role == UserRoleEnum.SUPERADMIN)
        )
        actor = result.scalars().first()

        # Create a doctor
        doctor = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(
                role=StaffRoleEnum.DOCTOR,
                first_name="Dr.",
                last_name="Consultation",
                specialty="Test",
            ),
        )

        # Create a consultation
        consultation = await create_consultation(
            seeded_db,
            actor=actor,
            data=ConsultationCreate(
                type=ConsultationType.KORIK,
                receipt_number=100,
                amount=Decimal("100000"),
                doctor_percent=Decimal("50"),
                doctor_id=doctor.id,
            ),
        )

        assert consultation.id is not None
        assert consultation.type == ConsultationType.KORIK
        assert consultation.receipt_number == 100
        assert consultation.amount == Decimal("100000")
        assert consultation.minus_beshming == Decimal("5000")  # Default
        assert consultation.is_voided is False

    async def test_consultation_expense_exceeds_amount(self, seeded_db: AsyncSession):
        from fastapi import HTTPException

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
                last_name="ExpenseTest",
                specialty="Test",
            ),
        )

        # Try to create with expense > amount
        with pytest.raises(HTTPException) as exc_info:
            await create_consultation(
                seeded_db,
                actor=actor,
                data=ConsultationCreate(
                    type=ConsultationType.KORIK,
                    receipt_number=101,
                    amount=Decimal("1000"),
                    doctor_percent=Decimal("50"),
                    minus_beshming=Decimal("5000"),
                    doctor_id=doctor.id,
                ),
            )

        assert exc_info.value.status_code == 422
        assert "Expense cannot exceed amount" in exc_info.value.detail

    async def test_update_consultation(self, seeded_db: AsyncSession):
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
                last_name="UpdateTest",
                specialty="Test",
            ),
        )

        consultation = await create_consultation(
            seeded_db,
            actor=actor,
            data=ConsultationCreate(
                type=ConsultationType.KORIK,
                receipt_number=102,
                amount=Decimal("100000"),
                doctor_percent=Decimal("50"),
                doctor_id=doctor.id,
            ),
        )

        # Update the amount
        updated = await update_consultation(
            seeded_db,
            actor=actor,
            consultation=consultation,
            data=ConsultationUpdate(amount=Decimal("120000")),
        )

        assert updated.amount == Decimal("120000")

    async def test_void_consultation(self, seeded_db: AsyncSession):
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
                last_name="VoidTest",
                specialty="Test",
            ),
        )

        consultation = await create_consultation(
            seeded_db,
            actor=actor,
            data=ConsultationCreate(
                type=ConsultationType.KORIK,
                receipt_number=103,
                amount=Decimal("100000"),
                doctor_percent=Decimal("50"),
                doctor_id=doctor.id,
            ),
        )

        # Void it
        voided = await void_consultation(
            seeded_db,
            actor=actor,
            consultation=consultation,
        )

        assert voided.is_voided is True
        assert voided.voided_at is not None

    async def test_void_already_voided_returns_409(self, seeded_db: AsyncSession):
        from fastapi import HTTPException

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
                last_name="Void409Test",
                specialty="Test",
            ),
        )

        consultation = await create_consultation(
            seeded_db,
            actor=actor,
            data=ConsultationCreate(
                type=ConsultationType.KORIK,
                receipt_number=104,
                amount=Decimal("100000"),
                doctor_percent=Decimal("50"),
                doctor_id=doctor.id,
            ),
        )

        # Void it
        await void_consultation(
            seeded_db,
            actor=actor,
            consultation=consultation,
        )

        # Try to void again
        with pytest.raises(HTTPException) as exc_info:
            await void_consultation(
                seeded_db,
                actor=actor,
                consultation=consultation,
            )

        assert exc_info.value.status_code == 409
