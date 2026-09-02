from __future__ import annotations

from typing import Any


class OverviewBuilder:
    def build(self, events: list[dict[str, Any]], filters: dict[str, Any] | None = None, status: str = "unread") -> list[dict[str, Any]]:
        filters = filters or {}
        items = []
        for event in events:
            read_keys = event.get("read_keys", set())
            overview_changes = []
            for index, change in enumerate(event["delta"].get("changes", [])):
                for read_index, overview_change in self.expand_change(index, change, event):
                    if overview_change.get("type") == "initial_snapshot" or self.is_noop_change(overview_change):
                        continue
                    overview_changes.append((read_index, overview_change))
            for item in self.group_items(event, overview_changes, read_keys):
                if self.matches_status(item, status) and self.matches_filters(item, filters):
                    items.append(item)
        return sorted(items, key=lambda item: (item["dataHora"], item["id"]), reverse=True)

    def expand_change(self, index: int, change: dict[str, Any], event: dict[str, Any] | None = None) -> list[tuple[int, dict[str, Any]]]:
        if change.get("type") == "row_added":
            items = []
            for column_index, (column, value) in enumerate(self.row_values(change.get("after", {}), event).items()):
                items.append(
                    (
                        -(index * 1000 + column_index + 1),
                        {
                            "type": "cell_filled",
                            "origin_type": "row_added",
                            "row_id": change.get("row_id"),
                            "excel_row": change.get("after", {}).get("_excel_row") or change.get("row_id"),
                            "column": column,
                            "before": None,
                            "after": value,
                        },
                    )
                )
            return items
        if change.get("type") == "row_removed":
            items = []
            for column_index, (column, value) in enumerate(self.row_values(change.get("before", {}), event).items()):
                items.append(
                    (
                        -(index * 1000 + column_index + 1),
                        {
                            "type": "cell_cleared",
                            "origin_type": "row_removed",
                            "row_id": change.get("row_id"),
                            "excel_row": change.get("before", {}).get("_excel_row") or change.get("row_id"),
                            "column": column,
                            "before": value,
                            "after": None,
                        },
                    )
                )
            return items
        return [(index, change)]

    def row_values(self, row: dict[str, Any], event: dict[str, Any] | None = None) -> dict[str, Any]:
        public = self.public_row_values(row or {})
        carteira = str((event or {}).get("carteira") or public.get("CARTEIRA") or public.get("carteira") or "").strip().upper()
        allowed = self.allowed_columns(carteira)
        result: dict[str, Any] = {}
        for column in allowed:
            value = self.row_value_by_alias(public, column)
            if value in (None, "") and column not in ("DATA PAGAMENTO", "JUSTIFICATIVA", "AUTORIZACAO", "CPF/CNPJ", "PORTFOLIO"):
                continue
            result[column] = value
        if result:
            return result
        return public

    def public_row_values(self, row: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in row.items() if not key.startswith("_")}

    def allowed_columns(self, carteira: str) -> list[str]:
        if carteira == "ALPHA":
            return [
                "DATA",
                "DEBIT ID",
                "CPF/CNPJ",
                "CLIENTE",
                "DATA DO 1 ATRASO",
                "PORTFOLIO",
                "CARTEIRA",
                "VALOR TOTAL",
                "ENTRADA",
                "TIPO",
                "VENCIMENTO",
                "DATA PAGAMENTO",
                "STATUS",
                "JUSTIFICATIVA",
                "USUARIO",
            ]
        return [
            "DATA",
            "NPJ",
            "CLIENTE",
            "GECOR",
            "VALOR TOTAL",
            "ENTRADA",
            "TIPO",
            "VENCIMENTO",
            "DATA PAGAMENTO",
            "STATUS",
            "HONORARIOS",
            "% H.O",
            "AUTORIZACAO",
            "USUARIO",
        ]

    def row_value_by_alias(self, row: dict[str, Any], column: str) -> Any:
        aliases = {
            "DATA": ("DATA", "data_acordo", "DATA ACORDO"),
            "NPJ": ("NPJ", "npj"),
            "DEBIT ID": ("DEBIT ID", "debit_id", "NPJ", "npj"),
            "CPF/CNPJ": ("CPF/CNPJ", "CPF", "CNPJ", "cpf", "cnpj"),
            "CLIENTE": ("CLIENTE", "NOME CLIENTE", "NOME", "cliente"),
            "GECOR": ("GECOR", "gecor"),
            "DATA DO 1 ATRASO": ("DATA DO 1 ATRASO", "DATA DO 1Âº ATRASO", "data_primeiro_atraso"),
            "PORTFOLIO": ("PORTFOLIO", "portfolio"),
            "CARTEIRA": ("CARTEIRA", "carteira_alpha", "carteira"),
            "VALOR TOTAL": ("VALOR TOTAL", "VALOR DO ACORDO", "valor_total_acordo"),
            "ENTRADA": ("ENTRADA", "VALOR DA ENTRADA", "valor_entrada"),
            "TIPO": ("TIPO", "TIPO ACORDO", "PARCELADO OU Ã€ VISTA", "PARCELADO OU A VISTA", "tipo_acordo_label", "tipo_acordo"),
            "VENCIMENTO": ("VENCIMENTO", "DATA DE VENCIMENTO", "data_vencimento"),
            "DATA PAGAMENTO": ("DATA PAGAMENTO", "DATA DO PAGAMENTO", "data_pagamento"),
            "STATUS": ("STATUS", "status_label", "status"),
            "HONORARIOS": ("HONORARIOS", "HONORÃRIOS", "HONORÃƒÂRIOS", "valor_ho"),
            "% H.O": ("% H.O", "%", "percentual_ho"),
            "AUTORIZACAO": ("AUTORIZACAO", "AUTORIZADO?", "autorizacao_flexibilizacao"),
            "JUSTIFICATIVA": ("JUSTIFICATIVA", "justificativa_status"),
            "USUARIO": ("USUARIO", "NEGOCIADOR", "OPERADOR", "usuario"),
        }
        for key in aliases.get(column, (column,)):
            if key in row:
                return row.get(key)
        return None

    def group_items(self, event: dict[str, Any], changes: list[tuple[int, dict[str, Any]]], read_keys: set[tuple[int, int]]) -> list[dict[str, Any]]:
        groups: dict[tuple[str, str], list[tuple[int, dict[str, Any]]]] = {}
        passthrough: list[tuple[int, dict[str, Any]]] = []
        for read_index, change in changes:
            change_type = change.get("type")
            if change.get("origin_type") in ("row_added", "row_removed") or change_type == "cell_changed":
                groups.setdefault((change.get("origin_type") or "row_changed", str(change.get("row_id") or "")), []).append((read_index, change))
            else:
                passthrough.append((read_index, change))

        items = [self.item(event, read_index, change, read_keys) for read_index, change in passthrough]
        for (_group_type, _row_id), group_changes in groups.items():
            if len(group_changes) == 1 and group_changes[0][1].get("origin_type") not in ("row_added", "row_removed"):
                items.append(self.item(event, group_changes[0][0], group_changes[0][1], read_keys))
                continue
            items.append(self.group_item(event, group_changes, read_keys))
        return items

    def group_item(self, event: dict[str, Any], group_changes: list[tuple[int, dict[str, Any]]], read_keys: set[tuple[int, int]]) -> dict[str, Any]:
        first_change = group_changes[0][1]
        read_indices = [read_index for read_index, _change in group_changes]
        details = [self.detail(change) for _read_index, change in group_changes]
        client_name = self.client_name_from_changes([change for _read_index, change in group_changes]) or self.client_name_from_details(details)
        is_new = first_change.get("origin_type") == "row_added"
        is_removed = first_change.get("origin_type") == "row_removed"
        if is_new:
            campo = "Novo Cliente"
            tipo = "Novo cliente"
            antes = None
            depois = client_name or "Cliente sem nome"
        elif is_removed:
            campo = "Cliente removido"
            tipo = "Remocao de cliente"
            antes = client_name or "Cliente sem nome"
            depois = None
        else:
            campo = "Varios Campos Alterados"
            tipo = "Atualizacao"
            antes = f"{len(details)} campos antes"
            depois = f"{len(details)} campos depois"
        priority = max((self.priority_for_change(change, change.get("column", "")) for _read_index, change in group_changes), key=self.priority_rank)
        return {
            "id": f"OVR_{event['id']}_{','.join(str(index) for index in read_indices)}",
            "eventId": event["id"],
            "negociadorId": event.get("negociador_id"),
            "changeIndices": read_indices,
            "usuario": event["negociador_nome"],
            "responsavel": event["negociador_nome"],
            "carteira": event.get("carteira") or "",
            "dataHora": event["changed_at"],
            "campo": campo,
            "cliente": client_name,
            "antes": antes,
            "depois": depois,
            "lido": all((event["id"], read_index) in read_keys for read_index in read_indices),
            "tipo": tipo,
            "prioridade": priority,
            "sheet": event["sheet"],
            "arquivo": event["file_path"],
            "details": details,
        }

    def item(self, event: dict[str, Any], read_index: int, change: dict[str, Any], read_keys: set[tuple[int, int]]) -> dict[str, Any]:
        tipo = self.change_type_label(change.get("type", event["event_type"]))
        campo = change.get("column") or change.get("type") or "Estrutura"
        antes = change.get("before")
        depois = change.get("after")
        if change.get("type") == "row_added":
            campo = "Registro adicionado"
            depois = change.get("after")
        elif change.get("type") == "row_removed":
            campo = "Registro removido"
            antes = change.get("before")
        elif change.get("type") in ("column_added", "column_removed"):
            campo = change.get("column")
        elif change.get("type") == "new_month":
            campo = "Novo M\u00eas"
        priority = self.priority_for_change(change, campo)
        client_name = self.client_name_from_changes([change])
        return {
            "id": f"ALT_{event['id']}_{read_index}",
            "eventId": event["id"],
            "negociadorId": event.get("negociador_id"),
            "changeIndex": read_index,
            "usuario": event["negociador_nome"],
            "responsavel": event["negociador_nome"],
            "carteira": event.get("carteira") or "",
            "dataHora": event["changed_at"],
            "campo": campo,
            "cliente": client_name,
            "antes": antes,
            "depois": depois,
            "lido": (event["id"], read_index) in read_keys,
            "tipo": tipo,
            "prioridade": priority,
            "sheet": event["sheet"],
            "arquivo": event["file_path"],
            "details": [self.detail(change)],
        }

    def detail(self, change: dict[str, Any]) -> dict[str, Any]:
        return {
            "campo": change.get("column") or change.get("type") or "Estrutura",
            "linha": change.get("excel_row") or change.get("row_id"),
            "antes": change.get("before"),
            "depois": change.get("after"),
            "tipo": self.change_type_label(change.get("type", "")),
        }

    def is_noop_change(self, change: dict[str, Any]) -> bool:
        change_type = change.get("type")
        if change_type in {"column_added", "column_removed"}:
            return int(change.get("non_empty_values") or 0) <= 0
        if change_type in {"row_added", "row_removed"}:
            row = change.get("after") if change_type == "row_added" else change.get("before")
            return not any(self.normalized_value(value) for key, value in (row or {}).items() if not str(key).startswith("_"))
        if change_type not in {"cell_changed", "cell_filled", "cell_cleared"}:
            return False
        return self.normalized_value(change.get("before")) == self.normalized_value(change.get("after"))

    def normalized_value(self, value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if text.lower() in {"", "none", "null", "nan", "vazio"}:
            return ""
        return " ".join(text.split())

    def client_name_from_details(self, details: list[dict[str, Any]]) -> str:
        for detail in details:
            if self.is_client_column(detail["campo"]):
                value = detail.get("depois") if detail.get("depois") not in (None, "") else detail.get("antes")
                return str(value or "")
        return ""

    def client_name_from_changes(self, changes: list[dict[str, Any]]) -> str:
        for change in changes:
            for row_key in ("row_after", "row_before", "after", "before"):
                row = change.get(row_key)
                if isinstance(row, dict):
                    name = self.client_name_from_row(row)
                    if name:
                        return name
        return ""

    def client_name_from_row(self, row: dict[str, Any]) -> str:
        for key, value in row.items():
            if key.startswith("_"):
                continue
            if self.is_client_column(key) and value not in (None, ""):
                return str(value)
        return ""

    def is_client_column(self, column: Any) -> bool:
        normalized = str(column or "").strip().lower()
        return normalized in ("cliente", "nome", "nome do cliente", "client", "customer") or "cliente" in normalized

    def priority_rank(self, priority: str) -> int:
        return {"normal": 0, "alta": 1, "critica": 2}.get(priority, 0)

    def change_type_label(self, change_type: str) -> str:
        return {
            "cell_changed": "Atualizacao",
            "cell_filled": "Preenchimento",
            "cell_cleared": "Remocao de valor",
            "row_added": "Registro adicionado",
            "row_removed": "Registro removido",
            "column_added": "Coluna adicionada",
            "column_removed": "Coluna removida",
            "file_changed": "Atualizacao",
            "manual_update": "Atualizacao manual",
            "sheet_changed": "Troca de sheet",
            "new_month": "Novo M\u00eas",
        }.get(change_type, change_type)

    def priority_for_change(self, change: dict[str, Any], campo: str) -> str:
        change_type = change.get("type")
        if change_type == "new_month":
            return "alta"
        if change_type in ("row_removed", "column_removed", "cell_cleared"):
            return "critica"
        if change_type in ("row_added", "column_added", "cell_filled"):
            return "alta"
        if str(campo).lower() in ("status", "valor", "pagamento", "vencimento"):
            return "alta"
        return "normal"

    def matches_filters(self, item: dict[str, Any], filters: dict[str, Any]) -> bool:
        for key in ("usuario", "tipo", "prioridade"):
            value = str(filters.get(key, "")).strip().lower()
            if value and value not in str(item.get(key, "")).lower():
                return False
        date_value = str(filters.get("data", "")).strip()
        if date_value and not str(item["dataHora"]).startswith(date_value):
            return False
        return True

    def matches_status(self, item: dict[str, Any], status: str) -> bool:
        status = (status or "unread").lower()
        if status == "read":
            return bool(item.get("lido"))
        if status == "all":
            return True
        return not item.get("lido")
