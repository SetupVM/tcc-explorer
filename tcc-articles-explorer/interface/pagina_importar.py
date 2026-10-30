"""Área 1: importar PDFs, acompanhar o processamento e revisar cada artigo."""

import json

import pandas as pd
import streamlit as st

from explorador import biblioteca as bib
from explorador import catalogo as cat
from explorador import config
from explorador.armazenamento import caminho_do_pdf, ler_metadados_pdf
from explorador.extracao import (
    avaliar_para_indexacao,
    carregar_elementos,
    carregar_manifesto,
    formatar_paginas,
    precisa_atualizar,
)
from explorador.formulas import LIMITE_CONCORDANCIA, comparar_leituras, leituras_por_fonte, tem_divergencia
from explorador.pos_processamento import caixas_na_pagina, texto_fora_das_caixas
from interface.comum import (
    AVISO_PAGINAS,
    COR_MOBILIA,
    CORES_TIPO,
    PASTAS,
    carregar_catalogo,
    config_extracao_atual,
    escapar_md,
    obter_conversor,
    obter_indice,
    obter_leitor_mineru,
    opcoes_melhoria,
    pagina_com_caixas,
    salvar_catalogo,
    situacao_mineru,
    tabela_como_df,
)


def mostrar() -> None:
    st.header("1 · Importar e revisar")
    secao_importacao(carregar_catalogo())
    catalogo = carregar_catalogo()
    if catalogo.empty:
        st.info("Nenhum artigo importado ainda. Envie os PDFs que você escolheu acima.")
        return
    secao_revisao(catalogo)


# ---------------------------------------------------------------- importação


def secao_importacao(catalogo: pd.DataFrame) -> None:
    st.caption(
        f"Envie de 1 a {config.MAX_ARQUIVOS_POR_ENVIO} PDFs por vez (até {config.MAX_TAMANHO_MB} MB "
        f"e {config.MAX_PAGINAS} páginas cada). A extração e os embeddings rodam nesta máquina; "
        "só as respostas (e a inferência de tema, se houver chave) usam a API do LLM."
    )
    with st.form("form_importacao", clear_on_submit=True):
        arquivos = st.file_uploader(
            "Artigos em PDF",
            type=["pdf"],
            accept_multiple_files=True,
            max_upload_size=config.MAX_TAMANHO_MB,
        )
        tema = st.text_input(
            "Tema destes artigos (opcional)",
            placeholder="vazio = inferir do próprio artigo",
        )
        indexar = st.checkbox("Indexar para perguntas quando a extração terminar sem problemas", value=True)
        enviado = st.form_submit_button("Importar e processar", type="primary")

    if enviado:
        if not arquivos:
            st.warning("Escolha pelo menos um PDF.")
        elif len(arquivos) > config.MAX_ARQUIVOS_POR_ENVIO:
            st.error(f"Envie no máximo {config.MAX_ARQUIVOS_POR_ENVIO} arquivos por vez ({len(arquivos)} escolhidos).")
        else:
            processar_envio(catalogo, arquivos, tema.strip() or None, indexar)

    if st.session_state.get("ultimo_envio"):
        st.markdown("**Resultado do último envio**")
        st.dataframe(
            pd.DataFrame(st.session_state["ultimo_envio"]).fillna(""),
            hide_index=True,
            width="stretch",
            alt="Resultado de cada arquivo enviado",
        )

    pendentes = catalogo[catalogo["status_extracao"] == "pendente"]
    if not pendentes.empty:
        st.warning(f"{len(pendentes)} artigo(s) importado(s) ainda sem extração.")
        if st.button("Extrair pendentes"):
            for artigo_id in pendentes["id"]:
                catalogo, _ = processar_artigo(catalogo, artigo_id, indexar=True)
            st.rerun()


def processar_envio(catalogo: pd.DataFrame, arquivos, tema: str | None, indexar: bool) -> None:
    resultados = []
    barra = st.progress(0.0, text="Iniciando...")
    for numero, arquivo in enumerate(arquivos, start=1):
        barra.progress((numero - 1) / len(arquivos), text=f"{numero}/{len(arquivos)} · {arquivo.name}")
        catalogo, importacao = bib.importar_pdf(
            catalogo, arquivo.getvalue(), arquivo.name, PASTAS, tema, config.MAX_TAMANHO_MB, config.MAX_PAGINAS
        )
        linha = {"arquivo": arquivo.name, "importação": importacao.situacao, "detalhes": importacao.mensagem}
        if importacao.situacao == "importado":
            salvar_catalogo(catalogo)
            catalogo, linha = processar_artigo(catalogo, importacao.artigo_id, indexar, linha)
        resultados.append(linha)
    barra.progress(1.0, text="Concluído.")
    st.session_state["ultimo_envio"] = resultados


