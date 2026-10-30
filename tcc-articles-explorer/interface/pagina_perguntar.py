"""Área 3: perguntas sobre os artigos (RAG) e sugestões de recortes de TCC."""

import hashlib
import json

import pandas as pd
import streamlit as st

from explorador import catalogo as cat
from explorador import config
from explorador.respostas import (
    CONSULTAS_TCC,
    REGRAS_BASE,
    TAREFA_PERGUNTA,
    TAREFA_TCC,
    ErroLLM,
    criar_cliente,
    montar_contexto,
    responder_pergunta,
    sugerir_tcc,
)
from interface.comum import (
    AVISO_PAGINAS,
    carregar_catalogo,
    escapar_md,
    mostrar_trecho,
    obter_indice,
    referencia_do_trecho,
    titulos_por_id,
)

EXEMPLOS = [
    "Quais métodos estes artigos utilizam?",
    "Quais limitações os autores relatam?",
    "Como os experimentos e métricas se diferenciam?",
    "Quais conjuntos de dados foram usados?",
]


def mostrar() -> None:
    st.header("3 · Perguntar")
    catalogo = carregar_catalogo()
    indexados = catalogo[catalogo["status_indexacao"] == "indexado"]
    if indexados.empty:
        st.info("Nenhum artigo indexado ainda. Importe e indexe artigos na área 1.")
        return
    if obter_indice().precisa_recriar():
        st.warning("O índice foi criado com outro modelo de embeddings. Recrie-o pela barra lateral antes de perguntar.")
        return

    rotulos = {linha["id"]: cat.rotulo_artigo(linha) for _, linha in indexados.iterrows()}
    selecionados = st.multiselect(
        "Artigos consultados", list(rotulos), format_func=rotulos.get,
        placeholder="Toda a biblioteca indexada",
    )
    quantos = len(selecionados) or len(indexados)

    with st.expander("Opções da busca"):
        quantidade = st.slider("Trechos enviados ao modelo", 4, 20, config.TRECHOS_POR_PERGUNTA)
        equilibrar = st.checkbox(
            "Buscar trechos de cada artigo (bom para comparações)", value=quantos > 1,
            help="Distribui os trechos entre os artigos, respeitando o limite acima. "
            "Se houver mais artigos que trechos permitidos, alguns artigos ficam de fora.",
        )
    ids_busca = selecionados or list(rotulos)

    sem_chave = not config.chave_llm_configurada()
    if sem_chave:
        st.info(
            "OPENAI_API_KEY não configurada: é possível buscar trechos, mas não gerar respostas. "
            "Veja o README para criar o arquivo .env."
        )

    aba_pergunta, aba_tcc = st.tabs(["Pergunta sobre os artigos", "Sugestões de recorte de TCC"])
    with aba_pergunta:
        st.pills("Exemplos", EXEMPLOS, key="exemplo", on_change=_usar_exemplo)
        pergunta = st.text_area("Sua pergunta", key="pergunta", placeholder="Ex.: Quais limitações os autores relatam?")
        coluna_1, coluna_2 = st.columns([1, 1])
        perguntar = coluna_1.button("Perguntar", type="primary", disabled=sem_chave or not pergunta.strip())
        so_buscar = coluna_2.button("Só buscar trechos (sem LLM)", disabled=not pergunta.strip())
        if perguntar or so_buscar:
            executar_pergunta(catalogo, pergunta.strip(), ids_busca, quantidade, equilibrar, usar_llm=perguntar)

    with aba_tcc:
        st.caption(
            "Sugestões geradas a partir dos trechos dos artigos importados. Elas não provam que a ideia é "
            "inédita nem que a lacuna existe: a biblioteca é pequena."
        )
        interesse = st.text_input("Seu interesse ou restrição (opcional)", placeholder="ex.: algo com dados públicos e pouca GPU")
        if st.button("Sugerir recortes de TCC", type="primary", disabled=sem_chave):
            executar_tcc(catalogo, interesse.strip(), ids_busca, quantidade, equilibrar)

    resultado = st.session_state.get("resultado_pergunta")
    if resultado:
        st.divider()
        st.caption("Resultado da última consulta. Alterações na biblioteca só aparecem ao fazer uma nova consulta.")
        if resultado["modo"] == "pergunta":
            mostrar_resposta(resultado["dados"], catalogo)
        elif resultado["modo"] == "tcc":
            mostrar_tcc(resultado["dados"], catalogo)
        else:
            mostrar_busca(resultado["dados"], resultado["pergunta"], catalogo)


def _usar_exemplo() -> None:
    if st.session_state.get("exemplo"):
        st.session_state["pergunta"] = st.session_state["exemplo"]


