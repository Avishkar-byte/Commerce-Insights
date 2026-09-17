"""Shared pytest fixtures.

Tests run entirely in-process against a local SparkSession and never touch
HDFS or MongoDB, so the suite works with the stack stopped.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pyspark.sql import SparkSession


@pytest.fixture(scope="session")
def spark() -> Iterator[SparkSession]:
    """Provide a small local SparkSession for the whole test session.

    Yields:
        A SparkSession on local[1] with UTC time zone and a single shuffle
        partition, which keeps small test jobs fast.
    """
    session = (
        SparkSession.builder.appName("olist-tests")
        .master("local[1]")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.ui.enabled", "false")
        .config("spark.driver.memory", "512m")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()
