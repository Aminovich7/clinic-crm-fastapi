from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.voidable import forbid_edit_if_voided
from app.expenses.models import Expense
from app.expenses.schemas import ExpenseCreate, ExpenseSummary, ExpenseUpdate
from app.finance.calculations import money
from app.finance.reports import get_business_datetime_range
from app.users.models import User

CLINIC_TZ = ZoneInfo("Asia/Tashkent")
ZERO = Decimal("0")

def _resolve_create_date(value: datetime | None) -> datetime:
    return value if value is not None else datetime.now(CLINIC_TZ)

def _apply_filters(stmt, *, date_from, date_to, search):
    start, end = get_business_datetime_range(date_from, date_to)
    if start:
        stmt = stmt.where(Expense.date >= start)
    if end:
        stmt = stmt.where(Expense.date < end)
    if search:
        stmt = stmt.where(Expense.title.ilike(f"%{search.strip()}%"))
    return stmt

async def create_expense(db: AsyncSession, *, actor: User, data: ExpenseCreate) -> Expense:
    record = Expense(
        title=data.title.strip(),
        amount=data.amount,
        date=_resolve_create_date(data.date),
        created_by_id=actor.id,
    )

    db.add(record)
    await db.flush()

    await db.commit()
    await db.refresh(record)
    return record

async def get_expense_or_404(db: AsyncSession, expense_id: int) -> Expense:
    record = await db.get(Expense, expense_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Expense not found")
    return record

async def list_expenses(
    db: AsyncSession,
    *,
    date_from: date | None,
    date_to: date | None,
    search: str | None,
    page: int,
    page_size: int,
) -> tuple[list[Expense], int]:
    stmt = select(Expense).where(Expense.is_voided.is_(False))
    stmt = _apply_filters(stmt, date_from=date_from, date_to=date_to, search=search)

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(Expense.date.desc(), Expense.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all()), total

async def sum_expenses(
    db: AsyncSession,
    *,
    date_from: date | None,
    date_to: date | None,
    search: str | None = None,
) -> ExpenseSummary:
    # Totals over the full filtered set, never just the current page.
    stmt = select(
        func.coalesce(func.sum(Expense.amount), ZERO),
        func.count(),
    ).where(Expense.is_voided.is_(False))
    stmt = _apply_filters(stmt, date_from=date_from, date_to=date_to, search=search)

    total_amount, count = (await db.execute(stmt)).one()

    return ExpenseSummary(total_amount=money(total_amount), count=count)

async def update_expense(
    db: AsyncSession, *, actor: User, expense: Expense, data: ExpenseUpdate
) -> Expense:
    forbid_edit_if_voided(expense)
    changes = data.model_dump(exclude_unset=True)

    for field, value in changes.items():
        if field == "title" and isinstance(value, str):
            value = value.strip()
        setattr(expense, field, value)

    await db.commit()
    await db.refresh(expense)
    return expense

async def void_expense(db: AsyncSession, *, actor: User, expense: Expense) -> Expense:
    if expense.is_voided:
        raise HTTPException(status.HTTP_409_CONFLICT, "Expense is already voided")

    expense.is_voided = True
    expense.voided_at = datetime.now(ZoneInfo("UTC"))
    expense.voided_by_id = actor.id

    await db.commit()
    await db.refresh(expense)
    return expense
