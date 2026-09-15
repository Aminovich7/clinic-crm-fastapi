from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_audit_event
from app.doctors.models import Doctor
from app.doctors.schemas import DoctorCreate, DoctorUpdate
from app.users.models import User


async def create_doctor(
    db: AsyncSession,
    *,
    actor: User,
    data: DoctorCreate,
) -> Doctor:

    doctor = Doctor(
        first_name=data.first_name.strip(),
        last_name=data.last_name.strip(),
        specialty=data.specialty.strip(),
    )

    db.add(doctor)
    await db.flush()

    await record_audit_event(
        db,
        actor=actor,
        action="create_doctor",
        resource_type="doctor",
        resource_id=doctor.id,
    )

    await db.commit()
    await db.refresh(doctor)

    return doctor


async def get_doctor_or_404(
    db: AsyncSession,
    doctor_id: int,
) -> Doctor:

    doctor = await db.get(Doctor, doctor_id)

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    return doctor


async def update_doctor(
    db: AsyncSession,
    *,
    actor: User,
    doctor: Doctor,
    data: DoctorUpdate,
) -> Doctor:

    changes = data.model_dump(exclude_unset=True)

    for field, value in changes.items():
        if isinstance(value, str):
            value = value.strip()

        setattr(doctor, field, value)

    await record_audit_event(
        db,
        actor=actor,
        action="update_doctor",
        resource_type="doctor",
        resource_id=doctor.id,
        metadata={"changed_fields": list(changes.keys())},
    )

    await db.commit()
    await db.refresh(doctor)

    return doctor


async def list_doctors(
    db: AsyncSession,
    *,
    search: str | None,
    page: int,
    page_size: int,
) -> tuple[list[Doctor], int]:

    stmt = select(Doctor)

    if search:
        search_value = f"%{search.strip()}%"

        stmt = stmt.where(
            or_(
                Doctor.first_name.ilike(search_value),
                Doctor.last_name.ilike(search_value),
                Doctor.specialty.ilike(search_value),
            )
        )

    count_stmt = select(func.count()).select_from(
        stmt.order_by(None).subquery()
    )

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt
        .order_by(
            Doctor.last_name.asc(),
            Doctor.first_name.asc(),
            Doctor.id.asc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(stmt)

    return list(result.scalars().all()), total


async def list_doctor_options(db: AsyncSession) -> list[Doctor]:
    stmt = select(Doctor).order_by(
        Doctor.last_name.asc(),
        Doctor.first_name.asc(),
        Doctor.id.asc(),
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def delete_doctor(
    db: AsyncSession,
    *,
    actor: User,
    doctor: Doctor,
) -> None:
    doctor_id = doctor.id

    await record_audit_event(
        db,
        actor=actor,
        action="delete_doctor",
        resource_type="doctor",
        resource_id=doctor_id,
    )

    await db.delete(doctor)
    await db.commit()
