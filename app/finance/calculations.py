from decimal import ROUND_HALF_UP, Decimal

ONE = Decimal("1")
HUNDRED = Decimal("100")
ZERO = Decimal("0")


def money(value: Decimal) -> Decimal:
    return value.quantize(
        ONE, rounding=ROUND_HALF_UP,
    )


def consultation_totals(
    amount: Decimal,
    minus_beshming: Decimal | None,
    doctor_percent: Decimal,
) -> dict[str, Decimal]:
    """Per-receipt totals for one consultation. Not a report aggregate."""

    minus = minus_beshming or ZERO

    doctor_share = money(
        (amount - minus) * doctor_percent / HUNDRED
    )

    clinic_profit = money(
        amount - doctor_share - minus
    )

    return {
        "income": money(amount),
        "doctor_share": doctor_share,
        "expense": money(minus),
        "clinic_profit": clinic_profit,
    }


def surgery_totals(
    amount: Decimal,
    surgery_expense: Decimal | None,
    doctor_percent: Decimal,
) -> dict[str, Decimal]:
    """Per-receipt totals for one surgery. Not a report aggregate."""

    expense = surgery_expense or ZERO

    doctor_share = money(
        (amount - expense) * doctor_percent / HUNDRED
    )

    clinic_profit = money(
        amount - doctor_share - expense
    )

    return {
        "income": money(amount),
        "doctor_share": doctor_share,
        "expense": money(expense),
        "clinic_profit": clinic_profit,
    }


def room_totals(
    amount: Decimal,
    doctor_percent: Decimal,
) -> dict[str, Decimal]:
    """Per-receipt totals for one room record. Rooms have no expense."""

    doctor_share = money(
        amount * doctor_percent / HUNDRED
    )

    clinic_profit = money(
        amount - doctor_share
    )

    return {
        "income": money(amount),
        "doctor_share": doctor_share,
        "expense": ZERO,
        "clinic_profit": clinic_profit,
    }
