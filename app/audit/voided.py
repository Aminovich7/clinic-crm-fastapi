"""The voided-record feed behind Audit Jurnali.

Audit Jurnali is the single place where voided records are seen and acted on;
the ordinary record pages show only live records. That means one listing has
to span all seven VoidableMixin tables at once, which is what this module
provides.

Voided records are rare by nature (they are corrections, not routine data), so
the seven queries are merged and paginated in Python rather than through a
SQL UNION over seven differently-shaped tables. Each query is already narrowed
by `is_voided = true`, so the rows pulled into memory are a small fraction of
the tables.
"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.duty.models import DutyEntry
from app.expenses.models import Expense
from app.finance.models import Consultation, Room, Surgery
from app.pharmacy.models import PharmacyEntry
from app.salary.models import SalaryPayment
from app.users.models import User

# resource_type -> Uzbek label shown in the "Turi" column.
VOIDED_RESOURCE_LABELS = {
    "consultation": "Ko'rik",
    "surgery": "Operatsiya",
    "room": "Xona",
    "duty_entry": "Navbatchilik",
    "expense": "Xarajat",
    "pharmacy_entry": "Dorixona",
    "salary_payment": "Oylik to'lovi",
}


def _receipt_label(prefix: str, number) -> str:
    return f"{prefix} #{number}" if number is not None else prefix


def _describe(resource_type: str, row) -> tuple[str, object, Decimal | None]:
    """(summary, business date, amount) for one voided row.

    Each table names its date and amount differently, so the shapes are
    normalised here rather than in the template.
    """
    if resource_type == "consultation":
        kind = "Qayta ko'rik" if row.type.value == "qaytakorik" else "Ko'rik"
        return _receipt_label(kind, row.receipt_number), row.date, row.amount
    if resource_type == "surgery":
        return _receipt_label("Operatsiya", row.receipt_number), row.date, row.amount
    if resource_type == "room":
        return _receipt_label("Xona", row.receipt_number), row.date, row.amount
    if resource_type == "duty_entry":
        return "Navbatchilik", row.date, row.amount
    if resource_type == "expense":
        return row.title, row.date, row.amount
    if resource_type == "pharmacy_entry":
        summary = row.comment or "Dorixona yozuvi"
        # A pharmacy entry may record either side of the ledger.
        amount = row.amount_paid if row.amount_paid is not None else row.medicine_cost
        return summary, row.date, amount
    if resource_type == "salary_payment":
        kind = "Avans" if row.payment_type.value == "avans" else "To'liq oylik"
        return kind, row.paid_at, row.amount
    return resource_type, None, None


_MODELS = [
    ("consultation", Consultation),
    ("surgery", Surgery),
    ("room", Room),
    ("duty_entry", DutyEntry),
    ("expense", Expense),
    ("pharmacy_entry", PharmacyEntry),
    ("salary_payment", SalaryPayment),
]


async def list_voided_records(
    db: AsyncSession,
    *,
    resource_type: str | None = None,
    page: int,
    page_size: int,
) -> tuple[list[dict], int]:
    wanted = [
        (name, model)
        for name, model in _MODELS
        if resource_type is None or name == resource_type
    ]

    # One lookup for every user who voided something, so the listing can name
    # them instead of printing a UUID.
    voider_names: dict = {}
    rows: list[dict] = []

    for name, model in wanted:
        stmt = select(model).where(model.is_voided.is_(True))
        for row in (await db.execute(stmt)).scalars().all():
            summary, when, amount = _describe(name, row)
            rows.append(
                {
                    "resource_type": name,
                    "resource_label": VOIDED_RESOURCE_LABELS[name],
                    "id": row.id,
                    "summary": summary,
                    "date": when,
                    "amount": amount,
                    "voided_at": row.voided_at,
                    "voided_by_id": row.voided_by_id,
                    "voided_by_name": None,
                }
            )
            if row.voided_by_id is not None:
                voider_names[row.voided_by_id] = None

    if voider_names:
        stmt = select(User.id, User.full_name).where(User.id.in_(list(voider_names)))
        voider_names = dict((await db.execute(stmt)).all())
        for row in rows:
            row["voided_by_name"] = voider_names.get(row["voided_by_id"])

    # Most recently voided first. voided_at is set whenever is_voided is, but
    # sort defensively so a NULL from older data can't raise.
    rows.sort(key=lambda r: (r["voided_at"] is not None, r["voided_at"]), reverse=True)

    total = len(rows)
    start = (page - 1) * page_size
    return rows[start : start + page_size], total
