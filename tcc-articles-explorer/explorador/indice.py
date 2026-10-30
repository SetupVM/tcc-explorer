"""Indexação e recuperação de trechos com ChromaDB (persistência local).

Os embeddings são calculados localmente com um modelo multilíngue
(padrão: intfloat/multilingual-e5-small), para que perguntas em português
encontrem trechos de artigos em inglês. O nome do modelo fica gravado na
coleção: se o modelo mudar, o índice precisa ser recriado.
"""

from pathlib import Path

import chromadb

from explorador.trechos import VERSAO_TRECHOS, Trecho

NOME_COLECAO = "trechos_artigos"


class EmbeddingsLocais:
    """Modelo sentence-transformers, carregado só no primeiro uso.

    Os modelos E5 pedem os prefixos "query:" e "passage:"; o BGE-M3 não.
    """

    def __init__(self, nome_modelo: str):
        self.nome = nome_modelo
        self._modelo = None
        self._usa_prefixo = "e5" in nome_modelo.lower()

    @property
    def modelo(self):
        if self._modelo is None:
            from sentence_transformers import SentenceTransformer

            self._modelo = SentenceTransformer(self.nome)
        return self._modelo

    def documentos(self, textos: list[str]) -> list[list[float]]:
        if self._usa_prefixo:
            textos = [f"passage: {t}" for t in textos]
        return self.modelo.encode(textos, normalize_embeddings=True, batch_size=8).tolist()

    def pergunta(self, texto: str) -> list[float]:
        if self._usa_prefixo:
            texto = f"query: {texto}"
        return self.modelo.encode([texto], normalize_embeddings=True)[0].tolist()