def processar_artigo(
    catalogo: pd.DataFrame,
    artigo_id: str,
    indexar: bool,
    linha: dict | None = None,
    forcar: bool = False,
    aceitar_parcial: bool = False,
) -> tuple[pd.DataFrame, dict]:
    """Extrai (ou reaproveita), aplica as melhorias e, se pedido, indexa."""
    linha = linha if linha is not None else {}
    config_extracao = config_extracao_atual()
    try:
        with st.spinner(f"Extraindo {artigo_id} com o Docling (pode levar alguns minutos)..."):
            catalogo, manifesto = bib.extrair_artigo(
                catalogo, artigo_id, PASTAS, config_extracao, obter_conversor(config_extracao), forcar=forcar
            )
        salvar_catalogo(catalogo)
        situacao = manifesto["status"] + (" (reaproveitada do disco)" if manifesto.get("reaproveitado") else "")
        linha["extração"] = situacao

        if manifesto["status"] == "falhou":
            # O backend bloqueia a indexação e remove trechos de uma versão anterior.
            catalogo, linha["indexação"] = indexar_agora(catalogo, artigo_id, aceitar_parcial=False)
        else:
            catalogo, linha["melhorias"] = melhorar(catalogo, artigo_id)
            if indexar:
                catalogo, linha["indexação"] = indexar_agora(catalogo, artigo_id, aceitar_parcial)
    except Exception as erro:  # ex.: sem internet para baixar modelos na 1ª vez
        linha["extração"] = f"erro: {erro}"
    return catalogo, linha


def melhorar(catalogo: pd.DataFrame, artigo_id: str, substituir_tema: bool = False) -> tuple[pd.DataFrame, str]:
    with st.spinner("Aplicando melhorias (parágrafos, fórmulas, figuras, título e tema)..."):
        catalogo, relatorio = bib.melhorar_artigo(catalogo, artigo_id, PASTAS, opcoes_melhoria(substituir_tema))
    salvar_catalogo(catalogo)
    return catalogo, " · ".join(relatorio)


def indexar_agora(catalogo: pd.DataFrame, artigo_id: str, aceitar_parcial: bool) -> tuple[pd.DataFrame, str]:
    with st.spinner("Gerando trechos e embeddings..."):
        catalogo, _, mensagem = bib.indexar_artigo(
            catalogo, artigo_id, PASTAS, obter_indice(), aceitar_parcial, config.TAMANHO_TRECHO
        )
    salvar_catalogo(catalogo)
    return catalogo, mensagem


# ---------------------------------------------------------------- revisão


def secao_revisao(catalogo: pd.DataFrame) -> None:
    st.divider()
    st.subheader("Revisar um artigo")
    rotulos = {linha["id"]: cat.rotulo_artigo(linha) for _, linha in catalogo.iterrows()}
    artigo_id = st.selectbox("Artigo", list(rotulos), format_func=rotulos.get, key="artigo_revisao")
    linha = catalogo[catalogo["id"] == artigo_id].iloc[0]
    pasta = PASTAS.do_artigo(artigo_id)
    manifesto = carregar_manifesto(pasta)

    aviso = st.session_state.pop("aviso_revisao", None)
    if aviso:
        getattr(st, aviso[0])(aviso[1])

    coluna_meta, coluna_status = st.columns([3, 2], gap="large")
    with coluna_meta:
        formulario_metadados(catalogo, linha)
    with coluna_status:
        painel_situacao(catalogo, linha, manifesto)

    elementos = carregar_elementos(pasta)
    if elementos:
        inspecao(catalogo, linha, manifesto, elementos)
    elif manifesto:
        st.error("A extração não produziu conteúdo. Veja os erros acima e tente reprocessar (ex.: OCR de página inteira).")


