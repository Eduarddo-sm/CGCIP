from datetime import date, datetime
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


StatusParecer = Literal["PENDENTE", "SOLICITADO", "CANCELADO"]


class ParecerCreate(BaseModel):
    npj: str = Field(min_length=1, max_length=80)
    cliente: str = Field(min_length=1, max_length=180)
    motivo: str = Field(min_length=1, max_length=120)
    descricao: str = Field(min_length=1, max_length=1000)

    @field_validator("npj", mode="before")
    @classmethod
    def normalize_npj(cls, value):
        digits = re.sub(r"\D", "", str(value or ""))
        if len(digits) != 14:
            raise ValueError("NPJ deve conter exatamente 14 digitos.")
        return digits


class ParecerUpdate(ParecerCreate):
    pass


class ParecerStatusUpdate(BaseModel):
    status: StatusParecer


class ParecerResponse(BaseModel):
    id: int
    data_solicitacao: date
    data_conclusao: date | None
    npj: str
    cliente: str
    motivo: str
    descricao: str
    status: str
    status_label: str
    approval_status: str
    approval_reason: str | None
    requested_at: datetime | None
    approval_decided_at: datetime | None
    carteira: str
    user_id: int
    negociador: str | None
    created_at: str
    updated_at: str
