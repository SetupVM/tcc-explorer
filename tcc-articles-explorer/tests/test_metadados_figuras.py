"""Inferência de título/tema e descrição de figuras, com dublês no lugar dos modelos."""

import json
from types import SimpleNamespace

from explorador import biblioteca as bib
from explorador import catalogo as cat
from explorador.figuras import descrever_figuras
from explorador.metadados import (
    MetadadosInferidos,
    escolher_titulo,
    limpar_titulo,
    inferir_com_llm,
    inferir_por_similaridade,
    texto_inicial,
)
from explorador.trechos import gerar_trechos
from tests.conftest import elemento, gerar_pdf_em_branco

TEXTO = (
    "An Experimental Study of Imagination\nC. W. Perky\nSource: The American Journal of Psychology, Jul., 1910\n"
    "This study investigates perception and imagination in psychological experiments with observers."
)


class LLMFalso:
    def __init__(self, titulo, tema="Ciências cognitivas e psicologia", autores=(), ano=None):
        dados = MetadadosInferidos(
            titulo=titulo, tema=tema, palavras_chave=["imaginação", "percepção"], justificativa="ok",
            autores=list(autores), ano=ano,
        )
        mensagem = SimpleNamespace(parsed=dados, refusal=None)
        resposta = SimpleNamespace(choices=[SimpleNamespace(message=mensagem)])
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=lambda **_: resposta))


def test_llm_nao_pode_inventar_titulo():
    assert inferir_com_llm(LLMFalso("An Experimental Study of Imagination"), TEXTO, "m").titulo == "An Experimental Study of Imagination"
    inventado = inferir_com_llm(LLMFalso("A Study I Made Up About Dreams"), TEXTO, "m")
    assert inventado.titulo is None and "descartado" in inventado.observacao
    assert inventado.tema == "Ciências cognitivas e psicologia"


def test_titulo_do_docling_so_e_trocado_quando_parece_errado():
    assert escolher_titulo("Attention Is All You Need", "Provided proper attribution...") == ("Attention Is All You Need", "Docling")
    assert escolher_titulo("Accessibility support:", "An Experimental Study of Imagination") == (
        "An Experimental Study of Imagination", "LLM",
    )
    assert escolher_titulo(None, None) == (None, None)


def test_marca_de_rodape_sai_do_fim_do_titulo():
    assert limpar_titulo("AN EXPERIMENTAL STUDY OF IMAGINATION1") == "AN EXPERIMENTAL STUDY OF IMAGINATION"
    assert limpar_titulo("Attention Is All You Need*") == "Attention Is All You Need"
    assert limpar_titulo("Evaluating GPT4") == "Evaluating GPT4"
    assert limpar_titulo("Scaling to Web3") == "Scaling to Web3"


def test_tema_por_similaridade_sem_llm(embeddings_falsos):
    texto = "imagens video deteccao de objetos segmentacao redes convolucionais imagens video"
    assert inferir_por_similaridade(embeddings_falsos, texto).tema == "Visão computacional"


def test_texto_inicial_ignora_marcas_e_referencias():
    elementos = [
        elemento("e1", "marca_dagua", "downloaded from jstor"),
        elemento("e2", "texto", "Resumo do artigo."),
        elemento("e3", "secao", "References"),
        elemento("e4", "texto", "[1] Outro artigo."),
    ]
    assert texto_inicial(elementos) == "Resumo do artigo."


def _artigo_com_extracao(catalogo, pastas, elementos, tema=None):
    catalogo, resultado = bib.importar_pdf(catalogo, gerar_pdf_em_branco(1), "a.pdf", pastas, tema=tema)
    pasta = pastas.do_artigo(resultado.artigo_id)
    pasta.mkdir(parents=True)
    (pasta / "elementos.json").write_text(json.dumps(elementos))
    (pasta / "manifesto.json").write_text(json.dumps({"status": "concluída", "config": {}, "contagens": {"caracteres": 999}}))
    return catalogo, resultado.artigo_id


def test_inferencia_respeita_tema_informado_pelo_usuario(catalogo, pastas):
    elementos = [elemento("e1", "secao", "Accessibility support:"), elemento("e2", "texto", TEXTO)]
    catalogo, artigo_id = _artigo_com_extracao(catalogo, pastas, elementos, tema="Imaginação")
    opcoes = bib.OpcoesMelhoria(cliente_llm=LLMFalso("An Experimental Study of Imagination"), modelo_llm="m")

    catalogo, _ = bib.inferir_metadados(catalogo, artigo_id, pastas, opcoes)
    linha = catalogo.iloc[0]
    assert linha["tema"] == "Imaginação" and linha["tema_origem"] == "informado"
    assert linha["titulo"] == "An Experimental Study of Imagination" and linha["titulo_origem"] == "LLM"
    assert linha["palavras_chave"] == "imaginação; percepção"

    opcoes.substituir_tema = True
    catalogo, _ = bib.inferir_metadados(catalogo, artigo_id, pastas, opcoes)
    assert catalogo.iloc[0]["tema"] == "Ciências cognitivas e psicologia"
    assert catalogo.iloc[0]["tema_origem"] == "inferido (LLM)"


