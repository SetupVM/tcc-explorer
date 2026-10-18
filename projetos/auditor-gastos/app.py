from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

from pipeline import build_analytics, extract_receipt, process_files

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data" / "recibos"
load_dotenv(PROJECT_DIR / ".env")


def _read_inputs(uploads: list[Any], use_samples: bool) -> list[tuple[str, bytes]]:
    if uploads:
        return [(upload.name, upload.getvalue()) for upload in uploads]
    if use_samples:
        return [
            (path.name, path.read_bytes())
            for path in sorted(DATA_DIR.iterdir())
            if path.is_file() and path.suffix.casefold() in {".txt", ".pdf"}
        ]
    return []


def _cache_key(files: list[tuple[str, bytes]], model: str) -> str:
    digest = sha256()
    for filename, content in sorted(files, key=lambda item: item[0]):
        digest.update(filename.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    digest.update(model.encode("utf-8"))
    return digest.hexdigest()


def _format_brl(value: Any) -> str:
    return "R$ " + f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _process(files: list[tuple[str, bytes]], client: OpenAI, model: str) -> dict[str, Any]:
    extractor = lambda text: extract_receipt(text, client, model)
    valid, errors = process_files(files, extractor=extractor, max_attempts=2)
    marked, monthly, item_ranking = build_analytics(valid)
    return {
        "receipts": marked,
        "monthly": monthly,
        "item_ranking": item_ranking,
        "errors": errors,
    }


def _show_results(result: dict[str, Any]) -> None:
    receipts = result["receipts"]
    errors = result["errors"]
    unique = receipts.loc[~receipts["duplicado"]] if not receipts.empty else receipts
    total_spent = unique["valor_total"].sum() if not unique.empty else 0

    columns = st.columns(4)
    columns[0].metric("Arquivos recebidos", len(receipts) + len(errors))
    columns[1].metric("Recibos válidos", len(receipts))
    columns[2].metric("Total após deduplicação", _format_brl(total_spent))
    columns[3].metric("Problemas", len(errors) + int(receipts["duplicado"].sum() if not receipts.empty else 0))

    if not result["monthly"].empty:
        st.subheader("Gastos por mês e categoria")
        st.dataframe(result["monthly"], use_container_width=True, hide_index=True)
        category_chart = (
            unique.groupby("categoria")["valor_total"]
            .sum()
            .astype(float)
            .sort_values(ascending=False)
            .to_frame("valor_total")
        )
        st.bar_chart(category_chart)
    else:
        st.info("Ainda não há recibos válidos para agregar.")

    st.subheader("Ranking dos itens mais caros")
    if result["item_ranking"].empty:
        st.info("Nenhum item foi extraído.")
    else:
        st.dataframe(result["item_ranking"], use_container_width=True, hide_index=True)
        st.bar_chart(result["item_ranking"].set_index("descricao")["valor"].astype(float))

    st.subheader("Recibos consolidados")
    if receipts.empty:
        st.info("Nenhum recibo válido.")
    else:
        st.dataframe(receipts, use_container_width=True, hide_index=True)

    if not errors.empty:
        st.subheader("Arquivos com falha ou inconsistência")
        st.dataframe(errors, use_container_width=True, hide_index=True)


def main() -> None:
    st.set_page_config(page_title="Auditor de Gastos", layout="wide")
    st.title("Auditor de Gastos")
    st.caption("Exemplo didático com recibos sintéticos. PDFs escaneados não passam por OCR.")

    uploads = st.file_uploader(
        "Envie recibos TXT ou PDF",
        type=["txt", "pdf"],
        accept_multiple_files=True,
    )
    use_samples = st.checkbox("Usar recibos sintéticos de exemplo", value=True)
    files = _read_inputs(uploads or [], use_samples)
    if not files:
        st.info("Envie um ou mais recibos ou selecione os exemplos sintéticos.")
        return
    st.caption(f"Arquivos selecionados: {len(files)}")

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        st.warning("OPENAI_API_KEY não configurada. Copie .env.example para .env e adicione sua chave.")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    cache_key = _cache_key(files, model)
    cache: dict[str, dict[str, Any]] = st.session_state.setdefault("expense_cache", {})
    if st.button("Processar recibos", type="primary", disabled=not bool(api_key)):
        if cache_key in cache:
            st.session_state["expense_active_key"] = cache_key
            st.info("Reutilizando resultados já calculados para estes arquivos.")
        else:
            try:
                client = OpenAI(api_key=api_key)
                cache[cache_key] = _process(files, client, model)
                st.session_state["expense_cache"] = cache
                st.session_state["expense_active_key"] = cache_key
            except Exception as error:
                st.error(f"Não foi possível processar os recibos: {error}")

    if st.session_state.get("expense_active_key") == cache_key and cache_key in cache:
        _show_results(cache[cache_key])


if __name__ == "__main__":
    main()
