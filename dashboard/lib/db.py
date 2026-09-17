"""MongoDB access for the dashboard.

Builds a MongoClient from the MONGO_URI environment variable with
st.cache_resource, and exposes query helpers that push $match and $group into
MongoDB and return small pandas DataFrames, cached with st.cache_data(ttl=600).
If MongoDB is unreachable the helpers show a friendly st.error explaining the
fix rather than a traceback. Connection strings are never displayed.
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st
from pymongo import MongoClient
from pymongo.errors import PyMongoError

#: primary_category value used for orders that contain no items at all.
#: It is a placeholder, not a product category, so it is excluded wherever
#: categories are ranked or compared.
PLACEHOLDER_CATEGORY = "no items"

#: Measure columns summed for each collection.
MEASURES: dict[str, list[str]] = {
    "order_metrics": [
        "orders",
        "gmv",
        "freight",
        "delivered_orders",
        "late_orders",
        "sum_delivery_days",
        "sum_late_days",
        "reviewed_orders",
        "sum_review_score",
        "low_review_orders",
        "five_star_orders",
        "canceled_orders",
    ],
    "delivery_distance": ["delivered_orders", "late_orders", "sum_delivery_days"],
    "review_by_delay": [
        "reviewed_orders",
        "sum_review_score",
        "score_1",
        "score_2",
        "score_3",
        "score_4",
        "score_5",
    ],
    "payment_mix": ["payments", "payment_value"],
}


@st.cache_resource(show_spinner=False)
def get_client() -> MongoClient:
    """Open the shared MongoClient.

    Returns:
        A connected client.

    Raises:
        RuntimeError: if MONGO_URI is not set.
    """
    uri = os.environ.get("MONGO_URI", "").strip()
    if not uri:
        raise RuntimeError("MONGO_URI is not set")
    return MongoClient(uri, serverSelectionTimeoutMS=5000)


def get_database():
    """Return the configured database handle.

    Returns:
        The pymongo Database object.
    """
    name = os.environ.get("MONGO_DB", "olist_analytics").strip()
    return get_client()[name]


def connection_error(exc: Exception) -> None:
    """Show a friendly error explaining how to restore the connection.

    The exception text is not displayed, because it can contain the
    connection string.

    Args:
        exc: The underlying error, used only to pick the wording.
    """
    st.error(
        "Cannot reach the database.\n\n"
        "Start it with `.\\tasks.ps1 serve` in PowerShell, wait for the mongo "
        "container to report healthy, then reload this page."
    )
    st.caption(f"Error type: {type(exc).__name__}")


@st.cache_data(ttl=600, show_spinner=False)
def get_meta() -> dict:
    """Read the meta document written by the export job.

    Returns:
        The meta document, or an empty dict when it is missing.
    """
    try:
        return get_database()["meta"].find_one({"_id": "run"}) or {}
    except (PyMongoError, RuntimeError):
        return {}


@st.cache_data(ttl=600, show_spinner=False)
def aggregate(
    collection: str,
    match: dict | None = None,
    group_by: list[str] | None = None,
    measures: list[str] | None = None,
) -> pd.DataFrame:
    """Run a $match then $group pipeline and return the result as a DataFrame.

    All filtering and grouping happens inside MongoDB, so only the small
    grouped result crosses the wire.

    Args:
        collection: Collection name.
        match: A MongoDB $match document, or None for no filter.
        group_by: Dimension fields to group on. None or empty groups everything
            into a single total row.
        measures: Measure fields to sum. Defaults to the collection's measures.

    Returns:
        One row per group, with the dimensions as columns. Empty when the
        selection matches nothing.
    """
    fields = measures if measures is not None else MEASURES.get(collection, [])

    pipeline: list[dict] = []
    if match:
        pipeline.append({"$match": match})

    group: dict = {"_id": {f: f"${f}" for f in group_by} if group_by else None}
    for field in fields:
        group[field] = {"$sum": f"${field}"}
    pipeline.append({"$group": group})

    try:
        rows = list(get_database()[collection].aggregate(pipeline))
    except (PyMongoError, RuntimeError) as exc:
        connection_error(exc)
        return pd.DataFrame(columns=(group_by or []) + fields)

    records = []
    for row in rows:
        record = dict(row.pop("_id") or {})
        record.update(row)
        records.append(record)

    frame = pd.DataFrame(records)
    if frame.empty:
        return pd.DataFrame(columns=(group_by or []) + fields)
    return frame


@st.cache_data(ttl=600, show_spinner=False)
def sellers(
    seller_state: str | None = None,
    min_orders: int = 0,
    limit: int = 5000,
    sort_by: str = "gmv",
) -> pd.DataFrame:
    """Read seller scorecard documents.

    The default limit is above the total seller count, so the leaderboard shows
    every seller that clears the filter rather than silently truncating. The
    embedded arrays are projected away, so each row stays small.

    Args:
        seller_state: Restrict to one state, or None for all.
        min_orders: Minimum all-time order count.
        limit: Maximum rows to return.
        sort_by: Field to sort on, descending.

    Returns:
        One row per seller, without the embedded arrays.
    """
    match: dict = {"orders": {"$gte": int(min_orders)}}
    if seller_state:
        match["seller_state"] = seller_state

    projection = {
        "seller_state": 1,
        "seller_city": 1,
        "orders": 1,
        "items": 1,
        "gmv": 1,
        "freight": 1,
        "reviewed_orders": 1,
        "avg_review": 1,
        "dispatch_late_rate": 1,
        "customer_late_rate": 1,
        "cancel_rate": 1,
        "health_score": 1,
    }

    try:
        rows = list(
            get_database()["seller_scorecard"]
            .find(match, projection)
            .sort(sort_by, -1)
            .limit(int(limit))
        )
    except (PyMongoError, RuntimeError) as exc:
        connection_error(exc)
        return pd.DataFrame()

    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.rename(columns={"_id": "seller_id"})
    return frame


@st.cache_data(ttl=600, show_spinner=False)
def seller_detail(seller_id: str) -> dict:
    """Read one seller document including its embedded arrays.

    Args:
        seller_id: The seller's id.

    Returns:
        The full document, or an empty dict when not found.
    """
    try:
        return get_database()["seller_scorecard"].find_one({"_id": seller_id}) or {}
    except (PyMongoError, RuntimeError) as exc:
        connection_error(exc)
        return {}


@st.cache_data(ttl=600, show_spinner=False)
def seller_platform_average() -> dict:
    """Compute platform-wide seller averages for comparison.

    Returns:
        A mapping of metric name to average, or an empty dict on failure.
    """
    pipeline = [
        {
            "$group": {
                "_id": None,
                "avg_review": {"$avg": "$avg_review"},
                "dispatch_late_rate": {"$avg": "$dispatch_late_rate"},
                "customer_late_rate": {"$avg": "$customer_late_rate"},
                "cancel_rate": {"$avg": "$cancel_rate"},
                "health_score": {"$avg": "$health_score"},
            }
        }
    ]
    try:
        rows = list(get_database()["seller_scorecard"].aggregate(pipeline))
    except (PyMongoError, RuntimeError) as exc:
        connection_error(exc)
        return {}
    if not rows:
        return {}
    result = rows[0]
    result.pop("_id", None)
    return result
