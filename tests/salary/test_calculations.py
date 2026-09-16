from datetime import date
from decimal import Decimal

from app.salary.calculations import prorate_fixed_salary


class TestProrateFixedSalary:
    def test_single_month_worked_example(self):
        result = prorate_fixed_salary(Decimal("3000000"), date(2026, 2, 10), date(2026, 2, 20))
        assert result == Decimal("1178571")

    def test_spans_two_months_worked_example(self):
        result = prorate_fixed_salary(Decimal("3000000"), date(2026, 1, 25), date(2026, 2, 5))
        assert result == Decimal("1213133")

    def test_single_day(self):
        result = prorate_fixed_salary(Decimal("2800000"), date(2026, 2, 1), date(2026, 2, 1))
        # 2800000 / 28 = 100000 exactly
        assert result == Decimal("100000")

    def test_full_calendar_month(self):
        result = prorate_fixed_salary(Decimal("2800000"), date(2026, 2, 1), date(2026, 2, 28))
        assert result == Decimal("2800000")

    def test_date_from_after_date_to_raises(self):
        import pytest

        with pytest.raises(ValueError):
            prorate_fixed_salary(Decimal("1000000"), date(2026, 2, 10), date(2026, 2, 1))
