# Auditor de Gastos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar um starter do Auditor de Gastos com 25 recibos sintéticos TXT/PDF, validação por recibo, consolidação Pandas e dashboard Streamlit.

**Architecture:** `pipeline.py` lê cada arquivo isoladamente, valida a extração Pydantic, acompanha erros por arquivo e gera tabelas/agrupamentos. `schemas.py` descreve recibos e itens. `app.py` permite upload múltiplo ou uso da amostra incluída; o projeto possui dependências, configuração e documentação próprias.

**Tech Stack:** Python 3.10+, Pandas, Pydantic, OpenAI, python-dotenv, PyPDF2, Streamlit, `unittest`.

**Spec:** [`docs/superpowers/specs/2026-10-18-projetos-finais-design.md`](../specs/2026-10-18-projetos-finais-design.md)

## Global Constraints

- Todos os dados serão inventados, identificados como exemplos sintéticos nos READMEs, e incluídos no repositório para permitir experimentar com os arquivos sem prepará-los manualmente. As chamadas de IA continuarão exigindo uma chave de API.
- Usar OpenAI como provedor inicial, coerente com as dependências já presentes no repositório; nomes de modelos ficam configuráveis por variáveis de ambiente documentadas em `.env.example`.
- Nunca incluir uma chave real nos exemplos. Os `.gitignore` da raiz e dos três projetos ignorarão ambientes virtuais, arquivos `.env`, caches Python e dados locais do ChromaDB, sem ignorar os datasets de exemplo.
- As chamadas de IA terão `temperature`, `max_tokens` e limite pequeno de tentativas explícitos. Exceções de API, leitura de arquivo, parsing ou validação serão apresentadas como problemas por registro/arquivo, sem descartar resultados válidos do restante do lote.
- Não serão feitas chamadas pagas à API durante os testes. Não será alterado o conteúdo de `projeto-final.md`.

---

## File Structure

- Create `projetos/auditor-gastos/app.py` — interface de upload, métricas e problemas.
- Create `projetos/auditor-gastos/pipeline.py` — leitura TXT/PDF, normalização, extração, validação e agregações.
- Create `projetos/auditor-gastos/schemas.py` — modelos Pydantic do recibo e dos itens.
- Create `projetos/auditor-gastos/requirements.txt` — dependências runtime específicas.
- Create `projetos/auditor-gastos/.env.example` and `.gitignore` — configuração sem segredo e proteção local.
- Create `projetos/auditor-gastos/README.md` — problema, setup, execução e gabarito manual.
- Create 25 fixtures under `projetos/auditor-gastos/data/recibos/` — 16 TXT e 9 PDFs.
- Create `projetos/auditor-gastos/tests/test_data.py`, `test_pipeline.py`, and `test_app_smoke.py` — testes sem rede.
- Modify root `README.md` — acrescentar o link para este projeto ao índice iniciado pelo plano do Analista de Feedback.

## Recommended Execution Order

Execute após `2026-10-18-analista-feedback.md` e antes de `2026-10-18-guru-manuais.md`. O Auditor também funciona isoladamente; essa ordem mantém o índice da raiz com links apenas para projetos já existentes.

---

### Task 1: Scaffold e fixtures sintéticas de recibos

**Files:**
- Create: `projetos/auditor-gastos/requirements.txt`
- Create: `projetos/auditor-gastos/.env.example`
- Create: `projetos/auditor-gastos/.gitignore`
- Create: `projetos/auditor-gastos/data/recibos/*`
- Create: `projetos/auditor-gastos/tests/test_data.py`

**Interfaces:**
- O diretório contém exatamente 25 arquivos: 16 `.txt` e 9 `.pdf`.
- `mercado_01.txt` e `mercado_01_copia.pdf` representam a mesma compra; `transporte_04.txt` e `transporte_04_copia.pdf` representam a mesma corrida.
- `recibo_incompleto.txt` não contém os campos necessários; `recibo_sem_texto.pdf` é um PDF válido sem camada de texto.

- [x] **Step 1: Escrever teste de contagem, formatos e gabarito do fixture**

