import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import clean_page_text, chunk_pages, extract_pdf_pages


class DocumentPipelineTests(unittest.TestCase):
    def test_cleaning_removes_header_and_collapses_whitespace(self):
        text = "MANUAL FICTICIO\nPagina 7\n\n  Regra   de   teste.  "
        self.assertEqual(clean_page_text(text), "Regra de teste.")

    def test_chunks_keep_source_page_and_overlap(self):
        chunks = chunk_pages([(7, "abcdefghijklmnopqrst")], chunk_size=10, overlap=3)
        self.assertEqual(chunks[0].pages, [7])
        self.assertEqual(chunks[0].text[-3:], chunks[1].text[:3])

    def test_pdf_extraction_numbers_pages_from_one(self):
        content = (Path(__file__).resolve().parents[1] / "data" / "manual_sintetico.pdf").read_bytes()
        pages = extract_pdf_pages(content)
        self.assertEqual(len(pages), 20)
        self.assertEqual(pages[5][0], 6)
        self.assertIn("No inicio do turno", pages[5][1])


if __name__ == "__main__":
    unittest.main()
