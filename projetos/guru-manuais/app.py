from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import os
import re
from typing import Any

import chromadb
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

from pipeline import (
    answer_question,
    chunk_pages,
    embed_query,
    embed_texts,
    extract_pdf_pages,
    index_chunks,
    record_question,
    retrieve_chunks,
)

PROJECT_DIR = Path(__file__).resolve().parent
SAMPLE_PDF = PROJECT_DIR / "data" / "manual_sintetico.pdf"
load_dotenv(PROJECT_DIR / ".env")


def _normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", question.casefold()).strip()


def _load_document(upload: Any | None) -> tuple[bytes, str]:
    if upload is not None:
        return upload.getvalue(), upload.name
    return SAMPLE_PDF.read_bytes(), SAMPLE_PDF.name


def _show_response(response: dict[str, Any]) -> None:
    st.subheader("Resposta")
    st.write(response["answer"])
    sources = response["sources"]
    if sources:
        st.subheader("Trechos usados como fonte")
        for index, source in enumerate(sources, start=1):
            pages = ", ".join(str(page) for page in source.get("pages", [])) or "sem página"
            with st.expander(f"Fonte {index} — página(s) {pages}"):
                st.write(source.get("text", ""))
    else:
        st.info("Nenhum trecho relevante foi recuperado.")
    st.caption(f"Tokens da resposta: {response['tokens']}")


def main() -> None:
    st.set_page_config(page_title="Guru dos Manuais", layout="wide")
    st.title("Guru dos Manuais")
    st.caption("Mini-RAG didático: respostas fundamentadas em trechos e páginas do PDF.")

    uploaded_pdf = st.file_uploader("Envie um PDF", type=["pdf"])
    try:
        pdf_bytes, filename = _load_document(uploaded_pdf)
    except OSError as error:
        st.error(f"Não foi possível abrir o PDF de exemplo: {error}")
        return
    document_hash = sha256(pdf_bytes).hexdigest()
    st.caption(f"Documento selecionado: {filename}")

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        st.warning("OPENAI_API_KEY não configurada. Copie .env.example para .env, adicione a chave e reinicie o app.")

    if "manual_index" not in st.session_state:
        st.session_state["manual_index"] = None
    if "manual_history" not in st.session_state:
        st.session_state["manual_history"] = []
    if "manual_answer_cache" not in st.session_state:
        st.session_state["manual_answer_cache"] = {}
    if "manual_last_response" not in st.session_state:
        st.session_state["manual_last_response"] = None

    index_state = st.session_state["manual_index"]
    if index_state is not None and index_state["hash"] != document_hash:
        st.session_state["manual_index"] = None
        st.session_state["manual_history"] = []
        st.session_state["manual_answer_cache"] = {}
        st.session_state["manual_last_response"] = None
        index_state = None

    if index_state is None:
        st.info("Indexe o documento para habilitar perguntas.")
    else:
        st.success("Este PDF já está indexado nesta sessão.")
    if st.button(
        "Indexar documento",
        type="primary",
        disabled=not bool(api_key) or index_state is not None,
    ):
        try:
            client = OpenAI(api_key=api_key)
            pages = extract_pdf_pages(pdf_bytes)
            chunks = chunk_pages(pages)
            if not chunks:
                raise ValueError("o PDF não contém texto extraível para indexar")
            embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
            vectors = embed_texts(client, [chunk.text for chunk in chunks], embedding_model, max_attempts=2)
            chroma_client = chromadb.Client()
            collection = index_chunks(chroma_client, chunks, vectors)
            st.session_state["manual_index"] = {
                "hash": document_hash,
                "collection": collection,
                "chroma_client": chroma_client,
                "chunks": chunks,
            }
            st.session_state["manual_history"] = []
            st.session_state["manual_answer_cache"] = {}
            st.session_state["manual_last_response"] = None
            st.success(f"Documento indexado: {len(pages)} páginas, {len(chunks)} trechos.")
            st.rerun()
        except Exception as error:
            st.error(f"Não foi possível indexar o documento: {error}")

    index_state = st.session_state.get("manual_index")
    if index_state is not None and index_state["hash"] == document_hash:
        question = st.text_input("Pergunte algo sobre o documento")
        if st.button("Perguntar", disabled=not bool(api_key) or not bool(question.strip())):
            normalized_question = _normalize_question(question)
            cache_key = f"{document_hash}:{normalized_question}"
            cache = st.session_state["manual_answer_cache"]
            if cache_key in cache:
                response = cache[cache_key]
                st.info("Reutilizando a resposta já calculada para esta pergunta e documento.")
            else:
                try:
                    client = OpenAI(api_key=api_key)
                    embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
                    chat_model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
                    query_vector = embed_query(
                        client, question, embedding_model, max_attempts=2
                    )
                    sources = retrieve_chunks(
                        index_state["collection"],
                        question,
                        lambda _question: query_vector,
                        top_k=3,
                    )
                    answer, tokens = answer_question(
                        question, sources, client, chat_model, max_attempts=2
                    )
                    response = {"answer": answer, "sources": sources, "tokens": tokens}
                    cache[cache_key] = response
                    st.session_state["manual_answer_cache"] = cache
                    st.session_state["manual_history"].append(
                        record_question(question, sources, tokens)
                    )
                except Exception as error:
                    st.error(f"Não foi possível responder à pergunta: {error}")
                    response = None
            if response is not None:
                st.session_state["manual_last_response"] = {
                    "document_hash": document_hash,
                    **response,
                }

        last_response = st.session_state.get("manual_last_response")
        if last_response and last_response.get("document_hash") == document_hash:
            _show_response(last_response)

        history = st.session_state["manual_history"]
        if history:
            st.subheader("Histórico de perguntas")
            st.dataframe(pd.DataFrame(history), use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
