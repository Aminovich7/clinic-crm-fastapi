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
