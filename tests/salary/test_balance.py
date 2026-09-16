from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.salary.models import SalaryPaymentType
from app.salary.schemas import SalaryPaymentCreate
from app.salary.service import build_staff_balance, compute_paid_amount, create_salary_payment
from app.staff.models import StaffRoleEnum
from app.staff.schemas import StaffCreate
from app.staff.service import create_staff
from app.users.models import User, UserRoleEnum


async def _get_superadmin(db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.role == UserRoleEnum.SUPERADMIN))
    return result.scalars().first()


@pytest.mark.asyncio
class TestPaymentOverlap:
    async def test_payment_fully_inside_range_counted(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)
        staff = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(role=StaffRoleEnum.OTHER, first_name="O", last_name="One"),
        )
        await create_salary_payment(
            seeded_db,
            actor=actor,
            data=SalaryPaymentCreate(
                staff_id=staff.id,
                period_start=date(2026, 3, 10),
                period_end=date(2026, 3, 20),
                payment_type=SalaryPaymentType.FULL,
                amount=100000,
            ),
        )

        paid = await compute_paid_amount(
            seeded_db, staff_id=staff.id, date_from=date(2026, 3, 1), date_to=date(2026, 3, 31)
        )
        assert paid == Decimal("100000")

    async def test_payment_fully_outside_range_excluded(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)
        staff = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(role=StaffRoleEnum.OTHER, first_name="O", last_name="Two"),
        )
        await create_salary_payment(
            seeded_db,
            actor=actor,
            data=SalaryPaymentCreate(
                staff_id=staff.id,
                period_start=date(2026, 1, 1),
                period_end=date(2026, 1, 31),
                payment_type=SalaryPaymentType.FULL,
                amount=100000,
            ),
        )

        paid = await compute_paid_amount(
            seeded_db, staff_id=staff.id, date_from=date(2026, 3, 1), date_to=date(2026, 3, 31)
        )
        assert paid == Decimal("0")

    async def test_payment_spanning_two_months_counted_in_full_for_both(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)
        staff = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(role=StaffRoleEnum.OTHER, first_name="O", last_name="Three"),
        )
        await create_salary_payment(
            seeded_db,
            actor=actor,
            data=SalaryPaymentCreate(
                staff_id=staff.id,
                period_start=date(2026, 1, 25),
                period_end=date(2026, 2, 5),
                payment_type=SalaryPaymentType.FULL,
                amount=100000,
            ),
        )

        jan_paid = await compute_paid_amount(
            seeded_db, staff_id=staff.id, date_from=date(2026, 1, 1), date_to=date(2026, 1, 31)
        )
        feb_paid = await compute_paid_amount(
            seeded_db, staff_id=staff.id, date_from=date(2026, 2, 1), date_to=date(2026, 2, 28)
        )
        # Full amount counted in BOTH months — intentional, not prorated.
        assert jan_paid == Decimal("100000")
        assert feb_paid == Decimal("100000")

    async def test_build_staff_balance_default_current_month(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)
        staff = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(role=StaffRoleEnum.OTHER, first_name="O", last_name="Four"),
        )

        summaries = await build_staff_balance(
            seeded_db, date_from=None, date_to=None, staff_id=staff.id
        )
        assert len(summaries) == 1
        assert summaries[0].staff_id == staff.id
