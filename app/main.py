import os

from app import audit, config, file_handler
from app.barcode_reader import decode_barcode
from app.logger import get_logger
from app.ocr_fallback import extract_tracking_number

logger = get_logger()


def process_file(image_path: str) -> dict:
    """Process a single receipt image: try barcode decode, then OCR fallback,
    then move it to processed/ or needs_review/ accordingly.

    Every outcome (success or failure) is recorded in the audit DB. Returns a
    result dict describing what happened.
    """
    original_filename = os.path.basename(image_path)
    logger.info("Processing %s", image_path)

    barcode_result = decode_barcode(image_path)
    if barcode_result:
        return _finish_processed(
            image_path, original_filename, barcode_result["value"], "barcode",
            barcode_type=barcode_result["type"], variant=barcode_result["variant"],
        )

    ocr_result = extract_tracking_number(image_path)
    if ocr_result:
        return _finish_processed(
            image_path, original_filename, ocr_result["value"], "ocr",
            rotation=ocr_result["rotation"], psm=ocr_result["psm"],
        )

    dest = file_handler.move_to_needs_review(image_path, "no barcode decoded and no tracking number found via OCR")
    audit.record(original_filename, None, None, "needs_review", dest)
    return {
        "status": "needs_review",
        "source": None,
        "value": None,
        "dest": dest,
    }


def _finish_processed(image_path: str, original_filename: str, value: str, source: str, **detail) -> dict:
    is_duplicate = audit.is_duplicate(value)
    if is_duplicate:
        logger.warning("Tracking number %r has already been processed before (duplicate upload/photo)", value)

    dest = file_handler.move_to_processed(image_path, value, source)
    audit.record(original_filename, value, source, "processed", dest)
    return {
        "status": "processed",
        "source": source,
        "value": value,
        "dest": dest,
        "is_duplicate": is_duplicate,
        **detail,
    }


def process_all_once() -> list:
    """Process every supported image currently sitting in INCOMING_DIR."""
    os.makedirs(config.INCOMING_DIR, exist_ok=True)
    results = []

    filenames = sorted(os.listdir(config.INCOMING_DIR))
    for filename in filenames:
        ext = os.path.splitext(filename)[1].lower()
        if ext not in config.SUPPORTED_EXTENSIONS:
            continue
        path = os.path.join(config.INCOMING_DIR, filename)
        results.append(process_file(path))

    if not results:
        logger.info("No supported images found in %s", config.INCOMING_DIR)

    return results
