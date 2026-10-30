"""Fórmulas: limpeza do LaTeX, leituras comparativas e escolha para o índice.

O Docling (modelo CodeFormula) faz a primeira leitura durante a extração. Aqui:

- o LaTeX é limpo ("A t t e n t i o n" vira "Attention", sem mudar o significado);
- o número da equação, como "(1)", é separado;
- cada fórmula é recortada do PDF (imagem para conferência);
- o Dolphin-1.5 (ByteDance, modelo local de 0,4B) lê o recorte de novo;
- leituras opcionais do MinerU também podem ser associadas à fórmula;
- todas as leituras disponíveis são comparadas. O estudante pode escolher uma
  versão; até a revisão, alternativas divergentes ficam identificadas no índice.

Campos de um elemento "formula" em elementos.json:
  latex           versão usada na tela e no índice
  latex_fonte     docling | dolphin | mineru | manual
  latex_revisado  escolha explícita do usuário, sem apagar as outras leituras
  latex_docling   leitura do Docling (limpa)
  latex_dolphin   leitura do Dolphin (limpa), se feita
  latex_mineru    leitura do MinerU (limpa), se feita
  concordancia    0 a 1, comparação legada Docling × Dolphin
  numero          número da equação, se houver
  imagem          recorte da fórmula (imagens/formula_NNN.png)
"""

import difflib
import re
from itertools import combinations
from pathlib import Path

MODELO_DOLPHIN = "ByteDance/Dolphin-1.5"
LIMITE_CONCORDANCIA = 0.97  # medido: erros de 1 palavra (d_model) ficam abaixo disso
VERSAO_PREPARACAO = 2  # 2: não confunde argumento numérico final com número da equação
FONTES_LEITURA = ("docling", "dolphin", "mineru")

COMANDOS_DE_TEXTO = {"\\text", "\\textrm", "\\textit", "\\textbf", "\\texttt", "\\textnormal", "\\mbox"}
TOKEN = re.compile(r"\\[a-zA-Z]+\*?|\\.|\s+|.", re.S)
# Espaços comuns são ignorados pelo LaTeX e também aparecem em argumentos,
# como O (1). Só alinhamento, espaço largo ou dois espaços escapados permitem
# destacar a numeração; o último formato também é emitido pelo Docling.
NUMERO_FINAL = re.compile(r"(?:&|\\q?quad|(?:\\ ){2,})(?:&|\\q?quad|\\[,; ]|~|\s)*\(\s*(\d+[a-z]?)\s*\)\s*$")
FINAL_VAZIO = re.compile(r"(\\\\|\\q?quad|\\[,;]|&|~|\s)+$")
OPERADORES = ("sin", "cos", "tan", "log", "exp", "max", "min", "arg", "lim", "sup", "inf")
TAG = re.compile(r"\\tag\*?\{\s*([^}]*)\}")


# ---------------------------------------------------------------- limpeza do LaTeX


def normalizar_latex(latex: str) -> str:
    """Remove os espaços que o reconhecedor põe entre símbolos.

    Em modo matemático esses espaços não mudam nada na fórmula, mas atrapalham a
    leitura e a busca. Mantém o espaço depois de comandos (\\cdot s ≠ \\cdots) e
    tudo o que está dentro de \\text{...}.
    """
    tokens = TOKEN.findall(latex.strip())
    saida: list[str] = []
    anterior = ""
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.isspace():
            i += 1
            continue
        precisa_espaco = anterior[:1] == "\\" and anterior[1:2].isalpha() and token[:1].isalpha()
        if token in COMANDOS_DE_TEXTO:
            j = i + 1
            while j < len(tokens) and tokens[j].isspace():
                j += 1
            if j < len(tokens) and tokens[j] == "{":
                fim = _fecha_chave(tokens, j)
                saida.append((" " if precisa_espaco else "") + token + "".join(tokens[j : fim + 1]))
                anterior, i = "}", fim + 1
                continue
        saida.append((" " if precisa_espaco else "") + token)
        anterior = token
        i += 1
    return "".join(saida)


def _fecha_chave(tokens: list[str], abertura: int) -> int:
    profundidade = 0
    for posicao in range(abertura, len(tokens)):
        if tokens[posicao] == "{":
            profundidade += 1
        elif tokens[posicao] == "}":
            profundidade -= 1
            if profundidade == 0:
                return posicao
    return len(tokens) - 1


def separar_numero(latex: str) -> tuple[str, str | None]:
    """Destaca numeração explícita; preserva finais ambíguos como f(3) e O(1)."""
    latex = FINAL_VAZIO.sub("", latex)
    tag = TAG.search(latex)
    if tag:
        return TAG.sub("", latex).strip(), tag.group(1).strip()
    encontrado = NUMERO_FINAL.search(latex)
    if encontrado and encontrado.start() > 0:
        return FINAL_VAZIO.sub("", latex[: encontrado.start()]), encontrado.group(1)
    return latex, None


