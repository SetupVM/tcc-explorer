import pytest

from explorador.pos_processamento import (
    caixas_na_pagina,
    completar_com_texto_do_pdf,
    juntar_paragrafos_entre_paginas,
    marcar_marcas_dagua,
    pos_processar,
)
from explorador.trechos import gerar_trechos
from tests.conftest import elemento
from tests.pdfs_sinteticos import ARTIGO_RAG, gerar_artigo

INICIO = "An attention function maps a query and a set of key-value pairs to an output, computed as a weighted sum"


def test_paragrafo_que_continua_na_proxima_pagina_e_unido():
    elementos = [
        elemento("e1", "secao", "3.2 Attention", [3]),
        elemento("e2", "texto", INICIO, [3]),
        elemento("e3", "figura", paginas=[4], legenda="Figure 2"),
        elemento("e4", "secao", "Scaled Dot-Product Attention", [4]),  # rótulo da figura
        elemento("e5", "texto", "of the values, where the weight is computed by a compatibility function.", [4]),
        elemento("e6", "secao", "3.2.1 Next section", [4]),
    ]
    resultado, unidos = juntar_paragrafos_entre_paginas(elementos)
    assert unidos == 1
    paragrafo = resultado[1]
    assert paragrafo["texto"].endswith("weighted sum of the values, where the weight is computed by a compatibility function.")
    assert paragrafo["paginas"] == [3, 4]
    assert [e["id"] for e in resultado] == ["e1", "e2", "e3", "e4", "e6"]  # figura e rótulo continuam


def test_nao_une_quando_nao_ha_continuacao():
    elementos = [
        elemento("e1", "texto", INICIO + ".", [3]),  # termina com ponto
        elemento("e2", "texto", "of the values, where...", [4]),
        elemento("e3", "texto", INICIO, [4]),
        elemento("e4", "texto", "The next paragraph starts with a capital letter.", [5]),  # maiúscula
        elemento("e5", "texto", "Short text", [5]),  # curto demais para ser fim de parágrafo
        elemento("e6", "texto", "continues here", [6]),
        elemento("e7", "secao", "4 Results", [6]),  # seção numerada não é pulada
        elemento("e8", "texto", INICIO, [6]),
        elemento("e9", "secao", "5 Discussion", [7]),
        elemento("e10", "texto", "lowercase after a real section", [7]),
    ]
    _, unidos = juntar_paragrafos_entre_paginas(elementos)
    assert unidos == 0


def test_palavra_hifenizada_na_quebra_de_pagina():
    elementos = [elemento("e1", "texto", "The model is trained with a learning rate sche-", [2]), elemento("e2", "texto", "dule that decays.", [3])]
    resultado, _ = juntar_paragrafos_entre_paginas(elementos)
    assert resultado[0]["texto"] == "The model is trained with a learning rate schedule that decays."


def test_marca_dagua_e_fragmentos_vizinhos_saem_do_texto():
    elementos = [
        elemento("e1", "texto", "This content downloaded from 201.27.216.153 on W", [2]),
        elemento("e2", "texto", "ed, 21 O", [2]),
        elemento("e3", "texto", "ct 2026 02:01:56 UTC", [2]),
        elemento("e4", "texto", "A real paragraph about imagination and perception in experiments.", [2]),
    ]
    assert marcar_marcas_dagua(elementos) == 3
    assert [e["tipo"] for e in elementos] == ["marca_dagua"] * 3 + ["texto"]


@pytest.mark.parametrize(
    "texto",
    [
        "The training data were downloaded from the public ImageNet repository.",
        "We evaluated traffic to 192.168.1.1 and obtained 95 percent accuracy.",
        "The historical dataset is available at jstor.org for further analysis.",
        "Measurements were taken at 02:01:56 UTC during the experiment.",
    ],
)
def test_texto_cientifico_com_origem_ip_ou_horario_permanece_no_indice(texto):
    elementos = [elemento("s1", "secao", "3 Results", [2]), elemento("e1", "texto", texto, [2])]
    assert marcar_marcas_dagua(elementos) == 0
    assert any(texto in trecho.texto for trecho in gerar_trechos(elementos, "artigo", "Teste"))


def test_so_carimbo_com_posicao_de_rodape_e_marcado():
    texto = "Downloaded from 192.168.1.1 on 21 Oct 2026"
    corpo = {**elemento("e1", "texto", texto, [2]), "caixa": _caixa(2, 400)}
    rodape = {**elemento("e2", "texto", texto, [2]), "caixa": _caixa(2, 790)}
    assert marcar_marcas_dagua([corpo, rodape]) == 1
    assert corpo["tipo"] == "texto"
    assert rodape["tipo"] == "marca_dagua"


def test_frase_curta_e_fragmento_de_outra_pagina_nao_sao_removidos_por_vizinhanca():
    elementos = [
        elemento("e1", "texto", "This content downloaded from 201.27.216.153 on Wed", [2]),
        elemento("e2", "texto", "Accuracy was 95%.", [2]),
        elemento("e3", "texto", "21 Oct 2026", [3]),
    ]
    assert marcar_marcas_dagua(elementos) == 1
    assert [e["tipo"] for e in elementos] == ["marca_dagua", "texto", "texto"]