def formulario_metadados(catalogo: pd.DataFrame, linha: pd.Series) -> None:
    st.markdown("**Metadados**")

    def valor(coluna: str) -> str:
        return "" if pd.isna(linha[coluna]) else str(linha[coluna])

    with st.form(f"metadados_{linha['id']}"):
        titulo = st.text_input("Título", valor("titulo"), placeholder=cat.NAO_INFORMADO)
        autores = st.text_input("Autores (separados por ;)", valor("autores"), placeholder=cat.NAO_INFORMADO)
        coluna_ano, coluna_doi = st.columns([1, 3])
        ano = coluna_ano.text_input("Ano", valor("ano"), placeholder=cat.NAO_INFORMADO)
        doi = coluna_doi.text_input("DOI", valor("doi"), placeholder=cat.NAO_INFORMADO)
        tema = st.text_input("Tema", valor("tema"), placeholder=cat.NAO_INFORMADO)
        palavras = st.text_input("Palavras-chave (separadas por ;)", valor("palavras_chave"), placeholder=cat.NAO_INFORMADO)
        salvar = st.form_submit_button("Salvar metadados")

    if salvar:
        campos = {
            "titulo": titulo, "autores": autores, "ano": ano, "doi": doi, "tema": tema,
            "palavras_chave": palavras, "metadados_revisados": True,
        }
        digitados = {"titulo": titulo, "autores": autores, "ano": ano, "doi": doi, "tema": tema}
        for campo, novo in digitados.items():
            if novo.strip() != valor(campo):
                campos[f"{campo}_origem"] = "usuário"  # inferências futuras não mexem mais
        catalogo = cat.atualizar_artigo(catalogo, linha["id"], campos)
        salvo = catalogo[catalogo["id"] == linha["id"]].iloc[0]
        salvar_catalogo(catalogo)
        st.success("Metadados salvos.")
        if ano.strip() and pd.isna(salvo["ano"]):
            st.warning("Ano inválido: ficou como “Não informado”.")
        if doi.strip() and pd.isna(salvo["doi"]):
            st.warning("DOI fora do formato 10.xxxx/...: ficou como “Não informado”.")

    origens = [
        f"**{nome}**: {valor(f'{campo}_origem') or '—'}"
        for campo, nome in [("titulo", "título"), ("autores", "autores"), ("ano", "ano"), ("doi", "DOI"), ("tema", "tema")]
    ]
    st.caption(
        "Origem de cada campo · " + " · ".join(origens) + ". "
        + ("✅ Revisados por você. " if linha["metadados_revisados"] else "Ainda não revisados. ")
        + "Tudo é tirado do próprio PDF: autores e ano do LLM só ficam se aparecerem no texto; "
        "ano e DOI também vêm do carimbo do arXiv ou do DOI impresso. Campos vazios = “Não informado”."
    )
    if st.button("Preencher a partir do artigo", icon=":material/auto_awesome:", key=f"sugerir_{linha['id']}",
                 help="Título, autores, ano, DOI, tema e palavras-chave. Não apaga o que você digitou."):
        with st.spinner("Lendo o início do artigo..."):
            opcoes = opcoes_melhoria(substituir_tema=False, forcar_metadados=True)
            catalogo, mensagem = bib.inferir_metadados(catalogo, linha["id"], PASTAS, opcoes)
        salvar_catalogo(catalogo)
        st.session_state["aviso_revisao"] = ("info", mensagem)
        st.rerun()
    try:
        gravados = ler_metadados_pdf(caminho_do_pdf(PASTAS.pdfs, linha["sha256"]))
    except Exception:
        gravados = {}
    if gravados:
        texto = "; ".join(f"{chave}: {valor}" for chave, valor in gravados.items())
        st.caption(f"Gravado nas propriedades do arquivo PDF (pode estar errado): {texto}")


def _salvar_qualidade(artigo_id: str, chave: str) -> None:
    catalogo = carregar_catalogo()
    salvar_catalogo(cat.atualizar_artigo(catalogo, artigo_id, {"qualidade_verificada": st.session_state[chave]}))


