"""Leitura opcional do MinerU em outro Python, sem importar seus modelos no app.

O processo isolado usa somente Basic/ONNX local. As fórmulas reconhecidas são
alternativas para revisão; este módulo nunca troca a versão principal do usuário.
"""

import hashlib
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path

from explorador.formulas import limpar_saida_dolphin, normalizar_latex, separar_numero

PROTOCOLO_WORKER = 1
MODELO_MINERU = "PP-FormulaNet_plus-M (MinerU basic/onnx)"
WORKER = Path(__file__).resolve().parents[1] / "scripts" / "mineru_worker.py"
CONFIG_LEITURA = {"tier": "basic", "backend": "onnx", "ocr_mode": "auto", "device": "cpu"}


class ErroMinerU(RuntimeError):
    """Falha recuperável da leitura opcional, sem modificar leituras anteriores."""


def _log_curto(texto) -> str:
    if isinstance(texto, bytes):
        texto = texto.decode("utf-8", errors="replace")
    return "".join(c for c in str(texto or "") if c.isprintable() or c == "\n")[-1800:].strip()


def _versoes_instaladas(python: Path) -> dict[str, str]:
    # Resolver o symlink bin/python faria o intérprete perder o pyvenv.cfg.
    python = Path(python).expanduser().absolute()
    if not python.is_file():
        raise ErroMinerU("Python do MinerU não encontrado. Configure o ambiente separado .venv-mineru.")
    codigo = (
        "import json; from importlib.metadata import version; "
        "print(json.dumps({p: version(p) for p in ('mineru', 'docvortex')}))"
    )
    try:
        processo = subprocess.run(
            [str(python), "-I", "-c", codigo], capture_output=True, text=True,
            timeout=15, check=False, shell=False,
        )
    except subprocess.TimeoutExpired as erro:
        raise ErroMinerU("O Python do MinerU demorou demais para informar a instalação.") from erro
    except OSError as erro:
        raise ErroMinerU("Não foi possível executar o Python do ambiente MinerU.") from erro
    if processo.returncode:
        raise ErroMinerU("MinerU e DocVortex não estão disponíveis nesse Python. " + _log_curto(processo.stderr))
    try:
        versoes = json.loads(processo.stdout)
        if not isinstance(versoes, dict) or any(not isinstance(versoes.get(p), str) for p in ("mineru", "docvortex")):
            raise ValueError("versões ausentes")
        if versoes["mineru"].split(".")[0] != "4":
            raise ErroMinerU("Esta integração requer MinerU 4.x; versão encontrada: " + versoes["mineru"])
        return {p: versoes[p] for p in ("mineru", "docvortex")}
    except (ValueError, TypeError) as erro:
        raise ErroMinerU("O Python do MinerU devolveu informações de instalação inválidas.") from erro


def verificar_instalacao(python: Path) -> tuple[bool, str]:
    """Confere metadados dos pacotes; não importa modelos nem baixa pesos."""
    try:
        versoes = _versoes_instaladas(python)
        return True, f"MinerU {versoes['mineru']} · DocVortex {versoes['docvortex']} (ambiente separado)"
    except ErroMinerU as erro:
        return False, str(erro)


def _paginas_validas(paginas: list[int]) -> list[int]:
    if not isinstance(paginas, list) or any(type(p) is not int or p <= 0 for p in paginas):
        raise ErroMinerU("As páginas do MinerU devem ser números inteiros positivos, começando em 1.")
    return sorted(set(paginas))


def _hash_pdf(pdf: Path) -> str:
    digest = hashlib.sha256()
    with pdf.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _caixa_valida(valores) -> dict | None:
    if isinstance(valores, dict):
        valores = [valores.get(c) for c in ("x0", "y0", "x1", "y1")]
    if not isinstance(valores, (list, tuple)) or len(valores) != 4:
        return None
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in valores):
        return None
    x0, y0, x1, y1 = map(float, valores)
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        return None
    return dict(zip(("x0", "y0", "x1", "y1"), (x0, y0, x1, y1)))


