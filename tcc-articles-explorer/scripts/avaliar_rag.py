"""Avalia o RAG com perguntas de resposta conhecida.

    python scripts/avaliar_rag.py avaliacao/perguntas_sinteticas.csv          # só a busca (sem custo)
    python scripts/avaliar_rag.py avaliacao/perguntas_sinteticas.csv --llm    # busca + LLM (usa a API)

O CSV tem as colunas:
- pergunta:        texto da pergunta (em português)
- titulo_contem:   parte do título do artigo que deve aparecer (vazio = qualquer um)
- trecho_contem:   texto que precisa estar em algum trecho recuperado (vazio se não houver resposta)
- deve_responder:  "sim" ou "não" (perguntas sem resposta na coleção)

Usa a biblioteca configurada no .env (PASTA_DADOS). Mostra, para cada pergunta,
se a busca encontrou o trecho esperado e, com --llm, se o modelo reconheceu
evidência suficiente e se citou trechos inexistentes.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from explorador import catalogo as cat  # noqa: E402
from explorador import config  # noqa: E402
from explorador.indice import EmbeddingsLocais, IndiceTrechos  # noqa: E402


def main() -> None:
    argumentos = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    argumentos.add_argument("csv", type=Path)
    argumentos.add_argument("--llm", action="store_true", help="também gera respostas com o LLM (custo da API)")
    argumentos.add_argument("--k", type=int, default=config.TRECHOS_POR_PERGUNTA, help="trechos por pergunta")
    opcoes = argumentos.parse_args()

    perguntas = pd.read_csv(opcoes.csv, dtype=str, keep_default_na=False)
    catalogo = cat.carregar_catalogo(config.ARQUIVO_CATALOGO)
    indexados = catalogo[catalogo["status_indexacao"] == "indexado"]
    if indexados.empty:
        sys.exit("Nenhum artigo indexado. Importe e indexe os PDFs pelo app antes de avaliar.")
    titulos = {linha["id"]: str(linha["titulo"] if pd.notna(linha["titulo"]) else linha["arquivo_original"]) for _, linha in indexados.iterrows()}
    indice = IndiceTrechos(config.PASTA_CHROMA, EmbeddingsLocais(config.EMBEDDING_MODELO))

    cliente = None
    if opcoes.llm:
        from explorador.respostas import criar_cliente

        cliente = criar_cliente()

    linhas = []
    for _, item in perguntas.iterrows():
        alvo_ids = [i for i, t in titulos.items() if item["titulo_contem"].lower() in t.lower()] if item["titulo_contem"] else None
        trechos = indice.buscar(item["pergunta"], quantidade=opcoes.k)
        posicao = next(
            (
                n
                for n, t in enumerate(trechos, start=1)
                if item["trecho_contem"]
                and item["trecho_contem"].lower() in t["texto"].lower()
                and (alvo_ids is None or t["artigo_id"] in alvo_ids)
            ),
            None,
        )
        linha = {
            "pergunta": item["pergunta"],
            "deve_responder": item["deve_responder"],
            "posicao_trecho_esperado": posicao if item["trecho_contem"] else "—",
        }
        if cliente is not None:
            from explorador.respostas import responder_pergunta

            resultado = responder_pergunta(cliente, item["pergunta"], trechos, titulos)
            esperado = item["deve_responder"].strip().lower() == "sim"
            linha.update(
                evidencia_suficiente=resultado.evidencia_suficiente,
                comportamento_correto=resultado.evidencia_suficiente == esperado,
                afirmacoes=len(resultado.afirmacoes),
                citacoes_invalidas=len(resultado.citacoes_invalidas),
                resposta=resultado.resposta[:160],
            )
        linhas.append(linha)

    tabela = pd.DataFrame(linhas)
    com_resposta = tabela[tabela["deve_responder"].str.lower() == "sim"]
    acertos = com_resposta["posicao_trecho_esperado"].apply(lambda p: isinstance(p, int) and p <= opcoes.k).sum()
    print(tabela.to_string(index=False))
    print(f"\nBusca: trecho esperado entre os {opcoes.k} primeiros em {acertos}/{len(com_resposta)} perguntas com resposta.")
    if cliente is not None:
        print(f"LLM: comportamento esperado (responder ou admitir falta de evidência) em {tabela['comportamento_correto'].sum()}/{len(tabela)}.")

    saida = opcoes.csv.parent / f"resultado_{datetime.now():%Y%m%d_%H%M}.csv"
    tabela.to_csv(saida, index=False)
    print(f"Resultado salvo em {saida}")


if __name__ == "__main__":
    main()
