# 📚 Explorador de Artigos

Aplicação local para apoiar estudantes na leitura de artigos científicos de
computação e IA e na elaboração de possíveis recortes de TCC.

Você escolhe e baixa os artigos (PDF), envia para o app, confere o que foi
extraído e faz perguntas em português. As respostas vêm com o artigo e a página
de cada evidência, e o app separa o que os autores relataram do que é sugestão
do assistente.

> Projeto final do curso **IA na Prática** (Instituto Mauá de Tecnologia).

---

## O problema

Ler 5 a 10 artigos em inglês para encontrar um tema de TCC é lento: métodos,
métricas e limitações ficam espalhados em PDFs de duas colunas, com tabelas,
fórmulas e figuras. Copiar trechos para um chat genérico não resolve, porque as
respostas não dizem de onde vieram e podem inventar resultados.

## A solução

```
PDFs escolhidos pelo estudante
        │  upload (Streamlit)
        ▼
1. Importação ─── SHA-256, validação, PDF original preservado
        ▼
2. Extração (Docling, local) ─── texto, seções, tabelas, fórmulas (LaTeX), figuras, páginas
        ▼                         → documento.json, documento.md, imagens/, elementos.json
   Melhorias (sem rodar o Docling de novo):
   · parágrafos unidos entre páginas, marcas d'água removidas, texto perdido recuperado do PDF
   · segunda leitura das fórmulas (Dolphin-1.5) e comparação com a do Docling
   · descrição das figuras por modelo de visão local (Ollama, opcional)
   · título e tema inferidos do texto (LLM; sem chave, similaridade local)
        ▼
3. Catálogo (Pandas) ─── metadados, limpeza, duplicatas, filtros, gráficos, CSV
        ▼
4. Índice (ChromaDB + embeddings multilíngues locais) ─── trechos com artigo, seção e páginas
        ▼
5. Respostas (OpenAI, Structured Outputs) ─── citações validadas, "não encontrei" quando falta evidência
        ▼
6. Sugestões de TCC ─── título, pergunta, motivação, método, recursos, artigos de apoio, dúvidas
```

| Requisito do curso | Onde está |
|---|---|
| Leitura de arquivos externos | Upload de PDFs → `explorador/armazenamento.py`, `explorador/extracao.py` |
| Limpeza com Pandas | `normalizar_catalogo`: tipos, espaços, ausências, ano, DOI, autores, temas |
| Structured Outputs (aula 3) | respostas e inferência de título/tema (`explorador/metadados.py`) |
| Filtros e agregações | `filtrar_catalogo`, `contar_por`, `resumo_por_tema` (groupby) |
| API de LLM | `explorador/respostas.py` (OpenAI, `chat.completions.parse` + Pydantic) |
| RAG com ChromaDB | `explorador/indice.py` (persistente em `dados/chroma`) |
| Interface Streamlit | `app.py` + `interface/` (3 áreas) |
| requirements, README, `.env` | `requirements.txt`, este arquivo, `.env.example` |

---

## Primeira execução após clonar

O aplicativo fica em `tcc-articles-explorer/`. O `requirements.txt` da raiz do
repositório pertence às aulas; instale o arquivo desta pasta para executar o projeto.
Use **Python 3.12** para reproduzir a versão testada. Os ambientes, modelos,
credenciais e banco local são criados por quem clonar; não acompanham o Git.
O `requirements-lock.txt` registra o ambiente macOS arm64 usado nos testes;
para instalar, inclusive no Windows, use `requirements.txt`.

No macOS/Linux:

```bash
git clone https://github.com/SetupVM/tcc-explorer.git
cd tcc-explorer/tcc-articles-explorer
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python scripts/baixar_modelos.py
python -m streamlit run app.py
```

Se já clonou, comece no `cd` usando o caminho do seu clone. Edite o `.env`
com sua própria `OPENAI_API_KEY` para testar respostas e sugestões de TCC.
Com a chave vazia, é possível importar, extrair, indexar e buscar trechos.
O download dos modelos requer internet e pode demorar na primeira execução.
O script baixa Docling, embeddings BGE-M3 e Dolphin (segunda leitura de fórmulas,
ativada por padrão).
MinerU e Ollama são opcionais; a instalação do MinerU está mais abaixo.

