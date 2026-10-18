# Guru dos Manuais Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar um starter Mini-RAG que lê PDF página a página, recupera trechos com ChromaDB, responde com fontes e registra perguntas.

**Architecture:** `pipeline.py` separa extração/limpeza/chunking, embeddings e busca vetorial da geração de resposta. ChromaDB roda em memória; chunks conservam números de página. `app.py` controla upload, pergunta, fontes e histórico em sessão Streamlit, usando o PDF sintético como demonstração padrão.

**Tech Stack:** Python 3.10+, Pandas, OpenAI, python-dotenv, PyPDF2, ChromaDB, Streamlit, `unittest`.

**Spec:** [`docs/superpowers/specs/2026-10-18-projetos-finais-design.md`](../specs/2026-10-18-projetos-finais-design.md)

## Global Constraints

- `manual_sintetico.pdf` terá 20 páginas de conteúdo fictício, mas coerente, sobre regras de um jogo/manual.
- O texto será distribuído por página de modo que perguntas sobre regras específicas tenham respostas e fontes verificáveis. O material não usará conteúdo protegido de terceiros.
- Usar OpenAI como provedor inicial, coerente com as dependências já presentes no repositório; nomes de modelos ficam configuráveis por variáveis de ambiente documentadas em `.env.example`.
- Nunca incluir uma chave real nos exemplos. Os `.gitignore` da raiz e dos três projetos ignorarão ambientes virtuais, arquivos `.env`, caches Python e dados locais do ChromaDB, sem ignorar os datasets de exemplo.
- As chamadas de IA terão `temperature`, `max_tokens` e limite pequeno de tentativas explícitos. Exceções de API, leitura de arquivo, parsing ou validação serão apresentadas como problemas por registro/arquivo, sem descartar resultados válidos do restante do lote.
- Não serão feitas chamadas pagas à API durante os testes. Não será alterado o conteúdo de `projeto-final.md`.

---

## File Structure

- Create `projetos/guru-manuais/app.py` — interface de upload/pergunta e apresentação de fontes/histórico.
- Create `projetos/guru-manuais/pipeline.py` — extração de páginas, limpeza, chunks, embeddings, busca, resposta e log.
- Create `projetos/guru-manuais/requirements.txt` — dependências runtime específicas.
- Create `projetos/guru-manuais/.env.example` and `.gitignore` — configuração sem chave e exclusão de artefatos locais.
- Create `projetos/guru-manuais/README.md` — instruções e gabarito por página.
- Create `projetos/guru-manuais/data/manual_sintetico.pdf` — manual sintético de 20 páginas.
- Create `projetos/guru-manuais/tests/test_data.py`, `test_pipeline.py`, and `test_app_smoke.py` — testes locais sem API.
- Modify root `README.md` — acrescentar o terceiro link no índice após os planos dos outros dois modelos.

## Recommended Execution Order

Execute após `2026-10-18-analista-feedback.md` e `2026-10-18-auditor-gastos.md`. A aplicação RAG é isolada; a ordem permite completar o índice da raiz com links para três diretórios existentes.

---

### Task 1: Configuração e manual sintético de 20 páginas

**Files:**
- Create: `projetos/guru-manuais/requirements.txt`
- Create: `projetos/guru-manuais/.env.example`
- Create: `projetos/guru-manuais/.gitignore`
- Create: `projetos/guru-manuais/data/manual_sintetico.pdf`
- Create: `projetos/guru-manuais/tests/test_data.py`

**Interfaces:**
- PDF contém exatamente 20 páginas extraíveis.
- Página 6 contém a regra `No inicio do turno, cada jogador compra duas cartas.`; esta frase será o gabarito conhecido para validar fontes.

- [x] **Step 1: Escrever teste de presença do PDF**

