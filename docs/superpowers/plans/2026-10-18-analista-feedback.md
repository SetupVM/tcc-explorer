# Analista de Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar um starter executável do Analista de Feedback com CSVs sintéticos, classificação aninhada validada e dashboard Streamlit.

**Architecture:** O `pipeline.py` concentra limpeza, deduplicação, merge, chamadas OpenAI e agregações. `schemas.py` define o contrato Pydantic. `app.py` conecta uploads/amostras ao pipeline e exibe resultados; dados, configuração e instruções ficam no próprio diretório para permitir copiá-lo como projeto independente.

**Tech Stack:** Python 3.10+, Pandas, Pydantic, OpenAI, python-dotenv, Streamlit, `unittest`.

**Spec:** [`docs/superpowers/specs/2026-10-18-projetos-finais-design.md`](../specs/2026-10-18-projetos-finais-design.md)

## Global Constraints

- Todos os dados serão inventados, identificados como exemplos sintéticos nos READMEs, e incluídos no repositório para permitir experimentar com os arquivos sem prepará-los manualmente. As chamadas de IA continuarão exigindo uma chave de API.
- Usar OpenAI como provedor inicial, coerente com as dependências já presentes no repositório; nomes de modelos ficam configuráveis por variáveis de ambiente documentadas em `.env.example`.
- Nunca incluir uma chave real nos exemplos. Os `.gitignore` da raiz e dos três projetos ignorarão ambientes virtuais, arquivos `.env`, caches Python e dados locais do ChromaDB, sem ignorar os datasets de exemplo.
- As chamadas de IA terão `temperature`, `max_tokens` e limite pequeno de tentativas explícitos. Exceções de API, leitura de arquivo, parsing ou validação serão apresentadas como problemas por registro/arquivo, sem descartar resultados válidos do restante do lote.
- Não serão feitas chamadas pagas à API durante os testes. Não será alterado o conteúdo de `projeto-final.md`.

---

## File Structure

- Create `projetos/analista-feedback/app.py` — entrada Streamlit e visualização.
- Create `projetos/analista-feedback/pipeline.py` — leitura, limpeza, deduplicação, classificação, conflitos, agregações e ranking de problemas. Expõe `load_feedback(review_source, product_source)` para caminhos locais e objetos file-like do Streamlit.
- Create `projetos/analista-feedback/schemas.py` — modelos Pydantic da resposta de feedback.
- Create `projetos/analista-feedback/requirements.txt` — dependências do starter.
- Create `projetos/analista-feedback/.env.example` — nomes de variáveis sem segredo.
- Create `projetos/analista-feedback/.gitignore` — proteção ao copiar o projeto.
- Create `projetos/analista-feedback/README.md` — setup, execução e gabarito manual.
- Create `projetos/analista-feedback/data/reviews_loja.csv` — 300 reviews artificiais.
- Create `projetos/analista-feedback/data/produtos.csv` — produtos correspondentes.
- Create `projetos/analista-feedback/tests/test_data.py`, `test_pipeline.py` and `test_app_smoke.py` — testes determinísticos sem rede.
- Modify root `.gitignore` — acrescentar caches e diretórios locais sem remover regras existentes.
- Modify root `README.md` — adicionar o primeiro link do índice de projetos finais.

## Recommended Execution Order

Execute este plano primeiro, depois `2026-10-18-auditor-gastos.md` e por último `2026-10-18-guru-manuais.md`. Os aplicativos não compartilham código; a ordem apenas permite que os planos seguintes acrescentem links ao índice da raiz sem deixá-lo apontando para projetos ainda inexistentes.

---

### Task 1: Scaffold seguro e dataset CSV

