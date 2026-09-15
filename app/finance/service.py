from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_audit_event
from app.doctors.models import Doctor
from app.finance.models import Consultation, ConsultationType, Room, Surgery, SystemSetting
from app.finance.reports import get_business_datetime_range
from app.finance.schemas import (
    ConsultationCreate,
    ConsultationUpdate,
    FinanceSettingsUpdate,
    RoomCreate,
    RoomUpdate,
    SurgeryCreate,
    SurgeryUpdate,
)
from app.users.models import User, UserRoleEnum

CLINIC_TZ = ZoneInfo("Asia/Tashkent")

SETTINGS_ROW_ID = 1


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _require_doctor(db: AsyncSession, doctor_id: int | None) -> None:
    if doctor_id is None:
        return
    doctor = await db.get(Doctor, doctor_id)
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )


def _require_expense_not_greater_than_income(*, amount: Decimal, expense: Decimal) -> None:
    if expense > amount:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Expense cannot exceed amount",
        )


def _resolve_create_date(date_value: datetime | None) -> datetime:
    return date_value if date_value is not None else datetime.now(CLINIC_TZ)


def _apply_assistant_ownership(stmt, model, actor: User):
    if actor.role == UserRoleEnum.ASSISTANT:
        stmt = stmt.where(model.created_by_id == actor.id)
    return stmt


def _forbid_if_not_owner_or_privileged(record, actor: User) -> None:
    if actor.role == UserRoleEnum.ASSISTANT and record.created_by_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this record",
        )


# ---------------------------------------------------------------------------
# Finance settings (dynamic minus_beshming default)
# ---------------------------------------------------------------------------


async def get_finance_settings(db: AsyncSession) -> SystemSetting:
    settings_row = await db.get(SystemSetting, SETTINGS_ROW_ID)
    if settings_row is None:
        # Should not happen — the migration seeds this row — but guard anyway.
        settings_row = SystemSetting(
            id=SETTINGS_ROW_ID, default_minus_beshming=Decimal("5000")
        )
        db.add(settings_row)
        await db.commit()
        await db.refresh(settings_row)
    return settings_row


async def get_minus_beshming_default(db: AsyncSession) -> Decimal:
    settings_row = await get_finance_settings(db)
    return settings_row.default_minus_beshming


async def update_finance_settings(
    db: AsyncSession, *, actor: User, data: FinanceSettingsUpdate
) -> SystemSetting:
    settings_row = await get_finance_settings(db)

    settings_row.default_minus_beshming = data.default_minus_beshming
    settings_row.updated_by_id = actor.id

    await record_audit_event(
        db,
        actor=actor,
        action="update_finance_settings",
        resource_type="finance_settings",
        resource_id=SETTINGS_ROW_ID,
        metadata={"default_minus_beshming": str(data.default_minus_beshming)},
    )

    await db.commit()
    await db.refresh(settings_row)
    return settings_row


# ---------------------------------------------------------------------------
# Consultations
# ---------------------------------------------------------------------------


async def create_consultation(
    db: AsyncSession,
    *,
    actor: User,
    data: ConsultationCreate,
) -> Consultation:
    await _require_doctor(db, data.doctor_id)

    minus_beshming = data.minus_beshming
    if minus_beshming is None:
        minus_beshming = await get_minus_beshming_default(db)

    _require_expense_not_greater_than_income(amount=data.amount, expense=minus_beshming)

    record = Consultation(
        type=data.type,
        receipt_number=data.receipt_number,
        date=_resolve_create_date(data.date),
        amount=data.amount,
        doctor_percent=data.doctor_percent,
        minus_beshming=minus_beshming,
        doctor_id=data.doctor_id,
        created_by_id=actor.id,
    )

    db.add(record)
    await db.flush()

    await record_audit_event(
        db,
        actor=actor,
        action="create_consultation",
        resource_type="consultation",
        resource_id=record.id,
    )

    await db.commit()
    await db.refresh(record)
    return record


