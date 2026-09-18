from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginatedResponse
from app.common.voidable import (
    hard_delete_voided_record,
    hide_if_voided,
    restore_voided_record,
)
from app.db.session import get_db
from app.salary.schemas import (
    SalaryPaymentCreate,
    SalaryPaymentRead,
    SalaryPaymentUpdate,
    StaffEarnedPaidSummary,
    StaffLifetimeSummary,
)
from app.salary.service import (
    build_staff_balance,
    build_staff_lifetime_summary,
    create_salary_payment,
    get_salary_payment_or_404,
    list_salary_payments,
    sum_total_paid,
    update_salary_payment,
    void_salary_payment,
)
from app.staff.service import get_staff_or_404
from app.users.dependencies import require_roles
from app.users.models import User, UserRoleEnum

router = APIRouter(prefix="/salary", tags=["Oyliklar"])

MANAGE_ROLES = (UserRoleEnum.SUPERADMIN, UserRoleEnum.MANAGER)


@router.post("/payments", response_model=SalaryPaymentRead, status_code=status.HTTP_201_CREATED)
async def create_salary_payment_endpoint(
    data: SalaryPaymentCreate,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await create_salary_payment(db, actor=actor, data=data)


@router.get("/payments", response_model=PaginatedResponse[SalaryPaymentRead])
async def list_salary_payments_endpoint(
    staff_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    try:
        items, total = await list_salary_payments(
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


# Dashboard-only aggregate — registered before /payments/{id} isn't needed
# here since this lives under a different sub-path, but kept adjacent to
# the other summary endpoints for readability.
@router.get("/total-paid")
async def total_paid_endpoint(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    _: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    total = await sum_total_paid(db, date_from=date_from, date_to=date_to)
    return {"total_paid": total}


@router.get("/balance", response_model=list[StaffEarnedPaidSummary])
async def salary_balance_endpoint(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    staff_id: int | None = Query(default=None),
    _: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await build_staff_balance(db, date_from=date_from, date_to=date_to, staff_id=staff_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.get("/staff/{staff_id}/summary", response_model=StaffLifetimeSummary)
async def staff_lifetime_summary_endpoint(
    staff_id: int,
    _: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    staff = await get_staff_or_404(db, staff_id)
    return await build_staff_lifetime_summary(db, staff=staff)


@router.get("/payments/{salary_payment_id}", response_model=SalaryPaymentRead)
async def get_salary_payment_endpoint(
    salary_payment_id: int,
    _: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_salary_payment_or_404(db, salary_payment_id)
    return hide_if_voided(record, "Salary payment not found")


@router.patch("/payments/{salary_payment_id}", response_model=SalaryPaymentRead)
async def update_salary_payment_endpoint(
    salary_payment_id: int,
    data: SalaryPaymentUpdate,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_salary_payment_or_404(db, salary_payment_id)
    return await update_salary_payment(db, actor=actor, salary_payment=record, data=data)


@router.post("/payments/{salary_payment_id}/void", response_model=SalaryPaymentRead)
async def void_salary_payment_endpoint(
    salary_payment_id: int,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_salary_payment_or_404(db, salary_payment_id)
    return await void_salary_payment(db, actor=actor, salary_payment=record)


@router.post("/payments/{salary_payment_id}/restore", response_model=SalaryPaymentRead)
async def restore_salary_payment_endpoint(
    salary_payment_id: int,
    actor: User = Depends(require_roles(UserRoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_salary_payment_or_404(db, salary_payment_id)
    return await restore_voided_record(
        db,
        actor=actor,
        obj=record,
    )


@router.delete("/payments/{salary_payment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_salary_payment_endpoint(
    salary_payment_id: int,
    actor: User = Depends(require_roles(UserRoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete an already-voided record (superadmin only).

    Irreversible: nothing of the record is kept anywhere, by design. The
    record must already be voided, which holds by construction because Audit
    Jurnali is the only page offering this action and it lists only voided
    records.
    """
    record = await get_salary_payment_or_404(db, salary_payment_id)
    await hard_delete_voided_record(
        db,
        actor=actor,
        obj=record,
    )
