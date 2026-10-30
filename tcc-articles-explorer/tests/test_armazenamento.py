import pytest

from explorador.armazenamento import ErroPDF, caminho_do_pdf, validar_pdf
from explorador.biblioteca import importar_pdf
from tests.conftest import gerar_pdf_em_branco


def test_mesmo_arquivo_com_outro_nome_nao_e_reimportado(catalogo, pastas):
    conteudo = gerar_pdf_em_branco(2)

    catalogo, primeiro = importar_pdf(catalogo, conteudo, "artigo.pdf", pastas)
    catalogo, segundo = importar_pdf(catalogo, conteudo, "copia_renomeada.pdf", pastas)

    assert primeiro.situacao == "importado"
    assert segundo.situacao == "duplicado"
    assert segundo.artigo_id == primeiro.artigo_id
    assert "artigo.pdf" in segundo.mensagem
    assert len(catalogo) == 1
    assert catalogo.iloc[0]["arquivo_original"] == "artigo.pdf"
    assert len(list(pastas.pdfs.glob("*.pdf"))) == 1


def test_conteudos_diferentes_viram_artigos_diferentes(catalogo, pastas):
    catalogo, _ = importar_pdf(catalogo, gerar_pdf_em_branco(1, marca="a"), "a.pdf", pastas)
    catalogo, _ = importar_pdf(catalogo, gerar_pdf_em_branco(1, marca="b"), "b.pdf", pastas)
    assert len(catalogo) == 2
    assert catalogo["sha256"].is_unique


def test_pdf_original_e_preservado_byte_a_byte(catalogo, pastas):
    conteudo = gerar_pdf_em_branco(1)
    catalogo, resultado = importar_pdf(catalogo, conteudo, "original.pdf", pastas)
    salvo = caminho_do_pdf(pastas.pdfs, catalogo.iloc[0]["sha256"])
    assert salvo.read_bytes() == conteudo


@pytest.mark.parametrize(
    "conteudo, trecho_da_mensagem",
    [
        (b"", "vazio"),
        (b"isto nao e um pdf, e um texto qualquer", "não é um PDF"),
        (b"%PDF-1.7\n isto parece pdf mas esta quebrado", "corrompido"),
    ],
)
def test_pdf_invalido_gera_erro_compreensivel(catalogo, pastas, conteudo, trecho_da_mensagem):
    catalogo, resultado = importar_pdf(catalogo, conteudo, "ruim.pdf", pastas)
    assert resultado.situacao == "erro"
    assert trecho_da_mensagem in resultado.mensagem
    assert catalogo.empty


def test_pdf_protegido_por_senha():
    with pytest.raises(ErroPDF, match="protegido por senha"):
        validar_pdf(gerar_pdf_em_branco(1, senha="segredo"), max_mb=10, max_paginas=10)


def test_limites_de_tamanho_e_de_paginas():
    conteudo = gerar_pdf_em_branco(5)
    with pytest.raises(ErroPDF, match="limite é 3"):
        validar_pdf(conteudo, max_mb=10, max_paginas=3)
    with pytest.raises(ErroPDF, match="MB"):
        validar_pdf(conteudo + b" " * (2 * 1024 * 1024), max_mb=1, max_paginas=10)


def test_validacao_conta_paginas():
    info = validar_pdf(gerar_pdf_em_branco(4), max_mb=10, max_paginas=10)
    assert info.paginas == 4
    assert len(info.sha256) == 64
