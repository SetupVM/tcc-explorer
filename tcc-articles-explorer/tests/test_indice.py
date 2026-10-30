import pytest

from explorador.indice import IndiceTrechos
from explorador.trechos import Trecho
from tests.conftest import EmbeddingsFalsos


def _trechos(artigo_id: str, textos: list[str]) -> list[Trecho]:
    return [
        Trecho(f"{artigo_id}-{i:04d}", artigo_id, f"Artigo {artigo_id}", "Seção", [i + 1], "texto", texto)
        for i, texto in enumerate(textos)
    ]


TEXTOS_RAG = ["hybrid retrieval bm25 dense recall", "retrieval augmented generation citations", "limitations english only"]
TEXTOS_CNN = ["leaf disease cnn mobilenet accuracy", "tomato leaf photos smartphone", "limitations daylight photos only"]


def _estado(indice):
    """Compara também os vetores persistidos, não apenas a quantidade de IDs."""
    dados = indice._colecao.get(include=["documents", "metadatas", "embeddings"])
    return {
        id_: (texto, metadados, vetor.tolist())
        for id_, texto, metadados, vetor in zip(
            dados["ids"], dados["documents"], dados["metadatas"], dados["embeddings"]
        )
    }


def test_reindexar_nao_duplica_trechos(indice):
    indice.indexar_artigo("rag", _trechos("rag", TEXTOS_RAG))
    indice.indexar_artigo("rag", _trechos("rag", TEXTOS_RAG))
    assert indice.contar("rag") == 3
    assert indice.contar() == 3


def test_reindexar_versao_menor_remove_trechos_antigos(indice):
    indice.indexar_artigo("rag", _trechos("rag", TEXTOS_RAG))
    indice.indexar_artigo("cnn", _trechos("cnn", TEXTOS_CNN))
    indice.indexar_artigo("rag", _trechos("rag", ["novo conteúdo revisado"]))
    assert indice.contar("rag") == 1
    assert indice.obter(["rag-0000"])[0]["texto"] == "novo conteúdo revisado"
    assert indice.contar("cnn") == 3


def test_falha_nos_embeddings_preserva_indice_anterior(indice, monkeypatch):
    indice.indexar_artigo("rag", _trechos("rag", TEXTOS_RAG))
    antes = _estado(indice)

    def falhar(_textos):
        raise RuntimeError("falha ao calcular embeddings")

    monkeypatch.setattr(indice.embeddings, "documentos", falhar)
    with pytest.raises(RuntimeError, match="calcular embeddings"):
        indice.indexar_artigo("rag", _trechos("rag", ["texto novo"]))
    assert _estado(indice) == antes


@pytest.mark.parametrize("momento", ["antes", "parcial", "depois"])
def test_falha_na_gravacao_restaura_documentos_metadados_e_vetores(indice, monkeypatch, momento):
    indice.indexar_artigo("rag", _trechos("rag", TEXTOS_RAG))
    indice.indexar_artigo("cnn", _trechos("cnn", TEXTOS_CNN))
    antes = _estado(indice)
    original = type(indice._colecao).upsert
    chamadas = 0

    def falhar_uma_vez(colecao, **dados):
        nonlocal chamadas
        chamadas += 1
        if chamadas == 1:
            if momento == "parcial":
                # Grava um ID existente e um novo antes da falha simulada.
                original(colecao, **{campo: [valores[0], valores[-1]] for campo, valores in dados.items()})
            elif momento == "depois":
                original(colecao, **dados)
            raise RuntimeError("falha simulada ao gravar")
        return original(colecao, **dados)

    monkeypatch.setattr(type(indice._colecao), "upsert", falhar_uma_vez)
    novos = _trechos("rag", ["revisão do texto", "outra seção", "limitação revista", "trecho adicional"])
    novos[0].paginas = [8]
    with pytest.raises(RuntimeError, match="falha simulada ao gravar"):
        indice.indexar_artigo("rag", novos)
    assert _estado(indice) == antes


@pytest.mark.parametrize("esvaziar", [False, True])
def test_falha_ao_remover_sobras_restaura_versao_anterior(indice, monkeypatch, esvaziar):
    indice.indexar_artigo("rag", _trechos("rag", TEXTOS_RAG))
    antes = _estado(indice)
    original = type(indice._colecao).delete
    chamadas = 0

    def falhar_uma_vez(colecao, **dados):
        nonlocal chamadas
        chamadas += 1
        original(colecao, **dados)
        if chamadas == 1:
            raise RuntimeError("falha depois de remover sobras")

    monkeypatch.setattr(type(indice._colecao), "delete", falhar_uma_vez)
    novos = [] if esvaziar else _trechos("rag", ["conteúdo revisado"])
    with pytest.raises(RuntimeError, match="remover sobras"):
        indice.indexar_artigo("rag", novos)
    assert _estado(indice) == antes