def painel_situacao(catalogo: pd.DataFrame, linha: pd.Series, manifesto: dict | None) -> None:
    st.markdown("**Situação**")
    coluna_1, coluna_2 = st.columns(2)
    coluna_1.metric("Extração", linha["status_extracao"])
    coluna_2.metric("Indexação", linha["status_indexacao"])
    st.caption(
        f"{linha['paginas']} página(s) · {linha['n_trechos'] or 0} trecho(s) no índice · "
        f"arquivo original: {linha['arquivo_original']}"
    )

    if manifesto:
        usada = manifesto["config"]
        st.caption(
            f"Docling {usada['versao_extrator']} · OCR: {usada['ocr']} · fórmulas LaTeX: "
            f"{'sim' if usada['formulas'] else 'não'} · tabelas: {'precisas' if usada['tabelas_precisas'] else 'rápidas'} "
            f"· {manifesto['duracao_s']} s em {manifesto['fim']}"
        )
        cobertura = (manifesto.get("pos_processamento") or {}).get("cobertura") or {}
        if cobertura.get("total") is not None:
            st.caption(
                f"Cobertura do texto do PDF: {cobertura['total']:.1%} das palavras apareceram na extração."
            )
        if precisa_atualizar(manifesto):
            st.info("Extração feita antes das melhorias atuais. Use **Melhorar** (não roda o Docling).")
        if manifesto["assinatura"] != config_extracao_atual().assinatura():
            st.info("As opções do Docling na barra lateral diferem das usadas aqui. Reprocesse para aplicá-las.")
        for alerta in manifesto["alertas"]:
            st.warning(alerta)
        if manifesto["erros"]:
            with st.expander("Erros registrados pelo extrator"):
                st.code("\n".join(manifesto["erros"]), language=None)

    chave_qualidade = f"qualidade_{linha['id']}"
    # A extração/correção pode invalidar a revisão mantendo a mesma chave do widget.
    # Só uma ação explícita no checkbox persiste o valor; reruns leem o catálogo.
    st.session_state[chave_qualidade] = bool(linha["qualidade_verificada"])
    st.checkbox(
        "Qualidade verificada",
        help="Marque depois de conferir texto, tabelas, fórmulas e figuras na inspeção abaixo.",
        key=chave_qualidade,
        disabled=manifesto is None,
        on_change=_salvar_qualidade,
        args=(linha["id"], chave_qualidade),
    )
    st.caption("Extração concluída não é o mesmo que qualidade verificada: símbolos, tabelas e fórmulas podem sair errados sem erro.")

    acoes(catalogo, linha, manifesto)


def acoes(catalogo: pd.DataFrame, linha: pd.Series, manifesto: dict | None) -> None:
    artigo_id = linha["id"]
    decisao, motivo = avaliar_para_indexacao(manifesto)
    aceitar = False
    if decisao == "confirmar":
        st.warning(f"Indexação depende de confirmação: {motivo}")
        aceitar = st.checkbox("Revisei a extração e quero indexar mesmo assim", key=f"aceitar_{artigo_id}")
    elif decisao == "bloqueado" and manifesto:
        st.error(f"Não pode ser indexado: {motivo}")
    bloqueado = decisao == "bloqueado" or (decisao == "confirmar" and not aceitar)

    with st.container(horizontal=True):
        if st.button(
            "Melhorar", key=f"melhorar_{artigo_id}", icon=":material/auto_fix_high:", disabled=manifesto is None,
            help="Parágrafos entre páginas, texto perdido, segunda leitura das fórmulas, figuras e tema. "
            "Não roda o Docling de novo.",
        ):
            catalogo, relatorio = melhorar(catalogo, artigo_id)
            mensagem = relatorio
            if not bloqueado:
                catalogo, indexacao = indexar_agora(catalogo, artigo_id, aceitar)
                mensagem += f" · {indexacao}"
            st.session_state["aviso_revisao"] = ("info", mensagem)
            st.rerun()

        rotulo = "Reindexar" if linha["status_indexacao"] != "não indexado" else "Indexar"
        if st.button(rotulo, key=f"indexar_{artigo_id}", disabled=bloqueado):
            catalogo, mensagem = indexar_agora(catalogo, artigo_id, aceitar)
            st.session_state["aviso_revisao"] = ("success", mensagem)
            st.rerun()

        if st.button("Reprocessar", key=f"reprocessar_{artigo_id}", help="Roda o Docling de novo com as opções da barra lateral."):
            catalogo, resultado = processar_artigo(catalogo, artigo_id, indexar=True, forcar=True, aceitar_parcial=aceitar)
            st.session_state["aviso_revisao"] = ("info", " · ".join(f"{k}: {v}" for k, v in resultado.items()))
            st.rerun()

        with st.popover("Remover"):
            st.write("Apaga o PDF, a extração, os trechos do índice e a linha do catálogo.")
            if st.button("Confirmar remoção", type="primary", key=f"remover_{artigo_id}"):
                salvar_catalogo(bib.remover_artigo(catalogo, artigo_id, PASTAS, obter_indice()))
                st.session_state["aviso_revisao"] = ("success", f"Artigo {artigo_id} removido.")
                st.rerun()


# ---------------------------------------------------------------- inspeção


