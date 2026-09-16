import io
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.calculations import consultation_totals, money, room_totals, surgery_totals
from app.finance.models import Consultation, ConsultationType, Room, Surgery
from app.finance.schemas import (
    ConsultationReport,
    ConsultationTypeSummary,
    DoctorShareReport,
    RoomReport,
    SurgeryReport,
    TotalReport,
)
from app.staff.models import Staff
from app.users.models import User, UserRoleEnum

CLINIC_TZ = ZoneInfo("Asia/Tashkent")
ZERO = Decimal("0")


def get_business_datetime_range(
    date_from: date | None,
    date_to: date | None,
) -> tuple[datetime | None, datetime | None]:
    """Inclusive date range implemented via an exclusive upper bound.

    date >= start AND date < end_exclusive (midnight of the day after
    date_to, in Asia/Tashkent). Do not implement this as `<= 23:59:59`.
    """
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ValueError("date_from cannot be after date_to")

    start = (
        datetime.combine(date_from, time.min, tzinfo=CLINIC_TZ)
        if date_from
        else None
    )

    end_exclusive = (
        datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=CLINIC_TZ)
        if date_to
        else None
    )

    return start, end_exclusive


async def _load_doctor_map(db: AsyncSession, doctor_ids: set[int]) -> dict[int, Staff]:
    if not doctor_ids:
        return {}

    stmt = select(Staff).where(Staff.id.in_(doctor_ids))
    doctors = (await db.execute(stmt)).scalars().all()
    return {doctor.id: doctor for doctor in doctors}


def _doctor_shares(doctor_groups: dict[int, dict], doctor_map: dict[int, Staff]) -> list[DoctorShareReport]:
    shares = []
    for doctor_id, group in doctor_groups.items():
        doctor = doctor_map.get(doctor_id)
        if doctor is None:
            continue
        shares.append(
            DoctorShareReport(
                doctor_id=doctor.id,
                name=f"{doctor.last_name} {doctor.first_name}",
                total_share=money(group["total_share"]),
                count=group["count"],
            )
        )
    return shares


async def build_consultation_report(
    db: AsyncSession,
    *,
    date_from: date | None,
    date_to: date | None,
    actor: User,
) -> ConsultationReport:
    stmt = select(Consultation).where(Consultation.is_voided.is_(False))

    if actor.role == UserRoleEnum.ASSISTANT:
        stmt = stmt.where(Consultation.created_by_id == actor.id)

    start, end = get_business_datetime_range(date_from, date_to)
    if start:
        stmt = stmt.where(Consultation.date >= start)
    if end:
        stmt = stmt.where(Consultation.date < end)

    records = (await db.execute(stmt)).scalars().all()

    korik_total = ZERO
    korik_count = 0
    qaytakorik_total = ZERO
    qaytakorik_count = 0

    total_doctor_share = ZERO
    total_clinic_profit = ZERO
    total_expense = ZERO

    doctor_groups: dict[int, dict] = {}

    for record in records:
        totals = consultation_totals(
            record.amount,
            record.minus_beshming,
            record.doctor_percent,
        )

        if record.type == ConsultationType.KORIK:
            korik_total += record.amount
            korik_count += 1
        elif record.type == ConsultationType.QAYTAKORIK:
            qaytakorik_total += record.amount
            qaytakorik_count += 1

        total_doctor_share += totals["doctor_share"]
        total_clinic_profit += totals["clinic_profit"]
        total_expense += totals["expense"]

        if record.doctor_id is not None:
            group = doctor_groups.setdefault(
                record.doctor_id, {"total_share": ZERO, "count": 0}
            )
            group["total_share"] += totals["doctor_share"]
            group["count"] += 1

    doctor_map = await _load_doctor_map(db, set(doctor_groups))

    return ConsultationReport(
        korik=ConsultationTypeSummary(total=money(korik_total), count=korik_count),
        qayta_korik=ConsultationTypeSummary(
            total=money(qaytakorik_total), count=qaytakorik_count
        ),
        total_income=money(korik_total + qaytakorik_total),
        total_doctor_share=money(total_doctor_share),
        total_clinic_profit=money(total_clinic_profit),
        total_consultation_expense=money(total_expense),
        doctor_shares=_doctor_shares(doctor_groups, doctor_map),
    )


async def build_surgery_report(
    db: AsyncSession,
    *,
    date_from: date | None,
    date_to: date | None,
    actor: User,
) -> SurgeryReport:
    stmt = select(Surgery).where(Surgery.is_voided.is_(False))

    if actor.role == UserRoleEnum.ASSISTANT:
        stmt = stmt.where(Surgery.created_by_id == actor.id)

    start, end = get_business_datetime_range(date_from, date_to)
    if start:
        stmt = stmt.where(Surgery.date >= start)
    if end:
        stmt = stmt.where(Surgery.date < end)

    records = (await db.execute(stmt)).scalars().all()

    total_income = ZERO
    total_doctor_share = ZERO
    total_expense = ZERO
    total_clinic_profit = ZERO

    doctor_groups: dict[int, dict] = {}

    for record in records:
        totals = surgery_totals(
            record.amount,
            record.surgery_expense,
            record.doctor_percent,
        )

        total_income += totals["income"]
        total_doctor_share += totals["doctor_share"]
        total_expense += totals["expense"]
        total_clinic_profit += totals["clinic_profit"]

        if record.doctor_id is not None:
            group = doctor_groups.setdefault(
                record.doctor_id, {"total_share": ZERO, "count": 0}
            )
            group["total_share"] += totals["doctor_share"]
            group["count"] += 1

    doctor_map = await _load_doctor_map(db, set(doctor_groups))

    return SurgeryReport(
        surgery_total_income=money(total_income),
        surgery_total_doctor_share=money(total_doctor_share),
        surgery_total_clinic_profit=money(total_clinic_profit),
        surgery_total_expense=money(total_expense),
        surgery_doctor_shares=_doctor_shares(doctor_groups, doctor_map),
    )


