from __future__ import annotations

import re
from collections.abc import Iterable

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine


IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CONTRACT_KEY_SQL = """
COALESCE(NULLIF(REGEXP_REPLACE(TRIM(CAST(\"contrato\" AS TEXT)), '^0+', ''), ''), '0')
"""
LAST_ACTION_COLUMNS = [
    "carteira_db", "contrato", "contrato_key_db", "nome_cliente_db",
    "ultimo_acionamento", "data_ultimo_acionamento", "hora_ultimo_acionamento",
    "observacao_ultimo_acionamento", "operador", "total_acionamentos",
]
ALLOWED_ACTIONS = (
    "ATUALIZAÇÃO CADASTRAL", "NEGOCIAÇÃO", "POSSÍVEL NEGÓCIO",
    "DESINTERESSE DA PARTE", "CONTRAPROPOSTA", "RECADO S/RETORNO",
    "RECADO RETORNO", "CARTA PRECATÓRIA", "DESCONHECE O CLIENTE", "PAGO",
    "PROMESSA DE PAGAMENTO", "QUEBRA", "RECEPTIVO", "RECUPERAÇÃO JUDICIAL",
    "SEM CONTATO", "INFORMAÇÃO", "MONITORAÇÃO DE ACORDO",
)


def _quote(value: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise ValueError(f"Identificador SQL invalido: {value}")
    return f'"{value}"'


class ExternalCrmRepository:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.table = f"{_quote(settings.postgres_schema)}.{_quote(settings.postgres_table)}"
        url = URL.create(
            "postgresql+psycopg",
            username=settings.postgres_user,
            password=settings.postgres_password,
            host=settings.postgres_host,
            port=settings.postgres_port,
            database=settings.postgres_db,
        )
        self.engine: Engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=1,
            pool_recycle=900,
            connect_args={"connect_timeout": 10, "options": "-c statement_timeout=120000 -c default_transaction_read_only=on"},
        )

    @staticmethod
    def _keys(values: Iterable[str]) -> tuple[str, ...]:
        result: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = str(raw or "").strip()
            value = value.split(".", 1)[0] if re.fullmatch(r"\d+\.0+", value) else value
            value = value.lstrip("0") or ("0" if value else "")
            if value and value not in seen:
                result.append(value)
                seen.add(value)
        return tuple(result)

    def test_connection(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def latest_actions(self, contracts: Iterable[str], *, discador: bool = False) -> pd.DataFrame:
        manual, dialer = self.latest_actions_bundle(contracts)
        return dialer if discador else manual

    def latest_actions_bundle(self, contracts: Iterable[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
        keys = self._keys(contracts)
        if not keys:
            empty = pd.DataFrame(columns=LAST_ACTION_COLUMNS)
            return empty.copy(), empty.copy()
        query = text(f"""
            WITH requested_contracts AS (
                SELECT UNNEST(CAST(:contracts AS TEXT[])) AS contrato_key
            ), source AS (
                SELECT CAST(actions.\"carteira\" AS TEXT) AS carteira_db,
                       CAST(actions.\"contrato\" AS TEXT) AS contrato,
                       {CONTRACT_KEY_SQL} AS contrato_key_db,
                       CAST(actions.\"nome\" AS TEXT) AS nome_cliente_db,
                       CAST(actions.\"acionamento\" AS TEXT) AS ultimo_acionamento,
                       CAST(actions.\"dt_acionamento\" AS DATE) AS data_ultimo_acionamento,
                       CAST(actions.\"hr_acionamento\" AS TEXT) AS hora_ultimo_acionamento,
                       CAST(actions.\"obs_acionamento\" AS TEXT) AS observacao_ultimo_acionamento,
                       CAST(actions.\"operador_acionamento\" AS TEXT) AS operador,
                       CASE
                           WHEN UPPER(TRIM(CAST(actions.\"acionamento\" AS TEXT))) = 'DISCADOR'
                           THEN 'discador' ELSE 'manual'
                       END AS action_scope,
                       ROW_NUMBER() OVER (
                           PARTITION BY {CONTRACT_KEY_SQL},
                               CASE
                                   WHEN UPPER(TRIM(CAST(actions.\"acionamento\" AS TEXT))) = 'DISCADOR'
                                   THEN 'discador' ELSE 'manual'
                               END
                           ORDER BY actions.\"dt_acionamento\" DESC NULLS LAST,
                                    actions.\"hr_acionamento\" DESC NULLS LAST
                       ) AS rn,
                       COUNT(*) OVER (
                           PARTITION BY {CONTRACT_KEY_SQL},
                               CASE
                                   WHEN UPPER(TRIM(CAST(actions.\"acionamento\" AS TEXT))) = 'DISCADOR'
                                   THEN 'discador' ELSE 'manual'
                               END
                       ) AS total_acionamentos
                FROM {self.table} actions
                INNER JOIN requested_contracts requested
                    ON requested.contrato_key = {CONTRACT_KEY_SQL}
                WHERE actions.\"contrato\" IS NOT NULL
                  AND (
                      UPPER(TRIM(CAST(actions.\"acionamento\" AS TEXT))) = 'DISCADOR'
                      OR UPPER(TRIM(CAST(actions.\"acionamento\" AS TEXT))) = ANY(CAST(:actions AS TEXT[]))
                  )
            )
            SELECT {", ".join(LAST_ACTION_COLUMNS)}, action_scope
            FROM source
            WHERE rn = 1
            ORDER BY data_ultimo_acionamento DESC NULLS LAST
        """)
        combined = pd.read_sql_query(
            query,
            self.engine,
            params={"contracts": list(keys), "actions": list(ALLOWED_ACTIONS)},
        )
        if combined.empty:
            empty = pd.DataFrame(columns=LAST_ACTION_COLUMNS)
            return empty.copy(), empty.copy()

        manual = combined[combined["action_scope"].eq("manual")][LAST_ACTION_COLUMNS].reset_index(drop=True)
        dialer = combined[combined["action_scope"].eq("discador")][LAST_ACTION_COLUMNS].reset_index(drop=True)
        return manual, dialer

    def timeline(self) -> pd.DataFrame:
        return pd.read_sql_query(text(f"""
            SELECT CAST(DATE_TRUNC('month', \"dt_acionamento\") AS DATE) AS periodo,
                   COUNT(*) AS quantidade
            FROM {self.table} WHERE \"dt_acionamento\" IS NOT NULL
            GROUP BY 1 ORDER BY 1
        """), self.engine)

    def operator_activity(self) -> pd.DataFrame:
        return pd.read_sql_query(text(f"""
            SELECT COALESCE(NULLIF(TRIM(CAST(\"operador_acionamento\" AS TEXT)), ''), 'Sem operador') AS operador,
                   COUNT(*) AS quantidade
            FROM {self.table} GROUP BY 1 ORDER BY quantidade DESC LIMIT 50
        """), self.engine)
