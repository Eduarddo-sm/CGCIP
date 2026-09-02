from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
import re
import unicodedata
from typing import Any
from decimal import Decimal, InvalidOperation
from datetime import date

from services.report_export_service import ReportExportService


class NegocialToolBuilderService:
    FIELD_TYPES = {
        "texto", "texto_longo", "numero", "moeda", "data", "select",
        "multiselect", "boolean", "usuario", "carteira", "arquivo",
    }
    TOOL_TYPES = {"CADASTRO", "SOLICITACAO"}
    SCREEN_TYPES = {"dashboard", "lista", "aprovacao", "historico", "planilha"}
    SCREEN_COMPONENTS = {"metricas", "busca", "filtros", "lista", "acoes", "planilha", "relatorio"}
    SCREEN_DENSITIES = {"compacta", "padrao", "confortavel"}
    SCREEN_DATE_MODES = {"none", "date", "period", "deadline"}
    SCREEN_FIELD_ROLES = {"info", "titulo", "subtitulo", "destaque", "badge", "rodape", "oculto"}
    SCREEN_FIELD_WIDTHS = {"auto", "full", "half", "third"}
    DASHBOARD_BLOCK_TYPES = {
        "metric", "status", "funnel", "distribution", "ranking", "timeline",
        "comparison", "deadline", "queue", "validation", "recent",
    }
    DASHBOARD_AGGREGATIONS = {
        "count", "sum", "average", "min", "max", "ratio", "difference",
        "duration_average",
    }
    DASHBOARD_CONDITION_OPERATORS = {
        "eq", "neq", "contains", "gt", "gte", "lt", "lte", "filled", "empty",
    }
    DASHBOARD_PERIODS = {"day", "month", "year"}

    def __init__(self, negocial_service) -> None:
        self.negocial = negocial_service
        self.report_export = ReportExportService()

    @staticmethod
    def _attachment_roots() -> list[Path]:
        shared_data = Path(__file__).resolve().parents[2] / "data"
        default_root = shared_data / "ferramenta-anexos"
        config_path = shared_data / "ferramenta_attachment_storage.json"
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            payload = payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            payload = {}
        configured = str(payload.get("path") or os.environ.get("FERRAMENTA_ATTACHMENTS_DIR") or "").strip()
        current = (Path(configured).expanduser() if configured else default_root).resolve()
        roots = [current]
        for raw in payload.get("legacy_paths") or []:
            try:
                legacy = Path(str(raw)).expanduser().resolve()
            except (OSError, ValueError):
                continue
            if legacy not in roots:
                roots.append(legacy)
        return roots

    @staticmethod
    def _slug(value: str) -> str:
        text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")

    @staticmethod
    def _key(value: str) -> str:
        text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
        return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").upper()

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        cleaned = re.sub(r"[^0-9,.\-]", "", str(value or "0"))
        if "," in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        try:
            return Decimal(cleaned or "0")
        except InvalidOperation:
            return Decimal("0")

    def _apply_calculations(self, payload: dict[str, Any], fields: list[dict[str, Any]]) -> dict[str, Any]:
        result = dict(payload)
        for _ in range(max(1, len(fields))):
            changed = False
            for field in fields:
                calculation = dict((field.get("validacao_json") or {}).get("calculo") or {})
                base_key = self._key(calculation.get("campo_base"))
                if not base_key:
                    continue
                condition = dict(calculation.get("condicao") or {})
                if condition:
                    actual = payload.get(self._key(condition.get("campo")))
                    expected = condition.get("valor")
                    operator = str(condition.get("operador") or "igual")
                    if operator == "igual" and actual != expected: continue
                    if operator == "diferente" and actual == expected: continue
                    if operator == "preenchido" and actual in (None, "", []): continue
                    if operator == "vazio" and actual not in (None, "", []): continue
                left = self._decimal(result.get(base_key))
                secondary = self._key(calculation.get("campo_secundario"))
                right = self._decimal(result.get(secondary)) if secondary else self._decimal(calculation.get("valor"))
                operation = str(calculation.get("operacao") or "percentual").lower()
                if operation == "soma": result_value = left + right
                elif operation == "subtracao": result_value = left - right
                elif operation == "multiplicacao": result_value = left * right
                elif operation == "divisao": result_value = left / right if right else Decimal("0")
                else: result_value = left * right / Decimal("100")
                normalized = str(result_value.quantize(Decimal("0.01")))
                if result.get(field["chave"]) != normalized:
                    result[field["chave"]] = normalized
                    changed = True
            if not changed:
                break
        return result

    def _normalize_screens(
        self,
        raw_screens: Any,
        statuses: list[dict[str, Any]],
        fields: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_screens, list):
            return []
        status_codes = {item["codigo"] for item in statuses}
        field_keys = {item["chave"] for item in fields}
        date_field_keys = {item["chave"] for item in fields if item["tipo"] == "data"}
        screens = []
        used_ids = set()
        for index, raw in enumerate(raw_screens):
            item = dict(raw or {})
            screen_type = str(item.get("tipo") or "lista").strip().lower()
            if screen_type not in self.SCREEN_TYPES:
                raise ValueError("Existe uma tela com tipo invalido.")
            name = str(item.get("nome") or f"Tela {index + 1}").strip()
            screen_id = self._slug(item.get("id") or name) or f"tela-{index + 1}"
            if screen_id in used_ids:
                raise ValueError("As telas devem possuir identificadores unicos.")
            used_ids.add(screen_id)
            components = item.get("componentes") or []
            if isinstance(components, str):
                components = components.split(",")
            components = [
                str(value).strip().lower() for value in components
                if str(value).strip().lower() in self.SCREEN_COMPONENTS
            ]
            selected_statuses = [
                self._key(value) for value in (item.get("status_codes") or [])
                if self._key(value) in status_codes
            ]
            history_statuses = [
                self._key(value) for value in (item.get("historico_status_codes") or [])
                if self._key(value) in status_codes
            ]
            selected_fields = [
                self._key(value) for value in (item.get("campos") or [])
                if self._key(value) in field_keys
            ]
            raw_layout = dict(item.get("layout") or {})
            density = str(raw_layout.get("densidade") or "compacta").strip().lower()
            if density not in self.SCREEN_DENSITIES:
                density = "compacta"
            layout = {
                "colunas_desktop": max(1, min(6, int(raw_layout.get("colunas_desktop") or 1))),
                "colunas_tablet": max(1, min(3, int(raw_layout.get("colunas_tablet") or 1))),
                "colunas_mobile": max(1, min(2, int(raw_layout.get("colunas_mobile") or 1))),
                "densidade": density,
                "altura_uniforme": bool(raw_layout.get("altura_uniforme")),
            }
            raw_filters = dict(item.get("filtros") or {})
            raw_custom_filters = raw_filters.get("campos") or []
            if isinstance(raw_custom_filters, str):
                raw_custom_filters = raw_custom_filters.split(",")
            custom_filter_keys = [
                self._key(value) for value in raw_custom_filters
                if self._key(value) in field_keys
            ]
            has_explicit_filters = any(
                key in raw_filters
                for key in ("mostrar_status", "mostrar_negociador", "mostrar_carteira", "mostrar_ordenacao", "campos")
            )
            date_mode = str(raw_filters.get("modo_data") or "none").strip().lower()
            if date_mode not in self.SCREEN_DATE_MODES:
                date_mode = "none"
            date_field = self._key(raw_filters.get("campo_data"))
            if date_field not in date_field_keys:
                date_field = ""
            raw_visible_deadlines = raw_filters.get("prazos_visiveis")
            if raw_visible_deadlines is None:
                raw_visible_deadlines = [
                    "all", "overdue", "today", "next3", "next7", "next30", "later", "no_date", "completed"
                ]
            elif isinstance(raw_visible_deadlines, str):
                raw_visible_deadlines = raw_visible_deadlines.split(",")
            filters = {
                # Definitions created before custom filters keep their previous behavior.
                "mostrar_status": bool(raw_filters.get("mostrar_status", not has_explicit_filters)),
                "mostrar_negociador": bool(raw_filters.get("mostrar_negociador", not has_explicit_filters)),
                "mostrar_carteira": bool(raw_filters.get("mostrar_carteira", False)),
                "mostrar_ordenacao": bool(raw_filters.get("mostrar_ordenacao", not has_explicit_filters)),
                "campos": list(dict.fromkeys(custom_filter_keys)),
                "campo_data": date_field,
                "modo_data": date_mode,
                "prazos_visiveis": [
                    value for value in dict.fromkeys(raw_visible_deadlines)
                    if value in {"all", "overdue", "today", "next3", "next7", "next30", "later", "no_date", "completed"}
                ],
                "agrupar_prazo": bool(raw_filters.get("agrupar_prazo")),
                "iniciar_recolhido": bool(raw_filters.get("iniciar_recolhido")),
            }
            raw_grouping = dict(item.get("agrupamento") or {})
            grouping_mode = str(raw_grouping.get("modo") or ("deadline" if filters["agrupar_prazo"] else "none")).strip().lower()
            if grouping_mode not in {"none", "deadline", "status", "field"}:
                grouping_mode = "none"
            grouping_field = self._key(raw_grouping.get("campo"))
            if grouping_field not in field_keys:
                grouping_field = ""
            grouping = {
                "modo": grouping_mode,
                "campo": grouping_field,
                "iniciar_recolhido": bool(raw_grouping.get("iniciar_recolhido", filters["iniciar_recolhido"])),
            }
            raw_card_actions = dict(item.get("acoes_card") or {})
            action_mode = str(raw_card_actions.get("status_modo") or "open").strip().lower()
            if action_mode not in {"none", "open", "select", "button"}:
                action_mode = "open"
            action_source = str(raw_card_actions.get("status_origem") or "flow").strip().lower()
            if action_source not in {"flow", "field"}:
                action_source = "flow"
            action_field = self._key(raw_card_actions.get("status_campo"))
            if action_field not in field_keys:
                action_field = ""
            copy_fields = raw_card_actions.get("copiar_campos") or []
            if isinstance(copy_fields, str):
                copy_fields = copy_fields.split(",")
            card_actions = {
                "copiar": bool(raw_card_actions.get("copiar")),
                "copiar_campos": list(dict.fromkeys(
                    self._key(value) for value in copy_fields if self._key(value) in field_keys
                )),
                "observacoes": bool(raw_card_actions.get("observacoes")),
                "mostrar_atualizacao": bool(raw_card_actions.get("mostrar_atualizacao", True)),
                "status_modo": action_mode,
                "status_origem": action_source,
                "status_campo": action_field,
                "botao_rotulo": str(raw_card_actions.get("botao_rotulo") or "Abrir").strip()[:40] or "Abrir",
                "botao_status": self._key(raw_card_actions.get("botao_status"))
                if self._key(raw_card_actions.get("botao_status")) in status_codes else "",
            }
            field_layout = {}
            for raw_key, raw_config in dict(item.get("campo_layout") or {}).items():
                key = self._key(raw_key)
                if key not in field_keys:
                    continue
                config = dict(raw_config or {})
                role = str(config.get("papel") or "info").strip().lower()
                width = str(config.get("largura") or "auto").strip().lower()
                field_layout[key] = {
                    "papel": role if role in self.SCREEN_FIELD_ROLES else "info",
                    "largura": width if width in self.SCREEN_FIELD_WIDTHS else "auto",
                    "copiavel": bool(config.get("copiavel")),
                }
            raw_dashboard = dict(item.get("dashboard") or {})
            dashboard_blocks = []
            used_block_ids = set()
            for block_index, raw_block in enumerate(raw_dashboard.get("blocks") or []):
                block = dict(raw_block or {})
                block_type = str(block.get("tipo") or "metric").strip().lower()
                if block_type not in self.DASHBOARD_BLOCK_TYPES:
                    continue
                block_id = self._slug(block.get("id") or block.get("titulo") or f"bloco-{block_index + 1}")
                base_id = block_id or f"bloco-{block_index + 1}"
                suffix = 2
                while block_id in used_block_ids:
                    block_id = f"{base_id}-{suffix}"
                    suffix += 1
                used_block_ids.add(block_id)
                aggregation = str(block.get("agregacao") or "count").strip().lower()
                value_field = self._key(block.get("campo"))
                secondary_field = self._key(block.get("campo_secundario"))
                group_field = self._key(block.get("agrupador"))
                condition_field = self._key(block.get("condicao_campo"))
                condition_operator = str(block.get("condicao_operador") or "eq").strip().lower()
                selected_block_statuses = [
                    self._key(value) for value in (block.get("status_codes") or [])
                    if self._key(value) in status_codes
                ]
                color = str(block.get("cor") or "#2563eb").strip()
                if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                    color = "#2563eb"
                dashboard_blocks.append({
                    "id": block_id,
                    "tipo": block_type,
                    "titulo": str(block.get("titulo") or f"Bloco {block_index + 1}").strip()[:120],
                    "agregacao": aggregation if aggregation in self.DASHBOARD_AGGREGATIONS else "count",
                    "campo": value_field if value_field in field_keys else "",
                    "campo_secundario": secondary_field if secondary_field in field_keys else "",
                    "agrupador": group_field if group_field in field_keys else "",
                    "condicao_campo": condition_field if condition_field in field_keys else "",
                    "condicao_operador": condition_operator
                    if condition_operator in self.DASHBOARD_CONDITION_OPERATORS else "eq",
                    "condicao_valor": str(block.get("condicao_valor") or "").strip()[:500],
                    "status_codes": list(dict.fromkeys(selected_block_statuses)),
                    "cor": color.lower(),
                    "largura": max(3, min(12, int(block.get("largura") or 6))),
                    "limite": max(3, min(30, int(block.get("limite") or 8))),
                    "periodo": str(block.get("periodo") or "day").lower()
                    if str(block.get("periodo") or "day").lower() in self.DASHBOARD_PERIODS else "day",
                })
            dashboard = {"columns": 12, "blocks": dashboard_blocks}
            screens.append({
                "id": screen_id,
                "nome": name,
                "icone": str(item.get("icone") or name[:1] or "T")[:8],
                "tipo": screen_type,
                "ordem": index,
                "visivel_negocial": bool(item.get("visivel_negocial", True)),
                "visivel_gerencial": bool(item.get("visivel_gerencial", True)),
                "status_codes": list(dict.fromkeys(selected_statuses)),
                "historico_status_codes": list(dict.fromkeys(history_statuses)),
                "campos": list(dict.fromkeys(selected_fields)),
                "componentes": list(dict.fromkeys(components)),
                "layout": layout,
                "filtros": filters,
                "agrupamento": grouping,
                "acoes_card": card_actions,
                "campo_layout": field_layout,
                "dashboard": dashboard,
            })
        return screens

    def _validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("nome") or "").strip()
        if len(name) < 2:
            raise ValueError("Informe o nome da ferramenta.")
        tool_type = str(payload.get("tipo") or "CADASTRO").upper()
        if tool_type not in self.TOOL_TYPES:
            raise ValueError("Tipo de ferramenta invalido.")
        configuration = dict(payload.get("configuracao") or {})
        use_status = tool_type != "CADASTRO" or bool(configuration.get("usar_status", True))
        configuration["usar_status"] = use_status
        configuration["negociador_define_status"] = bool(
            tool_type == "CADASTRO"
            and use_status
            and configuration.get("negociador_define_status")
        )

        fields = []
        keys = set()
        for index, raw in enumerate(payload.get("campos") or []):
            field = dict(raw or {})
            key = self._key(field.get("chave") or field.get("nome"))
            if not key or key in keys:
                raise ValueError("As chaves dos campos devem ser unicas.")
            field_type = str(field.get("tipo") or "texto").lower()
            if field_type not in self.FIELD_TYPES:
                raise ValueError(f"Tipo invalido no campo {field.get('nome') or key}.")
            keys.add(key)
            options = field.get("opcoes") or []
            if isinstance(options, str):
                options = options.split(",")
            fields.append({
                "chave": key,
                "nome": str(field.get("nome") or key).strip(),
                "tipo": field_type,
                "ordem": int(field.get("ordem", index)),
                "etapa": max(1, min(10, int(field.get("etapa") or 1))),
                "obrigatorio": bool(field.get("obrigatorio")),
                "somente_leitura": bool(field.get("somente_leitura")),
                "visivel_negocial": bool(field.get("visivel_negocial", True)),
                "visivel_gerencial": bool(field.get("visivel_gerencial", True)),
                "opcoes": list(dict.fromkeys(str(item).strip() for item in options if str(item).strip())),
                "validacao": dict(field.get("validacao") or {}),
                "condicao": dict(field.get("condicao") or {}),
                "valor_padrao": field.get("valor_padrao"),
            })
        if not fields:
            raise ValueError("Adicione ao menos um campo.")

        field_keys = {item["chave"] for item in fields}
        allowed_operators = {"igual", "diferente", "preenchido", "vazio", "contem", "em", "nao_em", "maior", "maior_igual", "menor", "menor_igual"}
        allowed_calculations = {"percentual", "soma", "subtracao", "multiplicacao", "divisao"}
        for field in fields:
            validation = field["validacao"]
            condition = field["condicao"]
            if condition:
                condition["campo"] = self._key(condition.get("campo"))
                condition["operador"] = str(condition.get("operador") or "igual").lower()
                if condition["campo"] not in field_keys or condition["operador"] not in allowed_operators:
                    raise ValueError(f"Condicao invalida no campo {field['nome']}.")
            if validation.get("regex"):
                if len(str(validation["regex"])) > 240:
                    raise ValueError(f"Expressao muito longa no campo {field['nome']}.")
                try:
                    re.compile(str(validation["regex"]))
                except re.error as exc:
                    raise ValueError(f"Expressao invalida no campo {field['nome']}.") from exc
            calculation = dict(validation.get("calculo") or {})
            if calculation:
                calculation["operacao"] = str(calculation.get("operacao") or "percentual").lower()
                calculation["campo_base"] = self._key(calculation.get("campo_base"))
                calculation["campo_secundario"] = self._key(calculation.get("campo_secundario"))
                if calculation["operacao"] not in allowed_calculations or calculation["campo_base"] not in field_keys:
                    raise ValueError(f"Calculo invalido no campo {field['nome']}.")
                if calculation["campo_secundario"] and calculation["campo_secundario"] not in field_keys:
                    raise ValueError(f"Campo secundario invalido no calculo de {field['nome']}.")
                calculation["condicao"] = dict(calculation.get("condicao") or {})
                validation["calculo"] = calculation
                field["somente_leitura"] = True

        statuses = []
        codes = set()
        raw_statuses = (payload.get("statuses") or []) if use_status else [{
            "codigo": "REGISTRADO",
            "nome": "Registrado",
            "cor": "#64748b",
            "inicial": True,
            "final": True,
        }]
        for index, raw in enumerate(raw_statuses):
            item = dict(raw or {})
            code = self._key(item.get("codigo") or item.get("nome"))
            if not code or code in codes:
                raise ValueError("Os status devem possuir codigos unicos.")
            codes.add(code)
            statuses.append({
                "codigo": code,
                "nome": str(item.get("nome") or code).strip(),
                "cor": str(item.get("cor") or "#2563eb").strip(),
                "ordem": int(item.get("ordem", index)),
                "inicial": bool(item.get("inicial")),
                "final": bool(item.get("final")),
            })
        if sum(1 for item in statuses if item["inicial"]) != 1:
            raise ValueError("Defina exatamente um status inicial.")

        raw_main_hub = dict(configuration.get("main_hub") or {})
        main_hub_enabled = bool(raw_main_hub.get("enabled")) and use_status
        main_hub_statuses = list(dict.fromkeys(
            self._key(item) for item in (raw_main_hub.get("status_codes") or [])
            if self._key(item) in codes
        ))
        main_hub_fields = list(dict.fromkeys(
            self._key(item) for item in (raw_main_hub.get("field_keys") or [])
            if self._key(item) in field_keys
        ))[:8]
        if main_hub_enabled and not main_hub_statuses:
            raise ValueError("Selecione ao menos um status de pendencia para o Main Hub.")
        configuration["main_hub"] = {
            "enabled": main_hub_enabled,
            "status_codes": main_hub_statuses,
            "field_keys": main_hub_fields,
        }

        configuration["telas"] = self._normalize_screens(
            configuration.get("telas"), statuses, fields
        )

        transitions = []
        seen_transitions = set()
        for raw in (payload.get("transicoes") or []) if use_status else []:
            item = dict(raw or {})
            origin = self._key(item.get("origem_codigo"))
            target = self._key(item.get("destino_codigo"))
            identity = (origin, target)
            if origin not in codes or target not in codes or origin == target:
                raise ValueError("Existe uma transicao com status invalido.")
            if identity in seen_transitions:
                raise ValueError("Existem transicoes duplicadas.")
            seen_transitions.add(identity)
            transition_config = dict(item.get("configuracao") or {})
            automations = []
            for raw_automation in transition_config.get("automacoes") or []:
                automation = dict(raw_automation or {})
                action = str(automation.get("tipo") or "").lower()
                field_key = self._key(automation.get("campo"))
                if action not in {"data_atual", "definir_valor", "limpar_campo", "notificar"}:
                    raise ValueError("Existe uma automacao de transicao invalida.")
                if action != "notificar" and field_key not in field_keys:
                    raise ValueError("Uma automacao aponta para um campo inexistente.")
                automations.append({"tipo": action, "campo": field_key, "valor": automation.get("valor")})
            transition_config["automacoes"] = automations
            transitions.append({
                "origem_codigo": origin,
                "destino_codigo": target,
                "nome": str(item.get("nome") or f"{origin} para {target}").strip(),
                "exige_justificativa": bool(item.get("exige_justificativa")),
                "permite_negociador": bool(item.get("permite_negociador")),
                "permite_gerencial": bool(item.get("permite_gerencial", True)),
                "configuracao": transition_config,
            })

        permissions = []
        for raw in payload.get("permissoes") or []:
            item = dict(raw or {})
            user_id = int(item["user_id"]) if item.get("user_id") else None
            wallet = str(item.get("carteira") or "").strip().upper() or None
            if not user_id and not wallet:
                raise ValueError("Permissao deve indicar usuario ou carteira.")
            permissions.append({
                "user_id": user_id,
                "carteira": wallet,
                "pode_visualizar": bool(item.get("pode_visualizar", True)),
                "pode_criar": bool(item.get("pode_criar", True)),
                "pode_editar": bool(item.get("pode_editar", True)),
                "pode_transicionar": bool(item.get("pode_transicionar")),
                "pode_exportar": bool(item.get("pode_exportar")),
            })

        return {
            "nome": name,
            "slug": self._slug(payload.get("slug") or name),
            "descricao": str(payload.get("descricao") or "").strip(),
            "tipo": tool_type,
            "icone": str(payload.get("icone") or "").strip() or None,
            "cor": str(payload.get("cor") or "").strip() or None,
            "destaque_gerencial": bool(payload.get("destaque_gerencial")),
            "configuracao": configuration,
            "campos": fields,
            "statuses": statuses,
            "transicoes": transitions,
            "permissoes": permissions,
        }

    @staticmethod
    def _iso(value):
        return value.isoformat() if value else None

    @staticmethod
    def _actor_username(actor: dict[str, Any] | str | None) -> str:
        if isinstance(actor, dict):
            return str(actor.get("username") or "").strip()
        return str(actor or "").strip()

    def _negocial_actor_id(self, conn, actor: dict[str, Any] | str | None) -> int | None:
        username = self._actor_username(actor)
        if not username:
            return None
        row = conn.execute(
            "SELECT id FROM users WHERE LOWER(username) = LOWER(%s) LIMIT 1",
            (username,),
        ).fetchone()
        return int(row["id"]) if row else None

    def _purge_expired_tools(self, conn) -> list[str]:
        expired = conn.execute(
            """
            SELECT id, nome
            FROM ferramentas
            WHERE deleted_at IS NOT NULL AND purge_after <= NOW()
            FOR UPDATE
            """
        ).fetchall()
        if not expired:
            return []

        removed_names: list[str] = []
        storage_keys: list[str] = []
        for tool in expired:
            tool_id = int(tool["id"])
            removed_names.append(str(tool["nome"]))
            attachments = conn.execute(
                """
                SELECT a.storage_key
                FROM ferramenta_anexos a
                JOIN ferramenta_registros r ON r.id = a.registro_id
                WHERE r.ferramenta_id = %s
                """,
                (tool_id,),
            ).fetchall()
            storage_keys.extend(str(row["storage_key"]) for row in attachments if row["storage_key"])
            conn.execute(
                "DELETE FROM carteira_ferramentas_config WHERE tool_key = %s",
                (f"tool:{tool_id}",),
            )
            # Registros usam RESTRICT para preservar dados durante o uso normal.
            # Na expiração confirmada da lixeira, a remoção é intencional e explícita.
            conn.execute("DELETE FROM ferramenta_registros WHERE ferramenta_id = %s", (tool_id,))
            conn.execute("DELETE FROM ferramentas WHERE id = %s", (tool_id,))

        self._bump_version(conn)
        for storage_key in storage_keys:
            for root in self._attachment_roots():
                candidate = (root / storage_key).resolve()
                if root in candidate.parents and candidate.is_file():
                    try:
                        candidate.unlink()
                    except OSError:
                        pass
                    break
        return removed_names

    def purge_expired_tools(self) -> dict[str, Any]:
        if self.negocial.database_backend != "postgresql":
            return {"ok": True, "removed": 0, "items": []}
        with self.negocial._connect_postgres() as conn:
            names = self._purge_expired_tools(conn)
        return {"ok": True, "removed": len(names), "items": names}

    def list_tools(self) -> list[dict[str, Any]]:
        if self.negocial.database_backend != "postgresql":
            return []
        with self.negocial._connect_postgres() as conn:
            self._purge_expired_tools(conn)
            tools = conn.execute(
                """
                SELECT f.*,
                       (SELECT COUNT(*) FROM ferramenta_registros r WHERE r.ferramenta_id = f.id AND r.active) AS registros,
                       (SELECT COUNT(*) FROM ferramenta_permissoes p WHERE p.ferramenta_id = f.id) AS permissoes
                FROM ferramentas f
                ORDER BY f.nome
                """
            ).fetchall()
            versions = conn.execute(
                """
                SELECT id, ferramenta_id, numero, status, configuracao_json,
                       created_at, published_at, archived_at
                FROM ferramenta_versoes
                ORDER BY ferramenta_id, numero DESC
                """
            ).fetchall()
            wallet_links = conn.execute(
                """
                SELECT ferramenta_id, COUNT(DISTINCT carteira) AS total
                FROM (
                    SELECT ferramenta_id, UPPER(carteira) AS carteira
                    FROM ferramenta_permissoes
                    WHERE carteira IS NOT NULL AND carteira <> '' AND pode_visualizar
                    UNION
                    SELECT CAST(SUBSTRING(tool_key FROM 6) AS INTEGER) AS ferramenta_id,
                           UPPER(carteira) AS carteira
                    FROM carteira_ferramentas_config
                    WHERE enabled AND tool_key ~ '^tool:[0-9]+$'
                ) links
                GROUP BY ferramenta_id
                """
            ).fetchall()
        by_tool: dict[int, list] = {}
        for version in versions:
            by_tool.setdefault(int(version["ferramenta_id"]), []).append({
                "id": int(version["id"]),
                "numero": int(version["numero"]),
                "status": version["status"],
                "created_at": self._iso(version["created_at"]),
                "published_at": self._iso(version["published_at"]),
                "archived_at": self._iso(version["archived_at"]),
            })
        links_by_tool = {int(row["ferramenta_id"]): int(row["total"] or 0) for row in wallet_links}
        return [{
            "id": int(row["id"]),
            "nome": row["nome"],
            "slug": row["slug"],
            "descricao": row["descricao"] or "",
            "tipo": row["tipo"],
            "icone": row["icone"],
            "cor": row["cor"],
            "active": bool(row["active"]),
            "destaque_gerencial": bool(row["destaque_gerencial"]),
            "exclusao_pendente": bool(row["deleted_at"]),
            "deleted_at": self._iso(row["deleted_at"]),
            "purge_after": self._iso(row["purge_after"]),
            "registros": int(row["registros"] or 0),
            "permissoes": int(row["permissoes"] or 0),
            "carteiras_vinculadas": links_by_tool.get(int(row["id"]), 0),
            "pode_inativar": not row["deleted_at"] and links_by_tool.get(int(row["id"]), 0) == 0,
            "pode_excluir": not bool(row["deleted_at"]),
            "versoes": by_tool.get(int(row["id"]), []),
        } for row in tools]

    def list_highlighted_tools(self) -> list[dict[str, Any]]:
        if self.negocial.database_backend != "postgresql":
            return []
        with self.negocial._connect_postgres() as conn:
            rows = conn.execute(
                """
                SELECT f.id, f.nome, f.slug, f.descricao, f.icone, f.cor
                FROM ferramentas f
                WHERE f.active
                  AND f.deleted_at IS NULL
                  AND f.destaque_gerencial
                  AND EXISTS (
                      SELECT 1 FROM ferramenta_versoes v
                      WHERE v.ferramenta_id = f.id AND v.status = 'PUBLICADA'
                  )
                ORDER BY f.nome
                """
            ).fetchall()
        return [{
            "id": int(row["id"]),
            "nome": row["nome"],
            "slug": row["slug"],
            "descricao": row["descricao"] or "",
            "icone": row["icone"] or "F",
            "cor": row["cor"] or "#2563eb",
        } for row in rows]

    @staticmethod
    def _tool_usage(conn, tool_id: int) -> tuple[int, int]:
        row = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM ferramenta_registros WHERE ferramenta_id = %s) AS registros,
                (SELECT COUNT(DISTINCT carteira) FROM (
                    SELECT UPPER(carteira) AS carteira
                    FROM ferramenta_permissoes
                    WHERE ferramenta_id = %s AND carteira IS NOT NULL
                      AND carteira <> '' AND pode_visualizar
                    UNION
                    SELECT UPPER(carteira) AS carteira
                    FROM carteira_ferramentas_config
                    WHERE tool_key = %s AND enabled
                ) links) AS carteiras
            """,
            (tool_id, tool_id, f"tool:{tool_id}"),
        ).fetchone()
        return int(row["registros"] or 0), int(row["carteiras"] or 0)

    def set_tool_active(self, tool_id: int, active: bool) -> dict[str, Any]:
        with self.negocial._connect_postgres() as conn:
            self._purge_expired_tools(conn)
            tool = conn.execute(
                "SELECT id, active FROM ferramentas WHERE id = %s AND deleted_at IS NULL",
                (tool_id,),
            ).fetchone()
            if not tool:
                raise ValueError("Ferramenta nao encontrada ou esta na lixeira.")
            _, wallets = self._tool_usage(conn, tool_id)
            if not active and wallets:
                raise ValueError(
                    f"Remova a ferramenta das {wallets} carteira(s) vinculada(s) antes de inativar."
                )
            conn.execute(
                """
                UPDATE ferramentas
                SET active = %s,
                    destaque_gerencial = CASE WHEN %s THEN destaque_gerencial ELSE FALSE END,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (bool(active), bool(active), tool_id),
            )
            self._bump_version(conn)
        return self.get_tool(tool_id)

    def delete_tool(self, tool_id: int, actor: dict[str, Any] | str | None = None) -> dict[str, Any]:
        with self.negocial._connect_postgres() as conn:
            self._purge_expired_tools(conn)
            tool = conn.execute(
                """
                SELECT id, nome, active, destaque_gerencial
                FROM ferramentas
                WHERE id = %s AND deleted_at IS NULL
                FOR UPDATE
                """,
                (tool_id,),
            ).fetchone()
            if not tool:
                raise ValueError("Ferramenta nao encontrada ou ja esta na lixeira.")
            wallet_rows = conn.execute(
                """
                SELECT carteira, enabled
                FROM carteira_ferramentas_config
                WHERE tool_key = %s
                ORDER BY carteira
                """,
                (f"tool:{tool_id}",),
            ).fetchall()
            snapshot = {
                "active": bool(tool["active"]),
                "destaque_gerencial": bool(tool["destaque_gerencial"]),
                "carteiras": [
                    {"carteira": row["carteira"], "enabled": bool(row["enabled"])}
                    for row in wallet_rows
                ],
            }
            actor_id = self._negocial_actor_id(conn, actor)
            conn.execute(
                """
                UPDATE carteira_ferramentas_config
                SET enabled = FALSE, updated_at = NOW()
                WHERE tool_key = %s
                """,
                (f"tool:{tool_id}",),
            )
            conn.execute(
                """
                UPDATE ferramentas
                SET active = FALSE,
                    destaque_gerencial = FALSE,
                    deleted_at = NOW(),
                    purge_after = NOW() + INTERVAL '3 days',
                    deleted_by = %s,
                    deletion_snapshot_json = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (actor_id, json.dumps(snapshot, ensure_ascii=False), tool_id),
            )
            for row in wallet_rows:
                self._bump_scope(conn, f"carteira-ferramentas:{str(row['carteira']).upper()}")
            self._bump_version(conn)
            result = conn.execute(
                "SELECT deleted_at, purge_after FROM ferramentas WHERE id = %s",
                (tool_id,),
            ).fetchone()
        return {
            "id": tool_id,
            "nome": tool["nome"],
            "deleted_at": self._iso(result["deleted_at"]),
            "purge_after": self._iso(result["purge_after"]),
        }

    def restore_tool(self, tool_id: int) -> dict[str, Any]:
        with self.negocial._connect_postgres() as conn:
            self._purge_expired_tools(conn)
            tool = conn.execute(
                """
                SELECT id, deletion_snapshot_json
                FROM ferramentas
                WHERE id = %s AND deleted_at IS NOT NULL AND purge_after > NOW()
                FOR UPDATE
                """,
                (tool_id,),
            ).fetchone()
            if not tool:
                raise ValueError("Ferramenta nao encontrada ou o prazo de restauracao expirou.")
            snapshot = tool["deletion_snapshot_json"] or {}
            active = bool(snapshot.get("active", False))
            highlighted = bool(snapshot.get("destaque_gerencial", False)) and active
            conn.execute(
                """
                UPDATE ferramentas
                SET active = %s,
                    destaque_gerencial = %s,
                    deleted_at = NULL,
                    purge_after = NULL,
                    deleted_by = NULL,
                    deletion_snapshot_json = '{}'::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (active, highlighted, tool_id),
            )
            for wallet in snapshot.get("carteiras") or []:
                carteira = str(wallet.get("carteira") or "").strip()
                if not carteira:
                    continue
                conn.execute(
                    """
                    UPDATE carteira_ferramentas_config
                    SET enabled = %s, updated_at = NOW()
                    WHERE carteira = %s AND tool_key = %s
                    """,
                    (bool(wallet.get("enabled")), carteira, f"tool:{tool_id}"),
                )
                self._bump_scope(conn, f"carteira-ferramentas:{carteira.upper()}")
            self._bump_version(conn)
        return self.get_tool(tool_id)

    def wallet_tool_settings(self, carteira: str) -> dict[str, Any]:
        wallet = str(carteira or "").strip().upper()
        if not wallet:
            raise ValueError("Informe a carteira.")
        with self.negocial._connect_postgres() as conn:
            configured = conn.execute(
                """
                SELECT tool_key, enabled
                FROM carteira_ferramentas_config
                WHERE UPPER(carteira) = %s
                """,
                (wallet,),
            ).fetchall()
        states = {str(row["tool_key"]).lower(): bool(row["enabled"]) for row in configured}
        items = [
            {"key": "producao", "nome": "Producao diaria", "enabled": True, "locked": True},
            {"key": "pareceres", "nome": "Pareceres", "enabled": states.get("pareceres", True), "locked": False},
            {
                "key": "colchao",
                "nome": "Colchao",
                "enabled": states.get("colchao", wallet in {"ALPHA", "BETA"}),
                "locked": False,
            },
        ]
        for tool in self.list_tools():
            if not tool["active"]:
                continue
            key = f"tool:{tool['id']}"
            items.append({
                "key": key,
                "nome": tool["nome"],
                "enabled": states.get(key, True),
                "locked": False,
                "tool_id": tool["id"],
            })
        return {"carteira": wallet, "items": items}

    def set_wallet_tool(
        self,
        carteira: str,
        tool_key: str,
        enabled: bool,
        actor: dict[str, Any] | str,
    ) -> dict[str, Any]:
        wallet = str(carteira or "").strip().upper()
        key = str(tool_key or "").strip().lower()
        if not wallet or not key:
            raise ValueError("Carteira e ferramenta sao obrigatorias.")
        if key == "producao" and not enabled:
            raise ValueError("Producao diaria nao pode ser desativada.")
        if key not in {"producao", "pareceres", "colchao"}:
            match = re.fullmatch(r"tool:(\d+)", key)
            if not match:
                raise ValueError("Ferramenta invalida.")
            if not any(item["id"] == int(match.group(1)) for item in self.list_tools()):
                raise ValueError("Ferramenta nao encontrada.")
        username = self._actor_username(actor)
        with self.negocial._connect_postgres() as conn:
            conn.execute(
                """
                INSERT INTO carteira_ferramentas_config
                    (carteira, tool_key, enabled, updated_by, created_at, updated_at)
                VALUES (%s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (carteira, tool_key)
                DO UPDATE SET enabled = EXCLUDED.enabled,
                              updated_by = EXCLUDED.updated_by,
                              updated_at = NOW()
                """,
                (wallet, key, bool(enabled), username or None),
            )
            self._bump_scope(conn, f"carteira-ferramentas:{wallet}")
            self._bump_version(conn)
        return self.wallet_tool_settings(wallet)

    def get_tool(self, tool_id: int, version_id: int | None = None) -> dict[str, Any]:
        with self.negocial._connect_postgres() as conn:
            tool = conn.execute("SELECT * FROM ferramentas WHERE id = %s", (tool_id,)).fetchone()
            if not tool:
                raise ValueError("Ferramenta nao encontrada.")
            if version_id:
                version = conn.execute(
                    "SELECT * FROM ferramenta_versoes WHERE ferramenta_id = %s AND id = %s",
                    (tool_id, version_id),
                ).fetchone()
            else:
                version = conn.execute(
                    """
                    SELECT * FROM ferramenta_versoes
                    WHERE ferramenta_id = %s
                    ORDER BY CASE status WHEN 'RASCUNHO' THEN 0 WHEN 'PUBLICADA' THEN 1 ELSE 2 END, numero DESC
                    LIMIT 1
                    """,
                    (tool_id,),
                ).fetchone()
            if not version:
                raise ValueError("Versao da ferramenta nao encontrada.")
            fields = conn.execute(
                "SELECT * FROM ferramenta_campos WHERE versao_id = %s ORDER BY etapa, ordem, id",
                (version["id"],),
            ).fetchall()
            statuses = conn.execute(
                "SELECT * FROM ferramenta_status WHERE versao_id = %s ORDER BY ordem, id",
                (version["id"],),
            ).fetchall()
            transitions = conn.execute(
                "SELECT * FROM ferramenta_transicoes WHERE versao_id = %s ORDER BY id",
                (version["id"],),
            ).fetchall()
            permissions = conn.execute(
                "SELECT * FROM ferramenta_permissoes WHERE ferramenta_id = %s ORDER BY user_id NULLS LAST, carteira",
                (tool_id,),
            ).fetchall()
        return {
            "id": int(tool["id"]),
            "nome": tool["nome"],
            "slug": tool["slug"],
            "descricao": tool["descricao"] or "",
            "tipo": tool["tipo"],
            "icone": tool["icone"],
            "cor": tool["cor"],
            "active": bool(tool["active"]),
            "destaque_gerencial": bool(tool["destaque_gerencial"]),
            "versao_id": int(version["id"]),
            "versao": int(version["numero"]),
            "versao_status": version["status"],
            "configuracao": version["configuracao_json"] or {},
            "campos": [{
                "id": int(row["id"]), "chave": row["chave"], "nome": row["nome"], "tipo": row["tipo"],
                "ordem": int(row["ordem"]), "etapa": int(row["etapa"]), "obrigatorio": bool(row["obrigatorio"]),
                "somente_leitura": bool(row["somente_leitura"]),
                "visivel_negocial": bool(row["visivel_negocial"]), "visivel_gerencial": bool(row["visivel_gerencial"]),
                "opcoes": row["opcoes_json"] or [], "validacao": row["validacao_json"] or {},
                "condicao": row["condicao_json"] or {}, "valor_padrao": row["valor_padrao_json"],
            } for row in fields],
            "statuses": [{
                "codigo": row["codigo"], "nome": row["nome"], "cor": row["cor"], "ordem": int(row["ordem"]),
                "inicial": bool(row["inicial"]), "final": bool(row["final"]),
            } for row in statuses],
            "transicoes": [{
                "origem_codigo": row["origem_codigo"], "destino_codigo": row["destino_codigo"],
                "nome": row["nome"], "exige_justificativa": bool(row["exige_justificativa"]),
                "permite_negociador": bool(row["permite_negociador"]),
                "permite_gerencial": bool(row["permite_gerencial"]),
                "configuracao": row["configuracao_json"] or {},
            } for row in transitions],
            "permissoes": [{
                "user_id": int(row["user_id"]) if row["user_id"] else None,
                "carteira": row["carteira"],
                "pode_visualizar": bool(row["pode_visualizar"]), "pode_criar": bool(row["pode_criar"]),
                "pode_editar": bool(row["pode_editar"]), "pode_transicionar": bool(row["pode_transicionar"]),
                "pode_exportar": bool(row["pode_exportar"]),
            } for row in permissions],
        }

    def save_draft(self, payload: dict[str, Any], actor: dict[str, Any] | str | None = None) -> dict[str, Any]:
        data = self._validate(payload)
        tool_id = int(payload.get("id") or 0)
        with self.negocial._connect_postgres() as conn:
            actor_id = self._negocial_actor_id(conn, actor)
            if tool_id:
                tool = conn.execute("SELECT * FROM ferramentas WHERE id = %s", (tool_id,)).fetchone()
                if not tool:
                    raise ValueError("Ferramenta nao encontrada.")
                if tool["deleted_at"]:
                    raise ValueError("Restaure a ferramenta antes de editar o rascunho.")
                version = conn.execute(
                    "SELECT * FROM ferramenta_versoes WHERE ferramenta_id = %s AND status = 'RASCUNHO' ORDER BY numero DESC LIMIT 1",
                    (tool_id,),
                ).fetchone()
                if not version:
                    raise ValueError("Crie uma nova versao antes de editar.")
                conn.execute(
                    """
                    UPDATE ferramentas SET nome = %s, descricao = %s, tipo = %s, icone = %s,
                        cor = %s, destaque_gerencial = %s, updated_at = NOW() WHERE id = %s
                    """,
                    (
                        data["nome"], data["descricao"], data["tipo"], data["icone"], data["cor"],
                        data["destaque_gerencial"], tool_id,
                    ),
                )
                version_id = int(version["id"])
                conn.execute("UPDATE ferramenta_versoes SET configuracao_json = %s::jsonb WHERE id = %s",
                             (json.dumps(data["configuracao"], ensure_ascii=False), version_id))
                conn.execute("DELETE FROM ferramenta_campos WHERE versao_id = %s", (version_id,))
                conn.execute("DELETE FROM ferramenta_status WHERE versao_id = %s", (version_id,))
                conn.execute("DELETE FROM ferramenta_transicoes WHERE versao_id = %s", (version_id,))
            else:
                if conn.execute("SELECT 1 FROM ferramentas WHERE slug = %s", (data["slug"],)).fetchone():
                    raise ValueError("Ja existe uma ferramenta com este nome.")
                tool = conn.execute(
                    """
                    INSERT INTO ferramentas
                        (nome, slug, descricao, tipo, icone, cor, destaque_gerencial, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                    """,
                    (
                        data["nome"], data["slug"], data["descricao"], data["tipo"], data["icone"],
                        data["cor"], data["destaque_gerencial"], actor_id,
                    ),
                ).fetchone()
                tool_id = int(tool["id"])
                version = conn.execute(
                    """
                    INSERT INTO ferramenta_versoes
                        (ferramenta_id, numero, status, configuracao_json, created_by)
                    VALUES (%s, 1, 'RASCUNHO', %s::jsonb, %s) RETURNING id
                    """,
                    (tool_id, json.dumps(data["configuracao"], ensure_ascii=False), actor_id),
                ).fetchone()
                version_id = int(version["id"])

            for field in data["campos"]:
                conn.execute(
                    """
                    INSERT INTO ferramenta_campos (
                        versao_id, chave, nome, tipo, ordem, etapa, obrigatorio, somente_leitura,
                        visivel_negocial, visivel_gerencial, opcoes_json, validacao_json,
                        condicao_json, valor_padrao_json
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb
                    )
                    """,
                    (
                        version_id, field["chave"], field["nome"], field["tipo"], field["ordem"], field["etapa"],
                        field["obrigatorio"], field["somente_leitura"], field["visivel_negocial"],
                        field["visivel_gerencial"], json.dumps(field["opcoes"], ensure_ascii=False),
                        json.dumps(field["validacao"], ensure_ascii=False),
                        json.dumps(field["condicao"], ensure_ascii=False),
                        json.dumps(field["valor_padrao"], ensure_ascii=False),
                    ),
                )
            for item in data["statuses"]:
                conn.execute(
                    """
                    INSERT INTO ferramenta_status
                        (versao_id, codigo, nome, cor, ordem, inicial, final)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (version_id, item["codigo"], item["nome"], item["cor"], item["ordem"], item["inicial"], item["final"]),
                )
            for item in data["transicoes"]:
                conn.execute(
                    """
                    INSERT INTO ferramenta_transicoes (
                        versao_id, origem_codigo, destino_codigo, nome, exige_justificativa,
                        permite_negociador, permite_gerencial, configuracao_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        version_id, item["origem_codigo"], item["destino_codigo"], item["nome"],
                        item["exige_justificativa"], item["permite_negociador"], item["permite_gerencial"],
                        json.dumps(item["configuracao"], ensure_ascii=False),
                    ),
                )
            conn.execute("DELETE FROM ferramenta_permissoes WHERE ferramenta_id = %s", (tool_id,))
            for item in data["permissoes"]:
                conn.execute(
                    """
                    INSERT INTO ferramenta_permissoes (
                        ferramenta_id, user_id, carteira, pode_visualizar, pode_criar,
                        pode_editar, pode_transicionar, pode_exportar
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        tool_id, item["user_id"], item["carteira"], item["pode_visualizar"],
                        item["pode_criar"], item["pode_editar"], item["pode_transicionar"], item["pode_exportar"],
                    ),
                )
            self._bump_version(conn)
        return self.get_tool(tool_id, version_id)

    def publish(self, tool_id: int, actor: dict[str, Any] | str | None = None) -> dict[str, Any]:
        with self.negocial._connect_postgres() as conn:
            actor_id = self._negocial_actor_id(conn, actor)
            if not conn.execute(
                "SELECT 1 FROM ferramentas WHERE id = %s AND deleted_at IS NULL",
                (tool_id,),
            ).fetchone():
                raise ValueError("Restaure a ferramenta antes de publicar.")
            version = conn.execute(
                "SELECT * FROM ferramenta_versoes WHERE ferramenta_id = %s AND status = 'RASCUNHO' ORDER BY numero DESC LIMIT 1",
                (tool_id,),
            ).fetchone()
            if not version:
                raise ValueError("Rascunho nao encontrado.")
            if not conn.execute("SELECT 1 FROM ferramenta_permissoes WHERE ferramenta_id = %s LIMIT 1", (tool_id,)).fetchone():
                raise ValueError("Defina ao menos uma carteira ou usuario antes de publicar.")
            conn.execute(
                "UPDATE ferramenta_versoes SET status = 'ARQUIVADA', archived_at = NOW() WHERE ferramenta_id = %s AND status = 'PUBLICADA'",
                (tool_id,),
            )
            conn.execute(
                """
                UPDATE ferramenta_versoes SET status = 'PUBLICADA', published_by = %s, published_at = NOW()
                WHERE id = %s
                """,
                (actor_id, version["id"]),
            )
            self._bump_version(conn)
        return self.get_tool(tool_id, int(version["id"]))

    def create_next_version(self, tool_id: int, actor: dict[str, Any] | str | None = None) -> dict[str, Any]:
        with self.negocial._connect_postgres() as conn:
            actor_id = self._negocial_actor_id(conn, actor)
            if not conn.execute(
                "SELECT 1 FROM ferramentas WHERE id = %s AND deleted_at IS NULL",
                (tool_id,),
            ).fetchone():
                raise ValueError("Restaure a ferramenta antes de criar uma versao.")
            if conn.execute(
                "SELECT 1 FROM ferramenta_versoes WHERE ferramenta_id = %s AND status = 'RASCUNHO'",
                (tool_id,),
            ).fetchone():
                raise ValueError("A ferramenta ja possui um rascunho.")
            source = conn.execute(
                "SELECT * FROM ferramenta_versoes WHERE ferramenta_id = %s AND status = 'PUBLICADA'",
                (tool_id,),
            ).fetchone()
            if not source:
                raise ValueError("Versao publicada nao encontrada.")
            next_number = int(conn.execute(
                "SELECT COALESCE(MAX(numero), 0) + 1 AS numero FROM ferramenta_versoes WHERE ferramenta_id = %s",
                (tool_id,),
            ).fetchone()["numero"])
            target = conn.execute(
                """
                INSERT INTO ferramenta_versoes
                    (ferramenta_id, numero, status, configuracao_json, created_by)
                VALUES (%s, %s, 'RASCUNHO', %s::jsonb, %s) RETURNING id
                """,
                (tool_id, next_number, json.dumps(source["configuracao_json"] or {}), actor_id),
            ).fetchone()
            target_id = int(target["id"])
            for table, columns in (
                ("ferramenta_campos", "chave,nome,tipo,ordem,etapa,obrigatorio,somente_leitura,visivel_negocial,visivel_gerencial,opcoes_json,validacao_json,condicao_json,valor_padrao_json"),
                ("ferramenta_status", "codigo,nome,cor,ordem,inicial,final"),
                ("ferramenta_transicoes", "origem_codigo,destino_codigo,nome,exige_justificativa,permite_negociador,permite_gerencial,configuracao_json"),
            ):
                conn.execute(
                    f"INSERT INTO {table} (versao_id,{columns}) SELECT %s,{columns} FROM {table} WHERE versao_id = %s",
                    (target_id, source["id"]),
                )
            self._bump_version(conn)
        return self.get_tool(tool_id, target_id)

    @staticmethod
    def _bump_version(conn) -> None:
        conn.execute(
            """
            INSERT INTO operational_versions (scope, version, updated_at)
            VALUES ('ferramentas', 1, NOW())
            ON CONFLICT (scope)
            DO UPDATE SET version = operational_versions.version + 1, updated_at = NOW()
            """
        )

    def list_records(
        self,
        tool_id: int,
        *,
        status: str = "",
        carteira: str = "",
        usuario: str = "",
        query: str = "",
        limit: int = 1000,
    ) -> dict[str, Any]:
        clauses = ["r.ferramenta_id = %s", "r.active = TRUE"]
        params: list[Any] = [tool_id]
        aggregate_clauses = list(clauses)
        aggregate_params: list[Any] = list(params)
        if status:
            clauses.append("UPPER(r.status_codigo) = UPPER(%s)")
            params.append(status)
        if carteira:
            clauses.append("UPPER(COALESCE(r.carteira, '')) = UPPER(%s)")
            params.append(carteira)
            aggregate_clauses.append("UPPER(COALESCE(r.carteira, '')) = UPPER(%s)")
            aggregate_params.append(carteira)
        if usuario:
            clauses.append("LOWER(COALESCE(r.owner_username, '')) = LOWER(%s)")
            params.append(usuario)
            aggregate_clauses.append("LOWER(COALESCE(r.owner_username, '')) = LOWER(%s)")
            aggregate_params.append(usuario)
        if query:
            search_clause = (
                "(COALESCE(r.titulo, '') ILIKE %s OR COALESCE(r.owner_username, '') ILIKE %s "
                "OR COALESCE(r.carteira, '') ILIKE %s OR r.payload_json::text ILIKE %s)"
            )
            clauses.append(search_clause)
            aggregate_clauses.append(search_clause)
            search = f"%{query.strip()}%"
            params.extend([search, search, search, search])
            aggregate_params.extend([search, search, search, search])
        params.append(max(1, min(int(limit or 1000), 10000)))
        with self.negocial._connect_postgres() as conn:
            published = conn.execute(
                """
                SELECT id FROM ferramenta_versoes
                WHERE ferramenta_id = %s AND status = 'PUBLICADA'
                LIMIT 1
                """,
                (tool_id,),
            ).fetchone()
            rows = conn.execute(
                f"""
                SELECT r.id, r.versao_id, r.owner_user_id, r.owner_username, r.carteira,
                       r.status_codigo, r.titulo, r.payload_json, r.created_at, r.updated_at
                FROM ferramenta_registros r
                WHERE {' AND '.join(clauses)}
                ORDER BY r.updated_at DESC, r.id DESC
                LIMIT %s
                """,
                tuple(params),
            ).fetchall()
            status_rows = conn.execute(
                f"""
                SELECT r.status_codigo, COUNT(*) AS total
                FROM ferramenta_registros r
                WHERE {' AND '.join(aggregate_clauses)}
                GROUP BY r.status_codigo
                """,
                tuple(aggregate_params),
            ).fetchall()
        definition = self.get_tool(tool_id, int(published["id"]) if published else None)
        items = [{
            "id": int(row["id"]),
            "versao_id": int(row["versao_id"]),
            "owner_user_id": int(row["owner_user_id"]) if row["owner_user_id"] else None,
            "negociador": row["owner_username"] or "",
            "carteira": row["carteira"] or "",
            "status": row["status_codigo"],
            "titulo": row["titulo"] or "",
            "payload": row["payload_json"] or {},
            "created_at": self._iso(row["created_at"]),
            "updated_at": self._iso(row["updated_at"]),
        } for row in rows]
        status_counts = {str(row["status_codigo"]): int(row["total"] or 0) for row in status_rows}
        return {
            "definition": definition,
            "items": items,
            "total": sum(status_counts.values()),
            "filtered_total": len(items),
            "status_counts": status_counts,
        }

    def get_record(self, tool_id: int, record_id: int) -> dict[str, Any]:
        with self.negocial._connect_postgres() as conn:
            row = conn.execute(
                """
                SELECT r.* FROM ferramenta_registros r
                WHERE r.ferramenta_id = %s AND r.id = %s AND r.active = TRUE
                """,
                (tool_id, record_id),
            ).fetchone()
            if not row:
                raise ValueError("Registro nao encontrado.")
            published = conn.execute(
                """
                SELECT id FROM ferramenta_versoes
                WHERE ferramenta_id = %s AND status = 'PUBLICADA'
                ORDER BY numero DESC
                LIMIT 1
                """,
                (tool_id,),
            ).fetchone()
            events = conn.execute(
                """
                SELECT id, actor_username, tipo, status_anterior, status_novo,
                       justificativa, before_json, after_json, created_at
                FROM ferramenta_eventos WHERE registro_id = %s
                ORDER BY created_at, id
                """,
                (record_id,),
            ).fetchall()
            comments = conn.execute(
                """
                SELECT id, username, texto, created_at
                FROM ferramenta_comentarios WHERE registro_id = %s
                ORDER BY created_at, id
                """,
                (record_id,),
            ).fetchall()
            attachments = conn.execute(
                """
                SELECT id, campo_chave, nome, content_type, tamanho, sha256,
                       username, created_at
                FROM ferramenta_anexos
                WHERE registro_id = %s AND active = TRUE
                ORDER BY created_at, id
                """,
                (record_id,),
            ).fetchall()
        record_definition = self.get_tool(tool_id, int(row["versao_id"]))
        definition = (
            self.get_tool(tool_id, int(published["id"]))
            if published and int(published["id"]) != int(row["versao_id"])
            else record_definition
        )
        if definition is not record_definition:
            current_keys = {field["chave"] for field in definition["campos"]}
            legacy_fields = [
                field for field in record_definition["campos"]
                if field["chave"] not in current_keys
                and (row["payload_json"] or {}).get(field["chave"]) not in (None, "")
            ]
            definition["campos"] = [*definition["campos"], *legacy_fields]
            definition["record_version_id"] = int(row["versao_id"])
            definition["workflow_version_id"] = int(published["id"])
        return {
            "definition": definition,
            "item": {
                "id": int(row["id"]),
                "versao_id": int(row["versao_id"]),
                "negociador": row["owner_username"] or "",
                "carteira": row["carteira"] or "",
                "status": row["status_codigo"],
                "titulo": row["titulo"] or "",
                "payload": row["payload_json"] or {},
                "created_at": self._iso(row["created_at"]),
                "updated_at": self._iso(row["updated_at"]),
                "eventos": [{
                    "id": int(event["id"]),
                    "usuario": event["actor_username"] or "",
                    "tipo": event["tipo"],
                    "status_anterior": event["status_anterior"],
                    "status_novo": event["status_novo"],
                    "justificativa": event["justificativa"] or "",
                    "antes": event["before_json"],
                    "depois": event["after_json"],
                    "created_at": self._iso(event["created_at"]),
                } for event in events],
                "comentarios": [{
                    "id": int(comment["id"]),
                    "usuario": comment["username"] or "",
                    "texto": comment["texto"],
                    "created_at": self._iso(comment["created_at"]),
                } for comment in comments],
                "anexos": [{
                    "id": int(attachment["id"]),
                    "campo": attachment["campo_chave"] or "",
                    "nome": attachment["nome"],
                    "content_type": attachment["content_type"] or "application/octet-stream",
                    "tamanho": int(attachment["tamanho"] or 0),
                    "sha256": attachment["sha256"] or "",
                    "usuario": attachment["username"] or "",
                    "created_at": self._iso(attachment["created_at"]),
                } for attachment in attachments],
            },
        }

    def attachment_file(self, tool_id: int, record_id: int, attachment_id: int) -> tuple[str, bytes, str]:
        with self.negocial._connect_postgres() as conn:
            row = conn.execute(
                """
                SELECT a.nome, a.content_type, a.storage_key
                FROM ferramenta_anexos a
                JOIN ferramenta_registros r ON r.id = a.registro_id
                WHERE r.ferramenta_id = %s AND r.id = %s AND a.id = %s
                  AND r.active = TRUE AND a.active = TRUE
                """,
                (tool_id, record_id, attachment_id),
            ).fetchone()
        if not row:
            raise ValueError("Anexo nao encontrado.")
        target = None
        for root in self._attachment_roots():
            candidate = (root / str(row["storage_key"])).resolve()
            if root in candidate.parents and candidate.is_file():
                target = candidate
                break
        if target is None:
            raise ValueError("Arquivo do anexo nao encontrado.")
        content_type = row["content_type"] or mimetypes.guess_type(row["nome"])[0] or "application/octet-stream"
        return row["nome"], target.read_bytes(), content_type

    def transition_record(
        self,
        tool_id: int,
        record_id: int,
        target_status: str,
        justification: str,
        actor: dict[str, Any] | str,
    ) -> dict[str, Any]:
        target_status = self._key(target_status)
        clean_reason = str(justification or "").strip()
        actor_username = self._actor_username(actor)
        with self.negocial._connect_postgres() as conn:
            actor_id = self._negocial_actor_id(conn, actor)
            row = conn.execute(
                """
                SELECT r.*, v.id AS definition_version_id
                FROM ferramenta_registros r
                JOIN ferramenta_versoes v ON v.id = r.versao_id
                WHERE r.ferramenta_id = %s AND r.id = %s AND r.active = TRUE
                FOR UPDATE
                """,
                (tool_id, record_id),
            ).fetchone()
            if not row:
                raise ValueError("Registro nao encontrado.")
            published = conn.execute(
                """
                SELECT id FROM ferramenta_versoes
                WHERE ferramenta_id = %s AND status = 'PUBLICADA'
                ORDER BY numero DESC
                LIMIT 1
                """,
                (tool_id,),
            ).fetchone()
            workflow_version_id = int(published["id"]) if published else int(row["versao_id"])
            transition = conn.execute(
                """
                SELECT * FROM ferramenta_transicoes
                WHERE versao_id = %s AND origem_codigo = %s AND destino_codigo = %s
                """,
                (workflow_version_id, row["status_codigo"], target_status),
            ).fetchone()
            if not transition and workflow_version_id != int(row["versao_id"]):
                transition = conn.execute(
                    """
                    SELECT * FROM ferramenta_transicoes
                    WHERE versao_id = %s AND origem_codigo = %s AND destino_codigo = %s
                    """,
                    (row["versao_id"], row["status_codigo"], target_status),
                ).fetchone()
                if transition:
                    workflow_version_id = int(row["versao_id"])
            if not transition or not transition["permite_gerencial"]:
                raise ValueError("Transicao de status nao permitida.")
            if transition["exige_justificativa"] and not clean_reason:
                raise ValueError("Justificativa obrigatoria.")
            previous = row["status_codigo"]
            before_payload = dict(row["payload_json"] or {})
            after_payload = dict(before_payload)
            transition_config = dict(transition["configuracao_json"] or {})
            automation_log = []
            transition_fields = [dict(item) for item in conn.execute(
                    "SELECT chave, validacao_json FROM ferramenta_campos WHERE versao_id = %s",
                    (workflow_version_id,),
                ).fetchall()]
            field_keys = {item["chave"] for item in transition_fields}
            for raw_automation in transition_config.get("automacoes") or []:
                automation = dict(raw_automation or {})
                action = str(automation.get("tipo") or "").lower()
                key = self._key(automation.get("campo"))
                if action == "notificar":
                    automation_log.append({"tipo": action, "mensagem": str(automation.get("valor") or "").strip()})
                elif key in field_keys and action == "data_atual":
                    after_payload[key] = date.today().isoformat()
                    automation_log.append({"tipo": action, "campo": key, "valor": after_payload[key]})
                elif key in field_keys and action == "definir_valor":
                    after_payload[key] = automation.get("valor")
                    automation_log.append({"tipo": action, "campo": key, "valor": after_payload[key]})
                elif key in field_keys and action == "limpar_campo":
                    after_payload[key] = None
                    automation_log.append({"tipo": action, "campo": key, "valor": None})
            after_payload = self._apply_calculations(after_payload, transition_fields)
            conn.execute(
                "UPDATE ferramenta_registros SET status_codigo = %s, payload_json = %s::jsonb, updated_at = NOW() WHERE id = %s",
                (target_status, json.dumps(after_payload, ensure_ascii=False), record_id),
            )
            conn.execute(
                """
                INSERT INTO ferramenta_eventos (
                    registro_id, actor_user_id, actor_username, tipo,
                    status_anterior, status_novo, justificativa, before_json, after_json
                ) VALUES (%s, %s, %s, 'TRANSICAO', %s, %s, %s, %s::jsonb, %s::jsonb)
                """,
                (
                    record_id, actor_id, actor_username, previous, target_status, clean_reason or None,
                    json.dumps(before_payload, ensure_ascii=False),
                    json.dumps({"payload": after_payload, "automacoes": automation_log}, ensure_ascii=False),
                ),
            )
            self._bump_scope(conn, f"ferramenta:{row['ferramenta_id']}")
            self._bump_version(conn)
        return self.get_record(tool_id, record_id)

    def update_record_field(
        self,
        tool_id: int,
        record_id: int,
        field_key: str,
        value: Any,
        actor: dict[str, Any] | str,
    ) -> dict[str, Any]:
        key = self._key(field_key)
        if not key:
            raise ValueError("Campo invalido.")
        actor_username = self._actor_username(actor)
        with self.negocial._connect_postgres() as conn:
            actor_id = self._negocial_actor_id(conn, actor)
            row = conn.execute(
                """
                SELECT r.*, v.configuracao_json
                FROM ferramenta_registros r
                JOIN ferramenta_versoes v ON v.id = r.versao_id
                WHERE r.ferramenta_id = %s AND r.id = %s AND r.active = TRUE
                FOR UPDATE
                """,
                (tool_id, record_id),
            ).fetchone()
            if not row:
                raise ValueError("Registro nao encontrado.")
            field = conn.execute(
                """
                SELECT chave, nome, somente_leitura, visivel_gerencial
                FROM ferramenta_campos
                WHERE versao_id = %s AND chave = %s
                """,
                (row["versao_id"], key),
            ).fetchone()
            if not field or not field["visivel_gerencial"]:
                raise ValueError("Campo nao disponivel no gerencial.")
            if field["somente_leitura"]:
                raise ValueError("Este campo e somente leitura.")

            before = dict(row["payload_json"] or {})
            after = dict(before)
            after[key] = value
            calculation_fields = [dict(item) for item in conn.execute(
                "SELECT chave, validacao_json FROM ferramenta_campos WHERE versao_id = %s ORDER BY ordem, id",
                (row["versao_id"],),
            ).fetchall()]
            after = self._apply_calculations(after, calculation_fields)
            configuration = dict(row["configuracao_json"] or {})
            title_key = self._key(configuration.get("campo_titulo") or "")
            title = str(after.get(title_key) or row["titulo"] or "").strip() or None
            conn.execute(
                """
                UPDATE ferramenta_registros
                SET payload_json = %s::jsonb, titulo = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (json.dumps(after, ensure_ascii=False), title, record_id),
            )
            conn.execute(
                """
                INSERT INTO ferramenta_eventos (
                    registro_id, actor_user_id, actor_username, tipo,
                    status_anterior, status_novo, before_json, after_json
                ) VALUES (%s, %s, %s, 'EDICAO_GERENCIAL', %s, %s, %s::jsonb, %s::jsonb)
                """,
                (
                    record_id,
                    actor_id,
                    actor_username,
                    row["status_codigo"],
                    row["status_codigo"],
                    json.dumps(before, ensure_ascii=False),
                    json.dumps(after, ensure_ascii=False),
                ),
            )
            self._bump_scope(conn, f"ferramenta:{tool_id}")
            self._bump_version(conn)
        return self.get_record(tool_id, record_id)

    def add_comment(
        self,
        tool_id: int,
        record_id: int,
        text: str,
        actor: dict[str, Any] | str,
    ) -> dict[str, Any]:
        clean_text = str(text or "").strip()
        if not clean_text:
            raise ValueError("Informe o comentario.")
        actor_username = self._actor_username(actor)
        with self.negocial._connect_postgres() as conn:
            actor_id = self._negocial_actor_id(conn, actor)
            if not conn.execute(
                "SELECT 1 FROM ferramenta_registros WHERE ferramenta_id = %s AND id = %s AND active = TRUE",
                (tool_id, record_id),
            ).fetchone():
                raise ValueError("Registro nao encontrado.")
            conn.execute(
                """
                INSERT INTO ferramenta_comentarios (registro_id, user_id, username, texto)
                VALUES (%s, %s, %s, %s)
                """,
                (record_id, actor_id, actor_username, clean_text),
            )
            self._bump_scope(conn, f"ferramenta:{tool_id}")
        return self.get_record(tool_id, record_id)

    def report_xlsx(self, tool_id: int, filters: dict[str, str] | None = None) -> tuple[str, bytes]:
        filters = filters or {}
        result = self.list_records(
            tool_id,
            status=filters.get("status", ""),
            carteira=filters.get("carteira", ""),
            usuario=filters.get("usuario", ""),
            query=filters.get("q", ""),
            limit=10000,
        )
        definition = result["definition"]
        fields = [field for field in definition["campos"] if field["visivel_gerencial"]]
        use_status = definition["tipo"] != "CADASTRO" or definition["configuracao"].get("usar_status", True)
        headers = [
            "ID",
            *(["STATUS"] if use_status else []),
            "CARTEIRA",
            "NEGOCIADOR",
            *[field["nome"] for field in fields],
            "CRIADO EM",
            "ATUALIZADO EM",
        ]
        rows = []
        for item in result["items"]:
            row = {
                "ID": item["id"],
                "STATUS": item["status"],
                "CARTEIRA": item["carteira"],
                "NEGOCIADOR": item["negociador"],
                "CRIADO EM": item["created_at"],
                "ATUALIZADO EM": item["updated_at"],
            }
            for field in fields:
                value = item["payload"].get(field["chave"])
                row[field["nome"]] = ", ".join(map(str, value)) if isinstance(value, list) else value
            rows.append(row)
        content = self.report_export.xlsx_bytes(
            definition["nome"][:31] or "Ferramenta",
            headers,
            rows,
            lambda value: "" if value is None else str(value),
        )
        return f"{definition['slug']}-registros.xlsx", content

    def list_open_notifications(self, limit: int = 80) -> list[dict[str, Any]]:
        if self.negocial.database_backend != "postgresql":
            return []
        with self.negocial._connect_postgres() as conn:
            rows = conn.execute(
                """
                SELECT r.id, r.ferramenta_id, r.status_codigo, r.titulo, r.owner_username,
                       r.carteira, r.updated_at, r.payload_json, f.nome AS ferramenta_nome, f.slug,
                       v.id AS versao_publicada_id, v.configuracao_json,
                       COALESCE(s.nome, r.status_codigo) AS status_nome,
                       COALESCE(s.final, FALSE) AS status_final
                FROM ferramenta_registros r
                JOIN ferramentas f ON f.id = r.ferramenta_id AND f.active = TRUE
                JOIN LATERAL (
                    SELECT id, configuracao_json
                    FROM ferramenta_versoes
                    WHERE ferramenta_id = f.id AND status = 'PUBLICADA'
                    ORDER BY numero DESC
                    LIMIT 1
                ) v ON TRUE
                LEFT JOIN ferramenta_status s
                  ON s.versao_id = v.id AND s.codigo = r.status_codigo
                WHERE r.active = TRUE
                  AND COALESCE(v.configuracao_json #>> '{main_hub,enabled}', 'false') = 'true'
                ORDER BY r.updated_at DESC, r.id DESC
                LIMIT 1000
                """,
            ).fetchall()
            version_ids = sorted({int(row["versao_publicada_id"]) for row in rows})
            field_rows = conn.execute(
                """
                SELECT versao_id, chave, nome
                FROM ferramenta_campos
                WHERE versao_id = ANY(%s)
                ORDER BY versao_id, ordem, id
                """,
                (version_ids,),
            ).fetchall() if version_ids else []
        labels = {
            (int(row["versao_id"]), row["chave"]): row["nome"]
            for row in field_rows
        }
        result = []
        for row in rows:
            configuration = dict(row["configuracao_json"] or {})
            hub = dict(configuration.get("main_hub") or {})
            pending_statuses = {self._key(item) for item in hub.get("status_codes") or []}
            if self._key(row["status_codigo"]) not in pending_statuses:
                continue
            payload = dict(row["payload_json"] or {})
            version_id = int(row["versao_publicada_id"])
            field_keys = [self._key(item) for item in hub.get("field_keys") or []]
            fields = [{
                "key": key,
                "label": labels.get((version_id, key), key.replace("_", " ").title()),
                "value": payload.get(key),
            } for key in field_keys]
            title_key = self._key(configuration.get("campo_titulo"))
            result.append({
                "id": int(row["id"]),
                "tool_id": int(row["ferramenta_id"]),
                "ferramenta": row["ferramenta_nome"],
                "slug": row["slug"],
                "status": row["status_codigo"],
                "status_nome": row["status_nome"] or row["status_codigo"],
                "titulo": payload.get(title_key) or row["titulo"] or "Registro sem titulo",
                "negociador": row["owner_username"] or "Negociador nao informado",
                "carteira": row["carteira"] or "Carteira nao informada",
                "updated_at": self._iso(row["updated_at"]),
                "fields": fields,
            })
            if len(result) >= max(1, min(int(limit or 80), 500)):
                break
        return result

    @staticmethod
    def _bump_scope(conn, scope: str) -> None:
        conn.execute(
            """
            INSERT INTO operational_versions (scope, version, updated_at)
            VALUES (%s, 1, NOW())
            ON CONFLICT (scope)
            DO UPDATE SET version = operational_versions.version + 1, updated_at = NOW()
            """,
            (scope,),
        )
