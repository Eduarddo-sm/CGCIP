import json

from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.auth.security import hash_password
from backend.config import settings
from backend.database import Base, DB_SCHEMA, IS_POSTGRES, IS_SQLITE, engine
from backend.models import User


SCHEMA_STATUS_OPTIONS = [
    "PROPOSTA",
    "AGUARDANDO_PAGAMENTO",
    "PAGAMENTO_REALIZADO",
    "PROPOSTA_NEGADA",
    "OPERACAO_RECOMPRADA",
    "QUEBRA",
]

ALPHA_SCHEMA_COLUMNS = [
    {"chave": "DATA", "nome": "DATA", "tipo": "data", "automatico": True, "auto_tipo": "today", "mostrar_cadastro": False},
    {"chave": "DEBIT_ID", "nome": "DEBIT ID", "tipo": "texto", "obrigatoria": True, "identificador": True, "max_length": 8, "cadastro_etapa": 1},
    {"chave": "CPF_CNPJ", "nome": "CPF/CNPJ", "tipo": "texto", "obrigatoria": True, "max_length": 14, "cadastro_etapa": 1},
    {"chave": "CLIENTE", "nome": "CLIENTE", "tipo": "texto", "obrigatoria": True, "max_length": 180, "cadastro_etapa": 1},
    {"chave": "DATA_DO_1_ATRASO", "nome": "DATA DO 1o ATRASO", "tipo": "data", "obrigatoria": True, "cadastro_etapa": 1},
    {"chave": "PORTFOLIO", "nome": "PORTFOLIO", "tipo": "texto", "max_length": 120, "cadastro_etapa": 1},
    {"chave": "CARTEIRA", "nome": "CARTEIRA", "tipo": "select", "obrigatoria": True, "opcoes": ["AUTOS", "SME"], "cadastro_etapa": 1},
    {"chave": "VALOR_TOTAL", "nome": "VALOR TOTAL", "tipo": "moeda", "obrigatoria": True, "cadastro_etapa": 2},
    {"chave": "ENTRADA", "nome": "ENTRADA", "tipo": "moeda", "obrigatoria": True, "cadastro_etapa": 2},
    {"chave": "TIPO_DE_ACORDO", "nome": "PARCELADO OU A VISTA", "tipo": "select", "obrigatoria": True, "opcoes": ["A_VISTA", "PARCELADO"], "cadastro_etapa": 1},
    {"chave": "VENCIMENTO", "nome": "VENCIMENTO", "tipo": "data", "obrigatoria": True, "cadastro_etapa": 2},
    {"chave": "DATA_DO_PAGAMENTO", "nome": "DATA DO PAGAMENTO", "tipo": "data", "mostrar_cadastro": False, "cadastro_etapa": 2},
    {"chave": "STATUS", "nome": "STATUS", "tipo": "select", "obrigatoria": True, "opcoes": SCHEMA_STATUS_OPTIONS, "cadastro_etapa": 2},
    {"chave": "JUSTIFICATIVA", "nome": "JUSTIFICATIVA", "tipo": "texto", "visivel": False, "mostrar_cadastro": False, "max_length": 600, "cadastro_etapa": 2},
    {"chave": "NEGOCIADOR", "nome": "NEGOCIADOR", "tipo": "texto", "visivel": False, "automatico": True, "auto_tipo": "usuario", "mostrar_cadastro": False, "max_length": 80, "cadastro_etapa": 2},
]

BETA_SCHEMA_COLUMNS = [
    {"chave": "DATA", "nome": "DATA", "tipo": "data", "automatico": True, "auto_tipo": "today", "mostrar_cadastro": False},
    {"chave": "SUITID", "nome": "SUITID", "tipo": "texto", "obrigatoria": True, "identificador": True, "max_length": 80, "cadastro_etapa": 1},
    {"chave": "CLIENTE", "nome": "CLIENTE", "tipo": "texto", "obrigatoria": True, "max_length": 180, "cadastro_etapa": 1},
    {"chave": "VALOR_TOTAL_DE_ACORDO", "nome": "VALOR TOTAL DE ACORDO", "tipo": "moeda", "obrigatoria": True, "cadastro_etapa": 2},
    {"chave": "VALOR_DA_ENTRADA", "nome": "VALOR DA ENTRADA", "tipo": "moeda", "obrigatoria": True, "cadastro_etapa": 2},
    {"chave": "TIPO_DE_ACORDO", "nome": "PARCELADO OU A VISTA", "tipo": "select", "obrigatoria": True, "opcoes": ["A_VISTA", "PARCELADO"], "cadastro_etapa": 1},
    {"chave": "DATA_DO_VENCIMENTO", "nome": "DATA DO VENCIMENTO", "tipo": "data", "obrigatoria": True, "cadastro_etapa": 2},
    {"chave": "DATA_DO_PAGAMENTO", "nome": "DATA DO PAGAMENTO", "tipo": "data", "mostrar_cadastro": False, "cadastro_etapa": 2},
    {"chave": "STATUS", "nome": "STATUS", "tipo": "select", "obrigatoria": True, "opcoes": SCHEMA_STATUS_OPTIONS, "cadastro_etapa": 2},
    {"chave": "JUSTIFICATIVA", "nome": "JUSTIFICATIVA", "tipo": "texto", "visivel": False, "mostrar_cadastro": False, "max_length": 600, "cadastro_etapa": 2},
    {"chave": "NEGOCIADOR", "nome": "NEGOCIADOR", "tipo": "texto", "visivel": False, "automatico": True, "auto_tipo": "usuario", "mostrar_cadastro": False, "max_length": 80, "cadastro_etapa": 2},
]


