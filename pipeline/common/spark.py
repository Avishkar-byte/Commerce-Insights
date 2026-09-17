"""Build the SparkSession used by every job.

Applies the 8 GB budget from plan section 3.10: local[2], 1 GB driver memory,
8 shuffle partitions, 256 MB max result size, and UTC session time zone. Sets
fs.defaultFS from HDFS_URL.

The MongoDB Spark Connector coordinate lives in config/settings.yaml and is
added to ``spark.jars.packages`` only when a job asks for it. Resolving that
package needs network access, so silver and gold deliberately start without it
and only the export job pays that cost.
"""

from __future__ import annotations

from pyspark.sql import SparkSession

from pipeline.common import config
from pipeline.common.log import get_logger

LOGGER = get_logger(__name__)


def get_spark(app_name: str | None = None, with_mongo: bool = False) -> SparkSession:
    """Create or return the SparkSession for a job.

    Args:
        app_name: Name shown in the Spark UI. Defaults to the configured name.
        with_mongo: When True, add the MongoDB Spark Connector to
            ``spark.jars.packages``. Only the export job needs it.

    Returns:
        An active SparkSession configured for the 8 GB memory budget.
    """
    spark_cfg = config.get("spark", default={})
    name = app_name or spark_cfg.get("app_name", "olist-pipeline")

    builder = (
        SparkSession.builder.appName(name)
        .master(spark_cfg.get("master", "local[2]"))
        .config("spark.driver.memory", spark_cfg.get("driver_memory", "1g"))
        .config("spark.sql.shuffle.partitions", spark_cfg.get("shuffle_partitions", 8))
        .config("spark.driver.maxResultSize", spark_cfg.get("max_result_size", "256m"))
        .config("spark.sql.session.timeZone", spark_cfg.get("timezone", "UTC"))
        .config("spark.hadoop.fs.defaultFS", config.hdfs_url())
        # The spark image ships no hdfs-site.xml, so the HDFS client would
        # otherwise default to 3 replicas and mark every block it writes
        # under-replicated on this two-DataNode cluster.
        .config("spark.hadoop.dfs.replication", str(config.get("hdfs", "replication", default=2)))
        .config("spark.ui.showConsoleProgress", "false")
    )

    if with_mongo:
        connector = spark_cfg.get("mongo_connector")
        if connector:
            LOGGER.info("Adding MongoDB Spark Connector: %s", connector)
            builder = builder.config("spark.jars.packages", connector)

    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    LOGGER.info(
        "SparkSession ready: %s on %s (shuffle partitions %s)",
        name,
        spark_cfg.get("master", "local[2]"),
        spark.conf.get("spark.sql.shuffle.partitions"),
    )
    return spark


def stop_spark(spark: SparkSession) -> None:
    """Stop a SparkSession if it is still running.

    Args:
        spark: The session to stop.
    """
    if spark is not None:
        spark.stop()
        LOGGER.info("SparkSession stopped")