def _ids_indexados(catalogo: pd.DataFrame, selecionados: list[str] | None) -> list[str]:
    validos = catalogo.loc[catalogo["status_indexacao"] == "indexado", "id"].tolist()
    return [artigo_id for artigo_id in validos if artigo_id in selecionados] if selecionados else validos


def _chave_cache(modo: str, consulta: str, trechos: list[dict], titulos: dict[str, str]) -> str:
    """IDs posicionais não bastam: uma nova extração pode mudar o mesmo trecho."""
    contexto, _ = montar_contexto(trechos, titulos)
    dados = {
        "modo": modo,
        "consulta": consulta,
        "contexto": contexto,
        "trechos": trechos,
        "regras": REGRAS_BASE,
        "tarefa": TAREFA_PERGUNTA if modo == "pergunta" else TAREFA_TCC,
        "modelo": config.OPENAI_MODELO,
        "temperatura": config.OPENAI_TEMPERATURA,
        "max_tokens": config.OPENAI_MAX_TOKENS,
        "base_url": config.OPENAI_BASE_URL,
    }
    serializado = json.dumps(dados, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def executar_pergunta(catalogo, pergunta, artigo_ids, quantidade, equilibrar, usar_llm) -> None:
    artigo_ids = _ids_indexados(catalogo, artigo_ids)
    indice = obter_indice()
    with st.spinner("Buscando trechos..."):
        trechos = indice.buscar(pergunta, artigo_ids, quantidade, equilibrar) if artigo_ids else []
    if not usar_llm:
        st.session_state["resultado_pergunta"] = {"modo": "busca", "dados": trechos, "pergunta": pergunta}
        return

    # Evita pagar duas vezes pela mesma pergunta com o mesmo contexto
    cache = st.session_state.setdefault("cache_llm", {})
    titulos = titulos_por_id(catalogo)
    chave = _chave_cache("pergunta", pergunta, trechos, titulos)
    if chave not in cache:
        try:
            with st.spinner(f"Consultando {config.OPENAI_MODELO}..."):
                cache[chave] = responder_pergunta(criar_cliente(), pergunta, trechos, titulos)
        except ErroLLM as erro:
            st.error(str(erro))
            return
    st.session_state["resultado_pergunta"] = {"modo": "pergunta", "dados": cache[chave]}


def executar_tcc(catalogo, interesse, artigo_ids, quantidade, equilibrar) -> None:
    artigo_ids = _ids_indexados(catalogo, artigo_ids)
    consultas = ([interesse] if interesse else []) + CONSULTAS_TCC
    with st.spinner("Buscando limitações, métodos e resultados nos artigos..."):
        trechos = obter_indice().buscar_varias(consultas, artigo_ids, quantidade, equilibrar) if artigo_ids else []
    cache = st.session_state.setdefault("cache_llm", {})
    titulos = titulos_por_id(catalogo)
    chave = _chave_cache("tcc", interesse, trechos, titulos)
    if chave not in cache:
        try:
            with st.spinner(f"Consultando {config.OPENAI_MODELO}..."):
                cache[chave] = sugerir_tcc(criar_cliente(), interesse, trechos, titulos)
        except ErroLLM as erro:
            st.error(str(erro))
            return
    st.session_state["resultado_pergunta"] = {"modo": "tcc", "dados": cache[chave]}


# ---------------------------------------------------------------- exibição


def _numerar_citados(ids_citados: list[str]) -> dict[str, int]:
    numeros: dict[str, int] = {}
    for trecho_id in ids_citados:
        numeros.setdefault(trecho_id, len(numeros) + 1)
    return numeros


def _referencias_curtas(ids: list[str], numeros: dict[str, int], trechos: dict[str, dict], titulos: dict) -> str:
    partes = []
    for trecho_id in ids:
        trecho = trechos[trecho_id]
        titulo = titulos.get(trecho["artigo_id"], "")[:45]
        partes.append(f"[{numeros[trecho_id]}] {titulo}, p. {trecho['paginas'].replace(',', ', ')}")
    return " · ".join(partes)


def mostrar_resposta(resultado, catalogo: pd.DataFrame) -> None:
    trechos = {t["id"]: t for t in resultado.trechos_recuperados}
    titulos = titulos_por_id(catalogo)
    numeros = _numerar_citados([i for a in resultado.afirmacoes for i in a.trechos])

    st.subheader("Resposta")
    st.caption(f"Pergunta: {resultado.pergunta}")
    if not resultado.evidencia_suficiente:
        st.warning(
            "A biblioteca não trouxe evidência suficiente para responder com segurança. "
            + (resultado.o_que_falta or "")
        )
    st.markdown(escapar_md(resultado.resposta))

    if resultado.afirmacoes:
        st.markdown("**Afirmações e evidências**")
        for afirmacao in resultado.afirmacoes:
            with st.container(border=True):
                if afirmacao.origem == "artigo":
                    st.markdown(f"📄 **Relatado nos artigos** — {escapar_md(afirmacao.texto)}")
                else:
                    st.markdown(f"💡 **Sugestão do assistente** — {escapar_md(afirmacao.texto)}")
                if afirmacao.trechos:
                    st.caption(_referencias_curtas(afirmacao.trechos, numeros, trechos, titulos))
                if afirmacao.sem_evidencia:
                    st.error("Nenhum trecho válido sustenta esta afirmação: desconsidere-a.")

    if resultado.o_que_falta and resultado.evidencia_suficiente:
        st.info(f"O que os artigos não responderam: {resultado.o_que_falta}")
    if resultado.citacoes_invalidas:
        st.warning(
            "O modelo citou trechos que não estavam no contexto enviado "
            f"({', '.join(resultado.citacoes_invalidas)}). Essas citações foram descartadas."
        )

    mostrar_evidencias(numeros, trechos, resultado.trechos_recuperados, catalogo)
    st.caption(f"Modelo: {resultado.modelo} · tokens: {resultado.tokens or '—'}")


def mostrar_tcc(resultado, catalogo: pd.DataFrame) -> None:
    trechos = {t["id"]: t for t in resultado.trechos_recuperados}
    numeros = _numerar_citados([i for p in resultado.propostas for i in p.trechos])

    st.subheader("Sugestões de recorte de TCC")
    st.info(
        "💡 São sugestões do assistente apoiadas nos artigos importados. Não afirmam que a ideia é inédita "
        "nem que a lacuna está comprovada: pesquise a literatura antes de decidir."
    )
    if not resultado.evidencia_suficiente:
        st.warning("Os trechos recuperados não sustentam bem uma proposta. " + (resultado.observacao or ""))
    elif resultado.observacao:
        st.caption(resultado.observacao)

    for numero, proposta in enumerate(resultado.propostas, start=1):
        with st.container(border=True):
            st.markdown(f"#### {numero}. {escapar_md(proposta.titulo_provisorio)}")
            st.markdown(f"**Pergunta de pesquisa:** {escapar_md(proposta.pergunta_pesquisa)}")
            st.markdown(f"**Motivação:** {escapar_md(proposta.motivacao)}")
            st.markdown(f"**Metodologia possível:** {escapar_md(proposta.metodologia)}")
            st.markdown("**Recursos e dados necessários:**\n" + "\n".join(f"- {escapar_md(r)}" for r in proposta.recursos_e_dados))
            st.markdown("**Artigos que sustentam a proposta:**")
            artigos = {}
            for trecho_id in proposta.trechos:
                trecho = trechos[trecho_id]
                artigos.setdefault(trecho["artigo_id"], []).append(f"[{numeros[trecho_id]}] p. {trecho['paginas']}")
            for artigo_id, citacoes in artigos.items():
                linha = catalogo[catalogo["id"] == artigo_id]
                referencia = cat.formatar_referencia(linha.iloc[0]) if not linha.empty else artigo_id
                st.markdown(f"- {escapar_md(referencia)} — trechos {', '.join(citacoes)}")
            st.markdown("**Dúvidas que ainda precisam ser investigadas:**\n" + "\n".join(f"- {escapar_md(d)}" for d in proposta.duvidas_em_aberto))

    if resultado.citacoes_invalidas:
        st.warning(f"Citações descartadas por não existirem no contexto: {', '.join(resultado.citacoes_invalidas)}.")
    mostrar_evidencias(numeros, trechos, resultado.trechos_recuperados, catalogo)
    st.caption(f"Modelo: {resultado.modelo} · tokens: {resultado.tokens or '—'}")


def mostrar_evidencias(numeros: dict[str, int], trechos: dict, recuperados: list[dict], catalogo) -> None:
    if numeros:
        st.markdown("**Trechos citados** — clique para abrir")
        st.caption(AVISO_PAGINAS)
        for trecho_id, numero in numeros.items():
            mostrar_trecho(trechos[trecho_id], catalogo, numero)
    with st.expander(f"Todos os {len(recuperados)} trechos recuperados (contexto enviado ao modelo)"):
        for trecho in recuperados:
            st.caption(f"distância {trecho['distancia']} · {referencia_do_trecho(trecho, catalogo)}")
            st.markdown(escapar_md(trecho["texto"][:600]))
            st.divider()


def mostrar_busca(trechos: list[dict], pergunta: str, catalogo) -> None:
    st.subheader("Trechos mais próximos da pergunta")
    st.caption(f"Pergunta: {pergunta} · busca semântica sem LLM (menor distância = mais parecido). {AVISO_PAGINAS}")
    if not trechos:
        st.info("Nenhum trecho encontrado.")
    for numero, trecho in enumerate(trechos, start=1):
        mostrar_trecho(trecho, catalogo, numero, aberto=numero == 1)
