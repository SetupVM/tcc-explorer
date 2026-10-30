"""Correções aplicadas à lista de elementos depois do Docling.

Trabalha só com elementos.json e com o PDF original, então pode ser
reaplicado em extrações antigas sem rodar o Docling de novo. Etapas:

1. ordem de leitura em páginas de duas colunas;
2. marcas d'água (ex.: carimbo do JSTOR) deixam de ser texto do artigo;
3. parágrafos que continuam na página seguinte são unidos;
4. título e seções;
5. texto que existe no PDF mas não apareceu na extração é recuperado.
"""

import re
from collections import Counter
from pathlib import Path

VERSAO_POS = 4  # 4: preserva argumentos de fórmulas e reavalia marcas d'água ambíguas

SECOES_COMUNS = re.compile(
    r"^\s*([\dIVX]+\.?\s*)?(abstract|resumo|introduction|introdução|keywords)\b", re.IGNORECASE
)
CABECALHO_NUMERADO = re.compile(r"^\s*(\d+(\.\d+)*\.?|[IVX]+\.|[A-Z]\.)\s")
MARCA_DAGUA = re.compile(
    r"^\s*(?:this (?:content|article|pdf) (?:was )?downloaded from\b|all use subject to\b)",
    re.IGNORECASE,
)
ENDERECO_CARIMBO = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b|\bjstor\.org\b", re.IGNORECASE)
FRAGMENTO_DATA = re.compile(
    r"^(?:[\d\s,.:/+-]|Mon|Tue|Wed|Thu|Fri|Sat|Sun|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|UTC|ed|ct|O)+$",
    re.IGNORECASE,
)
# Elementos que podem aparecer no meio de um parágrafo que continua na outra página
FLUTUANTES = {"figura", "tabela", "legenda", "nota", "marca_dagua"}
LIMITE_COBERTURA = 0.85


def pos_processar(elementos: list[dict], caminho_pdf: Path | None, corrigir_colunas: bool = True):
    """Aplica todas as correções. Devolve (elementos, informações para o manifesto)."""
    from explorador.formulas import preparar_formulas

    info = {"versao": VERSAO_POS}
    elementos = [e for e in elementos if e["tipo"] != "texto_pdf"]  # refeito no fim
    info["paginas_reordenadas"] = []
    if corrigir_colunas:
        elementos, info["paginas_reordenadas"] = corrigir_ordem_colunas(elementos)
    info["marcas_dagua"] = marcar_marcas_dagua(elementos)
    elementos, info["paragrafos_unidos"] = juntar_paragrafos_entre_paginas(elementos)
    preparar_formulas(elementos)
    marcar_titulo(elementos)
    atribuir_secoes(elementos)
    if caminho_pdf is not None and Path(caminho_pdf).exists():
        elementos, info["cobertura"] = completar_com_texto_do_pdf(elementos, caminho_pdf)
        atribuir_secoes(elementos)
    return elementos, info


# ---------------------------------------------------------------- título e seções


def detectar_titulo(elementos: list[dict]) -> str | None:
    """Título marcado pelo Docling; senão, o primeiro cabeçalho da página 1
    (às vezes o título vem rotulado como seção). Fica para o usuário revisar."""
    for elemento in elementos:
        if elemento["tipo"] == "titulo" and elemento["texto"].strip():
            return elemento["texto"].strip()
    for elemento in elementos:
        if elemento["paginas"] != [1]:
            break
        if elemento["tipo"] == "secao":
            texto = elemento["texto"].strip()
            return None if SECOES_COMUNS.match(texto) else texto
    return None


def marcar_titulo(elementos: list[dict]) -> None:
    """Se o título veio rotulado como seção, passa a ser tratado como título."""
    titulo = detectar_titulo(elementos)
    for elemento in elementos:
        if elemento["tipo"] == "titulo":
            return
        if elemento["tipo"] == "secao" and elemento["texto"].strip() == titulo:
            elemento["tipo"] = "titulo"
            return


def atribuir_secoes(elementos: list[dict]) -> list[dict]:
    """Cada elemento recebe o título da última seção vista na ordem de leitura."""
    secao_atual = ""
    for elemento in elementos:
        if elemento["tipo"] == "secao":
            secao_atual = elemento["texto"].strip()
        elemento["secao"] = secao_atual
    return elementos


# ---------------------------------------------------------------- marcas d'água e parágrafos


