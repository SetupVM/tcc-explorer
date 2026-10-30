from explorador.extracao import (
    atribuir_secoes,
    avaliar_para_indexacao,
    corrigir_ordem_colunas,
    detectar_doi,
    detectar_titulo,
    formatar_paginas,
    marcar_titulo,
)
from explorador.trechos import gerar_trechos
from tests.conftest import elemento


def test_paginas_sao_as_fisicas_e_comecam_em_1():
    elementos = [
        elemento("e1", "secao", "1 Introduction", [1]),
        elemento("e2", "texto", "A" * 500, [1]),
        elemento("e3", "texto", "B" * 500, [2]),
        elemento("e4", "texto", "C" * 500, [2, 3]),
    ]
    trechos = gerar_trechos(elementos, "art", "Título", tamanho_max=1100)
    assert trechos[0].paginas == [1, 2]
    assert trechos[1].paginas == [2, 3]
    assert trechos[0].metadados()["paginas"] == "1,2"
    assert trechos[1].metadados()["pagina_inicial"] == 2
    assert min(p for t in trechos for p in t.paginas) == 1


def test_trecho_nao_atravessa_secoes_e_guarda_a_secao():
    elementos = [
        elemento("e1", "secao", "2 Method"),
        elemento("e2", "texto", "We use BM25."),
        elemento("e3", "secao", "3 Results"),
        elemento("e4", "texto", "Hybrid wins."),
    ]
    trechos = gerar_trechos(elementos, "art", "Título")
    assert [t.secao for t in trechos] == ["2 Method", "3 Results"]
    assert "BM25" in trechos[0].texto and "Hybrid" not in trechos[0].texto


def test_tabela_grande_e_dividida_repetindo_o_cabecalho():
    linhas = [[f"modelo {i}", f"0.{i:02d}", "x" * 30] for i in range(40)]
    tabela = elemento("t1", "tabela", paginas=[4], legenda="Table 2: Results.", colunas=["Model", "F1", "Notes"], linhas=linhas)
    trechos = gerar_trechos([tabela], "art", "Título", tamanho_max=600)

    assert len(trechos) > 1
    for trecho in trechos:
        assert trecho.tipo == "tabela"
        assert "| Model | F1 | Notes |" in trecho.texto
        assert "Table 2: Results." in trecho.texto
        assert trecho.paginas == [4]
    todas = "\n".join(t.texto for t in trechos)
    assert all(f"modelo {i} |" in todas for i in range(40))  # nenhuma linha se perde


def test_formula_fica_junto_do_texto_que_explica_as_variaveis():
    elementos = [
        elemento("e1", "secao", "2 Method"),
        elemento("e2", "texto", "x" * 900),
        elemento("e3", "texto", "The hybrid score combines both retrievers:"),
        elemento("e4", "formula", latex=r"s(q,d) = w \cdot s_{bm25} + (1-w) \cdot s_{dense}"),
        elemento("e5", "texto", "where w is a weight between 0 and 1."),
        elemento("e6", "texto", "y" * 900),
    ]
    trechos = gerar_trechos(elementos, "art", "Título", tamanho_max=1000)
    com_formula = [t for t in trechos if "$$" in t.texto]
    assert len(com_formula) == 1
    texto = com_formula[0].texto
    assert com_formula[0].tipo == "texto_com_formula"
    assert "combines both retrievers" in texto  # contexto anterior
    assert "where w is a weight" in texto  # explicação das variáveis
    assert r"s_{bm25}" in texto  # LaTeX inteiro, sem corte


def test_formula_sem_latex_usa_texto_original_identificado():
    elementos = [elemento("e1", "formula", texto="L = - 1/N sum", texto_original="L = - 1/N sum")]
    trechos = gerar_trechos(elementos, "art", "Título")
    assert "[fórmula, texto do PDF]" in trechos[0].texto


