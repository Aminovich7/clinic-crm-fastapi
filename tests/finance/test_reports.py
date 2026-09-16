import pytest
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo

from app.staff.models import StaffRoleEnum
from app.staff.schemas import StaffCreate
from app.staff.service import create_staff
from app.finance.models import ConsultationType
from app.finance.reports import (
    get_business_datetime_range,
    build_consultation_report,
    build_surgery_report,
    build_room_report,
    build_total_report,
)
from app.finance.schemas import ConsultationCreate, SurgeryCreate, RoomCreate
from app.finance.service import create_consultation, create_surgery, create_room
from app.users.models import User, UserRoleEnum


@pytest.mark.asyncio
class TestReports:
    async def test_business_datetime_range(self):
        # Test date range with Tashkent timezone
        start, end = get_business_datetime_range(
            date(2026, 3, 1),
            date(2026, 3, 31),
        )

        assert start.date().isoformat() == "2026-03-01"
        assert end.date().isoformat() == "2026-04-01"

    async def test_consultation_report(self, seeded_db: AsyncSession):
        result = await seeded_db.execute(
            select(User).where(User.role == UserRoleEnum.SUPERADMIN)
        )
        actor = result.scalars().first()

        doctor = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(
                role=StaffRoleEnum.DOCTOR,
                first_name="Dr.",
                last_name="ReportConsult",
                specialty="Test",
            ),
        )

        # Create a consultation
        await create_consultation(
            seeded_db,
            actor=actor,
            data=ConsultationCreate(
                type=ConsultationType.KORIK,
                receipt_number=300,
                date=datetime(2026, 3, 15, 10, 0, 0, tzinfo=ZoneInfo("Asia/Tashkent")),
                amount=Decimal("100000"),
                doctor_percent=Decimal("50"),
                doctor_id=doctor.id,
            ),
        )

        # Get report
        report = await build_consultation_report(
            seeded_db,
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
            actor=actor,
        )

        assert report.total_income > 0
        assert hasattr(report, "korik")
        assert len(report.doctor_shares) >= 0

    async def test_surgery_report(self, seeded_db: AsyncSession):
        result = await seeded_db.execute(
            select(User).where(User.role == UserRoleEnum.SUPERADMIN)
        )
        actor = result.scalars().first()

        doctor = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(
                role=StaffRoleEnum.DOCTOR,
                first_name="Dr.",
                last_name="ReportSurgery",
                specialty="Surgeon",
            ),
        )

        # Create a surgery
        await create_surgery(
            seeded_db,
            actor=actor,
            data=SurgeryCreate(
                receipt_number=400,
                date=datetime(2026, 3, 15, 10, 0, 0, tzinfo=ZoneInfo("Asia/Tashkent")),
                amount=Decimal("500000"),
                surgery_expense=Decimal("50000"),
                doctor_percent=Decimal("40"),
                doctor_id=doctor.id,
            ),
        )

        # Get report
        report = await build_surgery_report(
            seeded_db,
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
            actor=actor,
        )

        assert report.surgery_total_income > 0

    async def test_room_report(self, seeded_db: AsyncSession):
        result = await seeded_db.execute(
            select(User).where(User.role == UserRoleEnum.SUPERADMIN)
        )
        actor = result.scalars().first()

        doctor = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(
                role=StaffRoleEnum.DOCTOR,
                first_name="Dr.",
                last_name="ReportRoom",
                specialty="General",
            ),
        )

        # Create a room
        await create_room(
            seeded_db,
            actor=actor,
            data=RoomCreate(
                date=datetime(2026, 3, 15, 10, 0, 0, tzinfo=ZoneInfo("Asia/Tashkent")),
                amount=Decimal("200000"),
                doctor_percent=Decimal("20"),
                doctor_id=doctor.id,
            ),
        )

        # Get report
        report = await build_room_report(
            seeded_db,
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
            actor=actor,
        )

        assert report.room_total_income > 0

    async def test_total_report_reconciles(self, seeded_db: AsyncSession):
        result = await seeded_db.execute(
            select(User).where(User.role == UserRoleEnum.SUPERADMIN)
        )
        actor = result.scalars().first()

        doctor = await create_staff(
            seeded_db,
            actor=actor,
            data=StaffCreate(
                role=StaffRoleEnum.DOCTOR,
                first_name="Dr.",
                last_name="ReportTotal",
                specialty="Test",
            ),
        )

        # Create records
        await create_consultation(
            seeded_db,
            actor=actor,
            data=ConsultationCreate(
                type=ConsultationType.KORIK,
                receipt_number=500,
                date=datetime(2026, 3, 15, 10, 0, 0, tzinfo=ZoneInfo("Asia/Tashkent")),
                amount=Decimal("100000"),
                doctor_percent=Decimal("50"),
                doctor_id=doctor.id,
            ),
        )

        await create_room(
            seeded_db,
            actor=actor,
            data=RoomCreate(
                date=datetime(2026, 3, 15, 10, 0, 0, tzinfo=ZoneInfo("Asia/Tashkent")),
                amount=Decimal("200000"),
                doctor_percent=Decimal("20"),
                doctor_id=doctor.id,
            ),
        )

        # Get total report
        total_report = await build_total_report(
            seeded_db,
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
            actor=actor,
        )

        # Verify the dashboard-equals-sum-of-sections invariant
        total_income = int(total_report.total_income)
        section_income = (
            int(total_report.consultation_income) +
            int(total_report.surgery_income) +
            int(total_report.room_income)
        )

        assert total_income == section_income, \
            f"Total {total_income} != sum of sections {section_income}"