No Windows (PowerShell), já dentro de `tcc-articles-explorer`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe scripts\baixar_modelos.py
.\.venv\Scripts\python.exe -m streamlit run app.py
```

### Criar a biblioteca e o banco vetorial

Não é necessário criar o banco com um script. Ao abrir o app, a pasta `dados/`
e a coleção Chroma são criadas automaticamente, inicialmente vazias.
Os PDFs em `artigos/` são exemplos de entrada, não são importados automaticamente.

1. Abra **1 · Importar e revisar** e selecione um PDF de `artigos/` pelo campo
   **Artigos em PDF**. Para começar, use `1706.03762v7.pdf` (*Attention Is All You Need*).
2. Mantenha **Indexar para perguntas quando a extração terminar sem problemas**
   marcado e clique em **Importar e processar**.
3. Confira os alertas, o texto, as tabelas e as fórmulas. Se a extração for parcial,
   revise os problemas antes de aceitar a indexação; use **Indexar/Reindexar**
   quando necessário. O resultado esperado é **Indexação: indexado**.
4. Em **3 · Perguntar**, selecione o artigo e busque, por exemplo,
   “Qual arquitetura os autores propõem?”. Para gerar a resposta com citações,
   configure a chave do LLM.

O app grava catálogo, extrações, PDFs importados e embeddings em `dados/`;
eles persistem entre execuções na mesma máquina. Recriar o índice a partir dos
PDFs demonstra o fluxo completo do trabalho e evita depender de um banco pronto.
O `.gitignore` permite os PDFs de `artigos/` e exclui `dados/`, `.env`, ambientes
virtuais e caches. Trocar o modelo de embeddings exige recriar/reindexar a base.

## Instalação

Pré-requisitos: **Python 3.11 ou 3.12** (testado com 3.12.2), ~6 GB livres em
disco para os modelos e internet na primeira execução.

```bash
cd tcc-articles-explorer
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Modelos (download único)

Tudo roda localmente, mas os modelos são baixados do Hugging Face na primeira
vez (ficam em `~/.cache/huggingface`, fora do projeto). Para baixar antes de
usar o app — recomendado antes de uma apresentação:

```bash
python scripts/baixar_modelos.py
```

| Modelo | Uso | Tamanho aproximado |
|---|---|---|
| Docling layout (Heron) + TableFormer | layout da página e estrutura de tabelas | ~0,5 GB |
| CodeFormulaV2 | fórmulas → LaTeX (`do_formula_enrichment`) | ~0,6 GB |
| RapidOCR (PP-OCR) | OCR de regiões sem texto | ~30 MB |
| BAAI/bge-m3 | embeddings multilíngues | ~2,3 GB (RAM ~2,5 GB) |

Funciona sem GPU (no Mac com Apple Silicon o PyTorch usa MPS). Nos testes, o
PDF sintético de 2 páginas levou ~25 s para extrair com fórmulas ligadas;
artigos reais maiores levam proporcionalmente mais (não medido aqui). O
resultado fica em disco e não é refeito.

### MinerU (opcional, terceira leitura de fórmulas)

O MinerU lê páginas selecionadas para comparar suas fórmulas com Docling e
Dolphin. Usa o modo **Basic/ONNX na CPU**, com PP-FormulaNet_plus-M, sem API
externa. Os pacotes ficam em outro ambiente porque suas versões de dependências
diferem das usadas pelo app. No macOS/Linux, a partir da pasta do aplicativo:

```bash
python -m venv .venv-mineru
.venv-mineru/bin/python -m pip install -r requirements-mineru.txt
MINERU_HOME="$PWD/.cache/mineru" .venv-mineru/bin/mineru-kit models download --tier basic --small-backend onnx --source huggingface
MINERU_HOME="$PWD/.cache/mineru" .venv-mineru/bin/mineru-kit models verify --tier basic --small-backend onnx
```

O download único precisa de internet; a comparação exige os modelos já locais
(cerca de 0,8 GB de pesos, além das dependências). No Windows, use os executáveis
em `.venv-mineru\Scripts` e defina `MINERU_HOME` no ambiente antes dos comandos.
As opções `.env` são `MINERU_PYTHON`, `MINERU_HOME` e `MINERU_TIMEOUT` (900 s).
Os padrões apontam para `.venv-mineru` e `.cache/mineru` dentro do app.

