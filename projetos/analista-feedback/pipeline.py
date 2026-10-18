from difflib import SequenceMatcher
from typing import Any
import re
import unicodedata

import pandas as pd

from schemas import FeedbackAnalysis

REVIEW_COLUMNS = {"id", "data", "id_produto", "nota", "comentario"}
PRODUCT_COLUMNS = {"id_produto", "nome", "categoria", "preco"}
NOTE_WORDS = {
    "zero": 0.0,
    "um": 1.0,
    "uma": 1.0,
    "dois": 2.0,
    "duas": 2.0,
    "tres": 3.0,
    "três": 3.0,
    "quatro": 4.0,
    "cinco": 5.0,
}
ASPECT_COLUMNS = ["nome", "categoria", "aspecto", "sentimento"]
AGGREGATE_COLUMNS = ASPECT_COLUMNS + ["quantidade"]
PROBLEM_COLUMNS = ["categoria", "aspecto", "quantidade"]


def load_feedback(review_source: Any, product_source: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the review and product CSVs from paths or file-like objects."""
    reviews = pd.read_csv(review_source)
    products = pd.read_csv(product_source)
    return reviews, products


def parse_rating(value: Any) -> float:
    """Convert numeric and Portuguese textual ratings to floats."""
    if pd.isna(value):
        return float("nan")
    text = str(value).strip().casefold()
    if not text:
        return float("nan")
    if text in NOTE_WORDS:
        return NOTE_WORDS[text]
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return float("nan")


def clean_reviews(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize dates, ratings and comments without mutating the source."""
    missing = REVIEW_COLUMNS.difference(df.columns)
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes em reviews: {', '.join(sorted(missing))}")

    cleaned = df.copy()
    cleaned["data"] = pd.to_datetime(
        cleaned["data"], format="mixed", dayfirst=True, errors="coerce"
    )
    cleaned["nota"] = cleaned["nota"].map(parse_rating).astype(float)
    cleaned["comentario"] = cleaned["comentario"].fillna("").astype(str)
    return cleaned


def normalize_comment(comment: Any) -> str:
    """Case/accent/punctuation-insensitive form used for duplicate detection."""
    if pd.isna(comment):
        return ""
    text = unicodedata.normalize("NFKD", str(comment).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text, flags=re.IGNORECASE).strip()


def remove_near_duplicates(df: pd.DataFrame, threshold: float = 0.92) -> pd.DataFrame:
    """Keep the first review per product when comments are nearly identical."""
    required = {"id_produto", "comentario"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Colunas obrigatórias ausentes: {', '.join(sorted(missing))}")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold precisa estar entre 0 e 1")

    seen_by_product: dict[Any, list[str]] = {}
    keep_indices: list[Any] = []
    for index, row in df.iterrows():
        product_id = row["id_produto"]
        if pd.isna(product_id):
            product_id = "__produto_sem_id__"
        normalized = normalize_comment(row["comentario"])
        previous = seen_by_product.setdefault(product_id, [])
        if not normalized:
            keep_indices.append(index)
            continue
        if any(SequenceMatcher(None, normalized, prior).ratio() >= threshold for prior in previous):
            continue
        keep_indices.append(index)
        previous.append(normalized)
    return df.loc[keep_indices].copy()


def merge_products(reviews: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    """Join reviews to products while enforcing one product row per ID."""
    missing_reviews = {"id_produto"}.difference(reviews.columns)
    missing_products = PRODUCT_COLUMNS.difference(products.columns)
    if missing_reviews or missing_products:
        missing = sorted(missing_reviews | missing_products)
        raise ValueError(f"Colunas obrigatórias ausentes para merge: {', '.join(missing)}")
    return reviews.merge(
        products,
        on="id_produto",
        how="left",
        validate="many_to_one",
        suffixes=("", "_produto"),
    )


def explode_aspects(df: pd.DataFrame) -> pd.DataFrame:
    """Convert nested aspect dictionaries into one row per aspect."""
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        aspects = row.get("aspectos", [])
        if not isinstance(aspects, list):
            continue
        base = row.drop(labels=["aspectos"], errors="ignore").to_dict()
        for aspect in aspects:
            if not isinstance(aspect, dict):
                continue
            rows.append({**base, **aspect})
    if not rows:
        return pd.DataFrame(columns=list(dict.fromkeys([*df.columns, *ASPECT_COLUMNS])))
    return pd.DataFrame(rows)


def aggregate_aspects(aspects: pd.DataFrame) -> pd.DataFrame:
    """Count aspects by product, product category, aspect and sentiment."""
    if aspects.empty:
        return pd.DataFrame(columns=AGGREGATE_COLUMNS)
    counts = (
        aspects.groupby(ASPECT_COLUMNS, dropna=False)
        .size()
        .reset_index(name="quantidade")
    )
    return counts.sort_values("quantidade", ascending=False, kind="stable").reset_index(drop=True)


def rank_problems_by_category(aspects: pd.DataFrame) -> pd.DataFrame:
    """Rank negative aspects by product category."""
    if aspects.empty:
        return pd.DataFrame(columns=PROBLEM_COLUMNS)
    problems = aspects.loc[aspects["sentimento"].eq("negativo")]
    if problems.empty:
        return pd.DataFrame(columns=PROBLEM_COLUMNS)
    ranking = (
        problems.groupby(["categoria", "aspecto"], dropna=False)
        .size()
        .reset_index(name="quantidade")
    )
    return ranking.sort_values(
        ["quantidade", "categoria", "aspecto"],
        ascending=[False, True, True],
        kind="stable",
    ).reset_index(drop=True)


# API-dependent functions are added in the next task; keeping pure data operations
# available here lets unit tests run without network access.
