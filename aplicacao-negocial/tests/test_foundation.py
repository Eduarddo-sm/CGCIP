import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from backend.auth.security import effective_enabled_tools, has_permission, user_permissions, wallet_tool_enabled
from backend.models.alpha_ho import AlphaHoCalculation
from backend.services.audit_service import public_diff
from backend.services.producao_service import (
    _coerce_dynamic_value,
    _explicit_ho_values,
    _is_dynamic_honorarios_column,
    _sync_dynamic_system_fields,
)


class FoundationTest(unittest.TestCase):
    def test_alpha_attainment_supports_exceptionally_high_percentages(self):
        column_type = AlphaHoCalculation.__table__.c.attainment_percent.type
        self.assertEqual((column_type.precision, column_type.scale), (14, 4))

    def test_admin_has_all_permissions(self):
        user = SimpleNamespace(role="ADMIN", enabled_tools="")
        self.assertIn("*", user_permissions(user))
        self.assertTrue(has_permission(user, "qualquer:coisa"))

    def test_negociador_tools_generate_read_and_write_permissions(self):
        user = SimpleNamespace(role="USER", enabled_tools="producao,pareceres")
        self.assertTrue(has_permission(user, "producao:read"))
        self.assertTrue(has_permission(user, "producao:write"))
        self.assertTrue(has_permission(user, "pareceres:write"))

    def test_daily_production_cannot_be_disabled_by_wallet_settings(self):
        db = MagicMock()
        user = SimpleNamespace(role="USER", enabled_tools="producao,pareceres", carteira="GAMMA")

        self.assertTrue(wallet_tool_enabled(db, user, "producao"))
        db.query.assert_not_called()

    def test_disabled_optional_wallet_tool_is_removed_from_effective_tools(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(enabled=False)
        user = SimpleNamespace(role="USER", enabled_tools="producao,pareceres", carteira="GAMMA")

        self.assertEqual(effective_enabled_tools(db, user), {"producao"})

    def test_audit_diff_ignores_updated_at(self):
        diff = public_diff(
            {"cliente": "A", "status": "PROPOSTA", "updated_at": "antes"},
            {"cliente": "A", "status": "QUEBRA", "updated_at": "depois"},
        )
        self.assertEqual(diff, {"status": {"antes": "PROPOSTA", "depois": "QUEBRA"}})

    def test_dynamic_date_accepts_iso_and_brazilian_formats(self):
        column = SimpleNamespace(tipo="data", nome="Data subsidio")
        self.assertEqual(_coerce_dynamic_value(column, "2026-07-09")[2], date(2026, 7, 9))
        self.assertEqual(_coerce_dynamic_value(column, "09/07/2026")[2], date(2026, 7, 9))

    def test_dynamic_date_returns_clear_validation_error(self):
        column = SimpleNamespace(tipo="data", nome="Data subsidio")
        with self.assertRaises(HTTPException) as context:
            _coerce_dynamic_value(column, "31/02/2026")
        self.assertEqual(context.exception.status_code, 422)
        self.assertIn("Data subsidio", context.exception.detail)

    def test_dynamic_multiselect_is_stored_as_unique_json_list(self):
        column = SimpleNamespace(tipo="multiselect", nome="Servicos")
        result = _coerce_dynamic_value(column, ["Parecer", "Evento", "Parecer"])
        self.assertEqual(result, (None, None, None, ["Parecer", "Evento"]))

    def test_dynamic_multiselect_accepts_legacy_delimited_text(self):
        column = SimpleNamespace(tipo="multiselect", nome="Servicos")
        result = _coerce_dynamic_value(column, "Parecer; Evento")
        self.assertEqual(result[3], ["Parecer", "Evento"])

    def test_only_full_honorarios_column_is_calculated_automatically(self):
        honorarios = SimpleNamespace(chave="HONOR_RIOS", nome="HONORARIOS")
        recebidos = SimpleNamespace(chave="HONOR_RIOS_RECEBIDOS", nome="HONORARIOS RECEBIDOS")
        self.assertTrue(_is_dynamic_honorarios_column(honorarios))
        self.assertFalse(_is_dynamic_honorarios_column(recebidos))

    def test_status_change_syncs_dynamic_schema_fields(self):
        item = SimpleNamespace(id=42, campos=[])
        user = SimpleNamespace(carteira="GAMMA")
        columns = [
            SimpleNamespace(id=1, chave="STATUS", nome="STATUS", tipo="select"),
            SimpleNamespace(id=2, chave="JUSTIFICATIVA", nome="JUSTIFICATIVA", tipo="texto"),
        ]

        with patch("backend.services.producao_service._dynamic_columns", return_value=columns):
            _sync_dynamic_system_fields(
                db=SimpleNamespace(),
                item=item,
                user=user,
                values={"STATUS": "PROPOSTA_NEGADA", "JUSTIFICATIVA": "Cliente recusou a proposta"},
            )

        by_column = {field.coluna_id: field for field in item.campos}
        self.assertEqual(by_column[1].valor_texto, "PROPOSTA_NEGADA")
        self.assertEqual(by_column[2].valor_texto, "Cliente recusou a proposta")

    def test_explicit_ho_rule_uses_configured_base_and_destination(self):
        base = SimpleNamespace(chave="VALOR_FECHADO", tipo="moeda", nome="Valor fechado")
        destination = SimpleNamespace(id=20, chave="HONORARIOS", tipo="moeda", nome="Honorarios")
        rule = SimpleNamespace(
            automatico=True,
            percentual_padrao=Decimal("22"),
            coluna_base=base,
            coluna_destino=destination,
            coluna_destino_id=20,
            coluna_valor_recebido=None,
            coluna_percentual_efetivo=None,
            casas_decimais=2,
        )

        result = _explicit_ho_values(
            rule,
            {"VALOR_DO_ACORDO": Decimal("9999")},
            {"VALOR_FECHADO": Decimal("1000")},
        )

        self.assertEqual(result, {20: Decimal("220.00")})

    def test_explicit_ho_rule_calculates_effective_percentage(self):
        base = SimpleNamespace(chave="VALOR_DO_ACORDO", tipo="moeda", nome="Valor do acordo")
        destination = SimpleNamespace(id=20, chave="HONORARIOS", tipo="moeda", nome="Honorarios")
        received = SimpleNamespace(chave="HONORARIOS_RECEBIDOS", tipo="moeda", nome="Recebidos")
        effective = SimpleNamespace(id=22, chave="PERCENTUAL", tipo="numero", nome="Percentual")
        rule = SimpleNamespace(
            automatico=True,
            percentual_padrao=Decimal("10"),
            coluna_base=base,
            coluna_destino=destination,
            coluna_destino_id=20,
            coluna_valor_recebido=received,
            coluna_percentual_efetivo=effective,
            coluna_percentual_efetivo_id=22,
            casas_decimais=2,
        )

        result = _explicit_ho_values(
            rule,
            {"VALOR_DO_ACORDO": Decimal("1000"), "HONORARIOS_RECEBIDOS": Decimal("85")},
            {},
        )

        self.assertEqual(result[20], Decimal("100.00"))
        self.assertEqual(result[22], Decimal("8.50"))

    def test_conditional_ho_rule_uses_entry_for_installment(self):
        total = SimpleNamespace(chave="VALOR_TOTAL", tipo="moeda", nome="Valor total")
        entry = SimpleNamespace(chave="ENTRADA", tipo="moeda", nome="Entrada")
        destination = SimpleNamespace(id=20, chave="HONORARIOS", tipo="moeda", nome="Honorarios")
        rule = SimpleNamespace(
            automatico=True,
            motor_calculo="PERCENTUAL_CONDICIONAL",
            percentual_padrao=Decimal("10"),
            coluna_base=None,
            coluna_base_vista=total,
            coluna_base_parcelado=entry,
            coluna_destino=destination,
            coluna_destino_id=20,
            coluna_valor_recebido=None,
            coluna_percentual_efetivo=None,
            casas_decimais=2,
        )

        result = _explicit_ho_values(
            rule,
            {"TIPO": "PARCELADO", "VALOR_TOTAL": Decimal("1000"), "ENTRADA": Decimal("200")},
            {},
        )

        self.assertEqual(result, {20: Decimal("20.00")})


if __name__ == "__main__":
    unittest.main()
