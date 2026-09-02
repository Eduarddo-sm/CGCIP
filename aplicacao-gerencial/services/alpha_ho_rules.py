from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Mapping
import unicodedata


PAYMENT_DATE_STATUSES = {"PAGAMENTO_REALIZADO", "AGUARDANDO_BAIXA"}


def _normalized_key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return "_".join(text.strip().upper().replace("-", " ").split())


def honorarios_base(record: Mapping[str, object]) -> tuple[Decimal, str]:
    agreement_type = _normalized_key(record.get("tipo_acordo"))
    if agreement_type == "PARCELADO":
        return Decimal(record.get("valor_entrada") or 0), "VALOR_DA_ENTRADA"
    return Decimal(record.get("valor_total_acordo") or 0), "VALOR_DO_ACORDO"


def dias_de_atraso(
    data_inicio: date | None,
    status: object,
    data_pagamento: date | None = None,
    hoje: date | None = None,
) -> int | None:
    if not data_inicio:
        return None
    status_key = _normalized_key(status)
    data_referencia = (
        data_pagamento
        if status_key in PAYMENT_DATE_STATUSES and data_pagamento
        else (hoje or date.today())
    )
    return max(0, (data_referencia - data_inicio).days)
