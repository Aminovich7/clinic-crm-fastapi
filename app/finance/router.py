import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginatedResponse
from app.common.voidable import (
    hard_delete_voided_record,
    hide_if_voided,
    restore_voided_record,
)
from app.db.session import get_db
from app.finance.models import ConsultationType
from app.finance.reports import (
    build_consultation_report,
    build_room_report,
    build_surgery_report,
    build_total_report,
    report_xlsx_response,
)
from app.finance.schemas import (
    ConsultationCreate,
    ConsultationRead,
    ConsultationReport,
    ConsultationUpdate,
    FinanceSettingsRead,
    FinanceSettingsUpdate,
    RoomCreate,
    RoomRead,
    RoomReport,
    RoomUpdate,
    SurgeryCreate,
    SurgeryRead,
    SurgeryReport,
    SurgeryUpdate,
    TotalReport,
)
from app.finance.service import (
    create_consultation,
    create_room,
    create_surgery,
    get_consultation_or_404,
    get_finance_settings,
    get_room_or_404,
    get_surgery_or_404,
    list_consultations,
    list_rooms,
    list_surgeries,
    update_consultation,
    update_finance_settings,
    update_room,
    update_surgery,
    void_consultation,
    void_room,
    void_surgery,
)
from app.users.dependencies import require_roles
from app.users.models import User, UserRoleEnum

router = APIRouter(tags=["Finance"])

ALL_ROLES = (UserRoleEnum.SUPERADMIN, UserRoleEnum.MANAGER, UserRoleEnum.ASSISTANT)
MANAGE_ROLES = (UserRoleEnum.SUPERADMIN, UserRoleEnum.MANAGER)


def _forbid_if_not_owner(record, actor: User) -> None:
    if actor.role == UserRoleEnum.ASSISTANT and record.created_by_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this record",
        )


# ---------------------------------------------------------------------------
# Consultations
# ---------------------------------------------------------------------------


