"""Extração de PDFs com Docling.

Este é o único módulo que conhece o Docling. Ele salva, na pasta de cada
artigo:

- documento.json  -> DoclingDocument completo (estrutura, posições, tabelas)
- documento.md    -> versão Markdown para inspeção rápida
- imagens/        -> figuras recortadas do PDF (PNG)
- elementos.json  -> lista simples de elementos na ordem de leitura,
                     usada pela inspeção e pela divisão em trechos
- manifesto.json  -> versão do extrator, configuração, status e alertas

O restante do app trabalha só com elementos.json e manifesto.json.
"""

import hashlib
import json
import math
import re
import shutil
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

from explorador.formulas import divergentes
from explorador.pos_processamento import (  # noqa: F401 (reexportadas)
    atribuir_secoes,
    corrigir_ordem_colunas,
    detectar_titulo,
    marcar_titulo,
    pos_processar,
)

# Muda quando o formato de elementos.json mudar (força reprocessamento)
VERSAO_FORMATO = 1

MAPA_STATUS = {
    "success": "concluída",
    "partial_success": "parcial",
    "failure": "falhou",
    "skipped": "falhou",
}

TIPOS_POR_ROTULO = {
    "title": "titulo",
    "section_header": "secao",
    "text": "texto",
    "paragraph": "texto",
    "handwritten_text": "texto",
    "checkbox_selected": "texto",
    "checkbox_unselected": "texto",
    "list_item": "lista",
    "caption": "legenda",
    "footnote": "nota",
    "reference": "referencia",
    "formula": "formula",
    "code": "codigo",
    "table": "tabela",
    "document_index": "tabela",
    "picture": "figura",
    "chart": "figura",
}

PADRAO_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.IGNORECASE)


@dataclass(frozen=True)
class ConfigExtracao:
    ocr: str = "auto"  # auto | desligado | pagina_inteira
    formulas: bool = True  # do_formula_enrichment (LaTeX)
    tabelas_precisas: bool = True  # TableFormer em modo ACCURATE
    escala_imagens: float = 2.0  # resolução das figuras salvas
    corrigir_colunas: bool = True  # corrige páginas de 2 colunas lidas fora de ordem

    def descricao(self) -> dict:
        return {
            **asdict(self),
            "extrator": "docling",
            "versao_extrator": versao_docling(),
            "formato_elementos": VERSAO_FORMATO,
        }

    def assinatura(self) -> str:
        texto = json.dumps(self.descricao(), sort_keys=True)
        return hashlib.sha256(texto.encode()).hexdigest()[:12]


def versao_docling() -> str:
    return version("docling")


def criar_conversor(config: ConfigExtracao):
    """Monta o DocumentConverter. Na primeira execução o Docling baixa os modelos."""
    # Importação tardia: carregar o Docling (e o PyTorch) é lento, e as telas de
    # catálogo e inspeção não precisam dele.
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        OcrAutoOptions,
        OcrMode,
        PdfPipelineOptions,
        TableFormerMode,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opcoes = PdfPipelineOptions()
    # OCR "auto": só nas regiões da página que não têm camada de texto no PDF.
    opcoes.do_ocr = config.ocr != "desligado"
    if config.ocr == "pagina_inteira":
        opcoes.ocr_options = OcrAutoOptions(mode=OcrMode.FULL_PAGE)
    opcoes.do_table_structure = True
    opcoes.table_structure_options.do_cell_matching = True
    opcoes.table_structure_options.mode = (
        TableFormerMode.ACCURATE if config.tabelas_precisas else TableFormerMode.FAST
    )
    opcoes.do_formula_enrichment = config.formulas
    opcoes.generate_picture_images = True
    opcoes.images_scale = config.escala_imagens

    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opcoes)}
    )


def carregar_manifesto(pasta: Path) -> dict | None:
    caminho = Path(pasta) / "manifesto.json"
    if not caminho.exists():
        return None
    return json.loads(caminho.read_text(encoding="utf-8"))


def carregar_elementos(pasta: Path) -> list[dict]:
    caminho = Path(pasta) / "elementos.json"
    if not caminho.exists():
        return []
    return json.loads(caminho.read_text(encoding="utf-8"))


def extracao_valida(manifesto: dict | None, config: ConfigExtracao) -> bool:
    """Uma extração em disco pode ser reaproveitada se usou a mesma configuração."""
    return (
        manifesto is not None
        and manifesto.get("assinatura") == config.assinatura()
        and manifesto.get("status") in ("concluída", "parcial")
    )


