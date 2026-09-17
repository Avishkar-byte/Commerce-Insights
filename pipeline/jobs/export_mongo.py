"""Job: export the gold layer from HDFS into MongoDB.

Writes each gold collection with the MongoDB Spark Connector (format
"mongodb", mode overwrite), using seller_id as _id for seller_scorecard. It
then creates the indexes from plan section 3.5 with PyMongo and upserts the
meta document. A --driver-fallback flag writes via PyMongo insert_many in
batches of 1000 if the connector JAR cannot be resolved.

Connection strings come from MONGO_URI_PIPELINE and are never printed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

from pymongo import ASCENDING, DESCENDING, MongoClient
from pyspark.sql import DataFrame, SparkSession

from pipeline.common import config, io
from pipeline.common.log import get_logger
from pipeline.common.spark import get_spark, stop_spark

LOGGER = get_logger("export")

#: Rows pushed per insert_many call in driver-fallback mode.
BATCH_SIZE = 1000

#: Compound index shared by the order-level collections.
ORDER_INDEX = [
    ("year_month", ASCENDING),
    ("customer_state", ASCENDING),
    ("primary_category", ASCENDING),
]


def mongo_settings() -> tuple[str, str]:
    """Read the MongoDB connection settings from the environment.

    Returns:
        A tuple of (connection URI, database name).

    Raises:
        RuntimeError: if either variable is missing.
    """
    uri = os.environ.get("MONGO_URI_PIPELINE", "").strip()
    database = os.environ.get("MONGO_DB", "").strip()
    if not uri or not database:
        raise RuntimeError(
            "MONGO_URI_PIPELINE and MONGO_DB must be set. Run this job through "
            "tasks.ps1 so docker compose provides them."
        )
    return uri, database


def prepare(df: DataFrame, collection: str) -> DataFrame:
    """Shape a gold DataFrame for MongoDB.

    The seller scorecard is keyed by seller_id so re-exports replace documents
    rather than duplicating them.

    Args:
        df: The gold DataFrame.
        collection: Target collection name.

    Returns:
        The DataFrame ready to write.
    """
    if collection == "seller_scorecard":
        return df.withColumnRenamed("seller_id", "_id")
    return df


def write_with_connector(df: DataFrame, collection: str, uri: str, database: str) -> None:
    """Write one collection using the MongoDB Spark Connector.

    Args:
        df: DataFrame to write.
        collection: Target collection name.
        uri: MongoDB connection URI.
        database: Target database name.
    """
    (
        df.write.format("mongodb")
        .mode("overwrite")
        .option("connection.uri", uri)
        .option("database", database)
        .option("collection", collection)
        .save()
    )


def write_with_driver(df: DataFrame, collection: str, client: MongoClient, database: str) -> None:
    """Write one collection with PyMongo, in batches.

    Used when the connector JAR cannot be resolved. Gold data is only a few MB,
    so collecting it to the driver is acceptable here.

    Args:
        df: DataFrame to write.
        collection: Target collection name.
        client: An open MongoClient.
        database: Target database name.
    """
    target = client[database][collection]
    target.drop()

    records = [row.asDict(recursive=True) for row in df.collect()]
    for start in range(0, len(records), BATCH_SIZE):
        batch = records[start : start + BATCH_SIZE]
        if batch:
            target.insert_many(batch, ordered=False)


def create_indexes(client: MongoClient, database: str) -> None:
    """Create the indexes described in plan section 3.5.

    Args:
        client: An open MongoClient.
        database: Target database name.
    """
    db = client[database]
    for collection in ("order_metrics", "delivery_distance", "review_by_delay", "payment_mix"):
        db[collection].create_index(ORDER_INDEX, name="filter_dims")
        LOGGER.info("Indexed %-18s on year_month, customer_state, primary_category", collection)

    db["seller_scorecard"].create_index(
        [("seller_state", ASCENDING), ("orders", DESCENDING)], name="state_orders"
    )
    LOGGER.info("Indexed %-18s on seller_state, orders", "seller_scorecard")


def build_meta(
    spark: SparkSession, client: MongoClient, database: str, gold_counts: dict[str, int]
) -> dict:
    """Build the meta document that the dashboard reads on startup.

    Args:
        spark: Active SparkSession, for reading the filter option lists.
        client: An open MongoClient.
        database: Target database name.
        gold_counts: Document count per gold collection.

    Returns:
        The meta document.
    """
    db = client[database]
    order_metrics = io.read_gold(spark, "order_metrics")

    def options(column: str) -> list[str]:
        values = (
            order_metrics.select(column)
            .distinct()
            .where(order_metrics[column].isNotNull())
            .collect()
        )
        return sorted(row[column] for row in values)

    payment_types = sorted(
        row["payment_type"]
        for row in io.read_gold(spark, "payment_mix")
        .select("payment_type")
        .distinct()
        .collect()
        if row["payment_type"] is not None
    )

    silver_counts = {
        table: io.read_silver(spark, table).count()
        for table in ("orders_fact", "items_fact", "customers", "sellers", "products")
    }

    return {
        "_id": "run",
        "run_at": dt.datetime.now(dt.UTC),
        "analysis_window": {
            "start": config.get("analysis_window", "start"),
            "end": config.get("analysis_window", "end"),
        },
        "source_counts": silver_counts,
        "gold_counts": gold_counts,
        "mongo_counts": {name: db[name].count_documents({}) for name in gold_counts},
        "filters": {
            "year_months": options("year_month"),
            "customer_states": options("customer_state"),
            "primary_categories": options("primary_category"),
            "payment_types": payment_types,
        },
    }


def main(argv: list[str] | None = None) -> int:
    """Export every gold collection into MongoDB.

    Args:
        argv: Command-line arguments, defaulting to sys.argv.

    Returns:
        0 on success, 1 if any collection count does not match.
    """
    parser = argparse.ArgumentParser(description="Export the gold layer to MongoDB.")
    parser.add_argument(
        "--driver-fallback",
        action="store_true",
        help="write with PyMongo instead of the Spark connector",
    )
    args = parser.parse_args(argv)

    uri, database = mongo_settings()
    collections = config.get("gold_collections", default=[])

    spark = get_spark("olist-export", with_mongo=not args.driver_fallback)
    client = MongoClient(uri)
    try:
        if args.driver_fallback:
            LOGGER.info("Driver-fallback mode: writing with PyMongo in batches of %d", BATCH_SIZE)
        else:
            LOGGER.info("Writing with the MongoDB Spark Connector")

        gold_counts: dict[str, int] = {}
        for name in collections:
            frame = prepare(io.read_gold(spark, name), name)
            rows = frame.count()
            gold_counts[name] = rows

            if args.driver_fallback:
                write_with_driver(frame, name, client, database)
            else:
                write_with_connector(frame, name, uri, database)

        LOGGER.info("Creating indexes")
        create_indexes(client, database)

        LOGGER.info("Writing the meta document")
        meta = build_meta(spark, client, database, gold_counts)
        client[database]["meta"].replace_one({"_id": "run"}, meta, upsert=True)

        LOGGER.info("")
        LOGGER.info("%-20s %10s %10s", "collection", "gold", "mongodb")
        LOGGER.info("%-20s %10s %10s", "-" * 20, "-" * 10, "-" * 10)
        mismatches = 0
        for name, expected in gold_counts.items():
            actual = client[database][name].count_documents({})
            flag = "" if actual == expected else "  MISMATCH"
            if actual != expected:
                mismatches += 1
            LOGGER.info("%-20s %10d %10d%s", name, expected, actual, flag)
        LOGGER.info("%-20s %10s %10d", "meta", "-", client[database]["meta"].count_documents({}))

        if mismatches:
            LOGGER.error("%d collection(s) did not match the gold count", mismatches)
            return 1

        LOGGER.info("Export complete")
        return 0
    finally:
        client.close()
        stop_spark(spark)


if __name__ == "__main__":
    sys.exit(main())