async def get_consultation_or_404(db: AsyncSession, consultation_id: int) -> Consultation:
    record = await db.get(Consultation, consultation_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consultation not found")
    return record


async def list_consultations(
    db: AsyncSession,
    *,
    actor: User,
    doctor_id: int | None,
    type_: ConsultationType | None,
    created_by_id=None,
    date_from,
    date_to,
    page: int,
    page_size: int,
) -> tuple[list[Consultation], int]:
    stmt = select(Consultation).where(Consultation.is_voided.is_(False))
    stmt = _apply_assistant_ownership(stmt, Consultation, actor)

    if doctor_id is not None:
        stmt = stmt.where(Consultation.doctor_id == doctor_id)
    if type_ is not None:
        stmt = stmt.where(Consultation.type == type_)
    if created_by_id is not None:
        stmt = stmt.where(Consultation.created_by_id == created_by_id)

    start, end = get_business_datetime_range(date_from, date_to)
    if start:
        stmt = stmt.where(Consultation.date >= start)
    if end:
        stmt = stmt.where(Consultation.date < end)


    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(Consultation.date.desc(), Consultation.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def update_consultation(
    db: AsyncSession, *, actor: User, consultation: Consultation, data: ConsultationUpdate
) -> Consultation:
    changes = data.model_dump(exclude_unset=True)

    if "doctor_id" in changes:
        await _require_doctor(db, changes["doctor_id"])

    new_amount = changes.get("amount", consultation.amount)
    new_minus = changes.get("minus_beshming", consultation.minus_beshming)
    _require_expense_not_greater_than_income(
        amount=new_amount, expense=new_minus or Decimal("0")
    )

    for field, value in changes.items():
        setattr(consultation, field, value)

    await record_audit_event(
        db,
        actor=actor,
        action="update_consultation",
        resource_type="consultation",
        resource_id=consultation.id,
        metadata={"changed_fields": list(changes.keys())},
    )

    await db.commit()
    await db.refresh(consultation)
    return consultation


async def void_consultation(db: AsyncSession, *, actor: User, consultation: Consultation) -> Consultation:
    if consultation.is_voided:
        raise HTTPException(status.HTTP_409_CONFLICT, "Consultation is already voided")

    consultation.is_voided = True
    consultation.voided_at = datetime.now(ZoneInfo("UTC"))
    consultation.voided_by_id = actor.id

    await record_audit_event(
        db,
        actor=actor,
        action="void_consultation",
        resource_type="consultation",
        resource_id=consultation.id,
    )

    await db.commit()
    await db.refresh(consultation)
    return consultation


# ---------------------------------------------------------------------------
# Surgeries
# ---------------------------------------------------------------------------


async def create_surgery(db: AsyncSession, *, actor: User, data: SurgeryCreate) -> Surgery:
    await _require_doctor(db, data.doctor_id)
    _require_expense_not_greater_than_income(amount=data.amount, expense=data.surgery_expense)

    record = Surgery(
        receipt_number=data.receipt_number,
        date=_resolve_create_date(data.date),
        amount=data.amount,
        surgery_expense=data.surgery_expense,
        doctor_percent=data.doctor_percent,
        doctor_id=data.doctor_id,
        created_by_id=actor.id,
    )

    db.add(record)
    await db.flush()

    await record_audit_event(
        db,
        actor=actor,
        action="create_surgery",
        resource_type="surgery",
        resource_id=record.id,
    )

    await db.commit()
    await db.refresh(record)
    return record


async def get_surgery_or_404(db: AsyncSession, surgery_id: int) -> Surgery:
    record = await db.get(Surgery, surgery_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Surgery not found")
    return record


async def list_surgeries(
    db: AsyncSession,
    *,
    actor: User,
    doctor_id: int | None,
    created_by_id=None,
    date_from,
    date_to,
    page: int,
    page_size: int,
) -> tuple[list[Surgery], int]:
    stmt = select(Surgery).where(Surgery.is_voided.is_(False))
    stmt = _apply_assistant_ownership(stmt, Surgery, actor)

    if doctor_id is not None:
        stmt = stmt.where(Surgery.doctor_id == doctor_id)
    if created_by_id is not None:
        stmt = stmt.where(Surgery.created_by_id == created_by_id)

    start, end = get_business_datetime_range(date_from, date_to)
    if start:
        stmt = stmt.where(Surgery.date >= start)
    if end:
        stmt = stmt.where(Surgery.date < end)


    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(Surgery.date.desc(), Surgery.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def update_surgery(
    db: AsyncSession, *, actor: User, surgery: Surgery, data: SurgeryUpdate
) -> Surgery:
    changes = data.model_dump(exclude_unset=True)

    if "doctor_id" in changes:
        await _require_doctor(db, changes["doctor_id"])

    new_amount = changes.get("amount", surgery.amount)
    new_expense = changes.get("surgery_expense", surgery.surgery_expense)
    _require_expense_not_greater_than_income(amount=new_amount, expense=new_expense)

    for field, value in changes.items():
        setattr(surgery, field, value)

    await record_audit_event(
        db,
        actor=actor,
        action="update_surgery",
        resource_type="surgery",
        resource_id=surgery.id,
        metadata={"changed_fields": list(changes.keys())},
    )

    await db.commit()
    await db.refresh(surgery)
    return surgery


async def void_surgery(db: AsyncSession, *, actor: User, surgery: Surgery) -> Surgery:
    if surgery.is_voided:
        raise HTTPException(status.HTTP_409_CONFLICT, "Surgery is already voided")

    surgery.is_voided = True
    surgery.voided_at = datetime.now(ZoneInfo("UTC"))
    surgery.voided_by_id = actor.id

    await record_audit_event(
        db,
        actor=actor,
        action="void_surgery",
        resource_type="surgery",
        resource_id=surgery.id,
    )

    await db.commit()
    await db.refresh(surgery)
    return surgery


# ---------------------------------------------------------------------------
# Rooms — no expense concept at all
# ---------------------------------------------------------------------------


async def create_room(db: AsyncSession, *, actor: User, data: RoomCreate) -> Room:
    await _require_doctor(db, data.doctor_id)

    record = Room(
        receipt_number=data.receipt_number,
        date=_resolve_create_date(data.date),
        amount=data.amount,
        doctor_percent=data.doctor_percent,
        doctor_id=data.doctor_id,
        created_by_id=actor.id,
    )

    db.add(record)
    await db.flush()

    await record_audit_event(
        db,
        actor=actor,
        action="create_room",
        resource_type="room",
        resource_id=record.id,
    )

    await db.commit()
    await db.refresh(record)
    return record


async def get_room_or_404(db: AsyncSession, room_id: int) -> Room:
    record = await db.get(Room, room_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Room record not found")
    return record


async def list_rooms(
    db: AsyncSession,
    *,
    actor: User,
    doctor_id: int | None,
    created_by_id=None,
    date_from,
    date_to,
    page: int,
    page_size: int,
) -> tuple[list[Room], int]:
    stmt = select(Room).where(Room.is_voided.is_(False))
    stmt = _apply_assistant_ownership(stmt, Room, actor)

    if doctor_id is not None:
        stmt = stmt.where(Room.doctor_id == doctor_id)
    if created_by_id is not None:
        stmt = stmt.where(Room.created_by_id == created_by_id)

    start, end = get_business_datetime_range(date_from, date_to)
    if start:
        stmt = stmt.where(Room.date >= start)
    if end:
        stmt = stmt.where(Room.date < end)


    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(Room.date.desc(), Room.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def update_room(db: AsyncSession, *, actor: User, room: Room, data: RoomUpdate) -> Room:
    changes = data.model_dump(exclude_unset=True)

    if "doctor_id" in changes:
        await _require_doctor(db, changes["doctor_id"])

    for field, value in changes.items():
        setattr(room, field, value)

    await record_audit_event(
        db,
        actor=actor,
        action="update_room",
        resource_type="room",
        resource_id=room.id,
        metadata={"changed_fields": list(changes.keys())},
    )

    await db.commit()
    await db.refresh(room)
    return room


async def void_room(db: AsyncSession, *, actor: User, room: Room) -> Room:
    if room.is_voided:
        raise HTTPException(status.HTTP_409_CONFLICT, "Room record is already voided")

    room.is_voided = True
    room.voided_at = datetime.now(ZoneInfo("UTC"))
    room.voided_by_id = actor.id

    await record_audit_event(
        db,
        actor=actor,
        action="void_room",
        resource_type="room",
        resource_id=room.id,
    )

    await db.commit()
    await db.refresh(room)
    return room
