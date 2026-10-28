"""Barcode decoding with a set of preprocessing fallbacks.

Real-world phone/WhatsApp photos of receipts are frequently low-res,
recompressed, skewed, or unevenly lit, so a single cv2.imread -> pyzbar.decode
call often fails. This module tries decoding against the raw image first,
then walks through progressively more aggressive preprocessing variants
(contrast boost, thresholding, sharpening, upscaling, rotation) until one
of them decodes, or all of them are exhausted.
"""

import cv2
import numpy as np
from pyzbar import pyzbar

from app.logger import get_logger

logger = get_logger()


def _clahe(gray):
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _otsu_threshold(gray):
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh


def _adaptive_threshold(gray):
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 5
    )


def _sharpen(gray):
    blurred = cv2.GaussianBlur(gray, (0, 0), sigmaX=3)
    return cv2.addWeighted(gray, 1.5, blurred, -0.5, 0)


def _upscale(gray, factor=2.0):
    return cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)


def _rotate(image, angle):
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_w = int((h * sin) + (w * cos))
    new_h = int((h * cos) + (w * sin))
    matrix[0, 2] += (new_w / 2) - center[0]
    matrix[1, 2] += (new_h / 2) - center[1]
    return cv2.warpAffine(
        image, matrix, (new_w, new_h), flags=cv2.INTER_CUBIC, borderValue=255
    )


def _build_variants(gray):
    """Yield (name, image) preprocessing variants, cheapest/most-likely first."""
    yield "grayscale", gray
    yield "clahe", _clahe(gray)
    yield "otsu", _otsu_threshold(gray)
    yield "adaptive_threshold", _adaptive_threshold(gray)
    yield "sharpen", _sharpen(gray)
    yield "clahe+sharpen", _sharpen(_clahe(gray))
    yield "upscale_2x", _upscale(gray, 2.0)
    yield "upscale_2x+clahe", _clahe(_upscale(gray, 2.0))

    # Only pay for rotation search if nothing above worked (caller stops early).
    for angle in (90, 180, 270, -5, 5, -10, 10, -15, 15):
        yield f"rotate_{angle}", _rotate(gray, angle)


def decode_barcode(image_path):
    """Attempt to decode a barcode from the image at image_path.

    Returns a dict: {"value": str, "type": str, "variant": str} on success,
    or None if no variant produced a decodable barcode.
    """
    image = cv2.imread(image_path)
    if image is None:
        logger.error("Could not read image (unsupported format or corrupt file): %s", image_path)
        return None

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    for variant_name, variant_image in _build_variants(gray):
        results = pyzbar.decode(variant_image)
        if results:
            value = results[0].data.decode("utf-8", errors="replace").strip()
            barcode_type = results[0].type
            logger.info(
                "Barcode decoded via variant '%s': value=%r type=%s", variant_name, value, barcode_type
            )
            return {"value": value, "type": barcode_type, "variant": variant_name}

    logger.warning("Barcode decode failed for %s after trying all preprocessing variants", image_path)
    return None
