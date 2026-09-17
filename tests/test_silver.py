"""Tests for pipeline.transforms.silver.

Covers the rules from plan sections 3.4 and 3.7 that are easy to get wrong:
zip padding, review dedupe, the primary-item tie-break, delay and distance
bucket boundaries, the bounding-box filter, and orders with no items.
"""

from __future__ import annotations

import datetime as dt

from pyspark.sql import Row
from pyspark.sql import functions as F

from pipeline.transforms import geo, silver


def _ts(text: str) -> dt.datetime:
    """Parse a test timestamp.

    Args:
        text: A ``yyyy-MM-dd HH:mm:ss`` string.

    Returns:
        The parsed datetime.
    """
    return dt.datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------- dimensions --


def test_customer_zip_is_left_padded_to_five(spark):
    raw = spark.createDataFrame(
        [
            Row(
                customer_id="c1",
                customer_unique_id="u1",
                customer_zip_code_prefix="123",
                customer_city="  São Paulo ",
                customer_state="SP",
            ),
            Row(
                customer_id="c2",
                customer_unique_id="u2",
                customer_zip_code_prefix="01310",
                customer_city="RIO",
                customer_state="RJ",
            ),
        ]
    )
    result = {r["customer_id"]: r for r in silver.build_customers(raw).collect()}

    assert result["c1"]["customer_zip_prefix"] == "00123"
    assert result["c2"]["customer_zip_prefix"] == "01310"
    # Trimmed and lower-cased, but accents are preserved.
    assert result["c1"]["customer_city"] == "são paulo"
    assert result["c2"]["customer_city"] == "rio"


def test_products_fall_back_to_portuguese_then_unknown(spark):
    products = spark.createDataFrame(
        [
            Row(
                product_id="p1",
                product_category_name="cama_mesa_banho",
                product_weight_g=1,
                product_length_cm=1,
                product_height_cm=1,
                product_width_cm=1,
            ),
            Row(
                product_id="p2",
                product_category_name="sem_traducao",
                product_weight_g=1,
                product_length_cm=1,
                product_height_cm=1,
                product_width_cm=1,
            ),
            Row(
                product_id="p3",
                product_category_name=None,
                product_weight_g=1,
                product_length_cm=1,
                product_height_cm=1,
                product_width_cm=1,
            ),
        ]
    )
    translation = spark.createDataFrame(
        [
            Row(
                product_category_name="cama_mesa_banho",
                product_category_name_english="bed_bath_table",
            )
        ]
    )
    built = silver.build_products(products, translation)
    result = {r["product_id"]: r["category"] for r in built.collect()}

    assert result["p1"] == "bed_bath_table"
    assert result["p2"] == "sem_traducao"
    assert result["p3"] == "unknown"


def test_geo_zip_drops_points_outside_brazil(spark):
    geolocation = spark.createDataFrame(
        [
            # Two valid points for 01310; their mean should be kept.
            Row(
                geolocation_zip_code_prefix="1310",
                geolocation_lat=-23.0,
                geolocation_lng=-46.0,
                geolocation_city="sp",
                geolocation_state="SP",
            ),
            Row(
                geolocation_zip_code_prefix="1310",
                geolocation_lat=-25.0,
                geolocation_lng=-48.0,
                geolocation_city="sp",
                geolocation_state="SP",
            ),
            # Far outside the bounding box: must be dropped before averaging.
            Row(
                geolocation_zip_code_prefix="1310",
                geolocation_lat=48.85,
                geolocation_lng=2.35,
                geolocation_city="paris",
                geolocation_state="XX",
            ),
        ]
    )
    rows = silver.build_geo_zip(geolocation).collect()

    assert len(rows) == 1
    assert rows[0]["zip_prefix"] == "01310"
    assert rows[0]["lat"] == -24.0
    assert rows[0]["lng"] == -47.0


# ------------------------------------------------------------------ reviews --


def test_latest_review_per_order_wins(spark):
    reviews = spark.createDataFrame(
        [
            Row(
                review_id="r1",
                order_id="o1",
                review_score=1,
                review_answer_timestamp=_ts("2018-01-01 10:00:00"),
            ),
            Row(
                review_id="r2",
                order_id="o1",
                review_score=5,
                review_answer_timestamp=_ts("2018-03-01 10:00:00"),
            ),
        ]
    )
    rows = silver.latest_reviews(reviews).collect()

    assert len(rows) == 1
    assert rows[0]["review_score"] == 5


# ------------------------------------------------------------- primary item --


def test_primary_item_picks_highest_price(spark):
    items = spark.createDataFrame(
        [
            Row(order_id="o1", order_item_id=1, product_id="p1", seller_id="s1", price=10.0),
            Row(order_id="o1", order_item_id=2, product_id="p2", seller_id="s2", price=99.0),
        ]
    )
    products = spark.createDataFrame(
        [Row(product_id="p1", category="toys"), Row(product_id="p2", category="electronics")]
    )
    rows = silver.primary_items(items, products).collect()

    assert len(rows) == 1
    assert rows[0]["primary_category"] == "electronics"
    assert rows[0]["primary_seller_id"] == "s2"


