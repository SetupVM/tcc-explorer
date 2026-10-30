"""Divisão dos elementos extraídos em trechos para o índice (chunking).

Regras:
- um trecho não atravessa seções; parágrafos se juntam até TAMANHO_TRECHO;
- fórmulas nunca são cortadas e ficam junto do parágrafo anterior e do
  seguinte (onde normalmente as variáveis são explicadas);
- tabelas viram trechos próprios; se forem grandes, são divididas por linhas
  e o cabeçalho é repetido em cada parte;
- figuras entram pela legenda, pelo texto reconhecido dentro delas e, se houver,
  pela descrição automática (marcada como não sendo texto do artigo);
- fórmulas com leituras divergentes entram com todas as alternativas identificadas;
- texto recuperado da camada do PDF vira trecho próprio; marcas d'água ficam fora;
- a seção de referências bibliográficas não é indexada;
- linhas curtas antes da primeira seção (autores, afiliações, e-mails) não
  são indexadas: esses dados ficam no catálogo;
- páginas são as físicas do PDF, começando em 1.
"""

import re
from dataclasses import dataclass, field

from explorador.formulas import forma_canonica, leituras_por_fonte, versoes

VERSAO_TRECHOS = 1

SECAO_REFERENCIAS = re.compile(
    r"^\s*([\dIVX]+\.?\s*)?(references|refer[êe]ncias|bibliography|bibliografia)\s*$",
    re.IGNORECASE,
)


@dataclass
class Trecho:
    id: str
    artigo_id: str
    titulo: str
    secao: str
    paginas: list[int]
    tipo: str  # texto | texto_com_formula | tabela | figura | texto_pdf
    texto: str
    imagem: str = ""

    def metadados(self) -> dict:
        """Metadados no formato aceito pelo ChromaDB (só valores simples)."""
        return {
            "artigo_id": self.artigo_id,
            "titulo": self.titulo,
            "secao": self.secao,
            "paginas": ",".join(str(p) for p in self.paginas),
            "pagina_inicial": min(self.paginas) if self.paginas else 0,
            "pagina_final": max(self.paginas) if self.paginas else 0,
            "tipo": self.tipo,
            "imagem": self.imagem,
        }


@dataclass
class _Bloco:
    texto: str
    paginas: list[int]
    formula: bool = False


@dataclass
class _Acumulador:
    """Junta parágrafos de uma mesma seção até o tamanho máximo."""

    blocos: list[_Bloco] = field(default_factory=list)

    def tamanho(self) -> int:
        return sum(len(b.texto) for b in self.blocos)

    def ultimo_e_formula(self) -> bool:
        return bool(self.blocos) and self.blocos[-1].formula


def gerar_trechos(
    elementos: list[dict],
    artigo_id: str,
    titulo: str,
    tamanho_max: int = 1200,
) -> list[Trecho]:
    trechos: list[Trecho] = []
    acumulador = _Acumulador()
    secao = ""
    ignorando_secao = False
    antes_da_primeira_secao = True

    def novo_trecho(tipo: str, texto: str, paginas: list[int], imagem: str = "") -> None:
        trechos.append(
            Trecho(
                id=f"{artigo_id}-{len(trechos):04d}",
                artigo_id=artigo_id,
                titulo=titulo,
                secao=secao,
                paginas=sorted(set(paginas)),
                tipo=tipo,
                texto=texto.strip(),
                imagem=imagem,
            )
        )

    def fechar(manter_ultimo: bool = False) -> None:
        """Fecha o trecho atual; opcionalmente leva o último parágrafo para o próximo."""
        blocos = acumulador.blocos
        if not blocos:
            return
        tipo = "texto_com_formula" if any(b.formula for b in blocos) else "texto"
        texto = "\n\n".join(b.texto for b in blocos)
        prefixo = f"Seção: {secao}\n\n" if secao else ""
        novo_trecho(tipo, prefixo + texto, [p for b in blocos for p in b.paginas])
        acumulador.blocos = [blocos[-1]] if manter_ultimo and not blocos[-1].formula else []

    for elemento in elementos:
        tipo = elemento["tipo"]
        paginas = elemento.get("paginas", [])

        if tipo in ("titulo", "marca_dagua"):
            continue
        if tipo == "secao":
            fechar()
            antes_da_primeira_secao = False
            secao = elemento["texto"].strip()
            ignorando_secao = bool(SECAO_REFERENCIAS.match(secao))
            continue
        if ignorando_secao:
            continue

        if tipo == "texto_pdf":
            fechar()
            rotulo = f"Texto recuperado do PDF (fora da estrutura extraída), página {paginas[0]}:\n"
            for parte in dividir_texto_longo(elemento["texto"], tamanho_max - len(rotulo)):
                novo_trecho("texto_pdf", rotulo + parte, paginas)
        elif tipo == "tabela":
            fechar()
            for texto in textos_da_tabela(elemento, tamanho_max):
                novo_trecho("tabela", texto, paginas)
        elif tipo == "figura":
            texto = texto_da_figura(elemento)
            if texto:
                novo_trecho("figura", texto, paginas, elemento.get("imagem") or "")
        elif tipo == "formula":
            formula = texto_da_formula(elemento)
            if not formula:
                continue
            if acumulador.tamanho() + len(formula) > tamanho_max:
                # Leva o parágrafo anterior junto, para a fórmula não ficar sem contexto
                fechar(manter_ultimo=True)
            acumulador.blocos.append(_Bloco(formula, paginas, formula=True))
        else:
            texto = elemento.get("texto", "").strip()
            if not texto or (antes_da_primeira_secao and len(texto) < 200):
                continue
            for parte in dividir_texto_longo(texto, tamanho_max):
                cabe = acumulador.tamanho() + len(parte) <= tamanho_max
                # Depois de uma fórmula, o parágrafo seguinte sempre fica junto
                if not cabe and not acumulador.ultimo_e_formula():
                    fechar()
                acumulador.blocos.append(_Bloco(parte, paginas))

    fechar()
    return trechos