```python
# projetos/auditor-gastos/tests/test_data.py
import unittest
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "recibos"

class ReceiptDatasetTests(unittest.TestCase):
    def test_dataset_has_25_mixed_files_and_problem_samples(self):
        files = sorted(p for p in DATA.iterdir() if p.is_file())
        self.assertEqual(len(files), 25)
        self.assertEqual(sum(p.suffix == ".txt" for p in files), 16)
        self.assertEqual(sum(p.suffix == ".pdf" for p in files), 9)
        self.assertTrue((DATA / "recibo_incompleto.txt").exists())
        self.assertTrue((DATA / "recibo_sem_texto.pdf").exists())
        self.assertTrue((DATA / "mercado_01_copia.pdf").exists())
        self.assertIn("R$ 1.234,56", (DATA / "recibo_15.txt").read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Executar para confirmar falha por diretório ausente**

Run: `python3 -m unittest discover -s projetos/auditor-gastos/tests -p 'test_data.py' -v`  
Expected: FAIL porque o diretório `data/recibos` ainda não existe.

- [x] **Step 3: Criar dependências, configuração e 25 arquivos**

```text
# requirements.txt
openai>=1.55,<3
python-dotenv>=1.0,<2
pandas>=2.0,<3
streamlit>=1.32,<2
pydantic>=2.0,<3
PyPDF2>=3.0,<4
```

```dotenv
# .env.example
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
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

Crie 16 TXT em UTF-8 e 9 PDFs textuais, exceto `recibo_sem_texto.pdf`. Inclua layouts de supermercado, transporte, restaurante e conta doméstica, datas em ISO e formatos brasileiros, valores como `R$ 1.234,56`, itens com quantidade, gorjeta/taxa e totais não negativos. O campo `valor` de cada item será o valor total da linha (não o preço unitário), de modo que a soma dos itens corresponda a `valor_total`.

Use este conteúdo-base exato em `mercado_01.txt` e seu equivalente formatado como PDF em `mercado_01_copia.pdf`; ambos devem extrair para o mesmo estabelecimento, data e total:

```text
MERCADO BOM PRECO
Data: 10/01/2025
Arroz 5kg | Quantidade: 2 | Valor: R$ 28,00
Feijao 1kg | Quantidade: 1 | Valor: R$ 8,50
TOTAL: R$ 36,50
```

Inclua `transporte_04.txt` e `transporte_04_copia.pdf` com os mesmos campos semânticos (estabelecimento `VaiVem`, data `2025-02-04`, total `R$ 24,90`) em layouts diferentes. Complete os arquivos com nomes `recibo_03.txt` a `recibo_14.txt`, `recibo_15.txt`, `recibo_pdf_01.pdf` a `recibo_pdf_06.pdf`, `recibo_incompleto.txt` e `recibo_sem_texto.pdf`; assim o total é 16 TXT e 9 PDFs.

Gere os PDFs estáticos com ReportLab somente no ambiente temporário de geração. Use `python3 -m venv /tmp/receipt-pdf-env`, `/tmp/receipt-pdf-env/bin/pip install reportlab` e `/tmp/receipt-pdf-env/bin/python` para executar este script de geração (não salve o script nem adicione ReportLab às dependências runtime):

```python
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

out = Path("projetos/auditor-gastos/data/recibos")
out.mkdir(parents=True, exist_ok=True)

def write_pdf(name, lines):
    pdf = canvas.Canvas(str(out / name), pagesize=A4)
    y = 800
    for line in lines:
        pdf.drawString(48, y, line)
        y -= 22
    pdf.showPage()
    pdf.save()

market = ["MERCADO BOM PRECO", "Data: 10/01/2025", "Arroz 5kg | Quantidade: 2 | Valor: R$ 28,00", "Feijao 1kg | Quantidade: 1 | Valor: R$ 8,50", "TOTAL: R$ 36,50"]
ride = ["VaiVem - RECIBO", "Data da corrida: 2025-02-04", "Viagem | Quantidade: 1 | Valor: R$ 24,90", "Total pago: R$ 24,90"]
write_pdf("mercado_01_copia.pdf", market)
write_pdf("transporte_04_copia.pdf", ride)
for i in range(1, 7):
    first, second = 10 + i, 2
    total = first + second
    write_pdf(f"recibo_pdf_{i:02d}.pdf", [
        f"CONTA CASA {i:02d}", f"Data: 2025-{(i % 12) + 1:02d}-10",
        f"Servico residencial | Quantidade: 1 | Valor: R$ {first},00",
        f"Taxa de servico | Quantidade: 1 | Valor: R$ {second},00",
        f"TOTAL: R$ {total},00",
    ])
blank = canvas.Canvas(str(out / "recibo_sem_texto.pdf"), pagesize=A4)
blank.showPage()
blank.save()
```

