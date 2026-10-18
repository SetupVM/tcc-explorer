from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable
import json
import re
from uuid import uuid4

from PyPDF2 import PdfReader


@dataclass(frozen=True)
class TextChunk:
    id: str
    text: str
    pages: list[int]


def extract_pdf_pages(content: bytes) -> list[tuple[int, str]]:
    """Extract selectable text from each page, keeping 1-based page numbers."""
    reader = PdfReader(BytesIO(content))
    return [
        (page_number, page.extract_text() or "")
        for page_number, page in enumerate(reader.pages, start=1)
    ]


def clean_page_text(text: str) -> str:
    """Remove repeating fixture headers and normalize whitespace."""
    kept_lines = []
    for line in text.replace("\r", "\n").splitlines():
        stripped = line.strip()
        if stripped.casefold() == "manual ficticio" or re.fullmatch(
            r"Pagina\s+\d+", stripped, flags=re.IGNORECASE
        ):
            continue
        if stripped:
            kept_lines.append(stripped)
    return re.sub(r"\s+", " ", " ".join(kept_lines)).strip()


def chunk_pages(
    pages: list[tuple[int, str]],
    chunk_size: int = 800,
    overlap: int = 120,
) -> list[TextChunk]:
    """Split each page into overlapping character chunks with page metadata."""
    if overlap < 0 or chunk_size <= 0 or chunk_size <= overlap:
        raise ValueError("chunk_size precisa ser maior que overlap >= 0")

    chunks: list[TextChunk] = []
    step = chunk_size - overlap
    for page_number, raw_text in pages:
        text = clean_page_text(raw_text)
        if not text:
            continue
        start = 0
        chunk_index = 0
        while start < len(text):
            chunk_text = text[start : start + chunk_size].strip()
            if chunk_text:
                chunks.append(
                    TextChunk(
                        id=f"p{page_number}-c{chunk_index}",
                        text=chunk_text,
                        pages=[page_number],
                    )
                )
                chunk_index += 1
            if start + chunk_size >= len(text):
                break
            start += step
    return chunks


def _bounded_embedding_call(call: Callable[[], Any], max_attempts: int) -> Any:
    if max_attempts < 1:
        raise ValueError("max_attempts precisa ser pelo menos 1")
    last_error: Exception | None = None
    for _ in range(max_attempts):
        try:
            return call()
        except Exception as error:
            last_error = error
    assert last_error is not None
    raise last_error


def embed_texts(
    client: Any,
    texts: list[str],
    model: str,
    max_attempts: int = 2,
) -> list[list[float]]:
    """Create embeddings in input order, retrying only a bounded number of times."""
    if not texts:
        return []
    response = _bounded_embedding_call(
        lambda: client.embeddings.create(model=model, input=texts), max_attempts
    )
    embeddings = [list(item.embedding) for item in response.data]
    if len(embeddings) != len(texts):
        raise ValueError("a API de embeddings retornou uma quantidade inesperada de vetores")
    return embeddings


def embed_query(client: Any, text: str, model: str, max_attempts: int = 2) -> list[float]:
    """Embed a single query using the same bounded retry policy as document vectors."""
    vectors = embed_texts(client, [text], model, max_attempts=max_attempts)
    return vectors[0]


def index_chunks(
    chroma_client: Any,
    chunks: list[TextChunk],
    embeddings: list[list[float]],
) -> Any:
    """Store chunks and their vectors in a unique in-memory Chroma collection."""
    if len(chunks) != len(embeddings):
        raise ValueError("cada chunk precisa ter exatamente um embedding")
    if not chunks:
        raise ValueError("não há chunks para indexar")
    collection = chroma_client.create_collection(name=f"manual_{uuid4().hex}")
    collection.add(
        ids=[chunk.id for chunk in chunks],
        documents=[chunk.text for chunk in chunks],
        embeddings=embeddings,
        metadatas=[{"pages": json.dumps(chunk.pages)} for chunk in chunks],
    )
    return collection


def retrieve_chunks(
    collection: Any,
    question: str,
    embed_query_fn: Callable[[str], list[float]],
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Retrieve the nearest chunks and decode their source-page metadata."""
    if top_k < 1:
        raise ValueError("top_k precisa ser pelo menos 1")
    result = collection.query(
        query_embeddings=[embed_query_fn(question)],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    sources: list[dict[str, Any]] = []
    for index, document in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) else {}
        pages_value = metadata.get("pages", "[]") if metadata else "[]"
        if isinstance(pages_value, str):
            try:
                pages = json.loads(pages_value)
            except json.JSONDecodeError:
                pages = []
        else:
            pages = pages_value
        distance = distances[index] if index < len(distances) else None
        sources.append({"text": document, "pages": pages, "distance": distance})
    return sources


def answer_question(
    question: str,
    sources: list[dict[str, Any]],
    client: Any,
    model: str,
    max_attempts: int = 2,
) -> tuple[str, int]:
    """Answer from retrieved context only, with bounded API retries."""
    if not sources:
        return "Não encontrei no documento.", 0
    if max_attempts < 1:
        raise ValueError("max_attempts precisa ser pelo menos 1")

    context_parts = []
    for source in sources:
        pages = ", ".join(str(page) for page in source.get("pages", []))
        context_parts.append(f"[p. {pages}] {source.get('text', '')}")
    context = "\n\n".join(context_parts)
    system_prompt = (
        "Responda somente com base no contexto fornecido. "
        "Se o contexto não contiver a resposta, responda exatamente "
        "'Não encontrei no documento.'. Cite apenas páginas indicadas como [p. N]. "
        "Não invente regras, fatos ou páginas."
    )
    last_error: Exception | None = None
    for _ in range(max_attempts):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0.1,
                max_tokens=500,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Contexto:\n{context}\n\nPergunta: {question}"},
                ],
            )
            answer = response.choices[0].message.content
            if not answer:
                raise ValueError("a API não retornou uma resposta")
            tokens = getattr(getattr(response, "usage", None), "total_tokens", 0) or 0
            return answer, int(tokens)
        except Exception as error:
            last_error = error
    assert last_error is not None
    raise last_error


def record_question(
    question: str,
    sources: list[dict[str, Any]],
    tokens: int,
) -> dict[str, Any]:
    """Create one history row with the question, citations and chat token count."""
    pages = sorted({page for source in sources for page in source.get("pages", [])})
    return {
        "pergunta": question,
        "trechos": [source.get("text", "") for source in sources],
        "paginas": pages,
        "tokens": int(tokens),
    }
