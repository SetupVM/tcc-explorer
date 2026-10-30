"""Baixa antecipadamente os modelos usados localmente (rode uma vez, com internet).

    python scripts/baixar_modelos.py

- Docling: layout, TableFormer, OCR (RapidOCR) e CodeFormula (fórmulas -> LaTeX).
- Embeddings: modelo definido em EMBEDDING_MODELO.
- Dolphin-1.5: segunda leitura das fórmulas.

A descrição de figuras usa o Ollama (instalado à parte): `ollama pull qwen2.5vl:7b`.

Os arquivos ficam no cache do Hugging Face (~/.cache/huggingface) e não vão
para o repositório. Depois disso, extração e indexação funcionam offline.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from explorador import config  # noqa: E402
from explorador.extracao import ConfigExtracao, criar_conversor, versao_docling  # noqa: E402


def main() -> None:
    from docling.datamodel.base_models import InputFormat

    inicio = time.time()
    print(f"Docling {versao_docling()}: carregando o pipeline com fórmulas e OCR...")
    conversor = criar_conversor(ConfigExtracao(formulas=True, ocr="auto"))
    conversor.initialize_pipeline(InputFormat.PDF)
    print(f"  ok ({time.time() - inicio:.0f}s)")

    print(f"Embeddings: {config.EMBEDDING_MODELO}...")
    from sentence_transformers import SentenceTransformer

    modelo = SentenceTransformer(config.EMBEDDING_MODELO)
    print(f"  ok (dimensão {modelo.get_embedding_dimension()})")

    print(f"Fórmulas: {config.MODELO_FORMULAS}...")
    from explorador.formulas import LeitorDolphin

    LeitorDolphin(config.MODELO_FORMULAS)._carregar()
    print("  ok")
    print(f"Pronto em {time.time() - inicio:.0f}s.")


if __name__ == "__main__":
    main()
