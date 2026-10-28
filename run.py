import argparse

from app.main import process_all_once
from app.watcher import watch


def main():
    parser = argparse.ArgumentParser(description="Receipt barcode/OCR scanner")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process everything currently in app/incoming/ once, then exit.",
    )
    args = parser.parse_args()

    if args.once:
        results = process_all_once()
        for result in results:
            print(result)
    else:
        watch()


if __name__ == "__main__":
    main()
