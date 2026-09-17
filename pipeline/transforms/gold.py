"""Gold layer aggregations, one function per MongoDB collection.

Stores sums and counts only, never averages, so the dashboard can re-aggregate
any filter combination correctly. The only exception is seller_scorecard,
which stores all-time rates because it holds one document per seller.
"""

from __future__ import annotations

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

#: Shared filter dimensions, so every global filter works on every page.
ORDER_DIMENSIONS = ["year_month", "customer_state", "primary_category"]

#: Used when an order has no payment rows at all.
UNKNOWN_PAYMENT_TYPE = "unknown"

#: Weights for the seller health score. A documented design choice, not a standard.
HEALTH_REVIEW_WEIGHT = 0.4
HEALTH_DISPATCH_WEIGHT = 0.3
HEALTH_CANCEL_WEIGHT = 0.3


def _count_if(condition: Column) -> Column:
    """Count rows where a condition holds, ignoring nulls.

    Args:
        condition: Boolean column.

    Returns:
        A long Column with the matching row count.
    """
    return F.sum(F.when(condition, F.lit(1)).otherwise(F.lit(0))).cast("long")


def _safe_ratio(numerator: Column, denominator: Column) -> Column:
    """Divide two columns, returning null when the denominator is zero.

    Args:
        numerator: Dividend column.
        denominator: Divisor column.

    Returns:
        A double Column, null where the denominator is 0 or null.
    """
    return F.when(denominator > 0, numerator / denominator).otherwise(F.lit(None).cast("double"))


def build_order_metrics(orders_fact: DataFrame) -> DataFrame:
    """Aggregate the order fact to the shared filter grain.

    Args:
        orders_fact: Silver order fact.

    Returns:
        One row per year_month, customer_state and primary_category.
    """
    delivered = F.col("is_delivered")
    late = F.col("is_late") & delivered
    reviewed = F.col("review_score").isNotNull()

    return orders_fact.groupBy(*ORDER_DIMENSIONS).agg(
        F.count(F.lit(1)).cast("long").alias("orders"),
        F.coalesce(F.sum("gmv"), F.lit(0.0)).alias("gmv"),
        F.coalesce(F.sum("freight"), F.lit(0.0)).alias("freight"),
        _count_if(delivered).alias("delivered_orders"),
        _count_if(late).alias("late_orders"),
        F.coalesce(F.sum(F.when(delivered, F.col("delivery_days"))), F.lit(0)).cast(
            "long"
        ).alias("sum_delivery_days"),
        F.coalesce(F.sum(F.when(late, F.col("delay_days"))), F.lit(0)).cast("long").alias(
            "sum_late_days"
        ),
        _count_if(reviewed).alias("reviewed_orders"),
        F.coalesce(F.sum("review_score"), F.lit(0)).cast("long").alias("sum_review_score"),
        _count_if(F.col("review_score") <= 2).alias("low_review_orders"),
        _count_if(F.col("review_score") == 5).alias("five_star_orders"),
        _count_if(F.col("status") == "canceled").alias("canceled_orders"),
    )


def build_delivery_distance(orders_fact: DataFrame) -> DataFrame:
    """Aggregate delivery measures by distance bucket.

    Args:
        orders_fact: Silver order fact.

    Returns:
        One row per filter grain and distance_bucket.
    """
    delivered = F.col("is_delivered")
    late = F.col("is_late") & delivered

    return orders_fact.groupBy(*ORDER_DIMENSIONS, "distance_bucket").agg(
        _count_if(delivered).alias("delivered_orders"),
        _count_if(late).alias("late_orders"),
        F.coalesce(F.sum(F.when(delivered, F.col("delivery_days"))), F.lit(0)).cast(
            "long"
        ).alias("sum_delivery_days"),
    )


