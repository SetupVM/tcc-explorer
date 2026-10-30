"""Executado pelo Python isolado do MinerU; não importa módulos do aplicativo."""

import argparse
import json
import os
import sys
from importlib.metadata import version
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Extrai páginas locais com MinerU Basic/ONNX.")
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--paginas", required=True)
    argumentos = parser.parse_args(argv)
    try:
        partes = argumentos.paginas.split(",")
        if not partes or any(not p.isascii() or not p.isdigit() or int(p) <= 0 for p in partes):
            raise ValueError("Use páginas positivas separadas por vírgulas.")
        paginas = sorted({int(p) for p in partes})
        pdf = argumentos.pdf.expanduser().resolve()
        if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
            raise ValueError("O PDF local não existe.")
        if version("mineru").split(".")[0] != "4":
            raise ValueError("Este worker aceita somente MinerU 4.x.")
        # Estes valores são impostos também aqui para impedir fallback remoto.
        os.environ.update(
            MINERU_MODEL_SMALL_BACKEND="onnx", MINERU_TABLE_DEVICE="cpu", MINERU_DEVICE_MODE="cpu",
            MINERU_MODEL_SOURCE="local", MINERU_MODEL_VLM_SERVER_URL="",
            MINERU_LLM_AIDED_FEATURES_TITLE_LEVELING="false",
            MINERU_LLM_AIDED_FEATURES_CROSS_PAGE_TABLE_CELL_MERGE="false",
            HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
        )
        from mineru.parser import parse

        resultado = parse(pdf, tier="basic", ocr_mode="auto", page_range=",".join(map(str, paginas)))
        texto = resultado.to_json()
        documento = json.loads(texto)
        if documento.get("schema") != "docvortex.middle" or documento.get("schema_version") != "2.0":
            raise ValueError("O SDK devolveu um formato incompatível com DocVortex Middle JSON 2.0.")
        argumentos.saida.write_text(texto, encoding="utf-8")
        return 0
    except Exception as erro:
        print(f"MinerU local: {type(erro).__name__}: {erro}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
