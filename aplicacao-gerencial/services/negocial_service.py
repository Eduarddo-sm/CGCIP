from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from services.carteira_schema_service import CarteiraSchemaService
from services.negocial_parecer_mixin import NegocialParecerMixin
from services.negocial_production_mixin import NegocialProductionMixin
from services.negocial_reporting_mixin import NegocialReportingMixin
from services.negocial_schema_mixin import NegocialSchemaMixin
from services.negocial_user_mixin import NegocialUserMixin
from services.report_export_service import ReportExportService


class NegocialService(
    NegocialSchemaMixin,
    NegocialUserMixin,
    NegocialParecerMixin,
    NegocialReportingMixin,
    NegocialProductionMixin,
):
    PRODUCAO_SHEET = "Producao Diaria"
    PRODUCAO_FILE_LABEL = "Sistema Negocial"
    PASSWORD_ROUNDS = 29000
    DEFAULT_ENABLED_TOOLS = ["producao", "pareceres"]
    ALLOWED_TOOLS = {"producao", "pareceres"}
    COLUMN_TYPES = {"texto", "numero", "moeda", "data", "select", "multiselect", "boolean"}
    MONTH_CLOSE_BREAK_JUSTIFICATIVA = "Fechamento mensal: quebra automatica"

    STATUS_LABELS = {
        "PROPOSTA": "Proposta",
        "AGUARDANDO_PAGAMENTO": "Aguardando pagamento",
        "PAGAMENTO_REALIZADO": "Pagamento realizado",
        "AGUARDANDO_LEVANTAMENTO": "Aguardando levantamento",
        "PROPOSTA_NEGADA": "Proposta negada",
        "OPERACAO_RECOMPRADA": "Operação recomprada",
        "QUEBRA": "Quebra",
    }
    TIPO_LABELS = {
        "A_VISTA": "A vista",
        "PARCELADO": "Parcelado",
    }

    HEADERS = [
        "NPJ",
        "CLIENTE",
        "GECOR",
        "UF",
        "DT AJUIZAMENTO",
        "DIAS DE ATRASO",
        "VALOR DO ACORDO",
        "VALOR DA ENTRADA",
        "PARCELADO OU À VISTA",
        "DATA ACORDO",
        "DATA DE VENCIMENTO",
        "DATA DO PAGAMENTO",
        "STATUS",
        "JUSTIFICATIVA",
        "NEGOCIADOR",
        "HONORÁRIOS",
        "HONORÁRIOS RECEBIDOS",
        "%",
        "AUTORIZADO?",
    ]

    ALPHA_HEADERS = [
        "DATA",
        "DEBIT ID",
        "CPF/CNPJ",
        "CLIENTE",
        "DATA DO 1\u00ba ATRASO",
        "PORTFOLIO",
        "CARTEIRA",
        "VALOR TOTAL",
        "ENTRADA",
        "TIPO",
        "VENCIMENTO",
        "PAGAMENTO",
        "STATUS",
        "JUSTIFICATIVA",
        "CARTEIRA SISTEMA",
        "USUARIO",
    ]

    BETA_HEADERS = [
        "DATA",
        "SUITID",
        "CLIENTE",
        "VALOR TOTAL DE ACORDO",
        "VALOR DA ENTRADA",
        "DATA DO VENCIMENTO",
        "DATA DO PAGAMENTO",
        "STATUS",
        "OPERADOR",
    ]

    PARECER_HEADERS = [
        "PK",
        "DATA",
        "NPJ",
        "NOME CLIENTE",
        "MOTIVO",
        "DESCRICAO",
        "OPERADOR",
        "CARTEIRA",
        "STATUS",
        "SOLICITADO?",
    ]

    DEFAULT_NEGOCIAL_COLUMNS = [
        {"nome": "DATA", "tipo": "data", "obrigatoria": True, "identificador": False},
        {"nome": "IDENTIFICADOR", "tipo": "texto", "obrigatoria": True, "identificador": True},
        {"nome": "CLIENTE", "tipo": "texto", "obrigatoria": True, "identificador": False},
        {"nome": "VALOR DO ACORDO", "tipo": "moeda", "obrigatoria": True, "identificador": False},
        {"nome": "VALOR DA ENTRADA", "tipo": "moeda", "obrigatoria": False, "identificador": False},
        {"nome": "DATA DE VENCIMENTO", "tipo": "data", "obrigatoria": True, "identificador": False},
        {
            "nome": "STATUS",
            "tipo": "select",
            "obrigatoria": True,
            "identificador": False,
            "opcoes": ["PROPOSTA", "AGUARDANDO_PAGAMENTO", "PAGAMENTO_REALIZADO", "PROPOSTA_NEGADA", "OPERACAO_RECOMPRADA", "QUEBRA"],
        },
        {"nome": "JUSTIFICATIVA", "tipo": "texto", "obrigatoria": False, "identificador": False, "visivel": False},
        {"nome": "NEGOCIADOR", "tipo": "texto", "obrigatoria": True, "identificador": False},
    ]

    def __init__(self, app_root: Path, database_url: str | None = None) -> None:
        self.database_url = (database_url or os.environ.get("DATABASE_URL", "")).strip()
        self.database_backend = self._detect_database_backend(self.database_url)
        env_path = os.environ.get("NEGOCIAL_DB_PATH", "").strip()
        self.db_path = Path(env_path) if env_path else app_root.parent / "aplicacao-negocial" / "database" / "negocial.sqlite3"
        self.schema_service = CarteiraSchemaService(self.STATUS_LABELS)
        self.report_export = ReportExportService()
        self._ensure_gerencial_schema()

    def _ensure_gerencial_schema(self) -> None:
        if self.database_backend != "postgresql":
            return
        with self._connect_postgres() as conn:
            # Estrutura e constraints pertencem ao Alembic. Aqui permanecem
            # apenas dados de referencia idempotentes das carteiras padrao.
            self._seed_default_carteiras_postgres(conn)

    def connect(self) -> sqlite3.Connection:
        self._ensure_database()
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def hash_password(self, password: str) -> str:
        password = self._clean_required(password, "Senha")
        salt = secrets.token_bytes(16)
        checksum = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            self.PASSWORD_ROUNDS,
            dklen=32,
        )
        return f"$pbkdf2-sha256${self.PASSWORD_ROUNDS}${self._b64(salt)}${self._b64(checksum)}"

    def _seed_default_carteiras_postgres(self, conn) -> None:
        for nome in ("GAMMA", "ALPHA", "BETA"):
            slug = self._slug(nome)
            current = conn.execute("SELECT id FROM carteiras_negociais WHERE slug = %s", (slug,)).fetchone()
            if current:
                continue
            now = self._now()
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
                    "Carteira padrao do sistema",
                    slug in {"GAMMA", "BETA"},
                    Decimal("10") if slug in {"GAMMA", "BETA"} else None,
                    Decimal("10") if slug in {"GAMMA", "BETA"} else None,
                    Decimal("10") if slug in {"GAMMA", "BETA"} else None,
                    slug in {"GAMMA", "BETA"},
                    slug == "GAMMA",
                    now,
                    now,
                ),
            ).fetchone()
            carteira_id = int(created["id"])
            for index, column in enumerate(self._default_columns_for_carteira(nome), start=1):
                conn.execute(
                    """
                    INSERT INTO carteira_colunas (
                        carteira_id, nome, chave, tipo, obrigatoria, identificador, visivel, ordem,
                        automatico, auto_tipo, max_length, mostrar_cadastro, cadastro_etapa, opcoes_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        carteira_id,
                        column["nome"],
                        column["chave"],
                        column["tipo"],
                        bool(column["obrigatoria"]),
                        bool(column["identificador"]),
                        index,
                        bool(column.get("automatico")),
                        column.get("auto_tipo") or None,
                        column.get("max_length"),
                        bool(column.get("mostrar_cadastro", True)),
                        int(column.get("cadastro_etapa") or 2),
                        json.dumps(column.get("opcoes") or [], ensure_ascii=False),
                    ),
                )

    def _repair_carteira_column_keys_postgres(self, conn) -> None:
        rows = conn.execute(
            "SELECT id, carteira_id, nome FROM carteira_colunas WHERE COALESCE(chave, '') = ''"
        ).fetchall()
        for row in rows:
            column_id = int(row["id"])
            carteira_id = int(row["carteira_id"])
            base_key = self._slug(row["nome"])
            if base_key == "CAMPO":
                base_key = f"COLUNA_{column_id}"
            candidate = base_key
            suffix = 2
            while conn.execute(
                "SELECT 1 FROM carteira_colunas WHERE carteira_id = %s AND chave = %s AND id <> %s LIMIT 1",
                (carteira_id, candidate, column_id),
            ).fetchone():
                candidate = f"{base_key}_{suffix}"
                suffix += 1
            conn.execute("UPDATE carteira_colunas SET chave = %s WHERE id = %s", (candidate, column_id))

    def _seed_default_carteiras_sqlite(self, conn: sqlite3.Connection) -> None:
        for nome in ("GAMMA", "ALPHA", "BETA"):
            slug = self._slug(nome)
            current = conn.execute("SELECT id FROM carteiras_negociais WHERE slug = ?", (slug,)).fetchone()
            if current:
                continue
            now = self._now()
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
                    "Carteira padrao do sistema",
                    int(slug in {"GAMMA", "BETA"}),
                    Decimal("10") if slug in {"GAMMA", "BETA"} else None,
                    Decimal("10") if slug in {"GAMMA", "BETA"} else None,
                    Decimal("10") if slug in {"GAMMA", "BETA"} else None,
                    int(slug in {"GAMMA", "BETA"}),
                    int(slug == "GAMMA"),
                    now,
                    now,
                ),
            )
            carteira_id = int(cursor.lastrowid)
            for index, column in enumerate(self._default_columns_for_carteira(nome), start=1):
                conn.execute(
                    """
                    INSERT INTO carteira_colunas (
                        carteira_id, nome, chave, tipo, obrigatoria, identificador, visivel, ordem,
                        automatico, auto_tipo, max_length, mostrar_cadastro, cadastro_etapa, opcoes_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        carteira_id,
                        column["nome"],
                        column["chave"],
                        column["tipo"],
                        int(bool(column["obrigatoria"])),
                        int(bool(column["identificador"])),
                        index,
                        int(bool(column.get("automatico"))),
                        column.get("auto_tipo") or None,
                        column.get("max_length"),
                        int(bool(column.get("mostrar_cadastro", True))),
                        int(column.get("cadastro_etapa") or 2),
                        json.dumps(column.get("opcoes") or [], ensure_ascii=False),
                    ),
                )

    def _default_columns_for_carteira(self, nome: str) -> list[dict[str, Any]]:
        carteira = self._slug(nome)
        if carteira == "GAMMA":
            headers = self.HEADERS
            identifier = "NPJ"
        elif carteira == "ALPHA":
            headers = self.ALPHA_HEADERS
            identifier = "DEBIT ID"
        elif carteira == "BETA":
            headers = self.BETA_HEADERS
            identifier = "SUITID"
        else:
            return self._normalize_carteira_columns(self.DEFAULT_NEGOCIAL_COLUMNS)
        columns = []
        for header in headers:
            upper = str(header or "").strip().upper()
            tipo = "texto"
            if "DATA" in upper or upper in {"VENCIMENTO", "PAGAMENTO"}:
                tipo = "data"
            elif any(token in upper for token in ("VALOR", "HONOR", "CASH", "%", "ENTRADA")):
                tipo = "numero" if "%" in upper else "moeda"
            elif upper == "STATUS":
                tipo = "select"
            columns.append({
                "nome": upper,
                "chave": self._slug(upper),
                "tipo": tipo,
                "obrigatoria": upper in {identifier, "CLIENTE", "STATUS", "NEGOCIADOR", "OPERADOR"},
                "identificador": upper == identifier,
                "visivel": True,
                "automatico": upper == "DATA",
                "auto_tipo": "today" if upper == "DATA" else "",
                "max_length": None,
                "mostrar_cadastro": upper not in {"NEGOCIADOR", "OPERADOR"},
                "cadastro_etapa": 1 if upper in {identifier, "DATA", "CLIENTE", "TIPO", "PARCELADO OU À VISTA", "PARCELADO OU A VISTA"} else 2,
                "opcoes": ["PROPOSTA", "AGUARDANDO_PAGAMENTO", "PAGAMENTO_REALIZADO", "PROPOSTA_NEGADA", "OPERACAO_RECOMPRADA", "QUEBRA"] if upper == "STATUS" else [],
            })
        return columns

    def _ensure_carteira_schema_sqlite(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS carteiras_negociais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT UNIQUE NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                descricao TEXT,
                active INTEGER DEFAULT 1 NOT NULL,
                usa_percentual_ho INTEGER DEFAULT 0 NOT NULL,
                percentual_ho_padrao NUMERIC,
                percentual_ho_minimo NUMERIC,
                percentual_ho_maximo NUMERIC,
                calculo_automatico_ho INTEGER DEFAULT 0 NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        wallet_columns = {row["name"] for row in conn.execute("PRAGMA table_info(carteiras_negociais)").fetchall()}
        if "usa_percentual_ho" not in wallet_columns:
            conn.execute("ALTER TABLE carteiras_negociais ADD COLUMN usa_percentual_ho INTEGER DEFAULT 0 NOT NULL")
        if "percentual_ho_padrao" not in wallet_columns:
            conn.execute("ALTER TABLE carteiras_negociais ADD COLUMN percentual_ho_padrao NUMERIC")
        if "percentual_ho_minimo" not in wallet_columns:
            conn.execute("ALTER TABLE carteiras_negociais ADD COLUMN percentual_ho_minimo NUMERIC")
        if "percentual_ho_maximo" not in wallet_columns:
            conn.execute("ALTER TABLE carteiras_negociais ADD COLUMN percentual_ho_maximo NUMERIC")
        if "calculo_automatico_ho" not in wallet_columns:
            conn.execute("ALTER TABLE carteiras_negociais ADD COLUMN calculo_automatico_ho INTEGER DEFAULT 0 NOT NULL")
        if "modo_schema" not in wallet_columns:
            conn.execute("ALTER TABLE carteiras_negociais ADD COLUMN modo_schema INTEGER DEFAULT 1 NOT NULL")
        conn.execute("UPDATE carteiras_negociais SET modo_schema = 1 WHERE modo_schema IS NULL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS carteira_colunas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                carteira_id INTEGER NOT NULL,
                nome TEXT NOT NULL,
                chave TEXT NOT NULL,
                tipo TEXT DEFAULT 'texto' NOT NULL,
                obrigatoria INTEGER DEFAULT 0 NOT NULL,
                identificador INTEGER DEFAULT 0 NOT NULL,
                visivel INTEGER DEFAULT 1 NOT NULL,
                ordem INTEGER DEFAULT 0 NOT NULL,
                automatico INTEGER DEFAULT 0 NOT NULL,
                auto_tipo TEXT,
                max_length INTEGER,
                mostrar_cadastro INTEGER DEFAULT 1 NOT NULL,
                cadastro_etapa INTEGER DEFAULT 2 NOT NULL,
                opcoes_json TEXT,
                UNIQUE (carteira_id, chave),
                FOREIGN KEY (carteira_id) REFERENCES carteiras_negociais(id) ON DELETE CASCADE
            )
            """
        )
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(carteira_colunas)").fetchall()}
        if "automatico" not in existing_columns:
            conn.execute("ALTER TABLE carteira_colunas ADD COLUMN automatico INTEGER DEFAULT 0 NOT NULL")
        if "auto_tipo" not in existing_columns:
            conn.execute("ALTER TABLE carteira_colunas ADD COLUMN auto_tipo TEXT")
        if "max_length" not in existing_columns:
            conn.execute("ALTER TABLE carteira_colunas ADD COLUMN max_length INTEGER")
        if "mostrar_cadastro" not in existing_columns:
            conn.execute("ALTER TABLE carteira_colunas ADD COLUMN mostrar_cadastro INTEGER DEFAULT 1 NOT NULL")
        if "cadastro_etapa" not in existing_columns:
            conn.execute("ALTER TABLE carteira_colunas ADD COLUMN cadastro_etapa INTEGER DEFAULT 2 NOT NULL")
        conn.execute(
            """
            UPDATE carteira_colunas
            SET automatico = 1, auto_tipo = 'today'
            WHERE chave = 'DATA' AND COALESCE(auto_tipo, '') = ''
            """
        )
        conn.execute(
            """
            UPDATE carteira_colunas
            SET cadastro_etapa = 1
            WHERE chave IN ('DATA', 'CLIENTE', 'TIPO', 'TIPO_DE_ACORDO', 'PARCELADO_OU_VISTA', 'PARCELADO_OU_A_VISTA')
               OR identificador = 1
            """
        )
        conn.execute(
            """
            UPDATE carteira_colunas
            SET mostrar_cadastro = 0
            WHERE chave IN ('NEGOCIADOR', 'OPERADOR', 'JUSTIFICATIVA')
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS producao_campos (
                producao_id INTEGER NOT NULL,
                coluna_id INTEGER NOT NULL,
                valor_texto TEXT,
                valor_numero NUMERIC,
                valor_data TEXT,
                valor_json TEXT,
                updated_at TEXT,
                PRIMARY KEY (producao_id, coluna_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS carteira_schema_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                carteira_id INTEGER NOT NULL,
                version_number INTEGER NOT NULL,
                action TEXT NOT NULL,
                schema_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (carteira_id, version_number),
                FOREIGN KEY (carteira_id) REFERENCES carteiras_negociais(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS carteira_regras_calculo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                carteira_id INTEGER NOT NULL,
                codigo TEXT NOT NULL DEFAULT 'HONORARIOS',
                nome TEXT NOT NULL DEFAULT 'Honorarios',
                tipo_calculo TEXT NOT NULL DEFAULT 'percentual',
                motor_calculo TEXT NOT NULL DEFAULT 'PERCENTUAL_FIXO',
                coluna_base_id INTEGER,
                coluna_destino_id INTEGER,
                coluna_base_vista_id INTEGER,
                coluna_base_parcelado_id INTEGER,
                coluna_valor_recebido_id INTEGER,
                coluna_percentual_efetivo_id INTEGER,
                percentual_padrao NUMERIC,
                percentual_minimo NUMERIC,
                percentual_maximo NUMERIC,
                automatico INTEGER NOT NULL DEFAULT 0,
                ativo INTEGER NOT NULL DEFAULT 1,
                casas_decimais INTEGER NOT NULL DEFAULT 2,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (carteira_id, codigo),
                FOREIGN KEY (carteira_id) REFERENCES carteiras_negociais(id) ON DELETE CASCADE,
                FOREIGN KEY (coluna_base_id) REFERENCES carteira_colunas(id) ON DELETE SET NULL,
                FOREIGN KEY (coluna_destino_id) REFERENCES carteira_colunas(id) ON DELETE SET NULL,
                FOREIGN KEY (coluna_base_vista_id) REFERENCES carteira_colunas(id) ON DELETE SET NULL,
                FOREIGN KEY (coluna_base_parcelado_id) REFERENCES carteira_colunas(id) ON DELETE SET NULL,
                FOREIGN KEY (coluna_valor_recebido_id) REFERENCES carteira_colunas(id) ON DELETE SET NULL,
                FOREIGN KEY (coluna_percentual_efetivo_id) REFERENCES carteira_colunas(id) ON DELETE SET NULL
            )
            """
        )
        rule_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(carteira_regras_calculo)").fetchall()
        }
        if "motor_calculo" not in rule_columns:
            conn.execute(
                "ALTER TABLE carteira_regras_calculo "
                "ADD COLUMN motor_calculo TEXT NOT NULL DEFAULT 'PERCENTUAL_FIXO'"
            )
        if "coluna_base_vista_id" not in rule_columns:
            conn.execute(
                "ALTER TABLE carteira_regras_calculo ADD COLUMN coluna_base_vista_id INTEGER"
            )
        if "coluna_base_parcelado_id" not in rule_columns:
            conn.execute(
                "ALTER TABLE carteira_regras_calculo ADD COLUMN coluna_base_parcelado_id INTEGER"
            )
        self._repair_carteira_column_keys_sqlite(conn)
        self._consolidate_duplicate_carteira_columns_sqlite(conn)

    def _normalize_carteira_columns(self, colunas: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        source = colunas or self.DEFAULT_NEGOCIAL_COLUMNS
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in source:
            nome = str(raw.get("nome") or "").strip().upper()
            if not nome:
                continue
            chave = self._slug(raw.get("chave") or nome)
            if not chave:
                continue
            tipo = str(raw.get("tipo") or "texto").strip().lower()
            if tipo not in self.COLUMN_TYPES:
                tipo = "texto"
            options = self._normalize_column_options(raw.get("opcoes") or raw.get("options") or [], chave)
            max_length_raw = raw.get("max_length")
            try:
                max_length = int(max_length_raw) if max_length_raw not in (None, "") else None
            except (TypeError, ValueError):
                max_length = None
            if max_length is not None and max_length <= 0:
                max_length = None
            automatico = bool(raw.get("automatico"))
            auto_tipo = str(raw.get("auto_tipo") or "").strip().lower()
            if not automatico:
                auto_tipo = ""
            elif auto_tipo not in {"today", "usuario", "carteira"}:
                auto_tipo = "today" if tipo == "data" else "usuario"
            mostrar_cadastro = raw.get("mostrar_cadastro") is not False
            try:
                cadastro_etapa = int(raw.get("cadastro_etapa") or 2)
            except (TypeError, ValueError):
                cadastro_etapa = 2
            if cadastro_etapa not in {1, 2}:
                cadastro_etapa = 2
            default_visible = chave != "JUSTIFICATIVA"
            column = {
                "nome": nome,
                "chave": chave,
                "tipo": tipo,
                "obrigatoria": bool(raw.get("obrigatoria")),
                "identificador": bool(raw.get("identificador")),
                "visivel": raw.get("visivel", default_visible) is not False,
                "automatico": automatico,
                "auto_tipo": auto_tipo,
                "max_length": max_length,
                "mostrar_cadastro": mostrar_cadastro,
                "cadastro_etapa": cadastro_etapa,
                "opcoes": options,
            }
            if chave in seen:
                existing = next((item for item in normalized if item["chave"] == chave), None)
                if existing:
                    self._merge_column_definition(existing, column)
                continue
            seen.add(chave)
            normalized.append(column)
        def ensure_standard(
            column: dict[str, Any],
            position: int | None = None,
            aliases: set[str] | None = None,
        ) -> None:
            accepted_keys = {column["chave"], *(aliases or set())}
            if any(item["chave"] in accepted_keys for item in normalized):
                return
            if position is None:
                normalized.append(column)
            else:
                normalized.insert(position, column)

        ensure_standard(
            {
                "nome": "DATA",
                "chave": "DATA",
                "tipo": "data",
                "obrigatoria": False,
                "identificador": False,
                "visivel": True,
                "automatico": True,
                "auto_tipo": "today",
                "max_length": None,
                "mostrar_cadastro": True,
                "cadastro_etapa": 1,
                "opcoes": [],
            },
            0,
            {"DATA_ACORDO"},
        )
        ensure_standard(
            {
                "nome": "CLIENTE",
                "chave": "CLIENTE",
                "tipo": "texto",
                "obrigatoria": True,
                "identificador": False,
                "visivel": True,
                "automatico": False,
                "auto_tipo": "",
                "max_length": None,
                "mostrar_cadastro": True,
                "cadastro_etapa": 1,
                "opcoes": [],
            },
            2 if len(normalized) > 1 else None,
            {"NOME", "NOME_CLIENTE"},
        )
        ensure_standard(
            {
                "nome": "TIPO DE ACORDO",
                "chave": "TIPO_DE_ACORDO",
                "tipo": "select",
                "obrigatoria": True,
                "identificador": False,
                "visivel": True,
                "automatico": False,
                "auto_tipo": "",
                "max_length": None,
                "mostrar_cadastro": True,
                "cadastro_etapa": 1,
                "opcoes": ["A VISTA", "PARCELADO"],
            },
            aliases={"TIPO", "PARCELADO_OU_VISTA", "PARCELADO_OU_A_VISTA"},
        )
        ensure_standard(
            {
                "nome": "STATUS",
                "chave": "STATUS",
                "tipo": "select",
                "obrigatoria": True,
                "identificador": False,
                "visivel": True,
                "automatico": False,
                "auto_tipo": "",
                "max_length": None,
                "mostrar_cadastro": True,
                "cadastro_etapa": 2,
                "opcoes": ["PROPOSTA", "AGUARDANDO_PAGAMENTO", "PAGAMENTO_REALIZADO", "PROPOSTA_NEGADA", "OPERACAO_RECOMPRADA", "QUEBRA"],
            },
        )
        ensure_standard(
            {
                "nome": "JUSTIFICATIVA",
                "chave": "JUSTIFICATIVA",
                "tipo": "texto",
                "obrigatoria": False,
                "identificador": False,
                "visivel": False,
                "automatico": False,
                "auto_tipo": "",
                "max_length": None,
                "mostrar_cadastro": False,
                "cadastro_etapa": 2,
                "opcoes": [],
            }
        )
        ensure_standard(
            {
                "nome": "NEGOCIADOR",
                "chave": "NEGOCIADOR",
                "tipo": "texto",
                "obrigatoria": True,
                "identificador": False,
                "visivel": True,
                "automatico": True,
                "auto_tipo": "usuario",
                "max_length": None,
                "mostrar_cadastro": False,
                "cadastro_etapa": 2,
                "opcoes": [],
            },
            aliases={"OPERADOR", "USUARIO"},
        )
        normalized = self._dedupe_carteira_columns(normalized)
        if not any(column["identificador"] for column in normalized):
            raise ValueError("Marque uma coluna como identificador da carteira.")
        return normalized

    def _normalize_ho_rules(self, regras_ho: dict[str, Any] | None, slug: str) -> dict[str, Any]:
        return self.schema_service.normalize_ho_rules(regras_ho, slug)

    def _group_carteiras(self, rows, columns, rules=()) -> list[dict[str, Any]]:
        grouped: dict[int, dict[str, Any]] = {}
        for row in rows:
            data = dict(row)
            item = {
                "id": int(data["id"]),
                "nome": data.get("nome") or "",
                "slug": data.get("slug") or "",
                "descricao": data.get("descricao") or "",
                "active": bool(data.get("active")),
                "modo_schema": bool(data.get("modo_schema")),
                "schema_version": int(data.get("schema_version") or 0),
                "regras_ho": {
                    "usa_percentual_ho": bool(data.get("usa_percentual_ho")),
                    "percentual_ho_padrao": float(data["percentual_ho_padrao"]) if data.get("percentual_ho_padrao") is not None else None,
                    "percentual_ho_minimo": float(data["percentual_ho_minimo"]) if data.get("percentual_ho_minimo") is not None else None,
                    "percentual_ho_maximo": float(data["percentual_ho_maximo"]) if data.get("percentual_ho_maximo") is not None else None,
                    "calculo_automatico_ho": bool(data.get("calculo_automatico_ho")),
                },
                "created_at": str(data.get("created_at") or ""),
                "updated_at": str(data.get("updated_at") or ""),
                "colunas": [],
            }
            grouped[item["id"]] = item
        for row in rules:
            data = dict(row)
            carteira_id = int(data["carteira_id"])
            if carteira_id not in grouped:
                continue
            grouped[carteira_id]["regras_ho"].update({
                "usa_percentual_ho": bool(data.get("ativo")),
                "percentual_ho_padrao": float(data["percentual_padrao"]) if data.get("percentual_padrao") is not None else None,
                "percentual_ho_minimo": float(data["percentual_minimo"]) if data.get("percentual_minimo") is not None else None,
                "percentual_ho_maximo": float(data["percentual_maximo"]) if data.get("percentual_maximo") is not None else None,
                "calculo_automatico_ho": bool(data.get("automatico")),
                "motor_calculo": data.get("motor_calculo") or "PERCENTUAL_FIXO",
                "coluna_base": data.get("coluna_base") or None,
                "coluna_base_vista": data.get("coluna_base_vista") or None,
                "coluna_base_parcelado": data.get("coluna_base_parcelado") or None,
                "coluna_destino": data.get("coluna_destino") or None,
                "coluna_valor_recebido": data.get("coluna_valor_recebido") or None,
                "coluna_percentual_efetivo": data.get("coluna_percentual_efetivo") or None,
                "casas_decimais": int(data.get("casas_decimais") or 2),
            })
        for row in columns:
            data = dict(row)
            carteira_id = int(data["carteira_id"])
            if carteira_id not in grouped:
                continue
            try:
                options = json.loads(data.get("opcoes_json") or "[]")
            except (TypeError, json.JSONDecodeError):
                options = []
            chave = data.get("chave") or ""
            grouped[carteira_id]["colunas"].append({
                "id": int(data["id"]),
                "nome": data.get("nome") or "",
                "chave": chave,
                "tipo": data.get("tipo") or "texto",
                "obrigatoria": bool(data.get("obrigatoria")),
                "identificador": bool(data.get("identificador")),
                "visivel": bool(data.get("visivel")),
                "ordem": int(data.get("ordem") or 0),
                "automatico": bool(data.get("automatico")),
                "auto_tipo": data.get("auto_tipo") or "",
                "max_length": int(data["max_length"]) if data.get("max_length") not in (None, "") else None,
                "mostrar_cadastro": bool(data.get("mostrar_cadastro")),
                "cadastro_etapa": int(data.get("cadastro_etapa") or 2),
                "opcoes": self._normalize_column_options(options, chave),
            })
        return list(grouped.values())

    def _slug(self, value: Any) -> str:
        text = str(value or "").strip().upper()
        if text in {"%", "PERCENTUAL"}:
            return "PERCENTUAL"
        text = re.sub(r"[^A-Z0-9]+", "_", text)
        return text.strip("_") or "CAMPO"

    def _repair_carteira_column_keys_sqlite(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            "SELECT id, carteira_id, nome FROM carteira_colunas WHERE COALESCE(chave, '') = ''"
        ).fetchall()
        for row in rows:
            column_id = int(row["id"])
            carteira_id = int(row["carteira_id"])
            base_key = self._slug(row["nome"])
            if base_key == "CAMPO":
                base_key = f"COLUNA_{column_id}"
            candidate = base_key
            suffix = 2
            while conn.execute(
                "SELECT 1 FROM carteira_colunas WHERE carteira_id = ? AND chave = ? AND id <> ? LIMIT 1",
                (carteira_id, candidate, column_id),
            ).fetchone():
                candidate = f"{base_key}_{suffix}"
                suffix += 1
            conn.execute("UPDATE carteira_colunas SET chave = ? WHERE id = ?", (candidate, column_id))

    def _ensure_database(self) -> None:
        if not self.db_path.exists():
            raise ValueError(f"Banco da aplicacao negocial nao encontrado: {self.db_path}")

    def _ensure_expected_schema(self, conn: sqlite3.Connection) -> None:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')").fetchall()}
        missing = {"users", "producao_unificada"} - tables
        if missing:
            raise ValueError(f"Banco negocial incompleto. Tabelas ausentes: {', '.join(sorted(missing))}")
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "enabled_tools" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN enabled_tools TEXT DEFAULT 'producao,pareceres' NOT NULL")
        conn.execute("UPDATE users SET enabled_tools = 'producao,pareceres' WHERE COALESCE(enabled_tools, '') = ''")
        self._ensure_carteira_schema_sqlite(conn)
        self._ensure_monthly_closing_schema_sqlite(conn)
        self._seed_default_carteiras_sqlite(conn)

    def _ensure_parecer_schema(self, conn: sqlite3.Connection) -> None:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        if "pareceres" not in tables:
            raise ValueError("Banco negocial ainda nao possui a tabela pareceres.")
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(pareceres)").fetchall()}
        if "approval_status" not in columns:
            conn.execute("ALTER TABLE pareceres ADD COLUMN approval_status TEXT DEFAULT 'PENDENTE' NOT NULL")
        if "approval_reason" not in columns:
            conn.execute("ALTER TABLE pareceres ADD COLUMN approval_reason TEXT")
        if "requested_at" not in columns:
            conn.execute("ALTER TABLE pareceres ADD COLUMN requested_at TEXT")
        if "approval_decided_at" not in columns:
            conn.execute("ALTER TABLE pareceres ADD COLUMN approval_decided_at TEXT")
        conn.execute("UPDATE pareceres SET approval_status = 'APROVADO' WHERE status = 'SOLICITADO' AND COALESCE(approval_status, '') = ''")
        conn.execute("UPDATE pareceres SET approval_status = 'REPROVADO' WHERE status = 'CANCELADO' AND COALESCE(approval_status, '') = ''")
        conn.execute("UPDATE pareceres SET approval_status = 'PENDENTE' WHERE COALESCE(approval_status, '') = ''")
        conn.execute("UPDATE pareceres SET requested_at = updated_at WHERE status = 'SOLICITADO' AND COALESCE(requested_at, '') = ''")
        conn.execute("UPDATE pareceres SET approval_decided_at = updated_at WHERE approval_status IN ('APROVADO', 'REPROVADO') AND COALESCE(approval_decided_at, '') = ''")

    def _map_producao_row(self, row: sqlite3.Row, index: int) -> dict[str, Any]:
        status = str(self._row_get(row, "status") or "")
        tipo = str(self._row_get(row, "tipo_acordo") or "")
        carteira_sistema = self._row_get(row, "carteira") or ""
        carteira_caso = self._row_get(row, "carteira_alpha") or ""
        valor_acordo = self._money(self._row_get(row, "valor_total_acordo"))
        valor_entrada = self._money(self._row_get(row, "valor_entrada"))
        honorarios_recebidos = self._money(self._row_get(row, "valor_ho"))
        honorarios_cheios = round(float(valor_acordo) * 0.10, 2)
        percentual_recebido = self._percent_value(honorarios_recebidos, valor_acordo)
        data_ajuizamento = self._date_value(
            self._row_get(row, "gerencial_data_ajuizamento")
            or self._row_get(row, "data_primeiro_atraso")
        )
        return {
            "_row_id": int(self._row_get(row, "id") or 0),
            "_excel_row": index,
            "competencia": self._date_value(self._row_get(row, "competencia"))[:7],
            "DATA": self._date_value(self._row_get(row, "data_acordo")),
            "DATA ACORDO": self._date_value(self._row_get(row, "data_acordo")),
            "NPJ": self._row_get(row, "npj"),
            "DEBIT ID": self._row_get(row, "npj"),
            "SUITID": self._row_get(row, "npj"),
            "CPF": self._row_get(row, "cpf"),
            "CPF/CNPJ": self._row_get(row, "cpf"),
            "CLIENTE": self._row_get(row, "cliente"),
            "GECOR": self._row_get(row, "gecor"),
            "UF": self._row_get(row, "gerencial_uf") or "",
            "DT AJUIZAMENTO": data_ajuizamento,
            "DIAS DE ATRASO": self._dias_de_atraso(
                data_ajuizamento,
                status,
                self._row_get(row, "data_pagamento"),
            ),
            "DATA DO 1\u00ba ATRASO": self._date_value(self._row_get(row, "data_primeiro_atraso")),
            "PORTFOLIO": self._row_get(row, "portfolio") or "",
            "CARTEIRA": carteira_caso if self._is_alpha(carteira_sistema) else carteira_sistema,
            "VALOR TOTAL": valor_acordo,
            "VALOR DO ACORDO": valor_acordo,
            "VALOR TOTAL DE ACORDO": valor_acordo,
            "ENTRADA": valor_entrada,
            "VALOR DA ENTRADA": valor_entrada,
            "HONORARIOS": honorarios_recebidos,
            "HONORÁRIOS": honorarios_cheios,
            "HONORÁRIOS RECEBIDOS": honorarios_recebidos,
            "% H.O": percentual_recebido,
            "%": percentual_recebido,
            "TIPO": self.TIPO_LABELS.get(tipo, tipo),
            "PARCELADO OU À VISTA": self.TIPO_LABELS.get(tipo, tipo),
            "VENCIMENTO": self._date_value(self._row_get(row, "data_vencimento")),
            "DATA DE VENCIMENTO": self._date_value(self._row_get(row, "data_vencimento")),
            "DATA DO VENCIMENTO": self._date_value(self._row_get(row, "data_vencimento")),
            "PAGAMENTO": self._date_value(self._row_get(row, "data_pagamento")),
            "DATA DO PAGAMENTO": self._date_value(self._row_get(row, "data_pagamento")),
            "STATUS": self.STATUS_LABELS.get(status, status),
            "JUSTIFICATIVA": self._row_get(row, "justificativa_status") or "",
            "AUTORIZACAO": self._row_get(row, "autorizacao_flexibilizacao") or "",
            "AUTORIZADO?": self._row_get(row, "autorizacao_flexibilizacao") or "",
            "CARTEIRA SISTEMA": carteira_sistema,
            "USUARIO": self._row_get(row, "usuario") or "",
            "NEGOCIADOR": self._row_get(row, "usuario") or "",
            "OPERADOR": self._row_get(row, "usuario") or "",
        }

    def _map_parecer_row(self, row: sqlite3.Row, index: int) -> dict[str, Any]:
        status = str(row["status"] or "").upper()
        approval_status = str(self._row_get(row, "approval_status") or "PENDENTE").upper()
        return {
            "__source": "sistema",
            "__parecer_id": int(row["id"]),
            "__row_number": index,
            "__created_at": str(self._row_get(row, "created_at") or ""),
            "__updated_at": str(self._row_get(row, "updated_at") or ""),
            "PK": self.parecer_pk(int(row["id"])),
            "DATA": self._date_value(row["data_solicitacao"]),
            "NPJ": row["npj"] or "",
            "NOME CLIENTE": row["cliente"] or "",
            "MOTIVO": row["motivo"] or "",
            "DESCRICAO": row["descricao"] or "",
            "OPERADOR": row["operador"] or "",
            "CARTEIRA": row["carteira"] or "",
            "STATUS": status,
            "APROVACAO": approval_status,
            "DATA SOLICITADO": self._datetime_value(self._row_get(row, "requested_at")),
            "DATA APROVADO/REPROVADO": self._datetime_value(self._row_get(row, "approval_decided_at")),
            "JUSTIFICATIVA APROVACAO/REPROVACAO": self._row_get(row, "approval_reason") or "",
            "SOLICITADO?": "NAO" if status == "PENDENTE" else "SIM",
        }

    def _infer_types(self, rows: list[dict[str, Any]], headers: list[str] | None = None) -> dict[str, str]:
        types: dict[str, str] = {}
        for header in headers or self.HEADERS:
            values = [row.get(header) for row in rows if row.get(header) not in (None, "")]
            if not values:
                types[header] = "text"
            elif header in {"VALOR TOTAL", "VALOR TOTAL DE ACORDO", "VALOR DO ACORDO", "ENTRADA", "VALOR DA ENTRADA", "HONORARIOS", "HONORÁRIOS", "HONORÁRIOS RECEBIDOS", "% H.O", "%"}:
                types[header] = "number"
            elif header in {"DATA", "DATA ACORDO", "DATA DO 1\u00ba ATRASO", "VENCIMENTO", "DATA DE VENCIMENTO", "DATA DO VENCIMENTO", "PAGAMENTO", "DATA DO PAGAMENTO"}:
                types[header] = "date"
            else:
                types[header] = "text"
        return types

    def _headers_for_carteira(self, carteira: str) -> list[str]:
        carteira_key = str(carteira or "").strip().upper()
        if carteira_key == "ALPHA":
            return self.ALPHA_HEADERS
        if carteira_key == "BETA":
            return self.BETA_HEADERS
        return self.HEADERS

    def _is_alpha(self, carteira: str) -> bool:
        return str(carteira or "").strip().upper() == "ALPHA"

    def _row_get(self, row: Any, key: str, default: Any = "") -> Any:
        if isinstance(row, dict):
            return row.get(key, default)
        try:
            if key in row.keys():
                return row[key]
        except Exception:
            pass
        return default

    def _date_value(self, value: Any) -> str:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return str(value or "")

    def _date_from_db_value(self, value: Any) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text[:10]).date()
        except ValueError:
            return None

    def _datetime_value(self, value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat(sep=" ", timespec="seconds")
        if isinstance(value, date):
            return value.isoformat()
        return str(value or "")

    def _money(self, value: Any) -> float:
        text = str(value or "0").strip()
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        return float(Decimal(text).quantize(Decimal("0.01")))

    def _decimal(self, value: Any) -> float:
        return float(Decimal(str(value or "0")).quantize(Decimal("0.01")))

    def _number(self, value: Any) -> float:
        try:
            return float(Decimal(str(value or "0")))
        except Exception:
            return 0.0

    def _percent_value(self, numerator: Any, denominator: Any) -> float:
        base = self._number(denominator)
        if base <= 0:
            return 0.0
        return round((self._number(numerator) / base) * 100, 2)

    def _dias_de_atraso(
        self,
        value: Any,
        status: Any = "",
        data_pagamento: Any = None,
    ) -> int | str:
        from services.alpha_ho_rules import dias_de_atraso

        text = str(value or "").strip()
        if not text:
            return ""
        try:
            parsed = datetime.fromisoformat(text[:10]).date()
            payment_text = str(data_pagamento or "").strip()
            payment_date = (
                datetime.fromisoformat(payment_text[:10]).date()
                if payment_text
                else None
            )
            result = dias_de_atraso(parsed, status, payment_date)
            return result if result is not None else ""
        except ValueError:
            return ""

    def _csv_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, tuple, set)):
            return "; ".join(str(item) for item in value if str(item).strip())
        if isinstance(value, float):
            return f"{value:.2f}".replace(".", ",")
        return str(value)

    def _day_from_value(self, value: Any) -> str:
        text = str(value or "")
        if not text:
            return ""
        try:
            parsed = datetime.fromisoformat(text[:10])
            return f"{parsed.day:02d}"
        except ValueError:
            parts = text.split("/")
            if parts and parts[0].isdigit():
                return parts[0].zfill(2)
        return ""

    def _normalize_report_status(self, value: Any) -> str:
        text = str(value or "").strip().upper()
        if not text:
            return ""
        reverse = {label.upper(): key for key, label in self.STATUS_LABELS.items()}
        return reverse.get(text, text.replace(" ", "_"))

    def _filename_slug(self, value: Any) -> str:
        text = str(value or "relatorio").strip().lower()
        cleaned = []
        for char in text:
            if char.isalnum():
                cleaned.append(char)
            elif char in {" ", "-", "_", "."}:
                cleaned.append("_")
        slug = "".join(cleaned).strip("_")
        return slug or "relatorio"

    def _detect_database_backend(self, database_url: str) -> str:
        scheme = urlparse(database_url).scheme
        if scheme.startswith("postgres"):
            return "postgresql"
        return "sqlite"

    def _psycopg_url(self) -> str:
        return self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    def _connect_postgres(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("Para usar usuarios negociais no PostgreSQL, instale psycopg[binary].") from exc
        conn = psycopg.connect(self._psycopg_url(), row_factory=dict_row)
        conn.execute("SET search_path TO negocial, public")
        return conn

    def _postgres_columns(self, conn, table_name: str) -> set[str]:
        rows = conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = %s
            """,
            (table_name,),
        ).fetchall()
        return {str(row["column_name"]) for row in rows}

    def _month_name(self, mes: int) -> str:
        months = [
            "Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
        ]
        return months[int(mes) - 1]

    def _monthly_summary(self, rows: list[dict[str, Any]], status_counts: dict[str, int]) -> str:
        if not rows:
            return "Nenhuma atualizacao encontrada para o periodo selecionado."
        main_status = sorted(status_counts.items(), key=lambda item: item[1], reverse=True)[0][0]
        total_users = len({self._row_user_label(row) for row in rows})
        return f"{len(rows)} casos atualizados por {total_users} negociador(es). Status mais frequente: {main_status}."

    def _public_negocial_user(self, row: dict[str, Any]) -> dict[str, Any]:
        row["online"] = int(row.get("online_sessions") or 0) > 0
        row["meta_pagamento"] = self._money(row.get("meta_pagamento"))
        row["enabled_tools"] = self._parse_tools(row.get("enabled_tools"))
        return row

    def _tools_text(self, value: Any) -> str:
        return ",".join(self._parse_tools(value))

    def _parse_tools(self, value: Any) -> list[str]:
        if value in (None, ""):
            return list(self.DEFAULT_ENABLED_TOOLS)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return list(self.DEFAULT_ENABLED_TOOLS)
            try:
                decoded = json.loads(text)
                if isinstance(decoded, list):
                    raw_items = decoded
                else:
                    raw_items = text.split(",")
            except json.JSONDecodeError:
                raw_items = text.split(",")
        elif isinstance(value, (list, tuple, set)):
            raw_items = list(value)
        else:
            raw_items = []
        normalized = []
        for item in raw_items:
            tool = str(item or "").strip().lower()
            if tool in self.ALLOWED_TOOLS and tool not in normalized:
                normalized.append(tool)
        return normalized or list(self.DEFAULT_ENABLED_TOOLS)

    def _clean_required(self, value: str, field: str) -> str:
        text = " ".join(str(value or "").strip().split())
        if not text:
            raise ValueError(f"{field} obrigatorio.")
        return text

    def _now(self) -> str:
        return datetime.utcnow().isoformat(sep=" ", timespec="microseconds")

    def _b64(self, value: bytes) -> str:
        return base64.b64encode(value).decode("ascii").rstrip("=")