def test_primary_item_tie_breaks_on_lowest_item_id(spark):
    items = spark.createDataFrame(
        [
            Row(order_id="o1", order_item_id=2, product_id="p2", seller_id="s2", price=50.0),
            Row(order_id="o1", order_item_id=1, product_id="p1", seller_id="s1", price=50.0),
        ]
    )
    products = spark.createDataFrame(
        [Row(product_id="p1", category="toys"), Row(product_id="p2", category="electronics")]
    )
    rows = silver.primary_items(items, products).collect()

    assert rows[0]["primary_seller_id"] == "s1"
    assert rows[0]["primary_category"] == "toys"


# ----------------------------------------------------------------- payments --


def test_primary_payment_type_is_the_largest_total(spark):
    payments = spark.createDataFrame(
        [
            Row(order_id="o1", payment_sequential=1, payment_type="voucher", payment_value=30.0),
            Row(order_id="o1", payment_sequential=2, payment_type="voucher", payment_value=30.0),
            Row(
                order_id="o1",
                payment_sequential=3,
                payment_type="credit_card",
                payment_value=50.0,
            ),
        ]
    )
    rows = silver.payment_aggregates(payments).collect()

    assert len(rows) == 1
    assert rows[0]["payment_total"] == 110.0
    # voucher totals 60 against credit_card's 50, so voucher wins.
    assert rows[0]["primary_payment_type"] == "voucher"


# ------------------------------------------------------------------ buckets --


def test_delay_bucket_boundaries(spark):
    cases = [
        (-5, "On time"),
        (0, "On time"),
        (1, "1–3 days late"),
        (3, "1–3 days late"),
        (4, "4–7 days late"),
        (7, "4–7 days late"),
        (8, "8–14 days late"),
        (14, "8–14 days late"),
        (15, "15+ days late"),
        (99, "15+ days late"),
    ]
    df = spark.createDataFrame(
        [Row(delay_days=d, is_delivered=True) for d, _ in cases]
    ).withColumn("bucket", geo.delay_bucket(F.col("delay_days"), F.col("is_delivered")))
    got = {r["delay_days"]: r["bucket"] for r in df.collect()}

    for delay, expected in cases:
        assert got[delay] == expected, f"delay {delay} should be {expected}"


def test_delay_bucket_marks_undelivered_orders(spark):
    df = spark.createDataFrame(
        [
            Row(delay_days=None, is_delivered=False),
            Row(delay_days=20, is_delivered=False),
        ]
    ).withColumn("bucket", geo.delay_bucket(F.col("delay_days"), F.col("is_delivered")))

    assert {r["bucket"] for r in df.collect()} == {"Not delivered"}


def test_distance_bucket_boundaries(spark):
    cases = [
        (0.0, "<100"),
        (99.9, "<100"),
        (100.0, "100–500"),
        (499.9, "100–500"),
        (500.0, "500–1000"),
        (1000.0, "1000–2000"),
        (2000.0, "2000+"),
        (None, "unknown"),
    ]
    df = spark.createDataFrame(
        [Row(km=k) for k, _ in cases], "km double"
    ).withColumn("bucket", geo.distance_bucket(F.col("km")))
    got = {r["km"]: r["bucket"] for r in df.collect()}

    for km, expected in cases:
        assert got[km] == expected, f"{km} km should be {expected}"


def test_haversine_matches_known_distance(spark):
    # São Paulo to Rio de Janeiro is roughly 357 km.
    df = spark.createDataFrame(
        [Row(lat1=-23.5505, lng1=-46.6333, lat2=-22.9068, lng2=-43.1729)]
    ).withColumn(
        "km",
        geo.haversine_km(F.col("lat1"), F.col("lng1"), F.col("lat2"), F.col("lng2")),
    )
    km = df.collect()[0]["km"]

    assert 350 < km < 365, f"expected about 357 km, got {km}"


# -------------------------------------------------------------- orders fact --