def build_review_by_delay(orders_fact: DataFrame) -> DataFrame:
    """Aggregate review scores by delay bucket.

    Args:
        orders_fact: Silver order fact.

    Returns:
        One row per filter grain and delay_bucket, with a count per score.
    """
    reviewed = F.col("review_score").isNotNull()

    aggregates = [
        _count_if(reviewed).alias("reviewed_orders"),
        F.coalesce(F.sum("review_score"), F.lit(0)).cast("long").alias("sum_review_score"),
    ]
    aggregates += [
        _count_if(F.col("review_score") == score).alias(f"score_{score}") for score in range(1, 6)
    ]

    return orders_fact.groupBy(*ORDER_DIMENSIONS, "delay_bucket").agg(*aggregates)


def build_payment_mix(orders_fact: DataFrame) -> DataFrame:
    """Aggregate payment value by payment type.

    The type is the order's *primary* payment type, the one contributing the
    largest share of that order's value. Splitting an order across several
    types would break additivity with the other order-level collections, so the
    dashboard reports the mix of primary types. State this in the report.

    Args:
        orders_fact: Silver order fact.

    Returns:
        One row per filter grain and payment_type.
    """
    payment_type = F.coalesce(
        F.col("primary_payment_type"), F.lit(UNKNOWN_PAYMENT_TYPE)
    ).alias("payment_type")

    return (
        orders_fact.withColumn("payment_type", payment_type)
        .groupBy(*ORDER_DIMENSIONS, "payment_type")
        .agg(
            F.count(F.lit(1)).cast("long").alias("payments"),
            F.coalesce(F.sum("payment_total"), F.lit(0.0)).alias("payment_value"),
        )
    )


def _seller_order_grain(items_fact: DataFrame) -> DataFrame:
    """Reduce the item fact to distinct seller and order pairs.

    Order-level attributes such as review_score repeat on every item of an
    order, so they must be de-duplicated before being summed per seller.

    Args:
        items_fact: Silver item fact.

    Returns:
        One row per seller_id and order_id.
    """
    return items_fact.select(
        "seller_id",
        "order_id",
        "year_month",
        "status",
        "is_delivered",
        "is_late",
        "review_score",
    ).distinct()


def _seller_top_categories(items_fact: DataFrame, limit: int = 3) -> DataFrame:
    """Build the embedded top_categories array for each seller.

    Args:
        items_fact: Silver item fact.
        limit: How many categories to keep per seller.

    Returns:
        One row per seller_id with an array of category and gmv structs.
    """
    by_category = items_fact.groupBy("seller_id", "category").agg(
        F.coalesce(F.sum("price"), F.lit(0.0)).alias("gmv")
    )
    return by_category.groupBy("seller_id").agg(
        F.slice(
            F.sort_array(
                F.collect_list(F.struct(F.col("gmv"), F.col("category"))),
                asc=False,
            ),
            1,
            limit,
        ).alias("_top")
    ).select(
        "seller_id",
        F.transform(
            F.col("_top"),
            lambda item: F.struct(item["category"].alias("category"), item["gmv"].alias("gmv")),
        ).alias("top_categories"),
    )


def _seller_monthly(items_fact: DataFrame) -> DataFrame:
    """Build the embedded monthly array for each seller.

    Args:
        items_fact: Silver item fact.

    Returns:
        One row per seller_id with an array of year_month, orders and gmv.
    """
    monthly = items_fact.groupBy("seller_id", "year_month").agg(
        F.countDistinct("order_id").cast("long").alias("orders"),
        F.coalesce(F.sum("price"), F.lit(0.0)).alias("gmv"),
    )
    return monthly.groupBy("seller_id").agg(
        F.sort_array(
            F.collect_list(
                F.struct(
                    F.col("year_month").alias("year_month"),
                    F.col("orders").alias("orders"),
                    F.col("gmv").alias("gmv"),
                )
            )
        ).alias("monthly")
    )


