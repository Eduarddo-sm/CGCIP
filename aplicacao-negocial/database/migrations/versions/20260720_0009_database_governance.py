"""Endurece governanca, integridade e retencao do banco negocial.

Revision ID: 20260720_0009
Revises: 20260716_0008
Create Date: 2026-07-20
"""

from __future__ import annotations

from alembic import op


revision = "20260720_0009"
down_revision = "20260716_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS negocial.db_retention_policies (
            scope VARCHAR(80) PRIMARY KEY,
            retention_days INTEGER NOT NULL,
            keep_latest INTEGER NOT NULL DEFAULT 0,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_negocial_retention_positive CHECK (retention_days >= 1 AND keep_latest >= 0)
        )
        """
    )
    op.execute(
        """
        INSERT INTO negocial.db_retention_policies (scope, retention_days, keep_latest)
        VALUES
          ('sessions', 7, 0),
          ('audit_logs', 365, 0),
          ('schema_versions', 3650, 50),
          ('data_quality', 180, 0)
        ON CONFLICT (scope) DO NOTHING
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS negocial.data_quality_issues (
            id SERIAL PRIMARY KEY,
            table_name VARCHAR(120) NOT NULL,
            entity_id VARCHAR(120),
            issue_type VARCHAR(120) NOT NULL,
            severity VARCHAR(40) NOT NULL DEFAULT 'warning',
            details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            resolved BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at TIMESTAMPTZ,
            CONSTRAINT ck_negocial_quality_severity CHECK (severity IN ('info', 'warning', 'error', 'critical'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_data_quality_open ON negocial.data_quality_issues (resolved, severity, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_data_quality_entity ON negocial.data_quality_issues (table_name, entity_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_sessions_expires_at ON negocial.sessions (expires_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_audit_logs_created_entity ON negocial.audit_logs (created_at DESC, entity_type, entity_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_carteira_colunas_carteira_ordem ON negocial.carteira_colunas (carteira_id, ordem, id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_producao_campos_coluna_numero ON negocial.producao_campos (coluna_id, valor_numero)")

    op.execute(
        """
        UPDATE negocial.producao_campos fields
        SET valor_texto = CASE WHEN columns.tipo IN ('texto', 'select', 'boolean') THEN fields.valor_texto ELSE NULL END,
            valor_numero = CASE WHEN columns.tipo IN ('numero', 'moeda') THEN fields.valor_numero ELSE NULL END,
            valor_data = CASE WHEN columns.tipo = 'data' THEN fields.valor_data ELSE NULL END,
            valor_json = CASE WHEN columns.tipo = 'multiselect' THEN fields.valor_json ELSE NULL END
        FROM negocial.carteira_colunas columns
        WHERE columns.id = fields.coluna_id
          AND num_nonnulls(fields.valor_texto, fields.valor_numero, fields.valor_data, fields.valor_json) > 1
        """
    )
    op.execute("ALTER TABLE negocial.producao_campos DROP CONSTRAINT IF EXISTS ck_negocial_producao_campos_single_value")
    op.execute(
        """
        ALTER TABLE negocial.producao_campos
        ADD CONSTRAINT ck_negocial_producao_campos_single_value
        CHECK (num_nonnulls(valor_texto, valor_numero, valor_data, valor_json) <= 1)
        """
    )
    op.execute("ALTER TABLE negocial.carteira_colunas DROP CONSTRAINT IF EXISTS ck_negocial_carteira_colunas_cadastro_etapa")
    op.execute("ALTER TABLE negocial.carteira_colunas ADD CONSTRAINT ck_negocial_carteira_colunas_cadastro_etapa CHECK (cadastro_etapa IN (1, 2))")
    op.execute("ALTER TABLE negocial.carteira_colunas DROP CONSTRAINT IF EXISTS ck_negocial_carteira_colunas_max_length")
    op.execute("ALTER TABLE negocial.carteira_colunas ADD CONSTRAINT ck_negocial_carteira_colunas_max_length CHECK (max_length IS NULL OR max_length > 0)")
    op.execute("ALTER TABLE negocial.carteiras_negociais DROP CONSTRAINT IF EXISTS ck_negocial_carteiras_percentuais_ho")
    op.execute(
        """
        ALTER TABLE negocial.carteiras_negociais
        ADD CONSTRAINT ck_negocial_carteiras_percentuais_ho
        CHECK (
            (percentual_ho_padrao IS NULL OR percentual_ho_padrao >= 0)
            AND (percentual_ho_minimo IS NULL OR percentual_ho_minimo >= 0)
            AND (percentual_ho_maximo IS NULL OR percentual_ho_maximo >= 0)
            AND (percentual_ho_minimo IS NULL OR percentual_ho_maximo IS NULL OR percentual_ho_minimo <= percentual_ho_maximo)
        )
        """
    )
    op.execute("ALTER TABLE negocial.producao_registros DROP CONSTRAINT IF EXISTS ck_negocial_producao_valores_non_negative")
    op.execute(
        """
        ALTER TABLE negocial.producao_registros
        ADD CONSTRAINT ck_negocial_producao_valores_non_negative
        CHECK (valor_total_acordo >= 0 AND valor_entrada >= 0)
        """
    )
    op.execute("ALTER TABLE negocial.producao_gamma DROP CONSTRAINT IF EXISTS ck_negocial_producao_gamma_valores_non_negative")
    op.execute(
        """
        ALTER TABLE negocial.producao_gamma
        ADD CONSTRAINT ck_negocial_producao_gamma_valores_non_negative
        CHECK (valor_ho >= 0 AND percentual_ho >= 0)
        """
    )

    op.execute(
        """
        INSERT INTO negocial.schema_migrations_meta (revision, description)
        VALUES ('20260720_0009', 'Endurece governanca, integridade e retencao do banco negocial')
        ON CONFLICT (revision) DO NOTHING
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DELETE FROM negocial.schema_migrations_meta WHERE revision = '20260720_0009'")
    op.execute("ALTER TABLE negocial.producao_gamma DROP CONSTRAINT IF EXISTS ck_negocial_producao_gamma_valores_non_negative")
    op.execute("ALTER TABLE negocial.producao_registros DROP CONSTRAINT IF EXISTS ck_negocial_producao_valores_non_negative")
    op.execute("ALTER TABLE negocial.carteiras_negociais DROP CONSTRAINT IF EXISTS ck_negocial_carteiras_percentuais_ho")
    op.execute("ALTER TABLE negocial.carteira_colunas DROP CONSTRAINT IF EXISTS ck_negocial_carteira_colunas_max_length")
    op.execute("ALTER TABLE negocial.carteira_colunas DROP CONSTRAINT IF EXISTS ck_negocial_carteira_colunas_cadastro_etapa")
    op.execute("ALTER TABLE negocial.producao_campos DROP CONSTRAINT IF EXISTS ck_negocial_producao_campos_single_value")
    op.execute("DROP INDEX IF EXISTS negocial.ix_negocial_producao_campos_coluna_numero")
    op.execute("DROP INDEX IF EXISTS negocial.ix_negocial_carteira_colunas_carteira_ordem")
    op.execute("DROP INDEX IF EXISTS negocial.ix_negocial_audit_logs_created_entity")
    op.execute("DROP INDEX IF EXISTS negocial.ix_negocial_sessions_expires_at")
    op.execute("DROP INDEX IF EXISTS negocial.ix_negocial_data_quality_entity")
    op.execute("DROP INDEX IF EXISTS negocial.ix_negocial_data_quality_open")
    op.execute("DROP TABLE IF EXISTS negocial.data_quality_issues")
    op.execute("DROP TABLE IF EXISTS negocial.db_retention_policies")

