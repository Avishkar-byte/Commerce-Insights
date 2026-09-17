"""Explicit StructType schemas for all 9 raw Olist CSV tables.

inferSchema is never used: it reads zip prefixes as integers and drops their
leading zeros (plan section 3.7, rule 1). Zip prefixes are StringType and are
left-padded to 5 characters in the silver layer.

Column names follow the source files exactly, including the two misspellings
in the products table (``product_name_lenght``, ``product_description_lenght``).
"""

from __future__ import annotations

from typing import Any

from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

#: Timestamp layout used by every date column in the dataset.
TIMESTAMP_FORMAT = "yyyy-MM-dd HH:mm:ss"

CUSTOMERS = StructType(
    [
        StructField("customer_id", StringType(), True),
        StructField("customer_unique_id", StringType(), True),
        # String, not integer: leading zeros are significant in Brazilian CEPs.
        StructField("customer_zip_code_prefix", StringType(), True),
        StructField("customer_city", StringType(), True),
        StructField("customer_state", StringType(), True),
    ]
)

ORDERS = StructType(
    [
        StructField("order_id", StringType(), True),
        StructField("customer_id", StringType(), True),
        StructField("order_status", StringType(), True),
        StructField("order_purchase_timestamp", TimestampType(), True),
        StructField("order_approved_at", TimestampType(), True),
        StructField("order_delivered_carrier_date", TimestampType(), True),
        StructField("order_delivered_customer_date", TimestampType(), True),
        StructField("order_estimated_delivery_date", TimestampType(), True),
    ]
)

ORDER_ITEMS = StructType(
    [
        StructField("order_id", StringType(), True),
        StructField("order_item_id", IntegerType(), True),
        StructField("product_id", StringType(), True),
        StructField("seller_id", StringType(), True),
        StructField("shipping_limit_date", TimestampType(), True),
        StructField("price", DoubleType(), True),
        StructField("freight_value", DoubleType(), True),
    ]
)

ORDER_PAYMENTS = StructType(
    [
        StructField("order_id", StringType(), True),
        StructField("payment_sequential", IntegerType(), True),
        StructField("payment_type", StringType(), True),
        StructField("payment_installments", IntegerType(), True),
        StructField("payment_value", DoubleType(), True),
    ]
)

ORDER_REVIEWS = StructType(
    [
        StructField("review_id", StringType(), True),
        StructField("order_id", StringType(), True),
        StructField("review_score", IntegerType(), True),
        StructField("review_comment_title", StringType(), True),
        StructField("review_comment_message", StringType(), True),
        StructField("review_creation_date", TimestampType(), True),
        StructField("review_answer_timestamp", TimestampType(), True),
    ]
)

PRODUCTS = StructType(
    [
        StructField("product_id", StringType(), True),
        StructField("product_category_name", StringType(), True),
        # The two "lenght" spellings are as published in the source data.
        StructField("product_name_lenght", IntegerType(), True),
        StructField("product_description_lenght", IntegerType(), True),
        StructField("product_photos_qty", IntegerType(), True),
        StructField("product_weight_g", IntegerType(), True),
        StructField("product_length_cm", IntegerType(), True),
        StructField("product_height_cm", IntegerType(), True),
        StructField("product_width_cm", IntegerType(), True),
    ]
)

SELLERS = StructType(
    [
        StructField("seller_id", StringType(), True),
        StructField("seller_zip_code_prefix", StringType(), True),
        StructField("seller_city", StringType(), True),
        StructField("seller_state", StringType(), True),
    ]
)

GEOLOCATION = StructType(
    [
        StructField("geolocation_zip_code_prefix", StringType(), True),
        StructField("geolocation_lat", DoubleType(), True),
        StructField("geolocation_lng", DoubleType(), True),
        StructField("geolocation_city", StringType(), True),
        StructField("geolocation_state", StringType(), True),
    ]
)

CATEGORY_TRANSLATION = StructType(
    [
        StructField("product_category_name", StringType(), True),
        StructField("product_category_name_english", StringType(), True),
    ]
)

#: Raw table name (as used in HDFS and settings.yaml) to its schema.
RAW_SCHEMAS: dict[str, StructType] = {
    "customers": CUSTOMERS,
    "orders": ORDERS,
    "order_items": ORDER_ITEMS,
    "order_payments": ORDER_PAYMENTS,
    "order_reviews": ORDER_REVIEWS,
    "products": PRODUCTS,
    "sellers": SELLERS,
    "geolocation": GEOLOCATION,
    "category_translation": CATEGORY_TRANSLATION,
}

#: Options shared by every raw CSV read.
BASE_READ_OPTIONS: dict[str, Any] = {
    "header": True,
    "timestampFormat": TIMESTAMP_FORMAT,
    "mode": "PERMISSIVE",
}

#: Per-table overrides. The reviews file contains newlines inside quoted
#: comment text, so it must be parsed in multiLine mode (plan 3.7, rule 2).
EXTRA_READ_OPTIONS: dict[str, dict[str, Any]] = {
    "order_reviews": {
        "multiLine": True,
        "quote": '"',
        "escape": '"',
    },
}


def read_options(table: str) -> dict[str, Any]:
    """Return the CSV reader options for one raw table.

    Args:
        table: Raw table name, such as ``order_reviews``.

    Returns:
        A mapping of Spark CSV options.
    """
    options = dict(BASE_READ_OPTIONS)
    options.update(EXTRA_READ_OPTIONS.get(table, {}))
    return options


def schema_for(table: str) -> StructType:
    """Return the explicit schema for one raw table.

    Args:
        table: Raw table name.

    Returns:
        The table's StructType.

    Raises:
        KeyError: if the table has no declared schema.
    """
    if table not in RAW_SCHEMAS:
        raise KeyError(f"No schema declared for raw table: {table}")
    return RAW_SCHEMAS[table]
