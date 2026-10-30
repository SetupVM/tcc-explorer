"""Configuração lida de variáveis de ambiente (arquivo .env da pasta do app).

Todos os valores têm um padrão seguro, então o app funciona sem .env —
exceto as respostas com LLM, que precisam de OPENAI_API_KEY.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

PASTA_APP = Path(__file__).resolve().parents[1]
load_dotenv(PASTA_APP / ".env")


def _texto(nome: str, padrao: str) -> str:
    valor = os.getenv(nome, "").strip()
    return valor or padrao


def _inteiro(nome: str, padrao: int) -> int:
    try:
        return int(_texto(nome, str(padrao)))
    except ValueError:
        return padrao


def _decimal(nome: str, padrao: float) -> float:
    try:
        return float(_texto(nome, str(padrao)))
    except ValueError:
        return padrao


def _booleano(nome: str, padrao: bool) -> bool:
    valor = _texto(nome, str(padrao)).lower()
    return valor in {"1", "true", "sim", "yes", "on"}


# Pastas de dados (nada aqui vai para o Git)
PASTA_DADOS = Path(_texto("PASTA_DADOS", str(PASTA_APP / "dados"))).resolve()
PASTA_PDFS = PASTA_DADOS / "pdfs"
PASTA_EXTRACOES = PASTA_DADOS / "extracoes"
PASTA_CHROMA = PASTA_DADOS / "chroma"
ARQUIVO_CATALOGO = PASTA_DADOS / "catalogo.csv"

# Limites de importação
MAX_ARQUIVOS_POR_ENVIO = _inteiro("MAX_ARQUIVOS_POR_ENVIO", 10)
MAX_TAMANHO_MB = _inteiro("MAX_TAMANHO_MB", 50)
MAX_PAGINAS = _inteiro("MAX_PAGINAS", 80)

# Extração (Docling)
EXTRACAO_OCR = _texto("EXTRACAO_OCR", "auto")  # auto | desligado | pagina_inteira
EXTRACAO_FORMULAS = _booleano("EXTRACAO_FORMULAS", True)
EXTRACAO_TABELAS_PRECISAS = _booleano("EXTRACAO_TABELAS_PRECISAS", True)

# Melhorias depois do Docling (podem ser reaplicadas sem reprocessar)
FORMULAS_SEGUNDA_LEITURA = _booleano("FORMULAS_SEGUNDA_LEITURA", True)
MODELO_FORMULAS = _texto("MODELO_FORMULAS", "ByteDance/Dolphin-1.5")
# MinerU é opcional e roda em outro ambiente para isolar suas dependências.
MINERU_PYTHON = Path(_texto("MINERU_PYTHON", str(
    PASTA_APP / ".venv-mineru" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
))).expanduser().absolute()  # Preserve o symlink do venv para carregar seus pacotes.
MINERU_HOME = Path(_texto("MINERU_HOME", str(PASTA_APP / ".cache" / "mineru"))).expanduser().resolve()
MINERU_TIMEOUT = _inteiro("MINERU_TIMEOUT", 900)
INFERIR_METADADOS = _booleano("INFERIR_METADADOS", True)
DESCREVER_FIGURAS = _booleano("DESCREVER_FIGURAS", False)
VISAO_URL = _texto("VISAO_URL", "http://localhost:11434/v1")  # Ollama
VISAO_MODELO = _texto("VISAO_MODELO", "qwen2.5vl:7b")
VISAO_API_KEY = _texto("VISAO_API_KEY", "ollama")

# Indexação e busca
EMBEDDING_MODELO = _texto("EMBEDDING_MODELO", "BAAI/bge-m3")
TAMANHO_TRECHO = _inteiro("TAMANHO_TRECHO", 1200)  # em caracteres
TRECHOS_POR_PERGUNTA = _inteiro("TRECHOS_POR_PERGUNTA", 8)

# LLM (OpenAI, o mesmo SDK usado nas aulas)
OPENAI_MODELO = _texto("OPENAI_MODELO", "gpt-4o-mini")
OPENAI_TEMPERATURA = _decimal("OPENAI_TEMPERATURA", 0.1)
OPENAI_MAX_TOKENS = _inteiro("OPENAI_MAX_TOKENS", 1800)
# Opcional: outro servidor compatível com a API da OpenAI (ex.: Ollama local)
OPENAI_BASE_URL = _texto("OPENAI_BASE_URL", "")


def chave_llm_configurada() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def criar_pastas() -> None:
    for pasta in (PASTA_PDFS, PASTA_EXTRACOES, PASTA_CHROMA):
        pasta.mkdir(parents=True, exist_ok=True)
