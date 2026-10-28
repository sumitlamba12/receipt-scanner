import os
import re
import shutil
from datetime import datetime

from app import config
from app.logger import get_logger

logger = get_logger()

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_-]")


def _sanitize(value: str) -> str:
    cleaned = _UNSAFE_CHARS.sub("_", value.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:80]


def _unique_destination(directory: str, filename: str) -> str:
    dest = os.path.join(directory, filename)
    if not os.path.exists(dest):
        return dest

    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(dest):
        dest = os.path.join(directory, f"{base}_{counter}{ext}")
        counter += 1
    return dest


def move_to_processed(image_path: str, value: str, source: str) -> str:
    """Rename/move a successfully decoded image into PROCESSED_DIR.

    Filename format: <sanitized_value>_<source><ext>, e.g. 1Z999AA1_barcode.jpg
    """
    os.makedirs(config.PROCESSED_DIR, exist_ok=True)
    ext = os.path.splitext(image_path)[1]
    filename = f"{_sanitize(value)}_{source}{ext}"
    dest = _unique_destination(config.PROCESSED_DIR, filename)

    shutil.move(image_path, dest)
    logger.info("Moved %s -> %s", image_path, dest)
    return dest


def move_to_needs_review(image_path: str, reason: str) -> str:
    """Move a failed image into NEEDS_REVIEW_DIR, keeping its original name."""
    os.makedirs(config.NEEDS_REVIEW_DIR, exist_ok=True)
    filename = os.path.basename(image_path)
    dest = _unique_destination(config.NEEDS_REVIEW_DIR, filename)

    shutil.move(image_path, dest)
    logger.warning("Moved %s -> %s (reason: %s)", image_path, dest, reason)
    return dest
