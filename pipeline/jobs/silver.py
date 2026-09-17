"""Job: read /olist/raw, build the silver tables, write /olist/silver.

A thin wrapper: it reads, calls pipeline.transforms.silver, and writes Parquet
with overwrite. It logs input rows, output rows, dropped duplicates, and null
counts for key columns.
"""

from __future__ import annotations

import sys

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from pipeline.common import io
from pipeline.common.log import get_logger
from pipeline.common.spark import get_spark, stop_spark
from pipeline.transforms import silver

LOGGER = get_logger("silver")

#: Columns whose null counts are worth logging per silver table.
KEY_COLUMNS: dict[str, list[str]] = {
    "customers": ["customer_id", "customer_unique_id", "customer_zip_prefix"],
    "sellers": ["seller_id", "seller_zip_prefix"],
    "products": ["product_id", "category"],
    "geo_zip": ["zip_prefix", "lat", "lng"],
    "orders_fact": ["order_id", "year_month", "customer_state", "primary_category"],
    "items_fact": ["order_id", "order_item_id", "seller_id", "category"],
}


def log_nulls(df: DataFrame, table: str) -> None:
    """Log the null count of each key column of a table.

    Args:
        df: The DataFrame about to be written.
        table: Silver table name, used to look up its key columns.
    """
    columns = [c for c in KEY_COLUMNS.get(table, []) if c in df.columns]
    if not columns:
        return
    counts = df.select(
        [F.sum(F.col(c).isNull().cast("long")).alias(c) for c in columns]
    ).collect()[0]
    summary = ", ".join(f"{c}={counts[c]}" for c in columns)
    LOGGER.info("  null counts: %s", summary)


def main() -> int:
    """Build every silver table from the raw layer.

    Returns:
        0 on success.
    """
    spark = get_spark("olist-silver")
    try:
        raw_customers = io.read_raw(spark, "customers")
        raw_orders = io.read_raw(spark, "orders")
        raw_items = io.read_raw(spark, "order_items")
        raw_payments = io.read_raw(spark, "order_payments")
        raw_reviews = io.read_raw(spark, "order_reviews")
        raw_products = io.read_raw(spark, "products")
        raw_sellers = io.read_raw(spark, "sellers")
        raw_geo = io.read_raw(spark, "geolocation")
        raw_translation = io.read_raw(spark, "category_translation")

        # Dimensions first: the facts depend on them.
        dimensions = {
            "customers": (raw_customers, silver.build_customers(raw_customers)),
            "sellers": (raw_sellers, silver.build_sellers(raw_sellers)),
            "products": (
                raw_products,
                silver.build_products(raw_products, raw_translation),
            ),
            "geo_zip": (raw_geo, silver.build_geo_zip(raw_geo)),
        }

        built: dict[str, DataFrame] = {}
        for table, (source, frame) in dimensions.items():
            frame = frame.cache()
            in_rows = source.count()
            out_rows = frame.count()
            LOGGER.info(
                "%-12s input %8d -> output %8d (removed %d)",
                table,
                in_rows,
                out_rows,
                in_rows - out_rows,
            )
            log_nulls(frame, table)
            io.write_silver(frame, table)
            built[table] = frame

        orders_fact = silver.build_orders_fact(
            orders=raw_orders,
            customers=built["customers"],
            items=raw_items,
            payments=raw_payments,
            reviews=raw_reviews,
            products=built["products"],
            sellers=built["sellers"],
            geo_zip=built["geo_zip"],
        ).cache()

        orders_in = raw_orders.count()
        orders_out = orders_fact.count()
        LOGGER.info(
            "%-12s input %8d -> output %8d (removed %d)",
            "orders_fact",
            orders_in,
            orders_out,
            orders_in - orders_out,
        )
        log_nulls(orders_fact, "orders_fact")
        io.write_silver(orders_fact, "orders_fact")

        items_fact = silver.attach_dispatch_late(
            silver.build_items_fact(
                items=raw_items,
                products=built["products"],
                sellers=built["sellers"],
                orders_fact=orders_fact,
            ),
            raw_orders,
        ).cache()

        items_in = raw_items.count()
        items_out = items_fact.count()
        LOGGER.info(
            "%-12s input %8d -> output %8d (removed %d)",
            "items_fact",
            items_in,
            items_out,
            items_in - items_out,
        )
        log_nulls(items_fact, "items_fact")
        io.write_silver(items_fact, "items_fact")

        for frame in (*built.values(), orders_fact, items_fact):
            frame.unpersist()

        LOGGER.info("Silver layer complete")
        return 0
    finally:
        stop_spark(spark)


if __name__ == "__main__":
    sys.exit(main())