def test_formula_com_tres_leituras_indexa_todas_com_origem_e_alerta():
    formula = elemento(
        "e1", "formula", paginas=[3], latex="a+b", latex_fonte="docling",
        latex_docling="a+b", latex_dolphin="a+c", latex_mineru="a+d", numero="2",
    )
    trechos = gerar_trechos([formula], "art", "Título")
    texto = trechos[0].texto
    assert trechos[0].paginas == [3]
    assert "Equação (2): $$ a+b $$" in texto
    assert "Origem da leitura principal: Docling" in texto
    assert "Leituras divergentes, ainda não conferidas" in texto
    assert "leitura alternativa, não conferida — Dolphin: $$ a+c $$" in texto
    assert "leitura alternativa, não conferida — MinerU: $$ a+d $$" in texto


def test_formula_com_duas_fontes_iguais_identifica_ambas_e_a_divergente():
    formula = elemento(
        "e1", "formula", latex="a+b", latex_fonte="docling", latex_docling="a+b",
        latex_dolphin="a + b", latex_mineru="a+c",
    )
    texto = gerar_trechos([formula], "art", "Título")[0].texto
    assert "Origem da leitura principal: Docling, Dolphin" in texto
    assert "leitura alternativa, não conferida — MinerU: $$ a+c $$" in texto
    assert texto.count("$$ a+b $$") == 1


def test_formula_mineru_revisada_indexa_somente_escolha():
    formula = elemento(
        "e1", "formula", latex="a+d", latex_fonte="mineru", latex_revisado=True,
        latex_docling="a+b", latex_dolphin="a+c", latex_mineru="a+d",
    )
    texto = gerar_trechos([formula], "art", "Título")[0].texto
    assert texto == "$$ a+d $$"
    assert formula["latex_docling"] == "a+b" and formula["latex_dolphin"] == "a+c"


def test_figura_entra_pela_legenda_e_guarda_a_imagem():
    figura = elemento("f1", "figura", paginas=[3], legenda="Figure 1: Recall by retriever.", imagem="imagens/figura_001.png", texto_interno="BM25 Dense Hybrid")
    trechos = gerar_trechos([figura, elemento("f2", "figura", paginas=[3])], "art", "Título")
    assert len(trechos) == 1  # figura sem legenda nem texto não vira trecho
    assert trechos[0].tipo == "figura"
    assert trechos[0].imagem == "imagens/figura_001.png"
    assert "Recall by retriever" in trechos[0].texto and "BM25" in trechos[0].texto


def test_secao_de_referencias_nao_e_indexada():
    elementos = [
        elemento("e1", "secao", "5 Conclusion"),
        elemento("e2", "texto", "We conclude."),
        elemento("e3", "secao", "References"),
        elemento("e4", "lista", "[1] Someone. A paper. 2020."),
    ]
    trechos = gerar_trechos(elementos, "art", "Título")
    assert len(trechos) == 1
    assert "Someone" not in trechos[0].texto


def test_autores_e_afiliacoes_antes_da_primeira_secao_nao_sao_indexados():
    elementos = [
        elemento("e0", "titulo", "A Study"),
        elemento("e1", "texto", "Ana Example and Bruno Placeholder"),
        elemento("e2", "texto", "Universidade X, ana@example.org"),
        elemento("e3", "texto", "We study retrieval for course questions. " * 8),  # resumo sem cabeçalho
        elemento("e4", "secao", "1 Introduction"),
        elemento("e5", "texto", "Short line."),
    ]
    textos = " ".join(t.texto for t in gerar_trechos(elementos, "art", "A Study"))
    assert "Ana Example" not in textos and "ana@example.org" not in textos
    assert "We study retrieval" in textos and "Short line." in textos


def test_titulo_rotulado_como_secao_vira_titulo():
    elementos = [
        elemento("e0", "secao", "Hybrid Retrieval for QA"),
        elemento("e1", "texto", "Ana Example"),
        elemento("e2", "secao", "Abstract"),
        elemento("e3", "texto", "We study..."),
    ]
    assert detectar_titulo(elementos) == "Hybrid Retrieval for QA"
    marcar_titulo(elementos)
    atribuir_secoes(elementos)
    assert elementos[0]["tipo"] == "titulo"
    assert elementos[1]["secao"] == "" and elementos[3]["secao"] == "Abstract"
    assert detectar_titulo([elemento("e0", "secao", "Abstract")]) is None


