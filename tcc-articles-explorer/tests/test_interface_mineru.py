"""UI do comparador opcional com leitores, catálogo e extrações em memória."""

from copy import deepcopy

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from explorador import catalogo as cat
from interface import pagina_importar as pagina


SCRIPT = '''
from interface import pagina_importar as p
catalogo = p.carregar_catalogo()
linha = catalogo.iloc[0]
p.aba_formulas(catalogo, linha, p.carregar_elementos(None), p.carregar_manifesto(None))
'''


@pytest.fixture
def ambiente_mineru(monkeypatch, pastas):
    registro = cat.novo_registro("a" * 64, "artigo.pdf", 3, titulo="Artigo de teste")
    registro.update(status_extracao="concluída", status_indexacao="indexado")
    estado = {
        "catalogo": cat.adicionar_artigo(cat.catalogo_vazio(), registro),
        "formulas": [
            {"id": "f1", "tipo": "formula", "texto": "x=1", "latex": "x=1", "latex_docling": "x=1",
             "latex_dolphin": "x=1", "latex_fonte": "docling", "paginas": [1], "secao": "Método"},
            {"id": "f2", "tipo": "formula", "texto": "y=2", "latex": "y=2", "latex_docling": "y=2",
             "latex_fonte": "docling", "paginas": [3], "secao": "Resultados"},
        ],
        "manifesto": {}, "chamadas": [], "leitores": [], "gravacoes": 0,
    }
    leitor = object()

    def obter_leitor():
        estado["leitores"].append(leitor)
        return leitor

    def salvar(catalogo):
        estado["catalogo"] = catalogo.copy(deep=True)
        estado["gravacoes"] += 1

    def comparar(catalogo, artigo_id, pastas_recebidas, leitor_recebido, paginas, forcar=False):
        estado["chamadas"].append((artigo_id, pastas_recebidas, leitor_recebido, paginas, forcar))
        relatorio = {"associadas": 1 if estado["formulas"] else 0, "ambiguas": 1 if estado["formulas"] else 0, "sem_correspondencia": 1,
                     "paginas": paginas, "nao_associadas": [{"pagina": paginas[0], "latex": "z=9"}]}
        estado["manifesto"]["formulas_mineru"] = relatorio
        return cat.atualizar_artigo(catalogo, artigo_id, {"status_indexacao": "reindexação necessária"}), relatorio

    monkeypatch.setattr(pagina, "PASTAS", pastas)
    monkeypatch.setattr(pagina, "carregar_catalogo", lambda: estado["catalogo"].copy(deep=True))
    monkeypatch.setattr(pagina, "salvar_catalogo", salvar)
    monkeypatch.setattr(pagina, "carregar_elementos", lambda caminho: deepcopy(estado["formulas"]))
    monkeypatch.setattr(pagina, "carregar_manifesto", lambda caminho: deepcopy(estado["manifesto"]))
    monkeypatch.setattr(pagina, "situacao_mineru", lambda: (True, "MinerU disponível"))
    monkeypatch.setattr(pagina, "obter_leitor_mineru", obter_leitor)
    monkeypatch.setattr(pagina.bib, "comparar_formulas_mineru", comparar, raising=False)
    estado["leitor"] = leitor
    return estado


def test_mineru_nao_roda_ao_abrir_aba_e_compara_so_paginas_pedidas(ambiente_mineru, pastas):
    estado = ambiente_mineru
    app = AppTest.from_string(SCRIPT).run()
    assert not app.exception
    assert estado["chamadas"] == estado["leitores"] == []
    assert app.multiselect[0].value == [1]
    app.multiselect[0].set_value([3]).run()
    app.checkbox[0].check().run()
    assert estado["chamadas"] == []
    app.button(key="comparar_mineru_" + "a" * 12).click().run()
    assert not app.exception
    assert estado["chamadas"] == [("a" * 12, pastas, estado["leitor"], [3], True)]
    assert estado["gravacoes"] == 1
    assert estado["catalogo"].iloc[0]["status_indexacao"] == "reindexação necessária"
    assert "reindexe" in app.session_state["aviso_revisao"][1]
    assert any("sem associação (1)" in e.label for e in app.expander)
    assert any(c.value == "z=9" for c in app.code)


def test_mineru_ausente_orienta_instalacao_sem_carregar_leitor(monkeypatch, ambiente_mineru):
    monkeypatch.setattr(pagina, "situacao_mineru", lambda: (False, "Ambiente não encontrado."))
    app = AppTest.from_string(SCRIPT).run()
    assert not app.exception
    assert app.button(key="comparar_mineru_" + "a" * 12).disabled
    assert any("README" in alerta.value for alerta in app.info)
    assert ambiente_mineru["leitores"] == ambiente_mineru["chamadas"] == []


def test_sem_paginas_selecionadas_nao_executa_mineru(ambiente_mineru):
    app = AppTest.from_string(SCRIPT).run()
    app.multiselect[0].set_value([]).run()
    assert not app.exception
    assert app.button(key="comparar_mineru_" + "a" * 12).disabled
    assert ambiente_mineru["chamadas"] == []