def extrair_pdf(
    caminho_pdf: Path,
    pasta_saida: Path,
    config: ConfigExtracao,
    conversor=None,
    forcar: bool = False,
) -> dict:
    """Converte o PDF e grava os arquivos de saída. Devolve o manifesto.

    Se já existe uma extração válida com a mesma configuração, ela é
    reaproveitada (a menos que forcar=True).
    """
    caminho_pdf, pasta_saida = Path(caminho_pdf), Path(pasta_saida)
    anterior = carregar_manifesto(pasta_saida)
    if not forcar and extracao_valida(anterior, config):
        return {**anterior, "reaproveitado": True}

    if pasta_saida.exists():
        shutil.rmtree(pasta_saida)
    pasta_imagens = pasta_saida / "imagens"
    pasta_imagens.mkdir(parents=True)

    inicio = time.time()
    manifesto = {
        "arquivo_pdf": caminho_pdf.name,
        "config": config.descricao(),
        "assinatura": config.assinatura(),
        "inicio": datetime.now().isoformat(timespec="seconds"),
        "paginas": 0,
        "erros": [],
        "confianca": {},
        "pos_processamento": {},
    }
    elementos: list[dict] = []

    try:
        conversor = conversor or criar_conversor(config)
        resultado = conversor.convert(caminho_pdf, raises_on_error=False)
        status = MAPA_STATUS.get(resultado.status.value, "falhou")
        manifesto["erros"] = [
            f"{erro.component_type}: {erro.error_message}" for erro in resultado.errors
        ]
        documento = resultado.document
        manifesto["paginas"] = len(documento.pages)
        manifesto["confianca"] = _resumir_confianca(resultado.confidence)

        if status != "falhou":
            from docling_core.types.doc import ImageRefMode

            elementos, manifesto["pos_processamento"] = pos_processar(
                converter_elementos(documento, pasta_imagens), caminho_pdf, config.corrigir_colunas
            )
            manifesto["mobilia"] = _mobilia(documento)
            # As figuras já estão em imagens/; no JSON e no Markdown ficam como marcador.
            documento.save_as_json(
                pasta_saida / "documento.json", image_mode=ImageRefMode.PLACEHOLDER
            )
            documento.save_as_markdown(
                pasta_saida / "documento.md",
                image_mode=ImageRefMode.PLACEHOLDER,
                page_break_placeholder="\n\n---\n\n",
            )
    except Exception as erro:  # o Docling pode falhar de várias formas em PDFs ruins
        status = "falhou"
        manifesto["erros"].append(f"{type(erro).__name__}: {erro}")

    if status != "falhou" and not elementos:
        status = "falhou"
        manifesto["erros"].append("Nenhum elemento de conteúdo foi reconhecido.")

    manifesto.update(
        status=status,
        fim=datetime.now().isoformat(timespec="seconds"),
        duracao_s=round(time.time() - inicio, 1),
        reaproveitado=False,
    )
    salvar_extracao(pasta_saida, elementos, manifesto)
    return manifesto


def salvar_extracao(pasta: Path, elementos: list[dict], manifesto: dict) -> dict:
    """Grava elementos e manifesto, recalculando contagens e alertas."""
    manifesto.update(
        contagens=contar_elementos(elementos),
        alertas=verificar_qualidade(elementos, manifesto),
        titulo_detectado=detectar_titulo(elementos),
        doi_detectado=detectar_doi(elementos),
    )
    _salvar_json(Path(pasta) / "elementos.json", elementos)
    _salvar_json(Path(pasta) / "manifesto.json", manifesto)
    return manifesto


def atualizar_sem_docling(caminho_pdf: Path, pasta: Path) -> dict | None:
    """Reaplica o pós-processamento numa extração existente (rápido, sem modelos)."""
    manifesto = carregar_manifesto(pasta)
    if manifesto is None or manifesto.get("status") == "falhou":
        return manifesto
    corrigir = manifesto.get("config", {}).get("corrigir_colunas", True)
    elementos = carregar_elementos(pasta)
    completar_caixas(elementos, pasta, manifesto)
    elementos, manifesto["pos_processamento"] = pos_processar(elementos, caminho_pdf, corrigir)
    return salvar_extracao(pasta, elementos, manifesto)


def precisa_atualizar(manifesto: dict | None) -> bool:
    from explorador.pos_processamento import VERSAO_POS

    return bool(manifesto) and manifesto.get("status") != "falhou" and (
        manifesto.get("pos_processamento", {}).get("versao", 1) < VERSAO_POS
    )


