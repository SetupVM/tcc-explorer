import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import (
    aggregate_aspects,
    clean_reviews,
    explode_aspects,
    load_feedback,
    merge_products,
    rank_problems_by_category,
    remove_near_duplicates,
)


class FeedbackTransformTests(unittest.TestCase):
    def test_clean_reviews_parses_notes_dates_and_keeps_empty_comment(self):
        raw = pd.DataFrame(
            {
                "id": [1, 2, 3],
                "data": ["03/01/2025", "2025-01-04", "Jan 05 2025"],
                "id_produto": [1, 1, 2],
                "nota": ["cinco", "4,5", ""],
                "comentario": ["bom", "ok", ""],
            }
        )
        result = clean_reviews(raw)
        self.assertEqual(result.loc[0, "nota"], 5.0)
        self.assertEqual(result.loc[1, "nota"], 4.5)
        self.assertTrue(pd.isna(result.loc[2, "nota"]))
        self.assertTrue(pd.notna(result.loc[0, "data"]))
        self.assertEqual(result.loc[2, "comentario"], "")

    def test_load_feedback_accepts_file_like_objects(self):
        from io import StringIO

        reviews = StringIO("id,data,id_produto,nota,comentario\n1,2025-01-01,1,5,bom\n")
        products = StringIO("id_produto,nome,categoria,preco\n1,Fone,eletronicos,10\n")
        loaded_reviews, loaded_products = load_feedback(reviews, products)
        self.assertEqual(len(loaded_reviews), 1)
        self.assertEqual(loaded_products.loc[0, "nome"], "Fone")

    def test_near_duplicate_criterion_is_case_and_accent_insensitive(self):
        raw = pd.DataFrame(
            {
                "id_produto": [1, 1],
                "comentario": [
                    "Entrega rápida, produto excelente!",
                    "ENTREGA rapida - produto excelente.",
                ],
            }
        )
        self.assertEqual(len(remove_near_duplicates(raw)), 1)

    def test_merge_and_aspect_aggregation(self):
        reviews = pd.DataFrame({"id_produto": [1], "comentario": ["bom"]})
        products = pd.DataFrame(
            {"id_produto": [1], "nome": ["Fone"], "categoria": ["eletronicos"], "preco": [100.0]}
        )
        merged = merge_products(reviews, products)
        self.assertEqual(merged.loc[0, "nome"], "Fone")
        enriched = merged.assign(
            aspectos=[
                [
                    {"aspecto": "qualidade", "sentimento": "positivo"},
                    {"aspecto": "entrega", "sentimento": "negativo"},
                ]
            ]
        )
        aspects = explode_aspects(enriched)
        summary = aggregate_aspects(aspects)
        ranking = rank_problems_by_category(aspects)
        self.assertEqual(int(summary["quantidade"].sum()), 2)
        self.assertEqual(ranking.loc[0, "aspecto"], "entrega")
        self.assertEqual(ranking.loc[0, "categoria"], "eletronicos")


if __name__ == "__main__":
    unittest.main()
