"""F4 Seller scorecard: which sellers help or hurt the platform.

Answers "Which sellers help or hurt the platform?" with page filters for seller
state, minimum orders (default 30), and sort metric; a leaderboard with row
selection; and a detail panel comparing one seller with the platform average,
its monthly GMV trend, and its category mix. The global month filter applies to
the monthly trend; lifetime metrics are labelled all-time, and the page states
that the customer state and category filters do not apply here. Reads
seller_scorecard.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import charts, db, filters, metrics, theme, ui

SORT_OPTIONS = {
    "GMV": "gmv",
    "Orders": "orders",
    "Average review": "avg_review",
    "Health score": "health_score",
}

ID_PREFIX = 8


def _page_filters(states: list[str]) -> tuple[str | None, int, str]:
    """Draw the seller-specific filters above the leaderboard.

    Args:
        states: Seller state options.

    Returns:
        A tuple of (seller state or None, minimum orders, sort field).
    """
    columns = st.columns([1, 1, 1])
    state = columns[0].selectbox("Seller state", ["All states", *states], index=0)
    min_orders = columns[1].number_input(
        "Minimum orders", min_value=0, max_value=2000, value=30, step=10
    )
    sort_label = columns[2].selectbox("Sort by", list(SORT_OPTIONS), index=0)
    return (
        None if state == "All states" else state,
        int(min_orders),
        SORT_OPTIONS[sort_label],
    )


def _leaderboard(frame: pd.DataFrame) -> str | None:
    """Draw the seller table and return the selected seller id.

    Args:
        frame: Seller rows from MongoDB.

    Returns:
        The selected seller id, or None when nothing is selected.
    """
    # The stored rates are fractions of 1; the percent column format prints the
    # raw number, so they are scaled here rather than in the scorecard.
    display = pd.DataFrame(
        {
            "Seller UUID": frame["seller_id"].str[:ID_PREFIX],
            "State": frame["seller_state"],
            "Orders": frame["orders"],
            "GMV": frame["gmv"],
            "Avg review": frame["avg_review"],
            "Dispatched late": frame["dispatch_late_rate"] * 100,
            "Cancel rate": frame["cancel_rate"] * 100,
            "Health score": frame["health_score"],
        }
    )

    event = st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        height=420,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "GMV": st.column_config.NumberColumn(format="R$ %.0f"),
            "Avg review": st.column_config.NumberColumn(format="%.2f"),
            "Dispatched late": st.column_config.NumberColumn(format="%.1f%%"),
            "Cancel rate": st.column_config.NumberColumn(format="%.1f%%"),
            "Health score": st.column_config.ProgressColumn(
                format="%.0f", min_value=0, max_value=100
            ),
        },
    )

    rows = event.selection.rows if event and event.selection else []
    if not rows:
        return None
    return str(frame.iloc[rows[0]]["seller_id"])


def _detail_tiles(seller: dict, platform: dict) -> None:
    """Draw the seller's headline metrics against the platform average.

    Args:
        seller: The seller document.
        platform: Platform-average metrics.
    """
    def fmt(value: float | None, kind: str) -> str:
        if value is None:
            return "n/a"
        if kind == "money":
            return metrics.format_currency(value)
        if kind == "percent":
            return metrics.format_percent(value)
        if kind == "score":
            return f"{value:.1f}"
        if kind == "points":
            return f"{value:.0f}"
        return metrics.format_number(value)

    tiles = [
        ("Orders", seller.get("orders"), None, "count", "All-time completed", True),
        ("GMV", seller.get("gmv"), None, "money", "Item prices, all-time", True),
        (
            "Avg review",
            seller.get("avg_review"),
            platform.get("avg_review"),
            "score",
            None,
            True,
        ),
        (
            "Dispatched late",
            seller.get("dispatch_late_rate"),
            platform.get("dispatch_late_rate"),
            "percent",
            None,
            False,
        ),
        (
            "Health score",
            seller.get("health_score"),
            platform.get("health_score"),
            "points",
            None,
            True,
        ),
    ]

    cells = ""
    for label, value, average, kind, static_note, higher_better in tiles:
        if average is not None and value is not None:
            good = (value >= average) == higher_better
            colour = theme.DELAY_ON_TIME if good else theme.DELAY_8_14
            note = (
                f"Platform {fmt(average, kind)} "
                f"<span style='color:{colour}'>"
                f"({'above' if value >= average else 'below'})</span>"
            )
        else:
            note = static_note or "No platform comparison"
        cells += f"""
        <div style="display:flex;flex-direction:column;gap:6px;padding:16px;border-radius:8px;
                    background:{theme.SURFACE_LOW}">
          <span style="font-size:12px;font-weight:500;color:{theme.SECONDARY}">{label}</span>
          <span style="font-size:24px;line-height:32px;font-weight:600;
                       color:{theme.ON_SURFACE};font-variant-numeric:tabular-nums">
            {fmt(value, kind)}</span>
          <span style="font-size:12px;color:{theme.SECONDARY}">{note}</span>
        </div>
        """

    ui.html(
        f"""<div style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));
                        gap:16px;margin-bottom:1.5rem">{cells}</div>"""
    )


