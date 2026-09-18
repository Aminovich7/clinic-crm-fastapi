from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.voidable import forbid_edit_if_voided
from app.duty.models import DutyEntry
from app.finance.calculations import consultation_totals, money, room_totals, surgery_totals
from app.finance.models import Consultation, Room, Surgery
from app.finance.reports import get_business_datetime_range
from app.salary.calculations import prorate_fixed_salary
from app.salary.models import SalaryPayment
from app.salary.schemas import (
    SalaryPaymentCreate,
    SalaryPaymentUpdate,
    StaffEarnedPaidSummary,
    StaffLifetimeSummary,
)
from app.staff.models import Staff, StaffRoleEnum, StaffStatusEnum
from app.users.models import User

CLINIC_TZ = ZoneInfo("Asia/Tashkent")
ZERO = Decimal("0")

# (model + the columns to select, per-record totals function, argument
# extractor). Declared once so _sum_doctor_share and its batched twin can
# never read different columns or apply different arithmetic.
_DOCTOR_SHARE_SOURCES = (
    (
        (Consultation, Consultation.amount, Consultation.minus_beshming, Consultation.doctor_percent),
        consultation_totals,
        lambda r: (r.minus_beshming, r.doctor_percent),
    ),
    (
        (Surgery, Surgery.amount, Surgery.surgery_expense, Surgery.doctor_percent),
        surgery_totals,
        lambda r: (r.surgery_expense, r.doctor_percent),
    ),
    (
        (Room, Room.amount, Room.doctor_percent),
        room_totals,
        lambda r: (r.doctor_percent,),
    ),
)

def _resolve_create_datetime(value: datetime | None) -> datetime:
    return value if value is not None else datetime.now(CLINIC_TZ)

def _current_month_range() -> tuple[date, date]:
    from calendar import monthrange

    today = datetime.now(CLINIC_TZ).date()
    last_day = monthrange(today.year, today.month)[1]
    return today.replace(day=1), today.replace(day=last_day)

async def _sum_doctor_share(
    db: AsyncSession,
    *,
    staff_id: int,
    date_from: date | None,
    date_to: date | None,
) -> Decimal:
    total = ZERO
    start, end = get_business_datetime_range(date_from, date_to)

    for columns, totals_fn, extra_args in _DOCTOR_SHARE_SOURCES:
        model = columns[0]
        stmt = select(*columns[1:]).where(
            model.is_voided.is_(False), model.doctor_id == staff_id
        )
        if start:
            stmt = stmt.where(model.date >= start)
        if end:
            stmt = stmt.where(model.date < end)

        for record in (await db.execute(stmt)).all():
            totals = totals_fn(record.amount, *extra_args(record))
            total += totals["doctor_share"]

    return total