def marcar_marcas_dagua(elementos: list[dict]) -> int:
    """Exclui carimbos reconhecíveis sem tratar IPs ou origem de dados como rodapé."""
    marcados = 0
    for elemento in elementos:
        if elemento["tipo"] == "marca_dagua":
            # As extrações antigas não guardavam o tipo anterior. Recuperar como
            # texto evita perder conteúdo; novas extrações também preservam notas.
            elemento["tipo"] = elemento.get("tipo_antes_marca_dagua", "texto")
        texto = elemento.get("texto", "")
        if elemento["tipo"] in ("texto", "nota") and len(texto) < 300:
            caixa = elemento.get("caixa") or {}
            altura = caixa.get("altura_pagina") or 0
            na_margem = altura > 0 and (
                caixa.get("y1", altura) <= altura * 0.08
                or caixa.get("y0", 0) >= altura * 0.92
            )
            carimbo_na_margem = (
                na_margem
                and re.match(r"^\s*downloaded from\b", texto, re.IGNORECASE)
                and ENDERECO_CARIMBO.search(texto)
            )
            if MARCA_DAGUA.search(texto) or carimbo_na_margem:
                elemento["tipo_antes_marca_dagua"] = elemento["tipo"]
                elemento["tipo"] = "marca_dagua"
                marcados += 1
    # Só fragmentos de data junto a um carimbo confirmado, na mesma página.
    # A mera proximidade não permite excluir uma frase curta do artigo.
    carimbos = [i for i, e in enumerate(elementos) if e["tipo"] == "marca_dagua"]
    for posicao, elemento in enumerate(elementos):
        texto = elemento.get("texto", "").strip()
        if (
            elemento["tipo"] == "texto"
            and len(texto) < 60
            and any(c.isdigit() for c in texto)
            and any(c.isalpha() for c in texto)
            and FRAGMENTO_DATA.fullmatch(texto)
            and any(
                abs(vizinho - posicao) <= 2
                and set(elementos[vizinho].get("paginas", [])) & set(elemento.get("paginas", []))
                for vizinho in carimbos
            )
        ):
            elemento["tipo_antes_marca_dagua"] = elemento["tipo"]
            elemento["tipo"] = "marca_dagua"
            marcados += 1
    return marcados


def _termina_aberto(texto: str) -> bool:
    final = texto.rstrip().rstrip("\"”')]")
    return bool(final) and final[-1] not in ".!?:;"


def _cabecalho_solto(elemento: dict) -> bool:
    """Cabeçalho curto e sem numeração: muitas vezes é o rótulo de uma figura."""
    texto = elemento.get("texto", "").strip()
    return elemento["tipo"] == "secao" and len(texto) <= 60 and not CABECALHO_NUMERADO.match(texto)


def juntar_paragrafos_entre_paginas(elementos: list[dict]) -> tuple[list[dict], int]:
    """Une o fim de um parágrafo com a continuação na página seguinte.

    Condições: o trecho termina sem pontuação final, a continuação começa com
    letra minúscula e está numa página posterior. Figuras, legendas, notas e
    rótulos soltos entre os dois pedaços são pulados (e continuam na lista).
    """
    resultado = list(elementos)
    unidos = 0
    i = 0
    while i < len(resultado):
        atual = resultado[i]
        texto_atual = atual.get("texto", "")
        if atual["tipo"] in ("texto", "lista") and len(texto_atual) >= 40 and _termina_aberto(texto_atual):
            j = i + 1
            while j < len(resultado) and j - i <= 5 and (
                resultado[j]["tipo"] in FLUTUANTES or _cabecalho_solto(resultado[j])
            ):
                j += 1
            if j < len(resultado):
                seguinte = resultado[j]
                texto_seguinte = seguinte.get("texto", "").lstrip()
                if (
                    seguinte["tipo"] == "texto"
                    and texto_seguinte[:1].islower()
                    and min(seguinte["paginas"]) > max(atual["paginas"])
                ):
                    resultado[i] = {
                        **atual,
                        "texto": _juntar(atual["texto"], texto_seguinte),
                        "paginas": sorted(set(atual["paginas"]) | set(seguinte["paginas"])),
                        "unido_com": atual.get("unido_com", []) + [seguinte["id"]],
                        "caixas": _todas_as_caixas(atual) + _todas_as_caixas(seguinte),
                    }
                    del resultado[j]
                    unidos += 1
                    continue  # o mesmo parágrafo pode seguir para mais uma página
        i += 1
    return resultado, unidos


def _todas_as_caixas(elemento: dict) -> list[dict]:
    if elemento.get("caixas"):
        return list(elemento["caixas"])
    return [elemento["caixa"]] if elemento.get("caixa") else []


