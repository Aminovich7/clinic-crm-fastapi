from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.pharmacy.schemas import PharmacyEntryCreate
from app.pharmacy.service import (
    build_pharmacy_balance,
    create_pharmacy_entry,
    void_pharmacy_entry,
)
from app.users.models import User, UserRoleEnum


async def _get_superadmin(db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.role == UserRoleEnum.SUPERADMIN))
    return result.scalars().first()


@pytest.mark.asyncio
class TestPharmacyEntries:
    async def test_create_and_void(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)

        entry = await create_pharmacy_entry(
            seeded_db, actor=actor, data=PharmacyEntryCreate(medicine_cost=500)
        )
        assert entry.medicine_cost == 500
        assert entry.amount_paid is None

        voided = await void_pharmacy_entry(seeded_db, actor=actor, pharmacy_entry=entry)
        assert voided.is_voided is True

    def test_not_both_null_rejected(self):
        with pytest.raises(ValueError):
            PharmacyEntryCreate()

    async def test_balance_positive_when_paid_exceeds_cost(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)

        await create_pharmacy_entry(seeded_db, actor=actor, data=PharmacyEntryCreate(amount_paid=200))
        await create_pharmacy_entry(seeded_db, actor=actor, data=PharmacyEntryCreate(medicine_cost=50))

        summary = await build_pharmacy_balance(seeded_db, date_from=None, date_to=None)
        assert summary.total_paid == Decimal("200")
        assert summary.total_medicine_cost == Decimal("50")
        assert summary.balance == Decimal("150")

    async def test_balance_negative_when_cost_exceeds_paid(self, seeded_db: AsyncSession):
        actor = await _get_superadmin(seeded_db)

        await create_pharmacy_entry(seeded_db, actor=actor, data=PharmacyEntryCreate(medicine_cost=722))
        await create_pharmacy_entry(seeded_db, actor=actor, data=PharmacyEntryCreate(amount_paid=200))

        summary = await build_pharmacy_balance(seeded_db, date_from=None, date_to=None)
        assert summary.balance == Decimal("-522")