def create_database():
    # PostgreSQL e administrado exclusivamente pelo Alembic antes deste ponto.
    # O caminho abaixo existe apenas para manter o fallback SQLite de testes e
    # desenvolvimento local compativel com bases antigas.
    if IS_POSTGRES:
        return
    Base.metadata.create_all(bind=engine)
    ensure_user_carteira_column()
    ensure_carteira_ho_rules()
    ensure_carteira_schema_mode()
    ensure_carteira_coluna_metadata()
    ensure_schema_migration_baseline_marker()
    ensure_alpha_beta_schema_migration()
    ensure_operational_tables()
    ensure_user_meta_pagamento_column()
    ensure_user_enabled_tools_column()
    ensure_parecer_constraints()
    ensure_parecer_approval_columns()
    ensure_producao_unificada_view()
    ensure_gerencial_correction_tables()


def ensure_dynamic_carteira_constraints():
    with engine.begin() as connection:
        table_names = postgres_tables(connection)
        if "users" in table_names:
            connection.execute(text(f"ALTER TABLE {qualified_table('users')} DROP CONSTRAINT IF EXISTS negocial_users_carteira_check"))
            connection.execute(text(f"""
                ALTER TABLE {qualified_table('users')}
                ADD CONSTRAINT negocial_users_carteira_check
                CHECK (carteira IS NULL OR btrim(carteira) <> '')
            """))
        if "pareceres" in table_names:
            connection.execute(text(f"ALTER TABLE {qualified_table('pareceres')} DROP CONSTRAINT IF EXISTS negocial_pareceres_carteira_check"))
            connection.execute(text(f"""
                ALTER TABLE {qualified_table('pareceres')}
                ADD CONSTRAINT negocial_pareceres_carteira_check
                CHECK (btrim(carteira) <> '')
            """))


