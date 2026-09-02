"""Amplia o percentual de atingimento dos honorarios Alpha.

Revision ID: 20260901_0036
Revises: 20260825_0035
Create Date: 2026-09-01
"""

from __future__ import annotations

from alembic import op


revision = "20260901_0036"
down_revision = "20260825_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        ALTER TABLE negocial.alpha_ho_calculations
        ALTER COLUMN attainment_percent TYPE NUMERIC(14, 4)
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        ALTER TABLE negocial.alpha_ho_calculations
        ALTER COLUMN attainment_percent TYPE NUMERIC(9, 4)
        """
    )
