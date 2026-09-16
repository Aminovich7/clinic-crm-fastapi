from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginatedResponse
from app.db.session import get_db
from app.staff.models import StaffRoleEnum, StaffStatusEnum
from app.staff.schemas import StaffCreate, StaffOption, StaffRead, StaffUpdate
from app.staff.service import (
    activate_staff,
    create_staff,
    deactivate_staff,
    delete_staff,
    get_staff_or_404,
    list_staff,
    list_staff_options,
    update_staff,
)
from app.users.dependencies import require_roles
from app.users.models import User, UserRoleEnum

router = APIRouter(prefix="/staff", tags=["Staff"])

ALL_ROLES = (UserRoleEnum.SUPERADMIN, UserRoleEnum.MANAGER, UserRoleEnum.ASSISTANT)
MANAGE_ROLES = (UserRoleEnum.SUPERADMIN, UserRoleEnum.MANAGER)


# CREATE
@router.post("", response_model=StaffRead, status_code=status.HTTP_201_CREATED)
async def create_staff_endpoint(
    data: StaffCreate,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await create_staff(db, actor=actor, data=data)


# OPTIONS — registered before /{staff_id} so the literal path isn't
# swallowed by the path parameter. Open to all roles; assistants are
# force-filtered to role=DOCTOR server-side regardless of the query param.
@router.get("/options", response_model=list[StaffOption])
async def list_staff_options_endpoint(
    role: StaffRoleEnum | None = Query(default=None),
    actor: User = Depends(require_roles(*ALL_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    staff = await list_staff_options(db, role=role, actor=actor)
    return [
        StaffOption(id=member.id, name=f"{member.last_name} {member.first_name}", role=member.role)
        for member in staff
    ]


@router.get("/{staff_id}", response_model=StaffRead)
async def get_staff_endpoint(
    staff_id: int,
    _: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await get_staff_or_404(db, staff_id)


# UPDATE
@router.patch("/{staff_id}", response_model=StaffRead)
async def update_staff_endpoint(
    staff_id: int,
    data: StaffUpdate,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    staff = await get_staff_or_404(db, staff_id)
    return await update_staff(db, actor=actor, staff=staff, data=data)


# LIST
@router.get("", response_model=PaginatedResponse[StaffRead])
async def list_staff_endpoint(
    role: StaffRoleEnum | None = Query(default=None),
    status_filter: StaffStatusEnum | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    items, total = await list_staff(
        db,
        role=role,
        status_=status_filter,
        search=search,
        page=page,
        page_size=page_size,
    )

    pages = (total + page_size - 1) // page_size

    return PaginatedResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        pages=pages,
    )


@router.post("/{staff_id}/activate", response_model=StaffRead)
async def activate_staff_endpoint(
    staff_id: int,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    staff = await get_staff_or_404(db, staff_id)
    return await activate_staff(db, actor=actor, staff=staff)


@router.post("/{staff_id}/deactivate", response_model=StaffRead)
async def deactivate_staff_endpoint(
    staff_id: int,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    staff = await get_staff_or_404(db, staff_id)
    return await deactivate_staff(db, actor=actor, staff=staff)


# DELETE — SUPERADMIN only, blocked with 409 if financial/payroll history
# exists (see app.staff.service._staff_has_financial_history).
@router.delete("/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_staff_endpoint(
    staff_id: int,
    actor: User = Depends(require_roles(UserRoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    staff = await get_staff_or_404(db, staff_id)
    await delete_staff(db, actor=actor, staff=staff)
