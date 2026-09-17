"""Silver layer transformations (plan section 3.4).

One pure function per output table: customers, sellers, products, geo_zip,
orders_fact, and items_fact. Every function takes DataFrames and returns a
DataFrame; no function reads or writes storage.
"""

from __future__ import annotations

from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F

from pipeline.transforms import geo

#: Placeholder category and seller for orders that contain no items at all.
NO_ITEMS = "no items"

#: Fallback used when a product has no category in the source data.
UNKNOWN_CATEGORY = "unknown"


def _zip5(column: Column) -> Column:
    """Left-pad a zip prefix to five characters.

    Args:
        column: Raw zip prefix column.

    Returns:
        A string Column of exactly five characters.
    """
    return F.lpad(column.cast("string"), 5, "0")


def _clean_city(column: Column) -> Column:
    """Trim and lower-case a city name without stripping accents.

    Args:
        column: Raw city column.

    Returns:
        The normalised city Column.
    """
    return F.lower(F.trim(column))


def build_customers(customers: DataFrame) -> DataFrame:
    """Build the customers dimension.

    Args:
        customers: Raw customers table.

    Returns:
        One row per customer_id with a padded zip prefix and cleaned city.
    """
    return customers.dropDuplicates().select(
        F.col("customer_id"),
        F.col("customer_unique_id"),
        _zip5(F.col("customer_zip_code_prefix")).alias("customer_zip_prefix"),
        _clean_city(F.col("customer_city")).alias("customer_city"),
        F.col("customer_state"),
    )


def build_sellers(sellers: DataFrame) -> DataFrame:
    """Build the sellers dimension.

    Args:
        sellers: Raw sellers table.

    Returns:
        One row per seller_id with a padded zip prefix and cleaned city.
    """
    return sellers.dropDuplicates().select(
        F.col("seller_id"),
        _zip5(F.col("seller_zip_code_prefix")).alias("seller_zip_prefix"),
        _clean_city(F.col("seller_city")).alias("seller_city"),
        F.col("seller_state"),
    )


def build_products(products: DataFrame, translation: DataFrame) -> DataFrame:
    """Build the products dimension with English category names.

    The English name comes from the translation file. Products whose category
    has no translation keep the Portuguese name, and products with no category
    at all become "unknown".

    Args:
        products: Raw products table.
        translation: Raw category translation table.

    Returns:
        One row per product_id.
    """
    prod = products.dropDuplicates().alias("p")
    trans = translation.dropDuplicates().alias("t")

    return (
        prod.join(
            trans,
            F.col("p.product_category_name") == F.col("t.product_category_name"),
            "left",
        )
        .select(
            F.col("p.product_id").alias("product_id"),
            F.col("p.product_category_name").alias("category_pt"),
            F.coalesce(
                F.col("t.product_category_name_english"),
                F.col("p.product_category_name"),
                F.lit(UNKNOWN_CATEGORY),
            ).alias("category"),
            F.col("p.product_weight_g").alias("weight_g"),
            F.col("p.product_length_cm").alias("length_cm"),
            F.col("p.product_height_cm").alias("height_cm"),
            F.col("p.product_width_cm").alias("width_cm"),
        )
    )


def build_geo_zip(geolocation: DataFrame) -> DataFrame:
    """Build one representative coordinate per zip prefix.

    Coordinates outside Brazil's bounding box are dropped before averaging, so
    a handful of bad points cannot drag a zip prefix into the ocean.

    Args:
        geolocation: Raw geolocation table.

    Returns:
        One row per zip_prefix with mean lat and lng.
    """
    return (
        geolocation.dropDuplicates()
        .filter(geo.in_brazil_bbox(F.col("geolocation_lat"), F.col("geolocation_lng")))
        .groupBy(_zip5(F.col("geolocation_zip_code_prefix")).alias("zip_prefix"))
        .agg(
            F.avg("geolocation_lat").alias("lat"),
            F.avg("geolocation_lng").alias("lng"),
        )
    )