def test_ids_sao_estaveis_e_unicos():
    elementos = [elemento(f"e{i}", "texto", f"Paragraph {i}. " * 40) for i in range(10)]
    primeira = gerar_trechos(elementos, "abc123", "Título", tamanho_max=800)
    segunda = gerar_trechos(elementos, "abc123", "Título", tamanho_max=800)
    assert [t.id for t in primeira] == [t.id for t in segunda]
    assert len({t.id for t in primeira}) == len(primeira)
    assert all(t.id.startswith("abc123-") for t in primeira)


def test_paragrafo_longo_e_dividido_sem_perder_texto():
    frases = " ".join(f"Sentence number {i} talks about retrieval." for i in range(100))
    trechos = gerar_trechos([elemento("e1", "texto", frases)], "art", "Título", tamanho_max=500)
    assert len(trechos) > 1
    assert all(len(t.texto) <= 500 for t in trechos)
    assert "Sentence number 99" in trechos[-1].texto


# ---------------------------------------------------------------- funções auxiliares da extração


def _com_caixa(id_, tipo, x0, x1, y0, texto="t"):
    caixa = {"pagina": 1, "x0": x0, "x1": x1, "y0": y0, "y1": y0 + 10, "largura_pagina": 600, "altura_pagina": 800}
    return {"id": id_, "tipo": tipo, "texto": texto, "secao": "", "paginas": [1], "caixa": caixa}


def test_corrige_pagina_de_duas_colunas_lida_fora_de_ordem():
    titulo = _com_caixa("titulo", "secao", 50, 550, 50)
    esquerda = [_com_caixa(f"esq{i}", "texto", 50, 290, 100 + i * 50) for i in range(3)]
    direita = [_com_caixa(f"dir{i}", "texto", 310, 550, 99 + i * 50) for i in range(3)]
    # Ordem errada: coluna direita antes da esquerda
    elementos, corrigidas = corrigir_ordem_colunas([titulo, *direita, *esquerda])
    assert corrigidas == [1]
    assert [e["id"] for e in elementos] == ["titulo", "esq0", "esq1", "esq2", "dir0", "dir1", "dir2"]


def test_nao_mexe_em_pagina_que_ja_esta_na_ordem_certa():
    esquerda = [_com_caixa(f"esq{i}", "texto", 50, 290, 100 + i * 50) for i in range(3)]
    direita = [_com_caixa(f"dir{i}", "texto", 310, 550, 100 + i * 50) for i in range(3)]
    ordem = [*esquerda, *direita]
    elementos, corrigidas = corrigir_ordem_colunas(ordem)
    assert corrigidas == []
    assert elementos == ordem


def test_avaliacao_para_indexacao():
    assert avaliar_para_indexacao(None)[0] == "bloqueado"
    assert avaliar_para_indexacao({"status": "falhou"})[0] == "bloqueado"
    assert avaliar_para_indexacao({"status": "concluída", "contagens": {"caracteres": 50}})[0] == "bloqueado"
    assert avaliar_para_indexacao({"status": "parcial", "contagens": {"caracteres": 5000}})[0] == "confirmar"
    assert avaliar_para_indexacao({"status": "concluída", "contagens": {"caracteres": 5000}, "alertas": []})[0] == "ok"


def test_doi_so_da_primeira_pagina_e_paginas_formatadas():
    elementos = [
        elemento("e1", "texto", "Published at X. https://doi.org/10.1145/3583780.3615000.", [1]),
        elemento("e2", "texto", "See 10.9999/outro.artigo", [2]),
    ]
    assert detectar_doi(elementos) == "10.1145/3583780.3615000"
    assert detectar_doi(elementos[1:]) is None
    assert formatar_paginas([1, 2, 3, 7, 9, 10]) == "1–3, 7, 9–10"
