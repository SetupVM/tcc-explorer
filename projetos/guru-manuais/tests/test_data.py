import unittest
from pathlib import Path

PDF = Path(__file__).resolve().parents[1] / "data" / "manual_sintetico.pdf"


class ManualFixtureTests(unittest.TestCase):
    def test_manual_pdf_exists_and_has_pdf_signature(self):
        self.assertTrue(PDF.exists())
        self.assertTrue(PDF.read_bytes().startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