def inspecao(catalogo: pd.DataFrame, linha: pd.Series, manifesto: dict, elementos: list[dict]) -> None:
    st.markdown("#### Inspeção da extração")
    st.caption(AVISO_PAGINAS)
    contagens = manifesto.get("contagens", {})
    with st.container(horizontal=True):
        st.metric("Parágrafos", contagens.get("texto", 0) + contagens.get("lista", 0))
        st.metric("Seções", contagens.get("secao", 0))
        st.metric("Tabelas", contagens.get("tabela", 0))
        st.metric("Fórmulas", contagens.get("formula", 0))
        st.metric("Figuras", contagens.get("figura", 0))

    # Só a aba aberta é montada: artigos longos têm dezenas de fórmulas e figuras
    abas = st.tabs(
        ["Texto", "Tabelas", "Fórmulas", "Figuras", "Página do PDF", "Arquivos"],
        on_change="rerun",
        key=f"abas_{linha['id']}",
    )
    conteudos = [
        lambda: aba_texto(linha, elementos),
        lambda: aba_tabelas(elementos),
        lambda: aba_formulas(catalogo, linha, elementos, manifesto),
        lambda: aba_figuras(linha, elementos),
        lambda: aba_pagina(linha, manifesto, elementos),
        lambda: aba_arquivos(linha),
    ]
    for aba, desenhar in zip(abas, conteudos):
        if aba.open:
            with aba:
                desenhar()


def aba_texto(linha: pd.Series, elementos: list[dict]) -> None:
    paginas = sorted({p for e in elementos for p in e["paginas"]})
    escolha = st.selectbox("Página", ["Todas", *paginas], key=f"pagina_texto_{linha['id']}")
    marcas = sum(1 for e in elementos if e["tipo"] == "marca_dagua")
    if marcas:
        st.caption(f"{marcas} marca(s) d'água (ex.: carimbo de download) ocultada(s) e fora do índice.")
    blocos = []
    for elemento in elementos:
        if elemento["tipo"] == "marca_dagua" or (escolha != "Todas" and escolha not in elemento["paginas"]):
            continue
        local = f"p. {formatar_paginas(elemento['paginas'])}"
        if elemento.get("unido_com"):
            local += " · parágrafo unido entre páginas"
        if elemento["tipo"] in ("titulo", "secao"):
            blocos.append(f"### {escapar_md(elemento['texto'])}\n:small[:gray[{local} · {elemento['tipo']}]]")
        elif elemento["tipo"] in ("tabela", "figura", "formula"):
            blocos.append(f":small[:gray[▣ {elemento['tipo']} ({local}) — veja a aba correspondente]]")
        elif elemento["tipo"] == "texto_pdf":
            blocos.append(
                f":orange-badge[Texto recuperado do PDF] :small[:gray[{local} · não estava na extração do Docling]]\n\n"
                + escapar_md(elemento["texto"]).replace("\n", "  \n")
            )
        else:
            blocos.append(f"{escapar_md(elemento['texto'])}\n:small[:gray[{local} · {elemento['tipo']}]]")
    st.markdown("\n\n".join(blocos))


def aba_tabelas(elementos: list[dict]) -> None:
    tabelas = [e for e in elementos if e["tipo"] == "tabela"]
    if not tabelas:
        st.info("Nenhuma tabela reconhecida.")
    for numero, tabela in enumerate(tabelas, start=1):
        legenda = tabela.get("legenda") or f"Tabela {numero} (sem legenda)"
        st.markdown(f"**{escapar_md(legenda)}** · p. {formatar_paginas(tabela['paginas'])}")
        if tabela.get("erro"):
            st.warning(tabela["erro"])
        st.dataframe(tabela_como_df(tabela), hide_index=True, width="stretch", alt=legenda[:120])