def build_seller_scorecard(items_fact: DataFrame, sellers: DataFrame) -> DataFrame:
    """Build one document per seller.

    This is the one collection that stores rates rather than raw sums, because
    it holds a single all-time document per seller and is never re-aggregated
    across a filter selection.

    A review belongs to an order, so in a multi-seller order every seller
    shares that review. Note this in the report.

    Args:
        items_fact: Silver item fact.
        sellers: Silver sellers dimension.

    Returns:
        One row per seller_id, ready to export as MongoDB documents.
    """
    order_grain = _seller_order_grain(items_fact)

    order_level = order_grain.groupBy("seller_id").agg(
        F.count(F.lit(1)).cast("long").alias("orders"),
        _count_if(F.col("is_delivered")).alias("delivered_orders"),
        _count_if(F.col("is_late") & F.col("is_delivered")).alias("late_orders"),
        _count_if(F.col("status") == "canceled").alias("canceled_orders"),
        _count_if(F.col("review_score").isNotNull()).alias("reviewed_orders"),
        F.coalesce(F.sum("review_score"), F.lit(0)).cast("long").alias("sum_review_score"),
    )

    item_level = items_fact.groupBy("seller_id").agg(
        F.count(F.lit(1)).cast("long").alias("items"),
        F.coalesce(F.sum("price"), F.lit(0.0)).alias("gmv"),
        F.coalesce(F.sum("freight_value"), F.lit(0.0)).alias("freight"),
        _count_if(F.col("dispatch_late")).alias("dispatch_late_items"),
        _count_if(F.col("dispatch_late").isNotNull()).alias("dispatch_known_items"),
    )

    joined = (
        order_level.join(item_level, "seller_id", "outer")
        .join(_seller_top_categories(items_fact), "seller_id", "left")
        .join(_seller_monthly(items_fact), "seller_id", "left")
        .join(
            sellers.select("seller_id", "seller_state", "seller_city"),
            "seller_id",
            "left",
        )
    )

    avg_review = _safe_ratio(F.col("sum_review_score"), F.col("reviewed_orders"))
    dispatch_late_rate = _safe_ratio(
        F.col("dispatch_late_items"), F.col("dispatch_known_items")
    )
    customer_late_rate = _safe_ratio(F.col("late_orders"), F.col("delivered_orders"))
    cancel_rate = _safe_ratio(F.col("canceled_orders"), F.col("orders"))

    # Unknown dispatch or cancel behaviour is treated as "no problem observed",
    # while a seller with no reviews at all gets a null score rather than a
    # flattering default.
    health_score = F.when(
        avg_review.isNotNull(),
        100
        * (
            HEALTH_REVIEW_WEIGHT * ((avg_review - 1) / 4)
            + HEALTH_DISPATCH_WEIGHT * (1 - F.coalesce(dispatch_late_rate, F.lit(0.0)))
            + HEALTH_CANCEL_WEIGHT * (1 - F.coalesce(cancel_rate, F.lit(0.0)))
        ),
    )

    return joined.select(
        F.col("seller_id"),
        F.col("seller_state"),
        F.col("seller_city"),
        F.coalesce(F.col("orders"), F.lit(0)).cast("long").alias("orders"),
        F.coalesce(F.col("items"), F.lit(0)).cast("long").alias("items"),
        F.coalesce(F.col("gmv"), F.lit(0.0)).alias("gmv"),
        F.coalesce(F.col("freight"), F.lit(0.0)).alias("freight"),
        F.coalesce(F.col("reviewed_orders"), F.lit(0)).cast("long").alias("reviewed_orders"),
        avg_review.alias("avg_review"),
        dispatch_late_rate.alias("dispatch_late_rate"),
        customer_late_rate.alias("customer_late_rate"),
        cancel_rate.alias("cancel_rate"),
        health_score.alias("health_score"),
        F.coalesce(F.col("top_categories"), F.array()).alias("top_categories"),
        F.coalesce(F.col("monthly"), F.array()).alias("monthly"),
    )