async def build_room_report(
    db: AsyncSession,
    *,
    date_from: date | None,
    date_to: date | None,
    actor: User,
) -> RoomReport:
    stmt = select(Room).where(Room.is_voided.is_(False))

    if actor.role == UserRoleEnum.ASSISTANT:
        stmt = stmt.where(Room.created_by_id == actor.id)

    start, end = get_business_datetime_range(date_from, date_to)
    if start:
        stmt = stmt.where(Room.date >= start)
    if end:
        stmt = stmt.where(Room.date < end)

    records = (await db.execute(stmt)).scalars().all()

    total_income = ZERO
    total_doctor_share = ZERO
    total_clinic_profit = ZERO

    doctor_groups: dict[int, dict] = {}

    for record in records:
        totals = room_totals(record.amount, record.doctor_percent)

        total_income += totals["income"]
        total_doctor_share += totals["doctor_share"]
        total_clinic_profit += totals["clinic_profit"]

        if record.doctor_id is not None:
            group = doctor_groups.setdefault(
                record.doctor_id, {"total_share": ZERO, "count": 0}
            )
            group["total_share"] += totals["doctor_share"]
            group["count"] += 1

    doctor_map = await _load_doctor_map(db, set(doctor_groups))

    return RoomReport(
        room_total_income=money(total_income),
        room_total_doctor_share=money(total_doctor_share),
        room_total_clinic_profit=money(total_clinic_profit),
        room_doctor_shares=_doctor_shares(doctor_groups, doctor_map),
    )


async def build_total_report(
    db: AsyncSession,
    *,
    date_from: date | None,
    date_to: date | None,
    actor: User,
) -> TotalReport:
    # Composed from the three section-report builders above — never
    # re-queries/re-calculates independently, so the dashboard can never
    # drift from its own sections.
    consultation = await build_consultation_report(
        db, date_from=date_from, date_to=date_to, actor=actor
    )
    surgery = await build_surgery_report(
        db, date_from=date_from, date_to=date_to, actor=actor
    )
    room = await build_room_report(
        db, date_from=date_from, date_to=date_to, actor=actor
    )

    return TotalReport(
        consultation_income=consultation.total_income,
        consultation_doctor_share=consultation.total_doctor_share,
        consultation_expense=consultation.total_consultation_expense,
        consultation_clinic_profit=consultation.total_clinic_profit,
        surgery_income=surgery.surgery_total_income,
        surgery_doctor_share=surgery.surgery_total_doctor_share,
        surgery_expense=surgery.surgery_total_expense,
        surgery_clinic_profit=surgery.surgery_total_clinic_profit,
        room_income=room.room_total_income,
        room_doctor_share=room.room_total_doctor_share,
        room_clinic_profit=room.room_total_clinic_profit,
        total_income=money(
            consultation.total_income + surgery.surgery_total_income + room.room_total_income
        ),
        total_doctor_share=money(
            consultation.total_doctor_share
            + surgery.surgery_total_doctor_share
            + room.room_total_doctor_share
        ),
        total_expense=money(
            consultation.total_consultation_expense + surgery.surgery_total_expense
        ),
        total_clinic_profit=money(
            consultation.total_clinic_profit
            + surgery.surgery_total_clinic_profit
            + room.room_total_clinic_profit
        ),
    )


def build_report_workbook(report_type: str, report) -> io.BytesIO:
    """Serialize an already-computed report object into an .xlsx workbook.

    Never recomputes totals — reuses exactly the numbers already produced
    by the build_*_report() functions above.
    """
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = report_type[:31]

    data = report.model_dump()

    def flatten(prefix: str, value, rows: list[tuple[str, str]]):
        if isinstance(value, dict):
            for key, sub_value in value.items():
                flatten(f"{prefix}.{key}" if prefix else key, sub_value, rows)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                flatten(f"{prefix}[{index}]", item, rows)
        else:
            rows.append((prefix, str(value)))

    rows: list[tuple[str, str]] = []
    flatten("", data, rows)

    ws.append(["Field", "Value"])
    for field, value in rows:
        ws.append([field, value])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def report_xlsx_response(report_type: str, report, date_from: date | None, date_to: date | None) -> StreamingResponse:
    buffer = build_report_workbook(report_type, report)
    filename = f"{report_type}_{date_from or 'all'}_{date_to or 'all'}.xlsx"

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