Gere os TXT correspondentes em UTF-8: `mercado_01.txt` com o bloco do recibo de mercado, `transporte_04.txt` com os mesmos campos da corrida, 12 exemplos legíveis `recibo_03.txt` a `recibo_14.txt`, `recibo_15.txt` e `recibo_incompleto.txt` com apenas estabelecimento/data parcial. Os 12 exemplos e `recibo_15.txt` devem ter itens cuja soma confira; varie layouts, categorias, datas e valores sem alterar as duas duplicatas fixas.

Gere os TXT fixos e as 13 amostras legíveis restantes com este segundo bloco (rode a partir da raiz do repositório):

```python
from pathlib import Path
from decimal import Decimal

out = Path("projetos/auditor-gastos/data/recibos")
def write_txt(name, text):
    (out / name).write_text(text + "\n", encoding="utf-8")
def brl(value):
    return "R$ " + f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

market_text = "\n".join(["MERCADO BOM PRECO", "Data: 10/01/2025", "Arroz 5kg | Quantidade: 2 | Valor: R$ 28,00", "Feijao 1kg | Quantidade: 1 | Valor: R$ 8,50", "TOTAL: R$ 36,50"])
ride_text = "\n".join(["VaiVem", "Data da corrida: 2025-02-04", "Viagem | Quantidade: 1 | Valor: R$ 24,90", "Total pago: R$ 24,90"])
write_txt("mercado_01.txt", market_text)
write_txt("transporte_04.txt", ride_text)
merchants = ["Padaria Central", "Restaurante da Vila", "Conta Casa Luz", "Mercado do Bairro"]
for i in range(3, 16):
    first = Decimal("1234.56") if i == 15 else Decimal(10 + i)
    second = Decimal("0.00") if i == 15 else Decimal("2.50")
    total = first + second
    month = (i % 12) + 1
    day = (i % 27) + 1
    date_text = f"{day:02d}/{month:02d}/2025" if i % 2 else f"2025-{month:02d}-{day:02d}"
    merchant = merchants[i % len(merchants)]
    fee_label = "Gorjeta" if merchant == "Restaurante da Vila" else "Taxa/extra"
    text = "\n".join([
        merchant, f"Data: {date_text}",
        f"Item principal | Quantidade: 1 | Valor: {brl(first)}",
        f"{fee_label} | Quantidade: 1 | Valor: {brl(second)}",
        f"TOTAL: {brl(total)}",
    ])
    write_txt(f"recibo_{i:02d}.txt", text)
write_txt("recibo_incompleto.txt", "Loja sem nome\nData parcial: 2025-02")
```

Por fim, crie `.venv` e instale os requisitos runtime com `python3 -m venv projetos/auditor-gastos/.venv` e `projetos/auditor-gastos/.venv/bin/python -m pip install -r projetos/auditor-gastos/requirements.txt`. Os dois blocos de geração de PDF/TXT são somente ferramentas locais; não devem ser incluídos no projeto.

- [x] **Step 4: Executar o teste de fixtures**

Run: `projetos/auditor-gastos/.venv/bin/python -m unittest discover -s projetos/auditor-gastos/tests -p 'test_data.py' -v`  
Expected: PASS; total 25, sendo 16 TXT e 9 PDF.

- [x] **Step 5: Commitar a entrega**

```bash
git add projetos/auditor-gastos/requirements.txt projetos/auditor-gastos/.env.example projetos/auditor-gastos/.gitignore projetos/auditor-gastos/data/recibos projetos/auditor-gastos/tests/test_data.py
git commit -m "feat(expenses): add synthetic receipts"
```

---

### Task 2: Schema, leitura resiliente e validação dos recibos

**Files:**
- Create: `projetos/auditor-gastos/schemas.py`
- Create: `projetos/auditor-gastos/pipeline.py`
- Create: `projetos/auditor-gastos/tests/test_pipeline.py`
- Modify: `projetos/auditor-gastos/tests/test_data.py`

