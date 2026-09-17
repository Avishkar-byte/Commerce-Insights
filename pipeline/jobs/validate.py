"""Job: validate row counts and reconciliation across the layers.

Checks the raw, silver, and gold expectations from plan section 6 (Phase 8)
and fails with a clear message. MongoDB document counts are checked only when
--mongo is passed.
"""

from __future__ import annotations

import argparse
import os
import sys

from pyspark.sql import functions as F

from pipeline.common import config, io
from pipeline.common.log import get_logger
from pipeline.common.spark import get_spark, stop_spark

LOGGER = get_logger("validate")


class Results:
    """Collects check outcomes so every check runs before the job fails."""

    def __init__(self) -> None:
        """Start with no recorded checks."""
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def check(self, name: str, condition: bool, detail: str) -> None:
        """Record one pass or fail.

        Args:
            name: Short check name.
            condition: True when the check passes.
            detail: Value detail shown in the log line.
        """
        if condition:
            self.passed += 1
            LOGGER.info("  PASS  %-42s %s", name, detail)
        else:
            self.failed += 1
            LOGGER.error("  FAIL  %-42s %s", name, detail)

    def warn(self, name: str, detail: str) -> None:
        """Record a non-fatal observation.

        Args:
            name: Short check name.
            detail: Value detail shown in the log line.
        """
        self.warnings += 1
        LOGGER.warning("  WARN  %-42s %s", name, detail)

    def note(self, name: str, detail: str) -> None:
        """Log an informational count without judging it.

        Args:
            name: Short check name.
            detail: Value detail shown in the log line.
        """
        LOGGER.info("  ..    %-42s %s", name, detail)


def check_raw(spark, results: Results) -> None:
    """Validate the raw layer row counts.

    Args:
        spark: Active SparkSession.
        results: Collector for outcomes.
    """
    LOGGER.info("Raw layer")
    expected = config.get("validation", default={})

    orders = io.read_raw(spark, "orders").count()
    customers_df = io.read_raw(spark, "customers")
    customers = customers_df.count()
    distinct_unique = customers_df.select("customer_unique_id").distinct().count()

    results.check(
        "raw orders row count",
        orders == expected.get("expected_orders"),
        f"{orders} (expected {expected.get('expected_orders')})",
    )
    results.check(
        "raw customers row count",
        customers == expected.get("expected_customers"),
        f"{customers} (expected {expected.get('expected_customers')})",
    )
    results.check(
        "distinct customer_unique_id",
        distinct_unique == expected.get("expected_distinct_customer_unique_id"),
        f"{distinct_unique} (expected {expected.get('expected_distinct_customer_unique_id')})",
    )

    for table in ("order_items", "order_payments", "order_reviews", "products", "sellers"):
        results.note(f"raw {table} rows", str(io.read_raw(spark, table).count()))


def check_silver(spark, results: Results) -> None:
    """Validate the silver layer.

    Args:
        spark: Active SparkSession.
        results: Collector for outcomes.
    """
    LOGGER.info("Silver layer")
    expected = config.get("validation", default={})

    orders_fact = io.read_silver(spark, "orders_fact")
    rows = orders_fact.count()
    distinct_ids = orders_fact.select("order_id").distinct().count()
    null_months = orders_fact.filter(F.col("year_month").isNull()).count()

    results.check(
        "orders_fact row count",
        rows == expected.get("expected_orders"),
        f"{rows} (expected {expected.get('expected_orders')})",
    )
    results.check(
        "orders_fact order_id is unique", distinct_ids == rows, f"{distinct_ids} distinct"
    )
    results.check("orders_fact year_month never null", null_months == 0, f"{null_months} nulls")


def check_gold(spark, results: Results) -> None:
    """Validate gold reconciliation against silver.

    Args:
        spark: Active SparkSession.
        results: Collector for outcomes.
    """
    LOGGER.info("Gold layer")
    tolerance = float(config.get("validation", "gmv_tolerance", default=0.01))

    order_metrics = io.read_gold(spark, "order_metrics")
    items_fact = io.read_silver(spark, "items_fact")
    orders_fact = io.read_silver(spark, "orders_fact")

    gold_gmv = order_metrics.agg(F.sum("gmv")).first()[0] or 0.0
    items_price = items_fact.agg(F.sum("price")).first()[0] or 0.0
    results.check(
        "GMV reconciles with items_fact",
        abs(gold_gmv - items_price) <= tolerance,
        f"gold {gold_gmv:.2f} vs items {items_price:.2f} (diff {gold_gmv - items_price:.4f})",
    )

    gold_orders = order_metrics.agg(F.sum("orders")).first()[0] or 0
    fact_orders = orders_fact.count()
    results.check(
        "order count reconciles with orders_fact",
        gold_orders == fact_orders,
        f"gold {gold_orders} vs silver {fact_orders}",
    )

    scorecard = io.read_gold(spark, "seller_scorecard")
    for column in ("dispatch_late_rate", "customer_late_rate", "cancel_rate"):
        out_of_range = scorecard.filter(
            F.col(column).isNotNull() & ~F.col(column).between(0.0, 1.0)
        ).count()
        results.check(
            f"seller {column} within 0 to 1", out_of_range == 0, f"{out_of_range} out of range"
        )


def check_mongo(spark, results: Results) -> None:
    """Validate that MongoDB matches the gold layer.

    Args:
        spark: Active SparkSession.
        results: Collector for outcomes.
    """
    LOGGER.info("MongoDB")
    from pymongo import MongoClient

    uri = os.environ.get("MONGO_URI_PIPELINE", "").strip()
    database = os.environ.get("MONGO_DB", "").strip()
    if not uri or not database:
        results.check("MongoDB environment is configured", False, "MONGO_URI_PIPELINE is not set")
        return

    client = MongoClient(uri)
    try:
        db = client[database]
        for name in config.get("gold_collections", default=[]):
            gold_rows = io.read_gold(spark, name).count()
            mongo_rows = db[name].count_documents({})
            results.check(
                f"{name} document count",
                mongo_rows == gold_rows,
                f"mongo {mongo_rows} vs gold {gold_rows}",
            )

        meta = db["meta"].find_one({"_id": "run"})
        results.check("meta document exists", meta is not None, "found" if meta else "missing")
        if meta:
            results.note("meta run_at", str(meta.get("run_at")))
    finally:
        client.close()


def main(argv: list[str] | None = None) -> int:
    """Run every validation check.

    Args:
        argv: Command-line arguments, defaulting to sys.argv.

    Returns:
        0 when all checks pass, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description="Validate the Olist pipeline layers.")
    parser.add_argument(
        "--mongo", action="store_true", help="also check MongoDB document counts"
    )
    args = parser.parse_args(argv)

    spark = get_spark("olist-validate")
    results = Results()
    try:
        check_raw(spark, results)
        check_silver(spark, results)
        check_gold(spark, results)
        if args.mongo:
            check_mongo(spark, results)

        LOGGER.info("")
        LOGGER.info(
            "%d passed, %d failed, %d warnings", results.passed, results.failed, results.warnings
        )
        if results.failed:
            LOGGER.error("Validation FAILED")
            return 1
        LOGGER.info("Validation passed")
        return 0
    finally:
        stop_spark(spark)


if __name__ == "__main__":
    sys.exit(main())
