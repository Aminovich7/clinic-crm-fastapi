from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_audit_event
from app.duty.models import DutyEntry
from app.duty.schemas import DutyEntryCreate, DutyEntryUpdate
from app.staff.service import get_staff_or_404
from app.users.models import User

CLINIC_TZ = ZoneInfo("Asia/Tashkent")


def _resolve_create_date(date_value: date | None) -> date:
    return date_value if date_value is not None else datetime.now(CLINIC_TZ).date()


async def create_duty_entry(
    db: AsyncSession,
    *,
    actor: User,
    data: DutyEntryCreate,
) -> DutyEntry:
    await get_staff_or_404(db, data.staff_id)

    record = DutyEntry(
        staff_id=data.staff_id,
        date=_resolve_create_date(data.date),
        amount=data.amount,
        created_by_id=actor.id,
    )

    db.add(record)
    await db.flush()

    await record_audit_event(
        db,
        actor=actor,
        action="create_duty_entry",
        resource_type="duty_entry",
        resource_id=record.id,
    )

    await db.commit()
    await db.refresh(record)
    return record


async def get_duty_entry_or_404(db: AsyncSession, duty_entry_id: int) -> DutyEntry:
    record = await db.get(DutyEntry, duty_entry_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Duty entry not found")
    return record


async def list_duty_entries(
    db: AsyncSession,
    *,
    staff_id: int | None,
    date_from: date | None,
    date_to: date | None,
    page: int,
    page_size: int,
) -> tuple[list[DutyEntry], int]:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ValueError("date_from cannot be after date_to")

    stmt = select(DutyEntry).where(DutyEntry.is_voided.is_(False))

    if staff_id is not None:
        stmt = stmt.where(DutyEntry.staff_id == staff_id)
    if date_from is not None:
        stmt = stmt.where(DutyEntry.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(DutyEntry.date <= date_to)

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(DutyEntry.date.desc(), DutyEntry.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def update_duty_entry(
    db: AsyncSession,
    *,
    actor: User,
    duty_entry: DutyEntry,
    data: DutyEntryUpdate,
) -> DutyEntry:
    changes = data.model_dump(exclude_unset=True)

    if "staff_id" in changes and changes["staff_id"] is not None:
        await get_staff_or_404(db, changes["staff_id"])

    for field, value in changes.items():
        setattr(duty_entry, field, value)

    await record_audit_event(
        db,
        actor=actor,
        action="update_duty_entry",
        resource_type="duty_entry",
        resource_id=duty_entry.id,
        metadata={"changed_fields": list(changes.keys())},
    )

    await db.commit()
    await db.refresh(duty_entry)
    return duty_entry


async def void_duty_entry(db: AsyncSession, *, actor: User, duty_entry: DutyEntry) -> DutyEntry:
    if duty_entry.is_voided:
        raise HTTPException(status.HTTP_409_CONFLICT, "Duty entry is already voided")

    duty_entry.is_voided = True
    duty_entry.voided_at = datetime.now(ZoneInfo("UTC"))
    duty_entry.voided_by_id = actor.id

    await record_audit_event(
        db,
        actor=actor,
        action="void_duty_entry",
        resource_type="duty_entry",
        resource_id=duty_entry.id,
    )

    await db.commit()
    await db.refresh(duty_entry)
    return duty_entry
