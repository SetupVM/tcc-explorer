"""Importação e armazenamento dos PDFs enviados pelo usuário.

Cada arquivo é identificado pelo SHA-256 do conteúdo: o mesmo PDF enviado de
novo (mesmo com outro nome) é reconhecido e não é reprocessado. O PDF original
é guardado sem alterações em dados/pdfs/<sha256>.pdf.
"""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import pypdfium2 as pdfium


class ErroPDF(Exception):
    """Erro de validação com mensagem pronta para mostrar ao usuário."""


@dataclass
class InfoPDF:
    sha256: str
    paginas: int
    metadados: dict = field(default_factory=dict)  # Title/Author gravados no próprio PDF


def calcular_sha256(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def id_do_artigo(sha256: str) -> str:
    """Identificador curto e estável, derivado do hash."""
    return sha256[:12]


def validar_pdf(conteudo: bytes, max_mb: int, max_paginas: int) -> InfoPDF:
    """Confere se o arquivo é um PDF legível dentro dos limites configurados."""
    if not conteudo:
        raise ErroPDF("O arquivo está vazio.")

    tamanho_mb = len(conteudo) / (1024 * 1024)
    if tamanho_mb > max_mb:
        raise ErroPDF(f"O arquivo tem {tamanho_mb:.1f} MB; o limite é {max_mb} MB.")

    # A assinatura %PDF- deve aparecer logo no início do arquivo.
    if b"%PDF-" not in conteudo[:1024]:
        raise ErroPDF("O arquivo não é um PDF (assinatura %PDF ausente).")

    try:
        documento = pdfium.PdfDocument(conteudo)
    except pdfium.PdfiumError as erro:
        if "password" in str(erro).lower():
            raise ErroPDF(
                "O PDF está protegido por senha. Remova a proteção antes de importar."
            ) from erro
        raise ErroPDF(f"O PDF está corrompido ou não pôde ser lido ({erro}).") from erro

    try:
        paginas = len(documento)
        metadados = {
            chave: valor.strip()
            for chave, valor in documento.get_metadata_dict(skip_empty=True).items()
            if chave in ("Title", "Author") and valor.strip()
        }
    finally:
        documento.close()

    if paginas == 0:
        raise ErroPDF("O PDF não tem páginas.")
    if paginas > max_paginas:
        raise ErroPDF(f"O PDF tem {paginas} páginas; o limite é {max_paginas}.")

    return InfoPDF(sha256=calcular_sha256(conteudo), paginas=paginas, metadados=metadados)


def caminho_do_pdf(pasta_pdfs: Path, sha256: str) -> Path:
    return Path(pasta_pdfs) / f"{sha256}.pdf"


def salvar_pdf(conteudo: bytes, pasta_pdfs: Path) -> Path:
    """Grava o PDF original (byte a byte) se ainda não existir."""
    pasta_pdfs = Path(pasta_pdfs)
    pasta_pdfs.mkdir(parents=True, exist_ok=True)
    caminho = caminho_do_pdf(pasta_pdfs, calcular_sha256(conteudo))
    if not caminho.exists():
        caminho.write_bytes(conteudo)
    return caminho


def ler_metadados_pdf(caminho_pdf: Path) -> dict:
    """Title/Author gravados no arquivo (muitas vezes vazios ou errados)."""
    return validar_pdf(Path(caminho_pdf).read_bytes(), max_mb=10_000, max_paginas=100_000).metadados


def renderizar_pagina(caminho_pdf: Path, pagina: int, escala: float = 1.5):
    """Imagem (PIL) de uma página física do PDF, contando a partir de 1."""
    documento = pdfium.PdfDocument(str(caminho_pdf))
    try:
        imagem = documento[pagina - 1].render(scale=escala).to_pil()
    finally:
        documento.close()
    return imagem