def _juntar(inicio: str, continuacao: str) -> str:
    inicio = inicio.rstrip()
    if inicio.endswith("-") and inicio[-2:-1].isalpha():  # palavra hifenizada na quebra
        return inicio[:-1] + continuacao
    return f"{inicio} {continuacao}"


# ---------------------------------------------------------------- texto perdido


def _palavras(texto: str) -> list[str]:
    return re.findall(r"[^\W\d_]{4,}", texto.lower())


def _texto_dos_elementos(elemento: dict) -> str:
    partes = [elemento.get(chave) or "" for chave in ("texto", "legenda", "texto_interno", "texto_original")]
    partes += [" ".join(map(str, linha)) for linha in elemento.get("linhas") or []]
    partes += [" ".join(map(str, elemento.get("colunas") or []))]
    return " ".join(partes)


def completar_com_texto_do_pdf(elementos: list[dict], caminho_pdf: Path, limite: float = LIMITE_COBERTURA):
    """Compara cada página com a camada de texto do PDF.

    Páginas com cobertura abaixo do limite recebem um elemento "texto_pdf" com
    as linhas que não apareceram na extração (fora da estrutura do Docling).
    Páginas sem camada de texto (digitalizadas) são ignoradas.
    """
    import pypdfium2 as pdfium

    extraidas: dict[int, set[str]] = {}
    contagem_extraida: dict[int, Counter] = {}
    for elemento in elementos:
        palavras = _palavras(_texto_dos_elementos(elemento))
        for pagina in elemento["paginas"]:
            extraidas.setdefault(pagina, set()).update(palavras)
            contagem_extraida.setdefault(pagina, Counter()).update(palavras)

    documento = pdfium.PdfDocument(str(caminho_pdf))
    novos: dict[int, dict] = {}
    por_pagina, total_pdf, total_ok = {}, 0, 0
    try:
        for indice in range(len(documento)):
            pagina = indice + 1
            texto_pdf = documento[indice].get_textpage().get_text_range()
            contagem_pdf = Counter(_palavras(texto_pdf))
            soma = sum(contagem_pdf.values())
            if soma < 30:
                continue
            achadas = sum(min(n, contagem_extraida.get(pagina, Counter())[p]) for p, n in contagem_pdf.items())
            total_pdf, total_ok = total_pdf + soma, total_ok + achadas
            por_pagina[pagina] = round(achadas / soma, 3)
            if por_pagina[pagina] >= limite:
                continue
            faltando = []
            for linha in texto_pdf.splitlines():
                linha = re.sub(r"[\ufffd\ufffe\u00ad\x00-\x08]", "", linha).strip()
                palavras = _palavras(linha)
                if len(palavras) < 3 or MARCA_DAGUA.search(linha):
                    continue
                if sum(p in extraidas.get(pagina, set()) for p in palavras) / len(palavras) < 0.5:
                    faltando.append(linha)
            if faltando:
                novos[pagina] = {
                    "id": f"pdf-p{pagina:03d}",
                    "tipo": "texto_pdf",
                    "texto": "\n".join(faltando),
                    "secao": "",
                    "paginas": [pagina],
                    "caixa": None,
                }
    finally:
        documento.close()

    # Cada bloco recuperado entra depois do último elemento da sua página
    resultado = []
    for posicao, elemento in enumerate(elementos):
        resultado.append(elemento)
        pagina_atual = max(elemento["paginas"]) if elemento["paginas"] else None
        proxima = elementos[posicao + 1] if posicao + 1 < len(elementos) else None
        proxima_pagina = min(proxima["paginas"]) if proxima and proxima["paginas"] else None
        if pagina_atual in novos and proxima_pagina != pagina_atual:
            resultado.append(novos.pop(pagina_atual))
    resultado += [novos[p] for p in sorted(novos)]  # páginas sem nenhum elemento

    baixas = {p: c for p, c in por_pagina.items() if c < limite}
    info = {
        "total": round(total_ok / total_pdf, 3) if total_pdf else None,
        "paginas_baixas": baixas,
        "linhas_recuperadas": sum(e["texto"].count("\n") + 1 for e in resultado if e["tipo"] == "texto_pdf"),
    }
    return resultado, info


# ---------------------------------------------------------------- ordem em duas colunas


def _coluna(elemento: dict) -> str | None:
    """'esq', 'dir' ou 'larga' (ocupa as duas colunas), pela posição na página."""
    caixa = elemento.get("caixa")
    if not caixa or not caixa.get("largura_pagina"):
        return None
    largura = caixa["largura_pagina"]
    if caixa["x1"] <= largura * 0.55:
        return "esq"
    if caixa["x0"] >= largura * 0.45:
        return "dir"
    return "larga"


