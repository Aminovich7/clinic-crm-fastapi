"""build_staff_balance must agree with the per-staff functions it replaced.

The balance builder used to call compute_earned_amount and compute_paid_amount
once per active staff member — five queries each. It now issues five queries in
total and buckets the results in Python. That is only a safe change if the
figures are identical, so this test computes both ways over a populated
dataset and compares them staff by staff.

compute_earned_amount / compute_paid_amount remain the reference
implementation: they are still used by the lifetime summary and are covered by
the other tests in this package.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.duty.schemas import DutyEntryCreate
from app.duty.service import create_duty_entry
from app.finance.models import ConsultationType
from app.finance.schemas import ConsultationCreate, RoomCreate, SurgeryCreate
from app.finance.service import create_consultation, create_room, create_surgery
from app.salary.models import SalaryPaymentType
from app.salary.schemas import SalaryPaymentCreate
from app.salary.service import (
    build_staff_balance,
    compute_earned_amount,
    compute_paid_amount,
    create_salary_payment,
)
from app.staff.models import Staff, StaffRoleEnum
from app.staff.schemas import StaffCreate
from app.staff.service import create_staff
from app.users.models import User, UserRoleEnum

pytestmark = pytest.mark.asyncio

PERIOD_START = date(2026, 9, 1)
PERIOD_END = date(2026, 9, 30)


async def _actor(db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.role == UserRoleEnum.SUPERADMIN))
    return result.scalars().first()


async def _populate(db: AsyncSession) -> None:
    """Two doctors with a mixed record set, two fixed-salary staff."""
    actor = await _actor(db)

    doctors = []
    for index in range(2):
        doctors.append(
            await create_staff(
                db,
                actor=actor,
                data=StaffCreate(
                    role=StaffRoleEnum.DOCTOR,
                    first_name=f"Doctor{index}",
                    last_name="Batch",
                    specialty="General",
                ),
            )
        )

    nurse = await create_staff(
        db,
        actor=actor,
        data=StaffCreate(
            role=StaffRoleEnum.NURSE,
            first_name="Nurse",
            last_name="Batch",
            fixed_salary=Decimal("3000000"),
            hire_date=date(2026, 9, 10),  # mid-period hire, so proration matters
        ),
    )
    other = await create_staff(
        db,
        actor=actor,
        data=StaffCreate(
            role=StaffRoleEnum.OTHER,
            first_name="Other",
            last_name="Batch",
            fixed_salary=Decimal("1500000"),
        ),
    )

    when = datetime(2026, 9, 15, 12, 0)

    # Deliberately awkward percentages and amounts: these are where rounding
    # per record before aggregation differs from rounding once at the end.
    for index, doctor in enumerate(doctors):
        for receipt in range(3):
            await create_consultation(
                db,
                actor=actor,
                data=ConsultationCreate(
                    type=ConsultationType.KORIK if receipt % 2 else ConsultationType.QAYTAKORIK,
                    receipt_number=1000 + index * 10 + receipt,
                    date=when,
                    amount=Decimal("100001") + receipt,
                    doctor_percent=Decimal("33.33"),
                    minus_beshming=Decimal("5000"),
                    doctor_id=doctor.id,
                ),
            )
        await create_surgery(
            db,
            actor=actor,
            data=SurgeryCreate(
                receipt_number=2000 + index,
                date=when,
                amount=Decimal("777777"),
                surgery_expense=Decimal("12345"),
                doctor_percent=Decimal("41.67"),
                doctor_id=doctor.id,
            ),
        )
        await create_room(
            db,
            actor=actor,
            data=RoomCreate(
                receipt_number=3000 + index,
                date=when,
                amount=Decimal("55555"),
                doctor_percent=Decimal("7.77"),
                doctor_id=doctor.id,
            ),
        )

    # Duty entries for a doctor and a fixed-salary staff member alike.
    for staff in (doctors[0], nurse, other):
        await create_duty_entry(
            db,
            actor=actor,
            data=DutyEntryCreate(
                staff_id=staff.id, date=date(2026, 9, 12), amount=Decimal("123457")
            ),
        )

    for staff, amount, kind in (
        (doctors[0], Decimal("500000"), SalaryPaymentType.AVANS),
        (nurse, Decimal("1000000"), SalaryPaymentType.FULL),
    ):
        await create_salary_payment(
            db,
            actor=actor,
            data=SalaryPaymentCreate(
                staff_id=staff.id,
                paid_at=datetime(2026, 9, 20, 10, 0),
                period_start=PERIOD_START,
                period_end=PERIOD_END,
                payment_type=kind,
                amount=amount,
            ),
        )


class TestBatchedBalanceMatchesPerStaff:
    async def test_earned_paid_and_remaining_are_identical(self, seeded_db: AsyncSession):
        await _populate(seeded_db)

        summaries = await build_staff_balance(
            seeded_db, date_from=PERIOD_START, date_to=PERIOD_END, staff_id=None
        )
        assert summaries, "expected the populated staff to appear in the balance"

        for summary in summaries:
            staff = await seeded_db.get(Staff, summary.staff_id)

            expected_earned = await compute_earned_amount(
                seeded_db, staff=staff, date_from=PERIOD_START, date_to=PERIOD_END
            )
            expected_paid = await compute_paid_amount(
                seeded_db,
                staff_id=staff.id,
                date_from=PERIOD_START,
                date_to=PERIOD_END,
            )

            assert summary.earned == expected_earned, f"earned mismatch for {summary.name}"
            assert summary.paid == expected_paid, f"paid mismatch for {summary.name}"
            assert summary.remaining == expected_earned - expected_paid

    async def test_matches_when_filtered_to_one_staff_member(
        self, seeded_db: AsyncSession
    ):
        await _populate(seeded_db)

        everyone = await build_staff_balance(
            seeded_db, date_from=PERIOD_START, date_to=PERIOD_END, staff_id=None
        )

        for summary in everyone:
            filtered = await build_staff_balance(
                seeded_db,
                date_from=PERIOD_START,
                date_to=PERIOD_END,
                staff_id=summary.staff_id,
            )
            assert len(filtered) == 1
            assert filtered[0] == summary

    async def test_staff_with_no_records_report_zero_not_missing(
        self, seeded_db: AsyncSession
    ):
        """A doctor with nothing in the period must still appear, at zero.

        The batched path seeds its totals dict from the staff list rather than
        from the query results, so an absent GROUP BY row cannot drop someone
        off the page.
        """
        actor = await _actor(seeded_db)
        idle = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(
                role=StaffRoleEnum.DOCTOR,
                first_name="Idle",
                last_name="Doctor",
                specialty="None",
            ),
        )

        summaries = await build_staff_balance(
            seeded_db, date_from=PERIOD_START, date_to=PERIOD_END, staff_id=idle.id
        )

        assert len(summaries) == 1
        assert summaries[0].earned == Decimal("0")
        assert summaries[0].paid == Decimal("0")
        assert summaries[0].remaining == Decimal("0")