```python
# projetos/guru-manuais/tests/test_data.py
import unittest
from pathlib import Path

PDF = Path(__file__).resolve().parents[1] / "data" / "manual_sintetico.pdf"

class ManualFixtureTests(unittest.TestCase):
    def test_manual_pdf_exists_and_has_pdf_signature(self):
        self.assertTrue(PDF.exists())
        self.assertTrue(PDF.read_bytes().startswith(b"%PDF-"))

if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Executar para confirmar falha por PDF ausente**

Run: `python3 -m unittest discover -s projetos/guru-manuais/tests -p 'test_data.py' -v`  
Expected: FAIL porque `manual_sintetico.pdf` ainda não existe.

- [x] **Step 3: Criar configuração e PDF estático**

```text
# requirements.txt
openai>=1.55,<3
python-dotenv>=1.0,<2
pandas>=2.0,<3
streamlit>=1.32,<2
PyPDF2>=3.0,<4
chromadb>=0.5,<2
```

```dotenv
# .env.example
OPENAI_API_KEY=
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

```gitignore
.env
.venv/
venv/
__pycache__/
*.py[cod]
.streamlit/secrets.toml
.chroma/
chroma_db/
```

Gere o PDF como fixture estático usando ReportLab em um ambiente temporário (não acrescente ReportLab ao `requirements.txt`, pois o app só lê PDFs). Use `python3 -m venv /tmp/manual-pdf-env` e `/tmp/manual-pdf-env/bin/pip install reportlab`; a partir da raiz do repositório, combine os dois blocos Python abaixo em `/tmp/build_manual.py` e rode `/tmp/manual-pdf-env/bin/python /tmp/build_manual.py`. Use 20 páginas e estes textos de regras, mantendo exatamente a frase da página 6:

```python
PAGES = [
    "Objetivo: explorar a ilha e recuperar tres artefatos antes do inverno.",
    "Componentes: mapa, cartas de trilha, marcadores de energia e artefatos.",
    "Preparacao: cada jogador inicia com quatro pontos de energia.",
    "Participantes: a partida aceita de dois a quatro exploradores.",
    "Primeiro jogador: comeca quem visitou uma floresta mais recentemente.",
    "No inicio do turno, cada jogador compra duas cartas.",
    "Acao: depois de comprar, o jogador pode mover ou usar um item.",
    "Movimento: cada ponto de energia permite atravessar uma regiao.",
    "Floresta: entrar na floresta custa um ponto extra de energia.",
    "Encontro: uma criatura pode ser evitada descartando uma carta de trilha.",
    "Ferimento: ao perder energia, reduza o marcador; energia zero encerra o turno.",
    "Itens: cada explorador pode carregar no maximo tres itens.",
    "Fim do turno: descarte ate ficar com cinco cartas na mao.",
    "Rodada: depois do ultimo explorador, avance o marcador de clima.",
    "Inverno: quando o marcador chega ao quarto espaco, inicia a rodada final.",
    "Vitoria: o grupo vence ao reunir os tres artefatos e voltar ao acampamento.",
    "Empate: se varios jogadores completarem a tarefa juntos, todos vencem.",
    "Penalidade: uma carta fora de turno deve voltar para o fundo do baralho.",
    "Cooperacao: jogadores podem trocar um item quando ocupam a mesma regiao.",
    "Glossario: uma regiao e um espaco adjacente indicado por uma linha no mapa.",
]
```

Use este código para gravar o PDF no caminho indicado; o cabeçalho fica em uma linha própria para que a limpeza posterior possa removê-lo:

```python
from pathlib import Path
from textwrap import wrap
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

path = Path("projetos/guru-manuais/data/manual_sintetico.pdf")
path.parent.mkdir(parents=True, exist_ok=True)
pdf = canvas.Canvas(str(path), pagesize=A4)
for page_number, text in enumerate(PAGES, start=1):
    pdf.setFont("Helvetica", 10)
    pdf.drawString(48, 810, "MANUAL FICTICIO")
    pdf.drawString(48, 790, f"Pagina {page_number}")
    y = 750
    for line in wrap(text, 85):
        pdf.drawString(48, y, line)
        y -= 18
    pdf.showPage()
pdf.save()
```

