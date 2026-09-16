from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from app.finance.calculations import money

ZERO = Decimal("0")


def prorate_fixed_salary(fixed_salary: Decimal, date_from: date, date_to: date) -> Decimal:
    """Prorate a monthly fixed_salary over [date_from, date_to] (inclusive).

    Splits the range into one segment per calendar month it touches. Each
    segment is money()-rounded before summing (never rounded once at the
    end), matching this project's per-item-before-aggregation rule for
    receipts.
    """
    if date_from > date_to:
        raise ValueError("date_from cannot be after date_to")

    total = ZERO
    current = date_from

    while current <= date_to:
        days_in_month = monthrange(current.year, current.month)[1]
        month_end = date(current.year, current.month, days_in_month)
        segment_end = min(date_to, month_end)
        segment_days = (segment_end - current).days + 1

        segment_amount = money(fixed_salary / days_in_month * segment_days)
        total += segment_amount

        current = segment_end + timedelta(days=1)

    return total