def _order_fact_inputs(spark):
    """Build a minimal set of inputs for build_orders_fact.

    Args:
        spark: The session fixture.

    Returns:
        A tuple of the eight DataFrames build_orders_fact expects.
    """
    orders = spark.createDataFrame(
        [
            Row(
                order_id="o1",
                customer_id="c1",
                order_status="delivered",
                order_purchase_timestamp=_ts("2017-11-01 10:00:00"),
                order_approved_at=_ts("2017-11-01 11:00:00"),
                order_delivered_carrier_date=_ts("2017-11-03 10:00:00"),
                order_delivered_customer_date=_ts("2017-11-11 10:00:00"),
                order_estimated_delivery_date=_ts("2017-11-08 00:00:00"),
            ),
            # An order with no items at all.
            Row(
                order_id="o2",
                customer_id="c2",
                order_status="canceled",
                order_purchase_timestamp=_ts("2017-12-01 10:00:00"),
                order_approved_at=None,
                order_delivered_carrier_date=None,
                order_delivered_customer_date=None,
                order_estimated_delivery_date=_ts("2017-12-20 00:00:00"),
            ),
        ]
    )
    customers = spark.createDataFrame(
        [
            Row(
                customer_id="c1",
                customer_unique_id="u1",
                customer_zip_prefix="01310",
                customer_city="sp",
                customer_state="SP",
            ),
            Row(
                customer_id="c2",
                customer_unique_id="u2",
                customer_zip_prefix="20040",
                customer_city="rio",
                customer_state="RJ",
            ),
        ]
    )
    items = spark.createDataFrame(
        [
            Row(
                order_id="o1",
                order_item_id=1,
                product_id="p1",
                seller_id="s1",
                shipping_limit_date=_ts("2017-11-02 10:00:00"),
                price=100.0,
                freight_value=10.0,
            )
        ]
    )
    payments = spark.createDataFrame(
        [
            Row(
                order_id="o1",
                payment_sequential=1,
                payment_type="credit_card",
                payment_installments=1,
                payment_value=110.0,
            )
        ]
    )
    reviews = spark.createDataFrame(
        [
            Row(
                review_id="r1",
                order_id="o1",
                review_score=2,
                review_answer_timestamp=_ts("2017-11-15 10:00:00"),
            )
        ]
    )
    products = spark.createDataFrame([Row(product_id="p1", category="toys")])
    sellers = spark.createDataFrame(
        [Row(seller_id="s1", seller_zip_prefix="20040", seller_city="rio", seller_state="RJ")]
    )
    geo_zip = spark.createDataFrame(
        [
            Row(zip_prefix="01310", lat=-23.5505, lng=-46.6333),
            Row(zip_prefix="20040", lat=-22.9068, lng=-43.1729),
        ]
    )
    return orders, customers, items, payments, reviews, products, sellers, geo_zip


def test_orders_fact_keeps_every_order_and_derives_delay(spark):
    args = _order_fact_inputs(spark)
    rows = {r["order_id"]: r for r in silver.build_orders_fact(*args).collect()}

    assert set(rows) == {"o1", "o2"}, "every order must survive into silver"

    o1 = rows["o1"]
    assert o1["year_month"] == "2017-11"
    assert o1["is_delivered"] is True
    assert o1["delivery_days"] == 10
    assert o1["delay_days"] == 3
    assert o1["is_late"] is True
    assert o1["delay_bucket"] == "1–3 days late"
    assert o1["gmv"] == 100.0
    assert o1["freight"] == 10.0
    assert o1["n_items"] == 1
    assert o1["primary_category"] == "toys"
    assert o1["primary_payment_type"] == "credit_card"
    assert o1["review_score"] == 2
    # SP customer, RJ seller: roughly the Sao Paulo to Rio distance.
    assert o1["distance_bucket"] == "100–500"


def test_orders_with_no_items_are_labelled(spark):
    args = _order_fact_inputs(spark)
    rows = {r["order_id"]: r for r in silver.build_orders_fact(*args).collect()}

    o2 = rows["o2"]
    assert o2["primary_category"] == "no items"
    assert o2["n_items"] == 0
    assert o2["gmv"] == 0.0
    assert o2["is_delivered"] is False
    assert o2["delay_bucket"] == "Not delivered"
    assert o2["distance_bucket"] == "unknown"


# --------------------------------------------------------------- items fact --


def test_dispatch_late_is_null_when_a_timestamp_is_missing(spark):
    items_fact = spark.createDataFrame(
        [
            Row(order_id="o1", shipping_limit_ts=_ts("2017-11-02 10:00:00")),
            Row(order_id="o2", shipping_limit_ts=_ts("2017-11-02 10:00:00")),
            Row(order_id="o3", shipping_limit_ts=None),
        ]
    )
    orders = spark.createDataFrame(
        [
            # Handed over after the limit: late.
            Row(order_id="o1", order_delivered_carrier_date=_ts("2017-11-05 10:00:00")),
            # Never handed over: unknown, not False.
            Row(order_id="o2", order_delivered_carrier_date=None),
            Row(order_id="o3", order_delivered_carrier_date=_ts("2017-11-05 10:00:00")),
        ]
    )
    rows = {
        r["order_id"]: r["dispatch_late"]
        for r in silver.attach_dispatch_late(items_fact, orders).collect()
    }

    assert rows["o1"] is True
    assert rows["o2"] is None
    assert rows["o3"] is None
