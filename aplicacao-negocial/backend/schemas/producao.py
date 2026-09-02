from datetime import date
from decimal import Decimal, InvalidOperation
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


TipoAcordo = Literal["A_VISTA", "PARCELADO"]
StatusProducao = Literal[
    "PROPOSTA",
    "AGUARDANDO_PAGAMENTO",
    "PAGAMENTO_REALIZADO",
    "AGUARDANDO_LEVANTAMENTO",
    "PROPOSTA_NEGADA",
    "OPERACAO_RECOMPRADA",
    "QUEBRA",
]


class ProducaoCreate(BaseModel):
    npj: str = Field(min_length=1, max_length=80)
    cpf: str | None = Field(default=None, max_length=14)
    cliente: str = Field(min_length=1, max_length=180)
    gecor: str | None = Field(default=None, max_length=80)
    dias_atraso: int | None = Field(default=None, ge=0)
    data_primeiro_atraso: date | None = None
    portfolio: str | None = Field(default=None, max_length=120)
    carteira_alpha: Literal["AUTOS", "SME"] | None = None
    valor_total_acordo: Decimal = Field(ge=0)
    valor_entrada: Decimal | None = Field(default=None, ge=0)
    valor_ho: Decimal | None = Field(default=None, ge=0)
    tipo_acordo: TipoAcordo
    data_vencimento: date
    data_pagamento: date | None = None
    status: StatusProducao
    justificativa_status: str | None = Field(default=None, max_length=600)
    autorizacao_flexibilizacao: str | None = None
    jogar_proximo_mes: bool = False
    campos: dict[str, str | int | float | Decimal | date | bool | list[str] | None] | None = None

    @field_validator("npj", mode="before")
    @classmethod
    def normalize_npj(cls, value):
        identifier = re.sub(r"[^0-9A-Za-z]", "", str(value or "")).strip()
        if not identifier:
            raise ValueError("Identificador obrigatorio.")
        return identifier

    @field_validator("cpf", mode="before")
    @classmethod
    def normalize_cpf(cls, value):
        if value in (None, ""):
            return None
        digits = re.sub(r"\D", "", str(value or ""))
        if len(digits) not in (11, 14):
            raise ValueError("CPF deve conter 11 digitos ou CNPJ deve conter 14 digitos.")
        return digits

    @field_validator("gecor", mode="before")
    @classmethod
    def normalize_gecor(cls, value):
        if value in (None, ""):
            return None
        digits = re.sub(r"\D", "", str(value or ""))
        if len(digits) != 4:
            raise ValueError("GECOR deve conter exatamente 4 digitos.")
        return digits

    @field_validator("valor_total_acordo", "valor_entrada", "valor_ho", mode="before")
    @classmethod
    def normalize_money(cls, value):
        if value is None or isinstance(value, Decimal):
            return value

        text = str(value).strip()
        if not text:
            return value

        cleaned = re.sub(r"[^0-9,.\-]", "", text)
        if not cleaned:
            return value

        if "," in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif cleaned.count(".") > 1:
            parts = cleaned.split(".")
            if len(parts[-1]) in (1, 2):
                cleaned = "".join(parts[:-1]) + "." + parts[-1]
            else:
                cleaned = "".join(parts)
        elif "." in cleaned:
            whole, decimal = cleaned.rsplit(".", 1)
            if len(decimal) == 3 and whole.replace("-", "").isdigit():
                cleaned = whole + decimal

        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return value


class ProducaoUpdate(ProducaoCreate):
    formalizado_novo_acordo: bool = False


class ProducaoStatusUpdate(BaseModel):
    status: StatusProducao
    justificativa_status: str | None = Field(default=None, max_length=600)
    data_pagamento: date | None = None
    jogar_proximo_mes: bool = False
    formalizado_novo_acordo: bool = False


class ProducaoViradaMensalDecisao(BaseModel):
    producao_id: int = Field(gt=0)
    status: Literal["QUEBRA", "PROPOSTA_NEGADA"]
    jogar_proximo_mes: bool = False


class ProducaoViradaMensalConfirm(BaseModel):
    decisoes: list[ProducaoViradaMensalDecisao] = Field(default_factory=list, max_length=5000)
