"""OCR fallback: when barcode decoding fails, try to read a printed tracking
number directly from the receipt text.

Earlier version ran heavy preprocessing (denoise + 2x upscale + forced Otsu
binarization) before OCR. Tested against real WhatsApp receipt photos, that
preprocessing destroyed the fine detail Tesseract needs to segment a busy
tabular courier form and it recovered nothing. Minimal preprocessing (plain
grayscale) with Tesseract's default automatic page segmentation reads these
forms far more reliably, so that is the primary attempt; PSM 6/11 and a
rotation sweep are fallbacks for images that are sideways or a single dense
block.
"""

import re

import cv2
import pytesseract

from app import config
from app.logger import get_logger

logger = get_logger()

if config.TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD

_COMPILED_PATTERNS = [re.compile(p) for p in config.TRACKING_NUMBER_PATTERNS]

_ROTATIONS = [
    ("0", None),
    ("90", cv2.ROTATE_90_CLOCKWISE),
    ("180", cv2.ROTATE_180),
    ("270", cv2.ROTATE_90_COUNTERCLOCKWISE),
]

_PSM_MODES = [3, 6, 11]  # 3 = automatic page segmentation (default), 6 = single block, 11 = sparse text


def _find_tracking_number(text):
    # Patterns are tried in priority order (most specific/trustworthy first);
    # the first pattern that matches anything wins outright. Candidates are
    # never mixed across patterns - see the comment in config.py for why
    # (a broad generic pattern can match a narrow pattern's target plus stray
    # OCR noise glued onto it, which would otherwise look like a "better",
    # longer match).
    for pattern in _COMPILED_PATTERNS:
        candidates = [
            match.strip() for match in pattern.findall(text)
            if len(match.strip()) >= config.MIN_TRACKING_NUMBER_LENGTH
        ]
        if candidates:
            candidates.sort(key=len, reverse=True)
            return candidates[0]

    return None


def extract_tracking_number(image_path):
    """Run OCR on image_path and try to find a tracking number in the text.

    Tries the image at 0/90/180/270 degrees (real phone photos are frequently
    sideways) and a couple of PSM modes at each angle, stopping as soon as a
    plausible tracking number is found. Returns a dict
    {"value": str, "raw_text": str, "rotation": str, "psm": int} on success,
    or None if nothing was found.
    """
    image = cv2.imread(image_path)
    if image is None:
        logger.error("OCR: could not read image %s", image_path)
        return None

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    for rotation_name, rotate_code in _ROTATIONS:
        variant = gray if rotate_code is None else cv2.rotate(gray, rotate_code)
        for psm in _PSM_MODES:
            try:
                text = pytesseract.image_to_string(variant, config=f"--psm {psm}")
            except pytesseract.TesseractNotFoundError:
                logger.error("Tesseract binary not found. Set TESSERACT_CMD or install tesseract-ocr.")
                raise

            value = _find_tracking_number(text)
            if value:
                logger.info(
                    "OCR fallback found tracking number %r (rotation=%s, psm=%d)",
                    value, rotation_name, psm,
                )
                return {"value": value, "raw_text": text, "rotation": rotation_name, "psm": psm}

    logger.warning("OCR fallback found no tracking number for %s after trying all rotations/PSM modes", image_path)
    return None
