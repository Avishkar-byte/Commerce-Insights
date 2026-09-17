"""Tests for pipeline.transforms.gold.

Hand-built fixtures check each measure, and a reconciliation test proves that
the sum of gmv in order_metrics equals the sum of price in items_fact, which is
the invariant the whole dashboard depends on.
"""

from __future__ import annotations

from pyspark.sql import Row
from pyspark.sql import functions as F

from pipeline.transforms import gold


def _orders(spark):
    """Build a small order fact covering delivered, late and cancelled orders.

    Args:
        spark: The session fixture.

    Returns:
        A DataFrame shaped like the silver order fact.
    """
    return spark.createDataFrame(
        [
            # On time, 5 stars.
            Row(
                order_id="o1",
                year_month="2017-11",
                customer_state="SP",
                primary_category="toys",
                status="delivered",
                is_delivered=True,
                is_late=False,
                delivery_days=5,
                delay_days=-2,
                delay_bucket="On time",
                distance_bucket="<100",
                gmv=100.0,
                freight=10.0,
                review_score=5,
                payment_total=110.0,
                primary_payment_type="credit_card",
            ),
            # Late by 3 days, 1 star.
            Row(
                order_id="o2",
                year_month="2017-11",
                customer_state="SP",
                primary_category="toys",
                status="delivered",
                is_delivered=True,
                is_late=True,
                delivery_days=15,
                delay_days=3,
                delay_bucket="1–3 days late",
                distance_bucket="<100",
                gmv=50.0,
                freight=5.0,
                review_score=1,
                payment_total=55.0,
                primary_payment_type="boleto",
            ),
            # Cancelled, never delivered, no review.
            Row(
                order_id="o3",
                year_month="2017-11",
                customer_state="SP",
                primary_category="toys",
                status="canceled",
                is_delivered=False,
                is_late=None,
                delivery_days=None,
                delay_days=None,
                delay_bucket="Not delivered",
                distance_bucket="unknown",
                gmv=20.0,
                freight=2.0,
                review_score=None,
                payment_total=22.0,
                primary_payment_type="credit_card",
            ),
        ]
    )


def test_order_metrics_measures(spark):
    row = gold.build_order_metrics(_orders(spark)).collect()[0]

    assert row["orders"] == 3
    assert row["gmv"] == 170.0
    assert row["freight"] == 17.0
    assert row["delivered_orders"] == 2
    assert row["late_orders"] == 1
    assert row["sum_delivery_days"] == 20
    assert row["sum_late_days"] == 3
    assert row["reviewed_orders"] == 2
    assert row["sum_review_score"] == 6
    assert row["low_review_orders"] == 1
    assert row["five_star_orders"] == 1
    assert row["canceled_orders"] == 1


def test_order_metrics_never_stores_an_average(spark):
    columns = set(gold.build_order_metrics(_orders(spark)).columns)

    assert not {c for c in columns if c.startswith("avg") or c.endswith("_rate")}


def test_delivery_distance_only_counts_delivered(spark):
    rows = {r["distance_bucket"]: r for r in gold.build_delivery_distance(_orders(spark)).collect()}

    assert rows["<100"]["delivered_orders"] == 2
    assert rows["<100"]["late_orders"] == 1
    assert rows["<100"]["sum_delivery_days"] == 20
    # The cancelled order lands in its own bucket and counts nothing.
    assert rows["unknown"]["delivered_orders"] == 0
    assert rows["unknown"]["sum_delivery_days"] == 0


def test_review_by_delay_counts_each_score(spark):
    rows = {r["delay_bucket"]: r for r in gold.build_review_by_delay(_orders(spark)).collect()}

    on_time = rows["On time"]
    assert on_time["reviewed_orders"] == 1
    assert on_time["sum_review_score"] == 5
    assert on_time["score_5"] == 1
    assert on_time["score_1"] == 0

    late = rows["1–3 days late"]
    assert late["score_1"] == 1
    assert late["sum_review_score"] == 1

    # Not delivered: present as a bucket, but nothing was reviewed.
    assert rows["Not delivered"]["reviewed_orders"] == 0


def test_payment_mix_totals_by_type(spark):
    rows = {r["payment_type"]: r for r in gold.build_payment_mix(_orders(spark)).collect()}

    assert rows["credit_card"]["payments"] == 2
    assert rows["credit_card"]["payment_value"] == 132.0
    assert rows["boleto"]["payments"] == 1
    assert rows["boleto"]["payment_value"] == 55.0


def test_payment_mix_value_equals_total_payments(spark):
    orders = _orders(spark)
    expected = orders.agg(F.sum("payment_total")).first()[0]
    got = gold.build_payment_mix(orders).agg(F.sum("payment_value")).first()[0]

    assert abs(got - expected) < 0.01


# ------------------------------------------------------------ reconciliation --


def test_order_metrics_gmv_reconciles_with_items(spark):
    """Sum of gmv in order_metrics must equal sum of price in items_fact."""
    orders = spark.createDataFrame(
        [
            Row(
                order_id="o1",
                year_month="2017-11",
                customer_state="SP",
                primary_category="toys",
                status="delivered",
                is_delivered=True,
                is_late=False,
                delivery_days=5,
                delay_days=-1,
                delay_bucket="On time",
                distance_bucket="<100",
                gmv=130.0,
                freight=10.0,
                review_score=4,
                payment_total=140.0,
                primary_payment_type="credit_card",
            ),
            Row(
                order_id="o2",
                year_month="2017-12",
                customer_state="RJ",
                primary_category="books",
                status="delivered",
                is_delivered=True,
                is_late=False,
                delivery_days=4,
                delay_days=-3,
                delay_bucket="On time",
                distance_bucket="100–500",
                gmv=70.0,
                freight=7.0,
                review_score=5,
                payment_total=77.0,
                primary_payment_type="boleto",
            ),
        ]
    )
    items = spark.createDataFrame(
        [
            Row(order_id="o1", price=100.0),
            Row(order_id="o1", price=30.0),
            Row(order_id="o2", price=70.0),
        ]
    )

    gold_gmv = gold.build_order_metrics(orders).agg(F.sum("gmv")).first()[0]
    items_price = items.agg(F.sum("price")).first()[0]

    assert abs(gold_gmv - items_price) < 0.01