def test_ip_isolado_nao_e_fragmento_de_data():
    elementos = [
        elemento("e1", "texto", "This content downloaded from 201.27.216.153 on Wed", [2]),
        elemento("e2", "texto", "192.168.1.1", [2]),
    ]
    assert marcar_marcas_dagua(elementos) == 1
    assert elementos[1]["tipo"] == "texto"


def test_melhoria_reavalia_marcas_antigas_sem_perder_notas():
    elementos = [
        elemento("e1", "marca_dagua", "The data were downloaded from ImageNet.", [2]),
        elemento("e2", "marca_dagua", "This content downloaded from 201.27.216.153 on Wed", [2]),
        {**elemento("e3", "marca_dagua", "Server address: 192.168.1.1", [2]), "tipo_antes_marca_dagua": "nota"},
    ]
    assert marcar_marcas_dagua(elementos) == 1
    assert [e["tipo"] for e in elementos] == ["texto", "marca_dagua", "nota"]
    assert marcar_marcas_dagua(elementos) == 1
    assert [e["tipo"] for e in elementos] == ["texto", "marca_dagua", "nota"]


def test_recuperacao_do_pdf_preserva_texto_com_origem_e_ip(tmp_path):
    from reportlab.pdfgen import canvas

    pdf = tmp_path / "origem_dados.pdf"
    pagina = canvas.Canvas(str(pdf))
    linhas = [
        "The training data were downloaded from the public ImageNet repository.",
        "We evaluated traffic to 192.168.1.1 and obtained high detection accuracy.",
        "Our results demonstrate consistent improvements across independent experimental trials.",
        "These experiments support further investigation using larger and more diverse datasets.",
    ]
    for i, linha in enumerate(linhas):
        pagina.drawString(50, 750 - 20 * i, linha)
    pagina.save()

    elementos, info = completar_com_texto_do_pdf([], pdf)
    recuperado = "\n".join(e["texto"] for e in elementos)
    assert info["linhas_recuperadas"] == len(linhas)
    assert linhas[0] in recuperado
    assert linhas[1] in recuperado


def test_texto_do_pdf_que_faltou_na_extracao_e_recuperado(tmp_path):
    pdf = tmp_path / "artigo.pdf"
    pdf.write_bytes(gerar_artigo(ARTIGO_RAG))
    # Extração "incompleta": só o resumo da página 1
    elementos = [elemento("e1", "texto", ARTIGO_RAG["secoes"][0][1][0], [1])]
    resultado, info = completar_com_texto_do_pdf(elementos, pdf)

    recuperados = [e for e in resultado if e["tipo"] == "texto_pdf"]
    assert info["paginas_baixas"] and 1 in info["paginas_baixas"]
    assert recuperados and recuperados[0]["paginas"] == [1]
    assert "Our evaluation only covers questions written" in " ".join(e["texto"] for e in recuperados)
    assert "We study retrieval-augmented generation" not in recuperados[0]["texto"]  # já estava extraído


def test_pos_processamento_pode_ser_reaplicado_sem_duplicar(tmp_path):
    pdf = tmp_path / "artigo.pdf"
    pdf.write_bytes(gerar_artigo(ARTIGO_RAG))
    elementos = [elemento("e1", "secao", "Abstract", [1]), elemento("e2", "texto", ARTIGO_RAG["secoes"][0][1][0], [1])]
    primeira, _ = pos_processar(elementos, pdf)
    segunda, _ = pos_processar(primeira, pdf)
    assert [e["id"] for e in primeira] == [e["id"] for e in segunda]
    assert sum(e["tipo"] == "texto_pdf" for e in segunda) == sum(e["tipo"] == "texto_pdf" for e in primeira)


def _caixa(pagina, y0):
    return {"pagina": pagina, "x0": 50, "y0": y0, "x1": 500, "y1": y0 + 40, "largura_pagina": 595, "altura_pagina": 842}


def test_paragrafo_unido_guarda_a_caixa_de_cada_pagina():
    inicio = {**elemento("e1", "texto", INICIO, [3]), "caixa": _caixa(3, 760), "caixas": [_caixa(3, 760)]}
    resto = {**elemento("e2", "texto", "of the values, computed by a compatibility function.", [4]), "caixa": _caixa(4, 60)}
    resultado, _ = juntar_paragrafos_entre_paginas([inicio, resto])
    paragrafo = resultado[0]
    assert caixas_na_pagina(paragrafo, 3) == [_caixa(3, 760)]
    assert caixas_na_pagina(paragrafo, 4) == [_caixa(4, 60)]  # a continuação tem caixa na página 4


def test_caixas_da_legenda_sao_separadas():
    tabela = {**elemento("t1", "tabela", paginas=[6]), "caixas": [_caixa(6, 200)], "caixas_legenda": [_caixa(6, 150)]}
    assert caixas_na_pagina(tabela, 6) == [_caixa(6, 200)]
    assert caixas_na_pagina(tabela, 6, legenda=True) == [_caixa(6, 150)]
    assert caixas_na_pagina({**elemento("e", "texto"), "caixa": _caixa(2, 10)}, 2) == [_caixa(2, 10)]  # formato antigo