def test_preenchimento_preserva_tema_e_palavras_chave_manuais(catalogo, pastas):
    catalogo, artigo_id = _artigo_com_extracao(catalogo, pastas, [elemento("e1", "texto", TEXTO)])
    catalogo = cat.atualizar_artigo(catalogo, artigo_id, {
        "tema": "Meu recorte de TCC", "tema_origem": "usuário",
        "palavras_chave": "termo revisado; recorte manual", "metadados_revisados": True,
    })
    opcoes = bib.OpcoesMelhoria(cliente_llm=LLMFalso("x"), modelo_llm="m")
    atualizado, mensagem = bib.inferir_metadados(catalogo, artigo_id, pastas, opcoes)
    assert atualizado.iloc[0]["tema"] == "Meu recorte de TCC"
    assert atualizado.iloc[0]["palavras_chave"] == "termo revisado; recorte manual"
    assert "(usuário)" in mensagem

    # A autorização explícita para trocar temas não autoriza trocar palavras-chave.
    opcoes.substituir_tema = True
    atualizado, _ = bib.inferir_metadados(catalogo, artigo_id, pastas, opcoes)
    assert atualizado.iloc[0]["tema"] == "Ciências cognitivas e psicologia"
    assert atualizado.iloc[0]["palavras_chave"] == "termo revisado; recorte manual"


class VisaoFalsa:
    def __init__(self):
        mensagem = SimpleNamespace(content="Diagrama com blocos de atenção e camadas de normalização.")
        resposta = SimpleNamespace(choices=[SimpleNamespace(message=mensagem)])
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **_: resposta))


def test_descricao_de_figura_entra_na_busca_marcada_como_automatica(tmp_path):
    (tmp_path / "imagens").mkdir()
    (tmp_path / "imagens" / "figura_001.png").write_bytes(b"png")
    figuras = [
        elemento("f1", "figura", paginas=[3], legenda="Figure 1: Architecture.", imagem="imagens/figura_001.png"),
        elemento("f2", "figura", paginas=[3]),  # sem imagem: não é descrita
    ]
    info = descrever_figuras(figuras, tmp_path, VisaoFalsa(), "qwen2.5vl:7b")
    assert info["descritas"] == 1 and "descricao" not in figuras[1]

    texto = gerar_trechos(figuras, "art", "Título")[0].texto
    assert "Figure 1: Architecture." in texto
    assert "Descrição automática da imagem (qwen2.5vl:7b; não é texto do artigo)" in texto


# ---------------------------------------------------------------- autores, ano e DOI


def _pdf_com_texto(caminho, linhas):
    from reportlab.pdfgen import canvas

    folha = canvas.Canvas(str(caminho))
    for numero, linha in enumerate(linhas):
        folha.drawString(72, 750 - 20 * numero, linha)
    folha.save()


def test_ano_e_doi_pelo_carimbo_do_arxiv(tmp_path):
    from explorador.metadados import referencia_do_pdf

    _pdf_com_texto(tmp_path / "x.pdf", ["Some Title", "arXiv:1706.03762v7 [cs.CL] 2 Aug 2023"])
    ref = referencia_do_pdf(tmp_path / "x.pdf", "qualquer_nome.pdf")
    assert (ref.ano, ref.doi) == (2017, "10.48550/arxiv.1706.03762")
    assert "carimbo" in ref.ano_origem


def test_doi_impresso_tem_prioridade_e_nome_do_arquivo_e_o_ultimo_recurso(tmp_path):
    from explorador.metadados import referencia_do_pdf

    _pdf_com_texto(tmp_path / "a.pdf", ["Title", "https://doi.org/10.1145/3583780.3615000"])
    ref = referencia_do_pdf(tmp_path / "a.pdf", "2407.17866v2.pdf")
    assert ref.doi == "10.1145/3583780.3615000" and ref.doi_origem == "impresso no artigo"
    assert ref.ano == 2024 and "nome do arquivo" in ref.ano_origem

    _pdf_com_texto(tmp_path / "b.pdf", ["Title"])
    assert referencia_do_pdf(tmp_path / "b.pdf", "ssrn-4849578.pdf").doi == "10.2139/ssrn.4849578"
    vazio = referencia_do_pdf(tmp_path / "b.pdf", "meu_artigo.pdf")
    assert (vazio.ano, vazio.doi) == (None, None)  # nada é inventado


def test_autores_e_ano_do_llm_so_ficam_se_estiverem_no_texto():
    sugestao = inferir_com_llm(LLMFalso("x", autores=["C. W. Perky", "Autor Inventado"], ano=1910), TEXTO, "m")
    assert sugestao.autores == ["C. W. Perky"] and sugestao.ano == 1910
    assert inferir_com_llm(LLMFalso("x", ano=1999), TEXTO, "m").ano is None


def test_inferencia_preenche_autores_e_ano_sem_apagar_o_que_o_usuario_digitou(catalogo, pastas):
    elementos = [elemento("e1", "secao", "Accessibility support:"), elemento("e2", "texto", TEXTO)]
    catalogo, artigo_id = _artigo_com_extracao(catalogo, pastas, elementos)
    opcoes = bib.OpcoesMelhoria(cliente_llm=LLMFalso("x", autores=["C. W. Perky"], ano=1910), modelo_llm="m")

    catalogo, mensagem = bib.inferir_metadados(catalogo, artigo_id, pastas, opcoes)
    linha = catalogo.iloc[0]
    assert linha["autores"] == "C. W. Perky" and linha["autores_origem"].startswith("LLM")
    assert linha["ano"] == 1910 and "autor" in mensagem

    catalogo = cat.atualizar_artigo(catalogo, artigo_id, {"autores": "Cheves West Perky", "autores_origem": "usuário"})
    catalogo, _ = bib.inferir_metadados(catalogo, artigo_id, pastas, opcoes)
    assert catalogo.iloc[0]["autores"] == "Cheves West Perky"


def test_acentos_soltos_do_pdf_sao_juntados_ao_nome():
    from explorador.metadados import autores_conferidos

    texto = "Stanisław St˛epie´n 1 , Michalina Janik 1"
    assert autores_conferidos(["Stanisław St˛epie´n", "Michalina Janik"], texto) == ["Stanisław Stępień", "Michalina Janik"]
