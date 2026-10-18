from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Any, Callable
import re
import unicodedata

import pandas as pd
from PyPDF2 import PdfReader

from schemas import Receipt

RECEIPT_COLUMNS = ["arquivo", "estabelecimento", "data", "valor_total", "categoria", "itens"]
ERROR_COLUMNS = ["arquivo", "erro"]
CATEGORY_COLUMNS = ["mes", "categoria", "valor_total"]
ITEM_COLUMNS = ["descricao", "valor"]


def read_receipt_text(name: str, content: bytes) -> str:
    """Read a UTF-8 text receipt or extract all selectable text from a PDF."""
    suffix = Path(name).suffix.casefold()
    if suffix == ".txt":
        text = content.decode("utf-8", errors="replace")
    elif suffix == ".pdf":
        reader = PdfReader(BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    else:
        raise ValueError(f"formato não suportado: {suffix or 'sem extensão'}")
    if not text.strip():
        raise ValueError("arquivo sem texto extraível")
    return text.strip()


def parse_brl_amount(value: str | Decimal) -> Decimal:
    """Parse Brazilian currency while preserving decimal precision."""
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace("R$", "").replace(" ", "")
    if not text:
        raise ValueError("valor monetário vazio")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation as error:
        raise ValueError(f"valor monetário inválido: {value!r}") from error


def validate_receipt(
    receipt: Receipt,
    tolerance: Decimal = Decimal("0.05"),
) -> list[str]:
    """Return consistency errors for item totals and receipt total."""
    if tolerance < 0:
        raise ValueError("tolerance não pode ser negativa")
    items_total = sum((item.valor for item in receipt.itens), start=Decimal("0"))
    difference = abs(items_total - receipt.valor_total)
    if difference <= tolerance:
        return []
    return [
        f"soma dos itens ({items_total}) difere do total ({receipt.valor_total}) "
        f"por {difference}, acima da tolerância {tolerance}"
    ]


def _receipt_row(filename: str, receipt: Receipt) -> dict[str, Any]:
    return {
        "arquivo": filename,
        "estabelecimento": receipt.estabelecimento,
        "data": receipt.data,
        "valor_total": receipt.valor_total,
        "categoria": receipt.categoria,
        "itens": [item.model_dump() for item in receipt.itens],
    }


def process_files(
    files: list[tuple[str, bytes]],
    extractor: Callable[[str], Receipt],
    max_attempts: int = 2,
    tolerance: Decimal = Decimal("0.05"),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Process files independently, bounding retries for parsing/validation errors."""
    if max_attempts < 1:
        raise ValueError("max_attempts precisa ser pelo menos 1")

    valid_rows: list[dict[str, Any]] = []
    error_rows: list[dict[str, str]] = []
    for filename, content in files:
        try:
            text = read_receipt_text(filename, content)
        except Exception as error:
            error_rows.append({"arquivo": filename, "erro": str(error)})
            continue

        last_error: Exception | None = None
        for _ in range(max_attempts):
            try:
                extracted = extractor(text)
                receipt = extracted if isinstance(extracted, Receipt) else Receipt.model_validate(extracted)
                consistency_errors = validate_receipt(receipt, tolerance=tolerance)
                if consistency_errors:
                    raise ValueError("; ".join(consistency_errors))
                valid_rows.append(_receipt_row(filename, receipt))
                break
            except Exception as error:
                last_error = error
        else:
            error_rows.append({"arquivo": filename, "erro": str(last_error)})

    valid = pd.DataFrame(valid_rows, columns=RECEIPT_COLUMNS)
    errors = pd.DataFrame(error_rows, columns=ERROR_COLUMNS)
    return valid, errors


def normalize_establishment(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return re.sub(r"\s+", " ", text)


RECEIPT_SYSTEM_PROMPT = """Você é um extrator de recibos.
Extraia estabelecimento, data, itens (descrição, quantidade e valor total da linha),
valor_total e categoria. Use somente estas categorias: alimentação, transporte,
moradia, lazer, outros. Converta valores para números decimais em reais e datas
para ISO (AAAA-MM-DD). Não invente campos ausentes; se o documento estiver
incompleto, deixe a validação estrutural rejeitar a resposta.
"""


def extract_receipt(text: str, client: Any, model: str) -> Receipt:
    """Extract a receipt using OpenAI Structured Outputs and the Pydantic schema."""
    if not text.strip():
        raise ValueError("texto do recibo vazio")
    response = client.beta.chat.completions.parse(
        model=model,
        temperature=0.1,
        max_tokens=700,
        response_format=Receipt,
        messages=[
            {"role": "system", "content": RECEIPT_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    )
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise ValueError("a API não retornou um recibo estruturado")
    return parsed if isinstance(parsed, Receipt) else Receipt.model_validate(parsed)


def mark_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Mark later rows sharing normalized establishment, date and total."""
    required = {"estabelecimento", "data", "valor_total"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"colunas obrigatórias ausentes: {', '.join(sorted(missing))}")
    marked = df.copy()
    dates = pd.to_datetime(marked["data"], format="mixed", errors="coerce").dt.strftime("%Y-%m-%d")
    totals = marked["valor_total"].map(parse_brl_amount)
    seen: set[tuple[str, str, Decimal]] = set()
    duplicate_flags: list[bool] = []
    for establishment, receipt_date, total in zip(marked["estabelecimento"], dates, totals):
        key = (normalize_establishment(establishment), str(receipt_date), total)
        duplicate_flags.append(key in seen)
        seen.add(key)
    marked["duplicado"] = duplicate_flags
    return marked


def build_analytics(
    receipts: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Mark duplicates and aggregate unique expenses by month/category and item."""
    marked = mark_duplicates(receipts)
    monthly = pd.DataFrame(columns=CATEGORY_COLUMNS)
    item_ranking = pd.DataFrame(columns=ITEM_COLUMNS)
    if marked.empty:
        return marked, monthly, item_ranking

    unique = marked.loc[~marked["duplicado"]].copy()
    unique["mes"] = pd.to_datetime(unique["data"], format="mixed", errors="coerce").dt.strftime("%Y-%m")
    monthly = (
        unique.groupby(["mes", "categoria"], dropna=False)["valor_total"]
        .sum()
        .reset_index()
        .sort_values(["mes", "categoria"], kind="stable")
        .reset_index(drop=True)
    )

    item_rows: list[dict[str, Any]] = []
    for items in unique["itens"] if "itens" in unique.columns else []:
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and "descricao" in item and "valor" in item:
                item_rows.append(
                    {"descricao": str(item["descricao"]), "valor": parse_brl_amount(item["valor"])}
                )
    if item_rows:
        item_ranking = (
            pd.DataFrame(item_rows)
            .groupby("descricao", dropna=False)["valor"]
            .sum()
            .reset_index()
            .sort_values(["valor", "descricao"], ascending=[False, True], kind="stable")
            .reset_index(drop=True)
        )
    return marked, monthly, item_ranking