def _detail(seller_id: str, match: dict) -> None:
    """Draw the detail panel for one seller.

    Args:
        seller_id: The selected seller id.
        match: The global $match, used only for its month range.
    """
    seller = db.seller_detail(seller_id)
    if not seller:
        st.info("That seller is no longer in the data. Pick another row.")
        return

    ui.page_title(
        f"Seller {seller_id[:ID_PREFIX]}, {seller.get('seller_city', 'unknown')} "
        f"({seller.get('seller_state', '??')})",
        f"{metrics.format_number(seller.get('orders', 0))} orders and "
        f"{metrics.format_currency(seller.get('gmv', 0))} GMV, all-time.",
    )

    _detail_tiles(seller, db.seller_platform_average())

    window = match.get("year_month", {})
    start, end = window.get("$gte", "0000-00"), window.get("$lte", "9999-99")

    left, right = st.columns(2)

    with left, st.container(border=True):
        ui.card_header(
            "Monthly sales for this seller",
            "Gross GMV progression",
            aside="Selected months",
        )
        monthly = pd.DataFrame(seller.get("monthly", []))
        if monthly.empty:
            st.info("This seller has no monthly history.")
        else:
            monthly = monthly[
                (monthly["year_month"] >= start) & (monthly["year_month"] <= end)
            ].sort_values("year_month")
            if monthly.empty:
                st.info("No activity in the selected months. Widen the month range.")
            else:
                charts.show(charts.line(monthly, "year_month", "gmv", "GMV"), 300)

    with right, st.container(border=True):
        ui.card_header(
            "What does this seller sell?",
            "Breakdown of revenue by catalogue segment",
            aside="Top 3 clusters",
        )
        categories = pd.DataFrame(seller.get("top_categories", []))
        if categories.empty:
            st.info("No category breakdown for this seller.")
        else:
            total = float(categories["gmv"].sum()) or 1.0
            peak = float(categories["gmv"].max()) or 1.0
            ui.ranked_bar_list(
                [
                    (
                        str(r["category"]).replace("_", " ").capitalize(),
                        f"{metrics.format_currency(r['gmv'])} ({r['gmv'] / total * 100:.1f}%)",
                        r["gmv"] / peak,
                    )
                    for _, r in categories.iterrows()
                ]
            )


def render() -> None:
    """Draw the sellers page."""
    match = filters.render_sidebar()
    ui.notice(
        "Customer state and category filters do not apply here. Seller figures are "
        "all-time unless noted; the month filter applies only to the monthly trend."
    )
    ui.page_title(
        "Seller scorecard",
        "How each seller performs on reviews, dispatch speed and cancellations.",
        eyebrow="Logistics and marketplace metrics / Merchant operations",
    )

    seller_states = sorted(
        {s for s in db.get_meta().get("filters", {}).get("customer_states", []) if s}
    )
    state, min_orders, sort_by = _page_filters(seller_states)
    frame = db.sellers(seller_state=state, min_orders=min_orders, sort_by=sort_by)

    if frame.empty:
        st.info(
            f"No seller has at least {min_orders} orders in this selection. "
            "Lower the minimum orders, or choose another state."
        )
        return

    scope = "in all states" if state is None else f"in {state}"
    ui.section_label(
        "Seller leaderboard",
        f"{len(frame):,} merchants {scope} with at least {min_orders} all-time orders",
    )
    selected = _leaderboard(frame)

    st.write("")
    if selected:
        _detail(selected, match)
    else:
        st.info("Select a seller in the table above to see its detail panel.")


render()
