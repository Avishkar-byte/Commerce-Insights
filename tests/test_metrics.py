"""Tests for dashboard.lib.metrics.

Covers every formula in plan section 3.6, including the rule that a zero
denominator returns None rather than 0 so the pages can render "n/a".
"""

from __future__ import annotations

import pandas as pd
import pytest

from lib import metrics


@pytest.fixture
def frame() -> pd.DataFrame:
    """Two rows of order metrics that must be summed before dividing.

    Returns:
        A frame shaped like the order_metrics collection.
    """
    return pd.DataFrame(
        [
            {
                "orders": 10,
                "gmv": 1000.0,
                "freight": 100.0,
                "delivered_orders": 8,
                "late_orders": 2,
                "sum_delivery_days": 80,
                "sum_late_days": 10,
                "reviewed_orders": 8,
                "sum_review_score": 32,
                "low_review_orders": 2,
                "five_star_orders": 4,
                "canceled_orders": 1,
            },
            {
                "orders": 10,
                "gmv": 500.0,
                "freight": 50.0,
                "delivered_orders": 2,
                "late_orders": 0,
                "sum_delivery_days": 10,
                "sum_late_days": 0,
                "reviewed_orders": 2,
                "sum_review_score": 10,
                "low_review_orders": 0,
                "five_star_orders": 2,
                "canceled_orders": 0,
            },
        ]
    )


@pytest.fixture
def empty() -> pd.DataFrame:
    """Build an empty frame with the same columns, as an empty selection gives.

    Returns:
        A zero-row frame.
    """
    return pd.DataFrame(
        columns=[
            "orders",
            "gmv",
            "freight",
            "delivered_orders",
            "late_orders",
            "sum_delivery_days",
            "sum_late_days",
            "reviewed_orders",
            "sum_review_score",
            "low_review_orders",
            "five_star_orders",
        ]
    )


# ------------------------------------------------------------ safe_divide --


def test_safe_divide_normal():
    assert metrics.safe_divide(10, 4) == 2.5


@pytest.mark.parametrize(
    "numerator,denominator",
    [(10, 0), (10, None), (None, 10), (None, None), (0, 0)],
)
def test_safe_divide_returns_none_not_zero(numerator, denominator):
    assert metrics.safe_divide(numerator, denominator) is None


# ----------------------------------------------------------------- totals --


def test_totals_sum_across_rows(frame):
    assert metrics.gmv(frame) == 1500.0
    assert metrics.orders(frame) == 20


def test_total_of_missing_column_is_zero(frame):
    assert metrics.total(frame, "not_a_column") == 0.0


# ------------------------------------------------------------------ sales --


def test_average_order_value(frame):
    assert metrics.average_order_value(frame) == 75.0


def test_freight_share(frame):
    # 150 freight over 1650 total spend.
    assert metrics.freight_share(frame) == pytest.approx(150 / 1650)


# --------------------------------------------------------------- delivery --


def test_late_rate_divides_summed_fields(frame):
    # 2 late over 10 delivered, not the mean of the per-row rates.
    assert metrics.late_rate(frame) == pytest.approx(0.2)


def test_avg_delivery_days(frame):
    assert metrics.avg_delivery_days(frame) == pytest.approx(9.0)


def test_avg_days_late_uses_late_orders_as_denominator(frame):
    assert metrics.avg_days_late(frame) == pytest.approx(5.0)


# ----------------------------------------------------------- satisfaction --


def test_avg_review(frame):
    assert metrics.avg_review(frame) == pytest.approx(4.2)


def test_low_review_share(frame):
    assert metrics.low_review_share(frame) == pytest.approx(0.2)


def test_five_star_share(frame):
    assert metrics.five_star_share(frame) == pytest.approx(0.6)


# ------------------------------------------------- empty selection is n/a --


@pytest.mark.parametrize(
    "func",
    [
        metrics.average_order_value,
        metrics.freight_share,
        metrics.late_rate,
        metrics.avg_delivery_days,
        metrics.avg_days_late,
        metrics.avg_review,
        metrics.low_review_share,
        metrics.five_star_share,
    ],
)
def test_every_ratio_is_none_on_an_empty_selection(empty, func):
    assert func(empty) is None


def test_totals_are_zero_not_none_on_an_empty_selection(empty):
    assert metrics.gmv(empty) == 0.0
    assert metrics.orders(empty) == 0.0


# ---------------------------------------------------------- payment mix --


def test_payment_mix_shares_sum_to_one():
    df = pd.DataFrame(
        [
            {"payment_type": "credit_card", "payment_value": 750.0},
            {"payment_type": "boleto", "payment_value": 250.0},
        ]
    )
    out = metrics.payment_mix(df)

    assert out.iloc[0]["payment_type"] == "credit_card", "sorted by value"
    assert out["share"].sum() == pytest.approx(1.0)
    assert out.iloc[0]["share"] == pytest.approx(0.75)


def test_payment_mix_of_empty_frame():
    out = metrics.payment_mix(pd.DataFrame())

    assert out.empty
    assert list(out.columns) == ["payment_type", "payment_value", "share"]


# ------------------------------------------------------------ formatting --


def test_none_formats_as_na():
    assert metrics.format_percent(None) == "n/a"
    assert metrics.format_currency(None) == "n/a"
    assert metrics.format_number(None) == "n/a"


def test_currency_abbreviations():
    assert metrics.format_currency(13_200_000) == "R$ 13.20M"
    assert metrics.format_currency(5_300) == "R$ 5K"
    assert metrics.format_currency(137) == "R$ 137"


def test_percent_and_number_formatting():
    assert metrics.format_percent(0.1472) == "14.7%"
    assert metrics.format_number(96211) == "96,211"
