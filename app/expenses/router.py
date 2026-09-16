from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PaginatedResponse
from app.db.session import get_db
from app.expenses.schemas import ExpenseCreate, ExpenseRead, ExpenseSummary, ExpenseUpdate
from app.expenses.service import (
    create_expense,
    get_expense_or_404,
    list_expenses,
    sum_expenses,
    update_expense,
    void_expense,
)
from app.users.dependencies import require_roles
from app.users.models import User, UserRoleEnum

router = APIRouter(prefix="/expenses", tags=["Boshqa harajatlar"])

MANAGE_ROLES = (UserRoleEnum.SUPERADMIN, UserRoleEnum.MANAGER)


@router.post("", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
async def create_expense_endpoint(
    data: ExpenseCreate,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await create_expense(db, actor=actor, data=data)


@router.get("", response_model=PaginatedResponse[ExpenseRead])
async def list_expenses_endpoint(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    try:
        items, total = await list_expenses(
            db, date_from=date_from, date_to=date_to, search=search, page=page, page_size=page_size
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    pages = (total + page_size - 1) // page_size
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total, pages=pages)


@router.get("/summary", response_model=ExpenseSummary)
async def expenses_summary_endpoint(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    search: str | None = Query(default=None),
    _: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await sum_expenses(db, date_from=date_from, date_to=date_to, search=search)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.get("/{expense_id}", response_model=ExpenseRead)
async def get_expense_endpoint(
    expense_id: int,
    _: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    return await get_expense_or_404(db, expense_id)


@router.patch("/{expense_id}", response_model=ExpenseRead)
async def update_expense_endpoint(
    expense_id: int,
    data: ExpenseUpdate,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_expense_or_404(db, expense_id)
    return await update_expense(db, actor=actor, expense=record, data=data)


@router.post("/{expense_id}/void", response_model=ExpenseRead)
async def void_expense_endpoint(
    expense_id: int,
    actor: User = Depends(require_roles(*MANAGE_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    record = await get_expense_or_404(db, expense_id)
    return await void_expense(db, actor=actor, expense=record)