class IndiceTrechos:
    def __init__(self, pasta: Path, embeddings):
        self.embeddings = embeddings
        self.assinatura = f"{embeddings.nome}|trechos-v{VERSAO_TRECHOS}"
        self._cliente = chromadb.PersistentClient(path=str(pasta))
        self._colecao = self._abrir_colecao()
        if self.precisa_recriar() and self._colecao.count() == 0:
            self.recriar()  # coleção vazia de outro modelo: nada a perder

    def _abrir_colecao(self):
        return self._cliente.get_or_create_collection(
            NOME_COLECAO,
            configuration={"hnsw": {"space": "cosine"}},
            metadata={"assinatura": self.assinatura},
            embedding_function=None,  # os embeddings são calculados aqui, não pelo Chroma
        )

    # ------------------------------------------------------------ consistência

    def assinatura_gravada(self) -> str:
        return (self._colecao.metadata or {}).get("assinatura", "")

    def precisa_recriar(self) -> bool:
        """True se a coleção foi criada com outro modelo/versão de trechos."""
        return self.assinatura_gravada() != self.assinatura

    def recriar(self) -> None:
        """Apaga a coleção inteira. Os artigos precisam ser indexados de novo."""
        self._cliente.delete_collection(NOME_COLECAO)
        self._colecao = self._abrir_colecao()

    # ------------------------------------------------------------ escrita

    def indexar_artigo(self, artigo_id: str, trechos: list[Trecho]) -> int:
        """Substitui os trechos e restaura a versão anterior se a escrita falhar.

        O Chroma usado pelo projeto não oferece uma transação para upsert + delete.
        A compensação abaixo cobre exceções enquanto o processo e o banco continuam
        disponíveis; não é uma transação durável contra queda do processo/disco.
        """
        if self.precisa_recriar():
            raise RuntimeError("O índice usa outro modelo de embeddings: recrie o índice antes.")
        ids = [t.id for t in trechos]
        if len(ids) != len(set(ids)) or any(t.artigo_id != artigo_id for t in trechos):
            raise ValueError("Os trechos devem ter IDs únicos e pertencer ao artigo informado.")
        # Nenhuma mutação ocorre antes de todos os vetores estarem calculados.
        vetores = self.embeddings.documentos([t.texto for t in trechos]) if trechos else []
        anteriores = self._colecao.get(
            where={"artigo_id": artigo_id}, include=["documents", "metadatas", "embeddings"]
        )
        ids_anteriores = set(anteriores["ids"])
        ids_novos = sorted(set(ids) - ids_anteriores)
        if ids_novos and self._colecao.get(ids=ids_novos, include=[])["ids"]:
            raise ValueError("Um ID de trecho já pertence a outro artigo.")
        sobras = sorted(ids_anteriores - set(ids))
        try:
            if trechos:
                self._colecao.upsert(
                    ids=ids,
                    documents=[t.texto for t in trechos],
                    metadatas=[t.metadados() for t in trechos],
                    embeddings=vetores,
                )
            if sobras:
                self._colecao.delete(ids=sobras)
        except Exception:
            try:
                if anteriores["ids"]:
                    self._colecao.upsert(
                        ids=anteriores["ids"],
                        documents=anteriores["documents"],
                        metadatas=anteriores["metadatas"],
                        embeddings=anteriores["embeddings"],
                    )
                if ids_novos:
                    self._colecao.delete(ids=ids_novos)
            except Exception as erro_restauracao:
                raise RuntimeError(
                    "A indexação falhou e não foi possível restaurar o índice anterior; "
                    "reindexe este artigo antes de consultá-lo."
                ) from erro_restauracao
            raise
        return len(trechos)

    def remover_artigo(self, artigo_id: str) -> None:
        self._colecao.delete(where={"artigo_id": artigo_id})

    # ------------------------------------------------------------ leitura

    def contar(self, artigo_id: str | None = None) -> int:
        if artigo_id is None:
            return self._colecao.count()
        return len(self._colecao.get(where={"artigo_id": artigo_id}, include=[])["ids"])

    def artigos_indexados(self) -> set[str]:
        resultado = self._colecao.get(include=["metadatas"])
        return {m["artigo_id"] for m in resultado["metadatas"]}

    def buscar(
        self,
        pergunta: str,
        artigo_ids: list[str] | None = None,
        quantidade: int = 8,
        equilibrar: bool = False,
    ) -> list[dict]:
        """Trechos mais próximos da pergunta.

        artigo_ids restringe a busca (None = biblioteca toda; [] = nenhum artigo).
        quantidade é um teto. equilibrar=True reserva primeiro um trecho por artigo
        e depois um segundo, quando houver espaço; as vagas restantes seguem a
        relevância geral. Se não couberem todos os artigos, entram os mais próximos.
        """
        if quantidade <= 0 or artigo_ids == []:
            return []
        if self.precisa_recriar():
            raise RuntimeError("O índice usa outro modelo de embeddings: recrie o índice antes.")
        vetor = self.embeddings.pergunta(pergunta)
        filtro = {"artigo_id": {"$in": list(artigo_ids)}} if artigo_ids is not None else None
        encontrados = {t["id"]: t for t in self._consultar(vetor, filtro, quantidade)}

        if equilibrar:
            selecionados = set(artigo_ids) if artigo_ids is not None else self.artigos_indexados()
            for artigo_id in sorted(selecionados):
                for trecho in self._consultar(vetor, {"artigo_id": artigo_id}, min(2, quantidade)):
                    encontrados.setdefault(trecho["id"], trecho)
        return self._limitar_resultados(list(encontrados.values()), quantidade, equilibrar)

    def buscar_varias(
        self,
        consultas: list[str],
        artigo_ids: list[str] | None = None,
        quantidade: int = 12,
        equilibrar: bool = False,
    ) -> list[dict]:
        """Junta consultas sem duplicatas, mantendo o teto e o equilíbrio finais."""
        if not consultas or quantidade <= 0 or artigo_ids == []:
            return []
        melhores: dict[str, dict] = {}
        for consulta in consultas:
            for trecho in self.buscar(consulta, artigo_ids, quantidade, equilibrar):
                atual = melhores.get(trecho["id"])
                if atual is None or trecho["distancia"] < atual["distancia"]:
                    melhores[trecho["id"]] = trecho
        return self._limitar_resultados(list(melhores.values()), quantidade, equilibrar)

    @staticmethod
    def _limitar_resultados(trechos: list[dict], quantidade: int, equilibrar: bool) -> list[dict]:
        ordenados = sorted(trechos, key=lambda t: (t["distancia"], t["id"]))
        if not equilibrar:
            return ordenados[:quantidade]
        escolhidos: dict[str, dict] = {}
        por_artigo: dict[str, int] = {}
        for rodada in range(2):
            for trecho in ordenados:
                artigo = trecho["artigo_id"]
                if trecho["id"] not in escolhidos and por_artigo.get(artigo, 0) == rodada:
                    escolhidos[trecho["id"]] = trecho
                    por_artigo[artigo] = rodada + 1
                    if len(escolhidos) == quantidade:
                        return sorted(escolhidos.values(), key=lambda t: (t["distancia"], t["id"]))
        for trecho in ordenados:
            escolhidos.setdefault(trecho["id"], trecho)
            if len(escolhidos) == quantidade:
                break
        return sorted(escolhidos.values(), key=lambda t: (t["distancia"], t["id"]))

    def _consultar(self, vetor: list[float], filtro: dict | None, quantidade: int) -> list[dict]:
        resultado = self._colecao.query(
            query_embeddings=[vetor],
            n_results=quantidade,
            where=filtro,
            include=["documents", "metadatas", "distances"],
        )
        return [
            {"id": id_, "texto": texto, "distancia": round(distancia, 4), **metadados}
            for id_, texto, metadados, distancia in zip(
                resultado["ids"][0],
                resultado["documents"][0],
                resultado["metadatas"][0],
                resultado["distances"][0],
            )
        ]

    def obter(self, ids: list[str]) -> list[dict]:
        if not ids:
            return []
        resultado = self._colecao.get(ids=list(ids), include=["documents", "metadatas"])
        return [
            {"id": id_, "texto": texto, **metadados}
            for id_, texto, metadados in zip(
                resultado["ids"], resultado["documents"], resultado["metadatas"]
            )
        ]
