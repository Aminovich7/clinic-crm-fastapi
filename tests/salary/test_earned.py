from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.duty.schemas import DutyEntryCreate
from app.duty.service import create_duty_entry
from app.finance.models import ConsultationType
from app.finance.schemas import ConsultationCreate
from app.finance.service import create_consultation
from app.salary.service import compute_earned_amount
from app.staff.models import StaffRoleEnum
from app.staff.schemas import StaffCreate
from app.staff.service import create_staff
from app.users.models import User, UserRoleEnum

CLINIC_TZ = ZoneInfo("Asia/Tashkent")


async def _get_superadmin(db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.role == UserRoleEnum.SUPERADMIN))
    return result.scalars().first()


@pytest.mark.asyncio
class TestComputeEarnedAmount:
    async def test_doctor_earns_receipts_plus_duty(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)

        doctor = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(role=StaffRoleEnum.DOCTOR, first_name="D", last_name="One", specialty="X"),
        )

        await create_consultation(
            seeded_db,
            actor=actor,
            data=ConsultationCreate(
                type=ConsultationType.KORIK,
                receipt_number=1,
                date=datetime(2026, 3, 10, tzinfo=CLINIC_TZ),
                amount=Decimal("100000"),
                doctor_percent=Decimal("50"),
                minus_beshming=Decimal("0"),
                doctor_id=doctor.id,
            ),
        )

        await create_duty_entry(
            seeded_db,
            actor=actor,
            data=DutyEntryCreate(staff_id=doctor.id, date=date(2026, 3, 15), amount=20000),
        )

        earned = await compute_earned_amount(
            seeded_db, staff=doctor, date_from=date(2026, 3, 1), date_to=date(2026, 3, 31)
        )
        # doctor_share = 100000 * 50% = 50000, plus duty 20000 = 70000
        assert earned == Decimal("70000")

    async def test_nurse_earns_prorated_salary_plus_duty(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)

        nurse = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(
                role=StaffRoleEnum.NURSE, first_name="N", last_name="Two", fixed_salary=Decimal("2800000")
            ),
        )

        await create_duty_entry(
            seeded_db,
            actor=actor,
            data=DutyEntryCreate(staff_id=nurse.id, date=date(2026, 2, 15), amount=15000),
        )

        earned = await compute_earned_amount(
            seeded_db, staff=nurse, date_from=date(2026, 2, 1), date_to=date(2026, 2, 28)
        )
        # Full February (28 days) of 2,800,000 == 2,800,000 exactly, plus duty 15000
        assert earned == Decimal("2815000")


@pytest.mark.asyncio
class TestHireDateClamping:
    """Fixed-salary staff must not accrue anything before their hire date.

    Regression coverage for a real reported case: a staff member hired
    2026-09-17 on a 50,000,000 fixed salary showed a full 50,000,000 as owed
    when the Oyliklar balance was filtered to the *previous* month, because
    compute_earned_amount() prorated across the requested range without ever
    consulting hire_date.
    """

    async def _hire(self, db: AsyncSession, *, hire_date: date, salary: int):
        actor = await _get_superadmin(db)
        return await create_staff(
            db,
            actor=actor,
            data=StaffCreate(
                role=StaffRoleEnum.OTHER,
                first_name="Mehroj",
                last_name="Hamraev",
                fixed_salary=Decimal(salary),
                hire_date=hire_date,
            ),
        )

    async def test_month_entirely_before_hire_earns_nothing(self, seeded_db: AsyncSession):
        staff = await self._hire(seeded_db, hire_date=date(2026, 9, 17), salary=50_000_000)

        earned = await compute_earned_amount(
            seeded_db,
            staff=staff,
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 31),
        )

        assert earned == Decimal("0")

    async def test_hire_month_is_prorated_from_hire_date(self, seeded_db: AsyncSession):
        staff = await self._hire(seeded_db, hire_date=date(2026, 9, 17), salary=50_000_000)

        earned = await compute_earned_amount(
            seeded_db,
            staff=staff,
            date_from=date(2026, 9, 1),
            date_to=date(2026, 9, 30),
        )

        # 17-30 September is 14 of the month's 30 days:
        # 50,000,000 / 30 * 14 = 23,333,333.33 -> 23,333,333
        assert earned == Decimal("23333333")

    async def test_month_fully_after_hire_is_unaffected(self, seeded_db: AsyncSession):
        staff = await self._hire(seeded_db, hire_date=date(2026, 9, 17), salary=50_000_000)

        earned = await compute_earned_amount(
            seeded_db,
            staff=staff,
            date_from=date(2026, 10, 1),
            date_to=date(2026, 10, 31),
        )

        assert earned == Decimal("50000000")

    async def test_range_starting_before_hire_counts_only_worked_days(
        self, seeded_db: AsyncSession
    ):
        """A range spanning the hire date is clamped, not zeroed."""
        staff = await self._hire(seeded_db, hire_date=date(2026, 9, 17), salary=50_000_000)

        earned = await compute_earned_amount(
            seeded_db,
            staff=staff,
            date_from=date(2026, 8, 1),
            date_to=date(2026, 9, 30),
        )

        # August contributes nothing; only 17-30 September counts.
        assert earned == Decimal("23333333")

    async def test_staff_without_hire_date_is_not_clamped(self, seeded_db: AsyncSession):
        """No hire_date means "unknown", never "hired on the day I was typed in".

        created_at is a data-entry timestamp. Falling back to it would quietly
        reduce the pay owed to long-standing staff whose CRM record happens to
        be recent, so an absent hire_date leaves earnings un-clamped.
        """
        actor = await _get_superadmin(seeded_db)
        staff = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(
                role=StaffRoleEnum.OTHER,
                first_name="No",
                last_name="Hiredate",
                fixed_salary=Decimal("2800000"),
            ),
        )
        assert staff.hire_date is None

        earned = await compute_earned_amount(
            seeded_db,
            staff=staff,
            date_from=date(2026, 2, 1),
            date_to=date(2026, 2, 28),
        )

        assert earned == Decimal("2800000")
