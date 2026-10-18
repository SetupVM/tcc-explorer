import unittest
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "recibos"


class ReceiptDatasetTests(unittest.TestCase):
    def test_dataset_has_25_mixed_files_and_problem_samples(self):
        files = sorted(path for path in DATA.iterdir() if path.is_file())
        self.assertEqual(len(files), 25)
        self.assertEqual(sum(path.suffix == ".txt" for path in files), 16)
        self.assertEqual(sum(path.suffix == ".pdf" for path in files), 9)
        self.assertTrue((DATA / "recibo_incompleto.txt").exists())
        self.assertTrue((DATA / "recibo_sem_texto.pdf").exists())
        self.assertTrue((DATA / "mercado_01_copia.pdf").exists())
        self.assertIn("R$ 1.234,56", (DATA / "recibo_15.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