def _itens_mantidos(documento):
    """(item, tipo) na ordem de leitura do Docling, já filtrados.

    A posição nesta sequência vira o id (e0000, e0001...). Por isso o mesmo
    filtro serve para recuperar as caixas de uma extração antiga.
    """
    from docling_core.types.doc import PictureItem, TableItem

    # Legendas e notas presas a tabelas/figuras não viram elementos soltos.
    refs_anexadas = set()
    for item, _ in documento.iterate_items():
        if isinstance(item, (TableItem, PictureItem)):
            refs_anexadas.update(ref.cref for ref in item.captions)
            refs_anexadas.update(ref.cref for ref in item.footnotes)

    for item, _ in documento.iterate_items():
        tipo = TIPOS_POR_ROTULO.get(item.label.value)
        if tipo is None or item.self_ref in refs_anexadas:
            continue
        if tipo not in ("tabela", "figura") and not (getattr(item, "text", "") or "").strip():
            continue
        yield item, tipo


def converter_elementos(documento, pasta_imagens: Path) -> list[dict]:
    """Transforma o DoclingDocument numa lista simples, na ordem de leitura."""
    elementos = []
    for numero, (item, tipo) in enumerate(_itens_mantidos(documento)):
        caixas = _caixas(item, documento)
        elemento = {
            "id": f"e{numero:04d}",  # posição na ordem original do Docling
            "tipo": tipo,
            "texto": getattr(item, "text", "") or "",
            "secao": "",
            "paginas": sorted({prov.page_no for prov in item.prov}),
            "caixa": caixas[0] if caixas else None,  # primeira página (usada na ordem de colunas)
            "caixas": caixas,  # uma por página em que o elemento aparece
        }

        if tipo == "formula":
            # Com do_formula_enrichment, `text` recebe o LaTeX; `orig` guarda o texto do PDF.
            elemento["latex"] = elemento["texto"].strip()
            elemento["texto_original"] = getattr(item, "orig", "") or ""
        elif tipo == "tabela":
            elemento.update(_dados_tabela(item, documento))
        elif tipo == "figura":
            elemento.update(_dados_figura(item, documento, pasta_imagens))
        if tipo in ("tabela", "figura"):
            elemento["caixas_legenda"] = _caixas_legenda(item, documento)
        elementos.append(elemento)
    return elementos


def _caixas(item, documento) -> list[dict]:
    return [_caixa_da_prov(prov, documento) for prov in item.prov]


def _caixas_legenda(item, documento) -> list[dict]:
    caixas = []
    for ref in item.captions:
        try:
            caixas += _caixas(ref.resolve(documento), documento)
        except Exception:
            continue
    return caixas


def _mobilia(documento) -> dict[str, list[dict]]:
    """Cabeçalhos e rodapés de página (o Docling os separa e eles não entram no índice)."""
    from docling_core.types.doc import ContentLayer

    vistos, por_pagina = set(), {}
    for raiz in (None, documento.furniture):
        for item, _ in documento.iterate_items(root=raiz, included_content_layers={ContentLayer.FURNITURE}):
            if item.self_ref in vistos or not getattr(item, "prov", None):
                continue
            vistos.add(item.self_ref)
            for caixa in _caixas(item, documento):
                caixa["texto"] = (getattr(item, "text", "") or "")[:80]
                por_pagina.setdefault(str(caixa["pagina"]), []).append(caixa)
    return por_pagina


def caixas_do_documento(pasta: Path) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    """Recupera, do documento.json salvo, todas as caixas de cada elemento (sem rodar o Docling)."""
    from docling_core.types.doc import DoclingDocument

    documento = DoclingDocument.load_from_json(Path(pasta) / "documento.json")
    por_id = {}
    for numero, (item, tipo) in enumerate(_itens_mantidos(documento)):
        por_id[f"e{numero:04d}"] = {
            "caixas": _caixas(item, documento),
            "caixas_legenda": _caixas_legenda(item, documento) if tipo in ("tabela", "figura") else [],
        }
    return por_id, _mobilia(documento)


def completar_caixas(elementos: list[dict], pasta: Path, manifesto: dict) -> None:
    """Preenche 'caixas' (todas as páginas, inclusive partes unidas) em extrações antigas."""
    if not (Path(pasta) / "documento.json").exists():
        return
    por_id, mobilia = caixas_do_documento(pasta)
    for elemento in elementos:
        origem = por_id.get(elemento["id"])
        if origem is None or elemento["tipo"] == "texto_pdf":
            continue
        caixas = list(origem["caixas"])
        for parte in elemento.get("unido_com", []):
            caixas += por_id.get(parte, {}).get("caixas", [])
        elemento["caixas"] = caixas
        if origem["caixas_legenda"]:
            elemento["caixas_legenda"] = origem["caixas_legenda"]
    manifesto["mobilia"] = mobilia


