"""Integração real: Docling + embeddings multilíngues + ChromaDB, sem LLM.

Usa PDFs sintéticos (artigos fictícios gerados com reportlab). É lento
(~1 min) e baixa modelos na primeira execução. Para pular:

    pytest -m "not docling"
"""

import pytest

from explorador import biblioteca as bib
from explorador import config
from explorador.catalogo import catalogo_vazio
from explorador.extracao import ConfigExtracao, carregar_elementos, extrair_pdf
from explorador.indice import EmbeddingsLocais, IndiceTrechos
from tests.pdfs_sinteticos import ARTIGO_RAG, ARTIGO_VISAO, gerar_artigo

pytestmark = [pytest.mark.docling, pytest.mark.embeddings]


@pytest.fixture(scope="module")
def ambiente(tmp_path_factory):
    """Importa, extrai e indexa os dois artigos sintéticos uma única vez."""
    raiz = tmp_path_factory.mktemp("integracao")
    pastas = bib.Pastas.em(raiz / "dados")
    indice = IndiceTrechos(raiz / "chroma", EmbeddingsLocais(config.EMBEDDING_MODELO))
    config_extracao = ConfigExtracao()
    catalogo = catalogo_vazio()
    ids, manifestos = {}, {}
    for nome, artigo in [("rag", ARTIGO_RAG), ("cnn", ARTIGO_VISAO)]:
        catalogo, resultado = bib.importar_pdf(catalogo, gerar_artigo(artigo), f"{nome}.pdf", pastas, tema="Teste")
        ids[nome] = resultado.artigo_id
        catalogo, manifestos[nome] = bib.extrair_artigo(catalogo, resultado.artigo_id, pastas, config_extracao)
        catalogo, ok, mensagem = bib.indexar_artigo(catalogo, resultado.artigo_id, pastas, indice)
        assert ok, mensagem
    return {"pastas": pastas, "indice": indice, "catalogo": catalogo, "ids": ids, "manifestos": manifestos, "config": config_extracao}


def test_extracao_concluida_com_paginas_fisicas(ambiente):
    manifesto = ambiente["manifestos"]["rag"]
    assert manifesto["status"] == "concluída"
    assert manifesto["paginas"] == 2
    assert manifesto["config"]["versao_extrator"]
    elementos = carregar_elementos(ambiente["pastas"].do_artigo(ambiente["ids"]["rag"]))
    assert {p for e in elementos for p in e["paginas"]} == {1, 2}
    referencias = [e for e in elementos if "Robertson" in e["texto"]]
    assert referencias and referencias[0]["paginas"] == [2]


def test_tabela_figura_e_formula_reconhecidas(ambiente):
    pasta = ambiente["pastas"].do_artigo(ambiente["ids"]["rag"])
    elementos = carregar_elementos(pasta)

    tabela = next(e for e in elementos if e["tipo"] == "tabela")
    assert tabela["colunas"][:2] == ["Retriever", "Recall@5"]
    assert ["Hybrid", "0.78", "0.47", "0.61"] in tabela["linhas"]
    assert "Table 1" in tabela["legenda"]

    figura = next(e for e in elementos if e["tipo"] == "figura")
    assert "Figure 1" in figura["legenda"]
    assert (pasta / figura["imagem"]).exists()

    formula = next(e for e in elementos if e["tipo"] == "formula")
    assert "bm" in formula["latex"].replace(" ", "")  # LaTeX reconhecido (não exato)


def test_formula_seguida_da_explicacao_na_ordem_de_leitura(ambiente):
    elementos = carregar_elementos(ambiente["pastas"].do_artigo(ambiente["ids"]["rag"]))
    posicao = next(i for i, e in enumerate(elementos) if e["tipo"] == "formula")
    assert elementos[posicao + 1]["texto"].startswith("where w is a weight")
    assert elementos[posicao]["secao"] == "3 Method"


