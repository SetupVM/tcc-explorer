"""Área 2: catálogo com filtros, indicadores, gráficos e exportação (Pandas)."""

import pandas as pd
import streamlit as st

from explorador import biblioteca as bib
from explorador import catalogo as cat
from explorador.extracao import carregar_manifesto, precisa_atualizar
from interface.comum import PASTAS, carregar_catalogo, obter_indice, opcoes_melhoria, salvar_catalogo

COLUNAS_TABELA = {
    "id": "Id",
    "titulo": "Título",
    "autores": "Autores",
    "ano": "Ano",
    "doi": "DOI",
    "tema": "Tema",
    "tema_origem": "Origem do tema",
    "palavras_chave": "Palavras-chave",
    "paginas": "Páginas",
    "status_extracao": "Extração",
    "qualidade_verificada": "Qualidade verificada",
    "status_indexacao": "Indexação",
    "n_trechos": "Trechos",
    "metadados_revisados": "Metadados revisados",
    "possivel_duplicata": "Possível duplicata",
    "arquivo_original": "Arquivo",
    "data_importacao": "Importado em",
}


def mostrar() -> None:
    st.header("2 · Biblioteca")
    catalogo = carregar_catalogo()
    if catalogo.empty:
        st.info("A biblioteca está vazia. Importe artigos na área 1.")
        return

    indicadores = cat.indicadores(catalogo)
    colunas = st.columns(6)
    colunas[0].metric("Artigos", indicadores["artigos"])
    colunas[1].metric("Páginas", indicadores["paginas"])
    colunas[2].metric("Indexados", indicadores["indexados"])
    colunas[3].metric("Trechos no índice", indicadores["trechos"])
    colunas[4].metric("Qualidade verificada", f"{indicadores['qualidade_verificada']}/{indicadores['artigos']}")
    colunas[5].metric("Metadados a revisar", indicadores["metadados_pendentes"])

    melhorar_todos(catalogo)
    filtrado = filtros(catalogo)
    filtrado = cat.marcar_possiveis_duplicatas(filtrado)

    duplicatas = filtrado[filtrado["possivel_duplicata"] != ""]
    if not duplicatas.empty:
        st.warning(
            f"{len(duplicatas)} arquivo(s) parecem ser o mesmo artigo (mesmo DOI ou título). "
            "Eles não foram mesclados: podem ser versões diferentes (ex.: preprint e publicado)."
        )

    st.markdown(f"**{len(filtrado)} de {len(catalogo)} artigo(s)**")
    exibicao = cat.para_exibicao(filtrado)[list(COLUNAS_TABELA)].rename(columns=COLUNAS_TABELA)
    st.dataframe(
        exibicao,
        hide_index=True,
        width="stretch",
        column_config={"Importado em": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")},
        alt="Catálogo de artigos filtrado",
    )
    st.download_button(
        "Exportar catálogo filtrado (CSV)",
        cat.exportar_csv(filtrado),
        file_name="catalogo_artigos.csv",
        mime="text/csv",
    )

    st.subheader("Visão geral")
    grafico_1, grafico_2 = st.columns(2)
    with grafico_1:
        st.markdown("**Artigos por tema**")
        st.bar_chart(cat.contar_por(filtrado, "tema"), x="tema", y="artigos", horizontal=True)
    with grafico_2:
        st.markdown("**Artigos por ano**")
        st.bar_chart(cat.contar_por(filtrado, "ano"), x="ano", y="artigos")

    grafico_3, grafico_4 = st.columns(2)
    with grafico_3:
        st.markdown("**Situação da extração e da indexação**")
        situacao = pd.concat(
            [
                cat.contar_por(filtrado, "status_extracao").rename(columns={"status_extracao": "situação"}).assign(etapa="extração"),
                cat.contar_por(filtrado, "status_indexacao").rename(columns={"status_indexacao": "situação"}).assign(etapa="indexação"),
            ]
        )
        st.bar_chart(situacao, x="situação", y="artigos", color="etapa", stack=False)
    with grafico_4:
        st.markdown("**Trechos indexados por artigo**")
        trechos = filtrado.assign(artigo=filtrado["titulo"].fillna(filtrado["arquivo_original"]).str.slice(0, 40))
        st.bar_chart(trechos, x="artigo", y="n_trechos", horizontal=True)

    st.markdown("**Resumo por tema** (groupby do Pandas)")
    resumo = cat.resumo_por_tema(filtrado)
    for coluna in ["ano_mais_antigo", "ano_mais_recente"]:
        resumo[coluna] = resumo[coluna].astype("string").fillna(cat.NAO_INFORMADO)
    st.dataframe(resumo, hide_index=True, width="stretch", alt="Resumo da biblioteca por tema")


def melhorar_todos(catalogo: pd.DataFrame) -> None:
    """Aplica as melhorias (sem Docling) em lote e reindexa."""
    validos = catalogo[catalogo["status_extracao"].isin(["concluída", "parcial"])]
    antigos = [i for i in validos["id"] if precisa_atualizar(carregar_manifesto(PASTAS.do_artigo(i)))]
    rotulo = f"Melhorar todos os artigos ({len(antigos)} com extração antiga)" if antigos else "Melhorar todos os artigos"
    with st.expander(rotulo, icon=":material/auto_fix_high:", expanded=bool(antigos)):
        st.caption(
            "Une parágrafos entre páginas, recupera texto perdido, relê as fórmulas, descreve figuras "
            "(se ligado na barra lateral), infere título e tema e reindexa. Não roda o Docling."
        )
        substituir = st.checkbox(
            "Substituir temas já preenchidos pelo tema inferido",
            help="Desmarcado, só artigos sem tema (ou com tema inferido antes) recebem o tema inferido.",
        )
        if not st.button("Melhorar e reindexar", type="primary", disabled=validos.empty):
            return
        barra = st.progress(0.0)
        relatorios = []
        for numero, artigo_id in enumerate(validos["id"], start=1):
            barra.progress((numero - 1) / len(validos), text=f"{numero}/{len(validos)} · {artigo_id}")
            catalogo, relatorio = bib.melhorar_artigo(catalogo, artigo_id, PASTAS, opcoes_melhoria(substituir))
            if catalogo.loc[catalogo["id"] == artigo_id, "status_indexacao"].iloc[0] != "não indexado":
                catalogo, _, mensagem = bib.indexar_artigo(catalogo, artigo_id, PASTAS, obter_indice(), aceitar_parcial=True)
                relatorio.append(mensagem)
            salvar_catalogo(catalogo)
            relatorios.append({"artigo": artigo_id, "resultado": " · ".join(relatorio)})
        barra.progress(1.0, text="Concluído.")
        st.dataframe(pd.DataFrame(relatorios), hide_index=True, width="stretch", alt="Resultado das melhorias por artigo")


def filtros(catalogo: pd.DataFrame) -> pd.DataFrame:
    with st.expander("Filtros", expanded=True):
        coluna_1, coluna_2, coluna_3 = st.columns(3)
        temas = sorted(catalogo["tema"].fillna(cat.NAO_INFORMADO).unique())
        escolhidos = coluna_1.multiselect("Tema", temas, placeholder="Todos")

        anos = catalogo["ano"].dropna()
        ano_min = ano_max = None
        incluir_sem_ano = True
        if anos.nunique() > 1:
            ano_min, ano_max = coluna_2.slider("Ano", int(anos.min()), int(anos.max()), (int(anos.min()), int(anos.max())))
            incluir_sem_ano = coluna_2.checkbox("Incluir artigos sem ano", value=True)
        else:
            coluna_2.caption("Filtro de ano disponível quando houver artigos de anos diferentes.")

        extracao = coluna_3.multiselect("Extração", sorted(catalogo["status_extracao"].unique()), placeholder="Todas")
        indexacao = coluna_3.multiselect("Indexação", sorted(catalogo["status_indexacao"].unique()), placeholder="Todas")

    return cat.filtrar_catalogo(catalogo, escolhidos, ano_min, ano_max, incluir_sem_ano, extracao, indexacao)