def comparacao_mineru(catalogo: pd.DataFrame, linha: pd.Series, formulas: list[tuple[int, dict]], manifesto: dict) -> None:
    st.markdown("**Comparação opcional com MinerU**")
    st.caption(
        "O MinerU lê as páginas escolhidas e acrescenta uma terceira transcrição para conferência. "
        "A comparação só roda ao clicar no botão e não escolhe uma versão por você."
    )
    disponivel, mensagem = situacao_mineru()
    if not disponivel:
        st.info(f"{mensagem} Consulte a seção MinerU do README para instalar e configurar o ambiente opcional.")

    paginas_formulas = sorted({pagina for _, formula in formulas for pagina in formula.get("paginas", [])})
    total_paginas = int(linha["paginas"]) if pd.notna(linha["paginas"]) else max(paginas_formulas, default=1)
    paginas = list(range(1, max(total_paginas, 1) + 1))
    primeira = next((pagina for pagina in paginas_formulas if pagina in paginas), 1)
    if paginas:
        escolhidas = st.multiselect(
            "Páginas do PDF para comparar", paginas, default=[primeira],
            key=f"paginas_mineru_{linha['id']}", disabled=not disponivel,
            help="Numeração física do PDF. Comece com uma página. Os modelos locais precisam estar preparados conforme o README.",
        )
        forcar = st.checkbox(
            "Refazer a leitura mesmo se houver resultado salvo", key=f"forcar_mineru_{linha['id']}",
            disabled=not disponivel,
        )
        if st.button(
            "Comparar com MinerU", key=f"comparar_mineru_{linha['id']}",
            disabled=not disponivel or not escolhidas,
        ):
            try:
                with st.spinner("Comparando as páginas com os modelos locais do MinerU..."):
                    atualizado, relatorio = bib.comparar_formulas_mineru(
                        catalogo.copy(deep=True), linha["id"], PASTAS, obter_leitor_mineru(), escolhidas, forcar=forcar,
                    )
                    salvar_catalogo(atualizado)
            except Exception as erro:
                st.error(f"Não foi possível comparar com MinerU: {erro}")
            else:
                st.session_state["aviso_revisao"] = (
                    "info",
                    f"MinerU: {relatorio.get('associadas', 0)} fórmula(s) associada(s), "
                    f"{relatorio.get('ambiguas', 0)} associação(ões) ambígua(s) e "
                    f"{relatorio.get('sem_correspondencia', 0)} sem correspondência. "
                    "Confira as leituras e reindexe o artigo para atualizar a busca.",
                )
                st.rerun()

    relatorio = manifesto.get("formulas_mineru") or {}
    if relatorio:
        st.caption(
            f"Última comparação · páginas {formatar_paginas(relatorio.get('paginas', []))} · "
            f"{relatorio.get('associadas', 0)} associada(s) · {relatorio.get('ambiguas', 0)} ambígua(s) · "
            f"{relatorio.get('sem_correspondencia', 0)} sem correspondência."
        )
        extras = relatorio.get("nao_associadas") or []
        if extras:
            with st.expander(f"Fórmulas encontradas pelo MinerU sem associação ({len(extras)})"):
                st.caption("Estas leituras ainda não foram ligadas a uma fórmula do catálogo; confira a página original.")
                for numero, extra in enumerate(extras, start=1):
                    st.caption(f"Leitura {numero} · página {extra.get('pagina', '—')}")
                    if extra.get("latex"):
                        st.latex(extra["latex"])
                        st.code(extra["latex"], language="latex")


def aba_formulas(catalogo: pd.DataFrame, linha: pd.Series, elementos: list[dict], manifesto: dict | None = None) -> None:
    formulas = [(i, e) for i, e in enumerate(elementos) if e["tipo"] == "formula"]
    comparacao_mineru(catalogo, linha, formulas, manifesto or {})
    if not formulas:
        st.info(
            "Nenhuma fórmula reconhecida pelo Docling. Você pode comparar páginas com MinerU; "
            "leituras sem associação aparecerão no relatório acima."
        )
        return
    divergentes = [f for f in formulas if tem_divergencia(f[1])]
    st.caption(
        "Leituras disponíveis: CodeFormula (Docling), Dolphin-1.5 e MinerU opcional. "
        f"Quando qualquer par diverge (semelhança < {LIMITE_CONCORDANCIA:.0%}), compare com a imagem e escolha ou corrija. "
        "Concordância entre extratores não garante que a fórmula esteja correta."
    )
    chave_divergentes = f"so_divergentes_{linha['id']}"
    if not divergentes:
        st.session_state[chave_divergentes] = False
    so_divergentes = st.toggle(
        f"Mostrar só as {len(divergentes)} com leituras diferentes",
        value=bool(divergentes),
        key=chave_divergentes,
        disabled=not divergentes,
    )
    for posicao, formula in divergentes if so_divergentes else formulas:
        cartao_formula(catalogo, linha, elementos, posicao, formula)


