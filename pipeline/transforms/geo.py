"""Geospatial helpers expressed as Spark column expressions.

The haversine distance is built from pyspark.sql.functions only; no Python UDF
is used, so the work stays inside the JVM.
"""

from __future__ import annotations

from pyspark.sql import Column
from pyspark.sql import functions as F

from pipeline.common import config


def haversine_km(lat1: Column, lng1: Column, lat2: Column, lng2: Column) -> Column:
    """Great-circle distance in kilometres between two coordinate pairs.

    Args:
        lat1: Latitude of the first point, in degrees.
        lng1: Longitude of the first point, in degrees.
        lat2: Latitude of the second point, in degrees.
        lng2: Longitude of the second point, in degrees.

    Returns:
        A Column of distances in kilometres, null when any input is null.
    """
    radius = float(config.get("geo", "earth_radius_km", default=6371.0))

    phi1 = F.radians(lat1)
    phi2 = F.radians(lat2)
    delta_phi = F.radians(lat2 - lat1)
    delta_lambda = F.radians(lng2 - lng1)

    a = (
        F.sin(delta_phi / 2) * F.sin(delta_phi / 2)
        + F.cos(phi1) * F.cos(phi2) * F.sin(delta_lambda / 2) * F.sin(delta_lambda / 2)
    )
    # Clamp to 1 so floating-point error cannot push asin out of its domain.
    # F.least is deliberately NOT used here: it ignores nulls, so a null
    # coordinate would collapse to 1.0 and yield a bogus antipodal distance
    # instead of staying null.
    a_clamped = F.when(a > F.lit(1.0), F.lit(1.0)).otherwise(a)
    return F.lit(2.0 * radius) * F.asin(F.sqrt(a_clamped))


def in_brazil_bbox(lat: Column, lng: Column) -> Column:
    """Whether a coordinate falls inside Brazil's bounding box.

    Args:
        lat: Latitude column, in degrees.
        lng: Longitude column, in degrees.

    Returns:
        A boolean Column.
    """
    bbox = config.get("geo", "bbox", default={})
    return (
        lat.between(bbox.get("lat_min", -35.0), bbox.get("lat_max", 5.5))
        & lng.between(bbox.get("lng_min", -74.0), bbox.get("lng_max", -34.0))
    )


def distance_bucket(distance: Column) -> Column:
    """Map a distance in kilometres to its configured bucket label.

    Bucket edges are exclusive upper bounds, so a label such as ``100-500``
    covers distances from 100 up to but not including 500. A null distance
    yields the configured unknown label rather than dropping the row.

    Args:
        distance: Distance column in kilometres.

    Returns:
        A string Column holding the bucket label.
    """
    edges = config.get("distance", "edges_km", default=[])
    labels = config.get("distance", "labels", default=[])
    unknown = config.get("distance", "unknown_label", default="unknown")

    expr = F.when(distance.isNull(), F.lit(unknown))
    for edge, label in zip(edges, labels, strict=False):
        expr = expr.when(distance < float(edge), F.lit(label))
    return expr.otherwise(F.lit(labels[-1] if labels else unknown))


def delay_bucket(delay_days: Column, is_delivered: Column) -> Column:
    """Map a delivery delay in days to its configured bucket label.

    Edges are inclusive upper bounds: a delay of 0 or less is "On time", 1 to 3
    days is the next label, and so on. Orders that were never delivered get the
    not-delivered label regardless of any delay value.

    Args:
        delay_days: Delay in whole days, positive when late.
        is_delivered: Boolean column marking delivered orders.

    Returns:
        A string Column holding the bucket label.
    """
    edges = config.get("delay", "edges", default=[])
    labels = config.get("delay", "labels", default=[])
    not_delivered = config.get("delay", "not_delivered_label", default="Not delivered")

    expr = F.when(~is_delivered | delay_days.isNull(), F.lit(not_delivered))
    for edge, label in zip(edges, labels, strict=False):
        expr = expr.when(delay_days <= int(edge), F.lit(label))
    return expr.otherwise(F.lit(labels[-1] if labels else not_delivered))
