"""Job: run representative Spark work, then hold the Spark UI open.

The Spark UI on port 4040 exists only while a SparkSession is alive, which
normally leaves a few seconds to capture the DAG of a job that has already
finished. This job runs joins and aggregations that produce real shuffle
stages, then keeps the session open for a fixed window so the UI can be
browsed and screenshotted without racing the job.

It writes nothing: silver and gold on HDFS are left untouched.
"""

from __future__ import annotations

import argparse
import sys
import time

from pyspark.sql import functions as F

from pipeline.common import io
from pipeline.common.log import get_logger
from pipeline.common.spark import get_spark, stop_spark
from pipeline.transforms import gold

LOGGER = get_logger("sparkui")

DEFAULT_MINUTES = 10


def run_workload(minutes: int = DEFAULT_MINUTES) -> None:
    """Execute joins and aggregations that generate visible shuffle stages.

    Args:
        minutes: How long to hold the UI open once the work has finished.
    """
    spark = get_spark("olist-spark-ui-demo")
    try:
        orders = io.read_silver(spark, "orders_fact").cache()
        items = io.read_silver(spark, "items_fact").cache()
        sellers = io.read_silver(spark, "sellers")

        LOGGER.info("Job 1 of 4: counting the silver fact tables")
        LOGGER.info("  orders_fact=%d  items_fact=%d", orders.count(), items.count())

        LOGGER.info("Job 2 of 4: grouped aggregation (shuffle) for order_metrics")
        LOGGER.info("  %d rows", gold.build_order_metrics(orders).count())

        LOGGER.info("Job 3 of 4: join of items to sellers, then aggregation (shuffle)")
        # items_fact already carries seller_state, so only the column it lacks is
        # taken from the dimension; joining the whole frame would make the name
        # ambiguous.
        cities = sellers.select("seller_id", "seller_city")
        joined = items.join(cities, "seller_id", "left").groupBy("seller_city").agg(
            F.sum("price").alias("gmv"),
            F.countDistinct("order_id").alias("orders"),
        )
        LOGGER.info("  %d seller cities", joined.count())

        LOGGER.info("Job 4 of 4: seller scorecard, the widest aggregation")
        LOGGER.info("  %d sellers", gold.build_seller_scorecard(items, sellers).count())

        orders.unpersist()
        items.unpersist()
        hold(minutes)
    finally:
        stop_spark(spark)


def hold(minutes: int = DEFAULT_MINUTES) -> None:
    """Block so the caller's SparkSession, and therefore the UI, stays alive.

    Args:
        minutes: How long to hold the UI open.
    """
    LOGGER.info("")
    LOGGER.info("=" * 68)
    LOGGER.info("  Spark UI is live at http://localhost:4040")
    LOGGER.info("")
    LOGGER.info("  Screenshot these three, in this order:")
    LOGGER.info("    1. Jobs tab, showing the four completed jobs")
    LOGGER.info("    2. Click a job, then 'DAG Visualization'")
    LOGGER.info("    3. Stages tab, a stage with non-zero Shuffle Read/Write")
    LOGGER.info("")
    LOGGER.info("  Holding for %d minutes. Press Ctrl+C when finished.", minutes)
    LOGGER.info("=" * 68)

    for remaining in range(minutes, 0, -1):
        LOGGER.info("  Spark UI open, %d minute(s) left ...", remaining)
        time.sleep(60)


def main(argv: list[str] | None = None) -> int:
    """Run the workload and hold the UI open.

    Args:
        argv: Command-line arguments, defaulting to sys.argv.

    Returns:
        0 on success.
    """
    parser = argparse.ArgumentParser(description="Hold the Spark UI open for screenshots.")
    parser.add_argument(
        "--minutes",
        type=int,
        default=DEFAULT_MINUTES,
        help=f"how long to keep the UI open (default {DEFAULT_MINUTES})",
    )
    args = parser.parse_args(argv)
    run_workload(args.minutes)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        LOGGER.info("Stopped. The Spark UI is now closed.")
        sys.exit(0)
