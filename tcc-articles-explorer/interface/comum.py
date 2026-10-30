"""Recursos compartilhados pelas páginas: cache, catálogo e componentes visuais."""

import re
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import ImageDraw, ImageFont

from explorador import catalogo as cat
from explorador import config
from explorador.armazenamento import caminho_do_pdf, renderizar_pagina
from explorador.biblioteca import OpcoesMelhoria, Pastas
from explorador.extracao import ConfigExtracao, criar_conversor
from explorador.pos_processamento import caixas_na_pagina

PASTAS = Pastas(config.PASTA_PDFS, config.PASTA_EXTRACOES, config.ARQUIVO_CATALOGO)

AVISO_PAGINAS = "Páginas = páginas físicas do arquivo PDF, contando a partir de 1 (não a numeração impressa)."

CORES_TIPO = {
    "titulo": "#7B2CBF",
    "secao": "#D62828",
    "texto": "#1D70B8",
    "lista": "#1D70B8",
    "tabela": "#2A9D8F",
    "figura": "#E9A23B",
    "formula": "#C2185B",
    "legenda": "#6C757D",
    "nota": "#6C757D",
    "referencia": "#6C757D",
    "codigo": "#495057",
    "texto_pdf": "#F08C00",
    "marca_dagua": "#ADB5BD",
}


# ---------------------------------------------------------------- recursos pesados (uma vez por sessão do servidor)


@st.cache_resource(show_spinner="Carregando o Docling (na primeira vez ele baixa os modelos)...")
def obter_conversor(config_extracao: ConfigExtracao):
    return criar_conversor(config_extracao)


@st.cache_resource(show_spinner="Abrindo o índice (ChromaDB)...")
def obter_indice():
    from explorador.indice import EmbeddingsLocais, IndiceTrechos

    return IndiceTrechos(config.PASTA_CHROMA, EmbeddingsLocais(config.EMBEDDING_MODELO))


@st.cache_resource(show_spinner="Carregando o Dolphin-1.5 (na primeira vez baixa ~0,8 GB)...")
def obter_leitor_formulas():
    from explorador.formulas import LeitorDolphin

    return LeitorDolphin(config.MODELO_FORMULAS)


@st.cache_resource(show_spinner=False, max_entries=1)
def obter_leitor_mineru():
    from explorador.mineru import LeitorMinerU

    return LeitorMinerU(config.MINERU_PYTHON, config.MINERU_TIMEOUT)


@st.cache_data(show_spinner=False, ttl=60)
def situacao_mineru() -> tuple[bool, str]:
    try:
        from explorador.mineru import verificar_instalacao

        return verificar_instalacao(config.MINERU_PYTHON)
    except Exception as erro:
        return False, f"MinerU indisponível: {erro}"


@st.cache_resource(show_spinner=False)
def obter_cliente_visao():
    from explorador.figuras import criar_cliente_visao

    return criar_cliente_visao(config.VISAO_URL, config.VISAO_API_KEY)


@st.cache_data(show_spinner=False, ttl=60)
def situacao_visao() -> tuple[bool, str]:
    """O modelo de visão (Ollama) está no ar? Reconsulta a cada minuto."""
    from explorador.figuras import modelo_disponivel

    return modelo_disponivel(obter_cliente_visao(), config.VISAO_MODELO)


@st.cache_data(show_spinner=False, max_entries=30)
def imagem_da_pagina(caminho_pdf: str, pagina: int):
    return renderizar_pagina(Path(caminho_pdf), pagina, escala=1.5)


# ---------------------------------------------------------------- catálogo


def carregar_catalogo() -> pd.DataFrame:
    return cat.carregar_catalogo(PASTAS.catalogo)


def salvar_catalogo(catalogo: pd.DataFrame) -> None:
    cat.salvar_catalogo(catalogo, PASTAS.catalogo)


def config_extracao_atual() -> ConfigExtracao:
    """Opções escolhidas na barra lateral (ou os padrões do .env)."""
    return ConfigExtracao(
        ocr=st.session_state.get("opcao_ocr", config.EXTRACAO_OCR),
        formulas=st.session_state.get("opcao_formulas", config.EXTRACAO_FORMULAS),
        tabelas_precisas=st.session_state.get("opcao_tabelas", config.EXTRACAO_TABELAS_PRECISAS),
    )


def opcoes_melhoria(substituir_tema: bool = False, forcar_metadados: bool = False) -> OpcoesMelhoria:
    """Etapas depois do Docling conforme a barra lateral e os recursos disponíveis."""
    from explorador.respostas import criar_cliente

    estado = st.session_state
    usar_figuras = estado.get("opcao_figuras", config.DESCREVER_FIGURAS) and situacao_visao()[0]
    inferir = forcar_metadados or estado.get("opcao_metadados", config.INFERIR_METADADOS)
    return OpcoesMelhoria(
        atualizar_estrutura=True,
        leitor_formulas=obter_leitor_formulas() if estado.get("opcao_dolphin", config.FORMULAS_SEGUNDA_LEITURA) else None,
        cliente_visao=obter_cliente_visao() if usar_figuras else None,
        modelo_visao=config.VISAO_MODELO,
        inferir_metadados=inferir,
        cliente_llm=criar_cliente() if inferir and config.chave_llm_configurada() else None,
        modelo_llm=config.OPENAI_MODELO,
        embeddings=obter_indice().embeddings if inferir else None,
        substituir_tema=substituir_tema,
    )


