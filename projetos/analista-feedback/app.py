from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

from pipeline import (
    aggregate_aspects,
    clean_reviews,
    enrich_reviews,
    explode_aspects,
    find_rating_conflicts,
    load_feedback,
    merge_products,
    rank_problems_by_category,
    remove_near_duplicates,
)

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
load_dotenv(PROJECT_DIR / ".env")


def _read_selected_files(
    review_upload: Any,
    product_upload: Any,
    use_samples: bool,
) -> tuple[bytes, bytes, str] | None:
    if review_upload is not None or product_upload is not None:
        if review_upload is None or product_upload is None:
            st.warning("Envie os dois arquivos CSV para continuar.")
            return None
        return review_upload.getvalue(), product_upload.getvalue(), "arquivos enviados"

    if use_samples:
        review_path = DATA_DIR / "reviews_loja.csv"
        product_path = DATA_DIR / "produtos.csv"
        return review_path.read_bytes(), product_path.read_bytes(), "dataset sintético"
    return None


def _analysis_key(review_bytes: bytes, product_bytes: bytes) -> str:
    digest = sha256()
    digest.update(review_bytes)
    digest.update(b"\0")
    digest.update(product_bytes)
    return digest.hexdigest()


def _run_pipeline(
    review_bytes: bytes,
    product_bytes: bytes,
    client: OpenAI,
    model: str,
) -> dict[str, Any]:
    reviews, products = load_feedback(BytesIO(review_bytes), BytesIO(product_bytes))
    cleaned = clean_reviews(reviews)
    unique_reviews = remove_near_duplicates(cleaned)
    merged = merge_products(unique_reviews, products)
    enriched, errors = enrich_reviews(merged, client, model, max_attempts=2)
    aspects = explode_aspects(enriched)
    return {
        "raw_count": len(reviews),
        "unique_count": len(unique_reviews),
        "enriched": enriched,
        "errors": errors,
        "aspects": aspects,
        "summary": aggregate_aspects(aspects),
        "ranking": rank_problems_by_category(aspects),
        "conflicts": find_rating_conflicts(enriched)
        if not enriched.empty
        else enriched.copy(),
    }


def _show_results(result: dict[str, Any]) -> None:
    enriched = result["enriched"]
    errors = result["errors"]
    aspects = result["aspects"]

    metric_columns = st.columns(4)
    metric_columns[0].metric("Reviews recebidos", result["raw_count"])
    metric_columns[1].metric("Após deduplicação", result["unique_count"])
    metric_columns[2].metric("Analisados", len(enriched))
    metric_columns[3].metric("Falhas", len(errors))

    if not result["summary"].empty:
        st.subheader("Aspectos por produto e sentimento")
        chart = (
            aspects.groupby(["aspecto", "sentimento"])
            .size()
            .unstack(fill_value=0)
            .sort_index()
        )
        st.bar_chart(chart)
        st.dataframe(result["summary"], use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum aspecto foi extraído dos comentários processados.")

    st.subheader("Ranking de problemas por categoria")
    if result["ranking"].empty:
        st.info("Não foram encontrados aspectos negativos.")
    else:
        st.dataframe(result["ranking"], use_container_width=True, hide_index=True)

    st.subheader("Notas que contradizem o sentimento")
    if result["conflicts"].empty:
        st.info("Nenhuma contradição encontrada.")
    else:
        st.dataframe(
            result["conflicts"][
                ["id", "nome", "nota", "sentimento_geral", "comentario"]
            ],
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Drill-down dos comentários")
    if aspects.empty:
        st.info("Não há comentários com aspectos para filtrar.")
    else:
        products = ["Todos"] + sorted(aspects["nome"].dropna().astype(str).unique().tolist())
        aspect_names = ["Todos"] + sorted(aspects["aspecto"].dropna().unique().tolist())
        sentiments = ["Todos"] + sorted(aspects["sentimento"].dropna().unique().tolist())
        product_col, aspect_col, sentiment_col = st.columns(3)
        selected_product = product_col.selectbox("Produto", products)
        selected_aspect = aspect_col.selectbox("Aspecto", aspect_names)
        selected_sentiment = sentiment_col.selectbox("Sentimento", sentiments)
        filtered = aspects
        if selected_product != "Todos":
            filtered = filtered.loc[filtered["nome"].astype(str).eq(selected_product)]
        if selected_aspect != "Todos":
            filtered = filtered.loc[filtered["aspecto"].eq(selected_aspect)]
        if selected_sentiment != "Todos":
            filtered = filtered.loc[filtered["sentimento"].eq(selected_sentiment)]
        columns = [
            column
            for column in [
                "id",
                "data",
                "nome",
                "categoria",
                "nota",
                "aspecto",
                "sentimento",
                "comentario",
                "urgente",
            ]
            if column in filtered.columns
        ]
        st.dataframe(filtered[columns], use_container_width=True, hide_index=True)

    if not errors.empty:
        st.subheader("Comentários que não puderam ser analisados")
        st.dataframe(errors, use_container_width=True, hide_index=True)


def main() -> None:
    st.set_page_config(page_title="Analista de Feedback", layout="wide")
    st.title("Analista de Feedback")
    st.caption("Exemplo didático com dados sintéticos. Configure uma chave OpenAI para classificar comentários.")

    review_upload = st.file_uploader("Reviews (CSV)", type=["csv"], key="reviews_upload")
    product_upload = st.file_uploader("Produtos (CSV)", type=["csv"], key="products_upload")
    use_samples = st.checkbox("Usar dados sintéticos de exemplo", value=True)
    selected_files = _read_selected_files(review_upload, product_upload, use_samples)
    if selected_files is None:
        st.info("Envie os dois CSVs ou selecione os dados sintéticos para começar.")
        return

    review_bytes, product_bytes, source_label = selected_files
    st.caption(f"Entrada selecionada: {source_label}")
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        st.warning("OPENAI_API_KEY não configurada. Copie .env.example para .env, adicione a chave e reinicie o app.")

    cache_key = _analysis_key(review_bytes, product_bytes)
    cache: dict[str, dict[str, Any]] = st.session_state.setdefault("feedback_cache", {})
    if st.button("Analisar comentários", type="primary", disabled=not bool(api_key)):
        if cache_key in cache:
            st.session_state["feedback_active_key"] = cache_key
            st.info("Reutilizando o resultado já calculado para estes arquivos.")
        else:
            try:
                client = OpenAI(api_key=api_key)
                model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
                cache[cache_key] = _run_pipeline(review_bytes, product_bytes, client, model)
                st.session_state["feedback_cache"] = cache
                st.session_state["feedback_active_key"] = cache_key
            except Exception as error:
                st.error(f"Não foi possível processar os arquivos: {error}")

    active_key = st.session_state.get("feedback_active_key")
    if active_key == cache_key and cache_key in cache:
        _show_results(cache[cache_key])


if __name__ == "__main__":
    main()
