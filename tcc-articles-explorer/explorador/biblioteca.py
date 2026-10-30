"""Orquestra o fluxo importar -> extrair -> indexar e mantém o catálogo em dia.

As funções recebem e devolvem o DataFrame do catálogo; quem chama decide
quando salvar. Assim o fluxo pode ser testado sem a interface.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from explorador import catalogo as cat
from explorador.armazenamento import ErroPDF, caminho_do_pdf, salvar_pdf, validar_pdf
from explorador.extracao import (
    ConfigExtracao,
    atualizar_sem_docling,
    avaliar_para_indexacao,
    carregar_elementos,
    carregar_manifesto,
    extrair_pdf,
    salvar_extracao,
)
from explorador.figuras import descrever_figuras
from explorador.formulas import reler_formulas
from explorador.metadados import (
    escolher_titulo,
    inferir_com_llm,
    inferir_por_similaridade,
    referencia_do_pdf,
    texto_inicial,
)
from explorador.pos_processamento import detectar_titulo
from explorador.trechos import gerar_trechos


@dataclass(frozen=True)
class Pastas:
    pdfs: Path
    extracoes: Path
    catalogo: Path

    @classmethod
    def em(cls, raiz: Path) -> "Pastas":
        raiz = Path(raiz)
        return cls(raiz / "pdfs", raiz / "extracoes", raiz / "catalogo.csv")

    def do_artigo(self, artigo_id: str) -> Path:
        return self.extracoes / artigo_id


@dataclass
class OpcoesMelhoria:
    """Etapas aplicadas depois do Docling. Recursos ausentes (None) pulam a etapa."""

    atualizar_estrutura: bool = True  # parágrafos, marcas d'água, texto perdido
    leitor_formulas: object = None  # LeitorDolphin
    cliente_visao: object = None  # cliente OpenAI apontando para o Ollama
    modelo_visao: str = ""
    inferir_metadados: bool = True
    cliente_llm: object = None
    modelo_llm: str = ""
    embeddings: object = None  # para inferir o tema sem LLM
    substituir_tema: bool = False


@dataclass
class ResultadoImportacao:
    arquivo: str
    situacao: str  # importado | duplicado | erro
    mensagem: str
    artigo_id: str | None = None


def _linha(catalogo: pd.DataFrame, artigo_id: str) -> pd.Series:
    linhas = catalogo[catalogo["id"] == artigo_id]
    if linhas.empty:
        raise KeyError(f"Artigo {artigo_id} não está no catálogo.")
    return linhas.iloc[0]


def importar_pdf(
    catalogo: pd.DataFrame,
    conteudo: bytes,
    nome_arquivo: str,
    pastas: Pastas,
    tema: str | None = None,
    max_mb: int = 50,
    max_paginas: int = 80,
) -> tuple[pd.DataFrame, ResultadoImportacao]:
    """Valida, identifica pelo SHA-256 e guarda o PDF original."""
    try:
        info = validar_pdf(conteudo, max_mb, max_paginas)
    except ErroPDF as erro:
        return catalogo, ResultadoImportacao(nome_arquivo, "erro", str(erro))

    existente = cat.buscar_por_hash(catalogo, info.sha256)
    if existente is not None:
        mensagem = (
            f"Conteúdo idêntico a “{existente['arquivo_original']}” "
            f"(id {existente['id']}). O arquivo não será reprocessado."
        )
        return catalogo, ResultadoImportacao(nome_arquivo, "duplicado", mensagem, existente["id"])

    salvar_pdf(conteudo, pastas.pdfs)
    registro = cat.novo_registro(info.sha256, nome_arquivo, info.paginas, tema=tema)
    catalogo = cat.adicionar_artigo(catalogo, registro)
    return catalogo, ResultadoImportacao(
        nome_arquivo, "importado", f"{info.paginas} página(s).", registro["id"]
    )


def extrair_artigo(
    catalogo: pd.DataFrame,
    artigo_id: str,
    pastas: Pastas,
    config: ConfigExtracao,
    conversor=None,
    forcar: bool = False,
) -> tuple[pd.DataFrame, dict]:
    """Roda (ou reaproveita) a extração e atualiza status e metadados detectados."""
    linha = _linha(catalogo, artigo_id)
    manifesto = extrair_pdf(
        caminho_do_pdf(pastas.pdfs, linha["sha256"]),
        pastas.do_artigo(artigo_id),
        config,
        conversor=conversor,
        forcar=forcar,
    )

    campos = {"status_extracao": manifesto["status"], "config_extracao": manifesto["assinatura"]}
    # Só preenche o que estava vazio, e só com o que foi encontrado no próprio PDF
    if pd.isna(linha["titulo"]) and manifesto.get("titulo_detectado"):
        campos["titulo"] = manifesto["titulo_detectado"]
    if pd.isna(linha["doi"]) and manifesto.get("doi_detectado"):
        campos["doi"] = manifesto["doi_detectado"]
    if not manifesto.get("reaproveitado"):
        campos["qualidade_verificada"] = False  # nova extração precisa ser conferida de novo
        if linha["status_indexacao"] == "indexado":
            campos["status_indexacao"] = "reindexação necessária"
    return cat.atualizar_artigo(catalogo, artigo_id, campos), manifesto


def melhorar_artigo(
    catalogo: pd.DataFrame, artigo_id: str, pastas: Pastas, opcoes: OpcoesMelhoria
) -> tuple[pd.DataFrame, list[str]]:
    """Aplica as melhorias numa extração existente, sem rodar o Docling.

    Devolve o catálogo e um relatório curto. O índice não é atualizado aqui:
    chame indexar_artigo depois.
    """
    linha = _linha(catalogo, artigo_id)
    pasta = pastas.do_artigo(artigo_id)
    caminho_pdf = caminho_do_pdf(pastas.pdfs, linha["sha256"])
    manifesto = carregar_manifesto(pasta)
    if manifesto is None or manifesto.get("status") == "falhou":
        return catalogo, ["Sem extração válida: nada a melhorar."]

    relatorio = []
    if opcoes.atualizar_estrutura:
        manifesto = atualizar_sem_docling(caminho_pdf, pasta)
        pos = manifesto["pos_processamento"]
        relatorio.append(
            f"{pos.get('paragrafos_unidos', 0)} parágrafo(s) unido(s), "
            f"{pos.get('marcas_dagua', 0)} marca(s) d'água, "
            f"{(pos.get('cobertura') or {}).get('linhas_recuperadas', 0)} linha(s) recuperada(s)"
        )

    elementos = carregar_elementos(pasta)
    info = reler_formulas(elementos, caminho_pdf, pasta, opcoes.leitor_formulas)
    manifesto["formulas"] = info
    if opcoes.leitor_formulas is not None:
        relatorio.append(f"{info['lidas']} fórmula(s) relida(s), {info['divergentes']} com leituras diferentes")
    if opcoes.cliente_visao is not None:
        manifesto["figuras"] = descrever_figuras(elementos, pasta, opcoes.cliente_visao, opcoes.modelo_visao)
        relatorio.append(f"{manifesto['figuras']['descritas']} figura(s) descrita(s)")
    salvar_extracao(pasta, elementos, manifesto)

    campos = {"qualidade_verificada": False}
    if linha["status_indexacao"] == "indexado":
        campos["status_indexacao"] = "reindexação necessária"
    if opcoes.inferir_metadados:
        catalogo, mensagem = inferir_metadados(catalogo, artigo_id, pastas, opcoes)
        relatorio.append(mensagem)
    if campos:
        catalogo = cat.atualizar_artigo(catalogo, artigo_id, campos)
    return catalogo, relatorio


def escolher_latex(
    catalogo: pd.DataFrame, artigo_id: str, pastas: Pastas, id_elemento: str, latex: str, fonte: str
) -> pd.DataFrame:
    """Grava a versão escolhida (ou corrigida à mão) de uma fórmula."""
    pasta = pastas.do_artigo(artigo_id)
    elementos = carregar_elementos(pasta)
    formula = next(e for e in elementos if e["id"] == id_elemento and e["tipo"] == "formula")
    formula["latex"], formula["latex_fonte"] = latex.strip(), fonte
    formula["latex_revisado"] = True
    salvar_extracao(pasta, elementos, carregar_manifesto(pasta))
    campos = {"qualidade_verificada": False}
    if _linha(catalogo, artigo_id)["status_indexacao"] == "indexado":
        campos["status_indexacao"] = "reindexação necessária"
    return cat.atualizar_artigo(catalogo, artigo_id, campos)


def comparar_formulas_mineru(
    catalogo: pd.DataFrame,
    artigo_id: str,
    pastas: Pastas,
    leitor,
    paginas: list[int],
    forcar: bool = False,
) -> tuple[pd.DataFrame, dict]:
    """Adiciona uma leitura local opcional sem substituir a fórmula escolhida.

    Uma falha do processo deixa os elementos e o catálogo intactos. Resultados
    sem correspondência geométrica ficam no relatório para inspeção humana.
    """
    from explorador.mineru import ErroMinerU, associar_formulas

    linha = _linha(catalogo, artigo_id)
    pasta = pastas.do_artigo(artigo_id)
    manifesto = carregar_manifesto(pasta)
    if not manifesto or manifesto.get("status") == "falhou":
        raise ErroMinerU("Extraia o artigo com o Docling antes de comparar as fórmulas.")
    if not paginas or any(type(p) is not int or p < 1 or p > int(linha["paginas"]) for p in paginas):
        raise ErroMinerU("Selecione páginas válidas do PDF para comparar.")
    paginas = sorted(set(paginas))
    elementos = carregar_elementos(pasta)
    resultado = leitor.ler(
        caminho_do_pdf(pastas.pdfs, linha["sha256"]), pasta / "mineru", paginas, forcar=forcar,
    )
    relatorio = associar_formulas(elementos, resultado["formulas"], paginas)
    relatorio.update(
        paginas=paginas,
        modelo=resultado.get("modelo", "MinerU basic/ONNX"),
        versao=resultado.get("versao"),
        reaproveitado=bool(resultado.get("reaproveitado")),
    )
    manifesto["formulas_mineru"] = relatorio
    salvar_extracao(pasta, elementos, manifesto)
    if relatorio["associadas"]:
        campos = {"qualidade_verificada": False}
        if linha["status_indexacao"] == "indexado":
            campos["status_indexacao"] = "reindexação necessária"
        catalogo = cat.atualizar_artigo(catalogo, artigo_id, campos)
    return catalogo, relatorio


def inferir_metadados(
    catalogo: pd.DataFrame, artigo_id: str, pastas: Pastas, opcoes: OpcoesMelhoria
) -> tuple[pd.DataFrame, str]:
    """Título, tema, autores, ano e DOI a partir do artigo.

    Preserva valores digitados pelo usuário. Apenas a opção explícita
    substituir_tema permite trocar um tema preenchido. Palavras-chave existentes
    são preservadas, pois catálogos antigos não registram a origem desse campo.
    """
    linha = _linha(catalogo, artigo_id)
    elementos = carregar_elementos(pastas.do_artigo(artigo_id))
    texto = texto_inicial(elementos)
    if not texto:
        return catalogo, "Sem texto para inferir título e tema."

    def editavel(campo: str) -> bool:
        origem = linha.get(f"{campo}_origem")
        return pd.isna(linha[campo]) or (pd.notna(origem) and origem != "usuário")

    campos, partes = {}, []
    # Ano e DOI por identificadores impressos (não precisam de LLM)
    referencia = referencia_do_pdf(caminho_do_pdf(pastas.pdfs, linha["sha256"]), linha["arquivo_original"])
    if referencia.doi and editavel("doi"):
        campos.update(doi=referencia.doi, doi_origem=referencia.doi_origem)
        partes.append(f"DOI: {referencia.doi_origem}")
    if referencia.ano and editavel("ano"):
        campos.update(ano=referencia.ano, ano_origem=referencia.ano_origem)
        partes.append(f"ano: {referencia.ano_origem}")

    sugestao, aviso = None, ""
    if opcoes.cliente_llm is not None:
        try:
            sugestao = inferir_com_llm(opcoes.cliente_llm, texto, opcoes.modelo_llm)
        except Exception as erro:  # sem crédito, sem rede...: cai para a similaridade
            aviso = f" (LLM indisponível: {type(erro).__name__})"
    if sugestao is None and opcoes.embeddings is not None:
        sugestao = inferir_por_similaridade(opcoes.embeddings, texto)
        sugestao.observacao += aviso
    if sugestao is None:
        catalogo = cat.atualizar_artigo(catalogo, artigo_id, campos)
        return catalogo, " · ".join(partes) or "Nenhum recurso disponível para inferir o tema."

    if sugestao.autores and editavel("autores"):
        campos.update(autores="; ".join(sugestao.autores), autores_origem="LLM (conferidos no texto)")
        partes.append(f"{len(sugestao.autores)} autor(es)")
    if sugestao.ano and "ano" not in campos and editavel("ano"):
        campos.update(ano=sugestao.ano, ano_origem="LLM (conferido no texto)")
        partes.append("ano: impresso no artigo")
    if pd.isna(linha["titulo_origem"]) or linha["titulo_origem"] != "usuário":
        titulo, origem = escolher_titulo(detectar_titulo(elementos), sugestao.titulo)
        if titulo:
            campos.update(titulo=titulo, titulo_origem=origem)
    tema_editavel = (
        pd.isna(linha["tema"])
        or opcoes.substituir_tema
        or str(linha["tema_origem"]).startswith("inferido")
    )
    if tema_editavel:
        campos.update(tema=sugestao.tema, tema_origem=f"inferido ({sugestao.origem})")
    if sugestao.palavras_chave and pd.isna(linha["palavras_chave"]):
        campos["palavras_chave"] = "; ".join(sugestao.palavras_chave)
    catalogo = cat.atualizar_artigo(catalogo, artigo_id, campos)
    tema_final = campos.get("tema", linha["tema"])
    origem_tema = campos.get("tema_origem", linha["tema_origem"])
    partes.insert(0, f"Tema: {tema_final} ({origem_tema})")
    return catalogo, " · ".join(partes) + f". {sugestao.observacao}".rstrip(". ")


def indexar_artigo(
    catalogo: pd.DataFrame,
    artigo_id: str,
    pastas: Pastas,
    indice,
    aceitar_parcial: bool = False,
    tamanho_trecho: int = 1200,
) -> tuple[pd.DataFrame, bool, str]:
    """Gera os trechos e substitui os do artigo no índice.

    Extrações falhas ou vazias nunca são indexadas; parciais ou suspeitas só
    com aceitar_parcial=True. Quando não indexa, remove trechos antigos.
    """
    linha = _linha(catalogo, artigo_id)
    pasta = pastas.do_artigo(artigo_id)
    decisao, motivo = avaliar_para_indexacao(carregar_manifesto(pasta))

    if decisao == "bloqueado" or (decisao == "confirmar" and not aceitar_parcial):
        indice.remover_artigo(artigo_id)
        catalogo = cat.atualizar_artigo(
            catalogo,
            artigo_id,
            {"status_indexacao": "não indexado", "n_trechos": 0, "modelo_indexacao": None},
        )
        if decisao == "confirmar":
            motivo += " Revise a extração e confirme para indexar mesmo assim."
        return catalogo, False, motivo

    titulo = linha["titulo"] if pd.notna(linha["titulo"]) else linha["arquivo_original"]
    trechos = gerar_trechos(carregar_elementos(pasta), artigo_id, titulo, tamanho_trecho)
    if not trechos:
        indice.remover_artigo(artigo_id)
        catalogo = cat.atualizar_artigo(
            catalogo, artigo_id,
            {"status_indexacao": "não indexado", "n_trechos": 0, "modelo_indexacao": None},
        )
        return catalogo, False, "A extração não gerou nenhum trecho indexável."

    quantidade = indice.indexar_artigo(artigo_id, trechos)
    catalogo = cat.atualizar_artigo(
        catalogo,
        artigo_id,
        {"status_indexacao": "indexado", "n_trechos": quantidade, "modelo_indexacao": indice.assinatura},
    )
    return catalogo, True, f"{quantidade} trechos indexados."


def remover_artigo(catalogo: pd.DataFrame, artigo_id: str, pastas: Pastas, indice) -> pd.DataFrame:
    """Remove o artigo do índice, do disco e do catálogo."""
    linha = _linha(catalogo, artigo_id)
    indice.remover_artigo(artigo_id)
    shutil.rmtree(pastas.do_artigo(artigo_id), ignore_errors=True)
    caminho_do_pdf(pastas.pdfs, linha["sha256"]).unlink(missing_ok=True)
    return cat.remover_artigo(catalogo, artigo_id)


def sincronizar_indexacao(catalogo: pd.DataFrame, indice) -> pd.DataFrame:
    """Marca para reindexação os artigos cujo índice sumiu ou usa outro modelo."""
    if catalogo.empty:
        return catalogo
    presentes = indice.artigos_indexados()
    desatualizado = catalogo["status_indexacao"].eq("indexado") & (
        ~catalogo["id"].isin(presentes) | catalogo["modelo_indexacao"].ne(indice.assinatura)
    )
    if not desatualizado.any():
        return catalogo
    df = catalogo.copy()
    df.loc[desatualizado, "status_indexacao"] = "reindexação necessária"
    return df


def reindexar_todos(catalogo: pd.DataFrame, pastas: Pastas, indice, tamanho_trecho: int = 1200):
    """Reindexa os artigos que já estavam no índice (útil após trocar o modelo)."""
    mensagens = []
    alvo = catalogo["status_indexacao"].isin(["indexado", "reindexação necessária"])
    for artigo_id in catalogo.loc[alvo, "id"]:
        # O usuário já tinha aceitado esses artigos antes; mantém a decisão
        catalogo, ok, mensagem = indexar_artigo(
            catalogo, artigo_id, pastas, indice, aceitar_parcial=True, tamanho_trecho=tamanho_trecho
        )
        mensagens.append((artigo_id, ok, mensagem))
    return catalogo, mensagens