def latest_reviews(reviews: DataFrame) -> DataFrame:
    """Keep only the latest review per order.

    Args:
        reviews: Raw order_reviews table.

    Returns:
        One row per order_id with its most recent review_score.
    """
    ranked = Window.partitionBy("order_id").orderBy(
        F.col("review_answer_timestamp").desc_nulls_last(),
        F.col("review_id").asc(),
    )
    return (
        reviews.dropDuplicates()
        .withColumn("_rank", F.row_number().over(ranked))
        .filter(F.col("_rank") == 1)
        .select(
            F.col("order_id"),
            F.col("review_score"),
            F.col("review_answer_timestamp"),
        )
    )


def order_item_aggregates(items: DataFrame) -> DataFrame:
    """Aggregate order items up to one row per order.

    Args:
        items: Raw order_items table.

    Returns:
        Per-order item counts, distinct seller count, GMV and freight.
    """
    return items.groupBy("order_id").agg(
        F.count(F.lit(1)).cast("int").alias("n_items"),
        F.countDistinct("seller_id").cast("int").alias("n_sellers"),
        F.sum("price").alias("gmv"),
        F.sum("freight_value").alias("freight"),
    )


def primary_items(items: DataFrame, products: DataFrame) -> DataFrame:
    """Pick each order's primary item.

    The primary item is the most expensive one; ties are broken by the lowest
    order_item_id so the choice is deterministic.

    Args:
        items: Raw order_items table.
        products: Silver products dimension.

    Returns:
        One row per order_id with its primary category and seller.
    """
    ranked = Window.partitionBy("order_id").orderBy(
        F.col("price").desc_nulls_last(),
        F.col("order_item_id").asc(),
    )
    top = (
        items.withColumn("_rank", F.row_number().over(ranked))
        .filter(F.col("_rank") == 1)
        .select("order_id", "product_id", "seller_id")
    )
    return (
        top.join(products.select("product_id", "category"), "product_id", "left")
        .select(
            F.col("order_id"),
            F.coalesce(F.col("category"), F.lit(UNKNOWN_CATEGORY)).alias("primary_category"),
            F.col("seller_id").alias("primary_seller_id"),
        )
    )


def payment_aggregates(payments: DataFrame) -> DataFrame:
    """Aggregate payments up to one row per order.

    The primary payment type is the type contributing the largest total value
    for that order, with ties broken alphabetically for determinism.

    Args:
        payments: Raw order_payments table.

    Returns:
        One row per order_id with payment_total and primary_payment_type.
    """
    deduped = payments.dropDuplicates()

    totals = deduped.groupBy("order_id").agg(F.sum("payment_value").alias("payment_total"))

    by_type = deduped.groupBy("order_id", "payment_type").agg(
        F.sum("payment_value").alias("type_value")
    )
    ranked = Window.partitionBy("order_id").orderBy(
        F.col("type_value").desc_nulls_last(),
        F.col("payment_type").asc(),
    )
    primary = (
        by_type.withColumn("_rank", F.row_number().over(ranked))
        .filter(F.col("_rank") == 1)
        .select(F.col("order_id"), F.col("payment_type").alias("primary_payment_type"))
    )

    return totals.join(primary, "order_id", "left")


