import pytest

from explorador.formulas import (
    LIMITE_CONCORDANCIA,
    comparar_leituras,
    concordancia,
    leituras_por_fonte,
    limpar_saida_dolphin,
    normalizar_latex,
    preparar_formulas,
    reler_formulas,
    separar_numero,
    tem_divergencia,
    versoes,
)
from explorador.trechos import texto_da_formula
from tests.pdfs_sinteticos import ARTIGO_RAG, gerar_artigo

DOCLING_ATTENTION = r"A t t e n t i o n ( Q , K , V ) = \text {softmax} ( \frac { Q K ^ { T } } { \sqrt { d _ { k } } } ) V & & ( 1 )"


def test_limpa_espacos_sem_mudar_a_formula():
    latex, numero = separar_numero(normalizar_latex(DOCLING_ATTENTION))
    assert latex == r"Attention(Q,K,V)=\text{softmax}(\frac{QK^{T}}{\sqrt{d_{k}}})V"
    assert numero == "1"


def test_mantem_espaco_depois_de_comando_e_dentro_de_texto():
    assert normalizar_latex(r"a \cdot s") == r"a\cdot s"  # \cdots seria outro símbolo
    assert normalizar_latex(r"\text {where head} _ { i }") == r"\text{where head}_{i}"


@pytest.mark.parametrize("latex", ["y=f(3)", "L=O(1)", "y=f (3)", "x=(1)", r"y=f\,(3)", r"y=f\ (3)"])
def test_argumento_numerico_final_e_preservado_no_indice(latex):
    formula = _formula(latex)
    preparar_formulas([formula])
    esperado = normalizar_latex(latex)
    assert formula["latex"] == esperado
    assert formula["numero"] is None
    assert texto_da_formula(formula) == f"$$ {esperado} $$"


@pytest.mark.parametrize("latex", [r"y=f(3)\quad(8)", r"y=f(3)&&(8)", r"y=f(3)\tag{8}", r"y=f(3)\ \ (8)"])
def test_separa_numero_explicito_sem_remover_argumento(latex):
    formula = _formula(latex)
    preparar_formulas([formula])
    assert formula["latex"] == "y=f(3)"
    assert formula["numero"] == "8"
    assert texto_da_formula(formula) == "Equação (8): $$ y=f(3) $$"


def test_numero_com_espacos_escapados_emitidos_pelo_docling():
    bruto = r"s ( q , d ) = w \cdot s _ { b m 2 5 } ( q , d ) + ( 1 - w ) \cdot s _ { d e n s e } ( q , d ) \ \ ( 1 )"
    formula = _formula(bruto)
    preparar_formulas([formula])
    assert formula["numero"] == "1"
    assert formula["latex"].endswith(r"s_{dense}(q,d)")
    assert texto_da_formula(formula).startswith("Equação (1): $$ s(q,d)=")


def test_migra_formula_antiga_usando_texto_original():
    formula = {
        **_formula("y=f(3)"),
        "latex": "y=f", "latex_docling": "y=f", "latex_fonte": "docling", "numero": "3",
    }
    preparar_formulas([formula])
    assert formula["latex"] == formula["latex_docling"] == "y=f(3)"
    assert formula["numero"] is None


@pytest.mark.parametrize("fonte", ["manual", "dolphin"])
def test_migracao_nao_substitui_versao_escolhida(fonte):
    formula = {
        **_formula("y=f(3)"),
        "latex": "y=g(3)", "latex_docling": "y=f", "latex_fonte": fonte, "numero": "3",
    }
    preparar_formulas([formula])
    assert formula["latex_docling"] == "y=f(3)"
    assert formula["latex"] == "y=g(3)" and formula["latex_fonte"] == fonte
    assert formula["numero"] is None


def test_limpa_saida_do_dolphin():
    bruto = r"$$x_{e}^{-} \equiv x_{i_{e}}^{-}, \quadx_{e}^{+} \equiv x_{i_{e}}^{+} .\quad(4)$$"
    latex, numero = separar_numero(normalizar_latex(limpar_saida_dolphin(bruto)))
    assert r"\quad x_{e}^{+}" in latex
    assert numero == "4"


