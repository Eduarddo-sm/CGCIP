from __future__ import annotations

import json
import re
import secrets
import sqlite3
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from typing import Any


class NegocialProductionMixin:
    def read_producao_table(self, username: str) -> dict[str, Any]:
        username = self._clean_required(username, "Usuario")
        if self.database_backend == "postgresql":
            with self._connect_postgres() as conn:
                user = conn.execute(
                    "SELECT id, username, carteira FROM users WHERE username = %s AND COALESCE(password_hash, '') NOT LIKE %s",
                    (username, "$deleted$%"),
                ).fetchone()
                if not user:
                    raise ValueError(f"Usuario negocial nao encontrado: {username}")
                rows = conn.execute(
                    """
                    SELECT p.*, u.username AS usuario
                    FROM producao_unificada p
                    JOIN users u ON u.id = p.user_id
                    WHERE u.id = %s
                    ORDER BY p.data_acordo DESC, p.created_at DESC, p.id DESC
                    """,
                    (int(user["id"]),),
                ).fetchall()
            file_path = "Sistema Negocial PostgreSQL"
        else:
            with self.connect() as conn:
                self._ensure_expected_schema(conn)
                user = conn.execute("SELECT id, username, carteira FROM users WHERE username = ?", (username,)).fetchone()
                if not user:
                    raise ValueError(f"Usuario negocial nao encontrado: {username}")
                rows = conn.execute(
                    """
                    SELECT p.*, u.username AS usuario
                    FROM producao_unificada p
                    JOIN users u ON u.id = p.user_id
                    WHERE u.id = ?
                    ORDER BY p.data_acordo DESC, p.created_at DESC, p.id DESC
                    """,
                    (int(user["id"]),),
                ).fetchall()
            file_path = str(self.db_path)

        headers, mapped_rows = self._build_producao_rows_for_carteira(user["carteira"] or "", rows)
        return {
            "file_path": file_path,
            "sheet": self.PRODUCAO_SHEET,
            "table_range": self.PRODUCAO_FILE_LABEL,
            "headers": headers,
            "types": self._infer_types(mapped_rows, headers),
            "rows": mapped_rows,
            "row_count": len(mapped_rows),
        }

    def producao_marker(self, username: str) -> str:
        username = self._clean_required(username, "Usuario")
        if self.database_backend == "postgresql":
            with self._connect_postgres() as conn:
                row = conn.execute(
                    """
                    SELECT
                        u.id AS user_id,
                        u.updated_at AS user_updated_at,
                        COUNT(p.id) AS total_rows,
                        COALESCE(MAX(p.id), 0) AS max_row_id,
                        COALESCE(MAX(p.updated_at)::text, '') AS last_producao_update
                    FROM users u
                    LEFT JOIN producao_unificada p ON p.user_id = u.id
                    WHERE u.username = %s
                      AND COALESCE(u.password_hash, '') NOT LIKE %s
                    GROUP BY u.id, u.updated_at
                    """,
                    (username, "$deleted$%"),
                ).fetchone()
        else:
            with self.connect() as conn:
                self._ensure_expected_schema(conn)
                row = conn.execute(
                    """
                    SELECT
                        u.id AS user_id,
                        u.updated_at AS user_updated_at,
                        COUNT(p.id) AS total_rows,
                        COALESCE(MAX(p.id), 0) AS max_row_id,
                        COALESCE(MAX(p.updated_at), '') AS last_producao_update
                    FROM users u
                    LEFT JOIN producao_unificada p ON p.user_id = u.id
                    WHERE u.username = ?
                    GROUP BY u.id, u.updated_at
                    """,
                    (username,),
                ).fetchone()
        if not row:
            raise ValueError(f"Usuario negocial nao encontrado: {username}")
        return "|".join(
            [
                str(row["user_id"]),
                str(row["user_updated_at"] or ""),
                str(row["total_rows"] or 0),
                str(row["max_row_id"] or 0),
                str(row["last_producao_update"] or ""),
            ]
        )

    def create_gamma_gerencial_client(self, payload: dict[str, Any], usuario: str) -> dict[str, Any]:
        if self.database_backend != "postgresql":
            raise ValueError("Cadastro gerencial de cliente esta disponivel apenas no PostgreSQL.")

        negociador = str(payload.get("negociador") or "").strip().upper()
        if negociador not in {"HONORARIOS", "ESCRITORIO"}:
            raise ValueError("Negociador invalido.")

        npj = "".join(char for char in str(payload.get("npj") or "") if char.isdigit())
        if len(npj) != 14:
            raise ValueError("NPJ deve conter 14 digitos.")

        gecor = "".join(char for char in str(payload.get("gecor") or "") if char.isdigit())
        if len(gecor) != 4:
            raise ValueError("GECOR deve conter 4 digitos.")

        cliente = self._clean_required(str(payload.get("cliente") or ""), "Cliente")[:180]
        data_acordo = self._parse_date_for_db(payload.get("data_acordo") or date.today().isoformat())
        data_vencimento = self._parse_date_for_db(payload.get("data_vencimento") or data_acordo.isoformat())
        data_pagamento = self._parse_date_for_db(payload.get("data_pagamento")) if payload.get("data_pagamento") else None
        data_ajuizamento = self._parse_date_for_db(payload.get("data_ajuizamento")) if payload.get("data_ajuizamento") else None
        tipo_acordo = str(payload.get("tipo_acordo") or "A_VISTA").strip().upper()
        if tipo_acordo not in {"A_VISTA", "PARCELADO"}:
            raise ValueError("Tipo de acordo invalido.")
        status = self._normalize_report_status(payload.get("status") or "PROPOSTA") or "PROPOSTA"
        valor_total = Decimal("0.00") if negociador == "HONORARIOS" else self._parse_money_for_db(payload.get("valor_total_acordo"))
        if negociador == "ESCRITORIO" and valor_total <= 0:
            raise ValueError("Valor do acordo obrigatorio para ESCRITORIO.")
        valor_entrada = self._parse_money_for_db(payload.get("valor_entrada"))
        valor_ho = self._parse_money_for_db(payload.get("valor_ho"))
        percentual = Decimal("0.00")
        if valor_total > 0:
            percentual = ((valor_ho / valor_total) * Decimal("100")).quantize(Decimal("0.01"))
        autorizacao = str(payload.get("autorizacao_flexibilizacao") or "NAO").strip().upper() or "NAO"
        uf = str(payload.get("uf") or "").strip().upper()[:2]

        with self._connect_postgres() as conn:
            self._ensure_month_open_postgres(conn, "GAMMA", data_acordo)
            user_id = self._ensure_system_producao_user(conn, negociador, "GAMMA")
            row = conn.execute(
                """
                INSERT INTO producao_registros (
                    data_acordo, cliente, valor_total_acordo, valor_entrada, tipo_acordo,
                    data_vencimento, data_pagamento, status, justificativa_status, carteira,
                    user_id, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, 'GAMMA', %s, NOW(), NOW())
                RETURNING id
                """,
                (data_acordo, cliente, valor_total, valor_entrada, tipo_acordo, data_vencimento, data_pagamento, status, user_id),
            ).fetchone()
            producao_id = int(row["id"])
            conn.execute(
                """
                INSERT INTO producao_gamma (
                    producao_id, npj, gecor, valor_ho, percentual_ho, autorizacao_flexibilizacao
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (producao_id, npj, gecor, valor_ho, percentual, autorizacao),
            )
            if uf or data_ajuizamento:
                conn.execute(
                    """
                    INSERT INTO producao_gamma_gerencial (producao_id, uf, data_ajuizamento, updated_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (producao_id)
                    DO UPDATE SET uf = EXCLUDED.uf, data_ajuizamento = EXCLUDED.data_ajuizamento, updated_at = NOW()
                    """,
                    (producao_id, uf or None, data_ajuizamento),
                )

        return {
            "ok": True,
            "id": producao_id,
            "cliente": cliente,
            "negociador": negociador,
            "created_by": usuario,
        }

    def create_gerencial_client(self, payload: dict[str, Any], usuario: str) -> dict[str, Any]:
        if self.database_backend != "postgresql":
            raise ValueError("Cadastro gerencial de cliente esta disponivel apenas no PostgreSQL.")

        carteira = self._clean_required(payload.get("carteira") or payload.get("carteira_nome") or "GAMMA", "Carteira").upper()
        negociador = self._clean_required(payload.get("negociador") or payload.get("usuario") or "", "Negociador")
        data_acordo = self._parse_date_for_db(payload.get("data_acordo") or date.today().isoformat())
        data_vencimento = self._parse_date_for_db(payload.get("data_vencimento") or data_acordo.isoformat())
        data_pagamento = self._parse_date_for_db(payload.get("data_pagamento")) if payload.get("data_pagamento") else None
        status = self._normalize_report_status(payload.get("status") or "PROPOSTA") or "PROPOSTA"
        tipo_acordo = str(payload.get("tipo_acordo") or payload.get("TIPO_DE_ACORDO") or "A_VISTA").strip().upper().replace(" ", "_")
        if tipo_acordo in {"A_VISTA", "AVISTA", "A"}:
            tipo_acordo = "A_VISTA"
        elif tipo_acordo not in {"PARCELADO"}:
            tipo_acordo = "PARCELADO"

        fields = dict(payload.get("campos") or {})
        for key, value in payload.items():
            if key not in {"campos", "carteira", "carteira_nome", "negociador", "usuario"}:
                fields.setdefault(str(key).upper(), value)

        cliente = self._clean_required(
            self._field_value_from_payload(fields, "CLIENTE", "NOME", "NOME_CLIENTE") or payload.get("cliente") or "",
            "Cliente",
        )[:180]
        valor_total = self._parse_money_for_db(
            self._field_value_from_payload(fields, "VALOR_TOTAL_ACORDO", "VALOR_DO_ACORDO", "VALOR_TOTAL", "VALOR_FECHADO")
            or payload.get("valor_total_acordo")
        )
        valor_entrada = self._parse_money_for_db(
            self._field_value_from_payload(fields, "VALOR_ENTRADA", "VALOR_DA_ENTRADA", "ENTRADA")
            or payload.get("valor_entrada")
        )

        with self._connect_postgres() as conn:
            wallet = conn.execute("SELECT id, slug, modo_schema FROM carteiras_negociais WHERE slug = %s", (carteira,)).fetchone()
            if carteira not in {"GAMMA", "ALPHA", "BETA"} and not wallet:
                raise ValueError("Carteira nao encontrada.")
            self._ensure_month_open_postgres(conn, carteira, data_acordo)
            user_id = self._ensure_existing_or_system_producao_user(conn, negociador, carteira)
            row = conn.execute(
                """
                INSERT INTO producao_registros (
                    data_acordo, cliente, valor_total_acordo, valor_entrada, tipo_acordo,
                    data_vencimento, data_pagamento, status, justificativa_status, carteira,
                    user_id, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, NOW(), NOW())
                RETURNING id
                """,
                (data_acordo, cliente, valor_total, valor_entrada, tipo_acordo, data_vencimento, data_pagamento, status, carteira, user_id),
            ).fetchone()
            producao_id = int(row["id"])
            if carteira == "GAMMA":
                self._insert_gerencial_gamma_detail(conn, producao_id, payload, fields, valor_total)
                if wallet and bool(wallet.get("modo_schema")):
                    defaults = self._gerencial_dynamic_defaults(
                        data_acordo, cliente, status, negociador, valor_total, valor_entrada,
                        data_vencimento, data_pagamento, tipo_acordo,
                    )
                    defaults["NPJ"] = str(payload.get("npj") or payload.get("identificador") or "").strip()
                    defaults["GECOR"] = str(payload.get("gecor") or fields.get("GECOR") or "").strip()
                    received_ho = self._parse_money_for_db(
                        self._field_value_from_payload(fields, "HONOR_RIOS_RECEBIDOS", "HONORARIOS_RECEBIDOS", "H_O")
                        or payload.get("valor_ho")
                    )
                    defaults["HONOR_RIOS"] = str((valor_total * Decimal("0.10")).quantize(Decimal("0.01")))
                    defaults["HONOR_RIOS_RECEBIDOS"] = str(received_ho)
                    defaults["PERCENTUAL"] = str(((received_ho / valor_total) * Decimal("100")).quantize(Decimal("0.01"))) if valor_total > 0 else "0"
                    defaults["AUTORIZADO"] = str(payload.get("autorizacao_flexibilizacao") or "NAO")
                    self._insert_gerencial_dynamic_fields(conn, producao_id, int(wallet["id"]), fields, defaults)
            elif carteira == "ALPHA":
                self._insert_gerencial_alpha_detail(conn, producao_id, payload, fields)
            elif carteira == "BETA":
                self._insert_gerencial_beta_detail(conn, producao_id, payload, fields)
            else:
                defaults = self._gerencial_dynamic_defaults(
                    data_acordo, cliente, status, negociador, valor_total, valor_entrada,
                    data_vencimento, data_pagamento, tipo_acordo,
                )
                identifier_column = conn.execute(
                    """
                    SELECT chave
                    FROM carteira_colunas
                    WHERE carteira_id = %s AND identificador = TRUE
                    ORDER BY ordem, id
                    LIMIT 1
                    """,
                    (int(wallet["id"]),),
                ).fetchone()
                if identifier_column:
                    defaults[str(identifier_column["chave"])] = str(payload.get("npj") or payload.get("identificador") or "").strip()
                self._insert_gerencial_dynamic_fields(conn, producao_id, int(wallet["id"]), fields, defaults)
        return {"ok": True, "id": producao_id, "cliente": cliente, "carteira": carteira, "negociador": negociador, "created_by": usuario}

    def _gerencial_dynamic_defaults(
        self, data_acordo: date, cliente: str, status: str, negociador: str,
        valor_total: Decimal, valor_entrada: Decimal, data_vencimento: date | None,
        data_pagamento: date | None, tipo_acordo: str,
    ) -> dict[str, Any]:
        return {
            "DATA": data_acordo.isoformat(),
            "DATA_ACORDO": data_acordo.isoformat(),
            "CLIENTE": cliente,
            "STATUS": status,
            "NEGOCIADOR": negociador,
            "OPERADOR": negociador,
            "VALOR_DO_ACORDO": str(valor_total),
            "VALOR_TOTAL": str(valor_total),
            "VALOR_DA_ENTRADA": str(valor_entrada),
            "DATA_DE_VENCIMENTO": data_vencimento.isoformat() if data_vencimento else "",
            "DATA_DO_PAGAMENTO": data_pagamento.isoformat() if data_pagamento else "",
            "TIPO_DE_ACORDO": tipo_acordo,
            "PARCELADO_OU_VISTA": tipo_acordo,
        }

    def _ensure_existing_or_system_producao_user(self, conn, username: str, carteira: str) -> int:
        row = conn.execute("SELECT id FROM users WHERE username = %s AND COALESCE(password_hash, '') NOT LIKE %s", (username, "$deleted$%")).fetchone()
        if row:
            return int(row["id"])
        return self._ensure_system_producao_user(conn, username, carteira)

    def _field_value_from_payload(self, fields: dict[str, Any], *keys: str) -> Any:
        normalized = {self._header_key(key): value for key, value in fields.items()}
        for key in keys:
            if key in fields:
                return fields[key]
            value = normalized.get(self._header_key(key))
            if value not in (None, ""):
                return value
        return None

    def _insert_gerencial_gamma_detail(self, conn, producao_id: int, payload: dict[str, Any], fields: dict[str, Any], valor_total: Decimal) -> None:
        npj = "".join(char for char in str(self._field_value_from_payload(fields, "NPJ") or payload.get("npj") or "") if char.isdigit())
        if len(npj) != 14:
            raise ValueError("NPJ deve conter 14 digitos.")
        gecor = "".join(char for char in str(self._field_value_from_payload(fields, "GECOR") or payload.get("gecor") or "") if char.isdigit())
        if len(gecor) != 4:
            raise ValueError("GECOR deve conter 4 digitos.")
        valor_ho = self._parse_money_for_db(self._field_value_from_payload(fields, "HONORARIOS_RECEBIDOS", "HONOR_RIOS_RECEBIDOS", "H_O") or payload.get("valor_ho"))
        percentual = Decimal("0.00")
        if valor_total > 0:
            percentual = ((valor_ho / valor_total) * Decimal("100")).quantize(Decimal("0.01"))
        autorizacao = str(payload.get("autorizacao_flexibilizacao") or payload.get("AUTORIZADO") or "NAO").strip().upper() or "NAO"
        conn.execute(
            """
            INSERT INTO producao_gamma (producao_id, npj, gecor, valor_ho, percentual_ho, autorizacao_flexibilizacao)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (producao_id, npj, gecor, valor_ho, percentual, autorizacao),
        )
        uf = str(payload.get("uf") or "").strip().upper()[:2]
        data_ajuizamento = self._parse_date_for_db(payload.get("data_ajuizamento")) if payload.get("data_ajuizamento") else None
        if uf or data_ajuizamento:
            conn.execute(
                """
                INSERT INTO producao_gamma_gerencial (producao_id, uf, data_ajuizamento, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (producao_id)
                DO UPDATE SET uf = EXCLUDED.uf, data_ajuizamento = EXCLUDED.data_ajuizamento, updated_at = NOW()
                """,
                (producao_id, uf or None, data_ajuizamento),
            )

    def _insert_gerencial_alpha_detail(self, conn, producao_id: int, payload: dict[str, Any], fields: dict[str, Any]) -> None:
        debit_id = "".join(char for char in str(self._field_value_from_payload(fields, "DEBIT_ID", "IDENTIFICADOR") or payload.get("npj") or "") if char.isdigit())
        if len(debit_id) != 8:
            raise ValueError("DEBIT ID deve conter 8 digitos.")
        cpf = "".join(char for char in str(self._field_value_from_payload(fields, "CPF", "CPF_CNPJ", "CNPJ") or payload.get("cpf") or "") if char.isdigit())
        if len(cpf) not in {11, 14}:
            raise ValueError("CPF/CNPJ deve conter 11 ou 14 digitos.")
        atraso = self._parse_date_for_db(self._field_value_from_payload(fields, "DATA_PRIMEIRO_ATRASO", "DATA_DO_1_ATRASO") or payload.get("data_primeiro_atraso"))
        carteira_alpha = str(self._field_value_from_payload(fields, "CARTEIRA_ALPHA", "CARTEIRA") or payload.get("carteira_alpha") or "AUTOS").strip().upper()
        portfolio = str(self._field_value_from_payload(fields, "PORTFOLIO") or payload.get("portfolio") or "").strip() or None
        conn.execute(
            """
            INSERT INTO producao_alpha (producao_id, debit_id, cpf, data_primeiro_atraso, portfolio, carteira_alpha)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (producao_id, debit_id, cpf, atraso, portfolio, carteira_alpha),
        )

    def _insert_gerencial_beta_detail(self, conn, producao_id: int, payload: dict[str, Any], fields: dict[str, Any]) -> None:
        suitid = str(self._field_value_from_payload(fields, "SUITID", "IDENTIFICADOR") or payload.get("npj") or "").strip()
        if not suitid:
            raise ValueError("SUITID e obrigatorio.")
        conn.execute("INSERT INTO producao_beta (producao_id, suitid) VALUES (%s, %s)", (producao_id, suitid))

    def _insert_gerencial_dynamic_fields(self, conn, producao_id: int, carteira_id: int, fields: dict[str, Any], defaults: dict[str, Any]) -> None:
        columns = conn.execute(
            """
            SELECT id, nome, chave, tipo, obrigatoria, opcoes_json
            FROM carteira_colunas
            WHERE carteira_id = %s AND visivel = TRUE
            ORDER BY ordem, id
            """,
            (carteira_id,),
        ).fetchall()
        for column in columns:
            key = str(column["chave"])
            value = self._field_value_from_payload(fields, key, str(column["nome"]))
            if self._dynamic_value_is_empty(value):
                value = defaults.get(key)
            value = self._validate_dynamic_column_value(column, value)
            if bool(column["obrigatoria"]) and self._dynamic_value_is_empty(value):
                raise ValueError(f"{column['nome']} e obrigatorio.")
            valor_texto, valor_numero, valor_data, valor_json = self._dynamic_db_value(str(column["tipo"]), value)
            conn.execute(
                """
                INSERT INTO producao_campos (
                    producao_id, coluna_id, valor_texto, valor_numero, valor_data, valor_json, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, NOW())
                """,
                (producao_id, int(column["id"]), valor_texto, valor_numero, valor_data, json.dumps(valor_json) if valor_json is not None else None),
            )
        self._recalculate_ho_rule_postgres(conn, carteira_id, [producao_id])

    def _dynamic_value_is_empty(self, value: Any) -> bool:
        return value is None or value == "" or value == [] or value == {}

    def _multiselect_values(self, value: Any) -> list[str]:
        if self._dynamic_value_is_empty(value):
            return []
        source = value
        if isinstance(value, str):
            text = value.strip()
            try:
                source = json.loads(text) if text.startswith("[") else re.split(r"[;,]", text)
            except json.JSONDecodeError:
                source = re.split(r"[;,]", text)
        if not isinstance(source, (list, tuple, set)):
            source = [source]
        selected: list[str] = []
        seen: set[str] = set()
        for item in source:
            option = str(item or "").strip()
            key = self._header_key(option)
            if option and key not in seen:
                seen.add(key)
                selected.append(option)
        return selected

    def _dynamic_column_options(self, column: dict[str, Any]) -> list[str]:
        raw = column.get("opcoes_json") or []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = re.split(r"[;,]", raw)
        return [str(item or "").strip() for item in raw if str(item or "").strip()]

    def _validate_dynamic_column_value(self, column: dict[str, Any], value: Any) -> Any:
        if str(column.get("tipo") or "").lower() != "multiselect" or self._dynamic_value_is_empty(value):
            return value
        selected = self._multiselect_values(value)
        options = self._dynamic_column_options(column)
        by_key = {self._header_key(option): option for option in options}
        if options and any(self._header_key(item) not in by_key for item in selected):
            raise ValueError(f"Selecione opcoes validas para {column.get('nome') or 'o campo'}.")
        return [by_key.get(self._header_key(item), item) for item in selected]

    def _dynamic_db_value(self, tipo: str, value: Any):
        if self._dynamic_value_is_empty(value):
            return None, None, None, None
        if tipo == "multiselect":
            selected = self._multiselect_values(value)
            return None, None, None, selected or None
        if tipo in {"numero", "moeda"}:
            return None, self._parse_money_for_db(value), None, None
        if tipo == "data":
            return None, None, self._parse_date_for_db(value), None
        if isinstance(value, (dict, list)):
            return None, None, None, value
        return str(value), None, None, None

    def update_gerencial_cell(self, producao_id: int, header: str, value: Any, usuario: str, motivo: str = "") -> dict[str, Any]:
        if self.database_backend != "postgresql":
            raise ValueError("Correcoes gerenciais estao disponiveis apenas no PostgreSQL.")
        producao_id = int(producao_id or 0)
        if producao_id <= 0:
            raise ValueError("Registro invalido.")
        header = str(header or "").strip().upper()
        header_key = self._header_key(header)
        if "%" in header or header_key in {"ULTIMA_ATUALIZACAO", "CRIADO_EM", "DIAS_DE_ATRASO", "PERCENTUAL"}:
            raise ValueError("Esta coluna e calculada e nao pode ser editada.")
        motivo = str(motivo or "").strip()

        with self._connect_postgres() as conn:
            row = conn.execute(
                """
                SELECT p.*,
                       u.username AS usuario,
                       gamma.npj, gamma.gecor, gamma.valor_ho, gamma.percentual_ho, gamma.autorizacao_flexibilizacao,
                       it.debit_id, it.cpf, it.data_primeiro_atraso, it.portfolio, it.carteira_alpha,
                       rt.suitid,
                       g.uf AS gerencial_uf, g.data_ajuizamento AS gerencial_data_ajuizamento
                FROM producao_registros p
                JOIN users u ON u.id = p.user_id
                LEFT JOIN producao_gamma gamma ON gamma.producao_id = p.id
                LEFT JOIN producao_alpha it ON it.producao_id = p.id
                LEFT JOIN producao_beta rt ON rt.producao_id = p.id
                LEFT JOIN producao_gamma_gerencial g ON g.producao_id = p.id
                WHERE p.id = %s
                """,
                (producao_id,),
            ).fetchone()
            if not row:
                raise ValueError("Registro de producao nao encontrado.")
            carteira = str(row.get("carteira") or "").strip().upper()
            self._ensure_month_open_postgres(conn, carteira, row.get("data_acordo"))

            previous = self._current_cell_value(conn, row, header)
            normalized = self._apply_gerencial_cell_update(conn, row, header, header_key, value, usuario)
            self._upsert_schema_cell_value(conn, carteira, producao_id, header, header_key, normalized)
            if carteira == "GAMMA":
                self._sync_gamma_schema_computed_fields(conn, producao_id)
            carteira_row = conn.execute(
                "SELECT id FROM carteiras_negociais WHERE UPPER(slug) = UPPER(%s)",
                (carteira,),
            ).fetchone()
            if carteira_row:
                self._recalculate_ho_rule_postgres(conn, int(carteira_row["id"]), [producao_id])
            if header_key == "DATA":
                self._ensure_month_open_postgres(conn, carteira, normalized)
            if self._should_record_correction(header_key) and str(previous) != str(normalized):
                conn.execute(
                    """
                    INSERT INTO producao_correcoes (
                        producao_id, campo, valor_anterior, valor_novo, corrigido_por, motivo, criado_em
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (producao_id, header, str(previous or ""), str(normalized or ""), usuario, motivo),
                )
        owner_before = str(row.get("usuario") or "").strip()
        owner_after = str(normalized or "").strip() if header_key in {"NEGOCIADOR", "OPERADOR", "USUARIO"} else owner_before
        affected_usernames = list(dict.fromkeys(item for item in (owner_before, owner_after) if item))
        return {
            "ok": True,
            "id": producao_id,
            "header": header,
            "value": str(normalized or ""),
            "previous_value": str(previous or ""),
            "owner_username": owner_after,
            "affected_usernames": affected_usernames,
            "change_origin": "gerencial",
        }

    def list_production_corrections(self, username: str, limit: int = 200) -> list[dict[str, Any]]:
        if self.database_backend != "postgresql":
            return []
        username = str(username or "").strip()
        if not username:
            return []
        limit = max(1, min(int(limit or 200), 1000))
        with self._connect_postgres() as conn:
            rows = conn.execute(
                """
                SELECT c.id,
                       c.producao_id,
                       p.cliente,
                       p.carteira,
                       c.campo,
                       c.valor_anterior,
                       c.valor_novo,
                       c.corrigido_por,
                       c.motivo,
                       c.criado_em,
                       c.visualizado_pelo_negociador
                FROM producao_correcoes c
                JOIN producao_registros p ON p.id = c.producao_id
                JOIN users u ON u.id = p.user_id
                WHERE lower(u.username) = lower(%s)
                ORDER BY c.criado_em DESC, c.id DESC
                LIMIT %s
                """,
                (username, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def _current_cell_value(self, conn, row: dict[str, Any], header: str) -> Any:
        carteira = str(row.get("carteira") or "").strip().upper()
        base = self._map_producao_row(row, 1)
        columns = self._schema_columns_for_carteira_conn(conn, carteira)
        if columns:
            dynamic = self._dynamic_values_by_producao_id([int(row.get("id") or 0)]).get(int(row.get("id") or 0), {})
            mapped = self._map_schema_producao_row(row, 1, columns, dynamic, include_monthly_meta=True)
            return mapped.get(header, "")
        return base.get(header, "")

    def _apply_gerencial_cell_update(self, conn, row: dict[str, Any], header: str, header_key: str, value: Any, usuario: str) -> Any:
        producao_id = int(row["id"])
        carteira = str(row.get("carteira") or "").strip().upper()
        if header_key in {"DATA", "DATA_ACORDO"}:
            parsed = self._parse_date_for_db(value)
            conn.execute("UPDATE producao_registros SET data_acordo = %s, updated_at = NOW() WHERE id = %s", (parsed, producao_id))
            return parsed
        if header_key in {"CLIENTE", "NOME", "NOME_CLIENTE"}:
            normalized = self._clean_required(value, "Cliente")[:180]
            conn.execute("UPDATE producao_registros SET cliente = %s, updated_at = NOW() WHERE id = %s", (normalized, producao_id))
            return normalized
        if header_key in {"VALOR_DO_ACORDO", "VALOR_TOTAL", "VALOR_TOTAL_DE_ACORDO", "VALOR_FECHADO", "ACORDO"}:
            normalized = self._parse_money_for_db(value)
            conn.execute("UPDATE producao_registros SET valor_total_acordo = %s, updated_at = NOW() WHERE id = %s", (normalized, producao_id))
            if carteira == "GAMMA":
                self._recalculate_gamma_percent(conn, producao_id)
            return normalized
        if header_key in {"VALOR_DA_ENTRADA", "VALOR_ENTRADA", "ENTRADA"}:
            normalized = self._parse_money_for_db(value)
            conn.execute("UPDATE producao_registros SET valor_entrada = %s, updated_at = NOW() WHERE id = %s", (normalized, producao_id))
            return normalized
        if header_key in {"TIPO", "TIPO_DE_ACORDO", "PARCELADO_OU_A_VISTA", "PARCELADO_OU_VISTA"}:
            normalized = str(value or "").strip().upper().replace(" ", "_")
            if normalized in {"A_VISTA", "AVISTA", "A"}:
                normalized = "A_VISTA"
            elif normalized not in {"PARCELADO"}:
                normalized = "PARCELADO"
            conn.execute("UPDATE producao_registros SET tipo_acordo = %s, updated_at = NOW() WHERE id = %s", (normalized, producao_id))
            return normalized
        if header_key in {"VENCIMENTO", "DATA_DE_VENCIMENTO", "DATA_DO_VENCIMENTO"}:
            normalized = self._parse_date_for_db(value)
            conn.execute("UPDATE producao_registros SET data_vencimento = %s, updated_at = NOW() WHERE id = %s", (normalized, producao_id))
            return normalized
        if header_key in {"PAGAMENTO", "DATA_DO_PAGAMENTO"}:
            normalized = self._parse_date_for_db(value) if str(value or "").strip() else None
            conn.execute("UPDATE producao_registros SET data_pagamento = %s, updated_at = NOW() WHERE id = %s", (normalized, producao_id))
            return normalized or ""
        if header_key == "STATUS":
            normalized = self._normalize_report_status(value)
            if normalized not in self.STATUS_LABELS:
                raise ValueError("Status invalido.")
            conn.execute("UPDATE producao_registros SET status = %s, updated_at = NOW() WHERE id = %s", (normalized, producao_id))
            return normalized
        if header_key == "JUSTIFICATIVA":
            normalized = str(value or "").strip()[:600]
            conn.execute("UPDATE producao_registros SET justificativa_status = %s, updated_at = NOW() WHERE id = %s", (normalized or None, producao_id))
            return normalized
        if header_key in {"NEGOCIADOR", "OPERADOR", "USUARIO"}:
            normalized = self._clean_required(value, "Negociador")
            user_id = self._ensure_existing_or_system_producao_user(conn, normalized, carteira)
            conn.execute("UPDATE producao_registros SET user_id = %s, updated_at = NOW() WHERE id = %s", (user_id, producao_id))
            return normalized
        if carteira == "GAMMA":
            if header_key in {"HONORARIOS", "HONOR_RIOS"}:
                raise ValueError("Honorarios e uma coluna calculada e nao pode ser editada.")
            gamma_specific_fields = {
                "NPJ", "GECOR", "UF", "URF", "DT_AJUIZAMENTO",
                "HONORARIOS_RECEBIDOS", "HONOR_RIOS_RECEBIDOS", "H_O", "HO",
                "AUTORIZADO", "AUTORIZADO_",
            }
            if header_key in gamma_specific_fields:
                return self._apply_gamma_specific_update(conn, producao_id, header_key, value, row)
            return self._apply_dynamic_wallet_update(conn, carteira, producao_id, header, header_key, value)
        if carteira == "ALPHA":
            return self._apply_alpha_specific_update(conn, producao_id, header_key, value)
        if carteira == "BETA":
            return self._apply_beta_specific_update(conn, producao_id, header_key, value)
        return self._apply_dynamic_wallet_update(conn, carteira, producao_id, header, header_key, value)

    def _apply_gamma_specific_update(self, conn, producao_id: int, header_key: str, value: Any, row: dict[str, Any]) -> Any:
        if header_key == "NPJ":
            normalized = "".join(char for char in str(value or "") if char.isdigit())
            if len(normalized) != 14:
                raise ValueError("NPJ deve conter 14 digitos.")
            conn.execute("UPDATE producao_gamma SET npj = %s WHERE producao_id = %s", (normalized, producao_id))
        elif header_key == "GECOR":
            normalized = "".join(char for char in str(value or "") if char.isdigit())
            if len(normalized) != 4:
                raise ValueError("GECOR deve conter 4 digitos.")
            conn.execute("UPDATE producao_gamma SET gecor = %s WHERE producao_id = %s", (normalized, producao_id))
        elif header_key in {"UF", "URF"}:
            normalized = str(value or "").strip().upper()[:2]
            conn.execute(
                """
                INSERT INTO producao_gamma_gerencial (producao_id, uf, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (producao_id)
                DO UPDATE SET uf = EXCLUDED.uf, updated_at = NOW()
                """,
                (producao_id, normalized or None),
            )
        elif header_key in {"DT_AJUIZAMENTO"}:
            normalized = self._parse_date_for_db(value) if str(value or "").strip() else None
            conn.execute(
                """
                INSERT INTO producao_gamma_gerencial (producao_id, data_ajuizamento, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (producao_id)
                DO UPDATE SET data_ajuizamento = EXCLUDED.data_ajuizamento, updated_at = NOW()
                """,
                (producao_id, normalized),
            )
        elif header_key in {"HONORARIOS_RECEBIDOS", "HONOR_RIOS_RECEBIDOS", "H_O", "HO"}:
            normalized = self._parse_money_for_db(value)
            conn.execute("UPDATE producao_gamma SET valor_ho = %s WHERE producao_id = %s", (normalized, producao_id))
            self._recalculate_gamma_percent(conn, producao_id)
        elif header_key in {"AUTORIZADO", "AUTORIZADO_"}:
            normalized = str(value or "").strip().upper() or "NAO"
            conn.execute("UPDATE producao_gamma SET autorizacao_flexibilizacao = %s WHERE producao_id = %s", (normalized, producao_id))
        else:
            raise ValueError("Esta coluna nao pode ser editada.")
        conn.execute("UPDATE producao_registros SET updated_at = NOW() WHERE id = %s", (producao_id,))
        return normalized or ""

    def _apply_alpha_specific_update(self, conn, producao_id: int, header_key: str, value: Any) -> Any:
        if header_key == "DEBIT_ID":
            normalized = "".join(char for char in str(value or "") if char.isdigit())
            if len(normalized) != 8:
                raise ValueError("DEBIT ID deve conter 8 digitos.")
            conn.execute("UPDATE producao_alpha SET debit_id = %s WHERE producao_id = %s", (normalized, producao_id))
        elif header_key in {"CPF", "CPF_CNPJ", "CNPJ"}:
            normalized = "".join(char for char in str(value or "") if char.isdigit())
            if len(normalized) not in {11, 14}:
                raise ValueError("CPF/CNPJ deve conter 11 ou 14 digitos.")
            conn.execute("UPDATE producao_alpha SET cpf = %s WHERE producao_id = %s", (normalized, producao_id))
        elif header_key in {"DATA_DO_1_ATRASO", "DATA_DO_1O_ATRASO", "DATA_PRIMEIRO_ATRASO"}:
            normalized = self._parse_date_for_db(value) if str(value or "").strip() else None
            conn.execute("UPDATE producao_alpha SET data_primeiro_atraso = %s WHERE producao_id = %s", (normalized, producao_id))
        elif header_key == "PORTFOLIO":
            normalized = str(value or "").strip()[:120]
            conn.execute("UPDATE producao_alpha SET portfolio = %s WHERE producao_id = %s", (normalized or None, producao_id))
        elif header_key == "CARTEIRA":
            normalized = str(value or "").strip().upper()[:40]
            conn.execute("UPDATE producao_alpha SET carteira_alpha = %s WHERE producao_id = %s", (normalized or None, producao_id))
        else:
            raise ValueError("Esta coluna nao pode ser editada.")
        conn.execute("UPDATE producao_registros SET updated_at = NOW() WHERE id = %s", (producao_id,))
        return normalized or ""

    def _apply_beta_specific_update(self, conn, producao_id: int, header_key: str, value: Any) -> Any:
        if header_key not in {"SUITID", "IDENTIFICADOR"}:
            raise ValueError("Esta coluna nao pode ser editada.")
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("SUITID e obrigatorio.")
        conn.execute("UPDATE producao_beta SET suitid = %s WHERE producao_id = %s", (normalized, producao_id))
        conn.execute("UPDATE producao_registros SET updated_at = NOW() WHERE id = %s", (producao_id,))
        return normalized

    def _apply_dynamic_wallet_update(self, conn, carteira: str, producao_id: int, header: str, header_key: str, value: Any) -> Any:
        column = conn.execute(
            """
            SELECT cc.id, cc.nome, cc.chave, cc.tipo, cc.opcoes_json
            FROM carteiras_negociais c
            JOIN carteira_colunas cc ON cc.carteira_id = c.id
            WHERE c.slug = %s
              AND (cc.chave = %s OR UPPER(cc.nome) = %s)
            ORDER BY cc.ordem, cc.id
            LIMIT 1
            """,
            (carteira, header_key, header),
        ).fetchone()
        if not column:
            raise ValueError("Coluna nao encontrada no schema da carteira.")
        value = self._validate_dynamic_column_value(column, value)
        valor_texto, valor_numero, valor_data, valor_json = self._dynamic_db_value(str(column["tipo"]), value)
        conn.execute(
            """
            INSERT INTO producao_campos (producao_id, coluna_id, valor_texto, valor_numero, valor_data, valor_json, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, NOW())
            ON CONFLICT (producao_id, coluna_id)
            DO UPDATE SET valor_texto = EXCLUDED.valor_texto,
                          valor_numero = EXCLUDED.valor_numero,
                          valor_data = EXCLUDED.valor_data,
                          valor_json = EXCLUDED.valor_json,
                          updated_at = NOW()
            """,
            (producao_id, int(column["id"]), valor_texto, valor_numero, valor_data, json.dumps(valor_json) if valor_json is not None else None),
        )
        conn.execute("UPDATE producao_registros SET updated_at = NOW() WHERE id = %s", (producao_id,))
        return self._dynamic_cell_value({
            "valor_texto": valor_texto,
            "valor_numero": valor_numero,
            "valor_data": valor_data,
            "valor_json": json.dumps(valor_json) if valor_json is not None else None,
        })

    def _upsert_schema_cell_value(self, conn, carteira: str, producao_id: int, header: str, header_key: str, value: Any) -> None:
        column = conn.execute(
            """
            SELECT cc.id, cc.tipo
            FROM carteiras_negociais c
            JOIN carteira_colunas cc ON cc.carteira_id = c.id
            WHERE c.slug = %s AND (cc.chave = %s OR UPPER(cc.nome) = %s)
            ORDER BY cc.ordem, cc.id
            LIMIT 1
            """,
            (carteira, header_key, header),
        ).fetchone()
        if not column:
            return
        valor_texto, valor_numero, valor_data, valor_json = self._dynamic_db_value(str(column["tipo"]), value)
        conn.execute(
            """
            INSERT INTO producao_campos (producao_id, coluna_id, valor_texto, valor_numero, valor_data, valor_json, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, NOW())
            ON CONFLICT (producao_id, coluna_id)
            DO UPDATE SET valor_texto = EXCLUDED.valor_texto, valor_numero = EXCLUDED.valor_numero,
                          valor_data = EXCLUDED.valor_data, valor_json = EXCLUDED.valor_json, updated_at = NOW()
            """,
            (producao_id, int(column["id"]), valor_texto, valor_numero, valor_data, json.dumps(valor_json) if valor_json is not None else None),
        )

    def _sync_gamma_schema_computed_fields(self, conn, producao_id: int) -> None:
        row = conn.execute(
            """
            SELECT p.valor_total_acordo, gamma.valor_ho, gamma.percentual_ho, gamma.autorizacao_flexibilizacao
            FROM producao_registros p
            JOIN producao_gamma gamma ON gamma.producao_id = p.id
            WHERE p.id = %s
            """,
            (producao_id,),
        ).fetchone()
        if not row:
            return
        values = {
            "HONOR_RIOS": Decimal(str(row["valor_total_acordo"] or 0)) * Decimal("0.10"),
            "HONOR_RIOS_RECEBIDOS": row["valor_ho"],
            "PERCENTUAL": row["percentual_ho"],
            "AUTORIZADO": row["autorizacao_flexibilizacao"],
        }
        for key, field_value in values.items():
            self._upsert_schema_cell_value(conn, "GAMMA", producao_id, key, key, field_value)

    def _schema_columns_for_carteira_conn(self, conn, carteira: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT cc.id, cc.nome, cc.chave, cc.tipo, cc.automatico, cc.auto_tipo, cc.ordem
            FROM carteiras_negociais c
            JOIN carteira_colunas cc ON cc.carteira_id = c.id
            WHERE c.slug = %s
            ORDER BY cc.ordem, cc.id
            """,
            (str(carteira or "").strip().upper(),),
        ).fetchall()
        return [dict(row) for row in rows]

    def _should_record_correction(self, header_key: str) -> bool:
        return header_key not in {"GECOR", "UF", "URF", "DT_AJUIZAMENTO"}

    def update_gamma_gerencial_cell(self, producao_id: int, header: str, value: Any, usuario: str, motivo: str = "") -> dict[str, Any]:
        if self.database_backend != "postgresql":
            raise ValueError("Correcoes gerenciais estao disponiveis apenas no PostgreSQL.")
        header = str(header or "").strip().upper()
        motivo = str(motivo or "").strip()
        sensitive = {"VALOR DO ACORDO", "VALOR DA ENTRADA", "HONORÁRIOS RECEBIDOS", "HONORARIOS RECEBIDOS"}
        gerencial_only_fields = {"GECOR", "UF", "URF", "DT AJUIZAMENTO"}
        if header in sensitive and not motivo:
            raise ValueError("Informe o motivo da correcao.")

        with self._connect_postgres() as conn:
            row = conn.execute(
                """
                SELECT p.*, gamma.npj, gamma.gecor, gamma.valor_ho, gamma.percentual_ho, gamma.autorizacao_flexibilizacao,
                       g.uf AS gerencial_uf, g.data_ajuizamento AS gerencial_data_ajuizamento
                FROM producao_registros p
                JOIN producao_gamma gamma ON gamma.producao_id = p.id
                LEFT JOIN producao_gamma_gerencial g ON g.producao_id = p.id
                WHERE p.id = %s AND UPPER(COALESCE(p.carteira, '')) = 'GAMMA'
                """,
                (int(producao_id),),
            ).fetchone()
            if not row:
                raise ValueError("Registro GAMMA nao encontrado.")
            self._ensure_month_open_postgres(conn, row.get("carteira") or "GAMMA", row.get("data_acordo"))

            previous = ""
            normalized = value
            if header == "UF":
                previous = row.get("gerencial_uf") or ""
                normalized = str(value or "").strip().upper()[:2]
                conn.execute(
                    """
                    INSERT INTO producao_gamma_gerencial (producao_id, uf, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (producao_id)
                    DO UPDATE SET uf = EXCLUDED.uf, updated_at = NOW()
                    """,
                    (int(producao_id), normalized or None),
                )
            elif header == "DT AJUIZAMENTO":
                previous = self._date_value(row.get("gerencial_data_ajuizamento"))
                normalized = self._parse_date_for_db(value)
                conn.execute(
                    """
                    INSERT INTO producao_gamma_gerencial (producao_id, data_ajuizamento, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (producao_id)
                    DO UPDATE SET data_ajuizamento = EXCLUDED.data_ajuizamento, updated_at = NOW()
                    """,
                    (int(producao_id), normalized),
                )
            elif header == "VALOR DO ACORDO":
                previous = str(row.get("valor_total_acordo") or "")
                normalized = self._parse_money_for_db(value)
                conn.execute("UPDATE producao_registros SET valor_total_acordo = %s, updated_at = NOW() WHERE id = %s", (normalized, int(producao_id)))
                self._recalculate_gamma_percent(conn, int(producao_id))
            elif header == "VALOR DA ENTRADA":
                previous = str(row.get("valor_entrada") or "")
                normalized = self._parse_money_for_db(value)
                conn.execute("UPDATE producao_registros SET valor_entrada = %s, updated_at = NOW() WHERE id = %s", (normalized, int(producao_id)))
            elif header in {"HONORÁRIOS RECEBIDOS", "HONORARIOS RECEBIDOS"}:
                previous = str(row.get("valor_ho") or "")
                normalized = self._parse_money_for_db(value)
                conn.execute("UPDATE producao_gamma SET valor_ho = %s WHERE producao_id = %s", (normalized, int(producao_id)))
                conn.execute("UPDATE producao_registros SET updated_at = NOW() WHERE id = %s", (int(producao_id),))
                self._recalculate_gamma_percent(conn, int(producao_id))
            elif header == "DATA DO PAGAMENTO":
                previous = self._date_value(row.get("data_pagamento"))
                normalized = self._parse_date_for_db(value)
                conn.execute("UPDATE producao_registros SET data_pagamento = %s, updated_at = NOW() WHERE id = %s", (normalized, int(producao_id)))
            elif header == "STATUS":
                previous = str(row.get("status") or "")
                normalized = self._normalize_report_status(value)
                conn.execute("UPDATE producao_registros SET status = %s, updated_at = NOW() WHERE id = %s", (normalized, int(producao_id)))
            elif header == "AUTORIZADO?":
                previous = str(row.get("autorizacao_flexibilizacao") or "")
                normalized = str(value or "").strip().upper()
                conn.execute("UPDATE producao_gamma SET autorizacao_flexibilizacao = %s WHERE producao_id = %s", (normalized or "NAO", int(producao_id)))
                conn.execute("UPDATE producao_registros SET updated_at = NOW() WHERE id = %s", (int(producao_id),))
            else:
                raise ValueError("Esta coluna nao pode ser editada pelo gerencial.")

            if str(previous) != str(normalized) and header not in gerencial_only_fields:
                conn.execute(
                    """
                    INSERT INTO producao_correcoes (
                        producao_id, campo, valor_anterior, valor_novo, corrigido_por, motivo, criado_em
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (int(producao_id), header, str(previous), str(normalized or ""), usuario, motivo),
                )
        return {"ok": True, "id": int(producao_id), "header": header, "value": str(normalized or "")}

    def delete_producao(self, producao_id: int, usuario: str) -> dict[str, Any]:
        producao_id = int(producao_id or 0)
        if producao_id <= 0:
            raise ValueError("Registro invalido.")

        if self.database_backend == "postgresql":
            with self._connect_postgres() as conn:
                row = conn.execute(
                    """
                    SELECT p.id, p.cliente, p.carteira, p.data_acordo, u.username AS usuario
                    FROM producao_registros p
                    JOIN users u ON u.id = p.user_id
                    WHERE p.id = %s
                    """,
                    (producao_id,),
                ).fetchone()
                if not row:
                    raise ValueError("Registro de producao nao encontrado.")
                self._ensure_month_open_postgres(conn, row.get("carteira") or "", row.get("data_acordo"))
                conn.execute("DELETE FROM producao_correcoes WHERE producao_id = %s", (producao_id,))
                conn.execute("DELETE FROM producao_gamma_gerencial WHERE producao_id = %s", (producao_id,))
                conn.execute("DELETE FROM producao_registros WHERE id = %s", (producao_id,))
                return {
                    "ok": True,
                    "id": producao_id,
                    "cliente": row.get("cliente") or "",
                    "carteira": row.get("carteira") or "",
                    "usuario": row.get("usuario") or "",
                    "deleted_by": usuario,
                }

        with self.connect() as conn:
            self._ensure_expected_schema(conn)
            row = conn.execute(
                """
                SELECT p.id, p.cliente, p.carteira, p.data_acordo, u.username AS usuario
                FROM producao_registros p
                JOIN users u ON u.id = p.user_id
                WHERE p.id = ?
                """,
                (producao_id,),
            ).fetchone()
            if not row:
                raise ValueError("Registro de producao nao encontrado.")
            self._ensure_month_open_sqlite(conn, row["carteira"] or "", row["data_acordo"])
            tables = {item["name"] for item in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            for table in ("producao_gamma_gerencial", "producao_correcoes", "producao_gamma", "producao_alpha", "producao_beta"):
                if table in tables:
                    conn.execute(f"DELETE FROM {table} WHERE producao_id = ?", (producao_id,))
            conn.execute("DELETE FROM producao_registros WHERE id = ?", (producao_id,))
            return {
                "ok": True,
                "id": producao_id,
                "cliente": row["cliente"] or "",
                "carteira": row["carteira"] or "",
                "usuario": row["usuario"] or "",
                "deleted_by": usuario,
            }

    def _parse_money_for_db(self, value: Any) -> Decimal:
        text = str(value or "0").strip()
        text = "".join(char for char in text if char.isdigit() or char in ",.-")
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        return Decimal(text or "0").quantize(Decimal("0.01"))

    def _parse_date_for_db(self, value: Any):
        text = str(value or "").strip()
        if not text or text.lower() == "vazio":
            return None
        try:
            return datetime.fromisoformat(text[:10]).date()
        except ValueError:
            parts = text.split("/")
            if len(parts) == 3:
                return date(int(parts[2]), int(parts[1]), int(parts[0]))
        raise ValueError("Data invalida. Use DD/MM/AAAA ou AAAA-MM-DD.")

    def _recalculate_gamma_percent(self, conn, producao_id: int) -> None:
        conn.execute(
            """
            UPDATE producao_gamma gamma
            SET percentual_ho = CASE
                WHEN pr.valor_total_acordo > 0 THEN ROUND((gamma.valor_ho / pr.valor_total_acordo) * 100, 2)
                ELSE 0
            END
            FROM producao_registros pr
            WHERE pr.id = gamma.producao_id AND gamma.producao_id = %s
            """,
            (int(producao_id),),
        )

    def _ensure_system_producao_user(self, conn, username: str, carteira: str) -> int:
        row = conn.execute("SELECT id FROM users WHERE username = %s", (username,)).fetchone()
        if row:
            conn.execute(
                "UPDATE users SET carteira = %s, role = 'USER', active = TRUE, updated_at = NOW() WHERE id = %s",
                (carteira, int(row["id"])),
            )
            return int(row["id"])
        created = conn.execute(
            """
            INSERT INTO users (
                username, password_hash, role, carteira, meta_pagamento, active, created_at, updated_at
            )
            VALUES (%s, %s, 'USER', %s, 0, TRUE, NOW(), NOW())
            RETURNING id
            """,
            (username, self.hash_password(secrets.token_urlsafe(24)), carteira),
        ).fetchone()
        return int(created["id"])

    def _producao_mensal_postgres(self, carteira: str, mes: int, ano: int) -> list[dict[str, Any]]:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("Para consultar a producao mensal no PostgreSQL, instale psycopg[binary].") from exc

        with psycopg.connect(self._psycopg_url(), row_factory=dict_row) as conn:
            conn.execute("SET search_path TO negocial, public")
            rows = conn.execute(
                """
                SELECT
                    p.*,
                    g.uf AS gerencial_uf,
                    g.data_ajuizamento AS gerencial_data_ajuizamento,
                    u.username AS usuario,
                    u.active AS usuario_ativo
                FROM producao_unificada p
                JOIN users u ON u.id = p.user_id
                LEFT JOIN producao_gamma_gerencial g ON g.producao_id = p.id
                WHERE UPPER(COALESCE(p.carteira, u.carteira, '')) = %s
                  AND EXTRACT(MONTH FROM p.competencia) = %s
                  AND EXTRACT(YEAR FROM p.competencia) = %s
                ORDER BY p.updated_at DESC, p.data_acordo DESC, p.id DESC
                """,
                (carteira, mes, ano),
            ).fetchall()
        return [dict(row) for row in rows]

    def _producao_carteira_postgres(self, carteira: str) -> list[dict[str, Any]]:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("Para consultar a producao no PostgreSQL, instale psycopg[binary].") from exc

        with psycopg.connect(self._psycopg_url(), row_factory=dict_row) as conn:
            conn.execute("SET search_path TO negocial, public")
            rows = conn.execute(
                """
                SELECT
                    p.*,
                    g.uf AS gerencial_uf,
                    g.data_ajuizamento AS gerencial_data_ajuizamento,
                    u.username AS usuario,
                    u.active AS usuario_ativo
                FROM producao_unificada p
                JOIN users u ON u.id = p.user_id
                LEFT JOIN producao_gamma_gerencial g ON g.producao_id = p.id
                WHERE UPPER(COALESCE(p.carteira, u.carteira, '')) = %s
                ORDER BY p.competencia DESC, p.updated_at DESC, p.data_acordo DESC, p.id DESC
                """,
                (carteira,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _producao_mensal_sqlite(self, carteira: str, mes: int, ano: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            self._ensure_expected_schema(conn)
            rows = conn.execute(
                """
                SELECT p.*, g.uf AS gerencial_uf, g.data_ajuizamento AS gerencial_data_ajuizamento, u.username AS usuario, u.active AS usuario_ativo
                FROM producao_unificada p
                JOIN users u ON u.id = p.user_id
                LEFT JOIN producao_gamma_gerencial g ON g.producao_id = p.id
                WHERE UPPER(COALESCE(p.carteira, u.carteira, '')) = ?
                  AND CAST(strftime('%m', p.data_acordo) AS INTEGER) = ?
                  AND CAST(strftime('%Y', p.data_acordo) AS INTEGER) = ?
                ORDER BY p.updated_at DESC, p.data_acordo DESC, p.id DESC
                """,
                (carteira, mes, ano),
            ).fetchall()
        return [dict(row) for row in rows]

    def _producao_carteira_sqlite(self, carteira: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            self._ensure_expected_schema(conn)
            rows = conn.execute(
                """
                SELECT p.*, g.uf AS gerencial_uf, g.data_ajuizamento AS gerencial_data_ajuizamento,
                       u.username AS usuario, u.active AS usuario_ativo
                FROM producao_unificada p
                JOIN users u ON u.id = p.user_id
                LEFT JOIN producao_gamma_gerencial g ON g.producao_id = p.id
                WHERE UPPER(COALESCE(p.carteira, u.carteira, '')) = ?
                ORDER BY p.data_acordo DESC, p.updated_at DESC, p.id DESC
                """,
                (carteira,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _build_producao_rows_for_carteira(
        self,
        carteira: str,
        records: list[dict[str, Any]],
        include_monthly_meta: bool = False,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        columns = self._schema_columns_for_gerencial(carteira)
        if not columns:
            mapper = self._map_monthly_producao_row if include_monthly_meta else self._map_producao_row
            return self._headers_for_carteira(carteira), [mapper(row, index) for index, row in enumerate(records, start=1)]

        headers = [str(column.get("nome") or column.get("chave") or "").strip().upper() for column in columns]
        record_ids = [int(self._row_get(row, "id") or 0) for row in records if int(self._row_get(row, "id") or 0) > 0]
        dynamic_values = self._dynamic_values_by_producao_id(record_ids)
        rows = [
            self._map_schema_producao_row(
                row,
                index,
                columns,
                dynamic_values.get(int(self._row_get(row, "id") or 0), {}),
                include_monthly_meta=include_monthly_meta,
            )
            for index, row in enumerate(records, start=1)
        ]
        return headers, rows

    def _schema_columns_for_gerencial(self, carteira: str) -> list[dict[str, Any]]:
        slug = str(carteira or "").strip().upper()
        if not slug:
            return []
        if self.database_backend == "postgresql":
            with self._connect_postgres() as conn:
                rows = conn.execute(
                    """
                    SELECT cc.id, cc.nome, cc.chave, cc.tipo, cc.automatico, cc.auto_tipo, cc.ordem
                    FROM carteiras_negociais c
                    JOIN carteira_colunas cc ON cc.carteira_id = c.id
                    WHERE c.slug = %s
                    ORDER BY cc.ordem, cc.id
                    """,
                    (slug,),
                ).fetchall()
            return [dict(row) for row in rows]

        with self.connect() as conn:
            self._ensure_expected_schema(conn)
            rows = conn.execute(
                """
                SELECT cc.id, cc.nome, cc.chave, cc.tipo, cc.automatico, cc.auto_tipo, cc.ordem
                FROM carteiras_negociais c
                JOIN carteira_colunas cc ON cc.carteira_id = c.id
                WHERE c.slug = ?
                ORDER BY cc.ordem, cc.id
                """,
                (slug,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _dynamic_values_by_producao_id(self, producao_ids: list[int]) -> dict[int, dict[str, Any]]:
        ids = sorted({int(item) for item in producao_ids if int(item or 0) > 0})
        if not ids:
            return {}

        if self.database_backend == "postgresql":
            with self._connect_postgres() as conn:
                rows = conn.execute(
                    """
                    SELECT pc.producao_id, cc.nome, cc.chave, cc.tipo,
                           pc.valor_texto, pc.valor_numero, pc.valor_data, pc.valor_json
                    FROM producao_campos pc
                    JOIN carteira_colunas cc ON cc.id = pc.coluna_id
                    WHERE pc.producao_id = ANY(%s)
                    ORDER BY pc.producao_id, cc.ordem, cc.id
                    """,
                    (ids,),
                ).fetchall()
        else:
            placeholders = ",".join("?" for _ in ids)
            with self.connect() as conn:
                self._ensure_expected_schema(conn)
                rows = conn.execute(
                    f"""
                    SELECT pc.producao_id, cc.nome, cc.chave, cc.tipo,
                           pc.valor_texto, pc.valor_numero, pc.valor_data, pc.valor_json
                    FROM producao_campos pc
                    JOIN carteira_colunas cc ON cc.id = pc.coluna_id
                    WHERE pc.producao_id IN ({placeholders})
                    ORDER BY pc.producao_id, cc.ordem, cc.id
                    """,
                    ids,
                ).fetchall()

        grouped: dict[int, dict[str, Any]] = {}
        for row in rows:
            data = dict(row)
            producao_id = int(data.get("producao_id") or 0)
            value = self._dynamic_cell_value(data)
            bucket = grouped.setdefault(producao_id, {})
            for key in (data.get("chave"), data.get("nome"), self._header_key(data.get("chave")), self._header_key(data.get("nome"))):
                if key:
                    bucket[str(key)] = value
        return grouped

    def _dynamic_cell_value(self, field: dict[str, Any]) -> Any:
        if field.get("valor_data") not in (None, ""):
            return self._date_value(field.get("valor_data"))
        if field.get("valor_numero") not in (None, ""):
            try:
                return float(Decimal(str(field.get("valor_numero"))))
            except Exception:
                return field.get("valor_numero")
        if field.get("valor_json") not in (None, ""):
            try:
                return json.loads(field.get("valor_json"))
            except Exception:
                return field.get("valor_json")
        return field.get("valor_texto") or ""

    def _map_schema_producao_row(
        self,
        row: dict[str, Any],
        index: int,
        columns: list[dict[str, Any]],
        field_values: dict[str, Any],
        include_monthly_meta: bool = False,
    ) -> dict[str, Any]:
        base = self._map_producao_row(row, index)
        mapped: dict[str, Any] = {
            "_row_id": base.get("_row_id"),
            "_excel_row": index,
            "competencia": base.get("competencia", ""),
        }
        for column in columns:
            header = str(column.get("nome") or column.get("chave") or "").strip().upper()
            mapped[header] = self._schema_column_value(column, row, base, field_values)
        if include_monthly_meta:
            mapped["ULTIMA ATUALIZACAO"] = self._datetime_value(self._row_get(row, "updated_at"))
            mapped["CRIADO EM"] = self._datetime_value(self._row_get(row, "created_at"))
        return mapped

    def _schema_column_value(
        self,
        column: dict[str, Any],
        row: dict[str, Any],
        base: dict[str, Any],
        field_values: dict[str, Any],
    ) -> Any:
        header = str(column.get("nome") or "").strip().upper()
        chave = str(column.get("chave") or header).strip().upper()
        key = self._header_key(header)
        if key == "STATUS":
            return base.get("STATUS", "")
        if key == "JUSTIFICATIVA":
            return base.get("JUSTIFICATIVA", "")
        if key == "DATA_DO_PAGAMENTO":
            return base.get("DATA DO PAGAMENTO", "")

        value = self._field_lookup(field_values, chave, header, self._header_key(chave), self._header_key(header))
        if value not in (None, ""):
            return self._normalize_schema_display_value(header, value)

        alias_map = {
            "DATA": "DATA",
            "DATA_ACORDO": "DATA ACORDO",
            "CLIENTE": "CLIENTE",
            "STATUS": "STATUS",
            "JUSTIFICATIVA": "JUSTIFICATIVA",
            "NEGOCIADOR": "NEGOCIADOR",
            "OPERADOR": "OPERADOR",
            "USUARIO": "USUARIO",
            "TIPO": "TIPO",
            "TIPO_DE_ACORDO": "TIPO",
            "PARCELADO_OU_A_VISTA": "TIPO",
            "VENCIMENTO": "VENCIMENTO",
            "DATA_DE_VENCIMENTO": "DATA DE VENCIMENTO",
            "DATA_DO_VENCIMENTO": "DATA DO VENCIMENTO",
            "PAGAMENTO": "PAGAMENTO",
            "DATA_DO_PAGAMENTO": "DATA DO PAGAMENTO",
            "VALOR_DO_ACORDO": "VALOR DO ACORDO",
            "VALOR_TOTAL": "VALOR TOTAL",
            "VALOR_TOTAL_DE_ACORDO": "VALOR TOTAL DE ACORDO",
            "VALOR_DA_ENTRADA": "VALOR DA ENTRADA",
            "ENTRADA": "ENTRADA",
            "HONORARIOS": "HONORARIOS",
            "AUTORIZADO": "AUTORIZADO?",
        }
        return base.get(alias_map.get(key, header), "")

    def _field_lookup(self, values: dict[str, Any], *keys: Any) -> Any:
        for key in keys:
            if key is None:
                continue
            text = str(key)
            if text in values:
                return values[text]
        return ""

    def _normalize_schema_display_value(self, header: str, value: Any) -> Any:
        key = self._header_key(header)
        if key == "STATUS":
            status = self._normalize_report_status(value)
            return self.STATUS_LABELS.get(status, value)
        if key in {"TIPO", "TIPO_DE_ACORDO", "PARCELADO_OU_A_VISTA"}:
            tipo = str(value or "").strip().upper().replace(" ", "_")
            return self.TIPO_LABELS.get(tipo, value)
        return value

    def _header_key(self, value: Any) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(char for char in text if not unicodedata.combining(char))
        return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")

    def _map_monthly_producao_row(self, row: dict[str, Any], index: int) -> dict[str, Any]:
        mapped = self._map_producao_row(row, index)
        mapped["ULTIMA ATUALIZACAO"] = self._datetime_value(row.get("updated_at"))
        mapped["CRIADO EM"] = self._datetime_value(row.get("created_at"))
        return mapped

    def _build_monthly_report(self, carteira: str, mes: int, ano: int, rows: list[dict[str, Any]], headers: list[str] | None = None) -> dict[str, Any]:
        carteira_key = str(carteira or "").strip().upper()
        value_header = self._monthly_value_header(carteira_key, headers or [], rows)
        total_producao = sum(self._number(row.get(value_header)) for row in rows)
        last_update = max((str(row.get("ULTIMA ATUALIZACAO") or "") for row in rows), default="")
        by_user: dict[str, dict[str, Any]] = {}
        status_counts: dict[str, int] = {}

        for row in rows:
            usuario = self._row_user_label(row)
            status = str(row.get("STATUS") or "Sem status")
            status_counts[status] = status_counts.get(status, 0) + 1
            item = by_user.setdefault(usuario, {
                "negociador": usuario,
                "casos_atualizados": 0,
                "producao_total": 0.0,
                "ultima_atualizacao": "",
            })
            item["casos_atualizados"] += 1
            item["producao_total"] += self._number(row.get(value_header))
            if str(row.get("ULTIMA ATUALIZACAO") or "") > item["ultima_atualizacao"]:
                item["ultima_atualizacao"] = str(row.get("ULTIMA ATUALIZACAO") or "")

        negociadores = sorted(
            by_user.values(),
            key=lambda item: (float(item["producao_total"]), int(item["casos_atualizados"])),
            reverse=True,
        )
        for item in negociadores:
            item["producao_total"] = round(float(item["producao_total"]), 2)

        return {
            "carteira": carteira,
            "periodo": f"{self._month_name(mes)}/{ano}",
            "total_casos_atualizados": len(rows),
            "total_producao": round(float(total_producao), 2),
            "ultima_atualizacao": last_update,
            "resumo_geral": self._monthly_summary(rows, status_counts),
            "status": status_counts,
            "negociadores": negociadores,
        }

    def _monthly_value_header(self, carteira_key: str, headers: list[str], rows: list[dict[str, Any]]) -> str:
        if self._is_alpha(carteira_key):
            return "VALOR TOTAL"
        if carteira_key == "BETA":
            return "VALOR TOTAL DE ACORDO"
        if carteira_key == "GAMMA":
            return "HONORÁRIOS RECEBIDOS"

        candidates = [
            "HONORARIOS",
            "HONORÁRIOS",
            "HONORARIOS RECEBIDOS",
            "HONORÁRIOS RECEBIDOS",
            "VALOR FECHADO",
            "VALOR DO ACORDO",
            "VALOR TOTAL DE ACORDO",
            "VALOR TOTAL",
            "VALOR TOTAL DO DEBITO",
            "VALOR MINIMO PRE APROVADO",
        ]
        headers_by_key = {self._header_key(header): header for header in headers}
        for candidate in candidates:
            header = headers_by_key.get(self._header_key(candidate))
            if header:
                return header
        for header in headers:
            key = self._header_key(header)
            if any(token in key for token in ("HONORARIO", "HONORARIOS", "VALOR", "TOTAL")):
                return header
        return headers[0] if headers else "VALOR DO ACORDO"

    def _filter_report_rows(self, rows: list[dict[str, Any]], usuario: str = "", dia: str = "", status: str = "") -> list[dict[str, Any]]:
        normalized_statuses = {
            normalized
            for item in str(status or "").split(",")
            if (normalized := self._normalize_report_status(item))
        }
        filtered = rows
        if usuario:
            filtered = [row for row in filtered if self._row_user_label(row).strip().lower() == usuario.lower()]
        if dia:
            filtered = [row for row in filtered if self._day_from_value(row.get("DATA")) == dia.zfill(2)]
        if normalized_statuses:
            filtered = [row for row in filtered if self._normalize_report_status(row.get("STATUS")) in normalized_statuses]
        return filtered

    def _row_user_label(self, row: dict[str, Any]) -> str:
        return str(row.get("USUARIO") or row.get("NEGOCIADOR") or row.get("OPERADOR") or "Nao identificado")
