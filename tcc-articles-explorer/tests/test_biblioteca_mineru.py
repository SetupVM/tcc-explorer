"""Comparação opcional: persistência e falhas sem carregar modelos."""

import json

import pytest

from explorador import biblioteca as bib
from explorador import catalogo as cat
from tests.conftest import elemento, gerar_pdf_em_branco


def _preparar(catalogo, pastas):
    catalogo, envio = bib.importar_pdf(catalogo, gerar_pdf_em_branco(2), "formula.pdf", pastas)
    artigo_id = envio.artigo_id
    pasta = pastas.do_artigo(artigo_id)
    pasta.mkdir(parents=True)
    formula = elemento(
        "e0", "formula", "x=y", latex="x=z", latex_fonte="manual", latex_revisado=True,
        latex_docling="x=y", caixa={"pagina": 1, "x0": 100, "y0": 100, "x1": 400, "y1": 200,
                                   "largura_pagina": 1000, "altura_pagina": 1000},
    )
    (pasta / "elementos.json").write_text(json.dumps([formula]))
    (pasta / "manifesto.json").write_text(json.dumps({"status": "concluída", "config": {}, "alertas": []}))
    catalogo = cat.atualizar_artigo(catalogo, artigo_id, {"status_extracao": "concluída",
        "status_indexacao": "indexado", "qualidade_verificada": True})
    return catalogo, artigo_id, pasta


class LeitorFalso:
    def ler(self, pdf, cache, paginas, forcar=False):
        assert pdf.is_file()
        assert paginas == [1]
        return {"formulas": [{"id": "m0", "pagina": 1, "latex": "x=w",
                              "caixa": {"x0": .1, "y0": .1, "x1": .4, "y1": .2}}],
                "modelo": "MinerU teste", "versao": "4.0.12", "reaproveitado": False}


def test_mineru_persiste_alternativa_preserva_escolha_e_invalida_indice(catalogo, pastas):
    catalogo, artigo_id, pasta = _preparar(catalogo, pastas)
    atualizado, relatorio = bib.comparar_formulas_mineru(catalogo, artigo_id, pastas, LeitorFalso(), [1])
    formula = bib.carregar_elementos(pasta)[0]
    assert relatorio["associadas"] == 1
    assert formula["latex_mineru"] == "x=w"
    assert formula["latex"] == "x=z" and formula["latex_fonte"] == "manual"
    assert formula["latex_revisado"]
    assert atualizado.iloc[0]["status_indexacao"] == "reindexação necessária"
    assert not atualizado.iloc[0]["qualidade_verificada"]
    assert bib.carregar_manifesto(pasta)["formulas_mineru"]["modelo"] == "MinerU teste"


def test_falha_mineru_preserva_arquivos_e_catalogo(catalogo, pastas):
    from explorador.mineru import ErroMinerU

    catalogo, artigo_id, pasta = _preparar(catalogo, pastas)
    antes = {p.name: p.read_bytes() for p in pasta.iterdir()}
    original = catalogo.copy(deep=True)

    class Falha:
        def ler(self, *args, **kwargs):
            raise ErroMinerU("Modelo indisponível")

    with pytest.raises(ErroMinerU, match="indisponível"):
        bib.comparar_formulas_mineru(catalogo, artigo_id, pastas, Falha(), [1])
    assert catalogo.equals(original)
    assert {p.name: p.read_bytes() for p in pasta.iterdir()} == antes


@pytest.mark.parametrize("paginas", [[], [0], [-1], [3], [1.5], [True]])
def test_mineru_rejeita_paginas_invalidas_antes_de_executar(catalogo, pastas, paginas):
    from explorador.mineru import ErroMinerU

    catalogo, artigo_id, _ = _preparar(catalogo, pastas)
    with pytest.raises(ErroMinerU, match="páginas válidas"):
        bib.comparar_formulas_mineru(catalogo, artigo_id, pastas, object(), paginas)
