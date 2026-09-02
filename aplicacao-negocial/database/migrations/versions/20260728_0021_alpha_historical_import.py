"""Suporte auditavel para importacao historica da Alpha.

Revision ID: 20260728_0021
Revises: 20260728_0020
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op


revision = "20260728_0021"
down_revision = "20260728_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        ALTER TABLE negocial.producao_registros
            ADD COLUMN IF NOT EXISTS origem_registro VARCHAR(32)
                NOT NULL DEFAULT 'SISTEMA',
            ADD COLUMN IF NOT EXISTS import_source_hash VARCHAR(64),
            ADD COLUMN IF NOT EXISTS import_source_row INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE negocial.producao_registros
            DROP CONSTRAINT IF EXISTS ck_producao_origem_registro
        """
    )
    op.execute(
        """
        ALTER TABLE negocial.producao_registros
            ADD CONSTRAINT ck_producao_origem_registro
            CHECK (origem_registro IN ('SISTEMA', 'LEGADO_PLANILHA'))
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_producao_import_source_row
        ON negocial.producao_registros(import_source_hash, import_source_row)
        WHERE import_source_hash IS NOT NULL AND import_source_row IS NOT NULL
        """
    )
    op.execute(
        """
        ALTER TABLE negocial.producao_alpha
            ALTER COLUMN data_primeiro_atraso DROP NOT NULL,
            ADD COLUMN IF NOT EXISTS ho_origem VARCHAR(32)
                NOT NULL DEFAULT 'CALCULADO',
            ADD COLUMN IF NOT EXISTS ho_legado NUMERIC(14, 2)
        """
    )
    op.execute(
        """
        ALTER TABLE negocial.producao_alpha
            DROP CONSTRAINT IF EXISTS ck_producao_alpha_ho_origem
        """
    )
    op.execute(
        """
        ALTER TABLE negocial.producao_alpha
            ADD CONSTRAINT ck_producao_alpha_ho_origem
            CHECK (ho_origem IN ('CALCULADO', 'LEGADO_PLANILHA'))
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        DELETE FROM negocial.producao_alpha
        WHERE data_primeiro_atraso IS NULL
        """
    )
    op.execute(
        """
        ALTER TABLE negocial.producao_alpha
            DROP CONSTRAINT IF EXISTS ck_producao_alpha_ho_origem,
            DROP COLUMN IF EXISTS ho_legado,
            DROP COLUMN IF EXISTS ho_origem,
            ALTER COLUMN data_primeiro_atraso SET NOT NULL
        """
    )
    op.execute("DROP INDEX IF EXISTS negocial.uq_producao_import_source_row")
    op.execute(
        """
        ALTER TABLE negocial.producao_registros
            DROP CONSTRAINT IF EXISTS ck_producao_origem_registro,
            DROP COLUMN IF EXISTS import_source_row,
            DROP COLUMN IF EXISTS import_source_hash,
            DROP COLUMN IF EXISTS origem_registro
        """
    )
