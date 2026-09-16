from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_audit_event
from app.duty.models import DutyEntry
from app.finance.models import Consultation, Room, Surgery
from app.salary.models import SalaryPayment
from app.staff.models import Staff, StaffRoleEnum, StaffStatusEnum
from app.staff.schemas import StaffCreate, StaffUpdate
from app.users.models import User, UserRoleEnum


def _validate_role_fields(*, role: StaffRoleEnum, specialty: str | None, fixed_salary) -> None:
    if role == StaffRoleEnum.DOCTOR:
        if not specialty or not specialty.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="specialty is required for doctors",
            )
        if fixed_salary is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="fixed_salary is not applicable to doctors",
            )


async def create_staff(
    db: AsyncSession,
    *,
    actor: User,
    data: StaffCreate,
) -> Staff:
    staff = Staff(
        first_name=data.first_name.strip(),
        last_name=data.last_name.strip(),
        specialty=data.specialty.strip() if data.specialty else None,
        role=data.role,
        fixed_salary=data.fixed_salary,
        hire_date=data.hire_date,
        status=StaffStatusEnum.ACTIVE,
    )

    db.add(staff)
    await db.flush()

    await record_audit_event(
        db,
        actor=actor,
        action="create_staff",
        resource_type="staff",
        resource_id=staff.id,
    )

    await db.commit()
    await db.refresh(staff)

    return staff


async def get_staff_or_404(db: AsyncSession, staff_id: int) -> Staff:
    staff = await db.get(Staff, staff_id)

    if staff is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff member not found",
        )

    return staff


async def update_staff(
    db: AsyncSession,
    *,
    actor: User,
    staff: Staff,
    data: StaffUpdate,
) -> Staff:
    changes = data.model_dump(exclude_unset=True)

    for field, value in changes.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(staff, field, value)

    # Validate the merged final state, not just the changed fields.
    _validate_role_fields(
        role=staff.role,
        specialty=staff.specialty,
        fixed_salary=staff.fixed_salary,
    )

    await record_audit_event(
        db,
        actor=actor,
        action="update_staff",
        resource_type="staff",
        resource_id=staff.id,
        metadata={"changed_fields": list(changes.keys())},
    )

    await db.commit()
    await db.refresh(staff)

    return staff


async def list_staff(
    db: AsyncSession,
    *,
    role: StaffRoleEnum | None,
    status_: StaffStatusEnum | None,
    search: str | None,
    page: int,
    page_size: int,
) -> tuple[list[Staff], int]:
    stmt = select(Staff)

    if role is not None:
        stmt = stmt.where(Staff.role == role)
    if status_ is not None:
        stmt = stmt.where(Staff.status == status_)
    if search:
        search_value = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Staff.first_name.ilike(search_value),
                Staff.last_name.ilike(search_value),
                Staff.specialty.ilike(search_value),
            )
        )

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(
            Staff.last_name.asc(),
            Staff.first_name.asc(),
            Staff.id.asc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(stmt)

    return list(result.scalars().all()), total


async def list_staff_options(
    db: AsyncSession,
    *,
    role: StaffRoleEnum | None,
    actor: User,
) -> list[Staff]:
    # Assistants must never receive nurse/other rows, regardless of what
    # role filter they asked for — force it server-side.
    if actor.role == UserRoleEnum.ASSISTANT:
        role = StaffRoleEnum.DOCTOR

    stmt = select(Staff).where(Staff.status == StaffStatusEnum.ACTIVE)

    if role is not None:
        stmt = stmt.where(Staff.role == role)

    stmt = stmt.order_by(
        Staff.last_name.asc(),
        Staff.first_name.asc(),
        Staff.id.asc(),
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def activate_staff(db: AsyncSession, *, actor: User, staff: Staff) -> Staff:
    if staff.status != StaffStatusEnum.ACTIVE:
        staff.status = StaffStatusEnum.ACTIVE

        await record_audit_event(
            db,
            actor=actor,
            action="activate_staff",
            resource_type="staff",
            resource_id=staff.id,
        )

        await db.commit()
        await db.refresh(staff)

    return staff


async def deactivate_staff(db: AsyncSession, *, actor: User, staff: Staff) -> Staff:
    if staff.status != StaffStatusEnum.INACTIVE:
        staff.status = StaffStatusEnum.INACTIVE

        await record_audit_event(
            db,
            actor=actor,
            action="deactivate_staff",
            resource_type="staff",
            resource_id=staff.id,
        )

        await db.commit()
        await db.refresh(staff)

    return staff


async def _staff_has_financial_history(db: AsyncSession, staff_id: int) -> bool:
    checks = (
        select(Consultation.id).where(Consultation.doctor_id == staff_id).limit(1),
        select(Surgery.id).where(Surgery.doctor_id == staff_id).limit(1),
        select(Room.id).where(Room.doctor_id == staff_id).limit(1),
        select(DutyEntry.id).where(DutyEntry.staff_id == staff_id).limit(1),
        select(SalaryPayment.id).where(SalaryPayment.staff_id == staff_id).limit(1),
    )

    for check_stmt in checks:
        result = await db.execute(check_stmt)
        if result.first() is not None:
            return True

    return False


async def delete_staff(db: AsyncSession, *, actor: User, staff: Staff) -> None:
    if await _staff_has_financial_history(db, staff.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot delete staff with existing financial/payroll history; "
                "deactivate instead."
            ),
        )

    staff_id = staff.id

    await record_audit_event(
        db,
        actor=actor,
        action="delete_staff",
        resource_type="staff",
        resource_id=staff_id,
    )

    await db.delete(staff)
    await db.commit()