**Interfaces:**
- `ReceiptItem`: `descricao: str`, `quantidade: Decimal` maior que zero, `valor: Decimal` não negativo (total da linha).
- `Receipt`: `estabelecimento: str`, `data: date`, `itens: list[ReceiptItem]`, `valor_total: Decimal` não negativo e `categoria: Literal["alimentação", "transporte", "moradia", "lazer", "outros"]`.
- `read_receipt_text(name: str, content: bytes) -> str` decodifica TXT ou concatena o texto de todas as páginas PDF; arquivo vazio/sem texto gera erro claro.
- `parse_brl_amount(value: str | Decimal) -> Decimal` converte `R$ 1.234,56` para `Decimal("1234.56")`.
- `validate_receipt(receipt: Receipt, tolerance: Decimal = Decimal("0.05")) -> list[str]` detecta diferença de soma maior que a tolerância.
- `process_files(files: list[tuple[str, bytes]], extractor, max_attempts: int = 2) -> tuple[pd.DataFrame, pd.DataFrame]` devolve recibos válidos e problemas por arquivo.

- [x] **Step 1: Escrever testes puros de moeda, schema, soma e isolamento**

```python
# test_pipeline.py; adicione o diretório do projeto ao sys.path antes do import
import sys
import unittest
from decimal import Decimal
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schemas import Receipt, ReceiptItem
from pipeline import parse_brl_amount, validate_receipt, process_files

class ReceiptValidationTests(unittest.TestCase):
    def make_receipt(self, total="36.50"):
        return Receipt(
            estabelecimento="Mercado Bom Preco", data="2025-01-10",
            itens=[
                ReceiptItem(descricao="Arroz", quantidade=2, valor=Decimal("28.00")),
                ReceiptItem(descricao="Feijao", quantidade=1, valor=Decimal("8.50")),
            ], valor_total=Decimal(total), categoria="alimentação",
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
            Receipt(estabelecimento="Loja", data="2025-19-40", itens=[], valor_total=0, categoria="outros")

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
        text = read_receipt_text("mercado_01_copia.pdf", (data / "mercado_01_copia.pdf").read_bytes())
        self.assertIn("MERCADO BOM PRECO", text)
        with self.assertRaises(ValueError):
            read_receipt_text("recibo_sem_texto.pdf", (data / "recibo_sem_texto.pdf").read_bytes())

if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Executar os testes para confirmar falha**

Run: `projetos/auditor-gastos/.venv/bin/python -m unittest discover -s projetos/auditor-gastos/tests -p 'test_pipeline.py' -v`  
Expected: FAIL porque `schemas.py` e `pipeline.py` ainda não existem.

- [x] **Step 3: Implementar schema e leitura/validação determinísticas**

Use Pydantic v2 e `Decimal`; configure `Field(gt=0)` para quantidade e `Field(ge=0)` para valores. Em `read_receipt_text`, aceite apenas `.txt` e `.pdf`, use `content.decode("utf-8", errors="replace")` para TXT e `PdfReader(BytesIO(content))` para PDF. Em PDF, concatene `page.extract_text() or ""`; se o resultado normalizado ficar vazio, levante `ValueError("PDF sem texto extraível")`.

`parse_brl_amount` remove `R$`, espaços e separadores de milhar `.` e substitui a vírgula decimal por ponto; preserve `Decimal` sem conversão intermediária para `float`. `validate_receipt` compara `abs(sum(item.valor) - receipt.valor_total)` com a tolerância e retorna a mensagem com ambos os totais quando falhar.

`process_files` captura erros separadamente para cada tupla `(nome, bytes)`, não chama o extrator se `read_receipt_text` falhar ou retornar texto em branco, executa no máximo `max_attempts` para erro de parsing/validação e retorna DataFrames com colunas fixas `arquivo,estabelecimento,data,valor_total,categoria,itens` e `arquivo,erro`. Para o teste, `extractor` é callable `extractor(texto) -> Receipt`; cada nova tentativa ocorre somente após exceção ou divergência de soma.

- [x] **Step 4: Rodar testes de moeda, schema e falha isolada**

Run: `projetos/auditor-gastos/.venv/bin/python -m unittest discover -s projetos/auditor-gastos/tests -v`  
Expected: PASS, inclusive PDF/arquivo problemático sem interromper recibos bons.

- [x] **Step 5: Commitar a entrega**

```bash
git add projetos/auditor-gastos/schemas.py projetos/auditor-gastos/pipeline.py projetos/auditor-gastos/tests/test_pipeline.py projetos/auditor-gastos/tests/test_data.py
git commit -m "feat(expenses): validate receipt data"
```

---

### Task 3: Extração OpenAI, deduplicação e análise Pandas

**Files:**
- Modify: `projetos/auditor-gastos/pipeline.py`
- Modify: `projetos/auditor-gastos/tests/test_pipeline.py`

**Interfaces:**
- `extract_receipt(text: str, client, model: str) -> Receipt` realiza uma chamada estruturada validada por Pydantic.
- `mark_duplicates(df: pd.DataFrame) -> pd.DataFrame` adiciona `duplicado`, com chave normalizada `(estabelecimento, data, valor_total)`; não elimina linhas.
- `build_analytics(receipts: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]` retorna recibos marcados, gasto por categoria/mês e ranking de itens.

- [x] **Step 1: Escrever teste de duplicata e agregações**

```python
from types import SimpleNamespace
from schemas import Receipt, ReceiptItem
from pipeline import extract_receipt, mark_duplicates, build_analytics

