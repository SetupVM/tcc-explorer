import hashlib
import io
import math
import re

import pytest
from pypdf import PdfWriter

from explorador.biblioteca import Pastas
from explorador.catalogo import catalogo_vazio


def gerar_pdf_em_branco(paginas: int = 1, senha: str | None = None, marca: str = "") -> bytes:
    """PDF mínimo com páginas em branco. `marca` muda os bytes (hash diferente)."""
    escritor = PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(width=595, height=842)
    if marca:
        escritor.add_metadata({"/Subject": marca})
    if senha:
        escritor.encrypt(user_password=senha, owner_password=senha)
    buffer = io.BytesIO()
    escritor.write(buffer)
    return buffer.getvalue()


class EmbeddingsFalsos:
    """Embeddings determinísticos (saco de palavras com hash) para testar o índice
    sem baixar modelos. Não medem qualidade semântica."""

    nome = "teste/hash-64"

    def _vetor(self, texto: str) -> list[float]:
        vetor = [0.0] * 64
        for palavra in re.findall(r"\w+", texto.lower()):
            posicao = int(hashlib.md5(palavra.encode()).hexdigest(), 16) % 64
            vetor[posicao] += 1.0
        norma = math.sqrt(sum(v * v for v in vetor)) or 1.0
        return [v / norma for v in vetor]

    def documentos(self, textos: list[str]) -> list[list[float]]:
        return [self._vetor(t) for t in textos]

    def pergunta(self, texto: str) -> list[float]:
        return self._vetor(texto)


@pytest.fixture
def pastas(tmp_path) -> Pastas:
    return Pastas.em(tmp_path / "dados")


@pytest.fixture
def catalogo():
    return catalogo_vazio()


@pytest.fixture
def embeddings_falsos():
    return EmbeddingsFalsos()


@pytest.fixture
def indice(tmp_path, embeddings_falsos):
    from explorador.indice import IndiceTrechos

    return IndiceTrechos(tmp_path / "chroma", embeddings_falsos)


def elemento(id_, tipo, texto="", paginas=(1,), secao="", **extras) -> dict:
    """Atalho para montar elementos como os de elementos.json."""
    return {"id": id_, "tipo": tipo, "texto": texto, "secao": secao, "paginas": list(paginas), "caixa": None, **extras}