def build_orders_fact(
    orders: DataFrame,
    customers: DataFrame,
    items: DataFrame,
    payments: DataFrame,
    reviews: DataFrame,
    products: DataFrame,
    sellers: DataFrame,
    geo_zip: DataFrame,
) -> DataFrame:
    """Build the order-grain fact table.

    Every order in the source is kept, including cancelled orders and orders
    with no items, so nothing is lost before the dashboard's own filtering.

    Args:
        orders: Raw orders table.
        customers: Silver customers dimension.
        items: Raw order_items table.
        payments: Raw order_payments table.
        reviews: Raw order_reviews table.
        products: Silver products dimension.
        sellers: Silver sellers dimension.
        geo_zip: Silver geo_zip dimension.

    Returns:
        One row per order_id.
    """
    base = orders.dropDuplicates().alias("o")

    enriched = (
        base.join(customers.alias("c"), F.col("o.customer_id") == F.col("c.customer_id"), "left")
        .join(order_item_aggregates(items).alias("ia"), "order_id", "left")
        .join(primary_items(items, products).alias("pi"), "order_id", "left")
        .join(payment_aggregates(payments).alias("pa"), "order_id", "left")
        .join(latest_reviews(reviews).alias("r"), "order_id", "left")
    )

    is_delivered = (F.col("o.order_status") == "delivered") & F.col(
        "o.order_delivered_customer_date"
    ).isNotNull()

    delivery_days = F.when(
        is_delivered,
        F.datediff(F.col("o.order_delivered_customer_date"), F.col("o.order_purchase_timestamp")),
    )
    delay_days = F.when(
        is_delivered,
        F.datediff(
            F.to_date(F.col("o.order_delivered_customer_date")),
            F.to_date(F.col("o.order_estimated_delivery_date")),
        ),
    )

    with_flags = enriched.select(
        F.col("order_id"),
        F.col("c.customer_unique_id").alias("customer_unique_id"),
        F.col("c.customer_state").alias("customer_state"),
        F.col("c.customer_zip_prefix").alias("customer_zip_prefix"),
        F.col("o.order_purchase_timestamp").alias("purchase_ts"),
        F.date_format(F.col("o.order_purchase_timestamp"), "yyyy-MM").alias("year_month"),
        F.col("o.order_status").alias("status"),
        is_delivered.alias("is_delivered"),
        delivery_days.alias("delivery_days"),
        delay_days.alias("delay_days"),
        F.coalesce(F.col("ia.n_items"), F.lit(0)).alias("n_items"),
        F.coalesce(F.col("ia.n_sellers"), F.lit(0)).alias("n_sellers"),
        F.coalesce(F.col("ia.gmv"), F.lit(0.0)).alias("gmv"),
        F.coalesce(F.col("ia.freight"), F.lit(0.0)).alias("freight"),
        F.coalesce(F.col("pi.primary_category"), F.lit(NO_ITEMS)).alias("primary_category"),
        F.col("pi.primary_seller_id").alias("primary_seller_id"),
        F.coalesce(F.col("pa.payment_total"), F.lit(0.0)).alias("payment_total"),
        F.col("pa.primary_payment_type").alias("primary_payment_type"),
        F.col("r.review_score").alias("review_score"),
    ).withColumn("is_late", F.col("delay_days") > 0)

    with_buckets = with_flags.withColumn(
        "delay_bucket", geo.delay_bucket(F.col("delay_days"), F.col("is_delivered"))
    )

    return _attach_distance(with_buckets, sellers, geo_zip)


def _attach_distance(orders_fact: DataFrame, sellers: DataFrame, geo_zip: DataFrame) -> DataFrame:
    """Add distance_km and distance_bucket to the order fact.

    Orders whose customer or seller zip prefix has no known coordinate keep a
    null distance and fall into the "unknown" bucket; they are never dropped.

    Args:
        orders_fact: Order fact without distance columns.
        sellers: Silver sellers dimension.
        geo_zip: Silver geo_zip dimension.

    Returns:
        The order fact with distance columns appended.
    """
    seller_zip = sellers.select(
        F.col("seller_id").alias("_seller_id"),
        F.col("seller_zip_prefix").alias("_seller_zip"),
    )
    customer_geo = geo_zip.select(
        F.col("zip_prefix").alias("_c_zip"),
        F.col("lat").alias("c_lat"),
        F.col("lng").alias("c_lng"),
    )
    seller_geo = geo_zip.select(
        F.col("zip_prefix").alias("_s_zip"),
        F.col("lat").alias("s_lat"),
        F.col("lng").alias("s_lng"),
    )

    joined = (
        orders_fact.join(
            seller_zip, orders_fact["primary_seller_id"] == seller_zip["_seller_id"], "left"
        )
        .join(customer_geo, orders_fact["customer_zip_prefix"] == customer_geo["_c_zip"], "left")
        .join(seller_geo, F.col("_seller_zip") == seller_geo["_s_zip"], "left")
    )

    distance = geo.haversine_km(
        F.col("c_lat"), F.col("c_lng"), F.col("s_lat"), F.col("s_lng")
    )

    return joined.withColumn("distance_km", distance).drop(
        "_seller_id", "_seller_zip", "_c_zip", "_s_zip", "c_lat", "c_lng", "s_lat", "s_lng"
    ).withColumn("distance_bucket", geo.distance_bucket(F.col("distance_km")))


