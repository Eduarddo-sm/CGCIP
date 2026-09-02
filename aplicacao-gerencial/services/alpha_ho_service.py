from __future__ import annotations

import base64
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from services.alpha_ho_rules import dias_de_atraso, honorarios_base
from services.alpha_meta_pdf_service import AlphaMetaPdfError, AlphaMetaPdfParser


MONEY = Decimal("0.01")
PERCENT = Decimal("0.0001")


class AlphaHonorariosService:
    def __init__(self, database_url: str, data_dir: Path) -> None:
        self.database_url = str(database_url or "").replace("postgresql+psycopg://", "postgresql://", 1)
        self.storage_dir = Path(data_dir) / "alpha_metas"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.parser = AlphaMetaPdfParser()

    def _connect(self):
        if not self.database_url.startswith(("postgresql://", "postgres://")):
            raise RuntimeError("Metas excepcionais da Alpha requerem PostgreSQL.")
        connection = psycopg.connect(self.database_url, row_factory=dict_row)
        connection.execute("SET search_path TO negocial, public")
        return connection

    @staticmethod
    def _json_value(value: Any) -> Any:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        return value

    def preview_pdf(self, file_name: str, content_base64: str, username: str) -> dict:
        try:
            content = base64.b64decode(content_base64, validate=True)
        except Exception as exc:
            raise ValueError("O conteudo enviado nao e um PDF valido.") from exc
        parsed = self.parser.parse(content, file_name)
        digest = hashlib.sha256(content).hexdigest()
        stored_path = self.storage_dir / f"{digest}.pdf"
        if not stored_path.exists():
            stored_path.write_bytes(content)

        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM alpha_meta_imports WHERE file_sha256 = %s",
                (digest,),
            ).fetchone()
            if existing:
                return {"item": self._import_payload(connection, int(existing["id"])), "duplicate": True}
            status = "VALIDADO" if parsed["validation"]["valid"] else "ERRO"
            row = connection.execute(
                """
                INSERT INTO alpha_meta_imports (
                    file_name, file_sha256, source_path, quarter, office, status,
                    raw_data_json, validation_json, created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    file_name,
                    digest,
                    str(stored_path),
                    parsed["quarter"],
                    parsed["office"],
                    status,
                    Jsonb(parsed),
                    Jsonb(parsed["validation"]),
                    username,
                ),
            ).fetchone()
            connection.commit()
            return {"item": self._import_payload(connection, int(row["id"])), "duplicate": False}

    def list_imports(self, limit: int = 50) -> dict:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, file_name, file_sha256, quarter, office, status,
                       validation_json, created_by, applied_by, created_at, applied_at
                FROM alpha_meta_imports
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (max(1, min(int(limit), 200)),),
            ).fetchall()
            return {"items": [self._serialize_row(row) for row in rows]}

    def get_import(self, import_id: int) -> dict:
        with self._connect() as connection:
            return {"item": self._import_payload(connection, import_id)}

    def apply_import(self, import_id: int, username: str) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM alpha_meta_imports WHERE id = %s FOR UPDATE",
                (import_id,),
            ).fetchone()
            if not row:
                raise ValueError("Importacao de metas nao encontrada.")
            if row["status"] == "APLICADO":
                calculation = self.recalculate(
                    (row["raw_data_json"] or {}).get("months") or None,
                    connection=connection,
                )
                connection.commit()
                return {
                    "item": self._import_payload(connection, import_id),
                    "calculation": calculation,
                    "already_applied": True,
                }
            validation = row["validation_json"] or {}
            if not validation.get("valid"):
                raise ValueError("A importacao possui erros de validacao e nao pode ser aplicada.")
            parsed = row["raw_data_json"]
            month_keys = parsed.get("months") or []
            portfolio_keys = [goal["portfolio_key"] for goal in parsed.get("goals") or []]
            if month_keys and portfolio_keys:
                connection.execute(
                    """
                    UPDATE alpha_portfolio_goals
                    SET active = FALSE
                    WHERE active = TRUE
                      AND competence = ANY(%s::date[])
                      AND portfolio_key = ANY(%s::text[])
                    """,
                    (month_keys, portfolio_keys),
                )
            for goal in parsed.get("goals") or []:
                for month in goal["months"]:
                    connection.execute(
                        """
                        INSERT INTO alpha_portfolio_goals (
                            import_id, portfolio, portfolio_key, group_name, competence,
                            meta_caixa, retomadas_count, retomadas_value, meta_pnt,
                            source_type, active
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'PDF', TRUE)
                        ON CONFLICT (import_id, portfolio_key, competence)
                        DO UPDATE SET
                            portfolio = EXCLUDED.portfolio,
                            group_name = EXCLUDED.group_name,
                            meta_caixa = EXCLUDED.meta_caixa,
                            retomadas_count = EXCLUDED.retomadas_count,
                            retomadas_value = EXCLUDED.retomadas_value,
                            meta_pnt = EXCLUDED.meta_pnt,
                            active = TRUE
                        """,
                        (
                            import_id,
                            goal["portfolio"],
                            goal["portfolio_key"],
                            goal["group_name"],
                            month["competence"],
                            month["meta_caixa"],
                            month["retomadas_count"],
                            month["retomadas_value"],
                            month["meta_pnt"],
                        ),
                    )
            connection.execute(
                """
                UPDATE alpha_meta_imports previous
                SET status = 'SUBSTITUIDO'
                WHERE previous.id <> %s
                  AND previous.status = 'APLICADO'
                  AND EXISTS (
                      SELECT 1
                      FROM alpha_portfolio_goals old_goal
                      WHERE old_goal.import_id = previous.id
                        AND old_goal.competence = ANY(%s::date[])
                  )
                """,
                (import_id, month_keys),
            )
            connection.execute(
                """
                UPDATE alpha_meta_imports
                SET status = 'APLICADO', applied_by = %s, applied_at = NOW()
                WHERE id = %s
                """,
                (username, import_id),
            )
            calculation = self.recalculate(month_keys, connection=connection)
            self._audit(
                connection,
                username,
                "alpha_meta_apply",
                "alpha_meta_import",
                import_id,
                {"quarter": row["quarter"], "months": month_keys, "calculation": calculation},
            )
            connection.commit()
            return {
                "item": self._import_payload(connection, import_id),
                "calculation": calculation,
                "already_applied": False,
            }

    def list_goals(self, competence: str = "") -> dict:
        params: list[Any] = []
        condition = "WHERE goal.active = TRUE"
        if competence:
            condition += " AND goal.competence = %s"
            params.append(competence)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    goal.*,
                    meta.quarter,
                    meta.file_name,
                    previous.source_type AS previous_source_type,
                    previous.meta_caixa AS previous_meta_caixa,
                    previous.retomadas_count AS previous_retomadas_count,
                    previous.retomadas_value AS previous_retomadas_value,
                    previous.meta_pnt AS previous_meta_pnt
                FROM alpha_portfolio_goals goal
                LEFT JOIN alpha_meta_imports meta ON meta.id = goal.import_id
                LEFT JOIN alpha_portfolio_goals previous ON previous.id = goal.supersedes_goal_id
                {condition}
                ORDER BY goal.competence DESC, goal.group_name, goal.portfolio
                """,
                params,
            ).fetchall()
            return {"items": [self._serialize_row(row) for row in rows]}

    def override_goal(self, goal_id: int, payload: dict, username: str) -> dict:
        reason = str(payload.get("reason") or "").strip()
        if len(reason) < 5:
            raise ValueError("Informe uma justificativa com pelo menos 5 caracteres.")

        values = {
            "meta_caixa": self._nonnegative_money(payload.get("meta_caixa"), "Meta caixa"),
            "retomadas_count": self._nonnegative_integer(
                payload.get("retomadas_count"),
                "Quantidade de retomadas",
            ),
            "retomadas_value": self._nonnegative_money(
                payload.get("retomadas_value"),
                "Valor de retomadas",
            ),
        }
        values["meta_pnt"] = (values["meta_caixa"] + values["retomadas_value"]).quantize(MONEY)

        with self._connect() as connection:
            current = connection.execute(
                """
                SELECT *
                FROM alpha_portfolio_goals
                WHERE id = %s AND active = TRUE
                FOR UPDATE
                """,
                (goal_id,),
            ).fetchone()
            if not current:
                raise ValueError("A meta ativa nao foi encontrada ou ja foi substituida.")

            connection.execute(
                "UPDATE alpha_portfolio_goals SET active = FALSE WHERE id = %s",
                (goal_id,),
            )
            created = connection.execute(
                """
                INSERT INTO alpha_portfolio_goals (
                    import_id, portfolio, portfolio_key, group_name, competence,
                    meta_caixa, retomadas_count, retomadas_value, meta_pnt,
                    source_type, active, supersedes_goal_id, adjustment_reason, created_by
                )
                VALUES (
                    NULL, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    'MANUAL', TRUE, %s, %s, %s
                )
                RETURNING *
                """,
                (
                    current["portfolio"],
                    current["portfolio_key"],
                    current["group_name"],
                    current["competence"],
                    values["meta_caixa"],
                    values["retomadas_count"],
                    values["retomadas_value"],
                    values["meta_pnt"],
                    goal_id,
                    reason,
                    username,
                ),
            ).fetchone()
            calculation = self.recalculate(
                [current["competence"].isoformat()],
                connection=connection,
            )
            before = self._serialize_row(current)
            after = self._serialize_row(created)
            self._audit(
                connection,
                username,
                "alpha_goal_manual_override",
                "alpha_portfolio_goal",
                created["id"],
                {"before": before, "after": after, "reason": reason},
            )
            connection.commit()
            return {
                "item": after,
                "previous": before,
                "calculation": calculation,
            }

    def list_rules(self) -> dict:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM alpha_ho_rule_versions ORDER BY effective_from DESC, id DESC"
            ).fetchall()
            return {"items": [self._serialize_row(row) for row in rows]}

    def save_rule(self, payload: dict, username: str) -> dict:
        matrix = payload.get("matrix")
        if not isinstance(matrix, dict):
            raise ValueError("A matriz de honorarios e obrigatoria.")
        self._validate_matrix(matrix)
        effective_from = str(payload.get("effective_from") or "").strip()
        if not effective_from:
            raise ValueError("Informe a data inicial da regra.")
        activate = bool(payload.get("activate", True))
        with self._connect() as connection:
            if activate:
                connection.execute(
                    """
                    UPDATE alpha_ho_rule_versions
                    SET status = 'ENCERRADA',
                        effective_to = GREATEST(effective_from, %s::date - INTERVAL '1 day')
                    WHERE status = 'ATIVA' AND effective_from <= %s::date
                    """,
                    (effective_from, effective_from),
                )
            row = connection.execute(
                """
                INSERT INTO alpha_ho_rule_versions (
                    name, effective_from, effective_to, status, matrix_json,
                    created_by, activated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, CASE WHEN %s THEN NOW() ELSE NULL END)
                RETURNING *
                """,
                (
                    str(payload.get("name") or "Matriz Alpha").strip(),
                    effective_from,
                    payload.get("effective_to") or None,
                    "ATIVA" if activate else "RASCUNHO",
                    Jsonb(matrix),
                    username,
                    activate,
                ),
            ).fetchone()
            self._audit(
                connection,
                username,
                "alpha_ho_rule_create",
                "alpha_ho_rule_version",
                row["id"],
                self._serialize_row(row),
            )
            connection.commit()
            return {"item": self._serialize_row(row)}

    def recalculate(
        self,
        competences: list[str] | None = None,
        *,
        connection=None,
    ) -> dict:
        owns_connection = connection is None
        connection = connection or self._connect()
        try:
            params: list[Any] = []
            competence_filter = ""
            if competences:
                competence_filter = "AND record.competencia = ANY(%s::date[])"
                params.append(competences)
            records = connection.execute(
                f"""
                SELECT
                    record.id,
                    record.competencia,
                    record.data_acordo,
                    record.valor_total_acordo,
                    record.valor_entrada,
                    record.tipo_acordo,
                    record.status,
                    record.data_pagamento,
                    detail.portfolio,
                    detail.data_primeiro_atraso,
                    goal.id AS goal_id,
                    goal.meta_pnt,
                    rule.id AS rule_id,
                    rule.matrix_json
                FROM producao_registros record
                JOIN producao_alpha detail ON detail.producao_id = record.id
                LEFT JOIN alpha_portfolio_goals goal
                  ON goal.active = TRUE
                 AND goal.competence = record.competencia
                 AND replace(goal.portfolio_key, 'FINANCEIRA', '') = replace(
                     regexp_replace(
                         upper(translate(coalesce(detail.portfolio, ''), 'ÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ', 'AAAAEEEIIIOOOOUUUC')),
                         '[^A-Z0-9]+', '', 'g'
                     ),
                     'FINANCEIRA',
                     ''
                 )
                JOIN LATERAL (
                    SELECT version.*
                    FROM alpha_ho_rule_versions version
                    WHERE version.status = 'ATIVA'
                      AND version.effective_from <= record.competencia
                      AND (version.effective_to IS NULL OR version.effective_to >= record.competencia)
                    ORDER BY version.effective_from DESC, version.id DESC
                    LIMIT 1
                ) rule ON TRUE
                WHERE record.carteira = 'ALPHA'
                  AND detail.data_primeiro_atraso IS NOT NULL
                  AND detail.ho_origem = 'CALCULADO'
                  {competence_filter}
                ORDER BY record.competencia, detail.portfolio, record.data_acordo, record.id
                """,
                params,
            ).fetchall()

            totals: dict[tuple[date, str], Decimal] = {}
            for record in records:
                matrix = record["matrix_json"] or {}
                eligible = set(matrix.get("eligible_statuses") or [])
                key = (record["competencia"], self._portfolio_key(record["portfolio"]))
                totals.setdefault(key, Decimal("0"))
                if not eligible or record["status"] in eligible:
                    totals[key] += Decimal(record["valor_total_acordo"] or 0)

            calculated = 0
            unmatched = 0
            for record in records:
                key = (record["competencia"], self._portfolio_key(record["portfolio"]))
                production = totals.get(key, Decimal("0"))
                goal_value = Decimal(record["meta_pnt"] or 0)
                attainment = (
                    (production / goal_value * Decimal("100")).quantize(PERCENT, rounding=ROUND_HALF_UP)
                    if goal_value > 0
                    else Decimal("0")
                )
                delay_days = max(
                    1,
                    dias_de_atraso(
                        record["data_primeiro_atraso"],
                        record["status"],
                        record["data_pagamento"],
                    ) or 0,
                )
                rate, delay_band, attainment_band = self._select_rate(
                    record["matrix_json"] or {},
                    delay_days,
                    attainment,
                )
                base_value, base_source = honorarios_base(record)
                honorarios = (base_value * rate / Decimal("100")).quantize(MONEY, rounding=ROUND_HALF_UP)
                details = {
                    "portfolio": record["portfolio"],
                    "goal": str(goal_value),
                    "status": record["status"],
                    "agreement_type": record["tipo_acordo"],
                    "base_source": base_source,
                    "delay_band": delay_band,
                    "attainment_band": attainment_band,
                    "eligible_statuses": (record["matrix_json"] or {}).get("eligible_statuses") or [],
                }
                connection.execute(
                    """
                    INSERT INTO alpha_ho_calculations (
                        producao_id, competence, portfolio_key, goal_id, rule_version_id,
                        delay_days, accumulated_production, attainment_percent, applied_rate,
                        base_value, calculated_honorarios, calculation_mode, details_json,
                        calculated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'CONFERENCIA', %s, NOW())
                    ON CONFLICT (producao_id, calculation_mode)
                    DO UPDATE SET
                        competence = EXCLUDED.competence,
                        portfolio_key = EXCLUDED.portfolio_key,
                        goal_id = EXCLUDED.goal_id,
                        rule_version_id = EXCLUDED.rule_version_id,
                        delay_days = EXCLUDED.delay_days,
                        accumulated_production = EXCLUDED.accumulated_production,
                        attainment_percent = EXCLUDED.attainment_percent,
                        applied_rate = EXCLUDED.applied_rate,
                        base_value = EXCLUDED.base_value,
                        calculated_honorarios = EXCLUDED.calculated_honorarios,
                        details_json = EXCLUDED.details_json,
                        calculated_at = NOW()
                    """,
                    (
                        record["id"],
                        record["competencia"],
                        key[1],
                        record["goal_id"],
                        record["rule_id"],
                        delay_days,
                        production,
                        attainment,
                        rate,
                        base_value,
                        honorarios,
                        Jsonb(details),
                    ),
                )
                calculated += 1
                unmatched += int(record["goal_id"] is None)
            self._materialize_exceptional_ho(connection, competences)
            if owns_connection:
                connection.commit()
            return {"calculated": calculated, "unmatched_portfolios": unmatched, "mode": "CONFERENCIA"}
        finally:
            if owns_connection:
                connection.close()

    def calculation_summary(self, competence: str = "") -> dict:
        params: list[Any] = []
        condition = "WHERE calculation.calculation_mode = 'CONFERENCIA'"
        if competence:
            condition += " AND calculation.competence = %s"
            params.append(competence)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    calculation.*,
                    record.cliente,
                    record.status,
                    detail.portfolio,
                    goal.meta_pnt
                FROM alpha_ho_calculations calculation
                JOIN producao_registros record ON record.id = calculation.producao_id
                JOIN producao_alpha detail ON detail.producao_id = record.id
                LEFT JOIN alpha_portfolio_goals goal ON goal.id = calculation.goal_id
                {condition}
                ORDER BY calculation.competence DESC, detail.portfolio, record.cliente
                """,
                params,
            ).fetchall()
            serialized = [self._serialize_row(row) for row in rows]
            return {
                "items": serialized,
                "summary": {
                    "records": len(rows),
                    "base_value": str(sum((Decimal(row["base_value"]) for row in rows), Decimal("0"))),
                    "calculated_honorarios": str(
                        sum((Decimal(row["calculated_honorarios"]) for row in rows), Decimal("0"))
                    ),
                    "unmatched_portfolios": sum(1 for row in rows if row["goal_id"] is None),
                    "mode": "CONFERENCIA",
                },
            }

    def recalculate_active(self) -> dict:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT competence
                FROM alpha_portfolio_goals
                WHERE active = TRUE
                ORDER BY competence
                """
            ).fetchall()
        competences = [row["competence"].isoformat() for row in rows]
        if not competences:
            result = {"calculated": 0, "unmatched_portfolios": 0, "mode": "CONFERENCIA"}
        else:
            result = self.recalculate(competences)
        result["aligned_existing"] = self.align_existing_calculations()
        return result

    def align_existing_calculations(self) -> int:
        """Align stored calculations without changing their historical rate or goal."""
        with self._connect() as connection:
            result = connection.execute(
                """
                UPDATE alpha_ho_calculations calculation
                SET delay_days = GREATEST(
                        1,
                        CASE
                            WHEN record.status IN ('PAGAMENTO_REALIZADO', 'AGUARDANDO_BAIXA')
                                 AND record.data_pagamento IS NOT NULL
                            THEN record.data_pagamento - detail.data_primeiro_atraso
                            ELSE CURRENT_DATE - detail.data_primeiro_atraso
                        END
                    ),
                    base_value = CASE
                        WHEN upper(replace(record.tipo_acordo, ' ', '_')) = 'PARCELADO'
                        THEN record.valor_entrada
                        ELSE record.valor_total_acordo
                    END,
                    calculated_honorarios = round(
                        (
                            CASE
                                WHEN upper(replace(record.tipo_acordo, ' ', '_')) = 'PARCELADO'
                                THEN record.valor_entrada
                                ELSE record.valor_total_acordo
                            END
                            * calculation.applied_rate / 100
                        )::numeric,
                        2
                    ),
                    details_json = jsonb_set(
                        COALESCE(calculation.details_json, '{}'::jsonb),
                        '{base_source}',
                        to_jsonb(
                            CASE
                                WHEN upper(replace(record.tipo_acordo, ' ', '_')) = 'PARCELADO'
                                THEN 'VALOR_DA_ENTRADA'
                                ELSE 'VALOR_DO_ACORDO'
                            END::text
                        ),
                        TRUE
                    ),
                    calculated_at = NOW()
                FROM producao_registros record
                JOIN producao_alpha detail ON detail.producao_id = record.id
                WHERE calculation.producao_id = record.id
                  AND calculation.calculation_mode = 'CONFERENCIA'
                  AND detail.data_primeiro_atraso IS NOT NULL
                """
            )
            updated = max(int(result.rowcount or 0), 0)
            if updated:
                self._materialize_exceptional_ho(connection, None)
            connection.commit()
            return updated

    def _import_payload(self, connection, import_id: int) -> dict:
        row = connection.execute(
            "SELECT * FROM alpha_meta_imports WHERE id = %s",
            (import_id,),
        ).fetchone()
        if not row:
            raise ValueError("Importacao de metas nao encontrada.")
        return self._serialize_row(row)

    @staticmethod
    def _materialize_exceptional_ho(connection, competences: list[str] | None) -> int:
        rule = connection.execute(
            """
            SELECT rule.coluna_destino_id
            FROM carteira_regras_calculo rule
            JOIN carteiras_negociais wallet ON wallet.id = rule.carteira_id
            WHERE wallet.slug = 'ALPHA'
              AND rule.codigo = 'HONORARIOS'
              AND rule.motor_calculo = 'ALPHA_EXCEPCIONAL'
              AND rule.ativo = TRUE
              AND rule.automatico = TRUE
              AND rule.coluna_destino_id IS NOT NULL
            LIMIT 1
            """
        ).fetchone()
        if not rule:
            return 0
        params: list[Any] = [int(rule["coluna_destino_id"])]
        competence_filter = ""
        if competences:
            competence_filter = "AND calculation.competence = ANY(%s::date[])"
            params.append(competences)
        result = connection.execute(
            f"""
            INSERT INTO producao_campos (
                producao_id, coluna_id, valor_texto, valor_numero,
                valor_data, valor_json, updated_at
            )
            SELECT
                calculation.producao_id,
                %s,
                NULL,
                calculation.calculated_honorarios,
                NULL,
                NULL,
                NOW()
            FROM alpha_ho_calculations calculation
            WHERE calculation.calculation_mode = 'CONFERENCIA'
              {competence_filter}
            ON CONFLICT (producao_id, coluna_id)
            DO UPDATE SET
                valor_texto = NULL,
                valor_numero = EXCLUDED.valor_numero,
                valor_data = NULL,
                valor_json = NULL,
                updated_at = NOW()
            """,
            params,
        )
        updated = max(int(result.rowcount or 0), 0)
        if updated:
            connection.execute(
                """
                INSERT INTO operational_versions (scope, version, updated_at)
                VALUES ('producao', 1, NOW())
                ON CONFLICT (scope)
                DO UPDATE SET version = operational_versions.version + 1,
                              updated_at = NOW()
                """
            )
        return updated

    @classmethod
    def _serialize_row(cls, row: dict) -> dict:
        return {key: cls._json_value(value) for key, value in dict(row).items()}

    @staticmethod
    def _nonnegative_money(value: Any, label: str) -> Decimal:
        try:
            if isinstance(value, (int, float, Decimal)):
                parsed = Decimal(str(value))
            else:
                text = str(value or "").strip()
                normalized = text.replace(".", "").replace(",", ".") if "," in text else text
                parsed = Decimal(normalized)
        except Exception as exc:
            raise ValueError(f"{label} possui um valor invalido.") from exc
        if parsed < 0:
            raise ValueError(f"{label} nao pode ser negativa.")
        return parsed.quantize(MONEY, rounding=ROUND_HALF_UP)

    @staticmethod
    def _nonnegative_integer(value: Any, label: str) -> int:
        try:
            parsed = int(value)
        except Exception as exc:
            raise ValueError(f"{label} possui um valor invalido.") from exc
        if parsed < 0:
            raise ValueError(f"{label} nao pode ser negativa.")
        return parsed

    @staticmethod
    def _portfolio_key(value: str | None) -> str:
        from services.alpha_meta_pdf_service import normalize_portfolio_key

        return normalize_portfolio_key(value or "").replace("FINANCEIRA", "")

    @staticmethod
    def _select_rate(matrix: dict, delay_days: int, attainment: Decimal) -> tuple[Decimal, str, str]:
        if attainment < 85:
            attainment_key = "BELOW_85"
        elif attainment <= 110:
            attainment_key = "BETWEEN_85_110"
        else:
            attainment_key = "ABOVE_110"
        for band in matrix.get("delay_bands") or []:
            minimum = int(band.get("min") or 0)
            maximum = band.get("max")
            if delay_days >= minimum and (maximum is None or delay_days <= int(maximum)):
                rate = Decimal(str((band.get("rates") or {}).get(attainment_key, 0)))
                return rate, f"{minimum}-{maximum or '+'}", attainment_key
        raise ValueError(f"Nenhuma faixa de atraso encontrada para {delay_days} dias.")

    @staticmethod
    def _validate_matrix(matrix: dict) -> None:
        delay_bands = matrix.get("delay_bands")
        if not isinstance(delay_bands, list) or not delay_bands:
            raise ValueError("A matriz deve possuir faixas de atraso.")
        for band in delay_bands:
            rates = band.get("rates") or {}
            for key in ("BELOW_85", "BETWEEN_85_110", "ABOVE_110"):
                try:
                    value = Decimal(str(rates[key]))
                except Exception as exc:
                    raise ValueError(f"Percentual ausente na faixa {key}.") from exc
                if value < 0 or value > 100:
                    raise ValueError("Os percentuais devem estar entre 0 e 100.")

    @staticmethod
    def _audit(connection, username: str, action: str, entity_type: str, entity_id: Any, after: dict) -> None:
        connection.execute(
            """
            INSERT INTO audit_logs (
                actor_username, action, entity_type, entity_id, source,
                after_json, diff_json, created_at
            )
            VALUES (%s, %s, %s, %s, 'gerencial', %s, %s, %s)
            """,
            (
                username,
                action,
                entity_type,
                str(entity_id),
                Jsonb(after),
                Jsonb({"changed": True}),
                datetime.now(timezone.utc),
            ),
        )
