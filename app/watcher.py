import os
import time
from concurrent.futures import ThreadPoolExecutor

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app import config, file_handler
from app.logger import get_logger
from app.main import process_all_once, process_file

logger = get_logger()


def _safe_process(image_path: str) -> None:
    """Wraps process_file so one unexpected failure (permissions error, a
    truly malformed file that slips past the None-checks, disk hiccup, ...)
    can't silently kill a worker thread and stop that file from ever being
    picked up again. Worst case, the file still ends up in needs_review/
    with the error logged, instead of vanishing from consideration.

    Also owns the "let the file finish writing" settle delay. This must NOT
    run in watchdog's event-dispatch callback (on_created) - that callback
    runs on a single dispatch thread, so sleeping there serializes every
    incoming file to one every 0.5s+ regardless of how many worker threads
    exist, which defeats the point of a thread pool during a burst.
    """
    time.sleep(0.5)
    if not os.path.exists(image_path):
        return

    try:
        process_file(image_path)
    except Exception:
        logger.exception("Unexpected error processing %s - moving to needs_review", image_path)
        try:
            if os.path.exists(image_path):
                file_handler.move_to_needs_review(image_path, "unexpected processing error, see log")
        except Exception:
            logger.exception("Also failed to move %s to needs_review after processing error", image_path)


class IncomingHandler(FileSystemEventHandler):
    def __init__(self, executor: ThreadPoolExecutor):
        self.executor = executor

    def on_created(self, event):
        if event.is_directory:
            return
        ext = os.path.splitext(event.src_path)[1].lower()
        if ext not in config.SUPPORTED_EXTENSIONS:
            return

        # Hand off immediately - do not block the dispatch thread here.
        self.executor.submit(_safe_process, event.src_path)


def _check_needs_review_backlog():
    try:
        count = len([
            f for f in os.listdir(config.NEEDS_REVIEW_DIR)
            if os.path.splitext(f)[1].lower() in config.SUPPORTED_EXTENSIONS
        ])
    except FileNotFoundError:
        count = 0

    if count >= config.NEEDS_REVIEW_ALERT_THRESHOLD:
        logger.warning(
            "needs_review/ has %d files awaiting manual review (threshold %d) - "
            "failure rate may be rising, worth a look",
            count, config.NEEDS_REVIEW_ALERT_THRESHOLD,
        )


def watch():
    os.makedirs(config.INCOMING_DIR, exist_ok=True)

    # Catch up on anything that arrived while the watcher wasn't running
    # (crash, reboot, Windows update, etc.) before switching to live events.
    logger.info("Catching up on any files already in %s ...", config.INCOMING_DIR)
    process_all_once()

    executor = ThreadPoolExecutor(max_workers=config.MAX_WORKERS)
    handler = IncomingHandler(executor)
    observer = Observer()
    observer.schedule(handler, config.INCOMING_DIR, recursive=False)
    observer.start()
    logger.info(
        "Watching %s for new receipt images with %d worker threads (Ctrl+C to stop)...",
        config.INCOMING_DIR, config.MAX_WORKERS,
    )

    last_backlog_check = 0.0
    try:
        while True:
            time.sleep(1)
            now = time.time()
            if now - last_backlog_check >= config.BACKLOG_CHECK_INTERVAL_SECONDS:
                _check_needs_review_backlog()
                last_backlog_check = now
    except KeyboardInterrupt:
        observer.stop()
        logger.info("Stopping watcher, waiting for in-flight files to finish processing...")
        executor.shutdown(wait=True)
        logger.info("Stopped.")
    observer.join()