**Files:**
- Create: `projetos/analista-feedback/requirements.txt`
- Create: `projetos/analista-feedback/.env.example`
- Create: `projetos/analista-feedback/.gitignore`
- Create: `projetos/analista-feedback/data/reviews_loja.csv`
- Create: `projetos/analista-feedback/data/produtos.csv`
- Create: `projetos/analista-feedback/tests/test_data.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces CSVs com colunas `id,data,id_produto,nota,comentario` e `id_produto,nome,categoria,preco`.
- Os registros especiais ficam com IDs fixos para os testes e o gabarito: `1` positivo, `2` irônico/negativo apesar da nota alta, `3` em inglês, `4` sem comentário, `5` e `6` quase duplicados, `7` duplicata exata de `1`.

- [x] **Step 1: Escrever o teste de contrato dos CSVs**

```python
# projetos/analista-feedback/tests/test_data.py
import csv
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data"

class DatasetTests(unittest.TestCase):
    def test_reviews_have_required_shape_and_examples(self):
        with (ROOT / "reviews_loja.csv").open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 300)
        self.assertEqual(set(rows[0]), {"id", "data", "id_produto", "nota", "comentario"})
        by_id = {row["id"]: row for row in rows}
        self.assertEqual(by_id["2"]["comentario"], "Ótimo, quebrou no segundo dia.")
        self.assertEqual(by_id["3"]["comentario"], "The delivery was late, but the product works.")
        self.assertEqual(by_id["4"]["comentario"], "")
        self.assertEqual(by_id["5"]["nota"], "cinco")
        self.assertEqual(by_id["6"]["nota"], "4,5")
        self.assertEqual(by_id["1"]["comentario"], by_id["7"]["comentario"])
        self.assertEqual(by_id["5"]["id_produto"], by_id["6"]["id_produto"])
        self.assertTrue(any("😊" in row["comentario"] for row in rows))
        self.assertTrue(any(row["nota"] == "" for row in rows))
        self.assertGreaterEqual(len({row["data"] for row in rows}), 3)

    def test_products_have_rows_and_required_shape(self):
        with (ROOT / "produtos.csv").open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertGreaterEqual(len(rows), 10)
        self.assertEqual(set(rows[0]), {"id_produto", "nome", "categoria", "preco"})

if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Executar para confirmar falha por arquivos ausentes**

Run: `python3 -m unittest discover -s projetos/analista-feedback/tests -p 'test_data.py' -v`  
Expected: FAIL porque os CSVs ainda não existem.

- [x] **Step 3: Criar configuração e dados determinísticos**

Use estes arquivos de configuração:

```text
# projetos/analista-feedback/requirements.txt
openai>=1.55,<3
python-dotenv>=1.0,<2
pandas>=2.0,<3
streamlit>=1.32,<2
pydantic>=2.0,<3
```

```dotenv
# .env.example
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

```gitignore
# .gitignore do projeto; na raiz, acrescente somente linhas ausentes e mantenha regras existentes.
.env
.venv/
venv/
__pycache__/
*.py[cod]
.streamlit/secrets.toml
.chroma/
chroma_db/
```

Gere os CSVs com um script Python de uso único usando `csv.DictWriter`, `encoding="utf-8"` e `newline=""`. Crie 12 produtos e 300 reviews com IDs `1..300`; use estas sete linhas fixas antes de gerar as demais por ciclo de templates, sempre escolhendo `id_produto` entre `1..12`:

```python
fixed = [
    (1, "2025-01-03", 1, "5", "Adorei o produto, chegou perfeito."),
    (2, "03/01/2025", 2, "5", "Ótimo, quebrou no segundo dia."),
    (3, "Jan 04 2025", 3, "2", "The delivery was late, but the product works."),
    (4, "2025-01-05", 4, "", ""),
    (5, "05/01/2025", 5, "cinco", "Entrega rápida, produto excelente!"),
    (6, "Jan 06 2025", 5, "4,5", "ENTREGA rapida - produto excelente."),
    (7, "2025-01-03", 1, "5", "Adorei o produto, chegou perfeito."),
]
templates = [
    "A qualidade superou minhas expectativas 😊",
    "A entrega demorou e o pacote chegou amassado.",
    "O atendimento resolveu meu problema rapidamente.",
    "Pelo preço, esperava um material melhor.",
    "Tudo certo com o pedido e o produto funciona bem.",
    "Que experiência maravilhosa: parou de funcionar no primeiro dia.",
    "The product is good, but customer service was slow.",
    "O produto veio diferente da foto e quero uma troca.",
]
observations = [
    "Depois de tres dias de uso, o acabamento continua firme.",
    "Na primeira semana, percebi um ruido diferente ao ligar.",
    "A caixa veio com a etiqueta rasgada e sem lacre.",
    "O suporte respondeu somente no dia seguinte.",
    "Usei em uma viagem curta e o desempenho foi estavel.",
    "A cor real ficou diferente das imagens do site.",
    "O prazo prometido era curto, mas o rastreio ficou parado.",
    "A peca principal veio com um risco pequeno.",
    "O manual explica bem a primeira configuracao.",
    "Precisei solicitar a troca porque veio no tamanho errado.",
]
contexts = [
    "Isso aconteceu na semana da compra.",
    "Eu esperava mais pelo preco pago.",
    "Ainda estou aguardando solucao do atendimento.",
    "Mesmo assim, recomendo verificar cada unidade antes do envio.",
]
details = [f"{observation} {context}" for observation in observations for context in contexts]
dates = ["2025-02-10", "10/02/2025", "Feb 11 2025", "11-02-2025"]
notes = ["5", "4", "3", "2", "1", "", "cinco", "4,5"]
```

Use estes 12 produtos e este código para gravar os dois arquivos determinísticos:

```python
from pathlib import Path
import csv

