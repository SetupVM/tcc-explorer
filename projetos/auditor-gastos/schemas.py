from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

ExpenseCategory = Literal["alimentação", "transporte", "moradia", "lazer", "outros"]


class ReceiptItem(BaseModel):
    descricao: str
    quantidade: Decimal = Field(gt=0)
    valor: Decimal = Field(ge=0, description="Valor total desta linha do recibo")


class Receipt(BaseModel):
    estabelecimento: str
    data: date
    itens: list[ReceiptItem]
    valor_total: Decimal = Field(ge=0)
    categoria: ExpenseCategory
