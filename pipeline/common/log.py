"""Logging setup shared by all jobs.

Jobs use logging, never print, and record input rows, output rows, dropped
duplicates, and null counts for key columns (plan section 3.7, rule 9).
"""

from __future__ import annotations

import logging
import sys

_LOG_FORMAT = "%(asctime)s  %(levelname)-7s %(name)s  %(message)s"
_DATE_FORMAT = "%H:%M:%S"


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger that writes to stdout.

    Configuring the root logger once keeps Spark's own noisy loggers from being
    reconfigured, while every pipeline module shares one format.

    Args:
        name: Logger name, normally ``__name__``.

    Returns:
        A logger at INFO level writing to stdout.
    """
    root = logging.getLogger("pipeline")
    if not root.handlers:
        handler = logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        root.propagate = False

    suffix = name.split(".")[-1]
    return root.getChild(suffix)


def human_bytes(size: int) -> str:
    """Format a byte count for log output.

    Args:
        size: Number of bytes.

    Returns:
        A short human-readable string such as ``"14.4 MB"``.
    """
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"