Crie `.venv` e instale as dependências runtime com `python3 -m venv projetos/guru-manuais/.venv` e `projetos/guru-manuais/.venv/bin/python -m pip install -r projetos/guru-manuais/requirements.txt`.

- [x] **Step 4: Rodar o teste da fixture**

Run: `projetos/guru-manuais/.venv/bin/python -m unittest discover -s projetos/guru-manuais/tests -p 'test_data.py' -v`  
Expected: PASS; o arquivo existe e começa com a assinatura `%PDF-`; extração e regra da página 6 são verificadas no Task 2.

- [x] **Step 5: Commitar a entrega**

```bash
git add projetos/guru-manuais/requirements.txt projetos/guru-manuais/.env.example projetos/guru-manuais/.gitignore projetos/guru-manuais/data/manual_sintetico.pdf projetos/guru-manuais/tests/test_data.py
git commit -m "feat(manuals): add synthetic manual fixture"
```

---

### Task 2: Extração, limpeza e chunks com páginas

**Files:**
- Create: `projetos/guru-manuais/pipeline.py`
- Create: `projetos/guru-manuais/tests/test_pipeline.py`

**Interfaces:**
- `extract_pdf_pages(content: bytes) -> list[tuple[int, str]]` retorna páginas numeradas a partir de 1.
- `clean_page_text(text: str) -> str` remove cabeçalhos `MANUAL FICTICIO` e `Pagina N`, normaliza espaços e quebras.
- `TextChunk` é um `dataclass` com `id: str`, `text: str`, `pages: list[int]`.
- `chunk_pages(pages: list[tuple[int, str]], chunk_size: int = 800, overlap: int = 120) -> list[TextChunk]` fatia cada página e mantém seu número de origem.

- [x] **Step 1: Escrever testes determinísticos de limpeza, número de página e overlap**

```python
# projetos/guru-manuais/tests/test_pipeline.py
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

if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Executar os testes para confirmar falha**

Run: `projetos/guru-manuais/.venv/bin/python -m unittest discover -s projetos/guru-manuais/tests -p 'test_pipeline.py' -v`  
Expected: FAIL porque `pipeline.py` ainda não existe.

- [x] **Step 3: Implementar funções puras de documento**

`clean_page_text` deve dividir por linhas, remover linhas iguais a `MANUAL FICTICIO` e as que correspondem a `Pagina ` seguida de dígitos, juntar as linhas restantes com espaços e colapsar espaços consecutivos. `chunk_pages` deve rejeitar `chunk_size <= overlap` e `overlap < 0`; para cada página limpa, usar passo `chunk_size - overlap`, descartar fragmentos vazios e criar ID determinístico `p{page_number}-c{index}`. Cada chunk recebe `pages=[page_number]`. `extract_pdf_pages` usa `PdfReader(BytesIO(content))`, preserva páginas vazias como string vazia e retorna tuplas `(número_1_based, texto)`.

- [x] **Step 4: Rodar os testes do pipeline de documento**

Run: `projetos/guru-manuais/.venv/bin/python -m unittest discover -s projetos/guru-manuais/tests -v`  
Expected: PASS; os chunks se sobrepõem em três caracteres no fixture pequeno e conservam a página 7.

- [x] **Step 5: Commitar a entrega**

```bash
git add projetos/guru-manuais/pipeline.py projetos/guru-manuais/tests/test_pipeline.py
git commit -m "feat(manuals): preserve PDF page sources"
```

---

### Task 3: Embeddings, ChromaDB, resposta fundamentada e histórico

**Files:**
- Modify: `projetos/guru-manuais/pipeline.py`
- Modify: `projetos/guru-manuais/tests/test_pipeline.py`

**Interfaces:**
- `embed_texts(client, texts: list[str], model: str, max_attempts: int = 2) -> list[list[float]]` retorna vetores na mesma ordem dos textos, com retry limitado.
- `embed_query(client, text: str, model: str, max_attempts: int = 2) -> list[float]` gera o vetor de uma pergunta com retry limitado.
- `index_chunks(chroma_client, chunks: list[TextChunk], embeddings: list[list[float]])` cria collection em memória e grava documentos, embeddings e metadados `pages`.
- `retrieve_chunks(collection, question: str, embed_query_fn, top_k: int = 3) -> list[dict]` chama `embed_query_fn(question)` e devolve `text`, `pages` e `distance` ordenados pelo Chroma.
- `answer_question(question: str, sources: list[dict], client, model: str, max_attempts: int = 2) -> tuple[str, int]` retorna resposta e tokens totais; sem fontes, retorna `"Não encontrei no documento."` e `0` sem chamar chat.
- `record_question(question, sources, tokens) -> dict` gera a linha para o histórico Pandas.

- [x] **Step 1: Escrever teste de recuperação e resposta sem contexto**

```python
import json
from types import SimpleNamespace
from pipeline import TextChunk, embed_texts, index_chunks, retrieve_chunks, answer_question, record_question