def test_reaproveita_extracao_e_reprocessa_quando_config_muda(ambiente):
    pastas, artigo_id = ambiente["pastas"], ambiente["ids"]["cnn"]
    linha = ambiente["catalogo"][ambiente["catalogo"]["id"] == artigo_id].iloc[0]
    pdf = pastas.pdfs / f"{linha['sha256']}.pdf"

    mesma = extrair_pdf(pdf, pastas.do_artigo(artigo_id), ambiente["config"])
    assert mesma["reaproveitado"] is True

    outra = extrair_pdf(pdf, pastas.do_artigo(artigo_id), ConfigExtracao(formulas=False))
    assert outra["reaproveitado"] is False
    assert outra["assinatura"] != mesma["assinatura"]


@pytest.mark.parametrize(
    "pergunta, artigo, esperado",
    [
        ("Qual conjunto de dados os autores usaram?", "rag", "MauaQA"),
        ("Quais limitações os autores relatam?", "rag", "only covers questions written in English"),
        ("Qual retriever teve o melhor Recall@5?", "rag", "0.78"),
        ("Qual a latência do MobileNetV3?", "cnn", "38"),
    ],
)
def test_pergunta_em_portugues_recupera_trecho_em_ingles(ambiente, pergunta, artigo, esperado):
    trechos = ambiente["indice"].buscar(pergunta, quantidade=5)
    assert any(esperado in t["texto"] and t["artigo_id"] == ambiente["ids"][artigo] for t in trechos), [
        t["texto"][:80] for t in trechos
    ]


def test_busca_restrita_com_artigos_reais_extraidos(ambiente):
    so_cnn = ambiente["indice"].buscar("Qual conjunto de dados os autores usaram?", [ambiente["ids"]["cnn"]], 5)
    assert so_cnn and {t["artigo_id"] for t in so_cnn} == {ambiente["ids"]["cnn"]}


def test_segunda_leitura_real_das_formulas_com_dolphin(ambiente):
    from explorador.formulas import LeitorDolphin

    pastas, artigo_id = ambiente["pastas"], ambiente["ids"]["rag"]
    opcoes = bib.OpcoesMelhoria(leitor_formulas=LeitorDolphin(), inferir_metadados=False)
    catalogo, relatorio = bib.melhorar_artigo(ambiente["catalogo"], artigo_id, pastas, opcoes)

    formula = next(e for e in carregar_elementos(pastas.do_artigo(artigo_id)) if e["tipo"] == "formula")
    assert (pastas.do_artigo(artigo_id) / formula["imagem"]).exists()
    assert "bm25" in formula["latex_dolphin"].replace(" ", "")
    assert formula["numero"] == "1"
    assert any("relida" in parte for parte in relatorio)



def test_legendas_e_cabecalhos_tem_caixa_e_nenhum_texto_fica_sem_posicao(ambiente):
    from explorador.extracao import carregar_manifesto
    from explorador.pos_processamento import caixas_na_pagina, texto_fora_das_caixas

    pastas, artigo_id = ambiente["pastas"], ambiente["ids"]["rag"]
    elementos = carregar_elementos(pastas.do_artigo(artigo_id))
    manifesto = carregar_manifesto(pastas.do_artigo(artigo_id))
    for flutuante in (e for e in elementos if e["tipo"] in ("tabela", "figura")):
        assert flutuante["caixas_legenda"], flutuante["id"]  # "Table 1: ..." e "Figure 1: ..."
    assert any(c["texto"] == "1" for c in manifesto["mobilia"]["1"])  # número da página, fora do índice

    linha = ambiente["catalogo"][ambiente["catalogo"]["id"] == artigo_id].iloc[0]
    pdf = pastas.pdfs / f"{linha['sha256']}.pdf"
    for pagina in (1, 2):
        caixas = [c for e in elementos for c in caixas_na_pagina(e, pagina) + caixas_na_pagina(e, pagina, True)]
        fora, amostra = texto_fora_das_caixas(pdf, pagina, caixas + manifesto["mobilia"].get(str(pagina), []))
        assert fora < 0.02, amostra