def _caixa_da_prov(prov, documento) -> dict:
    """Posição numa página, com origem no canto superior esquerdo."""
    pagina = documento.pages.get(prov.page_no)
    caixa = prov.bbox
    if pagina is not None:
        caixa = caixa.to_top_left_origin(page_height=pagina.size.height)
    return {
        "pagina": prov.page_no,
        "x0": round(caixa.l, 1),
        "y0": round(caixa.t, 1),
        "x1": round(caixa.r, 1),
        "y1": round(caixa.b, 1),
        "largura_pagina": round(pagina.size.width, 1) if pagina else None,
        "altura_pagina": round(pagina.size.height, 1) if pagina else None,
    }


def _dados_tabela(item, documento) -> dict:
    dados = {
        "legenda": item.caption_text(documento),
        "colunas": [],
        "linhas": [],
        "markdown": "",
    }
    try:
        tabela = item.export_to_dataframe(documento)
        dados["colunas"] = [str(coluna) for coluna in tabela.columns]
        dados["linhas"] = tabela.fillna("").astype(str).values.tolist()
        dados["markdown"] = item.export_to_markdown(documento)
    except Exception as erro:
        dados["erro"] = f"Não foi possível exportar a tabela: {erro}"
    return dados


def _dados_figura(item, documento, pasta_imagens: Path) -> dict:
    dados = {"legenda": item.caption_text(documento), "imagem": None, "texto_interno": ""}

    imagem = item.get_image(documento)
    if imagem is not None:
        nome = f"figura_{len(list(pasta_imagens.glob('*.png'))) + 1:03d}.png"
        imagem.save(pasta_imagens / nome)
        dados["imagem"] = f"imagens/{nome}"

    # Texto reconhecido dentro da figura (rótulos de eixos, caixas de diagrama)
    textos = [
        filho.text
        for filho, _ in documento.iterate_items(root=item, traverse_pictures=True)
        if filho is not item and getattr(filho, "text", "")
        and filho.self_ref not in {ref.cref for ref in item.captions}
    ]
    dados["texto_interno"] = " ".join(textos)[:600]
    return dados


def _resumir_confianca(confianca) -> dict:
    """Notas de confiança estimadas pelo próprio Docling (não é verificação humana)."""

    def nota(valor) -> str:
        return getattr(valor, "value", str(valor))

    try:
        paginas_fracas = [
            numero
            for numero, pagina in sorted(confianca.pages.items())
            if nota(pagina.low_grade) in ("poor", "fair")
        ]
        media = float(confianca.mean_score)
        return {
            "nota_media": nota(confianca.mean_grade),
            "pontuacao_media": None if math.isnan(media) else round(media, 3),
            "paginas_baixa_confianca": paginas_fracas,
        }
    except Exception:
        return {}


def contar_elementos(elementos: list[dict]) -> dict:
    contagem: dict[str, int] = {}
    for elemento in elementos:
        contagem[elemento["tipo"]] = contagem.get(elemento["tipo"], 0) + 1
    contagem["caracteres"] = sum(len(e.get("texto", "")) for e in elementos)
    return contagem