class FakeStructuredCompletions:
    def __init__(self, parsed):
        self.parsed = parsed
        self.kwargs = None
    def parse(self, **kwargs):
        self.kwargs = kwargs
        message = SimpleNamespace(parsed=self.parsed)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

class ExpenseAnalyticsTests(unittest.TestCase):
    def test_extract_receipt_uses_pydantic_structured_output(self):
        expected = Receipt(
            estabelecimento="Mercado", data="2025-01-10",
            itens=[ReceiptItem(descricao="Arroz", quantidade=1, valor=Decimal("10.00"))],
            valor_total=Decimal("10.00"), categoria="alimentação",
        )
        completions = FakeStructuredCompletions(expected)
        client = SimpleNamespace(beta=SimpleNamespace(chat=SimpleNamespace(completions=completions)))
        result = extract_receipt("texto de recibo", client, "fake")
        self.assertEqual(result, expected)
        self.assertIs(completions.kwargs["response_format"], Receipt)
        self.assertEqual(completions.kwargs["temperature"], 0.1)
        self.assertEqual(completions.kwargs["max_tokens"], 700)

    def test_duplicate_key_and_month_category_groupby(self):
        rows = pd.DataFrame([
            {"estabelecimento": "Mercado Bom Preco", "data": "2025-01-10", "valor_total": Decimal("36.50"), "categoria": "alimentação", "itens": [{"descricao": "Arroz", "quantidade": 2, "valor": Decimal("28.00")}]},
            {"estabelecimento": "mercado bom preco", "data": "2025-01-10", "valor_total": Decimal("36.50"), "categoria": "alimentação", "itens": [{"descricao": "Arroz", "quantidade": 2, "valor": Decimal("28.00")}]},
        ])
        marked, monthly, item_ranking = build_analytics(rows)
        self.assertEqual(marked["duplicado"].tolist(), [False, True])
        self.assertEqual(monthly.loc[0, "mes"], "2025-01")
        self.assertEqual(float(monthly.loc[0, "valor_total"]), 36.50)
        self.assertEqual(item_ranking.loc[0, "descricao"], "Arroz")
        self.assertEqual(float(item_ranking.loc[0, "valor"]), 28.00)