def build_items_fact(
    items: DataFrame,
    products: DataFrame,
    sellers: DataFrame,
    orders_fact: DataFrame,
) -> DataFrame:
    """Build the item-grain fact table.

    ``dispatch_late`` compares the carrier handover against the seller's
    shipping limit, which isolates the seller's own delay from carrier delay.
    It is null when either timestamp is missing.

    Args:
        items: Raw order_items table.
        products: Silver products dimension.
        sellers: Silver sellers dimension.
        orders_fact: Silver order fact, for order-level attributes.

    Returns:
        One row per order item.
    """
    orders = items.dropDuplicates().alias("i")

    carrier = orders_fact.select(
        F.col("order_id").alias("_o_id"),
        F.col("year_month"),
        F.col("status"),
        F.col("is_delivered"),
        F.col("is_late"),
        F.col("review_score"),
    )

    return (
        orders.join(
            products.select("product_id", "category").alias("p"),
            F.col("i.product_id") == F.col("p.product_id"),
            "left",
        )
        .join(
            sellers.select("seller_id", "seller_state").alias("s"),
            F.col("i.seller_id") == F.col("s.seller_id"),
            "left",
        )
        .join(carrier, F.col("i.order_id") == F.col("_o_id"), "left")
        .select(
            F.col("i.order_id").alias("order_id"),
            F.col("i.order_item_id").alias("order_item_id"),
            F.col("i.product_id").alias("product_id"),
            F.col("i.seller_id").alias("seller_id"),
            F.col("s.seller_state").alias("seller_state"),
            F.coalesce(F.col("p.category"), F.lit(UNKNOWN_CATEGORY)).alias("category"),
            F.col("i.price").alias("price"),
            F.col("i.freight_value").alias("freight_value"),
            F.col("i.shipping_limit_date").alias("shipping_limit_ts"),
            F.col("year_month"),
            F.col("status"),
            F.col("is_delivered"),
            F.col("is_late"),
            F.col("review_score"),
        )
    )


def attach_dispatch_late(items_fact: DataFrame, orders: DataFrame) -> DataFrame:
    """Add delivered_carrier_ts and dispatch_late to the item fact.

    Args:
        items_fact: Item fact without carrier columns.
        orders: Raw orders table, for the carrier handover timestamp.

    Returns:
        The item fact with carrier timestamp and dispatch_late appended.
    """
    carrier = orders.select(
        F.col("order_id").alias("_c_order_id"),
        F.col("order_delivered_carrier_date").alias("delivered_carrier_ts"),
    ).dropDuplicates(["_c_order_id"])

    joined = items_fact.join(
        carrier, items_fact["order_id"] == carrier["_c_order_id"], "left"
    ).drop("_c_order_id")

    dispatch_late = F.when(
        F.col("delivered_carrier_ts").isNull() | F.col("shipping_limit_ts").isNull(),
        F.lit(None).cast("boolean"),
    ).otherwise(F.col("delivered_carrier_ts") > F.col("shipping_limit_ts"))

    return joined.withColumn("dispatch_late", dispatch_late)