def titulos_por_id(catalogo: pd.DataFrame) -> dict[str, str]:
    return {
        linha["id"]: linha["titulo"] if pd.notna(linha["titulo"]) else linha["arquivo_original"]
        for _, linha in catalogo.iterrows()
    }


# ---------------------------------------------------------------- componentes


def escapar_md(texto: str) -> str:
    """Mostra texto do PDF literalmente (sem virar Markdown ou LaTeX do Streamlit)."""
    return re.sub(r"([\\`*_{}\[\]<>()#+\-.!|$~])", r"\\\1", texto)


def tabela_como_df(elemento: dict) -> pd.DataFrame:
    """DataFrame de uma tabela extraída, com nomes de coluna únicos."""
    nomes, vistos = [], {}
    for indice, nome in enumerate(elemento.get("colunas") or []):
        nome = str(nome).strip() or f"coluna {indice + 1}"
        vistos[nome] = vistos.get(nome, 0) + 1
        nomes.append(nome if vistos[nome] == 1 else f"{nome} ({vistos[nome]})")
    return pd.DataFrame(elemento.get("linhas") or [], columns=nomes or None)


COR_MOBILIA = "#ADB5BD"


def pagina_com_caixas(linha: pd.Series, pagina: int, elementos: list[dict], mobilia: list[dict] | None = None):
    """Imagem da página com as caixas de cada elemento, numeradas na ordem de leitura.

    Um elemento que continua de outra página ganha caixa em cada página; a
    legenda de tabela/figura usa o mesmo número; cabeçalho e rodapé (que não
    entram no índice) aparecem em cinza.
    """
    imagem = imagem_da_pagina(str(caminho_do_pdf(PASTAS.pdfs, linha["sha256"])), pagina).copy()
    desenho = ImageDraw.Draw(imagem)
    fonte = ImageFont.load_default(size=18)

    def retangulo(caixa: dict) -> list[float] | None:
        if not caixa.get("largura_pagina"):
            return None
        escala = imagem.width / caixa["largura_pagina"]
        return [caixa["x0"] * escala, caixa["y0"] * escala, caixa["x1"] * escala, caixa["y1"] * escala]

    def etiqueta(r: list[float], texto: str, cor: str) -> None:
        desenho.rectangle([r[0], r[1] - 22, r[0] + 12 + 10 * len(texto), r[1]], fill=cor)
        desenho.text((r[0] + 4, r[1] - 21), texto, fill="white", font=fonte)

    for caixa in mobilia or []:
        if (r := retangulo(caixa)):
            desenho.rectangle(r, outline=COR_MOBILIA, width=2)
    for ordem, elemento in enumerate(elementos, start=1):
        cor = CORES_TIPO.get(elemento["tipo"], "#000000")
        veio_de_antes = bool(elemento["paginas"]) and min(elemento["paginas"]) < pagina
        for parte, caixa in enumerate(caixas_na_pagina(elemento, pagina)):
            if (r := retangulo(caixa)):
                desenho.rectangle(r, outline=cor, width=3)
                etiqueta(r, f"{ordem}…" if parte > 0 or veio_de_antes else f"{ordem}", cor)
        for caixa in caixas_na_pagina(elemento, pagina, legenda=True):
            if (r := retangulo(caixa)):
                desenho.rectangle(r, outline=CORES_TIPO["legenda"], width=3)
                etiqueta(r, f"{ordem} leg.", CORES_TIPO["legenda"])
    return imagem


def referencia_do_trecho(trecho: dict, catalogo: pd.DataFrame) -> str:
    """Referência montada com os metadados do catálogo + páginas do trecho."""
    linhas = catalogo[catalogo["id"] == trecho["artigo_id"]]
    base = cat.formatar_referencia(linhas.iloc[0]) if not linhas.empty else trecho.get("titulo", "")
    paginas = trecho.get("paginas", "").replace(",", ", ")
    return f"{base} Página(s) {paginas} do PDF."


def mostrar_trecho(trecho: dict, catalogo: pd.DataFrame, numero: int | None = None, aberto: bool = False) -> None:
    titulo = titulos_por_id(catalogo).get(trecho["artigo_id"], trecho.get("titulo", ""))
    prefixo = f"[{numero}] " if numero else ""
    rotulo = f"{prefixo}{titulo[:70]} · p. {trecho.get('paginas', '?')} · {trecho.get('secao') or 'sem seção'}"
    with st.expander(rotulo, expanded=aberto):
        st.caption(f"{referencia_do_trecho(trecho, catalogo)} Tipo: {trecho.get('tipo')}. Id: `{trecho['id']}`")
        if trecho.get("imagem"):
            caminho = PASTAS.do_artigo(trecho["artigo_id"]) / trecho["imagem"]
            if caminho.exists():
                st.image(str(caminho), width=420)
        if trecho.get("tipo") == "tabela":
            st.code(trecho["texto"], language=None, wrap_lines=False)
        else:
            st.markdown(escapar_md(trecho["texto"]))
