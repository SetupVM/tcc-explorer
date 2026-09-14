# IA na Prática: Do Zero à Automação Corporativa

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Pandas](https://img.shields.io/badge/Pandas-Data_Manipulation-150458.svg)](https://pandas.pydata.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-Web_App-FF4B4B.svg)](https://streamlit.io/)
[![OpenAI](https://img.shields.io/badge/LLM-OpenAI_/_Gemini-412991.svg)](https://openai.com/)

Repositório oficial do curso **IA na Prática** ministrado no [Instituto Mauá de Tecnologia](https://maua.br). 

Este curso foi desenhado para tirar a "mágica" da Inteligência Artificial e ensinar como projetar sistemas reais e robustos ao redor de LLMs (Large Language Models). O foco principal é capacitar alunos para o mercado de trabalho, unindo o poder de raciocínio das APIs de IA com a força de manipulação de dados do Python.

## 🎯 Objetivo do Curso
Sair da interface web (Chat) que todo mundo usa e entrar no código.
Aulas sobre:
1. Orquestrar chamadas de API (OpenAI/Gemini) controlando parâmetros como `Temperature` e Tokens.
2. Forçar modelos a retornarem dados estruturados (JSON) para integração com bancos de dados.
3. Implementar busca semântica e contexto recuperado (Mini-RAG).
4. Extrair, limpar e processar dados de arquivos complexos e planilhas bagunçadas usando **Pandas**.
5. Construir pipelines completos de automação que leem arquivos locais, tomam decisões com IA e geram relatórios.
6. Criar interfaces web interativas para suas automações usando **Streamlit**.

---

## 📚 Ementa (Conteúdo Programático)

### Módulo 1: Cérebro - APIs e IA Estruturada
- **Aula 1:** Arquitetura de Sistemas com IA (Stateless, Contexto e RAG) - Overview.
- **Aula 2:** API na prática com controle de custo (Hiperparâmetros, Economia de Tokens, Segurança).
- **Aula 3:** Structured JSON Outputs com Pydantic e Validação.
- **Aula 4:** Mini-RAG: Embeddings, Busca Semântica e Retrieval-Augmented Generation.

### Módulo 2: Corpo - Dados e Automação
- **Aula 5:** Pandas aplicado com enriquecimento por IA (Filtros, Limpeza, Agregação).
- **Aula 6:** Extração de Dados em Arquivos Complexos (PDF/TXT + IA).

### Módulo 3: Entrega e Produto Final
- **Aula 7:** Streamlit, Entrega Técnica e Demo Day (Transformando scripts em produto, Checklist de Engenharia, Apresentação).

---

## 🚀 Como começar (Setup)

Para rodar os códigos deste repositório, você precisará ter o [Python](https://www.python.org/downloads/) instalado na sua máquina (versão 3.10 ou superior recomendada).

### 1. Clone o repositório
```bash
git clone [https://github.com/pedromatumoto/ia-na-pratica.git](https://github.com/pedromatumoto/ia-na-pratica.git)
cd ia-na-pratica
```

### 2. Crie um Ambiente Virtual (Recomendado)

```bash
python -m venv venv
# No Windows:
venv\Scripts\activate
# No Linux/Mac:
source venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```


### 4. Configuração de Chaves de API (!)

*NUNCA* suba suas chaves de API no GitHub. Crie um arquivo chamado .env na raiz do projeto e adicione suas chaves:

```
OPENAI_API_KEY="sk-sua-chave-aqui"
GEMINI_API_KEY="sua-chave-aqui"
```

O código usará a biblioteca python-dotenv para carregar essas variáveis de forma segura.
