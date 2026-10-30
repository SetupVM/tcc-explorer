"""Descrição automática de figuras com um modelo de visão local (Ollama).

Mesma ideia do projeto ollama-chromadb-image-search: um modelo de visão
descreve cada imagem em texto, e esse texto vai para o índice junto com a
legenda. Assim a busca encontra figuras pelo que elas mostram, não só pela
legenda.

O Ollama expõe uma API compatível com a da OpenAI, então usamos o mesmo SDK
das aulas com outro endereço (VISAO_URL). A descrição é marcada como gerada
por modelo: ela não é texto dos autores.
"""

import base64
from pathlib import Path

PROMPT = (
    "Esta é uma figura de um artigo científico. Descreva em português, em até 5 frases, "
    "o que ela mostra: tipo (gráfico, diagrama, tabela, foto), componentes, rótulos e eixos "
    "legíveis e a relação ou tendência principal. Transcreva termos técnicos como aparecem. "
    "Não invente valores que não estejam legíveis.\nLegenda no artigo: {legenda}"
)


def criar_cliente_visao(url: str, chave: str = "ollama"):
    from openai import OpenAI

    return OpenAI(base_url=url, api_key=chave, timeout=180)


def modelo_disponivel(cliente, modelo: str) -> tuple[bool, str]:
    """Confere se o servidor responde e se o modelo está instalado."""
    try:
        instalados = [m.id for m in cliente.models.list().data]
    except Exception:
        return False, "O Ollama não respondeu. Abra o aplicativo Ollama ou rode `ollama serve`."
    if modelo not in instalados:
        return False, f"Modelo {modelo} não encontrado. Rode `ollama pull {modelo}`."
    return True, ""


def descrever(cliente, modelo: str, caminho_imagem: Path, legenda: str) -> str:
    imagem = base64.b64encode(Path(caminho_imagem).read_bytes()).decode()
    resposta = cliente.chat.completions.create(
        model=modelo,
        temperature=0,
        max_tokens=350,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT.format(legenda=legenda or "(sem legenda)")},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{imagem}"}},
                ],
            }
        ],
    )
    return (resposta.choices[0].message.content or "").strip()


def descrever_figuras(elementos: list[dict], pasta: Path, cliente, modelo: str, forcar: bool = False) -> dict:
    """Descreve as figuras que têm imagem e ainda não foram descritas."""
    descritas = falhas = 0
    for elemento in elementos:
        if elemento["tipo"] != "figura" or not elemento.get("imagem"):
            continue
        if elemento.get("descricao") and not forcar:
            continue
        try:
            elemento["descricao"] = descrever(cliente, modelo, Path(pasta) / elemento["imagem"], elemento.get("legenda", ""))
            elemento["descricao_modelo"] = modelo
            descritas += 1
        except Exception:
            falhas += 1
    return {"modelo": modelo, "descritas": descritas, "falhas": falhas}
