"""Catálogo da biblioteca com Pandas.

O catálogo é um CSV simples (dados/catalogo.csv) com uma linha por PDF.
Campos desconhecidos ficam vazios (NA) e aparecem como "Não informado" na tela;
nada é preenchido por suposição.
"""

import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

import pandas as pd

NAO_INFORMADO = "Não informado"

COLUNAS = [
    "id",
    "arquivo_original",
    "sha256",
    "titulo",
    "titulo_origem",  # Docling | LLM | usuário
    "autores",
    "autores_origem",
    "ano",
    "ano_origem",
    "doi",
    "doi_origem",
    "tema",
    "tema_origem",  # informado | inferido (LLM) | inferido (similaridade) | usuário
    "palavras_chave",
    "paginas",
    "data_importacao",
    "status_extracao",  # pendente | concluída | parcial | falhou
    "status_indexacao",  # não indexado | indexado | reindexação necessária
    "qualidade_verificada",  # o usuário conferiu a extração na inspeção
    "metadados_revisados",  # o usuário salvou/corrigiu os metadados
    "n_trechos",
    "modelo_indexacao",
    "config_extracao",
]

COLUNAS_TEXTO = ["titulo", "autores", "doi", "tema", "palavras_chave"]
COLUNAS_ORIGEM = ["titulo_origem", "autores_origem", "ano_origem", "doi_origem", "tema_origem"]
CAMPOS_EDITAVEIS = ["titulo", "autores", "ano", "doi", "tema"]

PADRAO_DOI = re.compile(r"^10\.\d{4,9}/\S+$")


# ---------------------------------------------------------------- leitura e escrita


def catalogo_vazio() -> pd.DataFrame:
    return normalizar_catalogo(pd.DataFrame(columns=COLUNAS))


def carregar_catalogo(caminho: Path) -> pd.DataFrame:
    caminho = Path(caminho)
    if not caminho.exists():
        return catalogo_vazio()
    bruto = pd.read_csv(caminho, dtype=str, keep_default_na=False)
    return normalizar_catalogo(bruto)


def salvar_catalogo(catalogo: pd.DataFrame, caminho: Path) -> None:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    catalogo[COLUNAS].to_csv(caminho, index=False)


def exportar_csv(catalogo: pd.DataFrame) -> bytes:
    """CSV para download (utf-8 com BOM para abrir acentuado no Excel)."""
    return catalogo.to_csv(index=False).encode("utf-8-sig")


# ---------------------------------------------------------------- limpeza


def normalizar_catalogo(catalogo: pd.DataFrame) -> pd.DataFrame:
    """Padroniza tipos, espaços, ausências e formatos dos campos."""
    df = catalogo.copy()
    for coluna in COLUNAS:
        if coluna not in df.columns:
            df[coluna] = pd.NA

    # Textos: remove espaços extras; vazio ou "Não informado" vira ausente (NA)
    for coluna in ["id", "arquivo_original", "sha256", *COLUNAS_TEXTO, *COLUNAS_ORIGEM, "modelo_indexacao", "config_extracao"]:
        df[coluna] = (
            df[coluna]
            .astype("string")
            .str.replace(r"\s+", " ", regex=True)
            .str.strip()
            .replace({"": pd.NA, NAO_INFORMADO: pd.NA, "nan": pd.NA, "<NA>": pd.NA})
        )

    df["autores"] = df["autores"].map(normalizar_autores, na_action="ignore").astype("string")
    df["doi"] = df["doi"].map(normalizar_doi, na_action="ignore").astype("string")

    # Temas que diferem só em maiúsculas ("RAG" e "rag") viram a grafia mais usada
    chave_tema = df["tema"].str.lower()
    grafia = df.groupby(chave_tema)["tema"].agg(lambda temas: temas.mode().iloc[0])
    df["tema"] = chave_tema.map(grafia).astype("string")

    # Ano: só valores plausíveis; o resto fica ausente em vez de inventado
    ano = pd.to_numeric(df["ano"], errors="coerce")
    ano = ano.where((ano >= 1900) & (ano <= date.today().year + 1))
    df["ano"] = ano.round().astype("Int64")

    for coluna in ["paginas", "n_trechos"]:
        df[coluna] = pd.to_numeric(df[coluna], errors="coerce").astype("Int64")

    df["data_importacao"] = pd.to_datetime(df["data_importacao"], errors="coerce")

    for coluna in ["qualidade_verificada", "metadados_revisados"]:
        df[coluna] = (
            df[coluna].astype("string").str.lower().isin(["true", "1", "sim"]).astype(bool)
        )

    df["status_extracao"] = df["status_extracao"].astype("string").fillna("pendente")
    df["status_indexacao"] = df["status_indexacao"].astype("string").fillna("não indexado")
    df.loc[df["status_extracao"].str.strip() == "", "status_extracao"] = "pendente"
    df.loc[df["status_indexacao"].str.strip() == "", "status_indexacao"] = "não indexado"

    return df[COLUNAS].reset_index(drop=True)


