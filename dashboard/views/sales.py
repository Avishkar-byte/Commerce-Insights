"""F1 Sales overview: how the business is doing.

Answers "How is the business doing?" with KPIs for GMV, orders, average order
value, and freight share; monthly GMV and orders as a combined bar and line;
the top 10 categories by GMV; the payment mix by payment type; and the top 10
customer states by GMV. Reads order_metrics and payment_mix.
"""

from __future__ import annotations

import streamlit as st

from lib import charts, db, filters, metrics, theme, ui

TOP_N = 10

STATE_NAMES = {
    "SP": "São Paulo",
    "RJ": "Rio de Janeiro",
    "MG": "Minas Gerais",
    "RS": "Rio Grande do Sul",
    "PR": "Paraná",
    "SC": "Santa Catarina",
    "BA": "Bahia",
    "DF": "Distrito Federal",
    "GO": "Goiás",
    "ES": "Espírito Santo",
}


def _pretty(name: str) -> str:
    """Turn a snake_case category into display text.

    Args:
        name: Raw category name.

    Returns:
        A capitalised, spaced label.
    """
    return str(name).replace("_", " ").capitalize()


def _monthly(match: dict) -> None:
    """Draw monthly GMV as bars with the order count as a line.

    Args:
        match: The active $match document.
    """
    with st.container(border=True):
        ui.card_header(
            "How did sales grow month by month?",
            "Temporal distribution of gross revenue and fulfilled order volume",
        )
        monthly = db.aggregate("order_metrics", match, ["year_month"])
        if monthly.empty:
            filters.empty_state("this month range")
            return
        monthly = monthly.sort_values("year_month")
        charts.show(
            charts.combo_bar_line(monthly, "year_month", "gmv", "orders", "GMV (R$)", "Orders"),
            height=360,
        )


def _categories(match: dict) -> None:
    """Draw the top categories by GMV.

    Args:
        match: The active $match document.
    """
    with st.container(border=True):
        ui.card_header(
            "Which categories bring in the most revenue?",
            f"Top {TOP_N} categories ranked by item gross sales volume",
        )
        data = db.aggregate("order_metrics", match, ["primary_category"])
        if data.empty:
            filters.empty_state("these categories")
            return
        data = data[data["primary_category"] != db.PLACEHOLDER_CATEGORY]
        top = data.sort_values("gmv", ascending=False).head(TOP_N)
        peak = float(top["gmv"].max()) or 1.0
        ui.ranked_bar_list(
            [
                (_pretty(r["primary_category"]), metrics.format_currency(r["gmv"]), r["gmv"] / peak)
                for _, r in top.iterrows()
            ]
        )


def _payments(match: dict) -> None:
    """Draw the payment mix by payment type.

    Args:
        match: The active $match document.
    """
    with st.container(border=True):
        ui.card_header(
            "How do customers pay?",
            "Breakdown of gross transaction value across payment methods",
        )
        data = db.aggregate("payment_mix", match, ["payment_type"])
        if data.empty:
            filters.empty_state("this payment selection")
            return

        mix = metrics.payment_mix(data)
        for _, row in mix.iterrows():
            ui.html(
                f"""
                <div style="display:flex;justify-content:space-between;align-items:center;
                            border:1px solid {theme.OUTLINE_VARIANT};border-radius:4px;
                            padding:10px 12px;margin-bottom:8px">
                  <span style="font-size:14px;color:{theme.ON_SURFACE}">
                    {_pretty(row["payment_type"])}</span>
                  <span>
                    <strong style="font-size:16px;color:{theme.ON_SURFACE};
                                   font-variant-numeric:tabular-nums">
                      {metrics.format_percent(row["share"])}</strong>
                    <span style="font-size:12px;color:{theme.SECONDARY};margin-left:8px">
                      {metrics.format_currency(row["payment_value"])}</span>
                  </span>
                </div>
                """
            )
        ui.html(
            f"<span style='font-size:12px;color:{theme.SECONDARY}'>"
            "The payment type is the one covering most of each order's value.</span>",
        )


def _states(match: dict) -> None:
    """Draw the top customer states by GMV.

    Args:
        match: The active $match document.
    """
    with st.container(border=True):
        ui.card_header(
            "Which states spend the most?",
            f"Geographic concentration of revenue across the top {TOP_N} states",
        )
        data = db.aggregate("order_metrics", match, ["customer_state"])
        if data.empty:
            filters.empty_state("these states")
            return

        grand_total = metrics.gmv(data)
        top = data.sort_values("gmv", ascending=False).head(TOP_N)
        peak = float(top["gmv"].max()) or 1.0
        rows = []
        for _, r in top.iterrows():
            state = r["customer_state"]
            label = f"{state}  {STATE_NAMES.get(state, '')}".strip()
            share = f" ({r['gmv'] / grand_total * 100:.1f}%)" if grand_total else ""
            rows.append((label, metrics.format_currency(r["gmv"]) + share, r["gmv"] / peak))
        ui.ranked_bar_list(rows)


def render() -> None:
    """Draw the sales page."""
    match = filters.render_sidebar()
    ui.page_title(
        "Sales overview",
        "Revenue and orders for the selected period.",
        eyebrow="Logistics and marketplace metrics / Commercial",
    )

    totals = db.aggregate("order_metrics", match)
    if totals.empty or metrics.orders(totals) == 0:
        filters.empty_state()
        return

    states = db.aggregate("order_metrics", match, ["customer_state"])
    ui.kpi_grid(
        [
            (
                "Gross merchandise volume",
                metrics.format_currency(metrics.gmv(totals)),
                "Item prices, excluding freight",
            ),
            (
                "Orders",
                metrics.format_number(metrics.orders(totals)),
                f"Across {len(states)} Brazilian states",
            ),
            (
                "Average order value",
                metrics.format_currency(metrics.average_order_value(totals)),
                "Net of shipping charges",
            ),
            (
                "Freight share of total",
                metrics.format_percent(metrics.freight_share(totals)),
                f"{metrics.format_currency(metrics.total(totals, 'freight'))} logistics fees",
            ),
        ]
    )

    _monthly(match)
    st.write("")

    left, right = st.columns(2)
    with left:
        _categories(match)
    with right:
        _payments(match)

    st.write("")
    _states(match)


render()