def _faixa(elemento: dict, largos: list[dict]) -> int:
    """Faixa horizontal da página: elementos largos separam as faixas."""
    return sum(1 for largo in largos if largo["caixa"]["y0"] <= elemento["caixa"]["y0"])


def _tem_colunas_invertidas(grupo: list[dict]) -> bool:
    """Coluna direita lida antes de um trecho da esquerda que está acima dela, na mesma faixa."""
    largos = [e for e in grupo if _coluna(e) == "larga"]
    vistos_direita = []
    for elemento in grupo:
        coluna = _coluna(elemento)
        if coluna == "dir":
            vistos_direita.append(elemento)
        elif coluna == "esq":
            faixa = _faixa(elemento, largos)
            for direita in vistos_direita:
                mesma_faixa = _faixa(direita, largos) == faixa
                if mesma_faixa and elemento["caixa"]["y0"] < direita["caixa"]["y0"]:
                    return True
    return False


def _ordenar_por_colunas(grupo: list[dict]) -> list[dict]:
    """Por faixa: elemento largo, depois coluna esquerda e coluna direita (de cima para baixo)."""
    largos = sorted((e for e in grupo if _coluna(e) == "larga"), key=lambda e: e["caixa"]["y0"])
    ordenados = []
    for faixa in range(len(largos) + 1):
        if faixa > 0:
            ordenados.append(largos[faixa - 1])
        for lado in ("esq", "dir"):
            da_faixa = [e for e in grupo if _coluna(e) == lado and _faixa(e, largos) == faixa]
            ordenados += sorted(da_faixa, key=lambda e: e["caixa"]["y0"])
    return ordenados


def corrigir_ordem_colunas(elementos: list[dict]) -> tuple[list[dict], list[int]]:
    """Corrige páginas de duas colunas lidas na ordem errada.

    Só mexe numa página quando detecta a inversão; as outras ficam com a ordem
    do Docling. Devolve os elementos e a lista de páginas reordenadas.
    """
    por_pagina: dict[int, list[dict]] = {}
    pagina_anterior = 0
    for elemento in elementos:
        caixa = elemento.get("caixa")
        pagina = caixa["pagina"] if caixa else pagina_anterior
        por_pagina.setdefault(pagina, []).append(elemento)
        pagina_anterior = pagina

    resultado, corrigidas = [], []
    for pagina in sorted(por_pagina):
        grupo = por_pagina[pagina]
        posicionaveis = all(_coluna(e) for e in grupo)
        if posicionaveis and _tem_colunas_invertidas(grupo):
            resultado += _ordenar_por_colunas(grupo)
            corrigidas.append(pagina)
        else:
            resultado += grupo
    return resultado, corrigidas


# ---------------------------------------------------------------- conferência visual


def caixas_na_pagina(elemento: dict, pagina: int, legenda: bool = False) -> list[dict]:
    """Caixas do elemento (ou da sua legenda) numa página."""
    if legenda:
        caixas = elemento.get("caixas_legenda") or []
    else:
        caixas = elemento.get("caixas") or ([elemento["caixa"]] if elemento.get("caixa") else [])
    return [c for c in caixas if c and c.get("pagina") == pagina]


def texto_fora_das_caixas(caminho_pdf: Path, pagina: int, caixas: list[dict], margem: float = 2.0) -> tuple[float, str]:
    """Parte do texto do PDF numa página que não cai em nenhuma caixa.

    Devolve (fração de caracteres fora, amostra desse texto). Serve para
    conferir se a extração deixou algum pedaço sem posição.
    """
    import pypdfium2 as pdfium

    documento = pdfium.PdfDocument(str(caminho_pdf))
    try:
        pagina_pdf = documento[pagina - 1]
        altura = pagina_pdf.get_height()
        texto = pagina_pdf.get_textpage()
        fora, total, amostra = 0, 0, []
        for indice in range(texto.count_chars()):
            caractere = texto.get_text_range(indice, 1)
            if not caractere.strip():
                continue
            esquerda, baixo, direita, cima = texto.get_charbox(indice)
            x, y = (esquerda + direita) / 2, altura - (baixo + cima) / 2  # centro, origem no topo
            total += 1
            dentro = any(
                c["x0"] - margem <= x <= c["x1"] + margem and c["y0"] - margem <= y <= c["y1"] + margem
                for c in caixas
            )
            if not dentro:
                fora += 1
                amostra.append(caractere)
    finally:
        documento.close()
    return (fora / total if total else 0.0), "".join(amostra)[:200]
