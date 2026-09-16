from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginatedResponse
from app.db.session import get_db
from app.pharmacy.schemas import (
    PharmacyBalance,
    PharmacyEntryCreate,
    PharmacyEntryRead,
    PharmacyEntryUpdate,
)
from app.pharmacy.service import (
    build_pharmacy_balance,
    create_pharmacy_entry,
    get_pharmacy_entry_or_404,
    list_pharmacy_entries,
    update_pharmacy_entry,
    void_pharmacy_entry,
)
from app.users.dependencies import require_roles
from app.users.models import User, UserRoleEnum

router = APIRouter(prefix="/pharmacy", tags=["Dorixona"])

MANAGE_ROLES = (UserRoleEnum.SUPERADMIN, UserRoleEnum.MANAGER)


@router.post("/entries", response_model=PharmacyEntryRead, status_code=status.HTTP_201_CREATED)
async def create_pharmacy_entry_endpoint(
    data: PharmacyEntryCreate,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await create_pharmacy_entry(db, actor=actor, data=data)


@router.get("/entries", response_model=PaginatedResponse[PharmacyEntryRead])
async def list_pharmacy_entries_endpoint(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    try:
        items, total = await list_pharmacy_entries(
            db, date_from=date_from, date_to=date_to, page=page, page_size=page_size
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    pages = (total + page_size - 1) // page_size
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total, pages=pages)


@router.get("/summary", response_model=PharmacyBalance)
async def pharmacy_summary_endpoint(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    _: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await build_pharmacy_balance(db, date_from=date_from, date_to=date_to)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.get("/entries/{pharmacy_entry_id}", response_model=PharmacyEntryRead)
async def get_pharmacy_entry_endpoint(
    pharmacy_entry_id: int,
    _: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await get_pharmacy_entry_or_404(db, pharmacy_entry_id)


@router.patch("/entries/{pharmacy_entry_id}", response_model=PharmacyEntryRead)
async def update_pharmacy_entry_endpoint(
    pharmacy_entry_id: int,
    data: PharmacyEntryUpdate,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_pharmacy_entry_or_404(db, pharmacy_entry_id)
    return await update_pharmacy_entry(db, actor=actor, pharmacy_entry=record, data=data)


@router.post("/entries/{pharmacy_entry_id}/void", response_model=PharmacyEntryRead)
async def void_pharmacy_entry_endpoint(
    pharmacy_entry_id: int,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_pharmacy_entry_or_404(db, pharmacy_entry_id)
    return await void_pharmacy_entry(db, actor=actor, pharmacy_entry=record)