products = [
    (1, "Fone Aurora", "eletronicos", 149.90),
    (2, "Cafeteira Brisa", "eletrodomesticos", 229.00),
    (3, "Mochila Serra", "acessorios", 119.50),
    (4, "Luminaria Lua", "casa", 89.90),
    (5, "Garrafa Trilho", "acessorios", 45.00),
    (6, "Teclado Nuvem", "eletronicos", 199.00),
    (7, "Panela Horizonte", "casa", 159.90),
    (8, "Liquidificador Ponto", "eletrodomesticos", 179.00),
    (9, "Livro Mar Aberto", "livros", 54.90),
    (10, "Mouse Vale", "eletronicos", 79.90),
    (11, "Toalha Campo", "casa", 39.90),
    (12, "Fone Bruma", "eletronicos", 129.00),
]
rows = fixed + [
    (i, dates[i % len(dates)], ((i - 1) % 12) + 1, notes[i % len(notes)],
     f"{templates[i % len(templates)]} {details[i // 8]} Referência {i:03d}.")
    for i in range(8, 301)
]
folder = Path("projetos/analista-feedback/data")
folder.mkdir(parents=True, exist_ok=True)
def write_csv(path, headers, records):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(dict(zip(headers, row)) for row in records)
write_csv(folder / "reviews_loja.csv", ["id", "data", "id_produto", "nota", "comentario"], rows)
write_csv(folder / "produtos.csv", ["id_produto", "nome", "categoria", "preco"], products)
```

As datas fixas e geradas mantêm formatos deliberadamente diferentes. Preserve comentários e notas vazios como strings CSV vazias. Instale as dependências para as etapas de pipeline/UI com `python3 -m venv projetos/analista-feedback/.venv` e `projetos/analista-feedback/.venv/bin/python -m pip install -r projetos/analista-feedback/requirements.txt`.

- [x] **Step 4: Rodar os testes de dados**

Run: `projetos/analista-feedback/.venv/bin/python -m unittest discover -s projetos/analista-feedback/tests -p 'test_data.py' -v`  
Expected: PASS; há 300 reviews, 12 produtos e todos os casos especiais podem ser encontrados pelos IDs.

- [x] **Step 5: Commitar a entrega**

```bash
git add .gitignore projetos/analista-feedback/requirements.txt projetos/analista-feedback/.env.example projetos/analista-feedback/.gitignore projetos/analista-feedback/data projetos/analista-feedback/tests/test_data.py
git commit -m "feat(feedback): add synthetic dataset"
```

---

### Task 2: Schemas e pipeline Pandas determinístico

**Files:**
- Create: `projetos/analista-feedback/schemas.py`
- Create: `projetos/analista-feedback/pipeline.py`
- Create: `projetos/analista-feedback/tests/test_pipeline.py`

**Interfaces:**
- `load_feedback(review_source, product_source) -> tuple[pd.DataFrame, pd.DataFrame]` lê dois caminhos, buffers ou objetos `UploadedFile` via `pd.read_csv`.
- `clean_reviews(df: pd.DataFrame) -> pd.DataFrame`: retorna cópia, preserva comentários vazios, converte `data` para `datetime64` e `nota` para número float ou `NaN`.
- `remove_near_duplicates(df: pd.DataFrame, threshold: float = 0.92) -> pd.DataFrame`: compara comentários normalizados dentro do mesmo `id_produto`, conserva a primeira linha e usa `SequenceMatcher`.
- `merge_products(reviews: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame`: `left merge` por `id_produto` com validação muitos-para-um.
- `explode_aspects(df: pd.DataFrame) -> pd.DataFrame` e `aggregate_aspects(aspects: pd.DataFrame) -> pd.DataFrame` geram os resumos sem depender da API.
- `rank_problems_by_category(aspects: pd.DataFrame) -> pd.DataFrame` filtra sentimento negativo, conta por categoria/aspecto e ordena por contagem decrescente.
- `schemas.py` define `AspectAnalysis` e `FeedbackAnalysis`; os campos permitidos são `aspecto: Literal["entrega", "preço", "qualidade", "atendimento", "outro"]`, `sentimento: Literal["positivo", "neutro", "negativo"]`, `sentimento_geral` com os mesmos sentimentos, `idioma: str` e `urgente: bool`.

- [x] **Step 1: Escrever testes das transformações esperadas**

```python
# adicionar em test_pipeline.py
import sys
import unittest
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import clean_reviews, remove_near_duplicates, merge_products, explode_aspects, aggregate_aspects, rank_problems_by_category

class FeedbackTransformTests(unittest.TestCase):
    def test_clean_reviews_parses_notes_dates_and_keeps_empty_comment(self):
        raw = pd.DataFrame({
            "id": [1, 2, 3], "data": ["03/01/2025", "2025-01-04", "Jan 05 2025"],
            "id_produto": [1, 1, 2], "nota": ["cinco", "4,5", ""],
            "comentario": ["bom", "ok", ""],
        })
        result = clean_reviews(raw)
        self.assertEqual(result.loc[0, "nota"], 5.0)
        self.assertEqual(result.loc[1, "nota"], 4.5)
        self.assertTrue(pd.isna(result.loc[2, "nota"]))
        self.assertTrue(pd.notna(result.loc[0, "data"]))
        self.assertEqual(result.loc[2, "comentario"], "")

    def test_load_feedback_accepts_file_like_objects(self):
        from io import StringIO
        from pipeline import load_feedback
        reviews = StringIO("id,data,id_produto,nota,comentario\n1,2025-01-01,1,5,bom\n")
        products = StringIO("id_produto,nome,categoria,preco\n1,Fone,eletronicos,10\n")
        loaded_reviews, loaded_products = load_feedback(reviews, products)
        self.assertEqual(len(loaded_reviews), 1)
        self.assertEqual(loaded_products.loc[0, "nome"], "Fone")

    def test_synthetic_dataset_keeps_most_reviews_after_deduplication(self):
        data_dir = Path(__file__).resolve().parents[1] / "data"
        reviews = pd.read_csv(data_dir / "reviews_loja.csv")
        self.assertGreaterEqual(len(remove_near_duplicates(clean_reviews(reviews))), 250)

    def test_near_duplicate_criterion_is_case_and_accent_insensitive(self):
        raw = pd.DataFrame({"id_produto": [1, 1], "comentario": [
            "Entrega rápida, produto excelente!", "ENTREGA rapida - produto excelente."
        ]})
        self.assertEqual(len(remove_near_duplicates(raw)), 1)

    def test_merge_and_aspect_aggregation(self):
        reviews = pd.DataFrame({"id_produto": [1], "comentario": ["bom"]})
        products = pd.DataFrame({"id_produto": [1], "nome": ["Fone"], "categoria": ["eletronicos"], "preco": [100.0]})
        merged = merge_products(reviews, products)
        self.assertEqual(merged.loc[0, "nome"], "Fone")
        enriched = merged.assign(aspectos=[[
            {"aspecto": "qualidade", "sentimento": "positivo"},
            {"aspecto": "entrega", "sentimento": "negativo"},
        ]])
        aspects = explode_aspects(enriched)
        summary = aggregate_aspects(aspects)
        ranking = rank_problems_by_category(aspects)
        self.assertEqual(int(summary["quantidade"].sum()), 2)
        self.assertEqual(ranking.loc[0, "aspecto"], "entrega")
        self.assertEqual(ranking.loc[0, "categoria"], "eletronicos")

if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Executar os testes para confirmar falha**

Run: `projetos/analista-feedback/.venv/bin/python -m unittest discover -s projetos/analista-feedback/tests -p 'test_pipeline.py' -v`  
Expected: FAIL com `ModuleNotFoundError: pipeline`.

- [x] **Step 3: Implementar schemas e funções puras**

Em `schemas.py`, use Pydantic v2 (`BaseModel`, `Field`, `Literal`). Em `pipeline.py`, implemente as assinaturas acima e estas regras:

```python
NOTE_WORDS = {"cinco": 5.0, "quatro": 4.0, "três": 3.0, "tres": 3.0, "dois": 2.0, "um": 1.0}

# load_feedback: pd.read_csv para cada caminho/objeto file-like, sem fechar
# buffers pertencentes ao chamador.
# normalize_comment: Unicode NFKD -> casefold -> remover marcas combinantes
# -> manter apenas letras/dígitos, substituindo pontuação por espaço.
# parse_rating: trocar vírgula por ponto; converter palavras em NOTE_WORDS;
# valores ausentes/inválidos viram float("nan").
# clean_reviews: pd.to_datetime(..., format="mixed", dayfirst=True, errors="coerce").
# remove_near_duplicates: comparação apenas no mesmo id_produto;
# comentários vazios são preservados e não comparam como duplicata aproximada.
# aggregate_aspects: groupby nome,categoria,aspecto,sentimento e tamanho;
# renomear a contagem para quantidade.
# rank_problems_by_category: filtrar sentimento == "negativo", agrupar
# categoria/aspecto, nomear a contagem quantidade e ordenar decrescente.
```

Implemente `FeedbackAnalysis` com `aspectos: list[AspectAnalysis] = Field(default_factory=list)`. `explode_aspects` deve ignorar registros sem lista de aspectos e retornar DataFrame vazio com as colunas `nome,categoria,aspecto,sentimento` quando não houver linhas.

- [x] **Step 4: Rodar testes de dados e pipeline**

Run: `projetos/analista-feedback/.venv/bin/python -m unittest discover -s projetos/analista-feedback/tests -v`  
Expected: PASS para conversão de notas/datas, retenção de comentário vazio, deduplicação, merge e agregação.

- [x] **Step 5: Commitar a entrega**

```bash
git add projetos/analista-feedback/schemas.py projetos/analista-feedback/pipeline.py projetos/analista-feedback/tests/test_pipeline.py
git commit -m "feat(feedback): add pandas pipeline"
```

---

### Task 3: Classificação estruturada, retry limitado e contradições

**Files:**
- Modify: `projetos/analista-feedback/pipeline.py`
- Modify: `projetos/analista-feedback/tests/test_pipeline.py`

**Interfaces:**
- `analyze_comment(comment: str, client, model: str, max_attempts: int = 2) -> FeedbackAnalysis` faz uma chamada por tentativa e falha após no máximo duas tentativas.
- `enrich_reviews(df, client, model: str, max_attempts: int = 2) -> tuple[pd.DataFrame, pd.DataFrame]` retorna linhas enriquecidas e uma tabela de falhas com `id,comentario,erro`.
- `find_rating_conflicts(df: pd.DataFrame) -> pd.DataFrame` sinaliza nota `>= 4` com sentimento negativo ou nota `<= 2` com sentimento positivo.

- [x] **Step 1: Escrever testes com cliente falso, sem rede**

```python
from types import SimpleNamespace
from pipeline import analyze_comment, enrich_reviews, find_rating_conflicts

VALID_JSON = '{"sentimento_geral":"negativo","idioma":"pt","urgente":true,"aspectos":[{"aspecto":"qualidade","sentimento":"negativo"}]}'

from schemas import FeedbackAnalysis

class FakeCompletions:
    def __init__(self, contents):
        self.contents = iter(contents)
        self.calls = 0
    def parse(self, **kwargs):
        self.calls += 1
        content = next(self.contents)
        parsed = FeedbackAnalysis.model_validate_json(content)
        message = SimpleNamespace(parsed=parsed)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

class FakeClient:
    def __init__(self, contents):
        self.completions = FakeCompletions(contents)
        self.beta = SimpleNamespace(chat=SimpleNamespace(completions=self.completions))

class FeedbackAiTests(unittest.TestCase):
    def test_invalid_json_retries_once_then_validates(self):
        client = FakeClient(["não-json", VALID_JSON])
        result = analyze_comment("Quebrou no primeiro dia", client, "fake", max_attempts=2)
        self.assertEqual(result.sentimento_geral, "negativo")
        self.assertEqual(client.completions.calls, 2)

    def test_blank_comment_is_recorded_without_api_call(self):
        client = FakeClient([])
        enriched, errors = enrich_reviews(
            pd.DataFrame({"id": [4], "comentario": [""]}), client, "fake", max_attempts=2
        )
        self.assertEqual(len(enriched), 0)
        self.assertEqual(errors.loc[0, "id"], 4)
        self.assertEqual(client.completions.calls, 0)

    def test_attempt_count_is_bounded_and_conflict_rule_is_applied(self):
        client = FakeClient(["bad", "still bad", "unexpected third call"])
        with self.assertRaises(ValueError):
            analyze_comment("comentário", client, "fake", max_attempts=2)
        self.assertEqual(client.completions.calls, 2)
        rows = pd.DataFrame({"nota": [5.0, 1.0, 3.0], "sentimento_geral": ["negativo", "positivo", "negativo"]})
        self.assertEqual(len(find_rating_conflicts(rows)), 2)
```

- [x] **Step 2: Rodar os testes para confirmar falha**

Run: `projetos/analista-feedback/.venv/bin/python -m unittest discover -s projetos/analista-feedback/tests -p 'test_pipeline.py' -v`  
Expected: FAIL porque `analyze_comment` e `enrich_reviews` ainda não existem.

- [x] **Step 3: Implementar a chamada OpenAI e o processamento por linha**

`analyze_comment` deve enviar system prompt com as categorias permitidas e usar o Structured Outputs do SDK: `client.beta.chat.completions.parse(..., response_format=FeedbackAnalysis)`, `temperature=0.1` e `max_tokens=350`. Retorne `response.choices[0].message.parsed`; se vier `None`, trate como falha de parsing. Passe o cliente como dependência para que o teste nunca crie um `OpenAI()` real. Retente somente exceções de API/parsing/validação e, ao esgotar `max_attempts`, propague uma exceção com a causa final. `enrich_reviews` não chama a API para comentários vazios, registra a falha e continua com as demais linhas. Adicione as colunas de saída `sentimento_geral`, `idioma`, `urgente`, `aspectos` e `erro_analise`.

`find_rating_conflicts` aplica os limites `nota >= 4` + sentimento geral negativo e `nota <= 2` + sentimento geral positivo; valores nulos não são classificados como conflito.

- [x] **Step 4: Rodar os testes de retry e falha isolada**

Run: `projetos/analista-feedback/.venv/bin/python -m unittest discover -s projetos/analista-feedback/tests -v`  
Expected: PASS; o cliente falso recebe duas chamadas no teste de retry e zero no comentário vazio.

- [x] **Step 5: Commitar a entrega**

```bash
git add projetos/analista-feedback/pipeline.py projetos/analista-feedback/tests/test_pipeline.py
git commit -m "feat(feedback): validate AI analyses"
```

---

### Task 4: Streamlit, documentação e smoke check

**Files:**
- Create: `projetos/analista-feedback/app.py`
- Create: `projetos/analista-feedback/README.md`
- Modify: root `README.md`
- Test: `projetos/analista-feedback/tests/test_app_smoke.py`

**Interfaces:**
- `main()` é o ponto de entrada do app e só é executado por `streamlit run app.py`.
- O app aceita dois uploads CSV (uploads completos têm prioridade) ou usa os arquivos incluídos quando `Usar dados sintéticos` estiver marcado.

- [x] **Step 1: Escrever smoke test de import e função principal**

```python
# test_app_smoke.py
import importlib.util
import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"
sys.path.insert(0, str(APP.parent))

class AppSmokeTests(unittest.TestCase):
    def test_app_module_compiles_and_defines_main(self):
        spec = importlib.util.spec_from_file_location("feedback_app", APP)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(callable(module.main))

if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Executar o smoke test para confirmar falha**

Run: `projetos/analista-feedback/.venv/bin/python -m unittest discover -s projetos/analista-feedback/tests -p 'test_app_smoke.py' -v`  
Expected: FAIL porque `app.py` ainda não existe.

- [x] **Step 3: Implementar app e instruções de execução**

O `app.py` deve:
1. exibir `st.file_uploader` para os dois CSVs e uma opção marcada por padrão para carregar o dataset sintético; quando ambos uploads estiverem presentes, eles prevalecem sobre a amostra; se apenas um foi enviado, solicitar o segundo;
2. aceitar CSV enviado via `UploadedFile` ou `Path` local no mesmo `load_feedback`;
3. criar o cliente OpenAI somente após verificar `OPENAI_API_KEY`; sem chave, mostrar `st.warning` com o caminho do `.env.example` e não iniciar chamadas;
4. processar somente no clique de `Analisar comentários`, gerar chave SHA-256 dos bytes dos dois CSVs, guardar resultados em cache de `st.session_state` indexado por essa chave e reutilizá-los em reruns ou clique repetido para os mesmos dados;
5. exibir contagem processada/falha, conflitos de nota, `st.bar_chart` de aspectos/sentimentos, ranking negativo por categoria e tabela com comentário original, produto, categoria e filtros;
6. capturar erros de arquivos e mostrar a mensagem sem traceback.

O README explica `python -m venv .venv`, ativação, `pip install -r requirements.txt`, copiar `.env.example` para `.env`, preencher a chave e rodar `streamlit run app.py`. Inclua um gabarito manual: ID 1 é positivo, ID 2 é ironia/negativo apesar da nota 5, ID 3 está em inglês, IDs 5 e 6 são quase duplicados, ID 7 duplica exatamente o ID 1 e ID 4 é preservado como comentário vazio sem chamada à API. No README da raiz, acrescente uma seção `Projetos finais — exemplos` com o link `projetos/analista-feedback/README.md`.

- [x] **Step 4: Rodar testes, compilação e smoke do Streamlit**

Run: `projetos/analista-feedback/.venv/bin/python -m unittest discover -s projetos/analista-feedback/tests -v`  
Expected: PASS sem chave de API.  
Run: `projetos/analista-feedback/.venv/bin/python -m compileall -q projetos/analista-feedback`  
Expected: sem erros de sintaxe.  
Run manual: `cd projetos/analista-feedback && .venv/bin/streamlit run app.py`  
Expected: app abre, mostra aviso de chave ausente se `.env` ainda não estiver configurado e não dispara requisição.

- [x] **Step 5: Commitar a entrega**

```bash
git add README.md projetos/analista-feedback/app.py projetos/analista-feedback/README.md projetos/analista-feedback/tests/test_app_smoke.py
git commit -m "feat(feedback): add Streamlit starter"
```