def limpar_saida_dolphin(texto: str) -> str:
    """Tira delimitadores ($$, \\[ \\]) e corrige '\\quadx' -> '\\quad x'."""
    texto = texto.strip()
    texto = re.sub(r"^\$\$|\$\$$|^\\\[|\\\]$", "", texto).strip()
    return re.sub(r"\\(q?quad)(?=[A-Za-z])", r"\\\1 ", texto)


def forma_canonica(latex: str) -> str:
    """Versão sem formatação, só para comparar duas leituras."""
    texto = re.sub(r"\\(begin|end)\{[a-z*]+\}", "", latex)
    texto = re.sub(r"\\(mathrm|text|operatorname\*?|mathit|mathbf|displaystyle|left|right|qquad|quad)", "", texto)
    texto = re.sub(r"\\[,;!: ]|~|&|\\\\", "", texto)
    for antes, depois in [(r"\_", "_"), (r"\ldots", "..."), (r"\dots", "..."), (r"\cdots", "..."), (r"\mid", "|")]:
        texto = texto.replace(antes, depois)
    texto = re.sub(r"\\(" + "|".join(OPERADORES) + r")(?![a-zA-Z])", r"\1", texto)
    return re.sub(r"[\s{}]", "", texto).rstrip(".,;")


def concordancia(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return round(difflib.SequenceMatcher(None, forma_canonica(a), forma_canonica(b)).ratio(), 3)


def latex_valido(latex: str) -> bool:
    """Confere se o LaTeX pode ser interpretado (conversão para MathML)."""
    if not latex.strip():
        return False
    import latex2mathml.converter

    try:
        latex2mathml.converter.convert(latex)
        return True
    except Exception:
        return False


def preparar_formulas(elementos: list[dict]) -> None:
    """Limpa ou migra a leitura original; mantém a versão escolhida pelo usuário."""
    for elemento in elementos:
        if elemento["tipo"] != "formula" or elemento.get("versao_preparacao", 0) >= VERSAO_PREPARACAO:
            continue
        antiga = "latex_docling" in elemento
        bruto = elemento.get("texto") if antiga else elemento.get("latex", "")
        if antiga and not bruto:
            continue  # sem leitura original, não é possível desfazer uma limpeza antiga
        latex, numero = separar_numero(normalizar_latex(bruto or ""))
        elemento["latex_docling"] = latex
        elemento["numero"] = numero
        if elemento.get("latex_fonte", "docling") == "docling" and not elemento.get("latex_revisado"):
            elemento["latex"] = latex
            elemento["latex_fonte"] = "docling"
        if elemento.get("latex_dolphin"):
            elemento["concordancia"] = concordancia(latex, elemento["latex_dolphin"])
        elemento["versao_preparacao"] = VERSAO_PREPARACAO


def leituras_por_fonte(elemento: dict) -> dict[str, str]:
    """Leituras não vazias de cada extrator, sem substituir escolhas ou dados salvos."""
    leituras = {
        fonte: elemento[f"latex_{fonte}"].strip()
        for fonte in FONTES_LEITURA
        if (elemento.get(f"latex_{fonte}") or "").strip()
    }
    # Compatibilidade com elementos antigos que tinham apenas latex/latex_fonte.
    fonte = elemento.get("latex_fonte", "docling")
    principal = (elemento.get("latex") or "").strip()
    if fonte in FONTES_LEITURA and principal and fonte not in leituras:
        leituras[fonte] = principal
    return {fonte: leituras[fonte] for fonte in FONTES_LEITURA if fonte in leituras}


def comparar_leituras(elemento: dict) -> dict[str, float]:
    """Similaridade de todos os pares presentes; chaves como 'docling_mineru'.

    Zero ou uma leitura produzem {}, pois não existe uma comparação disponível.
    A similaridade mede transcrição, não garante a correção matemática.
    """
    leituras = leituras_por_fonte(elemento)
    return {
        f"{a}_{b}": concordancia(leituras[a], leituras[b])
        for a, b in combinations(leituras, 2)
    }


def tem_divergencia(elemento: dict) -> bool:
    """Qualquer par de extratores pode divergir, mesmo após uma escolha manual."""
    return any(nota < LIMITE_CONCORDANCIA for nota in comparar_leituras(elemento).values())


def versoes(elemento: dict) -> list[str]:
    """Principal escolhida ou, sem revisão, todas as leituras distintas em conflito."""
    principal = (elemento.get("latex") or "").strip()
    if elemento.get("latex_revisado") or elemento.get("latex_fonte") == "manual":
        return [principal] if principal else []

    leituras = leituras_por_fonte(elemento)
    principal = principal or next(iter(leituras.values()), "")
    if not principal:
        return []
    if not tem_divergencia(elemento):
        return [principal]

    # A relação de similaridade não é transitiva. Com conflito, deduplicar só
    # formas canônicas iguais evita esconder um par divergente por aproximação.
    resultado, vistas = [], set()
    for leitura in (principal, *leituras.values()):
        canonica = forma_canonica(leitura)
        if canonica not in vistas:
            resultado.append(leitura)
            vistas.add(canonica)
    return resultado


def divergentes(elementos: list[dict]) -> list[dict]:
    return [e for e in elementos if e["tipo"] == "formula" and len(versoes(e)) > 1]


# ---------------------------------------------------------------- recorte e segunda leitura


def recortar(caminho_pdf: Path, caixa: dict, escala: float = 3.0, margem: float = 4.0):
    """Imagem (PIL) da região da fórmula no PDF."""
    import pypdfium2 as pdfium

    documento = pdfium.PdfDocument(str(caminho_pdf))
    try:
        pagina = documento[caixa["pagina"] - 1].render(scale=escala).to_pil()
    finally:
        documento.close()
    return pagina.crop(
        (
            max(0, (caixa["x0"] - margem) * escala),
            max(0, (caixa["y0"] - margem) * escala),
            min(pagina.width, (caixa["x1"] + margem) * escala),
            min(pagina.height, (caixa["y1"] + margem) * escala),
        )
    ).convert("RGB")


class LeitorDolphin:
    """Dolphin-1.5 (encoder Swin + decoder MBart), carregado só no primeiro uso."""

    PROMPT = "<s>Read formula in the image. <Answer/>"

    def __init__(self, nome_modelo: str = MODELO_DOLPHIN):
        self.nome = nome_modelo
        self._modelo = None
        self._processador = None

    def _carregar(self) -> None:
        from transformers import AutoProcessor, VisionEncoderDecoderModel

        self._processador = AutoProcessor.from_pretrained(self.nome)
        # Os pesos vêm em float16; float32 roda em qualquer CPU
        self._modelo = VisionEncoderDecoderModel.from_pretrained(self.nome).float().eval()

    def ler(self, imagem) -> str:
        import torch

        if self._modelo is None:
            self._carregar()
        tokenizer = self._processador.tokenizer
        pixels = self._processador(imagem, return_tensors="pt").pixel_values
        prompt = tokenizer([self.PROMPT], add_special_tokens=False, return_tensors="pt")
        with torch.no_grad():
            saida = self._modelo.generate(
                pixel_values=pixels,
                decoder_input_ids=prompt.input_ids,
                decoder_attention_mask=prompt.attention_mask,
                max_length=1024,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
                bad_words_ids=[[tokenizer.unk_token_id]],
                do_sample=False,
                num_beams=1,
                repetition_penalty=1.1,
            )
        texto = tokenizer.batch_decode(saida, skip_special_tokens=False)[0]
        for marca in (self.PROMPT, "<pad>", "</s>", "<s>"):
            texto = texto.replace(marca, "")
        return texto.strip()


def reler_formulas(elementos: list[dict], caminho_pdf: Path, pasta: Path, leitor=None, forcar: bool = False) -> dict:
    """Recorta cada fórmula e, com um leitor, faz a segunda leitura.

    Se a leitura do Docling não é LaTeX válido e a do Dolphin é, a do Dolphin
    passa a ser a principal. Escolhas manuais nunca são trocadas.
    """
    preparar_formulas(elementos)
    pasta_imagens = Path(pasta) / "imagens"
    pasta_imagens.mkdir(parents=True, exist_ok=True)
    lidas = trocadas = 0
    for numero, elemento in enumerate(e for e in elementos if e["tipo"] == "formula"):
        if not elemento.get("caixa"):
            continue
        nome = f"imagens/formula_{numero + 1:03d}.png"
        if forcar or not (Path(pasta) / nome).exists():
            recortar(caminho_pdf, elemento["caixa"]).save(Path(pasta) / nome)
        elemento["imagem"] = nome
        if leitor is None or ("latex_dolphin" in elemento and not forcar):
            continue

        from PIL import Image

        bruto = leitor.ler(Image.open(Path(pasta) / nome))
        elemento["latex_dolphin_original"] = bruto
        lido, _ = separar_numero(normalizar_latex(limpar_saida_dolphin(bruto)))
        elemento["latex_dolphin"] = lido
        elemento["concordancia"] = concordancia(elemento["latex_docling"], lido)
        lidas += 1
        if (
            elemento.get("latex_fonte") == "docling"
            and not elemento.get("latex_revisado")
            and not latex_valido(elemento["latex_docling"])
            and latex_valido(lido)
        ):
            elemento["latex"], elemento["latex_fonte"] = lido, "dolphin"
            trocadas += 1
    return {
        "modelo": getattr(leitor, "nome", None),
        "lidas": lidas,
        "trocadas_por_invalidas": trocadas,
        "divergentes": len(divergentes(elementos)),
    }