def test_order_counts_reconcile(spark):
    orders = _orders(spark)
    total = gold.build_order_metrics(orders).agg(F.sum("orders")).first()[0]

    assert total == orders.count()


# ---------------------------------------------------------- seller scorecard --


def _items(spark):
    """Build a small item fact for two sellers sharing one order.

    Args:
        spark: The session fixture.

    Returns:
        A DataFrame shaped like the silver item fact.
    """
    return spark.createDataFrame(
        [
            Row(
                order_id="o1",
                order_item_id=1,
                seller_id="s1",
                category="toys",
                price=100.0,
                freight_value=10.0,
                dispatch_late=False,
                year_month="2017-11",
                status="delivered",
                is_delivered=True,
                is_late=False,
                review_score=5,
            ),
            # Same order, second seller: both share the order's review.
            Row(
                order_id="o1",
                order_item_id=2,
                seller_id="s2",
                category="books",
                price=40.0,
                freight_value=4.0,
                dispatch_late=True,
                year_month="2017-11",
                status="delivered",
                is_delivered=True,
                is_late=False,
                review_score=5,
            ),
            Row(
                order_id="o2",
                order_item_id=1,
                seller_id="s1",
                category="toys",
                price=60.0,
                freight_value=6.0,
                dispatch_late=True,
                year_month="2017-12",
                status="delivered",
                is_delivered=True,
                is_late=True,
                review_score=1,
            ),
            Row(
                order_id="o3",
                order_item_id=1,
                seller_id="s1",
                category="games",
                price=20.0,
                freight_value=2.0,
                dispatch_late=None,
                year_month="2017-12",
                status="canceled",
                is_delivered=False,
                is_late=None,
                review_score=None,
            ),
        ]
    )


def _sellers(spark):
    """Build the sellers dimension for the scorecard tests.

    Args:
        spark: The session fixture.

    Returns:
        A DataFrame shaped like the silver sellers dimension.
    """
    return spark.createDataFrame(
        [
            Row(seller_id="s1", seller_state="SP", seller_city="campinas"),
            Row(seller_id="s2", seller_state="RJ", seller_city="niteroi"),
        ]
    )


def test_seller_scorecard_measures(spark):
    rows = {
        r["seller_id"]: r
        for r in gold.build_seller_scorecard(_items(spark), _sellers(spark)).collect()
    }
    s1 = rows["s1"]

    assert s1["seller_state"] == "SP"
    assert s1["orders"] == 3
    assert s1["items"] == 3
    assert s1["gmv"] == 180.0
    assert s1["freight"] == 18.0
    assert s1["reviewed_orders"] == 2
    assert abs(s1["avg_review"] - 3.0) < 1e-9
    # One of two items with a known dispatch outcome was late.
    assert abs(s1["dispatch_late_rate"] - 0.5) < 1e-9
    # One late order out of two delivered.
    assert abs(s1["customer_late_rate"] - 0.5) < 1e-9
    # One cancelled order out of three.
    assert abs(s1["cancel_rate"] - (1 / 3)) < 1e-9


def test_seller_review_is_shared_across_multi_seller_orders(spark):
    rows = {
        r["seller_id"]: r
        for r in gold.build_seller_scorecard(_items(spark), _sellers(spark)).collect()
    }

    # o1 is a two-seller order; both sellers carry its 5 star review.
    assert rows["s2"]["reviewed_orders"] == 1
    assert abs(rows["s2"]["avg_review"] - 5.0) < 1e-9


def test_health_score_matches_the_documented_formula(spark):
    rows = {
        r["seller_id"]: r
        for r in gold.build_seller_scorecard(_items(spark), _sellers(spark)).collect()
    }
    s1 = rows["s1"]

    expected = 100 * (
        0.4 * ((s1["avg_review"] - 1) / 4)
        + 0.3 * (1 - s1["dispatch_late_rate"])
        + 0.3 * (1 - s1["cancel_rate"])
    )
    assert abs(s1["health_score"] - expected) < 1e-9


def test_seller_rates_stay_between_zero_and_one(spark):
    rows = gold.build_seller_scorecard(_items(spark), _sellers(spark)).collect()

    for row in rows:
        for field in ("dispatch_late_rate", "customer_late_rate", "cancel_rate"):
            value = row[field]
            if value is not None:
                assert 0.0 <= value <= 1.0, f"{field} out of range for {row['seller_id']}"


def test_seller_embedded_arrays(spark):
    rows = {
        r["seller_id"]: r
        for r in gold.build_seller_scorecard(_items(spark), _sellers(spark)).collect()
    }
    s1 = rows["s1"]

    categories = [c["category"] for c in s1["top_categories"]]
    assert categories[0] == "toys", "highest gmv category comes first"
    assert len(categories) <= 3

    months = {m["year_month"]: m for m in s1["monthly"]}
    assert months["2017-11"]["orders"] == 1
    assert months["2017-11"]["gmv"] == 100.0
    assert months["2017-12"]["orders"] == 2
    assert months["2017-12"]["gmv"] == 80.0
