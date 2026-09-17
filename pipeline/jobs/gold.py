"""Job: read /olist/silver, build the gold aggregates, write /olist/gold.

Writes one folder per MongoDB collection, with overwrite so the job is
idempotent, and logs the row count of each output.
"""

from __future__ import annotations

import sys

from pipeline.common import io
from pipeline.common.log import get_logger
from pipeline.common.spark import get_spark, stop_spark
from pipeline.transforms import gold

LOGGER = get_logger("gold")


def main() -> int:
    """Build every gold collection from the silver layer.

    Returns:
        0 on success.
    """
    spark = get_spark("olist-gold")
    try:
        orders_fact = io.read_silver(spark, "orders_fact").cache()
        items_fact = io.read_silver(spark, "items_fact").cache()
        sellers = io.read_silver(spark, "sellers")

        LOGGER.info(
            "Silver inputs: orders_fact=%d, items_fact=%d",
            orders_fact.count(),
            items_fact.count(),
        )

        collections = {
            "order_metrics": gold.build_order_metrics(orders_fact),
            "delivery_distance": gold.build_delivery_distance(orders_fact),
            "review_by_delay": gold.build_review_by_delay(orders_fact),
            "payment_mix": gold.build_payment_mix(orders_fact),
            "seller_scorecard": gold.build_seller_scorecard(items_fact, sellers),
        }

        for name, frame in collections.items():
            rows = frame.count()
            LOGGER.info("%-18s %7d documents", name, rows)
            io.write_gold(frame, name)

        orders_fact.unpersist()
        items_fact.unpersist()

        LOGGER.info("Gold layer complete")
        return 0
    finally:
        stop_spark(spark)


if __name__ == "__main__":
    sys.exit(main())
