# Receipt Scanner

Watches `app\incoming\` for receipt photos, reads the tracking number (barcode first, OCR fallback), and moves each image to:

- `app\processed\` - renamed to `<tracking number>_<barcode|ocr>.<ext>`
- `app\needs_review\` - could not be read, check by hand

Every result is recorded in `app\logs\receipts.db`; logs are in `app\logs\app.log`.

## Setup (Windows)

1. Install:
   - [Python 3.11](https://www.python.org/downloads/) - tick **"Add Python to PATH"**
   - [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) - default folder `C:\Program Files\Tesseract-OCR\`
     (if installed elsewhere, set the `TESSERACT_CMD` environment variable to the full path of `tesseract.exe`)
   - [Visual C++ 2013 Redistributable (x64)](https://www.microsoft.com/en-us/download/details.aspx?id=40784) - needed by the barcode reader
   - [Git](https://git-scm.com/download/win)
2. Clone and install dependencies:
   ```
   git clone <repo-url> C:\ReceiptScanner
   cd C:\ReceiptScanner
   pip install -r requirements.txt
   ```
3. Test:
   ```
   python -m unittest discover tests
   ```
4. Run: double-click `run_watcher.bat`.
5. Auto-start on boot: press `Win + R`, type `shell:startup`, and put a shortcut to `run_watcher.bat` in that folder.

## Usage

- `run_watcher.bat` / `python run.py` - keep watching `app\incoming\`
- `python run.py --once` - process what is in `app\incoming\` now, then exit

## Updating

```
git pull
pip install -r requirements.txt
```
Then restart `run_watcher.bat`. Receipts, logs and the database are not tracked by git, so they are kept.