def normalizar_autores(texto: str) -> str | None:
    """Separa autores por '; ' (aceita ';', ' and ' e quebras de linha)."""
    partes = re.split(r";|\n|\band\b", texto)
    nomes = [p.strip(" ,.") for p in partes if p.strip(" ,.")]
    return "; ".join(nomes) if nomes else None


def normalizar_doi(texto: str) -> str | None:
    """Remove prefixos (https://doi.org/, doi:) e valida o formato 10.xxxx/..."""
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", texto.strip(), flags=re.IGNORECASE)
    doi = doi.rstrip(".,;").lower()
    return doi if PADRAO_DOI.match(doi) else None


def titulo_normalizado(titulo) -> str:
    """Título sem acentos, pontuação e caixa — usado só para *sinalizar* duplicatas."""
    if pd.isna(titulo):
        return ""
    sem_acento = unicodedata.normalize("NFKD", str(titulo)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).strip()


# ---------------------------------------------------------------- operações


def novo_registro(
    sha256: str,
    arquivo_original: str,
    paginas: int,
    tema: str | None = None,
    titulo: str | None = None,
    doi: str | None = None,
) -> dict:
    return {
        "id": sha256[:12],
        "arquivo_original": arquivo_original,
        "sha256": sha256,
        "titulo": titulo,
        "titulo_origem": "Docling" if titulo else None,
        "autores": None,
        "autores_origem": None,
        "ano": None,
        "ano_origem": None,
        "doi": doi,
        "doi_origem": "impresso no artigo" if doi else None,
        "tema": tema,
        "tema_origem": "informado" if tema else None,
        "palavras_chave": None,
        "paginas": paginas,
        "data_importacao": datetime.now().isoformat(timespec="seconds"),
        "status_extracao": "pendente",
        "status_indexacao": "não indexado",
        "qualidade_verificada": False,
        "metadados_revisados": False,
        "n_trechos": 0,
        "modelo_indexacao": None,
        "config_extracao": None,
    }


def buscar_por_hash(catalogo: pd.DataFrame, sha256: str) -> pd.Series | None:
    encontrados = catalogo[catalogo["sha256"] == sha256]
    return None if encontrados.empty else encontrados.iloc[0]


def adicionar_artigo(catalogo: pd.DataFrame, registro: dict) -> pd.DataFrame:
    if buscar_por_hash(catalogo, registro["sha256"]) is not None:
        raise ValueError("Este arquivo já está no catálogo.")
    novo = pd.DataFrame([registro]).astype("object")
    base = catalogo.astype("object")
    return normalizar_catalogo(pd.concat([base, novo], ignore_index=True) if len(base) else novo)


def atualizar_artigo(catalogo: pd.DataFrame, artigo_id: str, campos: dict) -> pd.DataFrame:
    df = catalogo.astype("object").copy()
    linha = df["id"] == artigo_id
    if not linha.any():
        raise KeyError(f"Artigo {artigo_id} não encontrado.")
    for coluna, valor in campos.items():
        if coluna not in COLUNAS:
            raise KeyError(f"Coluna desconhecida: {coluna}")
        df.loc[linha, coluna] = valor
    return normalizar_catalogo(df)


def remover_artigo(catalogo: pd.DataFrame, artigo_id: str) -> pd.DataFrame:
    return catalogo[catalogo["id"] != artigo_id].reset_index(drop=True)


def marcar_possiveis_duplicatas(catalogo: pd.DataFrame) -> pd.DataFrame:
    """Sinaliza arquivos diferentes que parecem o mesmo artigo (mesmo DOI ou título).

    Apenas sinaliza: versões diferentes (preprint e publicado, por exemplo)
    continuam como linhas separadas, e o usuário decide o que fazer.
    """
    df = catalogo.copy()
    df["titulo_normalizado"] = df["titulo"].map(titulo_normalizado)
    df["possivel_duplicata"] = ""

    for coluna, motivo in [("doi", "mesmo DOI"), ("titulo_normalizado", "título igual")]:
        validos = df[df[coluna].notna() & (df[coluna] != "")]
        grupos = validos.groupby(coluna)["id"].apply(list)
        for ids in grupos[grupos.map(len) > 1]:
            for artigo_id in ids:
                outros = ", ".join(i for i in ids if i != artigo_id)
                linha = df["id"] == artigo_id
                atual = df.loc[linha, "possivel_duplicata"].iloc[0]
                texto = f"{motivo} de {outros}"
                df.loc[linha, "possivel_duplicata"] = f"{atual}; {texto}" if atual else texto

    return df.drop(columns="titulo_normalizado")


