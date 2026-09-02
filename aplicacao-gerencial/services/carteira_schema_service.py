from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from typing import Any


def schema_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")


class CarteiraSchemaService:
    def __init__(self, status_labels: dict[str, str]) -> None:
        self.status_labels = status_labels

    def normalize_options(self, options: Any, column_key: str | None = None) -> list[str]:
        if isinstance(options, str):
            raw_options = [item.strip() for item in options.split(",")]
        elif isinstance(options, list):
            raw_options = options
        else:
            raw_options = []

        normalized: list[str] = []
        seen: set[str] = set()
        for option in raw_options:
            if isinstance(option, dict):
                value = next(
                    (str(option[key]).strip() for key in ("value", "label", "nome", "name", "text", "titulo", "title") if option.get(key) not in (None, "")),
                    "",
                )
            else:
                value = str(option or "").strip()
            if not value:
                continue
            if column_key == "STATUS":
                value = self.normalize_status(value)
            if value not in seen:
                seen.add(value)
                normalized.append(value)
        return normalized

    def normalize_status(self, value: Any) -> str:
        key = schema_key(value)
        if key in self.status_labels:
            return key
        by_label = {schema_key(label): status for status, label in self.status_labels.items()}
        return by_label.get(key, key or str(value or "").strip())

    def normalize_ho_rules(self, rules: dict[str, Any] | None, slug: str) -> dict[str, Any]:
        source = rules or {}
        default_enabled = slug in {"GAMMA", "BETA"}
        enabled = bool(source.get("usa_percentual_ho", default_enabled))
        automatic = bool(source.get("calculo_automatico_ho", enabled and default_enabled))
        engine = schema_key(source.get("motor_calculo") or "PERCENTUAL_FIXO")
        allowed_engines = {
            "PERCENTUAL_FIXO",
            "PERCENTUAL_CONDICIONAL",
            "ALPHA_EXCEPCIONAL",
        }
        if engine not in allowed_engines:
            raise ValueError("Selecione um motor de calculo de H.O valido.")
        if engine == "ALPHA_EXCEPCIONAL" and slug != "ALPHA":
            raise ValueError("O motor excepcional da Alpha so pode ser usado nessa carteira.")
        default_bindings = {
            "GAMMA": {
                "coluna_base": "VALOR_DO_ACORDO",
                "coluna_base_vista": "VALOR_DO_ACORDO",
                "coluna_base_parcelado": "VALOR_DA_ENTRADA",
                "coluna_destino": "HONOR_RIOS",
                "coluna_valor_recebido": "HONOR_RIOS_RECEBIDOS",
                "coluna_percentual_efetivo": "PERCENTUAL",
            },
            "BETA": {
                "coluna_base": "VALOR_TOTAL_DE_ACORDO",
                "coluna_base_vista": "VALOR_TOTAL_DE_ACORDO",
                "coluna_base_parcelado": "VALOR_DA_ENTRADA",
                "coluna_destino": "HONORARIOS",
            },
            "ALPHA": {
                "coluna_base": "VALOR_TOTAL",
                "coluna_base_vista": "VALOR_TOTAL",
                "coluna_base_parcelado": "ENTRADA",
                "coluna_destino": "HONORARIOS_CALCULADOS",
            },
            "CAIXA": {
                "coluna_base": "VALOR_FECHADO",
                "coluna_base_vista": "VALOR_FECHADO",
                "coluna_base_parcelado": "VALOR_DA_ENTRADA",
                "coluna_destino": "HONORARIOS",
            },
        }.get(slug, {})

        def column_key(key: str) -> str | None:
            raw = source.get(key, default_bindings.get(key))
            normalized = schema_key(raw)
            return normalized or None

        if not enabled:
            return {
                "usa_percentual_ho": False,
                "percentual_ho_padrao": None,
                "percentual_ho_minimo": None,
                "percentual_ho_maximo": None,
                "calculo_automatico_ho": False,
                "motor_calculo": "PERCENTUAL_FIXO",
                "coluna_base": None,
                "coluna_base_vista": None,
                "coluna_base_parcelado": None,
                "coluna_destino": None,
                "coluna_valor_recebido": None,
                "coluna_percentual_efetivo": None,
                "casas_decimais": 2,
            }

        def percent(key: str, fallback: Decimal) -> Decimal:
            raw = source.get(key, fallback)
            if raw in (None, ""):
                return fallback
            try:
                return Decimal(str(raw).replace(",", "."))
            except Exception as exc:
                raise ValueError(f"Percentual invalido em {key}.") from exc

        default = percent("percentual_ho_padrao", Decimal("10"))
        minimum = percent("percentual_ho_minimo", default)
        maximum = percent("percentual_ho_maximo", default)
        if min(default, minimum, maximum) < 0 or max(default, minimum, maximum) > 100:
            raise ValueError("Percentuais de H.O devem estar entre 0 e 100.")
        if minimum > maximum:
            raise ValueError("Percentual minimo de H.O nao pode ser maior que o maximo.")
        if not minimum <= default <= maximum:
            raise ValueError("Percentual padrao de H.O deve ficar entre o minimo e o maximo.")
        try:
            decimal_places = int(source.get("casas_decimais", 2))
        except (TypeError, ValueError) as exc:
            raise ValueError("Casas decimais da regra de H.O devem ser um numero inteiro.") from exc
        if decimal_places < 0 or decimal_places > 6:
            raise ValueError("Casas decimais da regra de H.O devem ficar entre 0 e 6.")
        base_key = column_key("coluna_base")
        sight_base_key = column_key("coluna_base_vista")
        installment_base_key = column_key("coluna_base_parcelado")
        destination_key = column_key("coluna_destino")
        received_key = column_key("coluna_valor_recebido")
        effective_key = column_key("coluna_percentual_efetivo")
        if slug == "ALPHA" and engine == "ALPHA_EXCEPCIONAL":
            sight_base_key = sight_base_key or default_bindings["coluna_base_vista"]
            installment_base_key = installment_base_key or default_bindings["coluna_base_parcelado"]
            destination_key = destination_key or default_bindings["coluna_destino"]
        if automatic and not destination_key:
            raise ValueError("Selecione a coluna de destino da regra de H.O.")
        if automatic and engine == "PERCENTUAL_FIXO" and not base_key:
            raise ValueError("Selecione a coluna base da regra fixa de H.O.")
        if automatic and engine == "PERCENTUAL_CONDICIONAL" and (
            not sight_base_key or not installment_base_key
        ):
            raise ValueError("Selecione as bases para acordos a vista e parcelados.")
        selected_bases = {key for key in (base_key, sight_base_key, installment_base_key) if key}
        if destination_key and destination_key in selected_bases:
            raise ValueError("A coluna base e a coluna de destino da regra de H.O devem ser diferentes.")
        if effective_key and not received_key:
            raise ValueError("Selecione a coluna de valor recebido para calcular o percentual efetivo.")
        return {
            "usa_percentual_ho": True,
            "percentual_ho_padrao": default,
            "percentual_ho_minimo": minimum,
            "percentual_ho_maximo": maximum,
            "calculo_automatico_ho": automatic,
            "motor_calculo": engine,
            "coluna_base": base_key,
            "coluna_base_vista": sight_base_key,
            "coluna_base_parcelado": installment_base_key,
            "coluna_destino": destination_key,
            "coluna_valor_recebido": received_key,
            "coluna_percentual_efetivo": effective_key,
            "casas_decimais": decimal_places,
        }