def test_concordancia_detecta_erro_de_uma_palavra():
    certo = r"lrate=d_{model}^{-0.5}\cdot\min(step\_num^{-0.5},step\_num\cdot warmup\_steps^{-1.5})"
    errado = r"lrate=d_{\min odl}^{-0.5}\cdot\min(step_{-}nuam^{-0.5},step_{-}nuam\cdot warmup_{-}steps^{-1.5})"
    assert concordancia(certo, errado) < LIMITE_CONCORDANCIA
    formatacao_diferente = r"Attention(Q,K,V)=softmax\left(\frac{QK^{T}}{\sqrt{d_{k}}}\right)V"
    assert concordancia(r"Attention(Q,K,V)=\text{softmax}(\frac{QK^{T}}{\sqrt{d_{k}}})V", formatacao_diferente) >= LIMITE_CONCORDANCIA


def test_versoes_para_o_indice():
    formula = {"tipo": "formula", "latex": "a+b", "latex_docling": "a+b", "latex_fonte": "docling", "latex_dolphin": "a+c", "numero": "2"}
    assert versoes(formula) == ["a+b", "a+c"]
    texto = texto_da_formula(formula)
    assert texto.startswith("Equação (2): $$ a+b $$") and "leitura alternativa, não conferida" in texto

    formula["latex_dolphin"] = "a + b"
    assert versoes(formula) == ["a+b"]
    manual = {**formula, "latex": "a+b+c", "latex_fonte": "manual", "latex_dolphin": "x"}
    assert versoes(manual) == ["a+b+c"]


def test_tres_fontes_sao_comparadas_e_alternativas_sao_preservadas():
    formula = {
        **_formula("a+b"), "latex_fonte": "docling", "latex_docling": "a+b",
        "latex_dolphin": "a+c", "latex_mineru": "a+d",
    }
    anterior = formula.copy()
    assert leituras_por_fonte(formula) == {"docling": "a+b", "dolphin": "a+c", "mineru": "a+d"}
    assert set(comparar_leituras(formula)) == {"docling_dolphin", "docling_mineru", "dolphin_mineru"}
    assert tem_divergencia(formula)
    assert versoes(formula) == ["a+b", "a+c", "a+d"]
    assert formula == anterior


def test_duas_fontes_iguais_nao_ocultam_terceira_divergente():
    formula = {
        **_formula("a+b"), "latex_fonte": "docling", "latex_docling": "a+b",
        "latex_dolphin": "a + b", "latex_mineru": "a+c",
    }
    assert tem_divergencia(formula)
    assert versoes(formula) == ["a+b", "a+c"]
    formula["latex_mineru"] = "a+b"
    assert not tem_divergencia(formula)
    assert versoes(formula) == ["a+b"]


def test_comparacao_nao_assume_transitividade_da_similaridade():
    partes = [f"x_{i}" for i in range(20)]
    principal = "+".join(partes)
    dolphin = "+".join(["y_0", "y_1", *partes[2:]])
    mineru = "+".join([*partes[:-2], "z_18", "z_19"])
    formula = {
        **_formula(principal), "latex_fonte": "docling", "latex_docling": principal,
        "latex_dolphin": dolphin, "latex_mineru": mineru,
    }
    pares = comparar_leituras(formula)
    assert pares["docling_dolphin"] >= LIMITE_CONCORDANCIA
    assert pares["docling_mineru"] >= LIMITE_CONCORDANCIA
    assert pares["dolphin_mineru"] < LIMITE_CONCORDANCIA
    assert tem_divergencia(formula)
    assert versoes(formula) == [principal, dolphin, mineru]


@pytest.mark.parametrize("fonte", ["docling", "dolphin", "mineru"])
def test_uma_leitura_sem_alternativas_nao_tem_concordancia_medida(fonte):
    formula = {**_formula("a+b"), "latex_fonte": fonte, f"latex_{fonte}": "a+b"}
    assert leituras_por_fonte(formula) == {fonte: "a+b"}
    assert comparar_leituras(formula) == {}
    assert not tem_divergencia(formula)
    assert versoes(formula) == ["a+b"]


def test_campos_vazios_nao_sao_uma_leitura_alternativa():
    formula = {**_formula("a+b"), "latex_mineru": "  ", "latex_dolphin": None}
    assert leituras_por_fonte(formula) == {"docling": "a+b"}
    assert comparar_leituras(formula) == {}