Na inspeção do artigo, abra **Fórmulas**, escolha as páginas físicas do PDF e
clique em **Comparar com MinerU**. Comece com uma página. A comparação preserva
a versão principal; use **Escolher ou corrigir → MinerU → Usar esta versão**
após conferir a imagem e reindexe o artigo para atualizar a busca.

Referências da integração: [SDK local](https://opendatalab.github.io/MinerU/usage/sdk_api/),
[modo Basic](https://opendatalab.github.io/MinerU/usage/tiers/) e
[formato de saída](https://opendatalab.github.io/MinerU/reference/output_files/).
O MinerU tem licença própria; consulte os termos do projeto antes de redistribuir.

### Chave do LLM

```bash
cp .env.example .env
```

Preencha `OPENAI_API_KEY` no `.env`. Sem a chave, importação, catálogo,
inspeção e busca de trechos funcionam; só as respostas e sugestões ficam
desabilitadas.

## Execução

```bash
streamlit run app.py
```

O app abre em `http://localhost:8501`.

> Depois de atualizar o código (por exemplo, um `git pull`), pare o app com
> Ctrl+C e rode de novo: o Streamlit nem sempre recarrega os módulos de
> `explorador/` e `interface/`, e o processo antigo pode mostrar `ImportError`.

---

## Como usar

**1 · Importar e revisar** — envie até 10 PDFs (limites no `.env`), informe um
tema opcional e clique em *Importar e processar*. Para cada arquivo aparece o
resultado: importado, duplicado (mesmo conteúdo, ainda que com outro nome) ou
erro (arquivo inválido, protegido por senha, grande demais). Depois escolha um
artigo para:

- conferir e corrigir **metadados** (título, autores, ano, DOI, tema,
  palavras-chave). Todos vêm do próprio artigo (botão *Preencher a partir do
  artigo*), cada um com a origem indicada; o que você digitar nunca é
  sobrescrito;
- ver a **situação**: versão do Docling, configuração usada, alertas
  (páginas vazias, fórmulas sem LaTeX, figuras sem legenda, ordem de colunas
  corrigida, confiança baixa), e marcar **qualidade verificada** depois de
  conferir;
- **inspecionar** a extração: texto por página (com o texto recuperado do PDF
  destacado), tabelas, fórmulas com o recorte da imagem e até três leituras
  (escolha ou corrija as que divergem), figuras com legenda e descrição
  automática, e a página do PDF com a caixa e a ordem de leitura de cada
  elemento: a legenda tem caixa própria ("N leg."), a continuação de um
  parágrafo vindo da página anterior aparece como "N…", cabeçalho e rodapé
  (fora do índice) ficam em cinza, e a tela mede quanto texto do PDF ficou
  fora de qualquer caixa (nos 8 artigos digitais testados: 0%);
- **melhorar** (aplica as melhorias sem rodar o Docling), reindexar,
  reprocessar ou remover o artigo.

**2 · Biblioteca** — indicadores, filtros (tema, ano, status), tabela do
catálogo com tema, origem do tema e palavras-chave, possíveis duplicatas
sinalizadas, gráficos e exportação em CSV. *Melhorar todos os artigos* aplica
as melhorias em lote e reindexa (útil para extrações antigas).

**3 · Perguntar** — escolha os artigos (ou a biblioteca toda), faça uma
pergunta ou use um exemplo. A resposta separa **📄 Relatado nos artigos** de
**💡 Sugestão do assistente**, cita `[n] título, p. X` e cada trecho citado
abre com o texto original. A aba *Sugestões de recorte de TCC* gera de 1 a 3
propostas apoiadas nos trechos.

> **Páginas** são sempre as páginas físicas do arquivo PDF, contando a partir
> de 1 (não a numeração impressa no artigo).

---

## Arquitetura

```
tcc-articles-explorer/
├── app.py                    # Streamlit: navegação e barra lateral
├── interface/
│   ├── comum.py              # cache de recursos, componentes de tela
│   ├── pagina_importar.py    # área 1
│   ├── pagina_biblioteca.py  # área 2
│   └── pagina_perguntar.py   # área 3
├── explorador/
│   ├── config.py             # variáveis de ambiente
│   ├── armazenamento.py      # validação, SHA-256, PDF original
│   ├── extracao.py           # Docling (único módulo que o conhece)
│   ├── pos_processamento.py  # colunas, marcas d'água, parágrafos, texto perdido
│   ├── formulas.py           # limpeza do LaTeX, recorte, segunda leitura (Dolphin)
│   ├── mineru.py             # terceira leitura opcional, cache e associação por posição
│   ├── figuras.py            # descrição de figuras (modelo de visão via Ollama)
│   ├── metadados.py          # título e tema a partir do texto
│   ├── catalogo.py           # Pandas: limpeza, filtros, agregações
│   ├── trechos.py            # divisão em trechos (chunking)
│   ├── indice.py             # ChromaDB + embeddings
│   ├── respostas.py          # prompts, LLM, validação de citações
│   └── biblioteca.py         # orquestra importar → extrair → melhorar → indexar
├── scripts/                  # baixar_modelos.py, avaliar_rag.py, mineru_worker.py (ambiente isolado)
├── avaliacao/                # perguntas de avaliação (CSV)
├── tests/                    # pytest
└── dados/                    # gerado em execução (fora do Git)
    ├── catalogo.csv
    ├── pdfs/<sha256>.pdf
    ├── extracoes/<id>/{manifesto.json, elementos.json, documento.json, documento.md, imagens/}
    └── chroma/
```

### Decisões técnicas

**Identificação por hash.** O `id` do artigo são os 12 primeiros caracteres do
SHA-256 do conteúdo. Reenviar o mesmo PDF com outro nome não cria outra linha
nem reprocessa nada. Títulos parecidos ou o mesmo DOI só são **sinalizados**
como possível duplicata — preprint e versão publicada continuam separados.

**Extração (Docling 2.133).** Configuração em `extracao.criar_conversor`:
OCR automático só nas regiões sem camada de texto (opção de página inteira para
PDFs digitalizados), TableFormer em modo preciso, `do_formula_enrichment`
para LaTeX e recorte das figuras. A versão do Docling e a configuração ficam no
`manifesto.json`; se a configuração muda, o artigo pode ser reprocessado, e uma
extração válida com a mesma configuração é reaproveitada do disco.

**Ordem de leitura em duas colunas.** Nos testes, o preditor de ordem do
Docling leu a coluna da direita antes da esquerda quando havia uma linha de
autores centralizada. O app detecta essa inversão por página (um elemento da
direita lido antes de um da esquerda que está acima dele) e reordena **só essas
páginas** por coluna, avisando na inspeção. A ordem original continua no
`documento.json`.

**Texto que o Docling não pega.** Medimos, página a página, quantas palavras
da camada de texto do PDF apareceram na extração (nos 9 artigos testados: de
87% a 99,8%). Três correções rodam depois do Docling e podem ser reaplicadas
em extrações antigas pelo botão *Melhorar*:

- **parágrafo que continua na página seguinte**: se um trecho termina sem
  pontuação final e o próximo começa com minúscula numa página posterior, os
  dois são unidos, mesmo com figura, legenda, nota ou rótulo de figura no meio
  (achou casos em 6 dos 9 artigos);
- **marcas d'água** (carimbo do JSTOR com IP e data) deixam de ser texto do
  artigo, inclusive os pedaços curtos colados a elas;
- **texto perdido**: em páginas com cobertura abaixo de 85%, as linhas do PDF
  que não apareceram na extração entram como "texto recuperado do PDF"
  (destacado na inspeção e indexado como trecho próprio).

**Fórmulas.** O LaTeX do Docling vem com letras espaçadas
(`A t t e n t i o n`); o app limpa sem mudar o significado (preserva o espaço
depois de comandos e dentro de `\text{}`) e separa o número da equação.
Comparamos quatro leitores em 25 fórmulas recortadas dos artigos reais (6 com
gabarito conhecido, do *Attention*):

| | Docling (CodeFormula) | LaTeX-OCR (pix2tex) | **Dolphin-1.5** | Qwen2.5-VL 7B (Ollama) |
|---|---|---|---|---|
| Gabarito (6) | errou `d_model` e `step_num` | "Atention", `V V_i`, `1000` | **6/6** | certo, mas às vezes devolve um documento LaTeX inteiro |
| LaTeX interpretável (25) | 22 | 22 | **25** | 25 |
| Tempo por fórmula (CPU) | — (na extração) | ~1 s | 1,7 s | 4 s |
| Dependências | — | fixa `timm`/`x-transformers` antigos | nenhuma nova | Ollama + 6 GB |

Por isso o **Dolphin-1.5** (ByteDance, MIT) faz a segunda leitura: cada
fórmula é recortada do PDF, relida e comparada com a do Docling. Se a
semelhança fica abaixo de 97% (limite escolhido porque o erro em `d_model`
dava 94%), as duas leituras vão para o índice e a aba *Fórmulas* mostra o
recorte, as duas versões e permite escolher ou corrigir à mão. Se a leitura do
Docling não é LaTeX válido e a do Dolphin é, a do Dolphin vira a principal,
desde que o usuário ainda não tenha revisado a fórmula.

O **MinerU 4.0.12**, opcional, acrescenta outra leitura por página. A associação
usa página física e sobreposição de caixas normalizadas, com correspondência
única nos dois sentidos. Fórmulas sem associação ou com associação ambígua
aparecem separadas para inspeção; fórmulas inline sem caixa própria não são
associadas. O cache considera o PDF, páginas, versões e configuração. Falhas
na execução preservam as leituras anteriores.

Com três leitores, a interface compara todos os pares. Antes da revisão,
transcrições divergentes entram no contexto com sua origem e aviso de incerteza.
Depois de uma escolha explícita, só a versão escolhida entra na indexação.
Não há votação automática. O benchmark acima é anterior à inclusão do MinerU
e não permite concluir qual deles será melhor nos seus artigos.

**Figuras.** Como no projeto ollama-chromadb-image-search, um modelo de visão
local (`qwen2.5vl:7b` via Ollama, ~6 s por figura) descreve cada imagem, e a
descrição entra no índice junto da legenda, marcada como "descrição
automática; não é texto do artigo". O prompt do RAG proíbe apresentá-la como
resultado dos autores. É opcional (exige o Ollama).

**Metadados do artigo.** Ano e DOI saem primeiro de identificadores
impressos no PDF: DOI escrito na 1ª página ou o carimbo lateral do arXiv
(`arXiv:1706.03762v7 [cs.CL]` → ano da 1ª versão, 2017, e o DOI oficial
`10.48550/arXiv.1706.03762`); por último, do nome do arquivo baixado
(`2407.17866v2.pdf`, `ssrn-4849578.pdf`), com essa origem registrada. Com chave
do LLM, Structured Outputs lê o início do artigo e devolve título, autores,
ano, tema (lista fechada de áreas, para o catálogo agrupar bem) e
palavras-chave; cada autor e o ano só são aceitos se aparecerem no texto.
Nos 9 artigos testados: autores 9/9, ano 9/9, DOI 8/9 (o de 1910 não tem DOI
impresso). O título do Docling é mantido, a menos que pareça errado
(ex.: "Accessibility support:" vindo da capa do JSTOR); nesse caso entra o do
LLM, desde que apareça literalmente no texto. Sem chave, o tema é escolhido
por similaridade entre o início do artigo e a descrição de cada área (acertou
de forma plausível 7 dos 9 artigos). Temas informados por você não são
trocados, a não ser que peça.

**Trechos.** Não atravessam seções; parágrafos se juntam até 1.200 caracteres.
Fórmulas nunca são cortadas e ficam com o parágrafo anterior e o seguinte
(onde as variáveis costumam ser explicadas). Tabelas viram trechos próprios e,
se forem grandes, são divididas por linhas repetindo o cabeçalho. Figuras
entram pela legenda e pelo texto reconhecido dentro delas. Referências
bibliográficas e linhas de autores/afiliações não são indexadas. Cada trecho
guarda id estável (`<artigo>-<nnnn>`), artigo, título, seção, páginas e tipo.

**Embeddings.** Modelo local e multilíngue para perguntas em português sobre
artigos em inglês. Comparação feita com 8 perguntas sobre os artigos
sintéticos dos testes (posição do trecho correto, 16 trechos no índice):

| Modelo | Trecho certo no top 3 | Download |
|---|---|---|
| intfloat/multilingual-e5-small | 6/8 | ~0,5 GB |
| intfloat/multilingual-e5-base | 6/8* | ~1,1 GB |
| **BAAI/bge-m3** (padrão) | **7/8** (6 em 1º) | ~2,3 GB |

\* medido antes de remover do índice as linhas de autores; o e5-small subiu de
5/8 para 6/8 com essa mudança. É uma amostra pequena e sintética: serve para
escolher o padrão, não como benchmark.

O nome do modelo fica gravado na coleção do ChromaDB. Se `EMBEDDING_MODELO`
mudar, a busca é bloqueada até recriar o índice (botão na barra lateral).
Reindexar calcula os novos embeddings antes de alterar o índice, atualiza os
trechos por ID e remove os que sobraram. Se uma escrita falhar, tenta restaurar
os registros anteriores. Essa recuperação cobre exceções durante a operação,
não quedas do processo ou falhas de disco.

A busca considera apenas artigos marcados como indexados no catálogo. O limite
de trechos também vale para comparações e sugestões de TCC: a busca equilibrada
distribui as vagas entre artigos, sem ultrapassar o limite escolhido.

**Respostas.** O LLM recebe só os trechos recuperados, rotulados `T1, T2…`
entre marcas `<trecho>`, e devolve JSON validado por Pydantic. O código então:

- converte cada rótulo citado no id real do trecho e **descarta citações que
  não estavam no contexto** (avisando na tela);
- marca afirmações "do artigo" sem nenhuma citação válida e, se nenhuma tiver,
  considera a evidência insuficiente;
- monta as referências com os **metadados do catálogo** (não com o que o
  modelo escreveu).

O prompt de sistema trata o texto dos PDFs como material de consulta, nunca
como instrução, e o texto é neutralizado para não conseguir fechar a marca
`<trecho>` (teste de *prompt injection* incluído). As propostas de TCC sem
nenhum trecho válido são descartadas, e a tela lembra que a coleção é pequena
demais para afirmar ineditismo ou lacuna comprovada.

**Custo.** Extrações, embeddings e chamadas ao LLM só acontecem em botões
explícitos. Docling e índice ficam em `st.cache_resource`, e a mesma pergunta
com o mesmo contexto não é enviada duas vezes na sessão. O cache considera o
conteúdo, as páginas, os títulos, os prompts e os parâmetros do modelo; corrigir
e reindexar um artigo invalida a resposta anterior ao repetir a consulta.

## Processamento local e chamadas ao LLM

| Fica na sua máquina | Vai para a OpenAI |
|---|---|
| PDFs, imagens, extrações, catálogo | ao perguntar: a pergunta e o texto dos trechos recuperados (8 a ~20) e os títulos |
| embeddings e índice ChromaDB | ao sugerir TCC: o interesse e os trechos recuperados |
| Docling, Dolphin e embeddings | ao preencher metadados (se houver chave): os ~4 mil primeiros caracteres do artigo |
| descrição de figuras (Ollama local) | |

Para não usar a OpenAI, dá para apontar o mesmo código para um LLM local do
Ollama (`OPENAI_BASE_URL`, ver `.env.example`); com modelos pequenos como o
`llama3.2` o fluxo funciona, mas temas e respostas ficam bem piores.

Os PDFs inteiros nunca são enviados. Pela quantidade de trechos, uma pergunta
deve ficar entre ~3 e 8 mil tokens (estimativa; o app mostra o total real
abaixo de cada resposta). Modelo, temperatura e limite de tokens são configurados no `.env`
(`OPENAI_MODELO`, padrão `gpt-4o-mini`, o mesmo das aulas).

---

## Testes e avaliação

```bash
pip install -r requirements-dev.txt
pytest -m "not docling"     # rápidos (~2 s)
pytest                      # inclui integração real com Docling e embeddings (~1 min)
```

Cobertura dos comportamentos pedidos:

| Comportamento | Teste |
|---|---|
| Arquivo duplicado com nome diferente | `test_armazenamento::test_mesmo_arquivo_com_outro_nome_nao_e_reimportado` |
| Metadados ausentes | `test_catalogo::test_metadados_ausentes_ficam_vazios_e_aparecem_como_nao_informado` |
| PDF inválido / protegido / grande demais | `test_armazenamento::test_pdf_invalido_*`, `test_pdf_protegido_por_senha`, `test_limites_*` |
| Preservação das páginas | `test_trechos::test_paginas_sao_as_fisicas_e_comecam_em_1`, `test_integracao::test_extracao_concluida_com_paginas_fisicas` |
| Reindexação sem duplicação | `test_indice::test_reindexar_nao_duplica_trechos` |
| Consulta restrita aos artigos selecionados | `test_indice::test_busca_restrita_aos_artigos_selecionados`, `test_integracao::test_busca_restrita_com_artigos_reais_extraidos` |
| Referências a trechos inexistentes | `test_respostas::test_citacoes_viram_ids_reais_e_inexistentes_sao_descartadas` |
| Extração falha/parcial não indexada em silêncio | `test_biblioteca::test_extracao_que_falhou_nunca_e_indexada`, `test_extracao_parcial_exige_confirmacao` |
| Tabela, fórmula e figura reais | `test_integracao::test_tabela_figura_e_formula_reconhecidas` |
| Parágrafo entre páginas, marca d'água, texto perdido | `test_pos_processamento` |
| Limpeza do LaTeX, divergência, escolha manual preservada | `test_formulas`, `test_integracao::test_segunda_leitura_real_das_formulas_com_dolphin` |
| Título, autores e ano não inventados; valores do usuário preservados | `test_metadados_figuras` |
| Cache após correção, busca de artigos válidos e revisão de qualidade | `test_interface` (inclui AppTest) |
| Falha ao calcular/gravar vetores e limite da busca equilibrada | `test_indice` |
| MinerU: cache, timeout, saída incompatível, geometria e ambiente isolado | `test_mineru` |
| Terceira leitura sem sobrescrever escolhas, falha sem alterar artigo | `test_biblioteca_mineru` |
| Comparação e seleção de três leituras, páginas sem fórmulas Docling | `test_interface_mineru` (AppTest) |

Os testes de integração usam **artigos fictícios** gerados em
`tests/pdfs_sinteticos.py` (duas colunas, tabela, fórmula, figura, referências).
Os testes de `respostas` usam um cliente falso: verificam a validação de
citações e o prompt, **não** a qualidade do modelo.

Na validação de 25/10/2026, passaram 272 testes gerais e 11 de integração.
Separadamente, MinerU Basic/ONNX processou o PDF sintético de RAG (2 páginas)
em 13,8 s: encontrou a fórmula conhecida, reutilizou o cache na segunda chamada
e foi associado à fórmula do Docling sem ambiguidade (IoU 0,7695). Isso valida
o fluxo local, mas ainda não mede sua precisão nos artigos reais.

### Conferência com PDFs reais

Pipeline completo (importar → extrair → indexar) rodado em dois PDFs da pasta
`artigos/`, com conferência visual das páginas com caixas:

| | *Attention Is All You Need* (1706.03762) | 2610.23845 |
|---|---|---|
| Páginas / tempo | 15 / 144 s | 61 / 203 s |
| Seções, tabelas, fórmulas, figuras | 25, 4, 6, 7 | 74, 15, 3, 4 |
| Trechos indexados | 50 | 237 |
| Busca (`perguntas_artigos_reais.csv`) | trecho certo no top 8 em 7/7 perguntas (6 em 1º) | |

Erros reais que a inspeção mostrou (por isso a marcação de qualidade é manual):

- expoentes viraram texto corrido na Tabela 2 do *Attention* (`2.3 · 10^19` → `2.3 · 1019`);
- uma célula mesclada ("3.3 · 10^18") foi repetida nas duas colunas;
- o rótulo de uma figura ("Scaled Dot-Product Attention") virou cabeçalho de seção;
- a legenda da Figura 2 ficou ligada só a uma das duas imagens.

Os dois PDFs são de coluna única: a correção de duas colunas foi verificada
apenas com os PDFs sintéticos.

Para avaliar com seus artigos reais, copie `avaliacao/perguntas_modelo.csv`,
escreva perguntas cujas respostas você conferiu (e pelo menos uma sem resposta
na coleção) e rode:

```bash
python scripts/avaliar_rag.py avaliacao/minhas_perguntas.csv          # só busca, sem custo
python scripts/avaliar_rag.py avaliacao/minhas_perguntas.csv --llm    # inclui o LLM
```

## Limitações

- A extração é automática: fórmulas em LaTeX, tabelas complexas e símbolos
  podem sair errados sem que o Docling acuse erro (ex.: expoentes dentro de
  tabelas viram texto corrido). Por isso existe a marcação de qualidade
  verificada.
- A correção de ordem em duas colunas é uma heurística; layouts incomuns
  (três colunas, figuras no meio do texto) podem continuar fora de ordem.
- A união de parágrafos entre páginas e a recuperação de texto são
  heurísticas: confira na inspeção. O texto recuperado vem sem estrutura
  (sem seção e sem posição exata).
- As leituras de fórmulas podem errar do mesmo jeito; concordância não é
  garantia. Fórmulas em várias linhas às vezes são cortadas no recorte.
- O MinerU Basic também pode omitir ou transcrever mal fórmulas. Quando os
  leitores segmentam a mesma região de maneiras diferentes, a associação
  conservadora pode exigir conferência manual; as leituras sem associação
  não entram automaticamente no índice.
- Extrações anteriores ao pós-processamento v4 precisam passar por *Melhorar*
  e ser reindexadas para receber a correção de marcas d'água e fórmulas como
  `f(3)`. Escolhas manuais são preservadas. Leituras antigas do Dolphin sem
  saída original precisam de revisão ou nova leitura se estiverem incorretas.
- A validação de citações verifica se o trecho existe no contexto; não prova
  que o trecho sustenta semanticamente a afirmação. Confira as evidências.
- Descrições de figuras vêm de um modelo de visão e podem errar; por isso ficam
  marcadas e fora das afirmações "dos autores".
- O tema vem de uma lista fechada de áreas; com modelos pequenos a escolha
  piora. Sem chave do LLM, autores ficam vazios (ano e DOI ainda saem dos
  identificadores). O DOI derivado do arXiv identifica a versão do arXiv, não
  a publicação em revista ou conferência.
- Com 5 a 10 artigos, as sugestões de TCC são pontos de partida, não
  evidência de lacuna na literatura.
- Uso local e de um único usuário; não há autenticação. Não rode duas cópias
  do app (ou o app e um script) gravando na mesma pasta `dados/` ao mesmo
  tempo: o ChromaDB local não aceita escrita de vários processos e o índice
  pode corromper. Se acontecer, com o app parado, apague `dados/chroma`,
  inicie o app e use *Melhorar todos os artigos*: o índice é refeito a partir
  das extrações.

## Fora do escopo (evoluções futuras)

Busca/download de artigos na internet (os notebooks em `notebooks/` são
explorações separadas, não usadas pelo app), Dolphin como extrator de página inteira (alternativa ao
Docling), busca híbrida (BM25 + embeddings) e avaliação automática de
fidelidade das respostas.

## Versões

Testado com Python 3.12.2 (macOS, Apple Silicon). Dependências diretas em
`requirements.txt`; ambiente completo em `requirements-lock.txt`.

| Pacote | Versão |
|---|---|
| docling / docling-core / docling-ibm-models | 2.133.0 / 2.103.0 / 4.0.3 |
| rapidocr / onnxruntime | 3.9.2 / 1.31.0 |
| chromadb | 1.5.9 |
| sentence-transformers / torch | 6.1.0 / 2.14.1 |
| streamlit | 1.65.0 |
| openai | 3.24.0 |
| transformers / latex2mathml | 5.20.2 / 3.81.1 |
| Modelos | Docling (Heron, TableFormer, CodeFormulaV2), ByteDance/Dolphin-1.5, BAAI/bge-m3, qwen2.5vl:7b (Ollama, opcional) |
| pandas | 3.0.6 |

`rapidocr` está fixado em 3.9.2 porque a 3.10.0 deixa o OCR do Docling 2.133
desligado sem erro visível.