def test_dimensao_invalida_nao_apaga_indice_anterior(indice, monkeypatch):
    indice.indexar_artigo("rag", _trechos("rag", TEXTOS_RAG))
    antes = _estado(indice)
    monkeypatch.setattr(indice.embeddings, "documentos", lambda textos: [[1.0, 0.0] for _ in textos])
    with pytest.raises(Exception, match="dimension"):
        indice.indexar_artigo("rag", _trechos("rag", ["nova versão"]))
    assert _estado(indice) == antes


def test_falha_de_restauracao_e_reportada_explicitamente(indice, monkeypatch):
    indice.indexar_artigo("rag", _trechos("rag", TEXTOS_RAG))

    def banco_indisponivel(*args, **kwargs):
        raise RuntimeError("banco indisponível")

    monkeypatch.setattr(type(indice._colecao), "upsert", banco_indisponivel)
    with pytest.raises(RuntimeError, match="não foi possível restaurar"):
        indice.indexar_artigo("rag", _trechos("rag", ["nova versão"]))


def test_indexar_lista_vazia_remove_apenas_o_artigo(indice):
    indice.indexar_artigo("rag", _trechos("rag", TEXTOS_RAG))
    indice.indexar_artigo("cnn", _trechos("cnn", TEXTOS_CNN))
    assert indice.indexar_artigo("rag", []) == 0
    assert indice.artigos_indexados() == {"cnn"}


def test_reindexar_nao_permite_sobrescrever_id_de_outro_artigo(indice):
    indice.indexar_artigo("cnn", _trechos("cnn", TEXTOS_CNN))
    antes = _estado(indice)
    novo = _trechos("rag", ["texto novo"])
    novo[0].id = "cnn-0000"
    with pytest.raises(ValueError, match="outro artigo"):
        indice.indexar_artigo("rag", novo)
    assert _estado(indice) == antes


@pytest.mark.parametrize("erro", ["id_duplicado", "artigo_diferente"])
def test_indexar_rejeita_trechos_inconsistentes(indice, erro):
    trechos = _trechos("rag", TEXTOS_RAG)
    if erro == "id_duplicado":
        trechos[1].id = trechos[0].id
    else:
        trechos[1].artigo_id = "outro"
    with pytest.raises(ValueError, match="IDs únicos"):
        indice.indexar_artigo("rag", trechos)
    assert indice.contar() == 0


def test_busca_restrita_aos_artigos_selecionados(indice):
    indice.indexar_artigo("rag", _trechos("rag", TEXTOS_RAG))
    indice.indexar_artigo("cnn", _trechos("cnn", TEXTOS_CNN))

    so_cnn = indice.buscar("hybrid retrieval bm25", artigo_ids=["cnn"], quantidade=5)
    assert so_cnn and {t["artigo_id"] for t in so_cnn} == {"cnn"}

    todos = indice.buscar("hybrid retrieval bm25", quantidade=2)
    assert todos[0]["artigo_id"] == "rag"
    assert todos[0]["paginas"] == "1"


def test_equilibrar_traz_trechos_de_cada_artigo(indice):
    indice.indexar_artigo("rag", _trechos("rag", TEXTOS_RAG))
    indice.indexar_artigo("cnn", _trechos("cnn", TEXTOS_CNN))
    resultado = indice.buscar("limitations", artigo_ids=["rag", "cnn"], quantidade=4, equilibrar=True)
    assert len(resultado) == 4
    assert sum(t["artigo_id"] == "rag" for t in resultado) == 2
    assert {t["artigo_id"] for t in resultado} == {"rag", "cnn"}


@pytest.mark.parametrize("quantidade", [1, 2, 3, 4, 5, 8, 10, 20])
def test_equilibrio_respeita_teto_mesmo_com_mais_artigos_que_vagas(indice, quantidade):
    for artigo in ["a", "b", "c", "d"]:
        indice.indexar_artigo(artigo, _trechos(artigo, [f"{artigo} {texto}" for texto in TEXTOS_RAG]))
    resultado = indice.buscar("retrieval", artigo_ids=["a", "b", "c", "d"], quantidade=quantidade, equilibrar=True)
    assert len(resultado) == min(quantidade, 12)
    assert len({t["id"] for t in resultado}) == len(resultado)
    assert len({t["artigo_id"] for t in resultado}) == min(quantidade, 4)
    assert [t["distancia"] for t in resultado] == sorted(t["distancia"] for t in resultado)