class FakeCollection:
    def query(self, **kwargs):
        self.kwargs = kwargs
        return {"documents": [["regra da pagina seis"]],
                "metadatas": [[{"pages": "[6]"}]],
                "distances": [[0.1]]}

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
        self.embeddings = SimpleNamespace(create=self.create)
    def create(self, **kwargs):
        self.calls += 1
        if self.calls <= getattr(self, "fail_times", 0):
            raise RuntimeError("falha temporaria")
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2]) for _ in kwargs["input"]])

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
        sources = retrieve_chunks(collection, "quantas cartas?", lambda q: [0.1, 0.2], top_k=1)
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
```

- [x] **Step 2: Executar para confirmar falha**

Run: `projetos/guru-manuais/.venv/bin/python -m unittest discover -s projetos/guru-manuais/tests -p 'test_pipeline.py' -v`  
Expected: FAIL porque funções de busca/resposta ainda não existem.

- [x] **Step 3: Implementar indexação e geração**

`embed_texts` e `embed_query` usam `client.embeddings.create(model=model, input=...)` e extraem `data[i].embedding`; embeddings não aceitam `temperature` nem `max_tokens`, e cada função tenta no máximo `max_attempts`. `index_chunks` cria um nome de collection único (`manual_` + UUID), usa `chroma_client.create_collection`, e chama `collection.add` com IDs, documentos, vetores e metadados `{"pages": json.dumps(chunk.pages)}` (Chroma aceita valores escalares em metadata). `retrieve_chunks` recebe um callable `embed_query_fn(text) -> list[float]`, usa `collection.query(query_embeddings=[embed_query_fn(question)], n_results=top_k, include=["documents", "metadatas", "distances"])`, decodifica `pages` com `json.loads` e transforma o primeiro resultado em uma lista plana de fontes.

`answer_question` monta system prompt em português instruindo a responder somente com o contexto fornecido e usar exatamente `Não encontrei no documento.` se ele não contiver a resposta. Inclua cada trecho recuperado com rótulo `[p. N]` no contexto e instrua a citar apenas esses rótulos. Passe `temperature=0.1` e `max_tokens=500` ao chat completion, com no máximo `max_attempts` chamadas quando a API falhar. Use somente os textos recuperados no contexto, devolva `usage.total_tokens` (ou `0` se ausente) e não invente páginas: as fontes exibidas vêm dos metadados da busca. `record_question` retorna chaves `pergunta`, `trechos`, `paginas`, `tokens`; `trechos` é lista de textos e `paginas` é a lista única ordenada das fontes.

- [x] **Step 4: Rodar a suíte local sem API**

Run: `projetos/guru-manuais/.venv/bin/python -m unittest discover -s projetos/guru-manuais/tests -v`  
Expected: PASS; clientes falsos cobrem busca e geração, sem instanciar `OpenAI()`.

- [x] **Step 5: Commitar a entrega**

```bash
git add projetos/guru-manuais/pipeline.py projetos/guru-manuais/tests/test_pipeline.py
git commit -m "feat(manuals): add grounded RAG pipeline"
```

---

### Task 4: Streamlit, README e índice final do repositório

**Files:**
- Create: `projetos/guru-manuais/app.py`
- Create: `projetos/guru-manuais/README.md`
- Create: `projetos/guru-manuais/tests/test_app_smoke.py`
- Modify: root `README.md`

**Interfaces:**
- `main()` carrega PDF enviado ou a amostra local, indexa uma vez por conteúdo na sessão e registra perguntas em `st.session_state`; uploads têm prioridade sobre a amostra.
- O histórico exibe `pergunta`, `trechos`, `paginas` e `tokens`; resposta exibe as páginas usadas.

- [x] **Step 1: Escrever smoke test do app**

```python
# test_app_smoke.py
import importlib.util
import sys
import unittest
from pathlib import Path
APP = Path(__file__).resolve().parents[1] / "app.py"
sys.path.insert(0, str(APP.parent))

