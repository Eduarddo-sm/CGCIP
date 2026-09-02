from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from typing import Any


class NegocialSchemaMixin:
    def list_carteiras(self) -> list[dict[str, Any]]:
        if self.database_backend == "postgresql":
            with self._connect_postgres() as conn:
                rows = conn.execute(
                    """
                    SELECT cn.id, cn.nome, cn.slug, cn.descricao, cn.active, cn.usa_percentual_ho, cn.percentual_ho_padrao,
                           cn.percentual_ho_minimo, cn.percentual_ho_maximo, cn.calculo_automatico_ho, cn.modo_schema,
                           cn.created_at, cn.updated_at,
                           COALESCE((SELECT MAX(v.version_number) FROM carteira_schema_versions v WHERE v.carteira_id = cn.id), 0) AS schema_version
                    FROM carteiras_negociais cn
                    ORDER BY nome
                    """
                ).fetchall()
                columns = conn.execute(
                    """
                    SELECT carteira_id, id, nome, chave, tipo, obrigatoria, identificador, visivel, ordem,
                           automatico, auto_tipo, max_length, mostrar_cadastro, cadastro_etapa, opcoes_json
                    FROM carteira_colunas
                    ORDER BY carteira_id, ordem, id
                    """
                ).fetchall()
                rules = self._list_ho_rules_postgres(conn)
            return self._group_carteiras(rows, columns, rules)
        with self.connect() as conn:
            self._ensure_expected_schema(conn)
            rows = conn.execute(
                """
                SELECT cn.id, cn.nome, cn.slug, cn.descricao, cn.active, cn.usa_percentual_ho, cn.percentual_ho_padrao,
                       cn.percentual_ho_minimo, cn.percentual_ho_maximo, cn.calculo_automatico_ho, cn.modo_schema,
                       cn.created_at, cn.updated_at,
                       COALESCE((SELECT MAX(v.version_number) FROM carteira_schema_versions v WHERE v.carteira_id = cn.id), 0) AS schema_version
                FROM carteiras_negociais cn
                ORDER BY nome
                """
            ).fetchall()
            columns = conn.execute(
                """
                SELECT carteira_id, id, nome, chave, tipo, obrigatoria, identificador, visivel, ordem,
                       automatico, auto_tipo, max_length, mostrar_cadastro, cadastro_etapa, opcoes_json
                FROM carteira_colunas
                ORDER BY carteira_id, ordem, id
                """
            ).fetchall()
            rules = self._list_ho_rules_sqlite(conn)
        return self._group_carteiras(rows, columns, rules)

    def upsert_carteira(
        self,
        nome: str,
        descricao: str = "",
        colunas: list[dict[str, Any]] | None = None,
        regras_ho: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        nome = self._clean_required(nome, "Nome da carteira").upper()
        slug = self._slug(nome)
        descricao = str(descricao or "").strip()
        columns = self._normalize_carteira_columns(colunas)
        ho_rules = self._normalize_ho_rules(regras_ho, slug)
        schema_mode = True
        now = self._now()
        if self.database_backend == "postgresql":
            with self._connect_postgres() as conn:
                row = conn.execute("SELECT id FROM carteiras_negociais WHERE slug = %s", (slug,)).fetchone()
                if row:
                    carteira_id = int(row["id"])
                    conn.execute(
                        """
                        UPDATE carteiras_negociais
                        SET nome = %s, descricao = %s, active = TRUE,
                            usa_percentual_ho = %s,
                            percentual_ho_padrao = %s,
                            percentual_ho_minimo = %s,
                            percentual_ho_maximo = %s,
                            calculo_automatico_ho = %s,
                            modo_schema = %s,
                            updated_at = %s
                        WHERE id = %s
                        """,
                        (
                            nome,
                            descricao,
                            bool(ho_rules["usa_percentual_ho"]),
                            ho_rules["percentual_ho_padrao"],
                            ho_rules["percentual_ho_minimo"],
                            ho_rules["percentual_ho_maximo"],
                            bool(ho_rules["calculo_automatico_ho"]),
                            schema_mode,
                            now,
                            carteira_id,
                        ),
                    )
                else:
                    created = conn.execute(
                        """
                        INSERT INTO carteiras_negociais (
                            nome, slug, descricao, active, usa_percentual_ho, percentual_ho_padrao,
                            percentual_ho_minimo, percentual_ho_maximo, calculo_automatico_ho, modo_schema, created_at, updated_at
                        )
                        VALUES (%s, %s, %s, TRUE, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            nome,
                            slug,
                            descricao,
                            bool(ho_rules["usa_percentual_ho"]),
                            ho_rules["percentual_ho_padrao"],
                            ho_rules["percentual_ho_minimo"],
                            ho_rules["percentual_ho_maximo"],
                            bool(ho_rules["calculo_automatico_ho"]),
                            schema_mode,
                            now,
                            now,
                        ),
                    ).fetchone()
                    carteira_id = int(created["id"])
                self._sync_carteira_columns_postgres(conn, carteira_id, columns)
                self._sync_ho_rule_postgres(conn, carteira_id, ho_rules)
                self._recalculate_ho_rule_postgres(conn, carteira_id)
                self._record_carteira_schema_version_postgres(conn, carteira_id, "upsert", now)
            return next((item for item in self.list_carteiras() if item["slug"] == slug), {"nome": nome, "slug": slug, "colunas": columns})

        with self.connect() as conn:
            self._ensure_expected_schema(conn)
            row = conn.execute("SELECT id FROM carteiras_negociais WHERE slug = ?", (slug,)).fetchone()
            if row:
                carteira_id = int(row["id"])
                conn.execute(
                    """
                    UPDATE carteiras_negociais
                    SET nome = ?, descricao = ?, active = 1, usa_percentual_ho = ?,
                        percentual_ho_padrao = ?, percentual_ho_minimo = ?, percentual_ho_maximo = ?,
                        calculo_automatico_ho = ?, modo_schema = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        nome,
                        descricao,
                        int(bool(ho_rules["usa_percentual_ho"])),
                        ho_rules["percentual_ho_padrao"],
                        ho_rules["percentual_ho_minimo"],
                        ho_rules["percentual_ho_maximo"],
                        int(bool(ho_rules["calculo_automatico_ho"])),
                        int(schema_mode),
                        now,
                        carteira_id,
                    ),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO carteiras_negociais (
                        nome, slug, descricao, active, usa_percentual_ho, percentual_ho_padrao,
                        percentual_ho_minimo, percentual_ho_maximo, calculo_automatico_ho, modo_schema, created_at, updated_at
                    )
                    VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        nome,
                        slug,
                        descricao,
                        int(bool(ho_rules["usa_percentual_ho"])),
                        ho_rules["percentual_ho_padrao"],
                        ho_rules["percentual_ho_minimo"],
                        ho_rules["percentual_ho_maximo"],
                        int(bool(ho_rules["calculo_automatico_ho"])),
                        int(schema_mode),
                        now,
                        now,
                    ),
                )
                carteira_id = int(cursor.lastrowid)
            self._sync_carteira_columns_sqlite(conn, carteira_id, columns)
            self._sync_ho_rule_sqlite(conn, carteira_id, ho_rules)
            self._record_carteira_schema_version_sqlite(conn, carteira_id, "upsert", now)
        return next((item for item in self.list_carteiras() if item["slug"] == slug), {"nome": nome, "slug": slug, "colunas": columns})

    def _list_ho_rules_postgres(self, conn):
        return conn.execute(
            """
            SELECT rule.*, base.chave AS coluna_base, destination.chave AS coluna_destino,
                   sight.chave AS coluna_base_vista,
                   installment.chave AS coluna_base_parcelado,
                   received.chave AS coluna_valor_recebido,
                   effective.chave AS coluna_percentual_efetivo
            FROM carteira_regras_calculo rule
            LEFT JOIN carteira_colunas base ON base.id = rule.coluna_base_id
            LEFT JOIN carteira_colunas destination ON destination.id = rule.coluna_destino_id
            LEFT JOIN carteira_colunas sight ON sight.id = rule.coluna_base_vista_id
            LEFT JOIN carteira_colunas installment ON installment.id = rule.coluna_base_parcelado_id
            LEFT JOIN carteira_colunas received ON received.id = rule.coluna_valor_recebido_id
            LEFT JOIN carteira_colunas effective ON effective.id = rule.coluna_percentual_efetivo_id
            WHERE rule.codigo = 'HONORARIOS'
            """
        ).fetchall()

    def _list_ho_rules_sqlite(self, conn: sqlite3.Connection):
        return conn.execute(
            """
            SELECT rule.*, base.chave AS coluna_base, destination.chave AS coluna_destino,
                   sight.chave AS coluna_base_vista,
                   installment.chave AS coluna_base_parcelado,
                   received.chave AS coluna_valor_recebido,
                   effective.chave AS coluna_percentual_efetivo
            FROM carteira_regras_calculo rule
            LEFT JOIN carteira_colunas base ON base.id = rule.coluna_base_id
            LEFT JOIN carteira_colunas destination ON destination.id = rule.coluna_destino_id
            LEFT JOIN carteira_colunas sight ON sight.id = rule.coluna_base_vista_id
            LEFT JOIN carteira_colunas installment ON installment.id = rule.coluna_base_parcelado_id
            LEFT JOIN carteira_colunas received ON received.id = rule.coluna_valor_recebido_id
            LEFT JOIN carteira_colunas effective ON effective.id = rule.coluna_percentual_efetivo_id
            WHERE rule.codigo = 'HONORARIOS'
            """
        ).fetchall()

    def _sync_ho_rule_postgres(self, conn, carteira_id: int, rule: dict[str, Any]) -> None:
        column_definitions = {
            row["chave"]: {"id": int(row["id"]), "tipo": row["tipo"]}
            for row in conn.execute(
                "SELECT id, chave, tipo FROM carteira_colunas WHERE carteira_id = %s",
                (carteira_id,),
            ).fetchall()
        }
        params = self._ho_rule_params(rule, column_definitions)
        conn.execute(
            """
            INSERT INTO carteira_regras_calculo (
                carteira_id, codigo, nome, tipo_calculo, motor_calculo,
                coluna_base_id, coluna_destino_id,
                coluna_base_vista_id, coluna_base_parcelado_id,
                coluna_valor_recebido_id, coluna_percentual_efetivo_id,
                percentual_padrao, percentual_minimo, percentual_maximo,
                automatico, ativo, casas_decimais, created_at, updated_at
            )
            VALUES (
                %s, 'HONORARIOS', 'Honorarios', 'percentual', %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, NOW(), NOW()
            )
            ON CONFLICT (carteira_id, codigo) DO UPDATE SET
                motor_calculo = EXCLUDED.motor_calculo,
                coluna_base_id = EXCLUDED.coluna_base_id,
                coluna_destino_id = EXCLUDED.coluna_destino_id,
                coluna_base_vista_id = EXCLUDED.coluna_base_vista_id,
                coluna_base_parcelado_id = EXCLUDED.coluna_base_parcelado_id,
                coluna_valor_recebido_id = EXCLUDED.coluna_valor_recebido_id,
                coluna_percentual_efetivo_id = EXCLUDED.coluna_percentual_efetivo_id,
                percentual_padrao = EXCLUDED.percentual_padrao,
                percentual_minimo = EXCLUDED.percentual_minimo,
                percentual_maximo = EXCLUDED.percentual_maximo,
                automatico = EXCLUDED.automatico,
                ativo = EXCLUDED.ativo,
                casas_decimais = EXCLUDED.casas_decimais,
                updated_at = NOW()
            """,
            (carteira_id, *params),
        )

    def _recalculate_ho_rule_postgres(
        self,
        conn,
        carteira_id: int,
        producao_ids: list[int] | None = None,
    ) -> int:
        rule = conn.execute(
            """
            SELECT c.slug,
                   rule.motor_calculo,
                   rule.percentual_padrao,
                   rule.casas_decimais,
                   rule.coluna_destino_id,
                   rule.coluna_percentual_efetivo_id,
                   base.id AS coluna_base_id,
                   base.chave AS coluna_base_chave,
                   sight.id AS coluna_base_vista_id,
                   sight.chave AS coluna_base_vista_chave,
                   installment.id AS coluna_base_parcelado_id,
                   installment.chave AS coluna_base_parcelado_chave,
                   received.id AS coluna_recebida_id,
                   received.chave AS coluna_recebida_chave
            FROM carteira_regras_calculo rule
            JOIN carteiras_negociais c ON c.id = rule.carteira_id
            LEFT JOIN carteira_colunas base ON base.id = rule.coluna_base_id
            LEFT JOIN carteira_colunas sight ON sight.id = rule.coluna_base_vista_id
            LEFT JOIN carteira_colunas installment ON installment.id = rule.coluna_base_parcelado_id
            LEFT JOIN carteira_colunas received ON received.id = rule.coluna_valor_recebido_id
            WHERE rule.carteira_id = %s
              AND rule.codigo = 'HONORARIOS'
              AND rule.ativo = TRUE
              AND rule.automatico = TRUE
            """,
            (carteira_id,),
        ).fetchone()
        if not rule or rule["coluna_destino_id"] is None:
            return 0
        engine = str(rule["motor_calculo"] or "PERCENTUAL_FIXO")
        if engine == "ALPHA_EXCEPCIONAL":
            return 0
        if rule["percentual_padrao"] is None:
            return 0
        if engine == "PERCENTUAL_CONDICIONAL":
            if (
                rule["coluna_base_vista_id"] is None
                or rule["coluna_base_parcelado_id"] is None
            ):
                return 0
            sight_base_id = int(rule["coluna_base_vista_id"])
            sight_base_key = str(rule["coluna_base_vista_chave"] or "").upper()
            installment_base_id = int(rule["coluna_base_parcelado_id"])
            installment_base_key = str(rule["coluna_base_parcelado_chave"] or "").upper()
        else:
            if rule["coluna_base_id"] is None:
                return 0
            sight_base_id = installment_base_id = int(rule["coluna_base_id"])
            sight_base_key = installment_base_key = str(
                rule["coluna_base_chave"] or ""
            ).upper()

        ids = [int(item) for item in (producao_ids or []) if int(item) > 0]
        id_filter = "AND p.id = ANY(%s)" if ids else ""

        def fallback(key: str) -> str:
            if key in {
                "VALOR_DO_ACORDO",
                "VALOR_TOTAL",
                "VALOR_TOTAL_DE_ACORDO",
                "VALOR_FECHADO",
                "ACORDO",
            }:
                return "p.valor_total_acordo"
            if key in {"VALOR_DA_ENTRADA", "VALOR_ENTRADA", "ENTRADA"}:
                return "p.valor_entrada"
            return "NULL::numeric"

        sight_fallback = fallback(sight_base_key)
        installment_fallback = fallback(installment_base_key)
        base_expression = (
            "CASE "
            f"WHEN p.tipo_acordo = 'PARCELADO' THEN COALESCE(installment.valor_numero, {installment_fallback}) "
            f"ELSE COALESCE(sight.valor_numero, {sight_fallback}) END"
        )

        params: list[Any] = [
            sight_base_id,
            installment_base_id,
            str(rule["slug"]),
        ]
        if ids:
            params.append(ids)
        params.extend(
            [
                Decimal(str(rule["percentual_padrao"])),
                int(rule["casas_decimais"] or 2),
                int(rule["coluna_destino_id"]),
            ]
        )
        destination_result = conn.execute(
            f"""
            WITH source AS (
                SELECT p.id AS producao_id,
                       {base_expression} AS valor_base
                FROM producao_registros p
                LEFT JOIN producao_campos sight
                  ON sight.producao_id = p.id
                 AND sight.coluna_id = %s
                LEFT JOIN producao_campos installment
                  ON installment.producao_id = p.id
                 AND installment.coluna_id = %s
                WHERE UPPER(p.carteira) = UPPER(%s)
                  AND COALESCE(p.origem_registro, 'SISTEMA') <> 'LEGADO_PLANILHA'
                  {id_filter}
            ),
            calculated AS (
                SELECT producao_id,
                       ROUND(valor_base * %s / 100, %s) AS valor_calculado
                FROM source
                WHERE valor_base IS NOT NULL
            )
            INSERT INTO producao_campos (
                producao_id, coluna_id, valor_texto, valor_numero, valor_data, valor_json, updated_at
            )
            SELECT producao_id, %s, NULL, valor_calculado, NULL, NULL, NOW()
            FROM calculated
            ON CONFLICT (producao_id, coluna_id)
            DO UPDATE SET valor_texto = NULL,
                          valor_numero = EXCLUDED.valor_numero,
                          valor_data = NULL,
                          valor_json = NULL,
                          updated_at = NOW()
            """,
            tuple(params),
        )
        updated = max(int(destination_result.rowcount or 0), 0)
        if updated:
            self._bump_producao_version_postgres(conn)

        effective_id = rule["coluna_percentual_efetivo_id"]
        received_id = rule["coluna_recebida_id"]
        if effective_id is None or received_id is None:
            return updated

        received_key = str(rule["coluna_recebida_chave"] or "").upper()
        received_fallback = (
            "gamma.valor_ho"
            if received_key in {"HONORARIOS_RECEBIDOS", "HONOR_RIOS_RECEBIDOS", "H_O", "HO"}
            else "NULL::numeric"
        )
        effective_params: list[Any] = [
            sight_base_id,
            installment_base_id,
            int(received_id),
            str(rule["slug"]),
        ]
        if ids:
            effective_params.append(ids)
        effective_params.extend(
            [
                int(rule["casas_decimais"] or 2),
                int(effective_id),
            ]
        )
        conn.execute(
            f"""
            WITH source AS (
                SELECT p.id AS producao_id,
                       {base_expression} AS valor_base,
                       COALESCE(received.valor_numero, {received_fallback}) AS valor_recebido
                FROM producao_registros p
                LEFT JOIN producao_campos sight
                  ON sight.producao_id = p.id
                 AND sight.coluna_id = %s
                LEFT JOIN producao_campos installment
                  ON installment.producao_id = p.id
                 AND installment.coluna_id = %s
                LEFT JOIN producao_campos received
                  ON received.producao_id = p.id
                 AND received.coluna_id = %s
                LEFT JOIN producao_gamma gamma ON gamma.producao_id = p.id
                WHERE UPPER(p.carteira) = UPPER(%s)
                  {id_filter}
            ),
            calculated AS (
                SELECT producao_id,
                       ROUND(valor_recebido * 100 / valor_base, %s) AS valor_calculado
                FROM source
                WHERE valor_base IS NOT NULL
                  AND valor_base <> 0
                  AND valor_recebido IS NOT NULL
            )
            INSERT INTO producao_campos (
                producao_id, coluna_id, valor_texto, valor_numero, valor_data, valor_json, updated_at
            )
            SELECT producao_id, %s, NULL, valor_calculado, NULL, NULL, NOW()
            FROM calculated
            ON CONFLICT (producao_id, coluna_id)
            DO UPDATE SET valor_texto = NULL,
                          valor_numero = EXCLUDED.valor_numero,
                          valor_data = NULL,
                          valor_json = NULL,
                          updated_at = NOW()
            """,
            tuple(effective_params),
        )
        return updated

    def _bump_producao_version_postgres(self, conn) -> None:
        conn.execute(
            """
            INSERT INTO operational_versions (scope, version, updated_at)
            VALUES ('producao', 1, NOW())
            ON CONFLICT (scope)
            DO UPDATE SET version = operational_versions.version + 1,
                          updated_at = NOW()
            """
        )

    def _sync_ho_rule_sqlite(self, conn: sqlite3.Connection, carteira_id: int, rule: dict[str, Any]) -> None:
        column_definitions = {
            row["chave"]: {"id": int(row["id"]), "tipo": row["tipo"]}
            for row in conn.execute(
                "SELECT id, chave, tipo FROM carteira_colunas WHERE carteira_id = ?",
                (carteira_id,),
            ).fetchall()
        }
        params = self._ho_rule_params(rule, column_definitions)
        now = self._now()
        conn.execute(
            """
            INSERT INTO carteira_regras_calculo (
                carteira_id, codigo, nome, tipo_calculo, motor_calculo,
                coluna_base_id, coluna_destino_id,
                coluna_base_vista_id, coluna_base_parcelado_id,
                coluna_valor_recebido_id, coluna_percentual_efetivo_id,
                percentual_padrao, percentual_minimo, percentual_maximo,
                automatico, ativo, casas_decimais, created_at, updated_at
            )
            VALUES (?, 'HONORARIOS', 'Honorarios', 'percentual', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (carteira_id, codigo) DO UPDATE SET
                motor_calculo = excluded.motor_calculo,
                coluna_base_id = excluded.coluna_base_id,
                coluna_destino_id = excluded.coluna_destino_id,
                coluna_base_vista_id = excluded.coluna_base_vista_id,
                coluna_base_parcelado_id = excluded.coluna_base_parcelado_id,
                coluna_valor_recebido_id = excluded.coluna_valor_recebido_id,
                coluna_percentual_efetivo_id = excluded.coluna_percentual_efetivo_id,
                percentual_padrao = excluded.percentual_padrao,
                percentual_minimo = excluded.percentual_minimo,
                percentual_maximo = excluded.percentual_maximo,
                automatico = excluded.automatico,
                ativo = excluded.ativo,
                casas_decimais = excluded.casas_decimais,
                updated_at = excluded.updated_at
            """,
            (carteira_id, *params, now, now),
        )

    def _ho_rule_params(
        self,
        rule: dict[str, Any],
        column_definitions: dict[str, dict[str, Any]],
    ) -> tuple[Any, ...]:
        enabled = bool(rule.get("usa_percentual_ho"))

        def resolve(key: str) -> int | None:
            column_key = str(rule.get(key) or "").strip().upper()
            if not column_key:
                return None
            column = column_definitions.get(column_key)
            if column is None:
                raise ValueError(f"A coluna {column_key} configurada na regra de H.O nao existe no schema.")
            if column["tipo"] not in {"numero", "moeda"}:
                raise ValueError(f"A coluna {column_key} vinculada a H.O deve ser numerica ou monetaria.")
            return int(column["id"])

        base_id = resolve("coluna_base") if enabled else None
        sight_base_id = resolve("coluna_base_vista") if enabled else None
        installment_base_id = resolve("coluna_base_parcelado") if enabled else None
        destination_id = resolve("coluna_destino") if enabled else None
        received_id = resolve("coluna_valor_recebido") if enabled else None
        effective_id = resolve("coluna_percentual_efetivo") if enabled else None
        engine = str(rule.get("motor_calculo") or "PERCENTUAL_FIXO")
        if bool(rule.get("calculo_automatico_ho")) and destination_id is None:
            raise ValueError("A regra automatica de H.O exige coluna de destino.")
        if (
            bool(rule.get("calculo_automatico_ho"))
            and engine == "PERCENTUAL_FIXO"
            and base_id is None
        ):
            raise ValueError("A regra fixa de H.O exige coluna base.")
        if (
            bool(rule.get("calculo_automatico_ho"))
            and engine == "PERCENTUAL_CONDICIONAL"
            and (sight_base_id is None or installment_base_id is None)
        ):
            raise ValueError("A regra condicional exige bases a vista e parcelada.")
        return (
            engine,
            base_id,
            destination_id,
            sight_base_id,
            installment_base_id,
            received_id,
            effective_id,
            rule.get("percentual_ho_padrao"),
            rule.get("percentual_ho_minimo"),
            rule.get("percentual_ho_maximo"),
            bool(rule.get("calculo_automatico_ho")),
            enabled,
            int(rule.get("casas_decimais") or 2),
        )

    def deactivate_carteira(self, nome: str) -> dict[str, Any]:
        slug = self._slug(self._clean_required(nome, "Nome da carteira"))
        if self.database_backend == "postgresql":
            with self._connect_postgres() as conn:
                used = conn.execute(
                    "SELECT 1 FROM producao_registros WHERE UPPER(COALESCE(carteira, '')) = %s LIMIT 1",
                    (slug,),
                ).fetchone()
                if used:
                    raise ValueError("Carteira possui producao vinculada. Desative em vez de excluir definitivamente.")
                conn.execute("UPDATE carteiras_negociais SET active = FALSE, updated_at = %s WHERE slug = %s", (self._now(), slug))
            return {"ok": True, "slug": slug}
        with self.connect() as conn:
            self._ensure_expected_schema(conn)
            used = conn.execute(
                "SELECT 1 FROM producao_registros WHERE upper(coalesce(carteira, '')) = ? LIMIT 1",
                (slug,),
            ).fetchone()
            if used:
                raise ValueError("Carteira possui producao vinculada. Desative em vez de excluir definitivamente.")
            conn.execute("UPDATE carteiras_negociais SET active = 0, updated_at = ? WHERE slug = ?", (self._now(), slug))
        return {"ok": True, "slug": slug}

    def carteira_schema_versions(self, slug_or_nome: str) -> dict[str, Any]:
        slug = self._slug(self._clean_required(slug_or_nome, "Carteira"))
        if self.database_backend == "postgresql":
            with self._connect_postgres() as conn:
                carteira = conn.execute(
                    "SELECT id, nome, slug FROM carteiras_negociais WHERE slug = %s",
                    (slug,),
                ).fetchone()
                if not carteira:
                    raise ValueError("Carteira nao encontrada.")
                rows = conn.execute(
                    """
                    SELECT id, version_number, action, schema_json, created_at
                    FROM carteira_schema_versions
                    WHERE carteira_id = %s
                    ORDER BY version_number DESC
                    """,
                    (int(carteira["id"]),),
                ).fetchall()
            return self._schema_versions_payload(dict(carteira), rows)

        with self.connect() as conn:
            self._ensure_expected_schema(conn)
            carteira = conn.execute("SELECT id, nome, slug FROM carteiras_negociais WHERE slug = ?", (slug,)).fetchone()
            if not carteira:
                raise ValueError("Carteira nao encontrada.")
            rows = conn.execute(
                """
                SELECT id, version_number, action, schema_json, created_at
                FROM carteira_schema_versions
                WHERE carteira_id = ?
                ORDER BY version_number DESC
                """,
                (int(carteira["id"]),),
            ).fetchall()
        return self._schema_versions_payload(dict(carteira), rows)

    def _sync_carteira_columns_postgres(self, conn, carteira_id: int, columns: list[dict[str, Any]]) -> None:
        columns = self._dedupe_carteira_columns(columns)
        existing = {
            row["chave"]: dict(row)
            for row in conn.execute(
                """
                SELECT id, carteira_id, nome, chave, tipo, obrigatoria, identificador, visivel, ordem,
                       automatico, auto_tipo, max_length, mostrar_cadastro, cadastro_etapa, opcoes_json
                FROM carteira_colunas
                WHERE carteira_id = %s
                """,
                (carteira_id,),
            ).fetchall()
        }
        usage = self._carteira_column_usage_postgres(conn, [int(row["id"]) for row in existing.values()])
        incoming_keys = {column["chave"] for column in columns}

        for old_key, old_column in existing.items():
            if old_key not in incoming_keys:
                if usage.get(int(old_column["id"]), {}).get("count", 0):
                    raise ValueError(f"Nao e possivel remover a coluna {old_column['nome']}: ela possui dados de producao.")
                conn.execute("DELETE FROM carteira_colunas WHERE id = %s", (int(old_column["id"]),))

        for index, column in enumerate(columns, start=1):
            old_column = existing.get(column["chave"])
            if old_column:
                self._validate_carteira_column_change(old_column, column, usage.get(int(old_column["id"]), {}))
                conn.execute(
                    """
                    UPDATE carteira_colunas
                    SET nome = %s, tipo = %s, obrigatoria = %s, identificador = %s, visivel = %s, ordem = %s,
                        automatico = %s, auto_tipo = %s, max_length = %s, mostrar_cadastro = %s,
                        cadastro_etapa = %s, opcoes_json = %s
                    WHERE id = %s
                    """,
                    (
                        column["nome"],
                        column["tipo"],
                        bool(column["obrigatoria"]),
                        bool(column["identificador"]),
                        bool(column["visivel"]),
                        index,
                        bool(column["automatico"]),
                        column.get("auto_tipo") or None,
                        column.get("max_length"),
                        bool(column["mostrar_cadastro"]),
                        int(column["cadastro_etapa"]),
                        json.dumps(column.get("opcoes") or [], ensure_ascii=False),
                        int(old_column["id"]),
                    ),
                )
                continue

            conn.execute(
                """
                INSERT INTO carteira_colunas (
                    carteira_id, nome, chave, tipo, obrigatoria, identificador, visivel, ordem,
                    automatico, auto_tipo, max_length, mostrar_cadastro, cadastro_etapa, opcoes_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    carteira_id,
                    column["nome"],
                    column["chave"],
                    column["tipo"],
                    bool(column["obrigatoria"]),
                    bool(column["identificador"]),
                    bool(column["visivel"]),
                    index,
                    bool(column["automatico"]),
                    column.get("auto_tipo") or None,
                    column.get("max_length"),
                    bool(column["mostrar_cadastro"]),
                    int(column["cadastro_etapa"]),
                    json.dumps(column.get("opcoes") or [], ensure_ascii=False),
                ),
            )

    def _sync_carteira_columns_sqlite(self, conn: sqlite3.Connection, carteira_id: int, columns: list[dict[str, Any]]) -> None:
        columns = self._dedupe_carteira_columns(columns)
        existing = {
            row["chave"]: dict(row)
            for row in conn.execute(
                """
                SELECT id, carteira_id, nome, chave, tipo, obrigatoria, identificador, visivel, ordem,
                       automatico, auto_tipo, max_length, mostrar_cadastro, cadastro_etapa, opcoes_json
                FROM carteira_colunas
                WHERE carteira_id = ?
                """,
                (carteira_id,),
            ).fetchall()
        }
        usage = self._carteira_column_usage_sqlite(conn, [int(row["id"]) for row in existing.values()])
        incoming_keys = {column["chave"] for column in columns}

        for old_key, old_column in existing.items():
            if old_key not in incoming_keys:
                if usage.get(int(old_column["id"]), {}).get("count", 0):
                    raise ValueError(f"Nao e possivel remover a coluna {old_column['nome']}: ela possui dados de producao.")
                conn.execute("DELETE FROM carteira_colunas WHERE id = ?", (int(old_column["id"]),))

        for index, column in enumerate(columns, start=1):
            old_column = existing.get(column["chave"])
            if old_column:
                self._validate_carteira_column_change(old_column, column, usage.get(int(old_column["id"]), {}))
                conn.execute(
                    """
                    UPDATE carteira_colunas
                    SET nome = ?, tipo = ?, obrigatoria = ?, identificador = ?, visivel = ?, ordem = ?,
                        automatico = ?, auto_tipo = ?, max_length = ?, mostrar_cadastro = ?,
                        cadastro_etapa = ?, opcoes_json = ?
                    WHERE id = ?
                    """,
                    (
                        column["nome"],
                        column["tipo"],
                        int(bool(column["obrigatoria"])),
                        int(bool(column["identificador"])),
                        int(bool(column["visivel"])),
                        index,
                        int(bool(column["automatico"])),
                        column.get("auto_tipo") or None,
                        column.get("max_length"),
                        int(bool(column["mostrar_cadastro"])),
                        int(column["cadastro_etapa"]),
                        json.dumps(column.get("opcoes") or [], ensure_ascii=False),
                        int(old_column["id"]),
                    ),
                )
                continue

            conn.execute(
                """
                INSERT INTO carteira_colunas (
                    carteira_id, nome, chave, tipo, obrigatoria, identificador, visivel, ordem,
                    automatico, auto_tipo, max_length, mostrar_cadastro, cadastro_etapa, opcoes_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    carteira_id,
                    column["nome"],
                    column["chave"],
                    column["tipo"],
                    int(bool(column["obrigatoria"])),
                    int(bool(column["identificador"])),
                    int(bool(column["visivel"])),
                    index,
                    int(bool(column["automatico"])),
                    column.get("auto_tipo") or None,
                    column.get("max_length"),
                    int(bool(column["mostrar_cadastro"])),
                    int(column["cadastro_etapa"]),
                    json.dumps(column.get("opcoes") or [], ensure_ascii=False),
                ),
            )

    def _carteira_column_usage_postgres(self, conn, column_ids: list[int]) -> dict[int, dict[str, Any]]:
        if not column_ids:
            return {}
        rows = conn.execute(
            """
            SELECT coluna_id, COUNT(*) AS count, MAX(LENGTH(COALESCE(valor_texto, ''))) AS max_text_length
            FROM producao_campos
            WHERE coluna_id = ANY(%s)
            GROUP BY coluna_id
            """,
            (column_ids,),
        ).fetchall()
        return {
            int(row["coluna_id"]): {
                "count": int(row["count"] or 0),
                "max_text_length": int(row["max_text_length"] or 0),
            }
            for row in rows
        }

    def _carteira_column_usage_sqlite(self, conn: sqlite3.Connection, column_ids: list[int]) -> dict[int, dict[str, Any]]:
        if not column_ids:
            return {}
        placeholders = ",".join("?" for _ in column_ids)
        rows = conn.execute(
            f"""
            SELECT coluna_id, COUNT(*) AS count, MAX(LENGTH(COALESCE(valor_texto, ''))) AS max_text_length
            FROM producao_campos
            WHERE coluna_id IN ({placeholders})
            GROUP BY coluna_id
            """,
            column_ids,
        ).fetchall()
        return {
            int(row["coluna_id"]): {
                "count": int(row["count"] or 0),
                "max_text_length": int(row["max_text_length"] or 0),
            }
            for row in rows
        }

    def _validate_carteira_column_change(self, old_column: dict[str, Any], new_column: dict[str, Any], usage: dict[str, Any]) -> None:
        if not int(usage.get("count") or 0):
            return
        old_type = str(old_column.get("tipo") or "texto")
        new_type = str(new_column.get("tipo") or "texto")
        if old_type != new_type:
            raise ValueError(
                f"Nao e possivel alterar o tipo da coluna {old_column.get('nome')}: ela possui dados de producao."
            )
        old_identifier = bool(old_column.get("identificador"))
        new_identifier = bool(new_column.get("identificador"))
        if old_identifier != new_identifier:
            raise ValueError(
                f"Nao e possivel alterar a coluna chave {old_column.get('nome')}: ela possui dados de producao."
            )
        max_length = new_column.get("max_length")
        if max_length not in (None, "") and int(max_length) < int(usage.get("max_text_length") or 0):
            raise ValueError(
                f"Nao e possivel reduzir o limite da coluna {old_column.get('nome')}: existem valores maiores que {max_length} caracteres."
            )

    def _dedupe_carteira_columns(self, columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        by_key: dict[str, dict[str, Any]] = {}
        for column in columns:
            key = self._slug(column.get("chave") or column.get("nome"))
            if not key:
                continue
            current = by_key.get(key)
            if not current:
                by_key[key] = column
                deduped.append(column)
                continue
            self._merge_column_definition(current, column)
        return deduped

    def _normalize_column_options(self, options: Any, column_key: str | None = None) -> list[str]:
        return self.schema_service.normalize_options(options, column_key)

    def _normalize_status_option(self, value: Any) -> str:
        return self.schema_service.normalize_status(value)

    def _merge_column_definition(self, target: dict[str, Any], source: dict[str, Any]) -> None:
        target["obrigatoria"] = bool(target.get("obrigatoria")) or bool(source.get("obrigatoria"))
        target["identificador"] = bool(target.get("identificador")) or bool(source.get("identificador"))
        target["visivel"] = target.get("visivel") is not False or source.get("visivel") is not False
        target["automatico"] = bool(target.get("automatico")) or bool(source.get("automatico"))
        target["mostrar_cadastro"] = target.get("mostrar_cadastro") is not False or source.get("mostrar_cadastro") is not False
        if not target.get("auto_tipo") and source.get("auto_tipo"):
            target["auto_tipo"] = source.get("auto_tipo")
        if target.get("max_length") in (None, "") and source.get("max_length") not in (None, ""):
            target["max_length"] = source.get("max_length")
        target_options = self._normalize_column_options(target.get("opcoes"), target.get("chave"))
        for option in self._normalize_column_options(source.get("opcoes"), target.get("chave")):
            if option not in target_options:
                target_options.append(option)
        target["opcoes"] = target_options

    def _consolidate_duplicate_carteira_columns_postgres(self, conn) -> int:
        rows = conn.execute(
            """
            SELECT c.id AS carteira_id, cc.id, cc.nome, cc.chave, cc.ordem, cc.identificador,
                   COUNT(pc.*) AS total_campos,
                   COUNT(*) FILTER (
                       WHERE COALESCE(pc.valor_texto, '') <> ''
                          OR pc.valor_numero IS NOT NULL
                          OR pc.valor_data IS NOT NULL
                          OR pc.valor_json IS NOT NULL
                   ) AS valores_preenchidos
            FROM carteira_colunas cc
            JOIN carteiras_negociais c ON c.id = cc.carteira_id
            LEFT JOIN producao_campos pc ON pc.coluna_id = cc.id
            GROUP BY c.id, cc.id, cc.nome, cc.chave, cc.ordem, cc.identificador
            ORDER BY c.id, cc.ordem, cc.id
            """
        ).fetchall()
        return self._consolidate_duplicate_column_rows(conn, rows, sqlite_mode=False)

    def _consolidate_duplicate_carteira_columns_sqlite(self, conn: sqlite3.Connection) -> int:
        rows = conn.execute(
            """
            SELECT c.id AS carteira_id, cc.id, cc.nome, cc.chave, cc.ordem, cc.identificador,
                   COUNT(pc.producao_id) AS total_campos,
                   SUM(CASE
                       WHEN COALESCE(pc.valor_texto, '') <> ''
                         OR pc.valor_numero IS NOT NULL
                         OR pc.valor_data IS NOT NULL
                         OR pc.valor_json IS NOT NULL
                       THEN 1 ELSE 0 END
                   ) AS valores_preenchidos
            FROM carteira_colunas cc
            JOIN carteiras_negociais c ON c.id = cc.carteira_id
            LEFT JOIN producao_campos pc ON pc.coluna_id = cc.id
            GROUP BY c.id, cc.id, cc.nome, cc.chave, cc.ordem, cc.identificador
            ORDER BY c.id, cc.ordem, cc.id
            """
        ).fetchall()
        return self._consolidate_duplicate_column_rows(conn, rows, sqlite_mode=True)

    def _consolidate_duplicate_column_rows(self, conn, rows, sqlite_mode: bool) -> int:
        groups: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for row in rows:
            data = dict(row)
            key = (int(data["carteira_id"]), self._header_key(data.get("nome") or data.get("chave")))
            if key[1]:
                groups.setdefault(key, []).append(data)

        merged = 0
        for items in groups.values():
            if len(items) < 2:
                continue
            items.sort(key=lambda item: (
                -int(item.get("valores_preenchidos") or 0),
                -int(item.get("total_campos") or 0),
                -int(bool(item.get("identificador"))),
                int(item.get("ordem") or 0),
                int(item.get("id") or 0),
            ))
            keeper = items[0]
            for duplicate in items[1:]:
                self._merge_duplicate_column_data(conn, int(keeper["id"]), int(duplicate["id"]), sqlite_mode)
                if sqlite_mode:
                    conn.execute("DELETE FROM carteira_colunas WHERE id = ?", (int(duplicate["id"]),))
                else:
                    conn.execute("DELETE FROM carteira_colunas WHERE id = %s", (int(duplicate["id"]),))
                merged += 1
        return merged

    def _merge_duplicate_column_data(self, conn, keeper_id: int, duplicate_id: int, sqlite_mode: bool) -> None:
        placeholder = "?" if sqlite_mode else "%s"
        rows = conn.execute(
            f"""
            SELECT producao_id, valor_texto, valor_numero, valor_data, valor_json
            FROM producao_campos
            WHERE coluna_id = {placeholder}
            """,
            (duplicate_id,),
        ).fetchall()
        for row in rows:
            data = dict(row)
            producao_id = int(data["producao_id"])
            existing = conn.execute(
                f"""
                SELECT valor_texto, valor_numero, valor_data, valor_json
                FROM producao_campos
                WHERE producao_id = {placeholder} AND coluna_id = {placeholder}
                """,
                (producao_id, keeper_id),
            ).fetchone()
            if not existing:
                conn.execute(
                    f"""
                    UPDATE producao_campos
                    SET coluna_id = {placeholder}
                    WHERE producao_id = {placeholder} AND coluna_id = {placeholder}
                    """,
                    (keeper_id, producao_id, duplicate_id),
                )
                continue
            if self._is_empty_dynamic_row(dict(existing)) and not self._is_empty_dynamic_row(data):
                conn.execute(
                    f"""
                    UPDATE producao_campos
                    SET valor_texto = {placeholder},
                        valor_numero = {placeholder},
                        valor_data = {placeholder},
                        valor_json = {placeholder},
                        updated_at = {self._sql_now(sqlite_mode)}
                    WHERE producao_id = {placeholder} AND coluna_id = {placeholder}
                    """,
                    (
                        data.get("valor_texto"),
                        data.get("valor_numero"),
                        data.get("valor_data"),
                        json.dumps(data.get("valor_json"), ensure_ascii=False) if sqlite_mode and isinstance(data.get("valor_json"), (dict, list)) else data.get("valor_json"),
                        producao_id,
                        keeper_id,
                    ),
                )
            conn.execute(
                f"DELETE FROM producao_campos WHERE producao_id = {placeholder} AND coluna_id = {placeholder}",
                (producao_id, duplicate_id),
            )

    def _is_empty_dynamic_row(self, row: dict[str, Any]) -> bool:
        return (
            str(row.get("valor_texto") or "").strip() == ""
            and row.get("valor_numero") is None
            and row.get("valor_data") is None
            and row.get("valor_json") in (None, "", [], {})
        )

    def _sql_now(self, sqlite_mode: bool) -> str:
        return "CURRENT_TIMESTAMP" if sqlite_mode else "NOW()"

    def _record_carteira_schema_version_postgres(self, conn, carteira_id: int, action: str, created_at: str) -> None:
        snapshot = self._carteira_schema_snapshot_postgres(conn, carteira_id)
        version_number = int(conn.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 AS next_version FROM carteira_schema_versions WHERE carteira_id = %s",
            (carteira_id,),
        ).fetchone()["next_version"])
        conn.execute(
            """
            INSERT INTO carteira_schema_versions (carteira_id, version_number, action, schema_json, created_at)
            VALUES (%s, %s, %s, %s::jsonb, %s)
            """,
            (carteira_id, version_number, action, json.dumps(snapshot, ensure_ascii=False), created_at),
        )

    def _record_carteira_schema_version_sqlite(self, conn: sqlite3.Connection, carteira_id: int, action: str, created_at: str) -> None:
        snapshot = self._carteira_schema_snapshot_sqlite(conn, carteira_id)
        version_number = int(conn.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 AS next_version FROM carteira_schema_versions WHERE carteira_id = ?",
            (carteira_id,),
        ).fetchone()["next_version"])
        conn.execute(
            """
            INSERT INTO carteira_schema_versions (carteira_id, version_number, action, schema_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (carteira_id, version_number, action, json.dumps(snapshot, ensure_ascii=False), created_at),
        )

    def _schema_versions_payload(self, carteira: dict[str, Any], rows) -> dict[str, Any]:
        versions = []
        for row in rows:
            data = dict(row)
            raw_snapshot = data.get("schema_json")
            if isinstance(raw_snapshot, dict):
                snapshot = raw_snapshot
            else:
                try:
                    snapshot = json.loads(raw_snapshot or "{}")
                except (TypeError, json.JSONDecodeError):
                    snapshot = {}
            versions.append({
                "id": int(data["id"]),
                "version_number": int(data["version_number"]),
                "action": data.get("action") or "",
                "created_at": str(data.get("created_at") or ""),
                "schema": snapshot,
            })
        return {
            "carteira": {
                "id": int(carteira["id"]),
                "nome": carteira.get("nome") or "",
                "slug": carteira.get("slug") or "",
            },
            "items": versions,
        }

    def _carteira_schema_snapshot_postgres(self, conn, carteira_id: int) -> dict[str, Any]:
        carteira = dict(conn.execute(
            """
            SELECT id, nome, slug, descricao, active, usa_percentual_ho, percentual_ho_padrao,
                   percentual_ho_minimo, percentual_ho_maximo, calculo_automatico_ho, modo_schema,
                   created_at, updated_at
            FROM carteiras_negociais
            WHERE id = %s
            """,
            (carteira_id,),
        ).fetchone())
        columns = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, nome, chave, tipo, obrigatoria, identificador, visivel, ordem,
                       automatico, auto_tipo, max_length, mostrar_cadastro, cadastro_etapa, opcoes_json
                FROM carteira_colunas
                WHERE carteira_id = %s
                ORDER BY ordem, id
                """,
                (carteira_id,),
            ).fetchall()
        ]
        rules = [
            dict(row)
            for row in conn.execute(
                """
                SELECT codigo, nome, tipo_calculo, motor_calculo,
                       coluna_base_id, coluna_destino_id,
                       coluna_base_vista_id, coluna_base_parcelado_id,
                       coluna_valor_recebido_id, coluna_percentual_efetivo_id,
                       percentual_padrao, percentual_minimo, percentual_maximo,
                       automatico, ativo, casas_decimais
                FROM carteira_regras_calculo
                WHERE carteira_id = %s
                ORDER BY codigo
                """,
                (carteira_id,),
            ).fetchall()
        ]
        return self._normalize_schema_snapshot(carteira, columns, rules)

    def _carteira_schema_snapshot_sqlite(self, conn: sqlite3.Connection, carteira_id: int) -> dict[str, Any]:
        carteira = dict(conn.execute(
            """
            SELECT id, nome, slug, descricao, active, usa_percentual_ho, percentual_ho_padrao,
                   percentual_ho_minimo, percentual_ho_maximo, calculo_automatico_ho, modo_schema,
                   created_at, updated_at
            FROM carteiras_negociais
            WHERE id = ?
            """,
            (carteira_id,),
        ).fetchone())
        columns = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, nome, chave, tipo, obrigatoria, identificador, visivel, ordem,
                       automatico, auto_tipo, max_length, mostrar_cadastro, cadastro_etapa, opcoes_json
                FROM carteira_colunas
                WHERE carteira_id = ?
                ORDER BY ordem, id
                """,
                (carteira_id,),
            ).fetchall()
        ]
        rules = [
            dict(row)
            for row in conn.execute(
                """
                SELECT codigo, nome, tipo_calculo, motor_calculo,
                       coluna_base_id, coluna_destino_id,
                       coluna_base_vista_id, coluna_base_parcelado_id,
                       coluna_valor_recebido_id, coluna_percentual_efetivo_id,
                       percentual_padrao, percentual_minimo, percentual_maximo,
                       automatico, ativo, casas_decimais
                FROM carteira_regras_calculo
                WHERE carteira_id = ?
                ORDER BY codigo
                """,
                (carteira_id,),
            ).fetchall()
        ]
        return self._normalize_schema_snapshot(carteira, columns, rules)

    def _normalize_schema_snapshot(
        self,
        carteira: dict[str, Any],
        columns: list[dict[str, Any]],
        rules: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        def scalar(value: Any) -> Any:
            if isinstance(value, (date, datetime)):
                return value.isoformat()
            if isinstance(value, Decimal):
                return float(value)
            return value

        normalized_columns = []
        for column in columns:
            item = {key: scalar(value) for key, value in column.items()}
            try:
                item["opcoes"] = json.loads(item.get("opcoes_json") or "[]")
            except (TypeError, json.JSONDecodeError):
                item["opcoes"] = []
            normalized_columns.append(item)

        return {
            "carteira": {key: scalar(value) for key, value in carteira.items()},
            "colunas": normalized_columns,
            "regras_calculo": [
                {key: scalar(value) for key, value in rule.items()}
                for rule in (rules or [])
            ],
        }