def test_erro_mineru_nao_grava_nem_altera_catalogo(monkeypatch, ambiente_mineru):
    estado = ambiente_mineru
    antes = estado["catalogo"].copy(deep=True)

    def falhar(catalogo, *args, **kwargs):
        catalogo.loc[:, "titulo"] = "Alteração incompleta"
        raise RuntimeError("Tempo limite na leitura de teste")

    monkeypatch.setattr(pagina.bib, "comparar_formulas_mineru", falhar)
    app = AppTest.from_string(SCRIPT).run()
    app.button(key="comparar_mineru_" + "a" * 12).click().run()
    assert not app.exception
    assert any("Tempo limite" in alerta.value for alerta in app.error)
    assert estado["gravacoes"] == 0
    pd.testing.assert_frame_equal(estado["catalogo"], antes)


def test_relatorio_sem_associacoes_aparece_mesmo_sem_formulas(ambiente_mineru):
    estado = ambiente_mineru
    estado["formulas"] = []
    estado["manifesto"]["formulas_mineru"] = {
        "associadas": 0, "ambiguas": 0, "sem_correspondencia": 1, "paginas": [2],
        "nao_associadas": [{"pagina": 2, "latex": r"E=mc^2"}],
    }
    app = AppTest.from_string(SCRIPT).run()
    assert not app.exception
    assert any(c.value == r"E=mc^2" for c in app.code)
    assert any("Nenhuma fórmula" in alerta.value for alerta in app.info)


def test_sem_formulas_docling_permite_comparar_qualquer_pagina_e_salvar_extras(ambiente_mineru):
    estado = ambiente_mineru
    estado["formulas"] = []
    app = AppTest.from_string(SCRIPT).run()
    assert not app.exception
    assert app.multiselect[0].value == [1]
    app.multiselect[0].set_value([2]).run()
    app.button(key="comparar_mineru_" + "a" * 12).click().run()
    assert not app.exception
    assert estado["chamadas"][0][3] == [2]
    assert estado["gravacoes"] == 1
    assert estado["manifesto"]["formulas_mineru"]["associadas"] == 0
    assert any(c.value == "z=9" for c in app.code)
    assert any("sem associação (1)" in e.label for e in app.expander)


def test_terceira_fonte_divergente_aparece_e_pode_ser_escolhida(monkeypatch, ambiente_mineru):
    estado = ambiente_mineru
    estado["formulas"][0]["latex_mineru"] = "x=999"
    escolhas = []

    def escolher(catalogo, artigo_id, pastas, formula_id, latex, fonte):
        escolhas.append((formula_id, latex, fonte))
        estado["formulas"][0].update(latex=latex, latex_fonte=fonte, latex_revisado=True)
        return catalogo

    monkeypatch.setattr(pagina.bib, "escolher_latex", escolher)
    app = AppTest.from_string(SCRIPT).run()
    assert not app.exception
    assert any("Leituras diferentes" in m.value for m in app.markdown)
    assert any("Docling × MinerU" in c.value and "Dolphin × MinerU" in c.value for c in app.caption)
    assert escolhas == []
    app.segmented_control(key="versao_" + "a" * 12 + "_f1").set_value("MinerU").run()
    app.button(key="salvar_formula_" + "a" * 12 + "_f1").click().run()
    assert not app.exception
    assert escolhas == [("f1", "x=999", "mineru")]
    assert any("Revisada por você" in m.value for m in app.markdown)
    assert any(c.value == "MinerU" for c in app.caption)


def test_filtro_de_divergencia_nao_esconde_formulas_quando_leituras_passam_a_concordar(ambiente_mineru):
    estado = ambiente_mineru
    estado["formulas"][0]["latex_mineru"] = "x=999"
    app = AppTest.from_string(SCRIPT).run()
    assert app.toggle[0].value is True
    estado["formulas"][0]["latex_mineru"] = "x=1"
    app.run()
    assert not app.exception
    assert app.toggle[0].disabled
    assert app.toggle[0].value is False
    assert any("Leituras concordam" in m.value for m in app.markdown)


@pytest.mark.parametrize("campos, selo", [
    ({"latex_dolphin": "", "latex_mineru": "x=1"}, "Leituras concordam"),
    ({"latex_dolphin": "", "latex_mineru": ""}, "Só uma leitura"),
    ({"latex": "x=7", "latex_fonte": "manual", "latex_mineru": "x=9"}, "Corrigida por você"),
])
def test_selos_consideram_fontes_disponiveis_e_revisao(ambiente_mineru, campos, selo):
    ambiente_mineru["formulas"] = [ambiente_mineru["formulas"][0]]
    ambiente_mineru["formulas"][0].update(campos)
    app = AppTest.from_string(SCRIPT).run()
    assert not app.exception
    assert any(selo in m.value for m in app.markdown)
