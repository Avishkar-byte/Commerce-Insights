"""Metric formulas from plan section 3.6, as pure pandas functions.

This module imports no streamlit so the tests can exercise it directly. Every
ratio is computed from summed fields; stored averages are never averaged
again. A zero denominator returns None, which the pages render as "n/a".
"""

from __future__ import annotations

import math

import pandas as pd

#: Shown wherever a ratio has no denominator to divide by.
NA = "n/a"


def safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    """Divide two numbers, returning None when the result is undefined.

    Args:
        numerator: The dividend.
        denominator: The divisor.

    Returns:
        The quotient, or None when the denominator is zero, missing or NaN.
    """
    if numerator is None or denominator is None:
        return None
    try:
        num = float(numerator)
        den = float(denominator)
    except (TypeError, ValueError):
        return None
    if den == 0 or math.isnan(den) or math.isnan(num):
        return None
    return num / den


def total(df: pd.DataFrame, column: str) -> float:
    """Sum one column of a frame, tolerating an empty or missing column.

    Args:
        df: Source frame.
        column: Column to sum.

    Returns:
        The column total, or 0.0 when the frame is empty or lacks the column.
    """
    if df is None or df.empty or column not in df.columns:
        return 0.0
    value = pd.to_numeric(df[column], errors="coerce").sum()
    return 0.0 if pd.isna(value) else float(value)


# ------------------------------------------------------------------- sales --


def gmv(df: pd.DataFrame) -> float:
    """Gross merchandise value: item prices, excluding freight.

    Args:
        df: Frame with a gmv column.

    Returns:
        Total GMV.
    """
    return total(df, "gmv")


def orders(df: pd.DataFrame) -> float:
    """Total order count.

    Args:
        df: Frame with an orders column.

    Returns:
        Total orders.
    """
    return total(df, "orders")


def average_order_value(df: pd.DataFrame) -> float | None:
    """Average value of an order.

    Args:
        df: Frame with gmv and orders columns.

    Returns:
        GMV divided by orders, or None when there are no orders.
    """
    return safe_divide(total(df, "gmv"), total(df, "orders"))


def freight_share(df: pd.DataFrame) -> float | None:
    """Share of total spend that went on freight.

    Args:
        df: Frame with gmv and freight columns.

    Returns:
        Freight over GMV plus freight, or None when both are zero.
    """
    return safe_divide(total(df, "freight"), total(df, "gmv") + total(df, "freight"))


# ---------------------------------------------------------------- delivery --


def late_rate(df: pd.DataFrame) -> float | None:
    """Share of delivered orders that arrived after the estimate.

    Args:
        df: Frame with late_orders and delivered_orders columns.

    Returns:
        The late rate, or None when nothing was delivered.
    """
    return safe_divide(total(df, "late_orders"), total(df, "delivered_orders"))


def avg_delivery_days(df: pd.DataFrame) -> float | None:
    """Mean days from purchase to delivery.

    Args:
        df: Frame with sum_delivery_days and delivered_orders columns.

    Returns:
        Average delivery days, or None when nothing was delivered.
    """
    return safe_divide(total(df, "sum_delivery_days"), total(df, "delivered_orders"))


def avg_days_late(df: pd.DataFrame) -> float | None:
    """Mean lateness across late orders only.

    Args:
        df: Frame with sum_late_days and late_orders columns.

    Returns:
        Average days late, or None when no order was late.
    """
    return safe_divide(total(df, "sum_late_days"), total(df, "late_orders"))


# ------------------------------------------------------------ satisfaction --


def avg_review(df: pd.DataFrame) -> float | None:
    """Mean review score.

    Args:
        df: Frame with sum_review_score and reviewed_orders columns.

    Returns:
        Average score, or None when nothing was reviewed.
    """
    return safe_divide(total(df, "sum_review_score"), total(df, "reviewed_orders"))


def low_review_share(df: pd.DataFrame) -> float | None:
    """Share of reviews scoring 1 or 2 stars.

    Args:
        df: Frame with low_review_orders and reviewed_orders columns.

    Returns:
        The low-review share, or None when nothing was reviewed.
    """
    return safe_divide(total(df, "low_review_orders"), total(df, "reviewed_orders"))


def five_star_share(df: pd.DataFrame) -> float | None:
    """Share of reviews scoring 5 stars.

    Args:
        df: Frame with five_star_orders and reviewed_orders columns.

    Returns:
        The five-star share, or None when nothing was reviewed.
    """
    return safe_divide(total(df, "five_star_orders"), total(df, "reviewed_orders"))


def payment_mix(df: pd.DataFrame) -> pd.DataFrame:
    """Share of payment value per payment type.

    Args:
        df: Frame with payment_type and payment_value columns.

    Returns:
        The frame sorted by value, with an added share column. Shares are NaN
        when the total value is zero.
    """
    if df is None or df.empty or "payment_value" not in df.columns:
        return pd.DataFrame(columns=["payment_type", "payment_value", "share"])

    out = df.copy()
    grand_total = total(out, "payment_value")
    out["share"] = out["payment_value"] / grand_total if grand_total else float("nan")
    return out.sort_values("payment_value", ascending=False).reset_index(drop=True)


# -------------------------------------------------------------- formatting --


def format_currency(value: float | None, decimals: int = 0) -> str:
    """Format a value as Brazilian reais, abbreviating millions and thousands.

    Args:
        value: The amount, or None.
        decimals: Decimal places for values under one thousand.

    Returns:
        A display string, or "n/a" when the value is None.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return NA
    if abs(value) >= 1_000_000:
        return f"R$ {value / 1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"R$ {value / 1_000:.0f}K"
    return f"R$ {value:,.{decimals}f}"


def format_percent(value: float | None, decimals: int = 1) -> str:
    """Format a 0-to-1 ratio as a percentage.

    Args:
        value: The ratio, or None.
        decimals: Decimal places to show.

    Returns:
        A display string, or "n/a" when the value is None.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return NA
    return f"{value * 100:.{decimals}f}%"


def format_number(value: float | None, decimals: int = 0) -> str:
    """Format a count or measure with thousands separators.

    Args:
        value: The number, or None.
        decimals: Decimal places to show.

    Returns:
        A display string, or "n/a" when the value is None.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return NA
    return f"{value:,.{decimals}f}"
