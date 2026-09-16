from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.salary.models import SalaryPaymentType
from app.salary.schemas import SalaryPaymentCreate, SalaryPaymentUpdate
from app.salary.service import create_salary_payment, update_salary_payment, void_salary_payment
from app.staff.models import StaffRoleEnum
from app.staff.schemas import StaffCreate
from app.staff.service import create_staff
from app.users.models import User, UserRoleEnum


async def _get_superadmin(db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.role == UserRoleEnum.SUPERADMIN))
    return result.scalars().first()


@pytest.mark.asyncio
class TestSalaryPayments:
    async def test_create_and_void(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)
        staff = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(role=StaffRoleEnum.OTHER, first_name="O", last_name="One"),
        )

        payment = await create_salary_payment(
            seeded_db,
            actor=actor,
            data=SalaryPaymentCreate(
                staff_id=staff.id,
                period_start=date(2026, 3, 1),
                period_end=date(2026, 3, 31),
                payment_type=SalaryPaymentType.AVANS,
                amount=500000,
            ),
        )
        assert payment.amount == 500000
        assert payment.is_voided is False

        voided = await void_salary_payment(seeded_db, actor=actor, salary_payment=payment)
        assert voided.is_voided is True

        with pytest.raises(Exception):
            await void_salary_payment(seeded_db, actor=actor, salary_payment=voided)

    def test_period_start_after_end_rejected(self):
        with pytest.raises(ValueError):
            SalaryPaymentCreate(
                staff_id=1,
                period_start=date(2026, 3, 31),
                period_end=date(2026, 3, 1),
                payment_type=SalaryPaymentType.FULL,
                amount=1000,
            )

    async def test_update_rejects_invalid_period(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)
        staff = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(role=StaffRoleEnum.OTHER, first_name="O", last_name="Two"),
        )

        payment = await create_salary_payment(
            seeded_db,
            actor=actor,
            data=SalaryPaymentCreate(
                staff_id=staff.id,
                period_start=date(2026, 3, 1),
                period_end=date(2026, 3, 31),
                payment_type=SalaryPaymentType.FULL,
                amount=1000000,
            ),
        )

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await update_salary_payment(
                seeded_db,
                actor=actor,
                salary_payment=payment,
                data=SalaryPaymentUpdate(period_start=date(2026, 4, 1)),
            )
        assert exc_info.value.status_code == 422
