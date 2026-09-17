"""Load and expose config/settings.yaml.

The YAML file is the single source of truth for HDFS paths, the analysis
window, bucket edges, the Brazil bounding box, Spark settings, and the
CSV-to-table mapping. Nothing in the pipeline hard-codes those values.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

#: Repository root, resolved from this file's location (``/workspace`` in the
#: spark container, the repo folder when running on the host).
REPO_ROOT = Path(__file__).resolve().parents[2]

#: Location of the settings file.
SETTINGS_PATH = REPO_ROOT / "config" / "settings.yaml"


@lru_cache(maxsize=1)
def load_settings() -> dict[str, Any]:
    """Read and cache config/settings.yaml.

    Returns:
        The parsed settings mapping.

    Raises:
        FileNotFoundError: if the settings file is missing.
    """
    if not SETTINGS_PATH.exists():
        raise FileNotFoundError(f"Settings file not found: {SETTINGS_PATH}")
    with SETTINGS_PATH.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def get(*keys: str, default: Any = None) -> Any:
    """Read a nested settings value.

    Args:
        *keys: Successive mapping keys, for example ``"spark", "master"``.
        default: Value returned when any key along the path is absent.

    Returns:
        The value at that path, or ``default``.
    """
    node: Any = load_settings()
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def hdfs_url() -> str:
    """Return the HDFS address from the environment variable named in settings.

    Returns:
        The ``fs.defaultFS`` value, for example ``hdfs://namenode:8020``.

    Raises:
        RuntimeError: if the environment variable is unset or empty.
    """
    env_name = get("hdfs", "url_env", default="HDFS_URL")
    url = os.environ.get(env_name, "").strip()
    if not url:
        raise RuntimeError(
            f"{env_name} is not set. Run this job through tasks.ps1 so that "
            "docker compose provides the container environment."
        )
    return url


def hdfs_path(layer: str, *parts: str) -> str:
    """Build a fully qualified HDFS path for a medallion layer.

    Args:
        layer: One of ``raw``, ``silver`` or ``gold``.
        *parts: Additional path segments, such as a table name.

    Returns:
        An absolute ``hdfs://`` URL.

    Raises:
        KeyError: if the layer is not configured.
    """
    base = get("hdfs", layer)
    if base is None:
        raise KeyError(f"Unknown HDFS layer: {layer}")
    suffix = "/".join(str(part).strip("/") for part in parts if str(part).strip("/"))
    path = f"{base}/{suffix}" if suffix else base
    return f"{hdfs_url().rstrip('/')}{path}"


def raw_files() -> dict[str, str]:
    """Return the mapping of raw CSV file name to HDFS table name.

    Returns:
        An ordered mapping such as ``{"olist_customers_dataset.csv": "customers"}``.
    """
    return dict(get("raw_files", default={}))


def data_raw_dir() -> Path:
    """Return the local directory holding the downloaded CSVs.

    Returns:
        The ``data/raw`` path inside the repository.
    """
    return REPO_ROOT / "data" / "raw"
