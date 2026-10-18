from typing import Literal

from pydantic import BaseModel, Field

Sentiment = Literal["positivo", "neutro", "negativo"]
AspectName = Literal["entrega", "preço", "qualidade", "atendimento", "outro"]


class AspectAnalysis(BaseModel):
    aspecto: AspectName
    sentimento: Sentiment


class FeedbackAnalysis(BaseModel):
    sentimento_geral: Sentiment
    idioma: str
    urgente: bool
    aspectos: list[AspectAnalysis] = Field(default_factory=list)
