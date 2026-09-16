from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginatedResponse
from app.db.session import get_db
from app.duty.schemas import DutyEntryCreate, DutyEntryRead, DutyEntryUpdate
from app.duty.service import (
    create_duty_entry,
    get_duty_entry_or_404,
    list_duty_entries,
    update_duty_entry,
    void_duty_entry,
)
from app.users.dependencies import require_roles
from app.users.models import User, UserRoleEnum

router = APIRouter(prefix="/duty-entries", tags=["Navbatchilik"])

MANAGE_ROLES = (UserRoleEnum.SUPERADMIN, UserRoleEnum.MANAGER)


@router.post("", response_model=DutyEntryRead, status_code=status.HTTP_201_CREATED)
async def create_duty_entry_endpoint(
    data: DutyEntryCreate,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await create_duty_entry(db, actor=actor, data=data)


@router.get("", response_model=PaginatedResponse[DutyEntryRead])
async def list_duty_entries_endpoint(
    staff_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    try:
        items, total = await list_duty_entries(
            db,
            staff_id=staff_id,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    pages = (total + page_size - 1) // page_size
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total, pages=pages)


@router.get("/{duty_entry_id}", response_model=DutyEntryRead)
async def get_duty_entry_endpoint(
    duty_entry_id: int,
    _: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await get_duty_entry_or_404(db, duty_entry_id)


@router.patch("/{duty_entry_id}", response_model=DutyEntryRead)
async def update_duty_entry_endpoint(
    duty_entry_id: int,
    data: DutyEntryUpdate,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_duty_entry_or_404(db, duty_entry_id)
    return await update_duty_entry(db, actor=actor, duty_entry=record, data=data)


@router.post("/{duty_entry_id}/void", response_model=DutyEntryRead)
async def void_duty_entry_endpoint(
    duty_entry_id: int,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_duty_entry_or_404(db, duty_entry_id)
    return await void_duty_entry(db, actor=actor, duty_entry=record)
