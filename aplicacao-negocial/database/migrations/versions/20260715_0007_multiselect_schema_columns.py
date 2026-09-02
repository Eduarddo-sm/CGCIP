"""Adiciona colunas de selecao multipla aos schemas de carteira.

Revision ID: 20260715_0007
Revises: 20260714_0006
Create Date: 2026-07-15
"""

from __future__ import annotations

from alembic import op


revision = "20260715_0007"
down_revision = "20260714_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE negocial.carteira_colunas DROP CONSTRAINT IF EXISTS ck_negocial_carteira_colunas_tipo")
    op.execute(
        """
        ALTER TABLE negocial.carteira_colunas
        ADD CONSTRAINT ck_negocial_carteira_colunas_tipo
        CHECK (tipo IN ('texto', 'numero', 'moeda', 'data', 'select', 'multiselect', 'boolean'))
        """
    )
    op.execute(
        """
        INSERT INTO negocial.schema_migrations_meta (revision, description)
        VALUES ('20260715_0007', 'Adiciona selecao multipla aos schemas de carteira')
        ON CONFLICT (revision) DO NOTHING
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("UPDATE negocial.carteira_colunas SET tipo = 'select' WHERE tipo = 'multiselect'")
    op.execute("ALTER TABLE negocial.carteira_colunas DROP CONSTRAINT IF EXISTS ck_negocial_carteira_colunas_tipo")
    op.execute(
        """
        ALTER TABLE negocial.carteira_colunas
        ADD CONSTRAINT ck_negocial_carteira_colunas_tipo
        CHECK (tipo IN ('texto', 'numero', 'moeda', 'data', 'select', 'boolean'))
        """
    )
    op.execute("DELETE FROM negocial.schema_migrations_meta WHERE revision = '20260715_0007'")
