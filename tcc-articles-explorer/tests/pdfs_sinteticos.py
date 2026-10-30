"""Gera PDFs sintéticos (artigos fictícios) para testes e avaliação.

Os artigos são inventados e servem só para conferir o pipeline: duas colunas,
seções, tabela, fórmula numerada, figura com legenda e referências, com fatos
conhecidos (para perguntas com resposta certa). Não substituem artigos reais.

    python tests/pdfs_sinteticos.py pasta_destino/
"""

import io
import sys
from pathlib import Path

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    FrameBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ARTIGO_RAG = {
    "titulo": "Hybrid Retrieval for Course Question Answering: A Small Empirical Study",
    "autores": "Ana Example and Bruno Placeholder",
    "secoes": [
        ("Abstract", [
            "We study retrieval-augmented generation (RAG) for answering student questions "
            "about course material. We compare a sparse retriever (BM25), a dense retriever "
            "and a hybrid combination on the MauaQA dataset, which contains 1,200 questions "
            "written by undergraduate students. The hybrid retriever reached the best Recall@5.",
        ]),
        ("1 Introduction", [
            "Students frequently ask questions whose answers are spread across long PDF "
            "documents. Retrieval-augmented generation retrieves relevant passages and "
            "conditions a language model on them, reducing unsupported answers.",
            "Our contribution is a controlled comparison of three retrievers on the same "
            "question set, using the same generator and the same prompt for every run.",
        ]),
        ("2 Related Work", [
            "Sparse retrieval with BM25 remains a strong baseline for keyword-heavy questions, "
            "while dense retrievers capture paraphrases and synonyms. Several studies combine "
            "both signals, but most of them evaluate on open-domain benchmarks built from "
            "encyclopedic text rather than on course material.",
            "Course material differs from encyclopedic text: it contains exercises, formulas, "
            "tables with numeric results and figures whose meaning depends on the caption. "
            "Questions written by students also mix informal language with technical terms.",
            "Evaluation of RAG systems usually measures retrieval quality with Recall@k and "
            "answer quality with exact match and F1. Faithfulness to the retrieved passages is "
            "harder to measure and is often checked manually on a small sample.",
            "Our study follows this practice and adds a manual check of citations on 100 "
            "randomly sampled answers, verifying whether each cited passage supports the "
            "corresponding statement.",
        ]),
        ("3 Method", [
            "Each document is split into passages of at most 200 words. Given a question q "
            "and a passage d, the hybrid retriever combines both scores linearly:",
            "FORMULA",
            "where w is a weight between 0 and 1 tuned on a validation split, s<sub>bm25</sub> "
            "is the normalized BM25 score and s<sub>dense</sub> is the cosine similarity between "
            "multilingual embeddings. We used w = 0.4.",
            "The generator receives the five best passages and must cite the passage used "
            "for each statement.",
        ]),
        ("4 Experiments", [
            "TABELA",
            "We report Recall@5, exact match (EM) and token-level F1 on the test split of "
            "MauaQA. All experiments ran on a single consumer GPU.",
            "FIGURA",
        ]),
        ("5 Limitations", [
            "Our evaluation only covers questions written in English. We did not test scanned "
            "documents, and the dataset comes from a single university, so the results may "
            "not generalize to other institutions.",
            "Future work should evaluate multilingual questions and documents with complex "
            "tables and formulas.",
        ]),
        ("6 Conclusion", [
            "A simple hybrid retriever improved Recall@5 over sparse and dense retrievers "
            "while keeping the same generator.",
        ]),
        ("References", [
            "[1] S. Robertson and H. Zaragoza. The probabilistic relevance framework: BM25 and beyond. 2009.",
            "[2] P. Lewis et al. Retrieval-augmented generation for knowledge-intensive NLP tasks. 2020.",
        ]),
    ],
    "formula": "s(q, d) = w · s<sub>bm25</sub>(q, d) + (1 - w) · s<sub>dense</sub>(q, d)",
    "tabela_legenda": "Table 1: Results on the MauaQA test split.",
    "tabela": [
        ["Retriever", "Recall@5", "EM", "F1"],
        ["BM25", "0.61", "0.38", "0.52"],
        ["Dense", "0.72", "0.44", "0.58"],
        ["Hybrid", "0.78", "0.47", "0.61"],
    ],
    "figura_legenda": "Figure 1: Recall@5 by retriever on MauaQA.",
    "figura_valores": [0.61, 0.72, 0.78],
    "figura_nomes": ["BM25", "Dense", "Hybrid"],
}

