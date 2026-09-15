from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginatedResponse
from app.db.session import get_db
from app.doctors.schemas import (
    DoctorCreate,
    DoctorOption,
    DoctorRead,
    DoctorUpdate,
)
from app.doctors.service import (
    create_doctor,
    delete_doctor,
    get_doctor_or_404,
    list_doctor_options,
    list_doctors,
    update_doctor,
)
from app.users.dependencies import require_roles
from app.users.models import User, UserRoleEnum

router = APIRouter(
    prefix="/doctors",
    tags=["Doctors"],
)


# CREATE
@router.post(
    "",
    response_model=DoctorRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_doctor_endpoint(
    data: DoctorCreate,
    actor: User = Depends(
        require_roles(
            UserRoleEnum.SUPERADMIN,
            UserRoleEnum.MANAGER,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    return await create_doctor(db, actor=actor, data=data)


# OPTIONS — registered before /{doctor_id} so the literal path isn't
# swallowed by the path parameter.
@router.get(
    "/options",
    response_model=list[DoctorOption],
)
async def list_doctor_options_endpoint(
    _: User = Depends(
        require_roles(
            UserRoleEnum.SUPERADMIN,
            UserRoleEnum.MANAGER,
            UserRoleEnum.ASSISTANT,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    doctors = await list_doctor_options(db)
    return [
        DoctorOption(id=doctor.id, name=f"{doctor.last_name} {doctor.first_name}")
        for doctor in doctors
    ]


@router.get(
    "/{doctor_id}",
    response_model=DoctorRead,
)
async def get_doctor_endpoint(
    doctor_id: int,
    _: User = Depends(
        require_roles(
            UserRoleEnum.SUPERADMIN,
            UserRoleEnum.MANAGER,
            UserRoleEnum.ASSISTANT,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    return await get_doctor_or_404(db, doctor_id)


# UPDATE
@router.patch(
    "/{doctor_id}",
    response_model=DoctorRead,
)
async def update_doctor_endpoint(
    doctor_id: int,
    data: DoctorUpdate,
    actor: User = Depends(
        require_roles(
            UserRoleEnum.SUPERADMIN,
            UserRoleEnum.MANAGER,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    doctor = await get_doctor_or_404(db, doctor_id)

    return await update_doctor(
        db,
        actor=actor,
        doctor=doctor,
        data=data,
    )


# LIST
@router.get(
    "",
    response_model=PaginatedResponse[DoctorRead],
)
async def list_doctors_endpoint(
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(
        require_roles(
            UserRoleEnum.SUPERADMIN,
            UserRoleEnum.MANAGER,
            UserRoleEnum.ASSISTANT,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    items, total = await list_doctors(
        db,
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


# DELETE — SUPERADMIN only (kept stricter than the mk/ deviations doc's
# SUPERADMIN+MANAGER note; see plan.md Phase 0 item 3).
@router.delete(
    "/{doctor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_doctor_endpoint(
    doctor_id: int,
    actor: User = Depends(
        require_roles(
            UserRoleEnum.SUPERADMIN,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    doctor = await get_doctor_or_404(db, doctor_id)
    await delete_doctor(db, actor=actor, doctor=doctor)