def ensure_schema_migration_baseline_marker():
    with engine.begin() as connection:
        if not IS_POSTGRES:
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS schema_migrations_meta (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    revision VARCHAR(80) NOT NULL UNIQUE,
                    description TEXT NOT NULL,
                    applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            connection.execute(text("""
                INSERT OR IGNORE INTO schema_migrations_meta (revision, description)
                VALUES ('20260707_0001', 'Baseline apos migracao para producao_registros')
            """))
            return
        connection.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {qualified_table('schema_migrations_meta')} (
                id SERIAL PRIMARY KEY,
                revision VARCHAR(80) NOT NULL UNIQUE,
                description TEXT NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        connection.execute(text(f"""
            INSERT INTO {qualified_table('schema_migrations_meta')} (revision, description)
            VALUES ('20260707_0001', 'Baseline apos migracao para producao_registros')
            ON CONFLICT (revision) DO NOTHING
        """))


def _schema_column_payload(raw: dict, order: int) -> dict:
    return {
        "nome": raw["nome"],
        "chave": raw["chave"],
        "tipo": raw.get("tipo", "texto"),
        "obrigatoria": bool(raw.get("obrigatoria", False)),
        "identificador": bool(raw.get("identificador", False)),
        "visivel": bool(raw.get("visivel", True)),
        "ordem": order,
        "automatico": bool(raw.get("automatico", False)),
        "auto_tipo": raw.get("auto_tipo"),
        "max_length": raw.get("max_length"),
        "mostrar_cadastro": bool(raw.get("mostrar_cadastro", True)),
        "cadastro_etapa": int(raw.get("cadastro_etapa", 2)),
        "opcoes_json": json.dumps(raw.get("opcoes", []), ensure_ascii=True),
    }


def _upsert_schema_column(connection, carteira_id: int, payload: dict) -> int:
    table = qualified_table("carteira_colunas")
    existing = connection.execute(
        text(f"SELECT id FROM {table} WHERE carteira_id = :carteira_id AND chave = :chave"),
        {"carteira_id": carteira_id, "chave": payload["chave"]},
    ).scalar()
    params = {"carteira_id": carteira_id, **payload}
    if existing:
        params["id"] = int(existing)
        connection.execute(text(f"""
            UPDATE {table}
            SET nome = :nome, tipo = :tipo, obrigatoria = :obrigatoria,
                identificador = :identificador, visivel = :visivel, ordem = :ordem,
                automatico = :automatico, auto_tipo = :auto_tipo, max_length = :max_length,
                mostrar_cadastro = :mostrar_cadastro, cadastro_etapa = :cadastro_etapa,
                opcoes_json = :opcoes_json
            WHERE id = :id
        """), params)
        return int(existing)
    return int(connection.execute(text(f"""
        INSERT INTO {table} (
            carteira_id, nome, chave, tipo, obrigatoria, identificador, visivel, ordem,
            automatico, auto_tipo, max_length, mostrar_cadastro, cadastro_etapa, opcoes_json
        ) VALUES (
            :carteira_id, :nome, :chave, :tipo, :obrigatoria, :identificador, :visivel, :ordem,
            :automatico, :auto_tipo, :max_length, :mostrar_cadastro, :cadastro_etapa, :opcoes_json
        ) RETURNING id
    """), params).scalar())


def _upsert_migrated_producao_field(connection, producao_id: int, coluna_id: int, column_type: str, value):
    if value in (None, ""):
        text_value = number_value = date_value = None
    elif column_type in {"numero", "moeda"}:
        text_value, number_value, date_value = None, value, None
    elif column_type == "data":
        text_value, number_value, date_value = None, None, value
    else:
        text_value, number_value, date_value = str(value), None, None
    timestamp = "NOW()" if IS_POSTGRES else "CURRENT_TIMESTAMP"
    connection.execute(text(f"""
        INSERT INTO {qualified_table('producao_campos')} (
            producao_id, coluna_id, valor_texto, valor_numero, valor_data, valor_json, updated_at
        ) VALUES (
            :producao_id, :coluna_id, :valor_texto, :valor_numero, :valor_data, NULL, {timestamp}
        )
        ON CONFLICT (producao_id, coluna_id) DO UPDATE SET
            valor_texto = EXCLUDED.valor_texto,
            valor_numero = EXCLUDED.valor_numero,
            valor_data = EXCLUDED.valor_data,
            valor_json = NULL,
            updated_at = {timestamp}
    """), {
        "producao_id": producao_id,
        "coluna_id": coluna_id,
        "valor_texto": text_value,
        "valor_numero": number_value,
        "valor_data": date_value,
    })


def _schema_migration_record_values(slug: str, row: dict) -> dict:
    common = {
        "DATA": row["data_acordo"],
        "CLIENTE": row["cliente"],
        "VALOR_TOTAL": row["valor_total_acordo"],
        "VALOR_TOTAL_DE_ACORDO": row["valor_total_acordo"],
        "ENTRADA": row["valor_entrada"],
        "VALOR_DA_ENTRADA": row["valor_entrada"],
        "TIPO_DE_ACORDO": row["tipo_acordo"],
        "VENCIMENTO": row["data_vencimento"],
        "DATA_DO_VENCIMENTO": row["data_vencimento"],
        "DATA_DO_PAGAMENTO": row["data_pagamento"],
        "STATUS": row["status"],
        "JUSTIFICATIVA": row["justificativa_status"],
        "NEGOCIADOR": row["username"],
    }
    if slug == "ALPHA":
        common.update({
            "DEBIT_ID": row["debit_id"],
            "CPF_CNPJ": row["cpf"],
            "DATA_DO_1_ATRASO": row["data_primeiro_atraso"],
            "PORTFOLIO": row["portfolio"],
            "CARTEIRA": row["carteira_alpha"],
        })
    else:
        common["SUITID"] = row["suitid"]
    return common


def ensure_alpha_beta_schema_migration():
    revision = "20260714_0002_alpha_beta_schema"
    with engine.begin() as connection:
        applied = connection.execute(
            text(f"SELECT 1 FROM {qualified_table('schema_migrations_meta')} WHERE revision = :revision"),
            {"revision": revision},
        ).scalar()
        if applied:
            return

        schemas = {"ALPHA": ALPHA_SCHEMA_COLUMNS, "BETA": BETA_SCHEMA_COLUMNS}
        migrated_slugs: set[str] = set()
        obsolete = {
            "ALPHA": {"CARTEIRA_SISTEMA", "USUARIO", "TIPO", "PAGAMENTO"},
            "BETA": {"OPERADOR"},
        }
        for slug, raw_columns in schemas.items():
            carteira_id = connection.execute(
                text(f"SELECT id FROM {qualified_table('carteiras_negociais')} WHERE slug = :slug"),
                {"slug": slug},
            ).scalar()
            if not carteira_id:
                continue
            migrated_slugs.add(slug)

            for key in obsolete[slug]:
                column_id = connection.execute(text(f"""
                    SELECT id FROM {qualified_table('carteira_colunas')}
                    WHERE carteira_id = :carteira_id AND chave = :chave
                """), {"carteira_id": carteira_id, "chave": key}).scalar()
                if column_id:
                    usage = connection.execute(
                        text(f"SELECT COUNT(*) FROM {qualified_table('producao_campos')} WHERE coluna_id = :column_id"),
                        {"column_id": column_id},
                    ).scalar()
                    if not usage:
                        connection.execute(
                            text(f"DELETE FROM {qualified_table('carteira_colunas')} WHERE id = :column_id"),
                            {"column_id": column_id},
                        )

            columns: dict[str, tuple[int, str]] = {}
            for order, raw in enumerate(raw_columns, start=1):
                payload = _schema_column_payload(raw, order)
                columns[payload["chave"]] = (_upsert_schema_column(connection, int(carteira_id), payload), payload["tipo"])

            detail_join = (
                f"JOIN {qualified_table('producao_alpha')} detail ON detail.producao_id = pr.id"
                if slug == "ALPHA"
                else f"JOIN {qualified_table('producao_beta')} detail ON detail.producao_id = pr.id"
            )
            detail_fields = (
                "detail.debit_id, detail.cpf, detail.data_primeiro_atraso, detail.portfolio, detail.carteira_alpha, NULL AS suitid"
                if slug == "ALPHA"
                else "NULL AS debit_id, NULL AS cpf, NULL AS data_primeiro_atraso, NULL AS portfolio, NULL AS carteira_alpha, detail.suitid"
            )
            rows = connection.execute(text(f"""
                SELECT pr.id, pr.data_acordo, pr.cliente, pr.valor_total_acordo, pr.valor_entrada,
                       pr.tipo_acordo, pr.data_vencimento, pr.data_pagamento, pr.status,
                       pr.justificativa_status, users.username, {detail_fields}
                FROM {qualified_table('producao_registros')} pr
                JOIN {qualified_table('users')} users ON users.id = pr.user_id
                {detail_join}
                WHERE pr.carteira = :slug
            """), {"slug": slug}).mappings().all()
            for row in rows:
                values = _schema_migration_record_values(slug, dict(row))
                for key, (column_id, column_type) in columns.items():
                    _upsert_migrated_producao_field(connection, int(row["id"]), column_id, column_type, values.get(key))

            connection.execute(
                text(f"UPDATE {qualified_table('carteiras_negociais')} SET modo_schema = :enabled WHERE id = :id"),
                {"enabled": True, "id": carteira_id},
            )

            if IS_POSTGRES and "carteira_schema_versions" in postgres_tables(connection):
                version = int(connection.execute(text(f"""
                    SELECT COALESCE(MAX(version_number), 0) + 1
                    FROM {qualified_table('carteira_schema_versions')} WHERE carteira_id = :id
                """), {"id": carteira_id}).scalar() or 1)
                snapshot = [{**_schema_column_payload(raw, order), "id": columns[raw["chave"]][0]} for order, raw in enumerate(raw_columns, start=1)]
                connection.execute(text(f"""
                    INSERT INTO {qualified_table('carteira_schema_versions')} (
                        carteira_id, version_number, action, schema_json, created_at
                    ) VALUES (:id, :version, 'migration', CAST(:schema_json AS JSONB), NOW())
                """), {"id": carteira_id, "version": version, "schema_json": json.dumps({"colunas": snapshot}, ensure_ascii=True)})

        if migrated_slugs == set(schemas):
            connection.execute(text(f"""
                INSERT INTO {qualified_table('schema_migrations_meta')} (revision, description)
                VALUES (:revision, 'Migra Alpha e Beta para o modo schema')
                ON CONFLICT (revision) DO NOTHING
            """), {"revision": revision})


def ensure_operational_tables():
    with engine.begin() as connection:
        if IS_POSTGRES:
            connection.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {qualified_table('operational_versions')} (
                    scope VARCHAR(80) PRIMARY KEY,
                    version BIGINT NOT NULL DEFAULT 1,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            connection.execute(text(f"""
                INSERT INTO {qualified_table('operational_versions')} (scope, version)
                VALUES ('producao', 1), ('pareceres', 1), ('carteiras', 1)
                ON CONFLICT (scope) DO NOTHING
            """))
            connection.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {qualified_table('permission_profiles')} (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(60) UNIQUE NOT NULL,
                    description TEXT,
                    permissions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            connection.execute(text(f"""
                INSERT INTO {qualified_table('permission_profiles')} (name, description, permissions_json)
                VALUES
                  ('ADMIN', 'Acesso administrativo completo', '["*"]'::jsonb),
                  ('GERENCIAL', 'Acesso gerencial operacional', '["producao:read","pareceres:read","reports:read"]'::jsonb),
                  ('SUPERVISOR', 'Acompanhamento e revisao de equipe', '["producao:read","pareceres:read"]'::jsonb),
                  ('NEGOCIADOR', 'Operacao negocial padrao', '["producao:write","pareceres:write"]'::jsonb)
                ON CONFLICT (name) DO NOTHING
            """))
            return
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS operational_versions (
                scope TEXT PRIMARY KEY,
                version INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        for scope in ("producao", "pareceres", "carteiras"):
            connection.execute(
                text("INSERT OR IGNORE INTO operational_versions (scope, version) VALUES (:scope, 1)"),
                {"scope": scope},
            )


def ensure_parecer_constraints():
    if not IS_POSTGRES:
        return
    with engine.begin() as connection:
        if "pareceres" not in postgres_tables(connection):
            return
        # Motivos de parecer são uma configuração de interface/processo e podem
        # crescer com o tempo. Manter uma CHECK constraint fixa aqui fez o motivo
        # EVENTO quebrar o cadastro com erro 500.
        connection.execute(
            text(
                f"ALTER TABLE {qualified_table('pareceres')} "
                "DROP CONSTRAINT IF EXISTS negocial_pareceres_motivo_check"
            )
        )


def ensure_user_carteira_column():
    with engine.begin() as connection:
        if IS_POSTGRES:
            column_names = postgres_columns(connection, "users")
            if "carteira" not in column_names:
                connection.execute(text(f"ALTER TABLE {qualified_table('users')} ADD COLUMN carteira VARCHAR(40)"))
            return
        columns = connection.execute(text("PRAGMA table_info(users)")).fetchall()
        column_names = {column[1] for column in columns}
        if "carteira" not in column_names:
            connection.execute(text("ALTER TABLE users ADD COLUMN carteira VARCHAR(40)"))


def ensure_carteira_coluna_metadata():
    with engine.begin() as connection:
        if IS_POSTGRES:
            column_names = postgres_columns(connection, "carteira_colunas")
            table_name = qualified_table("carteira_colunas")
            if "automatico" not in column_names:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN automatico BOOLEAN DEFAULT FALSE NOT NULL"))
            if "auto_tipo" not in column_names:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN auto_tipo VARCHAR(40)"))
            if "max_length" not in column_names:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN max_length INTEGER"))
            if "mostrar_cadastro" not in column_names:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN mostrar_cadastro BOOLEAN DEFAULT TRUE NOT NULL"))
            if "cadastro_etapa" not in column_names:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN cadastro_etapa INTEGER DEFAULT 2 NOT NULL"))
            connection.execute(text(f"""
                UPDATE {table_name}
                SET automatico = TRUE, auto_tipo = 'today'
                WHERE chave = 'DATA' AND COALESCE(auto_tipo, '') = ''
            """))
            connection.execute(text(f"""
                UPDATE {table_name}
                SET cadastro_etapa = 1
                WHERE chave IN ('DATA', 'CLIENTE', 'TIPO', 'TIPO_DE_ACORDO', 'PARCELADO_OU_VISTA', 'PARCELADO_OU_A_VISTA')
                   OR identificador = TRUE
            """))
            connection.execute(text(f"""
                UPDATE {table_name}
                SET mostrar_cadastro = FALSE
                WHERE chave IN ('NEGOCIADOR', 'OPERADOR', 'JUSTIFICATIVA')
            """))
            return
        columns = connection.execute(text("PRAGMA table_info(carteira_colunas)")).fetchall()
        column_names = {column[1] for column in columns}
        if "automatico" not in column_names:
            connection.execute(text("ALTER TABLE carteira_colunas ADD COLUMN automatico INTEGER DEFAULT 0 NOT NULL"))
        if "auto_tipo" not in column_names:
            connection.execute(text("ALTER TABLE carteira_colunas ADD COLUMN auto_tipo TEXT"))
        if "max_length" not in column_names:
            connection.execute(text("ALTER TABLE carteira_colunas ADD COLUMN max_length INTEGER"))
        if "mostrar_cadastro" not in column_names:
            connection.execute(text("ALTER TABLE carteira_colunas ADD COLUMN mostrar_cadastro INTEGER DEFAULT 1 NOT NULL"))
        if "cadastro_etapa" not in column_names:
            connection.execute(text("ALTER TABLE carteira_colunas ADD COLUMN cadastro_etapa INTEGER DEFAULT 2 NOT NULL"))
        connection.execute(text("""
            UPDATE carteira_colunas
            SET automatico = 1, auto_tipo = 'today'
            WHERE chave = 'DATA' AND COALESCE(auto_tipo, '') = ''
        """))
        connection.execute(text("""
            UPDATE carteira_colunas
            SET cadastro_etapa = 1
            WHERE chave IN ('DATA', 'CLIENTE', 'TIPO', 'TIPO_DE_ACORDO', 'PARCELADO_OU_VISTA', 'PARCELADO_OU_A_VISTA')
               OR identificador = 1
        """))
        connection.execute(text("""
            UPDATE carteira_colunas
            SET mostrar_cadastro = 0
            WHERE chave IN ('NEGOCIADOR', 'OPERADOR', 'JUSTIFICATIVA')
        """))


def ensure_carteira_ho_rules():
    with engine.begin() as connection:
        if IS_POSTGRES:
            column_names = postgres_columns(connection, "carteiras_negociais")
            table_name = qualified_table("carteiras_negociais")
            if "usa_percentual_ho" not in column_names:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN usa_percentual_ho BOOLEAN DEFAULT FALSE NOT NULL"))
            if "percentual_ho_padrao" not in column_names:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN percentual_ho_padrao NUMERIC(6, 2)"))
            if "percentual_ho_minimo" not in column_names:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN percentual_ho_minimo NUMERIC(6, 2)"))
            if "percentual_ho_maximo" not in column_names:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN percentual_ho_maximo NUMERIC(6, 2)"))
            if "calculo_automatico_ho" not in column_names:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN calculo_automatico_ho BOOLEAN DEFAULT FALSE NOT NULL"))
            return
        columns = connection.execute(text("PRAGMA table_info(carteiras_negociais)")).fetchall()
        column_names = {column[1] for column in columns}
        if "usa_percentual_ho" not in column_names:
            connection.execute(text("ALTER TABLE carteiras_negociais ADD COLUMN usa_percentual_ho INTEGER DEFAULT 0 NOT NULL"))
        if "percentual_ho_padrao" not in column_names:
            connection.execute(text("ALTER TABLE carteiras_negociais ADD COLUMN percentual_ho_padrao NUMERIC"))
        if "percentual_ho_minimo" not in column_names:
            connection.execute(text("ALTER TABLE carteiras_negociais ADD COLUMN percentual_ho_minimo NUMERIC"))
        if "percentual_ho_maximo" not in column_names:
            connection.execute(text("ALTER TABLE carteiras_negociais ADD COLUMN percentual_ho_maximo NUMERIC"))
        if "calculo_automatico_ho" not in column_names:
            connection.execute(text("ALTER TABLE carteiras_negociais ADD COLUMN calculo_automatico_ho INTEGER DEFAULT 0 NOT NULL"))


def ensure_carteira_schema_mode():
    with engine.begin() as connection:
        if IS_POSTGRES:
            column_names = postgres_columns(connection, "carteiras_negociais")
            table_name = qualified_table("carteiras_negociais")
            if "modo_schema" not in column_names:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN modo_schema BOOLEAN DEFAULT TRUE NOT NULL"))
            connection.execute(text(f"UPDATE {table_name} SET modo_schema = TRUE WHERE modo_schema IS NULL"))
            return
        columns = connection.execute(text("PRAGMA table_info(carteiras_negociais)")).fetchall()
        column_names = {column[1] for column in columns}
        if "modo_schema" not in column_names:
            connection.execute(text("ALTER TABLE carteiras_negociais ADD COLUMN modo_schema INTEGER DEFAULT 1 NOT NULL"))
        connection.execute(text("UPDATE carteiras_negociais SET modo_schema = 1 WHERE modo_schema IS NULL"))


def ensure_user_meta_pagamento_column():
    with engine.begin() as connection:
        if IS_POSTGRES:
            column_names = postgres_columns(connection, "users")
            if "meta_pagamento" not in column_names:
                connection.execute(text(f"ALTER TABLE {qualified_table('users')} ADD COLUMN meta_pagamento NUMERIC(12, 2) DEFAULT 70000.00 NOT NULL"))
            connection.execute(text(f"UPDATE {qualified_table('users')} SET meta_pagamento = 70000.00 WHERE meta_pagamento IS NULL"))
            return
        columns = connection.execute(text("PRAGMA table_info(users)")).fetchall()
        column_names = {column[1] for column in columns}
        if "meta_pagamento" not in column_names:
            connection.execute(text("ALTER TABLE users ADD COLUMN meta_pagamento NUMERIC(12, 2) DEFAULT 70000.00 NOT NULL"))
        connection.execute(text("UPDATE users SET meta_pagamento = 70000.00 WHERE meta_pagamento IS NULL"))


def ensure_user_enabled_tools_column():
    with engine.begin() as connection:
        if IS_POSTGRES:
            column_names = postgres_columns(connection, "users")
            if "enabled_tools" not in column_names:
                connection.execute(text(f"ALTER TABLE {qualified_table('users')} ADD COLUMN enabled_tools VARCHAR(120) DEFAULT 'producao,pareceres' NOT NULL"))
            connection.execute(text(f"UPDATE {qualified_table('users')} SET enabled_tools = 'producao,pareceres' WHERE enabled_tools IS NULL OR enabled_tools = ''"))
            return
        columns = connection.execute(text("PRAGMA table_info(users)")).fetchall()
        column_names = {column[1] for column in columns}
        if "enabled_tools" not in column_names:
            connection.execute(text("ALTER TABLE users ADD COLUMN enabled_tools VARCHAR(120) DEFAULT 'producao,pareceres' NOT NULL"))
        connection.execute(text("UPDATE users SET enabled_tools = 'producao,pareceres' WHERE enabled_tools IS NULL OR enabled_tools = ''"))


def ensure_parecer_approval_columns():
    with engine.begin() as connection:
        if IS_POSTGRES:
            table_names = postgres_tables(connection)
            if "pareceres" not in table_names:
                return
            column_names = postgres_columns(connection, "pareceres")
            if "approval_status" not in column_names:
                connection.execute(text(f"ALTER TABLE {qualified_table('pareceres')} ADD COLUMN approval_status VARCHAR(40) DEFAULT 'PENDENTE' NOT NULL"))
            if "approval_reason" not in column_names:
                connection.execute(text(f"ALTER TABLE {qualified_table('pareceres')} ADD COLUMN approval_reason VARCHAR(600)"))
            if "requested_at" not in column_names:
                connection.execute(text(f"ALTER TABLE {qualified_table('pareceres')} ADD COLUMN requested_at TIMESTAMPTZ"))
            if "approval_decided_at" not in column_names:
                connection.execute(text(f"ALTER TABLE {qualified_table('pareceres')} ADD COLUMN approval_decided_at TIMESTAMPTZ"))
            connection.execute(text(f"UPDATE {qualified_table('pareceres')} SET approval_status = 'APROVADO' WHERE status = 'SOLICITADO' AND (approval_status IS NULL OR approval_status = '')"))
            connection.execute(text(f"UPDATE {qualified_table('pareceres')} SET approval_status = 'REPROVADO' WHERE status = 'CANCELADO' AND (approval_status IS NULL OR approval_status = '')"))
            connection.execute(text(f"UPDATE {qualified_table('pareceres')} SET approval_status = 'PENDENTE' WHERE approval_status IS NULL OR approval_status = ''"))
            connection.execute(text(f"UPDATE {qualified_table('pareceres')} SET requested_at = updated_at WHERE status = 'SOLICITADO' AND requested_at IS NULL"))
            connection.execute(text(f"UPDATE {qualified_table('pareceres')} SET approval_decided_at = updated_at WHERE approval_status IN ('APROVADO', 'REPROVADO') AND approval_decided_at IS NULL"))
            return

        tables = connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
        table_names = {table[0] for table in tables}
        if "pareceres" not in table_names:
            return
        columns = connection.execute(text("PRAGMA table_info(pareceres)")).fetchall()
        column_names = {column[1] for column in columns}
        if "approval_status" not in column_names:
            connection.execute(text("ALTER TABLE pareceres ADD COLUMN approval_status VARCHAR(40) DEFAULT 'PENDENTE' NOT NULL"))
        if "approval_reason" not in column_names:
            connection.execute(text("ALTER TABLE pareceres ADD COLUMN approval_reason VARCHAR(600)"))
        if "requested_at" not in column_names:
            connection.execute(text("ALTER TABLE pareceres ADD COLUMN requested_at DATETIME"))
        if "approval_decided_at" not in column_names:
            connection.execute(text("ALTER TABLE pareceres ADD COLUMN approval_decided_at DATETIME"))
        connection.execute(text("UPDATE pareceres SET approval_status = 'APROVADO' WHERE status = 'SOLICITADO' AND (approval_status IS NULL OR approval_status = '')"))
        connection.execute(text("UPDATE pareceres SET approval_status = 'REPROVADO' WHERE status = 'CANCELADO' AND (approval_status IS NULL OR approval_status = '')"))
        connection.execute(text("UPDATE pareceres SET approval_status = 'PENDENTE' WHERE approval_status IS NULL OR approval_status = ''"))
        connection.execute(text("UPDATE pareceres SET requested_at = updated_at WHERE status = 'SOLICITADO' AND requested_at IS NULL"))
        connection.execute(text("UPDATE pareceres SET approval_decided_at = updated_at WHERE approval_status IN ('APROVADO', 'REPROVADO') AND approval_decided_at IS NULL"))

def ensure_producao_unificada_view():
    with engine.begin() as connection:
        view_name = qualified_table("producao_unificada")
        registro = qualified_table("producao_registros")
        gamma = qualified_table("producao_gamma")
        alpha = qualified_table("producao_alpha")
        beta_table = qualified_table("producao_beta")
        campos = qualified_table("producao_campos")
        colunas = qualified_table("carteira_colunas")
        if IS_POSTGRES:
            connection.execute(text(f"DROP VIEW IF EXISTS {qualified_table('producao_diaria_unificada')}"))
            connection.execute(text(f"DROP VIEW IF EXISTS {view_name}"))
            connection.execute(text(f"""
                CREATE VIEW {view_name} AS
                SELECT
                    pr.id,
                    pr.data_acordo,
                    COALESCE(it.debit_id, rt.suitid, gamma.npj, dyn.identificador, '') AS npj,
                    it.cpf,
                    pr.cliente,
                    COALESCE(gamma.gecor, '') AS gecor,
                    NULL::INTEGER AS dias_atraso,
                    it.data_primeiro_atraso,
                    it.portfolio,
                    it.carteira_alpha,
                    pr.valor_total_acordo,
                    pr.valor_entrada,
                    COALESCE(gamma.valor_ho, 0) AS valor_ho,
                    COALESCE(gamma.percentual_ho, 0) AS percentual_ho,
                    pr.tipo_acordo,
                    pr.data_vencimento,
                    pr.data_pagamento,
                    pr.status,
                    pr.justificativa_status,
                    COALESCE(gamma.autorizacao_flexibilizacao, 'NAO') AS autorizacao_flexibilizacao,
                    pr.carteira,
                    pr.user_id,
                    pr.created_at,
                    pr.updated_at,
                    pr.competencia
                FROM {registro} pr
                LEFT JOIN {gamma} gamma ON gamma.producao_id = pr.id
                LEFT JOIN {alpha} it ON it.producao_id = pr.id
                LEFT JOIN {beta_table} rt ON rt.producao_id = pr.id
                LEFT JOIN LATERAL (
                    SELECT pc.valor_texto AS identificador
                    FROM {campos} pc
                    JOIN {colunas} cc ON cc.id = pc.coluna_id
                    WHERE pc.producao_id = pr.id
                      AND cc.identificador = TRUE
                    ORDER BY cc.ordem, cc.id
                    LIMIT 1
                ) dyn ON TRUE
            """))
            return

        connection.execute(text("DROP VIEW IF EXISTS producao_diaria_unificada"))
        connection.execute(text("DROP VIEW IF EXISTS producao_unificada"))
        connection.execute(text("""
            CREATE VIEW producao_unificada AS
            SELECT
                pr.id,
                pr.data_acordo,
                COALESCE(it.debit_id, rt.suitid, gamma.npj, dyn.identificador, '') AS npj,
                it.cpf,
                pr.cliente,
                COALESCE(gamma.gecor, '') AS gecor,
                NULL AS dias_atraso,
                it.data_primeiro_atraso,
                it.portfolio,
                it.carteira_alpha,
                pr.valor_total_acordo,
                pr.valor_entrada,
                COALESCE(gamma.valor_ho, 0) AS valor_ho,
                COALESCE(gamma.percentual_ho, 0) AS percentual_ho,
                pr.tipo_acordo,
                pr.data_vencimento,
                pr.data_pagamento,
                pr.status,
                pr.justificativa_status,
                COALESCE(gamma.autorizacao_flexibilizacao, 'NAO') AS autorizacao_flexibilizacao,
                pr.carteira,
                pr.user_id,
                pr.created_at,
                pr.updated_at,
                pr.competencia
            FROM producao_registros pr
            LEFT JOIN producao_gamma gamma ON gamma.producao_id = pr.id
            LEFT JOIN producao_alpha it ON it.producao_id = pr.id
            LEFT JOIN producao_beta rt ON rt.producao_id = pr.id
            LEFT JOIN (
                SELECT pc.producao_id, pc.valor_texto AS identificador
                FROM producao_campos pc
                JOIN carteira_colunas cc ON cc.id = pc.coluna_id
                WHERE cc.identificador = 1
                GROUP BY pc.producao_id
            ) dyn ON dyn.producao_id = pr.id
        """))


def ensure_gerencial_correction_tables():
    with engine.begin() as connection:
        if IS_POSTGRES:
            connection.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {qualified_table('producao_gamma_gerencial')} (
                    producao_id INTEGER PRIMARY KEY REFERENCES {qualified_table('producao_registros')}(id) ON DELETE CASCADE,
                    uf VARCHAR(2),
                    data_ajuizamento DATE,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            connection.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {qualified_table('producao_correcoes')} (
                    id SERIAL PRIMARY KEY,
                    producao_id INTEGER NOT NULL REFERENCES {qualified_table('producao_registros')}(id) ON DELETE CASCADE,
                    campo TEXT NOT NULL,
                    valor_anterior TEXT,
                    valor_novo TEXT,
                    corrigido_por TEXT NOT NULL,
                    motivo TEXT,
                    criado_em TIMESTAMPTZ DEFAULT NOW(),
                    visualizado_pelo_negociador BOOLEAN DEFAULT FALSE
                )
            """))
            return


def qualified_table(table_name: str) -> str:
    return f"{DB_SCHEMA}.{table_name}" if IS_POSTGRES and DB_SCHEMA else table_name


def postgres_tables(connection):
    rows = connection.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = :schema
            """
        ),
        {"schema": DB_SCHEMA},
    ).fetchall()
    return {row[0] for row in rows}


def postgres_columns(connection, table_name: str):
    rows = connection.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table_name
            """
        ),
        {"schema": DB_SCHEMA, "table_name": table_name},
    ).fetchall()
    return {row[0] for row in rows}


def seed_admin_user(db: Session):
    existing_users = db.query(User).count()
    username = str(settings.admin_username or "").strip()
    password = str(settings.admin_password or "")
    if existing_users:
        return db.query(User).filter(User.username == username).first() if username else None

    if not username or not password:
        raise RuntimeError(
            "Banco sem usuarios. Defina ADMIN_USERNAME e ADMIN_PASSWORD apenas para o primeiro bootstrap."
        )
    if len(password) < 12 or password in {"2024", "admin", "password", username}:
        raise RuntimeError("ADMIN_PASSWORD deve ter pelo menos 12 caracteres e nao pode ser uma senha padrao.")

    admin = User(
        username=username,
        password_hash=hash_password(password),
        role="ADMIN",
        carteira=None,
        meta_pagamento=70000,
        active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin
