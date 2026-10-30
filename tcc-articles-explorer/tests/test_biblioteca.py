"""Fluxo importar -> indexar sem o Docling: a extração é simulada gravando
manifesto.json e elementos.json como o módulo de extração faria."""

import json

import pandas as pd

from explorador import biblioteca as bib
from explorador.catalogo import atualizar_artigo
from tests.conftest import elemento, gerar_pdf_em_branco


def _simular_extracao(pastas, artigo_id, status="concluída", elementos=None, alertas=None):
    pasta = pastas.do_artigo(artigo_id)
    pasta.mkdir(parents=True, exist_ok=True)
    elementos = elementos if elementos is not None else [
        elemento("e0", "secao", "1 Introduction"),
        elemento("e1", "texto", "Students ask many questions about long PDFs. " * 10, [1]),
        elemento("e2", "texto", "We propose a hybrid retriever for course material. " * 10, [2]),
    ]
    caracteres = sum(len(e["texto"]) for e in elementos)
    manifesto = {"status": status, "contagens": {"caracteres": caracteres}, "alertas": alertas or [], "assinatura": "x"}
    (pasta / "manifesto.json").write_text(json.dumps(manifesto))
    (pasta / "elementos.json").write_text(json.dumps(elementos))


def _importar(catalogo, pastas, marca="a"):
    catalogo, resultado = bib.importar_pdf(catalogo, gerar_pdf_em_branco(2, marca=marca), f"{marca}.pdf", pastas)
    return catalogo, resultado.artigo_id


def test_fluxo_completo_indexa_e_atualiza_catalogo(catalogo, pastas, indice):
    catalogo, artigo_id = _importar(catalogo, pastas)
    _simular_extracao(pastas, artigo_id)

    catalogo, ok, mensagem = bib.indexar_artigo(catalogo, artigo_id, pastas, indice)
    linha = catalogo.iloc[0]
    assert ok, mensagem
    assert linha["status_indexacao"] == "indexado"
    assert linha["n_trechos"] == indice.contar(artigo_id) > 0
    assert linha["modelo_indexacao"] == indice.assinatura


def test_extracao_que_falhou_nunca_e_indexada(catalogo, pastas, indice):
    catalogo, artigo_id = _importar(catalogo, pastas)
    _simular_extracao(pastas, artigo_id, status="falhou", elementos=[])
    catalogo, ok, mensagem = bib.indexar_artigo(catalogo, artigo_id, pastas, indice, aceitar_parcial=True)
    assert not ok and "falhou" in mensagem
    assert indice.contar(artigo_id) == 0


def test_extracao_parcial_exige_confirmacao(catalogo, pastas, indice):
    catalogo, artigo_id = _importar(catalogo, pastas)
    _simular_extracao(pastas, artigo_id, status="parcial")

    catalogo, ok, mensagem = bib.indexar_artigo(catalogo, artigo_id, pastas, indice)
    assert not ok and "confirme" in mensagem
    assert indice.contar(artigo_id) == 0

    catalogo, ok, _ = bib.indexar_artigo(catalogo, artigo_id, pastas, indice, aceitar_parcial=True)
    assert ok and indice.contar(artigo_id) > 0


def test_extracao_refeita_e_ruim_remove_trechos_antigos(catalogo, pastas, indice):
    catalogo, artigo_id = _importar(catalogo, pastas)
    _simular_extracao(pastas, artigo_id)
    catalogo, ok, _ = bib.indexar_artigo(catalogo, artigo_id, pastas, indice)
    assert ok

    _simular_extracao(pastas, artigo_id, status="falhou", elementos=[])
    catalogo, ok, _ = bib.indexar_artigo(catalogo, artigo_id, pastas, indice)
    assert not ok
    assert indice.contar(artigo_id) == 0
    assert catalogo.iloc[0]["status_indexacao"] == "não indexado"


def test_remover_artigo_apaga_indice_arquivos_e_linha(catalogo, pastas, indice):
    catalogo, artigo_id = _importar(catalogo, pastas)
    _simular_extracao(pastas, artigo_id)
    catalogo, _, _ = bib.indexar_artigo(catalogo, artigo_id, pastas, indice)

    catalogo = bib.remover_artigo(catalogo, artigo_id, pastas, indice)
    assert catalogo.empty
    assert indice.contar() == 0
    assert not pastas.do_artigo(artigo_id).exists()
    assert not list(pastas.pdfs.glob("*.pdf"))


def test_sincronizar_marca_reindexacao_quando_o_indice_muda(catalogo, pastas, indice):
    catalogo, artigo_id = _importar(catalogo, pastas)
    _simular_extracao(pastas, artigo_id)
    catalogo, _, _ = bib.indexar_artigo(catalogo, artigo_id, pastas, indice)

    catalogo = atualizar_artigo(catalogo, artigo_id, {"modelo_indexacao": "outro-modelo|trechos-v1"})
    catalogo = bib.sincronizar_indexacao(catalogo, indice)
    assert catalogo.iloc[0]["status_indexacao"] == "reindexação necessária"

    catalogo, mensagens = bib.reindexar_todos(catalogo, pastas, indice)
    assert mensagens[0][1] is True
    assert catalogo.iloc[0]["status_indexacao"] == "indexado"
    assert indice.contar(artigo_id) == catalogo.iloc[0]["n_trechos"]


def test_sem_trechos_indexaveis_limpa_indice_e_catalogo(catalogo, pastas, indice):
    catalogo, artigo_id = _importar(catalogo, pastas)
    _simular_extracao(pastas, artigo_id)
    catalogo, _, _ = bib.indexar_artigo(catalogo, artigo_id, pastas, indice)
    _simular_extracao(pastas, artigo_id, elementos=[elemento("e0", "marca_dagua", "carimbo " * 80)])

    catalogo, ok, _ = bib.indexar_artigo(catalogo, artigo_id, pastas, indice)
    assert not ok
    assert indice.contar(artigo_id) == 0
    assert catalogo.iloc[0]["status_indexacao"] == "não indexado"
    assert catalogo.iloc[0]["n_trechos"] == 0
    assert pd.isna(catalogo.iloc[0]["modelo_indexacao"])


def test_melhorar_exige_nova_revisao_de_qualidade(catalogo, pastas):
    catalogo, artigo_id = _importar(catalogo, pastas)
    _simular_extracao(pastas, artigo_id)
    catalogo = atualizar_artigo(catalogo, artigo_id, {"qualidade_verificada": True})
    catalogo, _ = bib.melhorar_artigo(
        catalogo, artigo_id, pastas,
        bib.OpcoesMelhoria(atualizar_estrutura=False, inferir_metadados=False),
    )
    assert not catalogo.iloc[0]["qualidade_verificada"]


def test_corrigir_formula_exige_nova_revisao_e_reindexacao(catalogo, pastas):
    catalogo, artigo_id = _importar(catalogo, pastas)
    _simular_extracao(pastas, artigo_id, elementos=[elemento("e0", "formula", "y=f", latex="y=f")])
    catalogo = atualizar_artigo(catalogo, artigo_id, {
        "qualidade_verificada": True, "status_indexacao": "indexado",
    })
    catalogo = bib.escolher_latex(catalogo, artigo_id, pastas, "e0", "y=f(3)", "manual")
    assert not catalogo.iloc[0]["qualidade_verificada"]
    assert catalogo.iloc[0]["status_indexacao"] == "reindexação necessária"
    assert bib.carregar_elementos(pastas.do_artigo(artigo_id))[0]["latex"] == "y=f(3)"