def test_mineru_escolhido_limita_indice_sem_apagar_comparacoes():
    formula = {
        **_formula("a+d"), "latex_fonte": "mineru", "latex_revisado": True,
        "latex_docling": "a+b", "latex_dolphin": "a+c", "latex_mineru": "a+d",
    }
    anterior = formula.copy()
    assert versoes(formula) == ["a+d"]
    assert tem_divergencia(formula)
    assert len(leituras_por_fonte(formula)) == 3
    assert formula == anterior


def test_migracao_preserva_escolha_docling_revisada():
    formula = {
        **_formula("y=f(3)"), "latex": "y=f", "latex_docling": "y=f",
        "latex_fonte": "docling", "latex_revisado": True,
    }
    preparar_formulas([formula])
    assert formula["latex"] == "y=f"
    assert formula["latex_docling"] == "y=f(3)"
    assert versoes(formula) == ["y=f"]


class LeitorFalso:
    nome = "teste/leitor"

    def __init__(self, resposta):
        self.resposta = resposta
        self.chamadas = 0

    def ler(self, imagem):
        self.chamadas += 1
        assert imagem.size[0] > 10  # recebeu o recorte
        return self.resposta


def _formula(latex):
    caixa = {"pagina": 1, "x0": 60, "y0": 300, "x1": 290, "y1": 320, "largura_pagina": 595, "altura_pagina": 842}
    return {"id": "e9", "tipo": "formula", "texto": latex, "latex": latex, "secao": "", "paginas": [1], "caixa": caixa}


def test_segunda_leitura_recorta_compara_e_troca_leitura_invalida(tmp_path):
    pdf = tmp_path / "artigo.pdf"
    pdf.write_bytes(gerar_artigo(ARTIGO_RAG))
    elementos = [_formula(r"\frac{a}{")]  # LaTeX inválido (chave aberta)
    info = reler_formulas(elementos, pdf, tmp_path, LeitorFalso(r"$$\frac{a}{b}\quad(1)$$"))

    formula = elementos[0]
    assert (tmp_path / formula["imagem"]).exists()
    assert formula["latex_dolphin"] == r"\frac{a}{b}"
    assert formula["latex"] == r"\frac{a}{b}" and formula["latex_fonte"] == "dolphin"
    assert info["lidas"] == 1 and info["trocadas_por_invalidas"] == 1


def test_segunda_leitura_nao_desfaz_escolha_manual_nem_repete(tmp_path):
    pdf = tmp_path / "artigo.pdf"
    pdf.write_bytes(gerar_artigo(ARTIGO_RAG))
    elementos = [_formula("x")]
    preparar_formulas(elementos)
    elementos[0].update(latex="x^2", latex_fonte="manual")
    leitor = LeitorFalso("y")
    reler_formulas(elementos, pdf, tmp_path, leitor)
    reler_formulas(elementos, pdf, tmp_path, leitor)
    assert elementos[0]["latex"] == "x^2" and elementos[0]["latex_fonte"] == "manual"
    assert leitor.chamadas == 1  # não relê o que já foi lido


def test_segunda_leitura_preserva_argumento_numerico(tmp_path):
    pdf = tmp_path / "artigo.pdf"
    pdf.write_bytes(gerar_artigo(ARTIGO_RAG))
    elementos = [_formula("L=O(1)")]
    reler_formulas(elementos, pdf, tmp_path, LeitorFalso("$$L=O(1)$$"))
    assert elementos[0]["latex_dolphin"] == "L=O(1)"
    assert elementos[0]["latex_dolphin_original"] == "$$L=O(1)$$"
    assert elementos[0]["numero"] is None
    assert versoes(elementos[0]) == ["L=O(1)"]


def test_segunda_leitura_nao_troca_docling_revisado_mesmo_se_invalido(tmp_path):
    pdf = tmp_path / "artigo.pdf"
    pdf.write_bytes(gerar_artigo(ARTIGO_RAG))
    formula = {**_formula(r"\frac{a}{"), "latex_fonte": "docling", "latex_revisado": True}
    info = reler_formulas([formula], pdf, tmp_path, LeitorFalso(r"$$\frac{a}{b}$$"))
    assert formula["latex"] == r"\frac{a}{"
    assert formula["latex_fonte"] == "docling"
    assert formula["latex_dolphin"] == r"\frac{a}{b}"
    assert info["trocadas_por_invalidas"] == 0
