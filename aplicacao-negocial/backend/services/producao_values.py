from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException, status

from backend.models import CarteiraColuna


STATUS_LABELS = {
    "PROPOSTA": "Proposta",
    "AGUARDANDO_PAGAMENTO": "Aguardando pagamento",
    "PAGAMENTO_REALIZADO": "Pagamento realizado",
    "AGUARDANDO_LEVANTAMENTO": "Aguardando levantamento",
    "PROPOSTA_NEGADA": "Proposta negada",
    "OPERACAO_RECOMPRADA": "Operação recomprada",
    "QUEBRA": "Quebra",
}
TIPO_LABELS = {"A_VISTA": "A vista", "PARCELADO": "Parcelado"}


def money(value: Decimal | None) -> Decimal:
    return (value or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money_from_any(value: object) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    raw = "".join(char for char in str(value).strip() if char.isdigit() or char in ",.-")
    if not raw:
        return Decimal("0")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif raw.count(".") > 1:
        parts = raw.split(".")
        raw = "".join(parts[:-1]) + "." + parts[-1] if len(parts[-1]) <= 2 else "".join(parts)
    elif "." in raw:
        whole, decimal = raw.rsplit(".", 1)
        if len(decimal) == 3 and whole.replace("-", "").isdigit():
            raw = whole + decimal
    try:
        return Decimal(raw)
    except Exception:
        return Decimal("0")


def field_key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")


def normalize_status_value(value: object, fallback: str = "") -> str:
    key = field_key(value)
    if not key:
        return fallback
    if key in STATUS_LABELS:
        return key
    by_label = {field_key(label): status_key for status_key, label in STATUS_LABELS.items()}
    return by_label.get(key, key or fallback)


def schema_option_text(option: object) -> str:
    if isinstance(option, dict):
        for key in ("value", "label", "nome", "name", "text", "titulo", "title"):
            if option.get(key) not in (None, ""):
                return str(option.get(key)).strip()
        return ""
    return str(option or "").strip()


def schema_options(column: CarteiraColuna) -> list[str]:
    if not column.opcoes_json:
        return []
    try:
        raw_options = json.loads(column.opcoes_json or "[]")
    except (TypeError, ValueError):
        raw_options = []
    if isinstance(raw_options, str):
        raw_options = [item.strip() for item in raw_options.split(",")]
    if not isinstance(raw_options, list):
        return []
    values: list[str] = []
    seen: set[str] = set()
    for option in raw_options:
        value = schema_option_text(option)
        if not value:
            continue
        if column.chave == "STATUS":
            value = normalize_status_value(value, value)
        if value not in seen:
            seen.add(value)
            values.append(value)
    return values


def field_value(fields: dict[str, object], *keys: object) -> object | None:
    normalized = {field_key(key): value for key, value in fields.items()}
    for key in keys:
        if key in fields:
            return fields[key]
        normalized_key = field_key(key)
        if normalized_key in normalized:
            return normalized[normalized_key]
    return None


def percentual_ho(valor_ho: Decimal, valor_total: Decimal) -> Decimal:
    if valor_total <= 0:
        return Decimal("0.00")
    return ((valor_ho / valor_total) * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def optional_text(value: str | None) -> str | None:
    text = normalize_text(value or "")
    return text or None


def date_from_dynamic_value(value: object, label: str) -> date:
    if isinstance(value, date):
        return value
    raw_value = str(value or "").strip()
    try:
        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", raw_value):
            day, month, year = (int(part) for part in raw_value.split("/"))
            return date(year, month, day)
        return date.fromisoformat(raw_value[:10])
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{label} deve ser uma data valida no formato DD/MM/AAAA.",
        ) from exc
