import pandas as pd

from explorador import catalogo as cat


def _catalogo_exemplo() -> pd.DataFrame:
    df = cat.catalogo_vazio()
    registros = [
        dict(sha="a" * 64, nome="rag.pdf", tema="RAG", titulo="Hybrid Retrieval for QA", ano="2023", doi="https://doi.org/10.1234/ABC.1"),
        dict(sha="b" * 64, nome="rag_v2.pdf", tema="rag", titulo="Hybrid retrieval for QA!", ano="2024", doi=None),
        dict(sha="c" * 64, nome="cnn.pdf", tema="Visão computacional", titulo="Leaf CNNs", ano="20xx", doi="doi:10.5555/xyz"),
        dict(sha="d" * 64, nome="sem_dados.pdf", tema=None, titulo=None, ano=None, doi=None),
    ]
    for r in registros:
        registro = cat.novo_registro(r["sha"], r["nome"], paginas=10, tema=r["tema"], titulo=r["titulo"], doi=r["doi"])
        registro["ano"] = r["ano"]
        df = cat.adicionar_artigo(df, registro)
    return df


def test_metadados_ausentes_ficam_vazios_e_aparecem_como_nao_informado():
    df = _catalogo_exemplo()
    sem_dados = df[df["arquivo_original"] == "sem_dados.pdf"].iloc[0]
    for coluna in ["titulo", "autores", "ano", "doi", "tema"]:
        assert pd.isna(sem_dados[coluna]), coluna

    exibicao = cat.para_exibicao(df)
    linha = exibicao[exibicao["arquivo_original"] == "sem_dados.pdf"].iloc[0]
    assert linha["autores"] == cat.NAO_INFORMADO
    assert linha["ano"] == cat.NAO_INFORMADO
    assert "Autores não informados" in cat.formatar_referencia(sem_dados)


def test_normalizacao_de_tipos_e_formatos():
    df = _catalogo_exemplo()
    assert str(df["ano"].dtype) == "Int64"
    linha_cnn = df[df["arquivo_original"] == "cnn.pdf"].iloc[0]
    assert pd.isna(linha_cnn["ano"])  # "20xx" não vira um ano inventado
    assert linha_cnn["doi"] == "10.5555/xyz"
    assert df.iloc[0]["doi"] == "10.1234/abc.1"
    # "RAG" e "rag" passam a ser o mesmo tema
    assert df["tema"].dropna().nunique() == 2


def test_doi_e_autores_invalidos_ou_bagunçados():
    assert cat.normalizar_doi("isto não é doi") is None
    assert cat.normalizar_autores("Ana Silva and Bruno Souza; Carla Lima") == "Ana Silva; Bruno Souza; Carla Lima"


def test_correcao_manual_de_metadados():
    df = _catalogo_exemplo()
    artigo_id = df.iloc[3]["id"]
    df = cat.atualizar_artigo(df, artigo_id, {"titulo": "  Título   corrigido ", "ano": "2021", "autores": "", "metadados_revisados": True})
    linha = df[df["id"] == artigo_id].iloc[0]
    assert linha["titulo"] == "Título corrigido"
    assert linha["ano"] == 2021
    assert pd.isna(linha["autores"])
    assert bool(linha["metadados_revisados"]) is True


def test_duplicatas_sao_sinalizadas_mas_nao_mescladas():
    df = cat.marcar_possiveis_duplicatas(_catalogo_exemplo())
    assert len(df) == 4  # nada foi removido nem mesclado
    sinalizados = df[df["possivel_duplicata"] != ""]
    assert set(sinalizados["arquivo_original"]) == {"rag.pdf", "rag_v2.pdf"}
    assert "título igual" in sinalizados.iloc[0]["possivel_duplicata"]


def test_filtros_por_tema_ano_e_status():
    df = _catalogo_exemplo()
    assert len(cat.filtrar_catalogo(df, temas=["RAG"])) == 2
    assert len(cat.filtrar_catalogo(df, temas=[cat.NAO_INFORMADO])) == 1
    so_2024 = cat.filtrar_catalogo(df, ano_min=2024, ano_max=2024, incluir_sem_ano=False)
    assert list(so_2024["arquivo_original"]) == ["rag_v2.pdf"]
    com_sem_ano = cat.filtrar_catalogo(df, ano_min=2024, ano_max=2024, incluir_sem_ano=True)
    assert len(com_sem_ano) == 3
    assert len(cat.filtrar_catalogo(df, status_extracao=["concluída"])) == 0


def test_agregacoes():
    df = _catalogo_exemplo()
    resumo = cat.resumo_por_tema(df).set_index("tema")
    assert resumo.loc["RAG", "artigos"] == 2
    assert resumo.loc["RAG", "paginas"] == 20
    assert resumo.loc[cat.NAO_INFORMADO, "artigos"] == 1
    contagem = cat.contar_por(df, "ano").set_index("ano")
    assert contagem.loc[cat.NAO_INFORMADO, "artigos"] == 2
    assert cat.indicadores(df)["artigos"] == 4


def test_salvar_e_carregar_preserva_tipos(tmp_path):
    df = _catalogo_exemplo()
    caminho = tmp_path / "catalogo.csv"
    cat.salvar_catalogo(df, caminho)
    lido = cat.carregar_catalogo(caminho)
    assert lido["id"].tolist() == df["id"].tolist()
    assert str(lido["ano"].dtype) == "Int64"
    assert pd.isna(lido.iloc[3]["titulo"])
    assert lido["qualidade_verificada"].dtype == bool
    assert cat.exportar_csv(lido).startswith("﻿".encode("utf-8"))
