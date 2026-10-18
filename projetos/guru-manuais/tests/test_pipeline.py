import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import clean_page_text, chunk_pages, extract_pdf_pages


class DocumentPipelineTests(unittest.TestCase):
    def test_cleaning_removes_header_and_collapses_whitespace(self):
        text = "MANUAL FICTICIO\nPagina 7\n\n  Regra   de   teste.  "
        self.assertEqual(clean_page_text(text), "Regra de teste.")

    def test_chunks_keep_source_page_and_overlap(self):
        chunks = chunk_pages([(7, "abcdefghijklmnopqrst")], chunk_size=10, overlap=3)
        self.assertEqual(chunks[0].pages, [7])
        self.assertEqual(chunks[0].text[-3:], chunks[1].text[:3])

    def test_pdf_extraction_numbers_pages_from_one(self):
        content = (Path(__file__).resolve().parents[1] / "data" / "manual_sintetico.pdf").read_bytes()
        pages = extract_pdf_pages(content)
        self.assertEqual(len(pages), 20)
        self.assertEqual(pages[5][0], 6)
        self.assertIn("No inicio do turno", pages[5][1])


import json
from types import SimpleNamespace

from pipeline import TextChunk, answer_question, embed_texts, index_chunks, record_question, retrieve_chunks


class FakeCollection:
    def query(self, **kwargs):
        self.kwargs = kwargs
        return {
            "documents": [["regra da pagina seis"]],
            "metadatas": [[{"pages": "[6]"}]],
            "distances": [[0.1]],
        }


class FakeAddCollection:
    def add(self, **kwargs):
        self.kwargs = kwargs


class FakeChromaClient:
    def create_collection(self, **kwargs):
        self.collection = FakeAddCollection()
        return self.collection


class FakeEmbeddingClient:
    def __init__(self):
        self.calls = 0
        self.fail_times = 0
        self.embeddings = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("falha temporaria")
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2]) for _ in kwargs["input"]]
        )


class FakeChatClient:
    def __init__(self):
        self.calls = 0
        self.fail_times = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("falha temporaria")
        usage = SimpleNamespace(prompt_tokens=20, completion_tokens=8, total_tokens=28)
        message = SimpleNamespace(content="Compre duas cartas. [p. 6]")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


class RetrievalTests(unittest.TestCase):
    def test_retrieval_keeps_page_metadata(self):
        collection = FakeCollection()
        sources = retrieve_chunks(
            collection, "quantas cartas?", lambda question: [0.1, 0.2], top_k=1
        )
        self.assertEqual(sources[0]["pages"], [6])
        self.assertEqual(collection.kwargs["n_results"], 1)

    def test_index_serializes_pages_as_chroma_scalar_metadata(self):
        chroma = FakeChromaClient()
        collection = index_chunks(chroma, [TextChunk("p6-c0", "regra", [6])], [[0.1, 0.2]])
        self.assertEqual(json.loads(collection.kwargs["metadatas"][0]["pages"]), [6])

    def test_embedding_function_returns_vectors_in_order(self):
        client = FakeEmbeddingClient()
        vectors = embed_texts(client, ["um", "dois"], "fake", max_attempts=2)
        self.assertEqual(vectors, [[0.1, 0.2], [0.1, 0.2]])
        self.assertEqual(client.calls, 1)

    def test_embedding_retry_is_bounded(self):
        client = FakeEmbeddingClient()
        client.fail_times = 1
        vectors = embed_texts(client, ["um"], "fake", max_attempts=2)
        self.assertEqual(vectors, [[0.1, 0.2]])
        self.assertEqual(client.calls, 2)

    def test_answer_is_not_called_without_sources(self):
        client = FakeChatClient()
        answer, tokens = answer_question("pergunta", [], client, "fake")
        self.assertEqual(answer, "Não encontrei no documento.")
        self.assertEqual(tokens, 0)
        self.assertEqual(client.calls, 0)

    def test_answer_and_history_include_source_page_and_tokens(self):
        client = FakeChatClient()
        sources = [{"text": "regra", "pages": [6], "distance": 0.1}]
        answer, tokens = answer_question("quantas cartas?", sources, client, "fake")
        row = record_question("quantas cartas?", sources, tokens)
        self.assertIn("duas cartas", answer)
        self.assertEqual(tokens, 28)
        self.assertEqual(row["paginas"], [6])

    def test_chat_retry_is_limited_to_two_attempts(self):
        client = FakeChatClient()
        client.fail_times = 1
        sources = [{"text": "regra", "pages": [6], "distance": 0.1}]
        answer, _ = answer_question("quantas cartas?", sources, client, "fake", max_attempts=2)
        self.assertIn("duas cartas", answer)
        self.assertEqual(client.calls, 2)

    def test_chat_failure_stops_after_max_attempts(self):
        client = FakeChatClient()
        client.fail_times = 9
        sources = [{"text": "regra", "pages": [6], "distance": 0.1}]
        with self.assertRaises(RuntimeError):
            answer_question("pergunta", sources, client, "fake", max_attempts=2)
        self.assertEqual(client.calls, 2)


if __name__ == "__main__":
    unittest.main()
