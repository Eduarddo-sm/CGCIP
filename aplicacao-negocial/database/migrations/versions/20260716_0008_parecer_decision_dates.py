"""Adiciona datas de solicitacao e decisao aos pareceres.

Revision ID: 20260716_0008
Revises: 20260715_0007
Create Date: 2026-07-16
"""

from __future__ import annotations

from alembic import op


revision = "20260716_0008"
down_revision = "20260715_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE negocial.pareceres ADD COLUMN IF NOT EXISTS requested_at TIMESTAMPTZ")
    op.execute("ALTER TABLE negocial.pareceres ADD COLUMN IF NOT EXISTS approval_decided_at TIMESTAMPTZ")
    op.execute("UPDATE negocial.pareceres SET requested_at = updated_at WHERE status = 'SOLICITADO' AND requested_at IS NULL")
    op.execute("UPDATE negocial.pareceres SET approval_decided_at = updated_at WHERE approval_status IN ('APROVADO', 'REPROVADO') AND approval_decided_at IS NULL")
    op.execute(
        """
        INSERT INTO negocial.schema_migrations_meta (revision, description)
        VALUES ('20260716_0008', 'Adiciona datas de solicitacao e decisao aos pareceres')
        ON CONFLICT (revision) DO NOTHING
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE negocial.pareceres DROP COLUMN IF EXISTS approval_decided_at")
    op.execute("ALTER TABLE negocial.pareceres DROP COLUMN IF EXISTS requested_at")
    op.execute("DELETE FROM negocial.schema_migrations_meta WHERE revision = '20260716_0008'")