@router.post(
    "/consultations",
    response_model=ConsultationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_consultation_endpoint(
    data: ConsultationCreate,
    actor: User = Depends(require_roles(*ALL_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await create_consultation(db, actor=actor, data=data)


@router.get("/consultations", response_model=PaginatedResponse[ConsultationRead])
async def list_consultations_endpoint(
    doctor_id: int | None = Query(default=None),
    type: ConsultationType | None = Query(default=None),
    created_by_id: uuid.UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(require_roles(*ALL_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    try:
        items, total = await list_consultations(
            db,
            actor=actor,
            doctor_id=doctor_id,
            type_=type,
            created_by_id=created_by_id,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    pages = (total + page_size - 1) // page_size
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total, pages=pages)


@router.get("/consultations/{consultation_id}", response_model=ConsultationRead)
async def get_consultation_endpoint(
    consultation_id: int,
    actor: User = Depends(require_roles(*ALL_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_consultation_or_404(db, consultation_id)
    _forbid_if_not_owner(record, actor)
    return hide_if_voided(record, "Consultation not found")


@router.patch("/consultations/{consultation_id}", response_model=ConsultationRead)
async def update_consultation_endpoint(
    consultation_id: int,
    data: ConsultationUpdate,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_consultation_or_404(db, consultation_id)
    return await update_consultation(db, actor=actor, consultation=record, data=data)


@router.post("/consultations/{consultation_id}/void", response_model=ConsultationRead)
async def void_consultation_endpoint(
    consultation_id: int,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_consultation_or_404(db, consultation_id)
    return await void_consultation(db, actor=actor, consultation=record)


@router.post("/consultations/{consultation_id}/restore", response_model=ConsultationRead)
async def restore_consultation_endpoint(
    consultation_id: int,
    actor: User = Depends(require_roles(UserRoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_consultation_or_404(db, consultation_id)
    return await restore_voided_record(
        db,
        actor=actor,
        obj=record,
    )


@router.delete("/consultations/{consultation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_consultation_endpoint(
    consultation_id: int,
    actor: User = Depends(require_roles(UserRoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete an already-voided record (superadmin only).

    Irreversible: nothing of the record is kept anywhere, by design. The
    record must already be voided, which holds by construction because Audit
    Jurnali is the only page offering this action and it lists only voided
    records.
    """
    record = await get_consultation_or_404(db, consultation_id)
    await hard_delete_voided_record(
        db,
        actor=actor,
        obj=record,
    )


# ---------------------------------------------------------------------------
# Surgeries
# ---------------------------------------------------------------------------


@router.post("/surgeries", response_model=SurgeryRead, status_code=status.HTTP_201_CREATED)
async def create_surgery_endpoint(
    data: SurgeryCreate,
    actor: User = Depends(require_roles(*ALL_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await create_surgery(db, actor=actor, data=data)


@router.get("/surgeries", response_model=PaginatedResponse[SurgeryRead])
async def list_surgeries_endpoint(
    doctor_id: int | None = Query(default=None),
    created_by_id: uuid.UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(require_roles(*ALL_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    try:
        items, total = await list_surgeries(
            db,
            actor=actor,
            doctor_id=doctor_id,
            created_by_id=created_by_id,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    pages = (total + page_size - 1) // page_size
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total, pages=pages)


@router.get("/surgeries/{surgery_id}", response_model=SurgeryRead)
async def get_surgery_endpoint(
    surgery_id: int,
    actor: User = Depends(require_roles(*ALL_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_surgery_or_404(db, surgery_id)
    _forbid_if_not_owner(record, actor)
    return hide_if_voided(record, "Surgery not found")


@router.patch("/surgeries/{surgery_id}", response_model=SurgeryRead)
async def update_surgery_endpoint(
    surgery_id: int,
    data: SurgeryUpdate,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_surgery_or_404(db, surgery_id)
    return await update_surgery(db, actor=actor, surgery=record, data=data)


@router.post("/surgeries/{surgery_id}/void", response_model=SurgeryRead)
async def void_surgery_endpoint(
    surgery_id: int,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_surgery_or_404(db, surgery_id)
    return await void_surgery(db, actor=actor, surgery=record)


@router.post("/surgeries/{surgery_id}/restore", response_model=SurgeryRead)
async def restore_surgery_endpoint(
    surgery_id: int,
    actor: User = Depends(require_roles(UserRoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_surgery_or_404(db, surgery_id)
    return await restore_voided_record(
        db,
        actor=actor,
        obj=record,
    )


@router.delete("/surgeries/{surgery_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_surgery_endpoint(
    surgery_id: int,
    actor: User = Depends(require_roles(UserRoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete an already-voided record (superadmin only).

    Irreversible: nothing of the record is kept anywhere, by design. The
    record must already be voided, which holds by construction because Audit
    Jurnali is the only page offering this action and it lists only voided
    records.
    """
    record = await get_surgery_or_404(db, surgery_id)
    await hard_delete_voided_record(
        db,
        actor=actor,
        obj=record,
    )


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------


@router.post("/rooms", response_model=RoomRead, status_code=status.HTTP_201_CREATED)
async def create_room_endpoint(
    data: RoomCreate,
    actor: User = Depends(require_roles(*ALL_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await create_room(db, actor=actor, data=data)


@router.get("/rooms", response_model=PaginatedResponse[RoomRead])
async def list_rooms_endpoint(
    doctor_id: int | None = Query(default=None),
    created_by_id: uuid.UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(require_roles(*ALL_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    try:
        items, total = await list_rooms(
            db,
            actor=actor,
            doctor_id=doctor_id,
            created_by_id=created_by_id,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    pages = (total + page_size - 1) // page_size
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total, pages=pages)


@router.get("/rooms/{room_id}", response_model=RoomRead)
async def get_room_endpoint(
    room_id: int,
    actor: User = Depends(require_roles(*ALL_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_room_or_404(db, room_id)
    _forbid_if_not_owner(record, actor)
    return hide_if_voided(record, "Room record not found")


@router.patch("/rooms/{room_id}", response_model=RoomRead)
async def update_room_endpoint(
    room_id: int,
    data: RoomUpdate,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_room_or_404(db, room_id)
    return await update_room(db, actor=actor, room=record, data=data)


@router.post("/rooms/{room_id}/void", response_model=RoomRead)
async def void_room_endpoint(
    room_id: int,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_room_or_404(db, room_id)
    return await void_room(db, actor=actor, room=record)


@router.post("/rooms/{room_id}/restore", response_model=RoomRead)
async def restore_room_endpoint(
    room_id: int,
    actor: User = Depends(require_roles(UserRoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_room_or_404(db, room_id)
    return await restore_voided_record(
        db,
        actor=actor,
        obj=record,
    )


@router.delete("/rooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room_endpoint(
    room_id: int,
    actor: User = Depends(require_roles(UserRoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete an already-voided record (superadmin only).

    Irreversible: nothing of the record is kept anywhere, by design. The
    record must already be voided, which holds by construction because Audit
    Jurnali is the only page offering this action and it lists only voided
    records.
    """
    record = await get_room_or_404(db, room_id)
    await hard_delete_voided_record(
        db,
        actor=actor,
        obj=record,
    )


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@router.get("/reports/consultations")
async def consultations_report_endpoint(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    format: Literal["json", "xlsx"] = Query(default="json"),
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    try:
        report = await build_consultation_report(db, date_from=date_from, date_to=date_to, actor=actor)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    if format == "xlsx":
        return report_xlsx_response("consultations", report, date_from, date_to)
    return report


@router.get("/reports/surgeries")
async def surgeries_report_endpoint(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    format: Literal["json", "xlsx"] = Query(default="json"),
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    try:
        report = await build_surgery_report(db, date_from=date_from, date_to=date_to, actor=actor)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    if format == "xlsx":
        return report_xlsx_response("surgeries", report, date_from, date_to)
    return report


@router.get("/reports/rooms")
async def rooms_report_endpoint(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    format: Literal["json", "xlsx"] = Query(default="json"),
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    try:
        report = await build_room_report(db, date_from=date_from, date_to=date_to, actor=actor)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    if format == "xlsx":
        return report_xlsx_response("rooms", report, date_from, date_to)
    return report


@router.get("/reports/total")
async def total_report_endpoint(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    format: Literal["json", "xlsx"] = Query(default="json"),
    actor: User = Depends(require_roles(*ALL_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    try:
        report = await build_total_report(db, date_from=date_from, date_to=date_to, actor=actor)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    if format == "xlsx":
        return report_xlsx_response("total", report, date_from, date_to)
    return report


# ---------------------------------------------------------------------------
# Dynamic finance settings — superadmin only
# ---------------------------------------------------------------------------


@router.get("/admin/settings/finance", response_model=FinanceSettingsRead)
async def get_finance_settings_endpoint(
    _: User = Depends(require_roles(UserRoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await get_finance_settings(db)


@router.patch("/admin/settings/finance", response_model=FinanceSettingsRead)
async def update_finance_settings_endpoint(
    data: FinanceSettingsUpdate,
    actor: User = Depends(require_roles(UserRoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await update_finance_settings(db, actor=actor, data=data)
