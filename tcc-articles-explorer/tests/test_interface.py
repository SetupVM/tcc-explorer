"""Regressões da interface sem modelos, API, servidor ou banco de dados real."""

from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from explorador import catalogo as cat
from explorador import respostas
from interface import comum
from interface import pagina_importar as importar
from interface import pagina_perguntar as perguntar


@pytest.fixture
def catalogo_ui():
    catalogo = cat.catalogo_vazio()
    for chave, titulo, status in [
        ("a" * 64, "Artigo atual", "indexado"),
        ("b" * 64, "Versão obsoleta", "reindexação necessária"),
    ]:
        registro = cat.novo_registro(chave, f"{chave[0]}.pdf", 2, titulo=titulo)
        registro.update(status_extracao="concluída", status_indexacao=status)
        catalogo = cat.adicionar_artigo(catalogo, registro)
    return catalogo


class IndiceFalso:
    def __init__(self):
        self.consultas = []
        self.trechos = [
            {"id": f"{letra * 12}-0000", "artigo_id": letra * 12, "titulo": "Título antigo",
             "texto": f"Resultado de {letra}: x = 1", "secao": "Results", "paginas": "1"}
            for letra in ("a", "b")
        ]

    def precisa_recriar(self):
        return False

    def buscar(self, consulta, ids, quantidade, equilibrar):
        self.consultas.append(ids)
        return deepcopy([t for t in self.trechos if ids is None or t["artigo_id"] in ids])

    buscar_varias = buscar


@pytest.fixture
def ambiente_pergunta(monkeypatch):
    estado, chamadas = {}, []
    indice = IndiceFalso()
    monkeypatch.setattr(perguntar, "st", SimpleNamespace(
        session_state=estado, spinner=lambda *a, **kw: nullcontext(), error=lambda mensagem: pytest.fail(mensagem),
    ))
    monkeypatch.setattr(perguntar, "obter_indice", lambda: indice)
    monkeypatch.setattr(perguntar, "criar_cliente", lambda: object())

    def responder(cliente, consulta, trechos, titulos):
        resultado = {"consulta": consulta, "trechos": deepcopy(trechos), "titulos": dict(titulos)}
        chamadas.append(resultado)
        return resultado

    monkeypatch.setattr(perguntar, "responder_pergunta", responder)
    monkeypatch.setattr(perguntar, "sugerir_tcc", responder)
    return SimpleNamespace(estado=estado, chamadas=chamadas, indice=indice)


def executar(modo, catalogo, selecionados=None):
    if modo == "pergunta":
        perguntar.executar_pergunta(catalogo, "Qual o resultado?", selecionados, 8, False, usar_llm=True)
    else:
        perguntar.executar_tcc(catalogo, "Qual o resultado?", selecionados, 8, False)


@pytest.mark.parametrize("modo", ["pergunta", "tcc"])
@pytest.mark.parametrize("alteracao", [
    "texto", "paginas", "titulo", "OPENAI_MODELO", "OPENAI_TEMPERATURA", "OPENAI_MAX_TOKENS", "OPENAI_BASE_URL",
])
def test_cache_reutiliza_contexto_igual_e_invalida_alteracoes(
    monkeypatch, catalogo_ui, ambiente_pergunta, modo, alteracao,
):
    ambiente = ambiente_pergunta
    executar(modo, catalogo_ui)
    executar(modo, catalogo_ui)
    assert len(ambiente.chamadas) == 1

    if alteracao in {"texto", "paginas"}:
        ambiente.indice.trechos[0][alteracao] = "Resultado corrigido: x = 2" if alteracao == "texto" else "2"
    elif alteracao == "titulo":
        catalogo_ui = cat.atualizar_artigo(catalogo_ui, "a" * 12, {"titulo": "Título revisado"})
    else:
        valores = {"OPENAI_MODELO": "modelo-alternativo", "OPENAI_TEMPERATURA": 0.73,
                   "OPENAI_MAX_TOKENS": 4321, "OPENAI_BASE_URL": "http://api-falsa.invalid/v1"}
        monkeypatch.setattr(perguntar.config, alteracao, valores[alteracao])

    executar(modo, catalogo_ui)
    assert len(ambiente.chamadas) == 2
    resultado = ambiente.estado["resultado_pergunta"]["dados"]
    assert resultado is ambiente.chamadas[-1]
    if alteracao in {"texto", "paginas"}:
        assert resultado["trechos"][0][alteracao] == ambiente.indice.trechos[0][alteracao]
    elif alteracao == "titulo":
        assert resultado["titulos"]["a" * 12] == "Título revisado"