async def _sum_duty_entries(
    db: AsyncSession,
    *,
    staff_id: int,
    date_from: date | None,
    date_to: date | None,
) -> Decimal:
    stmt = select(func.coalesce(func.sum(DutyEntry.amount), ZERO)).where(
        DutyEntry.staff_id == staff_id,
        DutyEntry.is_voided.is_(False),
    )
    if date_from is not None:
        stmt = stmt.where(DutyEntry.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(DutyEntry.date <= date_to)

    return (await db.execute(stmt)).scalar_one()

def _prorated_fixed_salary(
    staff: Staff, *, date_from: date | None, date_to: date | None
) -> Decimal:
    """Fixed-salary base for one nurse/other staff member over a range.

    Nobody accrues salary before they were hired. Without this clamp a
    query for any month preceding the hire date returned a *full*
    month's pay — e.g. someone hired 2026-09-17 showed the whole
    fixed_salary as owed for August. Clamping the lower bound also
    prorates the hire month itself, so a mid-month hire is paid only
    for the days actually worked.

    Deliberately keyed on hire_date alone, with NO created_at fallback:
    created_at is when the record was typed into the CRM, which says
    nothing about when the person started working. Falling back to it
    would quietly *reduce* the pay owed to long-standing staff whose
    records were entered recently. Staff with no hire_date therefore
    keep the un-clamped behaviour until one is filled in.
    (build_staff_lifetime_summary does use the created_at fallback, but
    only as an explicitly documented approximation for a figure nobody
    pays out from.)

    Shared by compute_earned_amount and build_staff_balance so the two can
    never disagree about what someone is owed.
    """
    if date_from is None or date_to is None:
        raise ValueError("date_from and date_to are required to prorate a fixed salary")

    if staff.hire_date is not None and staff.hire_date > date_from:
        effective_from = staff.hire_date
    else:
        effective_from = date_from

    if effective_from > date_to:
        return ZERO

    return prorate_fixed_salary(staff.fixed_salary or ZERO, effective_from, date_to)

async def compute_earned_amount(
    db: AsyncSession,
    *,
    staff: Staff,
    date_from: date | None,
    date_to: date | None,
) -> Decimal:
    if staff.role == StaffRoleEnum.DOCTOR:
        base = await _sum_doctor_share(db, staff_id=staff.id, date_from=date_from, date_to=date_to)
    else:
        base = _prorated_fixed_salary(staff, date_from=date_from, date_to=date_to)

    duty_sum = await _sum_duty_entries(db, staff_id=staff.id, date_from=date_from, date_to=date_to)

    return money(base + duty_sum)

async def compute_paid_amount(
    db: AsyncSession,
    *,
    staff_id: int,
    date_from: date,
    date_to: date,
) -> Decimal:
    """Sum of non-voided SalaryPayments whose period overlaps the range.

    A payment's full amount counts on any overlap (not prorated) — see
    plan.md's Oyliklar section for why this is intentional.
    """
    stmt = select(func.coalesce(func.sum(SalaryPayment.amount), ZERO)).where(
        SalaryPayment.staff_id == staff_id,
        SalaryPayment.is_voided.is_(False),
        SalaryPayment.period_start <= date_to,
        SalaryPayment.period_end >= date_from,
    )
    return (await db.execute(stmt)).scalar_one()

async def create_salary_payment(
    db: AsyncSession,
    *,
    actor: User,
    data: SalaryPaymentCreate,
) -> SalaryPayment:
    from app.staff.service import get_staff_or_404

    await get_staff_or_404(db, data.staff_id)

    record = SalaryPayment(
        staff_id=data.staff_id,
        paid_at=_resolve_create_datetime(data.paid_at),
        period_start=data.period_start,
        period_end=data.period_end,
        payment_type=data.payment_type,
        amount=data.amount,
        created_by_id=actor.id,
    )

    db.add(record)
    await db.flush()

    await db.commit()
    await db.refresh(record)
    return record

async def get_salary_payment_or_404(db: AsyncSession, salary_payment_id: int) -> SalaryPayment:
    record = await db.get(SalaryPayment, salary_payment_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Salary payment not found")
    return record

async def list_salary_payments(
    db: AsyncSession,
    *,
    staff_id: int | None,
    date_from: date | None,
    date_to: date | None,
    page: int,
    page_size: int,
) -> tuple[list[SalaryPayment], int]:
    stmt = select(SalaryPayment).where(SalaryPayment.is_voided.is_(False))

    if staff_id is not None:
        stmt = stmt.where(SalaryPayment.staff_id == staff_id)

    start, end = get_business_datetime_range(date_from, date_to)
    if start:
        stmt = stmt.where(SalaryPayment.paid_at >= start)
    if end:
        stmt = stmt.where(SalaryPayment.paid_at < end)

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(SalaryPayment.paid_at.desc(), SalaryPayment.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all()), total

async def update_salary_payment(
    db: AsyncSession,
    *,
    actor: User,
    salary_payment: SalaryPayment,
    data: SalaryPaymentUpdate,
) -> SalaryPayment:
    forbid_edit_if_voided(salary_payment)
    changes = data.model_dump(exclude_unset=True)

    if "staff_id" in changes and changes["staff_id"] is not None:
        from app.staff.service import get_staff_or_404

        await get_staff_or_404(db, changes["staff_id"])

    new_start = changes.get("period_start", salary_payment.period_start)
    new_end = changes.get("period_end", salary_payment.period_end)
    if new_start > new_end:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "period_start cannot be after period_end",
        )

    for field, value in changes.items():
        setattr(salary_payment, field, value)

    await db.commit()
    await db.refresh(salary_payment)
    return salary_payment

async def void_salary_payment(
    db: AsyncSession, *, actor: User, salary_payment: SalaryPayment
) -> SalaryPayment:
    if salary_payment.is_voided:
        raise HTTPException(status.HTTP_409_CONFLICT, "Salary payment is already voided")

    salary_payment.is_voided = True
    salary_payment.voided_at = datetime.now(ZoneInfo("UTC"))
    salary_payment.voided_by_id = actor.id

    await db.commit()
    await db.refresh(salary_payment)
    return salary_payment

async def _sum_doctor_share_by_staff(
    db: AsyncSession,
    *,
    staff_ids: list[int],
    date_from: date | None,
    date_to: date | None,
) -> dict[int, Decimal]:
    """_sum_doctor_share for many doctors at once: 3 queries, not 3 per doctor.

    Identical arithmetic to _sum_doctor_share — the same totals_fn is applied
    to the same per-record values and the same per-record doctor_share is
    summed. Only the grouping moves from "one query per doctor" to "one query
    per table, bucketed in Python", so the figures cannot drift. Rounding is
    still per record before aggregation, which is this project's rule.
    """
    totals: dict[int, Decimal] = {staff_id: ZERO for staff_id in staff_ids}
    if not staff_ids:
        return totals

    start, end = get_business_datetime_range(date_from, date_to)

    for columns, totals_fn, extra_args in _DOCTOR_SHARE_SOURCES:
        model = columns[0]
        stmt = select(model.doctor_id, *columns[1:]).where(
            model.is_voided.is_(False), model.doctor_id.in_(staff_ids)
        )
        if start:
            stmt = stmt.where(model.date >= start)
        if end:
            stmt = stmt.where(model.date < end)

        for record in (await db.execute(stmt)).all():
            record_totals = totals_fn(record.amount, *extra_args(record))
            totals[record.doctor_id] += record_totals["doctor_share"]

    return totals

async def _sum_duty_entries_by_staff(
    db: AsyncSession,
    *,
    staff_ids: list[int],
    date_from: date | None,
    date_to: date | None,
) -> dict[int, Decimal]:
    """_sum_duty_entries for many staff at once, as one GROUP BY."""
    totals: dict[int, Decimal] = {staff_id: ZERO for staff_id in staff_ids}
    if not staff_ids:
        return totals

    stmt = (
        select(DutyEntry.staff_id, func.coalesce(func.sum(DutyEntry.amount), ZERO))
        .where(
            DutyEntry.staff_id.in_(staff_ids),
            DutyEntry.is_voided.is_(False),
        )
        .group_by(DutyEntry.staff_id)
    )
    if date_from is not None:
        stmt = stmt.where(DutyEntry.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(DutyEntry.date <= date_to)

    for entry_staff_id, total in (await db.execute(stmt)).all():
        totals[entry_staff_id] = total

    return totals

async def _sum_paid_by_staff(
    db: AsyncSession,
    *,
    staff_ids: list[int],
    date_from: date,
    date_to: date,
) -> dict[int, Decimal]:
    """compute_paid_amount for many staff at once, as one GROUP BY.

    Same period-overlap predicate, so a payment still counts in full on any
    overlap rather than being prorated.
    """
    totals: dict[int, Decimal] = {staff_id: ZERO for staff_id in staff_ids}
    if not staff_ids:
        return totals

    stmt = (
        select(
            SalaryPayment.staff_id,
            func.coalesce(func.sum(SalaryPayment.amount), ZERO),
        )
        .where(
            SalaryPayment.staff_id.in_(staff_ids),
            SalaryPayment.is_voided.is_(False),
            SalaryPayment.period_start <= date_to,
            SalaryPayment.period_end >= date_from,
        )
        .group_by(SalaryPayment.staff_id)
    )

    for payment_staff_id, total in (await db.execute(stmt)).all():
        totals[payment_staff_id] = total

    return totals

async def build_staff_balance(
    db: AsyncSession,
    *,
    date_from: date | None,
    date_to: date | None,
    staff_id: int | None,
) -> list[StaffEarnedPaidSummary]:
    if date_from is None and date_to is None:
        date_from, date_to = _current_month_range()
    elif date_from is None or date_to is None:
        raise ValueError("date_from and date_to must be given together")
    elif date_from > date_to:
        raise ValueError("date_from cannot be after date_to")

    stmt = select(Staff).where(Staff.status == StaffStatusEnum.ACTIVE)
    if staff_id is not None:
        stmt = stmt.where(Staff.id == staff_id)
    stmt = stmt.order_by(Staff.last_name.asc(), Staff.first_name.asc(), Staff.id.asc())

    staff_list = (await db.execute(stmt)).scalars().all()
    staff_ids = [staff.id for staff in staff_list]

    # Five queries total, whatever the headcount. This used to issue five
    # *per active staff member* (three record scans plus a duty sum inside
    # compute_earned_amount, plus compute_paid_amount), so the Oyliklar page
    # cost 5N round trips.
    doctor_ids = [
        staff.id for staff in staff_list if staff.role == StaffRoleEnum.DOCTOR
    ]
    doctor_shares = await _sum_doctor_share_by_staff(
        db, staff_ids=doctor_ids, date_from=date_from, date_to=date_to
    )
    duty_sums = await _sum_duty_entries_by_staff(
        db, staff_ids=staff_ids, date_from=date_from, date_to=date_to
    )
    paid_sums = await _sum_paid_by_staff(
        db, staff_ids=staff_ids, date_from=date_from, date_to=date_to
    )

    summaries: list[StaffEarnedPaidSummary] = []
    for staff in staff_list:
        if staff.role == StaffRoleEnum.DOCTOR:
            base = doctor_shares[staff.id]
        else:
            base = _prorated_fixed_salary(staff, date_from=date_from, date_to=date_to)

        earned = money(base + duty_sums[staff.id])
        paid = paid_sums[staff.id]

        summaries.append(
            StaffEarnedPaidSummary(
                staff_id=staff.id,
                name=f"{staff.last_name} {staff.first_name}",
                role=staff.role,
                earned=earned,
                paid=money(paid),
                remaining=money(earned - paid),
            )
        )

    return summaries

async def build_staff_lifetime_summary(db: AsyncSession, *, staff: Staff) -> StaffLifetimeSummary:
    if staff.role == StaffRoleEnum.DOCTOR:
        base = await _sum_doctor_share(db, staff_id=staff.id, date_from=None, date_to=None)
    else:
        start = staff.hire_date or staff.created_at.date()
        today = datetime.now(CLINIC_TZ).date()
        if start > today:
            base = ZERO
        else:
            base = prorate_fixed_salary(staff.fixed_salary or ZERO, start, today)

    duty_sum = await _sum_duty_entries(db, staff_id=staff.id, date_from=None, date_to=None)
    lifetime_earned = money(base + duty_sum)

    paid_stmt = select(func.coalesce(func.sum(SalaryPayment.amount), ZERO)).where(
        SalaryPayment.staff_id == staff.id,
        SalaryPayment.is_voided.is_(False),
    )
    lifetime_paid = (await db.execute(paid_stmt)).scalar_one()

    return StaffLifetimeSummary(
        staff_id=staff.id,
        name=f"{staff.last_name} {staff.first_name}",
        role=staff.role,
        lifetime_earned=lifetime_earned,
        lifetime_paid=money(lifetime_paid),
        lifetime_remaining=money(lifetime_earned - lifetime_paid),
    )

async def sum_total_paid(db: AsyncSession, *, date_from: date | None, date_to: date | None) -> Decimal:
    """Dashboard helper: how much was disbursed (by paid_at) in this window.

    Distinct from compute_paid_amount, which answers "how much of this
    period's wages is covered" via period-overlap. Never merge the two.
    """
    stmt = select(func.coalesce(func.sum(SalaryPayment.amount), ZERO)).where(
        SalaryPayment.is_voided.is_(False)
    )

    start, end = get_business_datetime_range(date_from, date_to)
    if start:
        stmt = stmt.where(SalaryPayment.paid_at >= start)
    if end:
        stmt = stmt.where(SalaryPayment.paid_at < end)

    return (await db.execute(stmt)).scalar_one()
