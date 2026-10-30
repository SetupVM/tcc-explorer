"""Explorador de Artigos — interface Streamlit.

    streamlit run app.py
"""

import streamlit as st

from explorador import biblioteca as bib
from explorador import config
from interface import pagina_biblioteca, pagina_importar, pagina_perguntar
from interface.comum import AVISO_PAGINAS, PASTAS, carregar_catalogo, obter_indice, salvar_catalogo, situacao_visao

st.set_page_config(page_title="Explorador de Artigos", page_icon="📚", layout="wide")
config.criar_pastas()

AREAS = {
    "1 · Importar e revisar": pagina_importar.mostrar,
    "2 · Biblioteca": pagina_biblioteca.mostrar,
    "3 · Perguntar": pagina_perguntar.mostrar,
}
ROTULOS_OCR = {
    "auto": "Automático (só onde não há texto)",
    "pagina_inteira": "Página inteira (PDF digitalizado)",
    "desligado": "Desligado",
}


def barra_lateral() -> str:
    with st.sidebar:
        st.title("📚 Explorador de Artigos")
        st.caption("Leitura de artigos de computação e IA e ideias de recorte de TCC.")
        area = st.radio("Área", list(AREAS), label_visibility="collapsed")

        with st.expander("Opções de extração (Docling)"):
            st.radio(
                "OCR", list(ROTULOS_OCR), format_func=ROTULOS_OCR.get, key="opcao_ocr",
                index=list(ROTULOS_OCR).index(config.EXTRACAO_OCR) if config.EXTRACAO_OCR in ROTULOS_OCR else 0,
            )
            st.checkbox("Fórmulas em LaTeX (mais lento)", value=config.EXTRACAO_FORMULAS, key="opcao_formulas")
            st.checkbox("Tabelas em modo preciso", value=config.EXTRACAO_TABELAS_PRECISAS, key="opcao_tabelas")
            st.caption("Valem para novas importações e para o botão Reprocessar.")

        with st.expander("Melhorias depois do Docling"):
            st.checkbox(
                "Segunda leitura das fórmulas (Dolphin-1.5)", value=config.FORMULAS_SEGUNDA_LEITURA, key="opcao_dolphin",
                help="Modelo local de 0,4B. Compara com a leitura do Docling e aponta divergências.",
            )
            visao_ok, visao_motivo = situacao_visao()
            st.checkbox(
                f"Descrever figuras ({config.VISAO_MODELO})", value=config.DESCREVER_FIGURAS and visao_ok,
                key="opcao_figuras", disabled=not visao_ok,
                help="Modelo de visão local via Ollama; a descrição entra na busca marcada como automática.",
            )
            if not visao_ok:
                st.caption(visao_motivo)
            st.checkbox("Inferir título e tema do artigo", value=config.INFERIR_METADADOS, key="opcao_metadados")
            st.caption("Aplicadas na importação e pelos botões Melhorar, sem rodar o Docling de novo.")

        st.divider()
        if config.chave_llm_configurada():
            servidor = f" · {config.OPENAI_BASE_URL}" if config.OPENAI_BASE_URL else ""
            st.success(f"LLM: {config.OPENAI_MODELO}{servidor}", icon=":material/check_circle:")
        else:
            st.warning(
                "Sem OPENAI_API_KEY: catálogo, inspeção e busca funcionam; respostas não. "
                "O tema é inferido localmente por similaridade.",
                icon=":material/warning:",
            )
        st.caption(f"Embeddings locais: {config.EMBEDDING_MODELO}")
        st.caption(AVISO_PAGINAS)
        manutencao_do_indice()
    return area


def manutencao_do_indice() -> None:
    """Mantém o catálogo coerente com o índice e oferece recriar o índice se o modelo mudou."""
    indice = obter_indice()
    catalogo = carregar_catalogo()
    sincronizado = bib.sincronizar_indexacao(catalogo, indice)
    if not sincronizado.equals(catalogo):
        salvar_catalogo(sincronizado)

    if indice.precisa_recriar():
        st.error(
            f"O índice foi criado com outro modelo ({indice.assinatura_gravada() or 'desconhecido'}). "
            f"Para usar {config.EMBEDDING_MODELO}, recrie o índice."
        )
        if st.button("Recriar índice e reindexar"):
            indice.recriar()
            with st.spinner("Reindexando os artigos..."):
                catalogo, mensagens = bib.reindexar_todos(
                    bib.sincronizar_indexacao(carregar_catalogo(), indice), PASTAS, indice, config.TAMANHO_TRECHO
                )
            salvar_catalogo(catalogo)
            st.success(f"{sum(ok for _, ok, _ in mensagens)} artigo(s) reindexado(s).")
            st.rerun()


AREAS[barra_lateral()]()