def verificar_qualidade(elementos: list[dict], manifesto: dict) -> list[str]:
    """Sinais de extração incompleta. Conversão sem erro não garante qualidade."""
    alertas = []
    caracteres = sum(len(e.get("texto", "")) for e in elementos)
    if elementos and caracteres < 500:
        alertas.append(
            "Pouco texto extraído (menos de 500 caracteres). O PDF pode ser "
            "digitalizado: tente reprocessar com OCR de página inteira."
        )

    total_paginas = manifesto.get("paginas") or 0
    com_conteudo = {pagina for e in elementos for pagina in e["paginas"]}
    vazias = [p for p in range(1, total_paginas + 1) if p not in com_conteudo]
    if elementos and vazias:
        alertas.append(f"Páginas sem conteúdo reconhecido: {formatar_paginas(vazias)}.")

    pos = manifesto.get("pos_processamento", {})
    reordenadas = pos.get("paginas_reordenadas", manifesto.get("paginas_reordenadas", []))
    if reordenadas:
        alertas.append(
            "Ordem de leitura corrigida por heurística de duas colunas nas páginas "
            f"{formatar_paginas(reordenadas)}. Confira o texto na inspeção."
        )

    if pos.get("paragrafos_unidos"):
        alertas.append(
            f"{pos['paragrafos_unidos']} parágrafo(s) que continuavam na página seguinte foram unidos."
        )
    cobertura = pos.get("cobertura") or {}
    if cobertura.get("paginas_baixas"):
        paginas = [int(p) for p in cobertura["paginas_baixas"]]
        alertas.append(
            f"Parte do texto do PDF não apareceu na extração (páginas {formatar_paginas(paginas)}); "
            f"{cobertura.get('linhas_recuperadas', 0)} linha(s) foram recuperadas da camada de texto do PDF."
        )

    fracas = manifesto.get("confianca", {}).get("paginas_baixa_confianca", [])
    if fracas:
        alertas.append(
            f"O Docling estimou confiança baixa nas páginas {formatar_paginas(fracas)}."
        )

    formulas = [e for e in elementos if e["tipo"] == "formula"]
    usou_formulas = manifesto.get("config", {}).get("formulas", True)
    if formulas and not usou_formulas:
        alertas.append(
            f"{len(formulas)} fórmula(s) detectada(s) com o reconhecimento LaTeX "
            "desligado: ficou apenas o texto bruto do PDF."
        )
    elif usou_formulas:
        sem_latex = sum(1 for e in formulas if not e.get("latex"))
        if sem_latex:
            alertas.append(f"{sem_latex} fórmula(s) sem LaTeX reconhecido.")
    if divergentes(elementos):
        alertas.append(
            f"{len(divergentes(elementos))} fórmula(s) com leituras diferentes entre os leitores disponíveis: "
            "confira na aba Fórmulas."
        )

    figuras = [e for e in elementos if e["tipo"] == "figura"]
    sem_legenda = sum(1 for e in figuras if not e.get("legenda"))
    if sem_legenda:
        alertas.append(f"{sem_legenda} de {len(figuras)} figura(s) sem legenda encontrada.")

    tabelas_vazias = sum(1 for e in elementos if e["tipo"] == "tabela" and not e.get("linhas"))
    if tabelas_vazias:
        alertas.append(f"{tabelas_vazias} tabela(s) sem células reconhecidas.")

    if manifesto.get("erros"):
        alertas.append(f"O extrator registrou {len(manifesto['erros'])} erro(s).")
    return alertas


def avaliar_para_indexacao(manifesto: dict | None) -> tuple[str, str]:
    """Decide se o artigo pode ir para o índice.

    Devolve ("ok" | "confirmar" | "bloqueado", motivo). "confirmar" exige que o
    usuário aceite explicitamente indexar um resultado parcial ou suspeito.
    """
    if manifesto is None:
        return "bloqueado", "O artigo ainda não foi extraído."
    if manifesto.get("status") == "falhou":
        return "bloqueado", "A extração falhou; não há conteúdo confiável para indexar."
    if manifesto.get("contagens", {}).get("caracteres", 0) < 200:
        return "bloqueado", "A extração está praticamente vazia."
    if manifesto.get("status") == "parcial":
        return "confirmar", "A extração foi parcial (algumas páginas falharam)."
    if any(a.startswith(("Pouco texto", "Páginas sem conteúdo")) for a in manifesto.get("alertas", [])):
        return "confirmar", "Há páginas sem conteúdo ou pouco texto extraído."
    return "ok", ""


def detectar_doi(elementos: list[dict]) -> str | None:
    """Procura um DOI escrito na primeira página. Não deduz nada além do texto."""
    for elemento in elementos:
        if 1 not in elemento["paginas"]:
            continue
        encontrado = PADRAO_DOI.search(elemento.get("texto", ""))
        if encontrado:
            return encontrado.group(1).rstrip(".,;)]}").lower()
    return None


def formatar_paginas(paginas: list[int]) -> str:
    """[1, 2, 3, 7] -> '1–3, 7'"""
    paginas = sorted(set(paginas))
    if not paginas:
        return ""
    faixas, inicio, anterior = [], paginas[0], paginas[0]
    for pagina in paginas[1:] + [None]:
        if pagina is not None and pagina == anterior + 1:
            anterior = pagina
            continue
        faixas.append(str(inicio) if inicio == anterior else f"{inicio}–{anterior}")
        if pagina is not None:
            inicio = anterior = pagina
    return ", ".join(faixas)


def _salvar_json(caminho: Path, dados) -> None:
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
