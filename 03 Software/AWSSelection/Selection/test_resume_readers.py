"""A missing runtime reader must not be mistaken for an empty/scanned CV."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'RF-One Data Store'))
from rfone_data_store.selection.parsing import text_extraction as extraction


class ReaderAvailabilityTests(unittest.TestCase):
    def test_missing_pdf_reader_reports_environment_problem(self):
        with patch.object(extraction, 'pdfplumber', None):
            with self.assertRaisesRegex(extraction.TextExtractionError, 'pdfplumber'):
                extraction.extract_text('unused.pdf', '.pdf')

    def test_missing_docx_reader_reports_environment_problem(self):
        with patch.object(extraction, '_python_docx', None):
            with self.assertRaisesRegex(extraction.TextExtractionError, 'python-docx'):
                extraction.extract_text('unused.docx', '.docx')

    def test_startup_checks_both_readers(self):
        with patch.object(extraction, 'pdfplumber', None), patch.object(extraction, '_python_docx', None):
            with self.assertRaisesRegex(extraction.TextExtractionError, 'pdfplumber, python-docx'):
                extraction.require_readers()

    def test_available_readers_pass_startup_check(self):
        extraction.require_readers()

    def test_mixed_pdf_keeps_text_and_reads_image_pages(self):
        text_page = MagicMock(images=[])
        text_page.extract_text.return_value = 'Embedded experience'
        image_page = MagicMock(images=[{'name': 'scan'}])
        image_page.extract_text.return_value = ''
        reader = MagicMock()
        reader.open.return_value.__enter__.return_value.pages = [text_page, image_page]
        with patch.object(extraction, 'pdfplumber', reader), patch.object(extraction, '_ocr_page', return_value='Scanned experience') as ocr:
            self.assertEqual(extraction.extract_text('mixed.pdf', '.pdf'), 'Embedded experience\nScanned experience')
            ocr.assert_called_once_with('mixed.pdf', 1)

    def test_blank_pdf_is_not_fabricated(self):
        page = MagicMock(images=[])
        page.extract_text.return_value = ''
        reader = MagicMock()
        reader.open.return_value.__enter__.return_value.pages = [page]
        with patch.object(extraction, 'pdfplumber', reader), patch.object(extraction, '_ocr_page') as ocr:
            self.assertIsNone(extraction.extract_text('blank.pdf', '.pdf'))
            ocr.assert_not_called()


if __name__ == '__main__':
    unittest.main()
