"""Motores semanticos e bases condicionais para H.O.

Revision ID: 20260728_0020
Revises: 20260728_0019
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op


revision = "20260728_0020"
down_revision = "20260728_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        ALTER TABLE negocial.carteira_regras_calculo
            ADD COLUMN IF NOT EXISTS motor_calculo VARCHAR(32)
                NOT NULL DEFAULT 'PERCENTUAL_FIXO',
            ADD COLUMN IF NOT EXISTS coluna_base_vista_id INTEGER
                REFERENCES negocial.carteira_colunas(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS coluna_base_parcelado_id INTEGER
                REFERENCES negocial.carteira_colunas(id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        ALTER TABLE negocial.carteira_regras_calculo
            DROP CONSTRAINT IF EXISTS ck_carteira_regra_ho_motor
        """
    )
    op.execute(
        """
        ALTER TABLE negocial.carteira_regras_calculo
            ADD CONSTRAINT ck_carteira_regra_ho_motor
            CHECK (
                motor_calculo IN (
                    'PERCENTUAL_FIXO',
                    'PERCENTUAL_CONDICIONAL',
                    'ALPHA_EXCEPCIONAL'
                )
            )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_carteira_regra_ho_bases_condicionais
        ON negocial.carteira_regras_calculo(
            coluna_base_vista_id,
            coluna_base_parcelado_id
        )
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        ALTER TABLE negocial.carteira_regras_calculo
            DROP CONSTRAINT IF EXISTS ck_carteira_regra_ho_motor
        """
    )
    op.execute("DROP INDEX IF EXISTS negocial.ix_carteira_regra_ho_bases_condicionais")
    op.execute(
        """
        ALTER TABLE negocial.carteira_regras_calculo
            DROP COLUMN IF EXISTS coluna_base_parcelado_id,
            DROP COLUMN IF EXISTS coluna_base_vista_id,
            DROP COLUMN IF EXISTS motor_calculo
        """
    )
