"""F3 Customer satisfaction: what drives bad reviews.

Answers "What drives bad reviews?" with KPIs for average review score and the
shares of 1-2 star and 5 star reviews; the key chart of average review score by
delay bucket; a 100% stacked bar of the score distribution per delay bucket;
and the 10 lowest-rated categories with at least 200 reviews. Delay buckets
always appear in the order On time, 1-3, 4-7, 8-14, 15+ days late, Not
delivered. Reads order_metrics and review_by_delay.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import charts, db, filters, metrics, theme, ui

#: A category needs at least this many reviews before it can be ranked.
MIN_REVIEWS = 200

SCORE_LABELS = {
    "score_1": "1 star",
    "score_2": "2 stars",
    "score_3": "3 stars",
    "score_4": "4 stars",
    "score_5": "5 stars",
}

#: Short descriptions under each bar, as in the reference screen.
BUCKET_NOTES = {
    "On time": "Within promised window",
    "1–3 days late": "Minor friction",
    "4–7 days late": "Steep decline",
    "8–14 days late": "Severe defect",
    "15+ days late": "Reputational loss",
    "Not delivered": "Pending or lost",
}


def _by_delay(match: dict) -> pd.DataFrame:
    """Read review counts per delay bucket, in the canonical order.

    Args:
        match: The active $match document.

    Returns:
        One row per delay bucket that has reviews.
    """
    data = db.aggregate("review_by_delay", match, ["delay_bucket"])
    if data.empty:
        return data

    data["_order"] = data["delay_bucket"].apply(
        lambda b: theme.DELAY_ORDER.index(b) if b in theme.DELAY_ORDER else 99
    )
    data = data.sort_values("_order")
    data["avg_review"] = data.apply(
        lambda r: metrics.safe_divide(r["sum_review_score"], r["reviewed_orders"]), axis=1
    )
    return data[data["reviewed_orders"] > 0]


def _key_chart(data: pd.DataFrame, total_reviews: float) -> None:
    """Draw average review score by delay bucket.

    Args:
        data: Output of _by_delay.
        total_reviews: Reviews in the whole selection.
    """
    with st.container(border=True):
        drop = data["avg_review"].max() - data["avg_review"].min()
        ui.card_header(
            "Review scores drop sharply once an order is late.",
            "Mean review score measured against the promised delivery date",
            aside=(
                f"Sample {metrics.format_number(total_reviews)} reviews "
                f"· spread {drop:.1f} stars"
            ),
        )

        labels = [
            f"{bucket}<br><span style='font-size:11px'>{BUCKET_NOTES.get(bucket, '')}</span>"
            for bucket in data["delay_bucket"]
        ]
        figure = go.Figure(
            go.Bar(
                x=labels,
                y=data["avg_review"],
                marker_color=theme.delay_colors(list(data["delay_bucket"])),
                text=[f"{v:.1f}" for v in data["avg_review"]],
                textposition="outside",
                textfont={"size": 15, "color": theme.ON_SURFACE},
                hovertemplate="%{y:.2f} stars<extra></extra>",
            )
        )
        figure.update_layout(
            yaxis={"range": [0, 5.5], "title": None, "dtick": 1, "ticksuffix": " ★"},
            xaxis={"title": None},
            showlegend=False,
        )
        charts.show(figure, height=380)
        ui.html(
            f"<span style='font-size:12px;color:{theme.SECONDARY}'>"
            "Each bar counts only orders that received a review.</span>",
        )


def _distribution(data: pd.DataFrame) -> None:
    """Draw the 100 percent stacked score distribution per delay bucket.

    Args:
        data: Output of _by_delay.
    """
    with st.container(border=True):
        ui.card_header(
            "How are scores spread in each delay group?",
            "Proportion of star ratings given within each delay bucket",
            aside="100% distribution",
        )
        frame = data.rename(columns=SCORE_LABELS)
        figure = charts.stacked_percent(
            frame, "delay_bucket", list(SCORE_LABELS.values()), theme.SCORE_COLORS
        )
        charts.show(figure, height=360)


def _worst_categories(match: dict) -> None:
    """Draw the lowest-rated categories that clear the review threshold.

    Args:
        match: The active $match document.
    """
    with st.container(border=True):
        ui.card_header(
            "Which categories get the lowest reviews?",
            f"Average score among categories with at least {MIN_REVIEWS} reviews",
            aside="10 lowest",
        )
        data = db.aggregate("order_metrics", match, ["primary_category"])
        if data.empty:
            filters.empty_state("these categories")
            return

        data = data[data["primary_category"] != db.PLACEHOLDER_CATEGORY]
        eligible = data[data["reviewed_orders"] >= MIN_REVIEWS].copy()
        if eligible.empty:
            st.info(
                f"No category reaches {MIN_REVIEWS} reviews in this selection. "
                "Widen the month range or clear the category filter."
            )
            return

        eligible["avg_review"] = eligible.apply(
            lambda r: metrics.safe_divide(r["sum_review_score"], r["reviewed_orders"]), axis=1
        )
        worst = eligible.nsmallest(10, "avg_review")

        def tone(score: float) -> str:
            if score < 3.5:
                return theme.DELAY_8_14
            if score < 3.8:
                return theme.DELAY_4_7
            return theme.DELAY_1_3

        for _, row in worst.iterrows():
            label = str(row["primary_category"]).replace("_", " ").capitalize()
            ui.html(
                f"""
                <div style="display:grid;grid-template-columns:160px 1fr 48px;align-items:center;
                            gap:12px;padding:5px 0">
                  <span style="font-size:13px;color:{theme.ON_SURFACE};overflow:hidden;
                               text-overflow:ellipsis;white-space:nowrap">{label}</span>
                  <div style="background:{theme.SURFACE_LOW};border-radius:3px;height:14px">
                    <div style="width:{row['avg_review'] / 5 * 100:.1f}%;
                                background:{tone(row['avg_review'])};height:14px;
                                border-radius:3px"></div>
                  </div>
                  <span style="font-size:13px;color:{tone(row['avg_review'])};text-align:right;
                               font-weight:600;font-variant-numeric:tabular-nums">
                    {row['avg_review']:.2f}</span>
                </div>
                """
            )
        ui.html(
            f"<span style='font-size:12px;color:{theme.SECONDARY}'>Scale 0.0 to 5.0</span>",
        )


def render() -> None:
    """Draw the satisfaction page."""
    match = filters.render_sidebar()
    ui.page_title(
        "Customer satisfaction",
        "Review scores from 1 to 5 stars, left after delivery.",
        eyebrow="Logistics and marketplace metrics / Post-purchase sentiment",
    )

    totals = db.aggregate("order_metrics", match)
    reviews = metrics.total(totals, "reviewed_orders")
    if totals.empty or reviews == 0:
        filters.empty_state()
        return

    ui.kpi_grid(
        [
            (
                "Average review score",
                f"{metrics.format_number(metrics.avg_review(totals), 2)}",
                f"Out of 5.0 across {metrics.format_number(reviews)} reviews",
            ),
            (
                "1 to 2 star reviews",
                metrics.format_percent(metrics.low_review_share(totals)),
                "Negative sentiment threshold",
            ),
            (
                "5 star reviews",
                metrics.format_percent(metrics.five_star_share(totals)),
                "Maximum satisfaction rating",
            ),
        ]
    )

    by_delay = _by_delay(match)
    if by_delay.empty:
        filters.empty_state()
        return

    _key_chart(by_delay, reviews)
    st.write("")

    left, right = st.columns(2)
    with left:
        _distribution(by_delay)
    with right:
        _worst_categories(match)


render()
