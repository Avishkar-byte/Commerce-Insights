"""Download the Olist CSVs from Kaggle into data/raw.

Skips any file that is already present, so it is safe to re-run. Reads the
Kaggle credentials from the directory named by KAGGLE_CONFIG_DIR.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from pipeline.common import config
from pipeline.common.log import get_logger, human_bytes

LOGGER = get_logger("download")


def missing_files(target_dir: Path, expected: list[str]) -> list[str]:
    """Return the expected CSV names that are absent or empty.

    Args:
        target_dir: Directory that should hold the CSVs.
        expected: File names required by config/settings.yaml.

    Returns:
        The subset of names that still need downloading.
    """
    missing = []
    for name in expected:
        path = target_dir / name
        if not path.exists() or path.stat().st_size == 0:
            missing.append(name)
    return missing


def download_dataset(target_dir: Path) -> None:
    """Download and unzip the Kaggle dataset into ``target_dir``.

    Args:
        target_dir: Directory to unzip the CSVs into.

    Raises:
        RuntimeError: if the Kaggle client cannot authenticate or download.
    """
    dataset = config.get("kaggle_dataset")
    LOGGER.info("Downloading %s from Kaggle", dataset)

    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ImportError as exc:  # pragma: no cover - depends on the image
        raise RuntimeError("The kaggle package is not installed in this image.") from exc

    try:
        api = KaggleApi()
        api.authenticate()
    except Exception as exc:
        raise RuntimeError(
            "Kaggle authentication failed. Put a valid kaggle.json in secrets/ "
            "(mounted at KAGGLE_CONFIG_DIR), or place the CSVs in data/raw "
            "manually and re-run."
        ) from exc

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        api.dataset_download_files(dataset, path=str(tmp_path), unzip=False, quiet=False)

        archives = list(tmp_path.glob("*.zip"))
        if not archives:
            raise RuntimeError(f"No zip archive was downloaded into {tmp_path}")

        target_dir.mkdir(parents=True, exist_ok=True)
        for archive in archives:
            LOGGER.info("Unzipping %s", archive.name)
            with zipfile.ZipFile(archive) as zf:
                for member in zf.namelist():
                    if member.endswith("/"):
                        continue
                    # Flatten any directory structure so every CSV lands directly
                    # in data/raw, which is what the /staging mount expects.
                    destination = target_dir / Path(member).name
                    with zf.open(member) as source, destination.open("wb") as sink:
                        shutil.copyfileobj(source, sink)


def main() -> int:
    """Ensure every expected CSV is present in data/raw.

    Returns:
        0 when all files are present, 1 when any is still missing.
    """
    target_dir = config.data_raw_dir()
    expected = sorted(config.raw_files())
    LOGGER.info("Expecting %d CSV files in %s", len(expected), target_dir)

    still_missing = missing_files(target_dir, expected)
    if still_missing:
        LOGGER.info("Missing %d file(s): %s", len(still_missing), ", ".join(still_missing))
        download_dataset(target_dir)
        still_missing = missing_files(target_dir, expected)
    else:
        LOGGER.info("All files already present; skipping the download")

    if still_missing:
        LOGGER.error("Still missing after download: %s", ", ".join(still_missing))
        return 1

    total = 0
    for name in expected:
        size = (target_dir / name).stat().st_size
        total += size
        LOGGER.info("  %-45s %10s", name, human_bytes(size))
    LOGGER.info("%d files, %s in total", len(expected), human_bytes(total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