class AppSmokeTests(unittest.TestCase):
    def test_app_module_defines_main(self):
        spec = importlib.util.spec_from_file_location("manual_app", APP)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(callable(module.main))

if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Executar para confirmar falha**

Run: `projetos/guru-manuais/.venv/bin/python -m unittest discover -s projetos/guru-manuais/tests -p 'test_app_smoke.py' -v`  
Expected: FAIL porque `app.py` ainda não existe.

- [x] **Step 3: Implementar app e instruções**

O app deve oferecer `st.file_uploader` para PDF, usar `manual_sintetico.pdf` quando não houver upload, apresentar botão `Indexar documento`, depois entrada de pergunta e botão `Perguntar`. Antes de indexar/verificar a pergunta, exigir `OPENAI_API_KEY` e exibir instrução clara quando estiver ausente. Armazenar hash do PDF, collection e histórico na sessão; ao trocar o PDF invalidar o índice e exigir reindexação, não recalcular embeddings em reruns, e cachear respostas por `(hash_pdf, pergunta_normalizada)` para evitar repetir a mesma chamada de chat. Exibir resposta, trechos/páginas de origem e tabela de histórico. Capturar erros de leitura, embedding, busca e chat com `st.error` sem traceback.

O README inclui instalação, `.env`, `streamlit run app.py`, explicação de que o PDF e suas regras são sintéticos e um gabarito manual: perguntar `Quantas cartas cada jogador compra no inicio do turno?` deve recuperar a página 6 e responder que são duas cartas. Atualize o índice `Projetos finais — exemplos` em `README.md` da raiz adicionando `projetos/guru-manuais/README.md` após os dois links já existentes.

- [x] **Step 4: Rodar testes, compilação e smoke manual**

Run: `projetos/guru-manuais/.venv/bin/python -m unittest discover -s projetos/guru-manuais/tests -v`  
Expected: PASS sem chave/API.  
Run: `projetos/guru-manuais/.venv/bin/python -m compileall -q projetos/guru-manuais`  
Expected: sem erros de sintaxe.  
Run manual: `cd projetos/guru-manuais && .venv/bin/streamlit run app.py`  
Expected: app abre, mostra aviso de configuração sem chave e não dispara embeddings/chat.

- [x] **Step 5: Verificar índice completo e commitar**

Run: `test -f projetos/analista-feedback/README.md && test -f projetos/auditor-gastos/README.md && test -f projetos/guru-manuais/README.md`  
Expected: status zero; os três links do índice apontam para READMEs existentes.

```bash
git add README.md projetos/guru-manuais/app.py projetos/guru-manuais/README.md projetos/guru-manuais/tests/test_app_smoke.py
git commit -m "feat(manuals): add Streamlit RAG starter"
```
