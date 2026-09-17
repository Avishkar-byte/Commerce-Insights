"""Home: one computed headline sentence, not a grid of KPI cards.

The sentence is calculated live from MongoDB for the current selection, and
the page lists what each of the other pages answers plus the data freshness
timestamp from meta.run_at.
"""

from __future__ import annotations

from lib import db, filters, metrics, ui

MODULES = [
    ("Sales", "Commercial", "Revenue, orders, top categories and how customers pay."),
    ("Delivery", "Logistics", "Where and how late orders arrive, by state and distance."),
    (
        "Satisfaction",
        "Customer experience",
        "How delivery delays and categories affect review scores.",
    ),
    ("Sellers", "Merchant ops", "Ranked seller performance with a health score for each seller."),
]

LATE_BUCKETS = ["1–3 days late", "4–7 days late", "8–14 days late", "15+ days late"]


def _headline(match: dict) -> None:
    """Draw the live headline sentence and the three summary tiles.

    Args:
        match: The $match document from the sidebar.
    """
    totals = db.aggregate("order_metrics", match)
    if totals.empty or metrics.orders(totals) == 0:
        filters.empty_state()
        return

    rate = metrics.late_rate(totals)
    by_delay = db.aggregate("review_by_delay", match, group_by=["delay_bucket"])

    on_time_score = late_score = None
    if not by_delay.empty:
        on_time_score = metrics.avg_review(by_delay[by_delay["delay_bucket"] == "On time"])
        late_score = metrics.avg_review(by_delay[by_delay["delay_bucket"].isin(LATE_BUCKETS)])

    sentence = (
        f"Of delivered orders in this selection, {ui.highlight(metrics.format_percent(rate))} "
        "arrived late."
    )
    if late_score is not None and on_time_score is not None:
        stars = ui.highlight(f"{metrics.format_number(late_score, 1)} stars")
        sentence += (
            f" Late orders averaged {stars}, against "
            f"{metrics.format_number(on_time_score, 1)} for on-time orders."
        )

    ui.headline(sentence, "Figures update with the filters on the left.")

    ui.kpi_grid(
        [
            (
                "Delivered orders sampled",
                metrics.format_number(metrics.total(totals, "delivered_orders")),
                f"Of {metrics.format_number(metrics.orders(totals))} orders placed",
            ),
            (
                "Average transit duration",
                f"{metrics.format_number(metrics.avg_delivery_days(totals), 1)} days",
                "Purchase to customer delivery",
            ),
            (
                "Overall satisfaction index",
                f"{metrics.format_number(metrics.avg_review(totals), 2)} / 5.0",
                f"Across {metrics.format_number(metrics.total(totals, 'reviewed_orders'))} reviews",
            ),
        ]
    )


def render() -> None:
    """Draw the home page."""
    match = filters.render_sidebar()
    ui.page_title(
        "Executive overview",
        "Executive summary of Brazilian marketplace order analysis (2016-2018).",
    )

    _headline(match)

    ui.section_label("Operational analysis modules", f"{len(MODULES)} research partitions")
    for name, tag, description in MODULES:
        ui.module_card(name, tag, description)

    counts = db.get_meta().get("source_counts", {})
    ui.about_box(
        "About the data",
        "Olist Brazilian e-commerce public dataset, "
        f"{metrics.format_number(counts.get('orders_fact', 0))} orders and "
        f"{metrics.format_number(counts.get('items_fact', 0))} order items, 2016-2018, "
        "processed with Hadoop HDFS and Apache Spark, served from MongoDB.",
    )


render()
