from decimal import Decimal

import pytest

from app.finance.calculations import consultation_totals, room_totals, surgery_totals


class TestConsultationTotals:
    def test_consultation_totals_basic(self):
        result = consultation_totals(
            amount=Decimal("100000"),
            doctor_percent=Decimal("50"),
            minus_beshming=Decimal("5000"),
        )

        assert result["income"] == Decimal("100000")
        assert result["doctor_share"] == Decimal("47500")
        assert result["expense"] == Decimal("5000")
        assert result["clinic_profit"] == Decimal("47500")

    def test_consultation_totals_no_expense(self):
        result = consultation_totals(
            amount=Decimal("100000"),
            doctor_percent=Decimal("50"),
            minus_beshming=Decimal("0"),
        )

        assert result["income"] == Decimal("100000")
        assert result["doctor_share"] == Decimal("50000")
        assert result["expense"] == Decimal("0")
        assert result["clinic_profit"] == Decimal("50000")

    def test_consultation_totals_rounding(self):
        # Test ROUND_HALF_UP behavior: (1000 - 0) * 33 / 100 = 330.00
        result = consultation_totals(
            amount=Decimal("1000"),
            doctor_percent=Decimal("33"),
            minus_beshming=Decimal("0"),
        )

        assert result["doctor_share"] == Decimal("330")
        assert result["clinic_profit"] == Decimal("670")


class TestSurgeryTotals:
    def test_surgery_totals_basic(self):
        result = surgery_totals(
            amount=Decimal("500000"),
            doctor_percent=Decimal("40"),
            surgery_expense=Decimal("50000"),
        )

        assert result["income"] == Decimal("500000")
        assert result["doctor_share"] == Decimal("180000")
        assert result["expense"] == Decimal("50000")
        assert result["clinic_profit"] == Decimal("270000")

    def test_surgery_totals_no_expense(self):
        result = surgery_totals(
            amount=Decimal("500000"),
            doctor_percent=Decimal("40"),
            surgery_expense=Decimal("0"),
        )

        assert result["income"] == Decimal("500000")
        assert result["doctor_share"] == Decimal("200000")
        assert result["expense"] == Decimal("0")
        assert result["clinic_profit"] == Decimal("300000")


class TestRoomTotals:
    def test_room_totals_basic(self):
        result = room_totals(
            amount=Decimal("200000"),
            doctor_percent=Decimal("20"),
        )

        assert result["income"] == Decimal("200000")
        assert result["doctor_share"] == Decimal("40000")
        assert result["expense"] == Decimal("0")
        assert result["clinic_profit"] == Decimal("160000")

    def test_room_totals_high_percent(self):
        result = room_totals(
            amount=Decimal("1000000"),
            doctor_percent=Decimal("50"),
        )

        assert result["income"] == Decimal("1000000")
        assert result["doctor_share"] == Decimal("500000")
        assert result["expense"] == Decimal("0")
        assert result["clinic_profit"] == Decimal("500000")