def cartao_formula(catalogo: pd.DataFrame, linha: pd.Series, elementos: list[dict], posicao: int, formula: dict) -> None:
    with st.container(border=True):
        numero = f" · equação ({formula['numero']})" if formula.get("numero") else ""
        fonte = formula.get("latex_fonte", "docling")
        leituras = leituras_por_fonte(formula)
        selo = ":orange-badge[Leituras diferentes]" if tem_divergencia(formula) else ":green-badge[Leituras concordam]"
        if fonte == "manual":
            selo = ":blue-badge[Corrigida por você]"
        elif formula.get("latex_revisado"):
            selo = ":blue-badge[Revisada por você]"
        elif len(leituras) <= 1:
            selo = ":gray-badge[Só uma leitura]"
        st.markdown(f"{selo} :small[:gray[p. {formatar_paginas(formula['paginas'])}{numero} · seção: {formula['secao'] or '—'}]]")

        caminho = PASTAS.do_artigo(linha["id"]) / (formula.get("imagem") or "")
        if formula.get("imagem") and caminho.exists():
            st.image(str(caminho), alt="Recorte da fórmula no PDF", width="content")
            st.caption("Imagem original do PDF")

        nomes = {"docling": "Docling", "dolphin": "Dolphin", "mineru": "MinerU"}
        opcoes = {nomes[origem]: latex for origem, latex in leituras.items()}
        if fonte == "manual":
            opcoes = {"Corrigida": formula["latex"], **opcoes}
        for nome, latex in opcoes.items():
            if latex:
                st.caption(nome)
                st.latex(latex)
        comparacoes = comparar_leituras(formula)
        if comparacoes:
            st.caption("Semelhança da transcrição · " + " · ".join(
                f"{' × '.join(nomes[f] for f in par.split('_'))}: {valor:.0%}"
                for par, valor in comparacoes.items()
            ))

        padrao = "Corrigida" if fonte == "manual" else nomes.get(fonte)
        if padrao not in opcoes:
            padrao = next(iter(opcoes), "Editar")
        with st.expander("Escolher ou corrigir", icon=":material/edit:"):
            escolha = st.segmented_control(
                "Versão", list(opcoes) + ["Editar"],
                default=padrao,
                key=f"versao_{linha['id']}_{formula['id']}",
            )
            texto = opcoes.get(escolha, formula.get("latex", ""))
            if escolha == "Editar":
                texto = st.text_area("LaTeX", formula.get("latex", ""), key=f"edicao_{linha['id']}_{formula['id']}")
                if texto.strip():
                    st.latex(texto)
            else:
                st.code(texto, language="latex")
            if st.button(f"Usar esta versão · {escolha or 'escolha uma fonte'}", key=f"salvar_formula_{linha['id']}_{formula['id']}", disabled=not (escolha and texto.strip())):
                fonte_nova = {"Docling": "docling", "Dolphin": "dolphin", "MinerU": "mineru"}.get(escolha, "manual")
                salvar_catalogo(bib.escolher_latex(catalogo, linha["id"], PASTAS, formula["id"], texto, fonte_nova))
                st.session_state["aviso_revisao"] = ("success", "Fórmula salva. Reindexe o artigo para atualizar a busca.")
                st.rerun()

        if formula.get("texto_original"):
            st.caption(f"Texto bruto do PDF: {formula['texto_original']}")
        antes = next((e["texto"] for e in reversed(elementos[:posicao]) if e["tipo"] in ("texto", "lista")), "")
        depois = next((e["texto"] for e in elementos[posicao + 1 :] if e["tipo"] in ("texto", "lista")), "")
        st.caption(f"Contexto antes: {antes[-250:]}")
        st.caption(f"Contexto depois: {depois[:250]}")


def aba_figuras(linha: pd.Series, elementos: list[dict]) -> None:
    figuras = [e for e in elementos if e["tipo"] == "figura"]
    if not figuras:
        st.info("Nenhuma figura reconhecida.")
        return
    descritas = sum(1 for f in figuras if f.get("descricao"))
    st.caption(
        f"As figuras entram na busca pela legenda, pelo texto dentro delas e pela descrição automática "
        f"({descritas} de {len(figuras)} descritas). A descrição é gerada por um modelo de visão local e "
        "não é texto dos autores."
    )
    colunas = st.columns(2)
    for numero, figura in enumerate(figuras):
        with colunas[numero % 2].container(border=True):
            caminho = PASTAS.do_artigo(linha["id"]) / (figura.get("imagem") or "")
            legenda = figura.get("legenda") or "Figura sem legenda encontrada."
            if figura.get("imagem") and caminho.exists():
                st.image(str(caminho), width="stretch", alt=legenda[:120])
            st.markdown(escapar_md(legenda))
            caixa = figura.get("caixa") or {}
            st.caption(
                f"p. {formatar_paginas(figura['paginas'])} · posição (pt): "
                f"x {caixa.get('x0')}–{caixa.get('x1')}, y {caixa.get('y0')}–{caixa.get('y1')}"
            )
            if figura.get("texto_interno"):
                st.caption(f"Texto dentro da figura: {figura['texto_interno']}")
            if figura.get("descricao"):
                st.markdown(
                    f":violet-badge[Descrição automática · {figura.get('descricao_modelo', '')}] "
                    f"{escapar_md(figura['descricao'])}"
                )


