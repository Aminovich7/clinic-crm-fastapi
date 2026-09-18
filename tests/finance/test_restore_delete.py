"""Restore (un-void) and hard delete of voided records.

Both operations live in app/common/voidable.py and are shared by all seven
VoidableMixin resources, so these tests exercise one finance resource
(consultations) and one non-finance resource (expenses) to prove the shared
implementation generalises.
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.voided import list_voided_records
from app.common.voidable import hard_delete_voided_record, restore_voided_record
from app.expenses.schemas import ExpenseCreate
from app.expenses.models import Expense
from app.expenses.service import create_expense, list_expenses, void_expense
from app.finance.models import Consultation, ConsultationType
from app.finance.schemas import ConsultationCreate
from app.finance.service import (
    create_consultation,
    list_consultations,
    void_consultation,
)
from app.users.models import User, UserRoleEnum


async def _get_superadmin(db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.role == UserRoleEnum.SUPERADMIN))
    return result.scalars().first()


async def _make_consultation(db: AsyncSession, actor: User) -> Consultation:
    return await create_consultation(
        db,
        actor=actor,
        data=ConsultationCreate(
            type=ConsultationType.KORIK,
            receipt_number=7001,
            date=datetime(2026, 3, 10),
            amount=Decimal("120000"),
            doctor_percent=Decimal("50"),
            minus_beshming=Decimal("5000"),
        ),
    )


@pytest.mark.asyncio
class TestRestore:
    async def test_restore_clears_all_void_flags(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)
        record = await _make_consultation(seeded_db, actor)
        await void_consultation(seeded_db, actor=actor, consultation=record)
        assert record.is_voided is True

        restored = await restore_voided_record(
            seeded_db,
            actor=actor,
            obj=record,
        )

        assert restored.is_voided is False
        assert restored.voided_at is None
        assert restored.voided_by_id is None

    async def test_restored_record_reappears_in_listings(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)
        record = await _make_consultation(seeded_db, actor)
        await void_consultation(seeded_db, actor=actor, consultation=record)

        items, _ = await list_consultations(
            seeded_db, actor=actor, doctor_id=None, type_=None,
            date_from=None, date_to=None, page=1, page_size=50,
        )
        assert record.id not in [c.id for c in items]

        await restore_voided_record(
            seeded_db, actor=actor, obj=record,
        )

        items, _ = await list_consultations(
            seeded_db, actor=actor, doctor_id=None, type_=None,
            date_from=None, date_to=None, page=1, page_size=50,
        )
        assert record.id in [c.id for c in items]

    async def test_restore_preserves_original_values(self, seeded_db: AsyncSession):
        """Voiding never destroyed data, so a restore returns it untouched."""
        actor = await _get_superadmin(seeded_db)
        record = await _make_consultation(seeded_db, actor)
        await void_consultation(seeded_db, actor=actor, consultation=record)

        restored = await restore_voided_record(
            seeded_db, actor=actor, obj=record,
        )

        assert restored.receipt_number == 7001
        assert restored.amount == Decimal("120000")
        assert restored.doctor_percent == Decimal("50.00")
        assert restored.minus_beshming == Decimal("5000")

    async def test_restoring_a_live_record_is_rejected(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)
        record = await _make_consultation(seeded_db, actor)

        with pytest.raises(HTTPException) as exc:
            await restore_voided_record(
                seeded_db, actor=actor, obj=record,
            )
        assert exc.value.status_code == 409


@pytest.mark.asyncio
class TestHardDelete:
    async def test_deleting_a_live_record_is_rejected(self, seeded_db: AsyncSession):
        """Destruction must always be two deliberate steps: void, then delete."""
        actor = await _get_superadmin(seeded_db)
        record = await _make_consultation(seeded_db, actor)

        with pytest.raises(HTTPException) as exc:
            await hard_delete_voided_record(
                seeded_db, actor=actor, obj=record,
            )
        assert exc.value.status_code == 409

        assert await seeded_db.get(Consultation, record.id) is not None

    async def test_delete_removes_the_row(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)
        record = await _make_consultation(seeded_db, actor)
        record_id = record.id
        await void_consultation(seeded_db, actor=actor, consultation=record)

        await hard_delete_voided_record(
            seeded_db, actor=actor, obj=record,
        )

        assert await seeded_db.get(Consultation, record_id) is None

    async def test_delete_leaves_no_trace(self, seeded_db: AsyncSession):
        """The record is gone and nothing records that it existed.

        The owner had the audit trail removed entirely, so a permanent delete
        leaves nothing behind anywhere.
        """
        actor = await _get_superadmin(seeded_db)
        record = await _make_consultation(seeded_db, actor)
        record_id = record.id
        await void_consultation(seeded_db, actor=actor, consultation=record)
        await hard_delete_voided_record(
            seeded_db, actor=actor, obj=record,
        )

        assert await seeded_db.get(Consultation, record_id) is None
        items, _ = await list_voided_records(seeded_db, page=1, page_size=100)
        assert record_id not in [r["id"] for r in items if r["resource_type"] == "consultation"]


@pytest.mark.asyncio
class TestSharedAcrossResources:
    async def test_expense_restore_and_delete(self, seeded_db: AsyncSession):
        """The same helpers work on a non-finance resource."""
        actor = await _get_superadmin(seeded_db)
        expense = await create_expense(
            seeded_db,
            actor=actor,
            data=ExpenseCreate(title="Ofis", amount=Decimal("90000"), date=date(2026, 3, 4)),
        )
        expense_id = expense.id

        await void_expense(seeded_db, actor=actor, expense=expense)
        await restore_voided_record(
            seeded_db, actor=actor, obj=expense,
        )
        assert expense.is_voided is False

        items, _ = await list_expenses(
            seeded_db, date_from=None, date_to=None, search=None, page=1, page_size=50
        )
        assert expense_id in [e.id for e in items]

        await void_expense(seeded_db, actor=actor, expense=expense)
        await hard_delete_voided_record(
            seeded_db, actor=actor, obj=expense,
        )

        assert await seeded_db.get(Expense, expense_id) is None


@pytest.mark.asyncio
class TestVoidedRecordsFeed:
    """Audit Jurnali's listing, which spans all seven voidable tables.

    Voided records appear only here — the ordinary record pages keep showing
    live records only, so this feed is the sole route to restoring one.
    """

    async def test_record_pages_never_show_voided_records(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)
        record = await _make_consultation(seeded_db, actor)
        await void_consultation(seeded_db, actor=actor, consultation=record)

        items, _ = await list_consultations(
            seeded_db, actor=actor, doctor_id=None, type_=None,
            date_from=None, date_to=None, page=1, page_size=50,
        )
        assert record.id not in [c.id for c in items]

    async def test_voided_record_appears_in_the_feed(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)
        record = await _make_consultation(seeded_db, actor)
        await void_consultation(seeded_db, actor=actor, consultation=record)

        items, total = await list_voided_records(seeded_db, page=1, page_size=50)

        match = [r for r in items if r["resource_type"] == "consultation" and r["id"] == record.id]
        assert len(match) == 1
        assert match[0]["summary"] == "Ko'rik #7001"
        assert match[0]["amount"] == Decimal("120000")
        assert match[0]["voided_by_name"] == actor.full_name
        assert total >= 1

    async def test_live_records_are_absent_from_the_feed(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)
        record = await _make_consultation(seeded_db, actor)

        items, _ = await list_voided_records(seeded_db, page=1, page_size=50)
        assert record.id not in [r["id"] for r in items if r["resource_type"] == "consultation"]

    async def test_restored_record_leaves_the_feed(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)
        record = await _make_consultation(seeded_db, actor)
        await void_consultation(seeded_db, actor=actor, consultation=record)
        await restore_voided_record(
            seeded_db, actor=actor, obj=record,
        )

        items, _ = await list_voided_records(seeded_db, page=1, page_size=50)
        assert record.id not in [r["id"] for r in items if r["resource_type"] == "consultation"]

    async def test_feed_spans_resource_types_and_filters(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)
        consultation = await _make_consultation(seeded_db, actor)
        await void_consultation(seeded_db, actor=actor, consultation=consultation)

        expense = await create_expense(
            seeded_db,
            actor=actor,
            data=ExpenseCreate(title="Ofis", amount=Decimal("90000"), date=date(2026, 3, 4)),
        )
        await void_expense(seeded_db, actor=actor, expense=expense)

        items, _ = await list_voided_records(seeded_db, page=1, page_size=50)
        assert {"consultation", "expense"} <= {r["resource_type"] for r in items}

        only_expenses, _ = await list_voided_records(
            seeded_db, resource_type="expense", page=1, page_size=50
        )
        assert {r["resource_type"] for r in only_expenses} == {"expense"}
        assert only_expenses[0]["summary"] == "Ofis"
