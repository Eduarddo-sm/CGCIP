"""Adiciona auditoria, perfis e versoes operacionais.

Revision ID: 20260713_0004
Revises: 20260707_0003
Create Date: 2026-07-13
"""

from __future__ import annotations

from alembic import op


revision = "20260713_0004"
down_revision = "20260707_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS negocial.audit_logs (
            id SERIAL PRIMARY KEY,
            actor_user_id INTEGER NULL REFERENCES negocial.users(id) ON DELETE SET NULL,
            actor_username VARCHAR(80),
            action VARCHAR(80) NOT NULL,
            entity_type VARCHAR(80) NOT NULL,
            entity_id VARCHAR(80),
            source VARCHAR(40) NOT NULL DEFAULT 'negocial',
            before_json JSONB,
            after_json JSONB,
            diff_json JSONB,
            reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_audit_logs_actor ON negocial.audit_logs (actor_user_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_audit_logs_entity ON negocial.audit_logs (entity_type, entity_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_audit_logs_action ON negocial.audit_logs (action, created_at DESC)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS negocial.operational_versions (
            scope VARCHAR(80) PRIMARY KEY,
            version BIGINT NOT NULL DEFAULT 1,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        INSERT INTO negocial.operational_versions (scope, version)
        VALUES ('producao', 1), ('pareceres', 1), ('carteiras', 1)
        ON CONFLICT (scope) DO NOTHING
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS negocial.permission_profiles (
            id SERIAL PRIMARY KEY,
            name VARCHAR(60) UNIQUE NOT NULL,
            description TEXT,
            permissions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        INSERT INTO negocial.permission_profiles (name, description, permissions_json)
        VALUES
          ('ADMIN', 'Acesso administrativo completo', '["*"]'::jsonb),
          ('GERENCIAL', 'Acesso gerencial operacional', '["producao:read","pareceres:read","reports:read"]'::jsonb),
          ('SUPERVISOR', 'Acompanhamento e revisao de equipe', '["producao:read","pareceres:read"]'::jsonb),
          ('NEGOCIADOR', 'Operacao negocial padrao', '["producao:write","pareceres:write"]'::jsonb)
        ON CONFLICT (name) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO negocial.schema_migrations_meta (revision, description)
        VALUES ('20260713_0004', 'Adiciona auditoria, perfis de permissao e versoes operacionais')
        ON CONFLICT (revision) DO NOTHING
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DELETE FROM negocial.schema_migrations_meta WHERE revision = '20260713_0004'")
    op.execute("DROP TABLE IF EXISTS negocial.permission_profiles")
    op.execute("DROP TABLE IF EXISTS negocial.operational_versions")
    op.execute("DROP INDEX IF EXISTS negocial.ix_negocial_audit_logs_action")
    op.execute("DROP INDEX IF EXISTS negocial.ix_negocial_audit_logs_entity")
    op.execute("DROP INDEX IF EXISTS negocial.ix_negocial_audit_logs_actor")
    op.execute("DROP TABLE IF EXISTS negocial.audit_logs")