def texto_da_formula(elemento: dict) -> str:
    leituras = versoes(elemento)
    if leituras:
        numero = f"Equação ({elemento['numero']}): " if elemento.get("numero") else ""
        texto = f"{numero}$$ {leituras[0]} $$"
        if len(leituras) > 1:
            nomes = {"docling": "Docling", "dolphin": "Dolphin", "mineru": "MinerU"}
            por_fonte = leituras_por_fonte(elemento)

            def origem(leitura: str) -> str:
                fontes = [
                    nomes[fonte] for fonte, valor in por_fonte.items()
                    if forma_canonica(valor) == forma_canonica(leitura)
                ]
                return ", ".join(fontes) or "fonte não identificada"

            texto += (
                "\n[Leituras divergentes, ainda não conferidas; consultar o PDF antes de usar a fórmula. "
                f"Origem da leitura principal: {origem(leituras[0])}.]"
            )
            for alternativa in leituras[1:]:
                texto += f"\n(leitura alternativa, não conferida — {origem(alternativa)}: $$ {alternativa} $$)"
        return texto
    original = (elemento.get("texto_original") or elemento.get("texto") or "").strip()
    return f"[fórmula, texto do PDF] {original}" if original else ""


def texto_da_figura(elemento: dict) -> str:
    legenda = (elemento.get("legenda") or "").strip()
    interno = (elemento.get("texto_interno") or "").strip()
    descricao = (elemento.get("descricao") or "").strip()
    if not legenda and not interno and not descricao:
        return ""
    partes = [f"Figura: {legenda}" if legenda else "Figura sem legenda."]
    if interno:
        partes.append(f"Texto dentro da figura: {interno}")
    if descricao:
        modelo = elemento.get("descricao_modelo") or "modelo de visão"
        partes.append(f"Descrição automática da imagem ({modelo}; não é texto do artigo): {descricao}")
    return "\n".join(partes)


def textos_da_tabela(elemento: dict, tamanho_max: int) -> list[str]:
    """Tabela em Markdown; se passar do limite, divide por linhas repetindo o cabeçalho."""
    legenda = (elemento.get("legenda") or "").strip()
    colunas = elemento.get("colunas") or []
    linhas = elemento.get("linhas") or []
    titulo = f"Tabela: {legenda}" if legenda else "Tabela sem legenda."

    if not colunas and not linhas:
        markdown = (elemento.get("markdown") or "").strip()
        return [f"{titulo}\n{markdown}"] if markdown or legenda else []

    cabecalho = _linha_markdown(colunas) + "\n" + _linha_markdown(["---"] * len(colunas))
    linhas_md = [_linha_markdown(linha) for linha in linhas]

    partes: list[list[str]] = [[]]
    for linha in linhas_md:
        tamanho_atual = len(cabecalho) + sum(len(l) + 1 for l in partes[-1])
        if partes[-1] and tamanho_atual + len(linha) > tamanho_max:
            partes.append([])
        partes[-1].append(linha)

    textos = []
    for numero, parte in enumerate(partes, start=1):
        sufixo = f" (parte {numero} de {len(partes)})" if len(partes) > 1 else ""
        textos.append(f"{titulo}{sufixo}\n{cabecalho}\n" + "\n".join(parte))
    return textos


def _linha_markdown(celulas: list) -> str:
    return "| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in celulas) + " |"


def dividir_texto_longo(texto: str, tamanho_max: int) -> list[str]:
    """Quebra parágrafos maiores que o limite em frases, sem cortar palavras."""
    if len(texto) <= tamanho_max:
        return [texto]
    frases = re.split(r"(?<=[.!?])\s+", texto)
    partes, atual = [], ""
    for frase in frases:
        if atual and len(atual) + len(frase) + 1 > tamanho_max:
            partes.append(atual)
            atual = ""
        atual = f"{atual} {frase}".strip()
        while len(atual) > tamanho_max:  # frase gigante: corta no último espaço
            corte = atual.rfind(" ", 0, tamanho_max)
            corte = corte if corte > 0 else tamanho_max
            partes.append(atual[:corte])
            atual = atual[corte:].strip()
    if atual:
        partes.append(atual)
    return partes
