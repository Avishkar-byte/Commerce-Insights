"""F2 Delivery performance: where and why deliveries run late.

Answers "Where and why are deliveries late?" with KPIs for late-delivery rate,
average delivery days, and average days late; a Brazil map of late rate by
customer state where states with fewer than 100 delivered orders in the
selection are grey; the monthly late-rate trend; and late rate with average
delivery days by distance bucket. Reads order_metrics and delivery_distance.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import charts, db, filters, metrics, theme, ui

#: Below this many delivered orders a state's late rate is not meaningful.
MIN_DELIVERED = 100

GEOJSON_PATH = Path(__file__).resolve().parent.parent / "assets" / "brazil_states.geojson"


@st.cache_data(ttl=3600, show_spinner=False)
def _load_geojson() -> dict | None:
    """Load the Brazil states GeoJSON if it is present.

    Returns:
        The parsed GeoJSON, or None when the file is missing or unreadable.
    """
    if not GEOJSON_PATH.exists():
        return None
    try:
        with GEOJSON_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def _state_rates(match: dict) -> pd.DataFrame:
    """Compute the late rate per customer state.

    Args:
        match: The active $match document.

    Returns:
        A frame with customer_state, late_rate and a sufficient-data flag.
    """
    data = db.aggregate("order_metrics", match, ["customer_state"])
    if data.empty:
        return data
    data["late_rate"] = data.apply(
        lambda r: metrics.safe_divide(r["late_orders"], r["delivered_orders"]), axis=1
    )
    data["enough"] = data["delivered_orders"] >= MIN_DELIVERED
    return data.sort_values("late_rate", ascending=False)


def _map(data: pd.DataFrame) -> None:
    """Draw the late-rate choropleth, or a ranked list if the GeoJSON is missing.

    Args:
        data: Output of _state_rates.
    """
    shown = data[data["enough"] & data["late_rate"].notna()]
    hidden = data[~data["enough"]]

    with st.container(border=True):
        ui.card_header(
            "Where do late deliveries concentrate?",
            f"Late rate by customer state. States with fewer than {MIN_DELIVERED} delivered "
            "orders in this selection are shown grey.",
            aside=f"{len(shown)} states rated",
        )

        geojson = _load_geojson()
        if geojson is None:
            st.caption("Map unavailable: dashboard/assets/brazil_states.geojson is missing.")
            bars = shown.head(15)
            peak = float(bars["late_rate"].max()) or 1.0
            ui.ranked_bar_list(
                [
                    (r["customer_state"], metrics.format_percent(r["late_rate"]),
                     r["late_rate"] / peak)
                    for _, r in bars.iterrows()
                ]
            )
            return

        figure = go.Figure()
        if not shown.empty:
            figure.add_choropleth(
                geojson=geojson,
                featureidkey="properties.sigla",
                locations=shown["customer_state"],
                z=shown["late_rate"],
                colorscale=[
                    [0.0, theme.DELAY_ON_TIME],
                    [0.35, theme.DELAY_1_3],
                    [0.6, theme.DELAY_4_7],
                    [0.8, theme.DELAY_8_14],
                    [1.0, theme.DELAY_15_PLUS],
                ],
                marker_line_color=theme.SURFACE_LOWEST,
                marker_line_width=0.6,
                colorbar={
                    "title": {"text": "Late rate", "font": {"size": 11, "color": theme.SECONDARY}},
                    "tickformat": ".0%",
                    "thickness": 10,
                    "outlinewidth": 0,
                    "len": 0.8,
                },
                hovertemplate="%{location}: %{z:.1%} late<extra></extra>",
            )
        if not hidden.empty:
            figure.add_choropleth(
                geojson=geojson,
                featureidkey="properties.sigla",
                locations=hidden["customer_state"],
                z=[0] * len(hidden),
                colorscale=[[0, theme.NEUTRAL], [1, theme.NEUTRAL]],
                showscale=False,
                marker_line_color=theme.SURFACE_LOWEST,
                marker_line_width=0.6,
                hovertemplate="%{location}: too few delivered orders<extra></extra>",
            )

        figure.update_geos(fitbounds="locations", visible=False, bgcolor="rgba(0,0,0,0)")
        figure.update_layout(margin={"l": 0, "r": 0, "t": 0, "b": 0})
        charts.show(figure, height=440)

        if not hidden.empty:
            ui.html(
                f"<span style='font-size:12px;color:{theme.SECONDARY}'>Shown grey, under "
                f"{MIN_DELIVERED} delivered orders: {', '.join(sorted(hidden['customer_state']))}"
                "</span>",
            )


def _trend(match: dict) -> None:
    """Draw the monthly late-rate trend.

    Args:
        match: The active $match document.
    """
    with st.container(border=True):
        ui.card_header(
            "Is lateness getting better or worse?",
            "Share of delivered orders that missed the estimated date, by month",
        )
        monthly = db.aggregate("order_metrics", match, ["year_month"])
        if monthly.empty:
            filters.empty_state("this month range")
            return
        monthly = monthly.sort_values("year_month")
        monthly["late_rate"] = monthly.apply(
            lambda r: metrics.safe_divide(r["late_orders"], r["delivered_orders"]), axis=1
        )
        charts.show(
            charts.line(monthly, "year_month", "late_rate", "Late rate", percent=True), 320
        )


def _distance(match: dict) -> None:
    """Draw late rate and delivery days by distance bucket.

    Args:
        match: The active $match document.
    """
    with st.container(border=True):
        ui.card_header(
            "Does distance explain late deliveries?",
            "Late rate and average transit time by seller-to-customer distance",
        )
        data = db.aggregate("delivery_distance", match, ["distance_bucket"])
        if data.empty:
            filters.empty_state("this distance selection")
            return

        data["late_rate"] = data.apply(
            lambda r: metrics.safe_divide(r["late_orders"], r["delivered_orders"]), axis=1
        )
        data["avg_days"] = data.apply(
            lambda r: metrics.safe_divide(r["sum_delivery_days"], r["delivered_orders"]), axis=1
        )
        data["_order"] = data["distance_bucket"].apply(
            lambda b: theme.DISTANCE_ORDER.index(b) if b in theme.DISTANCE_ORDER else 99
        )
        data = data.sort_values("_order")

        figure = go.Figure()
        figure.add_bar(
            x=data["distance_bucket"],
            y=data["late_rate"],
            name="Late rate",
            marker_color=theme.PRIMARY_CONTAINER,
            hovertemplate="%{x}: %{y:.1%} late<extra></extra>",
        )
        figure.add_scatter(
            x=data["distance_bucket"],
            y=data["avg_days"],
            name="Average delivery days",
            mode="lines+markers",
            line={"color": theme.SECONDARY, "width": 2},
            yaxis="y2",
            hovertemplate="%{x}: %{y:.1f} days<extra></extra>",
        )
        figure.update_layout(
            yaxis={"title": "Late rate", "tickformat": ".0%", "rangemode": "tozero"},
            yaxis2={
                "title": "Days",
                "overlaying": "y",
                "side": "right",
                "showgrid": False,
                "rangemode": "tozero",
            },
            hovermode="x unified",
        )
        charts.show(figure, height=340)


def render() -> None:
    """Draw the delivery page."""
    match = filters.render_sidebar()
    ui.page_title(
        "Delivery performance",
        "Where and why orders arrive after the estimated date.",
        eyebrow="Logistics and marketplace metrics / Fulfilment",
    )

    totals = db.aggregate("order_metrics", match)
    if totals.empty or metrics.total(totals, "delivered_orders") == 0:
        filters.empty_state()
        return

    ui.kpi_grid(
        [
            (
                "Late delivery rate",
                metrics.format_percent(metrics.late_rate(totals)),
                f"{metrics.format_number(metrics.total(totals, 'late_orders'))} of "
                f"{metrics.format_number(metrics.total(totals, 'delivered_orders'))} delivered",
            ),
            (
                "Average delivery time",
                f"{metrics.format_number(metrics.avg_delivery_days(totals), 1)} days",
                "Purchase to customer delivery",
            ),
            (
                "Average days late",
                f"{metrics.format_number(metrics.avg_days_late(totals), 1)} days",
                "Late orders only",
            ),
        ]
    )

    _map(_state_rates(match))
    st.write("")
    _trend(match)
    st.write("")
    _distance(match)


render()