def _extrair_formulas(documento: dict, paginas: list[int]) -> list[dict]:
    if not isinstance(documento, dict) or documento.get("schema") != "docvortex.middle" or documento.get("schema_version") != "2.0":
        raise ErroMinerU("Formato de saída incompatível: esperado DocVortex Middle JSON 2.0 do MinerU 4.x.")
    if not isinstance(documento.get("pages"), list):
        raise ErroMinerU("Saída do MinerU sem uma lista válida de páginas.")
    formulas, vistas, ids = [], set(), set()
    for pagina in documento["pages"]:
        if not isinstance(pagina, dict) or type(pagina.get("page_idx")) is not int or pagina["page_idx"] < 0:
            raise ErroMinerU("O MinerU devolveu uma página inválida.")
        numero = pagina["page_idx"] + 1
        if numero not in paginas:
            continue
        if numero in vistas or not isinstance(pagina.get("blocks"), list):
            raise ErroMinerU("O MinerU devolveu páginas repetidas ou blocos inválidos.")
        vistas.add(numero)
        for bloco in pagina["blocks"]:
            if not isinstance(bloco, dict):
                raise ErroMinerU("O MinerU devolveu um bloco inválido.")
            if bloco.get("type") != "equation":
                continue  # spans equation_inline não têm caixa própria para associação
            indice, latex = bloco.get("index"), bloco.get("content")
            caixa = _caixa_valida(bloco.get("bbox"))
            if type(indice) is not int or indice < 0 or not isinstance(latex, str) or caixa is None:
                raise ErroMinerU("O MinerU devolveu uma fórmula sem índice, LaTeX ou caixa normalizada válidos.")
            identificador = f"mineru-{pagina['page_idx']}-{indice}"
            if identificador in ids:
                raise ErroMinerU("O MinerU devolveu identificadores de fórmulas repetidos.")
            ids.add(identificador)
            if latex.strip():
                formulas.append({"id": identificador, "pagina": numero, "latex": latex,
                                 "caixa": caixa, "modelo": MODELO_MINERU})
    if vistas != set(paginas):
        raise ErroMinerU("O MinerU não devolveu todas as páginas solicitadas. Confira o intervalo escolhido.")
    return formulas


def _com_proveniencia(formulas: list[dict], versoes: dict[str, str]) -> list[dict]:
    """Cada alternativa continua identificável depois de sair do envelope/cache."""
    modelo = f"PP-FormulaNet_plus-M (MinerU {versoes['mineru']} basic/onnx)"
    return [{**formula, "modelo": modelo, "versao": versoes["mineru"],
             "docvortex": versoes["docvortex"]} for formula in formulas]