```

- [x] **Step 2: Executar para confirmar falha**

Run: `projetos/auditor-gastos/.venv/bin/python -m unittest discover -s projetos/auditor-gastos/tests -p 'test_pipeline.py' -v`  
Expected: FAIL porque `extract_receipt`, `mark_duplicates` e `build_analytics` ainda não existem.

- [x] **Step 3: Implementar extração estruturada e analytics**

`extract_receipt` envia texto e system prompt pedindo somente os campos do schema; usa o Structured Outputs do SDK `client.beta.chat.completions.parse(..., response_format=Receipt)`, `temperature=0.1` e `max_tokens=700`, retornando `response.choices[0].message.parsed` (falha se for `None`). O retry permanece em `process_files`, que recebe `extractor=lambda text: extract_receipt(text, client, model)`.

`mark_duplicates` normaliza nome com `casefold` e espaços, mantém todas as linhas e marca apenas ocorrências após a primeira para cada chave. `build_analytics` cria `mes` no formato `YYYY-MM`, devolve as linhas marcadas para auditoria e calcula agregados/ranking somente sobre `duplicado == False`, evitando contar uma compra duas vezes. Exploda itens sem alterar o total do recibo e agrupe o valor de linha por descrição. Não inclua falhas no agregado de recibos válidos.

- [x] **Step 4: Rodar toda a suíte determinística**

Run: `projetos/auditor-gastos/.venv/bin/python -m unittest discover -s projetos/auditor-gastos/tests -v`  
Expected: PASS, sem instanciar cliente OpenAI durante testes.

- [x] **Step 5: Commitar a entrega**

```bash
git add projetos/auditor-gastos/pipeline.py projetos/auditor-gastos/tests/test_pipeline.py
git commit -m "feat(expenses): aggregate receipt spending"
```

---

### Task 4: App Streamlit, documentação e integração do índice

**Files:**
- Create: `projetos/auditor-gastos/app.py`
- Create: `projetos/auditor-gastos/README.md`
- Create: `projetos/auditor-gastos/tests/test_app_smoke.py`
- Modify: root `README.md`

**Interfaces:**
- Upload múltiplo produz `list[tuple[str, bytes]]`; uploads completos têm prioridade; sem upload, opção `Usar recibos sintéticos` seleciona os arquivos locais incluídos.
- `main()` verifica configuração antes de instanciar OpenAI e não reprocessa arquivos em reruns sem novo clique.

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
    def test_app_defines_main(self):
        spec = importlib.util.spec_from_file_location("expenses_app", APP)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(callable(module.main))

if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Executar para confirmar falha**

Run: `projetos/auditor-gastos/.venv/bin/python -m unittest discover -s projetos/auditor-gastos/tests -p 'test_app_smoke.py' -v`  
Expected: FAIL porque `app.py` ainda não existe.

- [x] **Step 3: Implementar interface e documentação**

`app.py` apresenta `st.file_uploader(type=["txt", "pdf"], accept_multiple_files=True)`, usa bytes de cada upload, e permite selecionar a pasta de amostras quando não há uploads. Ao clicar em `Processar recibos`, cria cliente apenas se `OPENAI_API_KEY` existir, calcula SHA-256 sobre nomes/bytes de todos os arquivos, consulta cache de `st.session_state` por essa chave e só chama `process_files` em cache miss. Exibe total gasto, tabela consolidada, gráfico por categoria, ranking de itens e tabela de falhas/inconsistências. Cada erro fica associado ao nome do arquivo; erro num recibo não esconde os válidos.

O README documenta setup (`python -m venv .venv`, ativação, `pip install -r requirements.txt`), `.env`, `streamlit run app.py`, limitações de PDF sem OCR e a semântica de `valor` como total da linha. Gabarito: `mercado_01.txt` tem total `36,50`, categoria `alimentação` e dois itens cuja soma confere; `mercado_01_copia.pdf` é duplicata; `recibo_sem_texto.pdf` deve aparecer na lista de erros. Acrescente ao bloco `Projetos finais — exemplos` do README raiz o link `projetos/auditor-gastos/README.md`, mantendo o link do Analista existente.

- [x] **Step 4: Rodar testes, compilação e smoke manual**

Run: `projetos/auditor-gastos/.venv/bin/python -m unittest discover -s projetos/auditor-gastos/tests -v`  
Expected: PASS sem chave e sem chamadas à API.  
Run: `projetos/auditor-gastos/.venv/bin/python -m compileall -q projetos/auditor-gastos`  
Expected: sem erros de sintaxe.  
Run manual: `cd projetos/auditor-gastos && .venv/bin/streamlit run app.py`  
Expected: app abre e mostra aviso de chave ausente sem traceback quando não há `.env`.

- [x] **Step 5: Commitar a entrega**

```bash
git add README.md projetos/auditor-gastos/app.py projetos/auditor-gastos/README.md projetos/auditor-gastos/tests/test_app_smoke.py
git commit -m "feat(expenses): add Streamlit starter"
```