def aba_pagina(linha: pd.Series, manifesto: dict, elementos: list[dict]) -> None:
    total = int(manifesto.get("paginas") or linha["paginas"] or 1)
    pagina = st.number_input("Página física", min_value=1, max_value=total, value=1, key=f"pagina_pdf_{linha['id']}")
    # Tudo o que aparece nesta página: com caixa aqui, com legenda aqui, ou sem posição (texto recuperado)
    da_pagina = [
        e for e in elementos
        if e["tipo"] != "marca_dagua"
        and (caixas_na_pagina(e, pagina) or caixas_na_pagina(e, pagina, legenda=True) or pagina in e["paginas"])
    ]
    mobilia = (manifesto.get("mobilia") or {}).get(str(pagina), [])
    caixas = [c for e in da_pagina for c in caixas_na_pagina(e, pagina) + caixas_na_pagina(e, pagina, legenda=True)]
    fora, amostra = texto_fora_das_caixas(caminho_do_pdf(PASTAS.pdfs, linha["sha256"]), pagina, caixas + mobilia)

    coluna_imagem, coluna_lista = st.columns([3, 2])
    with coluna_imagem:
        st.image(
            pagina_com_caixas(linha, pagina, da_pagina, mobilia), width="stretch",
            alt=f"Página {pagina} do PDF com as caixas dos elementos extraídos",
        )
    with coluna_lista:
        legenda = " ".join(f":color[■ {tipo}]{{foreground=\"{cor}\"}}" for tipo, cor in CORES_TIPO.items())
        st.markdown(f":small[{legenda} :color[■ cabeçalho/rodapé]{{foreground=\"{COR_MOBILIA}\"}}]")
        st.caption(
            "Números = ordem de leitura usada na indexação. “N…” = continuação do elemento N vindo de "
            "outra página; “N leg.” = legenda do elemento N. Cinza = cabeçalho/rodapé, fora do índice."
        )
        if fora > 0.03:
            st.warning(f"{fora:.0%} do texto desta página no PDF está fora de qualquer caixa: “{amostra[:120]}”")
        else:
            st.caption(f"Texto do PDF fora de qualquer caixa nesta página: {fora:.0%}.")
        for ordem, elemento in enumerate(da_pagina, start=1):
            resumo = elemento.get("texto") or elemento.get("legenda") or elemento.get("latex") or ""
            if not caixas_na_pagina(elemento, pagina) and caixas_na_pagina(elemento, pagina, legenda=True):
                resumo = elemento.get("legenda") or resumo
            observacao = ""
            if len(elemento["paginas"]) > 1:
                observacao = f" :small[:gray[(p. {formatar_paginas(elemento['paginas'])})]]"
            if elemento["tipo"] == "texto_pdf":
                observacao = " :small[:orange[(sem posição: recuperado do PDF)]]"
            st.markdown(f"**{ordem}.** `{elemento['tipo']}` {escapar_md(resumo[:90])}{observacao}")
        if mobilia:
            st.caption("Cabeçalho/rodapé: " + " · ".join(c["texto"] for c in mobilia if c.get("texto"))[:200])


def aba_arquivos(linha: pd.Series) -> None:
    pasta = PASTAS.do_artigo(linha["id"])
    st.caption(f"Pasta da extração: {pasta}")
    with st.container(horizontal=True):
        for nome, tipo in [
            ("documento.md", "text/markdown"),
            ("elementos.json", "application/json"),
            ("documento.json", "application/json"),
            ("manifesto.json", "application/json"),
        ]:
            caminho = pasta / nome
            if caminho.exists():
                st.download_button(nome, caminho.read_bytes(), file_name=f"{linha['id']}_{nome}", mime=tipo, key=f"baixar_{nome}_{linha['id']}")
    markdown = pasta / "documento.md"
    if markdown.exists():
        with st.expander("Ver Markdown gerado pelo Docling"):
            st.code(markdown.read_text(encoding="utf-8")[:20000], language="markdown")
    manifesto = pasta / "manifesto.json"
    if manifesto.exists():
        with st.expander("Ver manifesto (versão, configuração, status)"):
            st.json(json.loads(manifesto.read_text(encoding="utf-8")))