class LeitorMinerU:
    def __init__(self, python: Path, timeout: int, model_home: Path | None = None):
        if type(timeout) is not int or timeout <= 0:
            raise ValueError("O tempo limite do MinerU deve ser um inteiro positivo.")
        if model_home is None:
            from explorador import config

            model_home = config.MINERU_HOME
        self.python = Path(python).expanduser().absolute()
        self.timeout = timeout
        self.model_home = Path(model_home).expanduser().resolve()
        self.nome = MODELO_MINERU

    def _ambiente(self) -> dict[str, str]:
        # Não herdar configurações remotas do processo Streamlit ou de outro MinerU.
        ambiente = {k: v for k, v in os.environ.items() if not k.startswith("MINERU_")}
        ambiente.update(
            MINERU_HOME=str(self.model_home), MINERU_MODEL_SMALL_BACKEND="onnx",
            MINERU_TABLE_DEVICE="cpu", MINERU_DEVICE_MODE="cpu", MINERU_MODEL_SOURCE="local",
            MINERU_MODEL_VLM_SERVER_URL="", MINERU_LLM_AIDED_FEATURES_TITLE_LEVELING="false",
            MINERU_LLM_AIDED_FEATURES_CROSS_PAGE_TABLE_CELL_MERGE="false",
            HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
        )
        return ambiente

    def ler(self, pdf: Path, pasta_cache: Path, paginas: list[int], forcar: bool = False) -> dict:
        paginas = _paginas_validas(paginas)
        if not paginas:
            return {"formulas": [], "modelo": self.nome, "versao": "", "reaproveitado": False}
        pdf = Path(pdf).expanduser().resolve()
        if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
            raise ErroMinerU("Informe um PDF local existente para comparar as fórmulas com o MinerU.")
        versoes = _versoes_instaladas(self.python)
        try:
            hash_pdf = _hash_pdf(pdf)
            identidade = {"pdf_sha256": hash_pdf, "versoes": versoes, "config": CONFIG_LEITURA,
                          "paginas": paginas, "protocolo": PROTOCOLO_WORKER, "model_home": str(self.model_home)}
            assinatura = hashlib.sha256(json.dumps(identidade, sort_keys=True).encode()).hexdigest()
            pasta_cache = Path(pasta_cache).expanduser().resolve()
            pasta_cache.mkdir(parents=True, exist_ok=True)
            cache = pasta_cache / f"mineru-{assinatura}.json"
            if not forcar and cache.is_file():
                try:
                    salvo = json.loads(cache.read_text(encoding="utf-8"))
                    if salvo.get("identidade") == identidade:
                        formulas = _com_proveniencia(_extrair_formulas(salvo["documento"], paginas), versoes)
                        return {"formulas": formulas, "modelo": self.nome, "versao": versoes["mineru"],
                                "docvortex": versoes["docvortex"], "reaproveitado": True}
                except (ValueError, KeyError, TypeError, AttributeError, ErroMinerU):
                    pass  # cache incompleto/antigo nunca é tratado como uma leitura válida

            with tempfile.TemporaryDirectory(prefix=".mineru-", dir=pasta_cache) as temporaria:
                saida = Path(temporaria) / "middle.json"
                try:
                    processo = subprocess.run(
                        [str(self.python), "-I", str(WORKER), "--pdf", str(pdf), "--saida", str(saida),
                         "--paginas", ",".join(map(str, paginas))],
                        capture_output=True, text=True, timeout=self.timeout, check=False, shell=False,
                        env=self._ambiente(),
                    )
                except subprocess.TimeoutExpired as erro:
                    detalhe = _log_curto(erro.stderr or erro.stdout)
                    raise ErroMinerU(f"MinerU excedeu o limite de {self.timeout} segundos. " + detalhe) from erro
                except OSError as erro:
                    raise ErroMinerU("Não foi possível iniciar o processo separado do MinerU.") from erro
                if processo.returncode:
                    raise ErroMinerU("A leitura local do MinerU falhou. " + _log_curto(processo.stderr or processo.stdout))
                try:
                    documento = json.loads(saida.read_text(encoding="utf-8"))
                except (OSError, ValueError) as erro:
                    raise ErroMinerU("O MinerU terminou sem produzir um arquivo JSON válido.") from erro
                formulas = _com_proveniencia(_extrair_formulas(documento, paginas), versoes)
                if _hash_pdf(pdf) != hash_pdf:
                    raise ErroMinerU("O PDF mudou durante a leitura. Execute a comparação novamente.")
                # O arquivo anterior só é substituído depois de validar toda a saída.
                preparado = Path(temporaria) / "cache.json"
                preparado.write_text(json.dumps({"identidade": identidade, "documento": documento}, ensure_ascii=False), encoding="utf-8")
                os.replace(preparado, cache)
            return {"formulas": formulas, "modelo": self.nome, "versao": versoes["mineru"],
                    "docvortex": versoes["docvortex"], "reaproveitado": False}
        except OSError as erro:
            raise ErroMinerU("Não foi possível ler o PDF ou gravar o cache local do MinerU.") from erro


def _caixa_docling(elemento: dict) -> tuple[int | None, dict | None]:
    caixa = elemento.get("caixa") or {}
    pagina = caixa.get("pagina")
    if pagina is None and len(elemento.get("paginas", [])) == 1:
        pagina = elemento["paginas"][0]
    largura, altura = caixa.get("largura_pagina"), caixa.get("altura_pagina")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in (largura, altura)):
        return pagina, None
    try:
        valores = [caixa[c] / tamanho for c, tamanho in zip(("x0", "y0", "x1", "y1"), (largura, altura, largura, altura))]
    except (KeyError, TypeError):
        return pagina, None
    return pagina, _caixa_valida(valores)