def test_equilibrio_com_uma_vaga_escolhe_artigo_mais_relevante(indice):
    indice.indexar_artigo("rag", _trechos("rag", TEXTOS_RAG))
    indice.indexar_artigo("cnn", _trechos("cnn", TEXTOS_CNN))
    resultado = indice.buscar("leaf disease cnn", artigo_ids=["rag", "cnn"], quantidade=1, equilibrar=True)
    assert len(resultado) == 1
    assert resultado[0]["artigo_id"] == "cnn"


def test_equilibrio_none_inclui_biblioteca_sem_contar_ids_duplicados_ou_ausentes(indice):
    indice.indexar_artigo("rag", _trechos("rag", TEXTOS_RAG))
    indice.indexar_artigo("cnn", _trechos("cnn", TEXTOS_CNN[:1]))
    for ids in (None, ["rag", "rag", "cnn", "inexistente"]):
        resultado = indice.buscar("retrieval", artigo_ids=ids, quantidade=4, equilibrar=True)
        assert len(resultado) == 4
        assert {t["artigo_id"] for t in resultado} == {"rag", "cnn"}


@pytest.mark.parametrize("quantidade,artigo_ids", [(4, []), (0, None), (-1, ["rag"])])
def test_busca_sem_vagas_ou_sem_selecao_nao_calcula_embedding(indice, monkeypatch, quantidade, artigo_ids):
    indice.indexar_artigo("rag", _trechos("rag", TEXTOS_RAG))

    def nao_deve_calcular(_pergunta):
        raise AssertionError("seleção vazia não deve executar busca")

    monkeypatch.setattr(indice.embeddings, "pergunta", nao_deve_calcular)
    assert indice.buscar("retrieval", artigo_ids, quantidade, equilibrar=True) == []
    assert indice.buscar_varias(["retrieval"], artigo_ids, quantidade, equilibrar=True) == []


def test_busca_varias_preserva_equilibrio_e_teto_no_resultado_final(indice):
    for artigo in ["a", "b", "c", "d"]:
        indice.indexar_artigo(artigo, _trechos(artigo, [f"{artigo} {texto}" for texto in TEXTOS_RAG]))
    for quantidade in (2, 4, 8):
        resultado = indice.buscar_varias(
            ["retrieval", "limitations", "citations"], ["a", "b", "c", "d"], quantidade, equilibrar=True
        )
        assert len(resultado) == quantidade
        assert len({t["id"] for t in resultado}) == quantidade
        assert len({t["artigo_id"] for t in resultado}) == min(quantidade, 4)
    assert indice.buscar_varias([]) == []


def test_remover_artigo_limpa_o_indice(indice):
    indice.indexar_artigo("rag", _trechos("rag", TEXTOS_RAG))
    indice.indexar_artigo("cnn", _trechos("cnn", TEXTOS_CNN))
    indice.remover_artigo("rag")
    assert indice.contar("rag") == 0
    assert indice.artigos_indexados() == {"cnn"}


def test_obter_trechos_por_id(indice):
    indice.indexar_artigo("rag", _trechos("rag", TEXTOS_RAG))
    obtidos = indice.obter(["rag-0001"])
    assert obtidos[0]["texto"] == TEXTOS_RAG[1]
    assert indice.obter(["nao-existe"]) == []


def test_troca_de_modelo_de_embeddings_exige_recriar_o_indice(tmp_path, indice):
    indice.indexar_artigo("rag", _trechos("rag", TEXTOS_RAG))

    class OutroModelo(EmbeddingsFalsos):
        nome = "teste/outro-modelo"

    reaberto = IndiceTrechos(tmp_path / "chroma", OutroModelo())
    assert reaberto.precisa_recriar()
    with pytest.raises(RuntimeError, match="recrie o índice"):
        reaberto.buscar("bm25")

    reaberto.recriar()
    assert not reaberto.precisa_recriar()
    assert reaberto.contar() == 0


def test_indice_persiste_em_disco(tmp_path, indice, embeddings_falsos):
    indice.indexar_artigo("rag", _trechos("rag", TEXTOS_RAG))
    reaberto = IndiceTrechos(tmp_path / "chroma", embeddings_falsos)
    assert reaberto.contar("rag") == 3