@pytest.mark.parametrize("modo", ["pergunta", "tcc"])
@pytest.mark.parametrize("selecionados", [None, ["a" * 12, "b" * 12]])
def test_busca_exclui_artigos_que_precisam_reindexar(catalogo_ui, ambiente_pergunta, modo, selecionados):
    executar(modo, catalogo_ui, selecionados)
    assert ambiente_pergunta.indice.consultas == [["a" * 12]]
    assert [t["artigo_id"] for t in ambiente_pergunta.chamadas[0]["trechos"]] == ["a" * 12]


@pytest.mark.parametrize("modo", ["pergunta", "tcc"])
def test_selecao_so_de_artigo_obsoleto_nao_vira_busca_global(catalogo_ui, ambiente_pergunta, modo):
    executar(modo, catalogo_ui, ["b" * 12])
    assert ambiente_pergunta.indice.consultas == []
    assert ambiente_pergunta.chamadas[0]["trechos"] == []


def test_pagina_sem_selecao_e_sem_equilibrar_limita_busca(monkeypatch, catalogo_ui):
    indice = IndiceFalso()
    monkeypatch.setattr(perguntar, "carregar_catalogo", lambda: catalogo_ui.copy())
    monkeypatch.setattr(perguntar, "obter_indice", lambda: indice)
    monkeypatch.setattr(perguntar.config, "chave_llm_configurada", lambda: False)
    monkeypatch.setattr(perguntar, "mostrar_busca", lambda *args: None)
    app = AppTest.from_string("from interface.pagina_perguntar import mostrar\nmostrar()").run()
    assert not app.exception
    assert app.checkbox[0].value is False
    app.text_area[0].set_value("Qual o resultado?").run()
    next(b for b in app.button if b.label == "Só buscar trechos (sem LLM)").click().run()
    assert not app.exception
    assert indice.consultas == [["a" * 12]]


def test_tcc_respeita_o_limite_minimo_escolhido_no_slider(monkeypatch, catalogo_ui):
    limites = []
    monkeypatch.setattr(perguntar, "carregar_catalogo", lambda: catalogo_ui.copy())
    monkeypatch.setattr(perguntar, "obter_indice", lambda: IndiceFalso())
    monkeypatch.setattr(perguntar.config, "chave_llm_configurada", lambda: True)
    monkeypatch.setattr(perguntar, "executar_tcc", lambda catalogo, interesse, ids, quantidade, equilibrar: limites.append(quantidade))
    app = AppTest.from_string("from interface.pagina_perguntar import mostrar\nmostrar()").run()
    app.slider[0].set_value(4).run()
    next(b for b in app.button if b.label == "Sugerir recortes de TCC").click().run()
    assert not app.exception
    assert limites == [4]


@pytest.fixture
def catalogo_em_memoria(monkeypatch, catalogo_ui):
    estado = {"catalogo": catalogo_ui.copy(), "gravacoes": 0}

    def salvar(catalogo):
        estado["catalogo"] = catalogo.copy()
        estado["gravacoes"] += 1

    monkeypatch.setattr(importar, "carregar_catalogo", lambda: estado["catalogo"].copy())
    monkeypatch.setattr(importar, "salvar_catalogo", salvar)
    return estado


def test_qualidade_persiste_so_acao_do_usuario_e_reflete_invalidacao(monkeypatch, catalogo_em_memoria):
    estado = catalogo_em_memoria
    monkeypatch.setattr(importar, "acoes", lambda *args: None)
    monkeypatch.setattr(importar, "precisa_atualizar", lambda manifesto: False)
    monkeypatch.setattr(importar, "config_extracao_atual", lambda: SimpleNamespace(assinatura=lambda: "mesma"))
    script = '''
from interface import pagina_importar as p
catalogo = p.carregar_catalogo()
manifesto = {"config": {"versao_extrator": "fake", "ocr": "auto", "formulas": True,
"tabelas_precisas": True}, "duracao_s": 0, "fim": "mesmo instante", "assinatura": "mesma",
"alertas": [], "erros": []}
p.painel_situacao(catalogo, catalogo.iloc[0], manifesto)
'''
    app = AppTest.from_string(script).run()
    assert not app.exception
    app.checkbox[0].check().run()
    assert bool(estado["catalogo"].iloc[0]["qualidade_verificada"])
    assert estado["gravacoes"] == 1

    # Extração, correção de fórmula ou melhoria pode invalidar a revisão sem mudar o manifesto.
    estado["catalogo"] = cat.atualizar_artigo(estado["catalogo"], "a" * 12, {"qualidade_verificada": False})
    app.run()
    assert not app.exception
    assert app.checkbox[0].value is False
    assert not bool(estado["catalogo"].iloc[0]["qualidade_verificada"])
    assert estado["gravacoes"] == 1

    # Mesmo com catálogo já False, um estado antigo de sessão não pode confirmar a revisão.
    app.session_state["qualidade_" + "a" * 12] = True
    app.run()
    assert app.checkbox[0].value is False
    assert estado["gravacoes"] == 1
    app.checkbox[0].check().run()
    app.checkbox[0].uncheck().run()
    assert not app.exception
    assert not bool(estado["catalogo"].iloc[0]["qualidade_verificada"])
    assert estado["gravacoes"] == 3