def _sobreposicao(a: dict, b: dict) -> tuple[float, float, float]:
    intersecao = max(0.0, min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])) * max(0.0, min(a["y1"], b["y1"]) - max(a["y0"], b["y0"]))
    area_a = (a["x1"] - a["x0"]) * (a["y1"] - a["y0"])
    area_b = (b["x1"] - b["x0"]) * (b["y1"] - b["y0"])
    return intersecao / (area_a + area_b - intersecao), intersecao / min(area_a, area_b), max(area_a, area_b) / min(area_a, area_b)


def associar_formulas(elementos: list[dict], candidatas: list[dict], paginas: list[int]) -> dict:
    """Associa por geometria, exigindo correspondência única dos dois lados.

    Caixas Docling estão em pontos TOPLEFT e incluem dimensões da página; caixas
    MinerU estão em 0..1 TOPLEFT. Não compara texto nem depende da ordem das listas.
    Dúvidas de segmentação ficam para revisão, preservando leituras antigas.
    """
    selecionadas = set(_paginas_validas(paginas))
    relatorio = {"associadas": 0, "ambiguas": 0, "sem_correspondencia": 0, "nao_associadas": [], "detalhes": []}
    validas = {}
    for indice, candidata in enumerate(candidatas):
        if candidata.get("pagina") not in selecionadas:
            continue
        caixa, original = _caixa_valida(candidata.get("caixa")), candidata.get("latex")
        if caixa and isinstance(original, str) and original.strip():
            latex, numero = separar_numero(normalizar_latex(limpar_saida_dolphin(original)))
            if latex.strip():
                validas[indice] = {**candidata, "caixa": caixa, "limpo": latex, "numero": numero}

    alvos, opcoes, usos = {}, {}, {}
    for indice, elemento in enumerate(elementos):
        if elemento.get("tipo") != "formula":
            continue
        pagina, caixa = _caixa_docling(elemento)
        if pagina not in selecionadas and not selecionadas.intersection(elemento.get("paginas", [])):
            continue
        alvos[indice] = (elemento, pagina, caixa)
        opcoes[indice] = []
        if caixa is None:
            continue
        for chave, candidata in validas.items():
            if candidata["pagina"] != pagina:
                continue
            iou, cobertura, proporcao = _sobreposicao(caixa, candidata["caixa"])
            if iou >= 0.30 or (cobertura >= 0.75 and proporcao <= 3.0):
                opcoes[indice].append((chave, iou, cobertura))
                usos.setdefault(chave, []).append(indice)

    usadas = set()
    for indice, (elemento, pagina, caixa) in alvos.items():
        possiveis = opcoes[indice]
        detalhe = {"id": elemento.get("id"), "pagina": pagina,
                   "candidatas": [validas[c]["id"] for c, _, _ in possiveis]}
        if not possiveis:
            relatorio["sem_correspondencia"] += 1
            detalhe.update(situacao="sem_correspondencia", motivo="Sem caixa válida." if caixa is None else "Sem sobreposição suficiente.")
        elif len(possiveis) != 1 or len(usos[possiveis[0][0]]) != 1:
            relatorio["ambiguas"] += 1
            detalhe.update(situacao="ambigua", motivo="Mais de uma correspondência geométrica possível.")
        else:
            chave, iou, cobertura = possiveis[0]
            candidata = validas[chave]
            elemento.update(latex_mineru=candidata["limpo"], latex_mineru_original=candidata["latex"],
                            latex_mineru_modelo=candidata.get("modelo") or MODELO_MINERU,
                            latex_mineru_caixa=dict(candidata["caixa"]))
            usadas.add(chave)
            relatorio["associadas"] += 1
            detalhe.update(situacao="associada", mineru_id=candidata["id"], iou=round(iou, 4), cobertura=round(cobertura, 4))
        relatorio["detalhes"].append(detalhe)
    for indice, candidata in enumerate(candidatas):
        if candidata.get("pagina") in selecionadas and indice not in usadas:
            relatorio["nao_associadas"].append({"id": candidata.get("id"), "pagina": candidata["pagina"],
                                                "latex": candidata.get("latex", ""),
                                                "motivo": "Correspondência ambígua." if indice in usos else "Sem correspondência geométrica válida."})
    return relatorio
