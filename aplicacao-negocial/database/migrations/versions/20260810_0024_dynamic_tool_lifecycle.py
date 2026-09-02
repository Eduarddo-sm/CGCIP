"""Adiciona destaque e suporte ao ciclo de vida das ferramentas dinamicas.

Revision ID: 20260810_0024
Revises: 20260804_0023
Create Date: 2026-08-10
"""

from alembic import op


revision = "20260810_0024"
down_revision = "20260804_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        ALTER TABLE negocial.ferramentas
            ADD COLUMN IF NOT EXISTS destaque_gerencial BOOLEAN NOT NULL DEFAULT FALSE;

        CREATE INDEX IF NOT EXISTS ix_ferramentas_destaque_ativas
            ON negocial.ferramentas (destaque_gerencial, active)
            WHERE destaque_gerencial = TRUE AND active = TRUE;
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        DROP INDEX IF EXISTS negocial.ix_ferramentas_destaque_ativas;
        ALTER TABLE negocial.ferramentas DROP COLUMN IF EXISTS destaque_gerencial;
        """
    )
