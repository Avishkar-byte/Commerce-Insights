"""Read and write helpers for the HDFS medallion layers.

Reads raw CSVs with explicit schemas, and reads and writes silver and gold
Parquet. All writes use overwrite mode so every job is idempotent.
"""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession

from pipeline.common import config, schemas
from pipeline.common.log import get_logger

LOGGER = get_logger(__name__)


def read_raw(spark: SparkSession, table: str) -> DataFrame:
    """Read one raw CSV table from HDFS using its explicit schema.

    Args:
        spark: Active SparkSession.
        table: Raw table name, such as ``orders``.

    Returns:
        The parsed DataFrame.
    """
    path = config.hdfs_path("raw", table)
    reader = spark.read.schema(schemas.schema_for(table))
    for key, value in schemas.read_options(table).items():
        reader = reader.option(key, value)
    LOGGER.info("Reading raw %-22s from %s", table, path)
    return reader.csv(path)


def read_silver(spark: SparkSession, table: str) -> DataFrame:
    """Read one silver Parquet table from HDFS.

    Args:
        spark: Active SparkSession.
        table: Silver table name, such as ``orders_fact``.

    Returns:
        The DataFrame read from Parquet.
    """
    path = config.hdfs_path("silver", table)
    LOGGER.info("Reading silver %-19s from %s", table, path)
    return spark.read.parquet(path)


def write_silver(df: DataFrame, table: str) -> None:
    """Write one silver table to HDFS as Parquet, overwriting any previous run.

    Args:
        df: DataFrame to persist.
        table: Silver table name.
    """
    path = config.hdfs_path("silver", table)
    LOGGER.info("Writing silver %-19s to   %s", table, path)
    df.write.mode("overwrite").parquet(path)


def read_gold(spark: SparkSession, collection: str) -> DataFrame:
    """Read one gold collection from HDFS.

    Args:
        spark: Active SparkSession.
        collection: Gold collection name, such as ``order_metrics``.

    Returns:
        The DataFrame read from Parquet.
    """
    path = config.hdfs_path("gold", collection)
    LOGGER.info("Reading gold %-20s from %s", collection, path)
    return spark.read.parquet(path)


def write_gold(df: DataFrame, collection: str) -> None:
    """Write one gold collection to HDFS as Parquet, overwriting any previous run.

    Args:
        df: DataFrame to persist.
        collection: Gold collection name.
    """
    path = config.hdfs_path("gold", collection)
    LOGGER.info("Writing gold %-20s to   %s", collection, path)
    df.write.mode("overwrite").parquet(path)
