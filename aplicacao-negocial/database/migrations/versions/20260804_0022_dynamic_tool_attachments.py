"""Completa metadados e auditoria dos anexos das ferramentas dinamicas.

Revision ID: 20260804_0022
Revises: 20260728_0021
Create Date: 2026-08-04
"""

from alembic import op


revision = "20260804_0022"
down_revision = "20260728_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        ALTER TABLE negocial.ferramenta_anexos
            ADD COLUMN IF NOT EXISTS username VARCHAR(80),
            ADD COLUMN IF NOT EXISTS campo_chave VARCHAR(120),
            ADD COLUMN IF NOT EXISTS sha256 VARCHAR(64),
            ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE,
            ADD COLUMN IF NOT EXISTS removed_at TIMESTAMPTZ
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ferramenta_anexos_registro_ativos "
        "ON negocial.ferramenta_anexos(registro_id, active, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ferramenta_anexos_campo "
        "ON negocial.ferramenta_anexos(registro_id, campo_chave, active)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS negocial.ix_ferramenta_anexos_campo")
    op.execute("DROP INDEX IF EXISTS negocial.ix_ferramenta_anexos_registro_ativos")
    op.execute(
        """
        ALTER TABLE negocial.ferramenta_anexos
            DROP COLUMN IF EXISTS removed_at,
            DROP COLUMN IF EXISTS active,
            DROP COLUMN IF EXISTS sha256,
            DROP COLUMN IF EXISTS campo_chave,
            DROP COLUMN IF EXISTS username
        """
    )
