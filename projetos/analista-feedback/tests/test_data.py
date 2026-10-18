import csv
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data"


class DatasetTests(unittest.TestCase):
    def test_reviews_have_required_shape_and_examples(self):
        with (ROOT / "reviews_loja.csv").open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 300)
        self.assertEqual(set(rows[0]), {"id", "data", "id_produto", "nota", "comentario"})
        by_id = {row["id"]: row for row in rows}
        self.assertEqual(by_id["2"]["comentario"], "Ótimo, quebrou no segundo dia.")
        self.assertEqual(by_id["3"]["comentario"], "The delivery was late, but the product works.")
        self.assertEqual(by_id["4"]["comentario"], "")
        self.assertEqual(by_id["5"]["nota"], "cinco")
        self.assertEqual(by_id["6"]["nota"], "4,5")
        self.assertEqual(by_id["1"]["comentario"], by_id["7"]["comentario"])
        self.assertEqual(by_id["5"]["id_produto"], by_id["6"]["id_produto"])
        self.assertTrue(any("😊" in row["comentario"] for row in rows))
        self.assertTrue(any(row["nota"] == "" for row in rows))
        self.assertGreaterEqual(len({row["data"] for row in rows}), 3)

    def test_products_have_rows_and_required_shape(self):
        with (ROOT / "produtos.csv").open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertGreaterEqual(len(rows), 10)
        self.assertEqual(set(rows[0]), {"id_produto", "nome", "categoria", "preco"})


if __name__ == "__main__":
    unittest.main()
