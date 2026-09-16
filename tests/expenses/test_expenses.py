from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.expenses.schemas import ExpenseCreate
from app.expenses.service import create_expense, list_expenses, sum_expenses, void_expense
from app.users.models import User, UserRoleEnum


async def _get_superadmin(db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.role == UserRoleEnum.SUPERADMIN))
    return result.scalars().first()


@pytest.mark.asyncio
class TestExpenses:
    async def test_create_list_void(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)

        expense = await create_expense(
            seeded_db, actor=actor, data=ExpenseCreate(title="Elektr energiya", amount=150000)
        )
        assert expense.title == "Elektr energiya"

        items, total = await list_expenses(
            seeded_db, date_from=None, date_to=None, search=None, page=1, page_size=20
        )
        assert total == 1

        voided = await void_expense(seeded_db, actor=actor, expense=expense)
        assert voided.is_voided is True

        items, total = await list_expenses(
            seeded_db, date_from=None, date_to=None, search=None, page=1, page_size=20
        )
        assert total == 0

    async def test_search_by_title(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)

        await create_expense(seeded_db, actor=actor, data=ExpenseCreate(title="Internet to'lovi", amount=100000))
        await create_expense(seeded_db, actor=actor, data=ExpenseCreate(title="Tozalash xizmati", amount=50000))

        items, total = await list_expenses(
            seeded_db, date_from=None, date_to=None, search="internet", page=1, page_size=20
        )
        assert total == 1
        assert items[0].title == "Internet to'lovi"

    async def test_summary_totals_full_filtered_set(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)

        await create_expense(seeded_db, actor=actor, data=ExpenseCreate(title="A", amount=100000))
        await create_expense(seeded_db, actor=actor, data=ExpenseCreate(title="B", amount=200000))

        summary = await sum_expenses(seeded_db, date_from=None, date_to=None)
        assert summary.total_amount == Decimal("300000")
        assert summary.count == 2