def test_preencher_metadados_nao_pede_substituicao_de_tema(monkeypatch, catalogo_em_memoria):
    recebidas = []

    def opcoes(substituir_tema, forcar_metadados=False):
        recebidas.append((substituir_tema, forcar_metadados))
        return SimpleNamespace(substituir_tema=substituir_tema, inferir_metadados=forcar_metadados)

    monkeypatch.setattr(importar, "opcoes_melhoria", opcoes)
    monkeypatch.setattr(importar, "ler_metadados_pdf", lambda caminho: {})
    monkeypatch.setattr(importar.bib, "inferir_metadados", lambda catalogo, *args: (catalogo, "Concluído"))
    app = AppTest.from_string('''
from interface import pagina_importar as p
catalogo = p.carregar_catalogo()
p.formulario_metadados(catalogo, catalogo.iloc[0])
''').run()
    next(b for b in app.button if b.label == "Preencher a partir do artigo").click().run()
    assert not app.exception
    assert recebidas == [(False, True)]


@pytest.mark.parametrize("com_chave", [False, True])
def test_botao_preencher_habilita_recursos_com_inferencia_automatica_desligada(
    monkeypatch, catalogo_em_memoria, com_chave,
):
    cliente, embeddings = object(), object()
    recebidas, recursos = [], []

    def indice():
        recursos.append("embeddings")
        return SimpleNamespace(embeddings=embeddings)

    def criar_cliente():
        recursos.append("cliente")
        return cliente

    def inferir(catalogo, artigo_id, pastas, opcoes):
        recebidas.append(opcoes)
        return catalogo, "Concluído"

    monkeypatch.setattr(comum, "obter_indice", indice)
    monkeypatch.setattr(respostas, "criar_cliente", criar_cliente)
    monkeypatch.setattr(comum.config, "chave_llm_configurada", lambda: com_chave)
    monkeypatch.setattr(importar, "ler_metadados_pdf", lambda caminho: {})
    monkeypatch.setattr(importar.bib, "inferir_metadados", inferir)
    app = AppTest.from_string('''
import streamlit as st
from interface import comum, pagina_importar as p
st.session_state.setdefault("opcao_metadados", False)
st.session_state.setdefault("opcao_dolphin", False)
st.session_state.setdefault("opcao_figuras", False)
opcoes_automaticas = comum.opcoes_melhoria()
st.session_state["inferir_automaticamente"] = opcoes_automaticas.inferir_metadados
catalogo = p.carregar_catalogo()
p.formulario_metadados(catalogo, catalogo.iloc[0])
''').run()
    assert not app.exception
    assert app.session_state["inferir_automaticamente"] is False
    assert recursos == []
    next(b for b in app.button if b.label == "Preencher a partir do artigo").click().run()
    assert not app.exception
    assert len(recebidas) == 1
    opcoes = recebidas[0]
    assert opcoes.inferir_metadados is True
    assert opcoes.substituir_tema is False
    assert opcoes.embeddings is embeddings
    assert opcoes.cliente_llm is (cliente if com_chave else None)
    assert recursos == (["cliente", "embeddings"] if com_chave else ["embeddings"])


@pytest.mark.parametrize("indexar", [False, True])
def test_extracao_falha_tambem_remove_indice_anterior(monkeypatch, catalogo_em_memoria, indexar):
    chamadas = []
    monkeypatch.setattr(importar, "st", SimpleNamespace(spinner=lambda *a, **kw: nullcontext()))
    monkeypatch.setattr(importar, "config_extracao_atual", lambda: object())
    monkeypatch.setattr(importar, "obter_conversor", lambda config: object())
    monkeypatch.setattr(importar.bib, "extrair_artigo", lambda catalogo, *a, **kw: (catalogo, {"status": "falhou"}))

    def limpar(catalogo, artigo_id, aceitar_parcial):
        chamadas.append((artigo_id, aceitar_parcial))
        return cat.atualizar_artigo(catalogo, artigo_id, {"status_indexacao": "não indexado"}), "Índice removido"

    monkeypatch.setattr(importar, "indexar_agora", limpar)
    catalogo, resultado = importar.processar_artigo(catalogo_em_memoria["catalogo"], "a" * 12, indexar, forcar=True)
    assert chamadas == [("a" * 12, False)]
    assert catalogo.iloc[0]["status_indexacao"] == "não indexado"
    assert resultado["indexação"] == "Índice removido"