ARTIGO_VISAO = {
    "titulo": "Lightweight Convolutional Networks for Leaf Disease Detection on Smartphones",
    "autores": "Carla Fictional",
    "secoes": [
        ("Abstract", [
            "We evaluate lightweight convolutional neural networks for detecting leaf "
            "diseases in tomato plants using smartphone photos. MobileNetV3 achieved 91.2% "
            "accuracy on the TomatoLeaf-5k dataset while running in 38 ms per image.",
        ]),
        ("1 Introduction", [
            "Farmers need fast diagnosis in the field, where internet access is limited. "
            "Models must therefore run directly on the phone.",
        ]),
        ("2 Method", [
            "We fine-tuned MobileNetV3 and EfficientNet-B0 with data augmentation "
            "(rotation, color jitter and random crops). Images were resized to 224 x 224 pixels.",
            "FORMULA",
            "where N is the number of images, C the number of classes, y the one-hot label "
            "and p the predicted probability.",
        ]),
        ("3 Results", [
            "TABELA",
            "MobileNetV3 offered the best trade-off between accuracy and latency.",
            "FIGURA",
        ]),
        ("4 Limitations", [
            "All photos were taken under daylight; performance at night or with blurred "
            "images was not measured. Only five disease classes were considered.",
        ]),
        ("References", [
            "[1] A. Howard et al. Searching for MobileNetV3. 2019.",
        ]),
    ],
    "formula": "L = -(1/N) sum<sub>i</sub> sum<sub>c</sub> y<sub>i,c</sub> log(p<sub>i,c</sub>)",
    "tabela_legenda": "Table 1: Accuracy and latency on TomatoLeaf-5k.",
    "tabela": [
        ["Model", "Accuracy (%)", "Latency (ms)"],
        ["MobileNetV3", "91.2", "38"],
        ["EfficientNet-B0", "92.0", "71"],
    ],
    "figura_legenda": "Figure 1: Accuracy of each model on TomatoLeaf-5k.",
    "figura_valores": [91.2, 92.0],
    "figura_nomes": ["MobileNetV3", "EfficientNet-B0"],
}


def _grafico(valores: list[float], nomes: list[str]) -> Drawing:
    desenho = Drawing(7.5 * cm, 4.5 * cm)
    grafico = VerticalBarChart()
    grafico.x, grafico.y = 1 * cm, 0.8 * cm
    grafico.width, grafico.height = 6 * cm, 3.2 * cm
    grafico.data = [valores]
    grafico.categoryAxis.categoryNames = nomes
    grafico.valueAxis.valueMin = 0
    grafico.bars[0].fillColor = colors.HexColor("#4C78A8")
    desenho.add(grafico)
    return desenho


def gerar_artigo(conteudo: dict) -> bytes:
    """Monta um PDF de duas colunas com título em largura total na primeira página."""
    buffer = io.BytesIO()
    margem = 1.8 * cm
    largura, altura = A4
    coluna = (largura - 2 * margem - 0.8 * cm) / 2

    cabecalho = Frame(margem, altura - margem - 3.2 * cm, largura - 2 * margem, 3.2 * cm, id="cab")
    def colunas(topo):
        return [
            Frame(margem, margem, coluna, topo - margem, id="esq"),
            Frame(margem + coluna + 0.8 * cm, margem, coluna, topo - margem, id="dir"),
        ]

    documento = BaseDocTemplate(buffer, pagesize=A4, title="", author="")
    documento.addPageTemplates([
        PageTemplate("primeira", [cabecalho, *colunas(altura - margem - 3.4 * cm)], onPage=_numero_pagina, autoNextPageTemplate="demais"),
        PageTemplate("demais", colunas(altura - margem), onPage=_numero_pagina),
    ])

    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle("titulo", parent=estilos["Title"], fontSize=15, leading=19)
    autores = ParagraphStyle("autores", parent=estilos["Normal"], alignment=1, fontSize=10)
    secao = ParagraphStyle("secao", parent=estilos["Heading2"], fontSize=11, spaceBefore=8)
    corpo = ParagraphStyle("corpo", parent=estilos["BodyText"], fontSize=9, leading=12, alignment=4)
    formula = ParagraphStyle("formula", parent=corpo, alignment=1, fontSize=9, spaceBefore=6, spaceAfter=6)
    legenda = ParagraphStyle("legenda", parent=corpo, fontSize=8, alignment=1, spaceAfter=8)

    historia = [Paragraph(conteudo["titulo"], titulo), Paragraph(conteudo["autores"], autores), FrameBreak()]
    for nome_secao, paragrafos in conteudo["secoes"]:
        historia.append(Paragraph(nome_secao, secao))
        for paragrafo in paragrafos:
            if paragrafo == "FORMULA":
                historia.append(Paragraph(f"{conteudo['formula']}&nbsp;&nbsp;&nbsp;&nbsp;(1)", formula))
            elif paragrafo == "TABELA":
                tabela = Table(conteudo["tabela"])
                tabela.setStyle(TableStyle([
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.black),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
                    ("LINEBELOW", (0, -1), (-1, -1), 0.8, colors.black),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ]))
                historia += [Paragraph(conteudo["tabela_legenda"], legenda), tabela, Spacer(1, 8)]
            elif paragrafo == "FIGURA":
                historia += [
                    _grafico(conteudo["figura_valores"], conteudo["figura_nomes"]),
                    Paragraph(conteudo["figura_legenda"], legenda),
                ]
            else:
                historia.append(Paragraph(paragrafo, corpo))
        historia.append(Spacer(1, 4))

    documento.build(historia)
    return buffer.getvalue()


def _numero_pagina(canvas, documento) -> None:
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(A4[0] / 2, 1 * cm, str(documento.page))


if __name__ == "__main__":
    destino = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "sintetico_rag_hibrido.pdf").write_bytes(gerar_artigo(ARTIGO_RAG))
    (destino / "sintetico_folhas_cnn.pdf").write_bytes(gerar_artigo(ARTIGO_VISAO))
    print(f"PDFs sintéticos gravados em {destino.resolve()}")
