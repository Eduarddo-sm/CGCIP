"""Adiciona lixeira reversivel para ferramentas dinamicas.

Revision ID: 20260811_0030
Revises: 20260811_0029
Create Date: 2026-08-11
"""

from alembic import op


revision = "20260811_0030"
down_revision = "20260811_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        ALTER TABLE negocial.ferramentas
            ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS purge_after TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS deleted_by INTEGER
                REFERENCES negocial.users(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS deletion_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb;

        CREATE INDEX IF NOT EXISTS ix_ferramentas_lixeira_expiracao
            ON negocial.ferramentas (purge_after)
            WHERE deleted_at IS NOT NULL;

        ALTER TABLE negocial.ferramentas
            DROP CONSTRAINT IF EXISTS ck_ferramentas_lixeira_datas;
        ALTER TABLE negocial.ferramentas
            ADD CONSTRAINT ck_ferramentas_lixeira_datas CHECK (
                (deleted_at IS NULL AND purge_after IS NULL)
                OR (deleted_at IS NOT NULL AND purge_after IS NOT NULL AND purge_after > deleted_at)
            );

        INSERT INTO negocial.schema_migrations_meta (revision, description)
        VALUES ('20260811_0030', 'Lixeira reversivel de tres dias para ferramentas dinamicas')
        ON CONFLICT (revision) DO NOTHING;
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        DELETE FROM negocial.schema_migrations_meta WHERE revision = '20260811_0030';
        DROP INDEX IF EXISTS negocial.ix_ferramentas_lixeira_expiracao;
        ALTER TABLE negocial.ferramentas
            DROP CONSTRAINT IF EXISTS ck_ferramentas_lixeira_datas,
            DROP COLUMN IF EXISTS deletion_snapshot_json,
            DROP COLUMN IF EXISTS deleted_by,
            DROP COLUMN IF EXISTS purge_after,
            DROP COLUMN IF EXISTS deleted_at;
        """
    )
