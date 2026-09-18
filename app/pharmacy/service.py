from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.calculations import money
from app.finance.reports import get_business_datetime_range
from app.pharmacy.models import PharmacyEntry
from app.pharmacy.schemas import PharmacyBalance, PharmacyEntryCreate, PharmacyEntryUpdate
from app.users.models import User

CLINIC_TZ = ZoneInfo("Asia/Tashkent")
ZERO = Decimal("0")

def _resolve_create_date(value: datetime | None) -> datetime:
    return value if value is not None else datetime.now(CLINIC_TZ)

async def create_pharmacy_entry(
    db: AsyncSession,
    *,
    actor: User,
    data: PharmacyEntryCreate,
) -> PharmacyEntry:
    record = PharmacyEntry(
        date=_resolve_create_date(data.date),
        medicine_cost=data.medicine_cost,
        amount_paid=data.amount_paid,
        comment=data.comment.strip() if data.comment else None,
        created_by_id=actor.id,
    )

    db.add(record)
    await db.flush()

    await db.commit()
    await db.refresh(record)
    return record

async def get_pharmacy_entry_or_404(db: AsyncSession, pharmacy_entry_id: int) -> PharmacyEntry:
    record = await db.get(PharmacyEntry, pharmacy_entry_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pharmacy entry not found")
    return record

async def list_pharmacy_entries(
    db: AsyncSession,
    *,
    date_from: date | None,
    date_to: date | None,
    page: int,
    page_size: int,
) -> tuple[list[PharmacyEntry], int]:
    stmt = select(PharmacyEntry).where(PharmacyEntry.is_voided.is_(False))

    start, end = get_business_datetime_range(date_from, date_to)
    if start:
        stmt = stmt.where(PharmacyEntry.date >= start)
    if end:
        stmt = stmt.where(PharmacyEntry.date < end)

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(PharmacyEntry.date.desc(), PharmacyEntry.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all()), total

async def update_pharmacy_entry(
    db: AsyncSession,
    *,
    actor: User,
    pharmacy_entry: PharmacyEntry,
    data: PharmacyEntryUpdate,
) -> PharmacyEntry:
    changes = data.model_dump(exclude_unset=True)

    new_cost = changes.get("medicine_cost", pharmacy_entry.medicine_cost)
    new_paid = changes.get("amount_paid", pharmacy_entry.amount_paid)
    if new_cost is None and new_paid is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "At least one of medicine_cost or amount_paid is required",
        )

    for field, value in changes.items():
        if field == "comment" and isinstance(value, str):
            value = value.strip() or None
        setattr(pharmacy_entry, field, value)

    await db.commit()
    await db.refresh(pharmacy_entry)
    return pharmacy_entry

async def void_pharmacy_entry(
    db: AsyncSession, *, actor: User, pharmacy_entry: PharmacyEntry
) -> PharmacyEntry:
    if pharmacy_entry.is_voided:
        raise HTTPException(status.HTTP_409_CONFLICT, "Pharmacy entry is already voided")

    pharmacy_entry.is_voided = True
    pharmacy_entry.voided_at = datetime.now(ZoneInfo("UTC"))
    pharmacy_entry.voided_by_id = actor.id

    await db.commit()
    await db.refresh(pharmacy_entry)
    return pharmacy_entry

async def build_pharmacy_balance(
    db: AsyncSession,
    *,
    date_from: date | None,
    date_to: date | None,
) -> PharmacyBalance:
    stmt = select(
        func.coalesce(func.sum(PharmacyEntry.amount_paid), ZERO),
        func.coalesce(func.sum(PharmacyEntry.medicine_cost), ZERO),
    ).where(PharmacyEntry.is_voided.is_(False))

    start, end = get_business_datetime_range(date_from, date_to)
    if start:
        stmt = stmt.where(PharmacyEntry.date >= start)
    if end:
        stmt = stmt.where(PharmacyEntry.date < end)

    total_paid, total_cost = (await db.execute(stmt)).one()

    return PharmacyBalance(
        total_paid=money(total_paid),
        total_medicine_cost=money(total_cost),
        balance=money(total_paid - total_cost),
    )
