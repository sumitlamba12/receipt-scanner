import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from app import audit, config, file_handler, main
from app.ocr_fallback import _find_tracking_number


class TestFileHandler(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.processed_dir = os.path.join(self.tmpdir, "processed")
        self.review_dir = os.path.join(self.tmpdir, "needs_review")
        self.patcher_processed = patch.object(config, "PROCESSED_DIR", self.processed_dir)
        self.patcher_review = patch.object(config, "NEEDS_REVIEW_DIR", self.review_dir)
        self.patcher_processed.start()
        self.patcher_review.start()

    def tearDown(self):
        self.patcher_processed.stop()
        self.patcher_review.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_dummy_image(self, name="sample.jpg"):
        path = os.path.join(self.tmpdir, name)
        cv2.imwrite(path, np.zeros((10, 10, 3), dtype=np.uint8))
        return path

    def test_move_to_processed_sanitizes_and_renames(self):
        path = self._make_dummy_image()
        dest = file_handler.move_to_processed(path, "1Z 999-AA1!", "barcode")
        self.assertTrue(os.path.exists(dest))
        self.assertTrue(dest.endswith("1Z_999-AA1.jpg"))

    def test_move_to_processed_avoids_overwrite(self):
        path1 = self._make_dummy_image("a.jpg")
        path2 = self._make_dummy_image("b.jpg")
        dest1 = file_handler.move_to_processed(path1, "SAME123", "barcode")
        dest2 = file_handler.move_to_processed(path2, "SAME123", "barcode")
        self.assertNotEqual(dest1, dest2)
        self.assertTrue(os.path.exists(dest1))
        self.assertTrue(os.path.exists(dest2))

    def test_move_to_needs_review(self):
        path = self._make_dummy_image("bad.jpg")
        dest = file_handler.move_to_needs_review(path, "no barcode found")
        self.assertTrue(os.path.exists(dest))
        self.assertIn("needs_review", dest)


class TestOcrRegex(unittest.TestCase):
    def test_finds_long_digit_run(self):
        text = "Courier Receipt\nTracking No: 1234567890123\nThank you"
        self.assertEqual(_find_tracking_number(text), "1234567890123")

    def test_finds_carrier_style_code(self):
        text = "AWB: 1Z999AA10123456784\nDeliver by Friday"
        self.assertEqual(_find_tracking_number(text), "1Z999AA10123456784")

    def test_returns_none_when_nothing_matches(self):
        text = "Thank you for shopping with us"
        self.assertIsNone(_find_tracking_number(text))

    def test_known_prefix_pattern_wins_over_glued_ocr_noise(self):
        # Regression: a generic alnum pattern would happily match the whole
        # glued token "NJPR1317313" (stray leading char from OCR noise) as a
        # "longer, therefore better" candidate. The narrow JPR-prefix pattern
        # must take priority and return the clean value instead.
        text = "AWB No. NJPR1317313 SURFACE"
        self.assertEqual(_find_tracking_number(text), "JPR1317313")


class TestMainPipeline(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.processed_dir = os.path.join(self.tmpdir, "processed")
        self.review_dir = os.path.join(self.tmpdir, "needs_review")
        patch.object(config, "PROCESSED_DIR", self.processed_dir).start()
        patch.object(config, "NEEDS_REVIEW_DIR", self.review_dir).start()
        patch.object(config, "AUDIT_DB_PATH", os.path.join(self.tmpdir, "receipts.db")).start()
        self.addCleanup(patch.stopall)
        self.addCleanup(lambda: shutil.rmtree(self.tmpdir, ignore_errors=True))

        self.image_path = os.path.join(self.tmpdir, "receipt.jpg")
        cv2.imwrite(self.image_path, np.zeros((10, 10, 3), dtype=np.uint8))

    @patch("app.main.decode_barcode")
    def test_barcode_success_moves_to_processed(self, mock_decode):
        mock_decode.return_value = {"value": "TRACK123", "type": "CODE128", "variant": "grayscale"}
        result = main.process_file(self.image_path)
        self.assertEqual(result["status"], "processed")
        self.assertEqual(result["source"], "barcode")
        self.assertTrue(os.path.exists(result["dest"]))

    @patch("app.main.extract_tracking_number")
    @patch("app.main.decode_barcode")
    def test_ocr_fallback_used_when_barcode_fails(self, mock_decode, mock_ocr):
        mock_decode.return_value = None
        mock_ocr.return_value = {"value": "OCRTRACK456", "raw_text": "...", "rotation": "0", "psm": 3}
        result = main.process_file(self.image_path)
        self.assertEqual(result["status"], "processed")
        self.assertEqual(result["source"], "ocr")

    @patch("app.main.extract_tracking_number")
    @patch("app.main.decode_barcode")
    def test_needs_review_when_both_fail(self, mock_decode, mock_ocr):
        mock_decode.return_value = None
        mock_ocr.return_value = None
        result = main.process_file(self.image_path)
        self.assertEqual(result["status"], "needs_review")
        self.assertTrue(os.path.exists(result["dest"]))

    @patch("app.main.decode_barcode")
    def test_first_scan_of_a_value_is_not_a_duplicate(self, mock_decode):
        mock_decode.return_value = {"value": "FIRSTSCAN1", "type": "CODE128", "variant": "grayscale"}
        result = main.process_file(self.image_path)
        self.assertFalse(result["is_duplicate"])

    @patch("app.main.decode_barcode")
    def test_second_scan_of_same_value_is_flagged_duplicate(self, mock_decode):
        mock_decode.return_value = {"value": "REPEATED1", "type": "CODE128", "variant": "grayscale"}
        main.process_file(self.image_path)

        second_image = os.path.join(self.tmpdir, "receipt2.jpg")
        cv2.imwrite(second_image, np.zeros((10, 10, 3), dtype=np.uint8))
        result = main.process_file(second_image)
        self.assertTrue(result["is_duplicate"])


class TestAudit(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        patch.object(config, "AUDIT_DB_PATH", os.path.join(self.tmpdir, "receipts.db")).start()
        self.addCleanup(patch.stopall)
        self.addCleanup(lambda: shutil.rmtree(self.tmpdir, ignore_errors=True))

    def test_unknown_value_is_not_a_duplicate(self):
        self.assertFalse(audit.is_duplicate("NEVERSEEN123"))

    def test_recorded_processed_value_is_a_duplicate(self):
        audit.record("a.jpg", "SEENBEFORE1", "barcode", "processed", "/processed/SEENBEFORE1_barcode.jpg")
        self.assertTrue(audit.is_duplicate("SEENBEFORE1"))

    def test_needs_review_records_do_not_count_as_duplicates(self):
        # A file with no decoded value (status=needs_review, value=None) must
        # never mark a later None lookup or block genuine reprocessing.
        audit.record("bad.jpg", None, None, "needs_review", "/needs_review/bad.jpg")
        self.assertFalse(audit.is_duplicate(None))


class TestWatcherSafety(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.review_dir = os.path.join(self.tmpdir, "needs_review")
        patch.object(config, "NEEDS_REVIEW_DIR", self.review_dir).start()
        self.addCleanup(patch.stopall)
        self.addCleanup(lambda: shutil.rmtree(self.tmpdir, ignore_errors=True))

        self.image_path = os.path.join(self.tmpdir, "receipt.jpg")
        cv2.imwrite(self.image_path, np.zeros((10, 10, 3), dtype=np.uint8))

    @patch("app.watcher.process_file")
    def test_unexpected_exception_lands_file_in_needs_review_instead_of_crashing(self, mock_process):
        from app.watcher import _safe_process

        mock_process.side_effect = RuntimeError("simulated unexpected failure")
        _safe_process(self.image_path)  # must not raise

        review_files = os.listdir(self.review_dir)
        self.assertEqual(len(review_files), 1)


if __name__ == "__main__":
    unittest.main()