def filtrar_catalogo(
    catalogo: pd.DataFrame,
    temas: list[str] | None = None,
    ano_min: int | None = None,
    ano_max: int | None = None,
    incluir_sem_ano: bool = True,
    status_extracao: list[str] | None = None,
    status_indexacao: list[str] | None = None,
) -> pd.DataFrame:
    filtro = pd.Series(True, index=catalogo.index)
    if temas:
        filtro &= catalogo["tema"].fillna(NAO_INFORMADO).isin(temas)
    if ano_min is not None or ano_max is not None:
        no_intervalo = catalogo["ano"].between(ano_min or 0, ano_max or 9999)
        no_intervalo = no_intervalo.fillna(False).astype(bool)
        if incluir_sem_ano:
            no_intervalo |= catalogo["ano"].isna()
        filtro &= no_intervalo
    if status_extracao:
        filtro &= catalogo["status_extracao"].isin(status_extracao)
    if status_indexacao:
        filtro &= catalogo["status_indexacao"].isin(status_indexacao)
    return catalogo[filtro]


# ---------------------------------------------------------------- agregações


def contar_por(catalogo: pd.DataFrame, coluna: str) -> pd.DataFrame:
    """Quantidade de artigos por valor da coluna; ausências contam como "Não informado"."""
    valores = catalogo[coluna].astype("string").fillna(NAO_INFORMADO)
    contagem = valores.value_counts().rename_axis(coluna).reset_index(name="artigos")
    return contagem.sort_values(coluna).reset_index(drop=True)


def resumo_por_tema(catalogo: pd.DataFrame) -> pd.DataFrame:
    df = catalogo.assign(
        tema=catalogo["tema"].fillna(NAO_INFORMADO),
        indexado=catalogo["status_indexacao"].eq("indexado"),
    )
    return (
        df.groupby("tema")
        .agg(
            artigos=("id", "count"),
            paginas=("paginas", "sum"),
            trechos=("n_trechos", "sum"),
            indexados=("indexado", "sum"),
            ano_mais_antigo=("ano", "min"),
            ano_mais_recente=("ano", "max"),
        )
        .reset_index()
        .sort_values("artigos", ascending=False)
    )


def indicadores(catalogo: pd.DataFrame) -> dict:
    return {
        "artigos": len(catalogo),
        "paginas": int(catalogo["paginas"].sum()) if len(catalogo) else 0,
        "indexados": int(catalogo["status_indexacao"].eq("indexado").sum()),
        "trechos": int(catalogo["n_trechos"].sum()) if len(catalogo) else 0,
        "qualidade_verificada": int(catalogo["qualidade_verificada"].sum()),
        "metadados_pendentes": int((~catalogo["metadados_revisados"]).sum()),
    }


def para_exibicao(catalogo: pd.DataFrame) -> pd.DataFrame:
    """Cópia para a tela: ausências viram "Não informado"."""
    df = catalogo.copy()
    for coluna in COLUNAS_TEXTO:
        df[coluna] = df[coluna].fillna(NAO_INFORMADO)
    df["ano"] = df["ano"].astype("string").fillna(NAO_INFORMADO)
    return df


def rotulo_artigo(linha: pd.Series) -> str:
    """Texto curto para listas de seleção."""
    titulo = linha["titulo"] if pd.notna(linha["titulo"]) else linha["arquivo_original"]
    ano = f" ({linha['ano']})" if pd.notna(linha["ano"]) else ""
    return f"{titulo}{ano} · {linha['id']}"


def formatar_referencia(linha: pd.Series) -> str:
    """Referência curta construída só com os metadados armazenados."""
    autores = linha["autores"] if pd.notna(linha["autores"]) else "Autores não informados"
    ano = str(linha["ano"]) if pd.notna(linha["ano"]) else "ano não informado"
    titulo = linha["titulo"] if pd.notna(linha["titulo"]) else linha["arquivo_original"]
    referencia = f"{autores} ({ano}). {titulo}."
    if pd.notna(linha["doi"]):
        referencia += f" DOI: {linha['doi']}."
    return referencia
