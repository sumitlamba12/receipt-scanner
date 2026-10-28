import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(BASE_DIR, "app")

INCOMING_DIR = os.path.join(APP_DIR, "incoming")
PROCESSED_DIR = os.path.join(APP_DIR, "processed")
NEEDS_REVIEW_DIR = os.path.join(APP_DIR, "needs_review")
LOGS_DIR = os.path.join(APP_DIR, "logs")
LOG_FILE = os.path.join(LOGS_DIR, "app.log")
LOG_MAX_BYTES = 10 * 1024 * 1024  # rotate at 10MB
LOG_BACKUP_COUNT = 10  # keep up to 10 rotated log files (~100MB total)

AUDIT_DB_PATH = os.path.join(LOGS_DIR, "receipts.db")

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"}

# How many images to process in parallel. Barcode/OCR work is CPU-bound but
# opencv/numpy/Tesseract release the GIL during their C-level calls, so a
# small thread pool gives real throughput on multi-core machines during
# upload bursts without the complexity of multiprocessing.
MAX_WORKERS = int(os.environ.get("RECEIPT_SCANNER_WORKERS", "4"))

# If needs_review/ accumulates more than this many files, log a WARNING on
# every check so a human notices a rising failure rate instead of it going
# unnoticed until someone happens to look in the folder.
NEEDS_REVIEW_ALERT_THRESHOLD = 50
BACKLOG_CHECK_INTERVAL_SECONDS = 300

# Explicit override for Windows installs where tesseract.exe isn't on PATH.
TESSERACT_CMD = os.environ.get("TESSERACT_CMD") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Tracking number patterns, most specific/trustworthy first. _find_tracking_number
# tries these IN ORDER and returns the first pattern that matches anything -
# it does not mix candidates across patterns, so a narrow known-format match
# always wins over a broad generic one (important because OCR sometimes glues
# a stray extra character onto a token, e.g. "NJPR1317313" instead of
# "JPR1317313" - the generic alnum pattern below would happily match that
# whole glued token, so it must never be allowed to outrank a known prefix).
TRACKING_NUMBER_PATTERNS = [
    r"JPR\d{6,10}",  # Khubani Air Pack AWB numbers (this client's courier)
    r"\b\d{10,18}\b",  # generic long digit-only tracking numbers
    # Generic carrier-style alphanumeric code (e.g. "1Z999AA10123456784").
    # Requires at least one letter AND one digit so it doesn't match plain
    # words in the receipt text. Broadest pattern - kept last on purpose.
    r"\b(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{10,20}\b",
]

MIN_TRACKING_NUMBER_LENGTH = 8
