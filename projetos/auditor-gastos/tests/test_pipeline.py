import sys
import unittest
from decimal import Decimal
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas import Receipt, ReceiptItem
from pipeline import parse_brl_amount, process_files, validate_receipt


class ReceiptValidationTests(unittest.TestCase):
    def make_receipt(self, total="36.50"):
        return Receipt(
            estabelecimento="Mercado Bom Preco",
            data="2025-01-10",
            itens=[
                ReceiptItem(descricao="Arroz", quantidade=2, valor=Decimal("28.00")),
                ReceiptItem(descricao="Feijao", quantidade=1, valor=Decimal("8.50")),
            ],
            valor_total=Decimal(total),
            categoria="alimentação",
        )

    def test_brazilian_currency_and_tolerance(self):
        self.assertEqual(parse_brl_amount("R$ 1.234,56"), Decimal("1234.56"))
        self.assertEqual(validate_receipt(self.make_receipt()), [])
        self.assertTrue(validate_receipt(self.make_receipt("40.00")))

    def test_negative_value_is_rejected_by_schema(self):
        with self.assertRaises(ValueError):
            ReceiptItem(descricao="Item", quantidade=1, valor=Decimal("-1"))

    def test_invalid_date_is_rejected_by_schema(self):
        with self.assertRaises(ValueError):
            Receipt(
                estabelecimento="Loja",
                data="2025-19-40",
                itens=[],
                valor_total=0,
                categoria="outros",
            )

    def test_bad_file_does_not_abort_batch(self):
        files = [("ruim.txt", b""), ("bom.txt", b"texto do recibo")]

        def fake_extractor(text):
            return self.make_receipt()

        valid, errors = process_files(files, extractor=fake_extractor, max_attempts=2)
        self.assertEqual(len(valid), 1)
        self.assertEqual(errors.loc[0, "arquivo"], "ruim.txt")

    def test_validation_retry_is_bounded(self):
        calls = []

        def mismatched_extractor(text):
            calls.append(text)
            return self.make_receipt("99.00")

        valid, errors = process_files(
            [("bom.txt", b"texto")], extractor=mismatched_extractor, max_attempts=2
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(valid), 0)
        self.assertEqual(errors.loc[0, "arquivo"], "bom.txt")

    def test_pdf_text_is_read_and_blank_pdf_is_reported(self):
        from pipeline import read_receipt_text

        data = Path(__file__).resolve().parents[1] / "data" / "recibos"
        text = read_receipt_text(
            "mercado_01_copia.pdf", (data / "mercado_01_copia.pdf").read_bytes()
        )
        self.assertIn("MERCADO BOM PRECO", text)
        with self.assertRaises(ValueError):
            read_receipt_text(
                "recibo_sem_texto.pdf", (data / "recibo_sem_texto.pdf").read_bytes()
            )


if __name__ == "__main__":
    unittest.main()
