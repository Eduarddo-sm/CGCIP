"""Normaliza JSON null legado nos campos dinamicos.

Revision ID: 20260721_0012
Revises: 20260720_0011
Create Date: 2026-07-21
"""
from __future__ import annotations

from alembic import op


revision = "20260721_0012"
down_revision = "20260720_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        UPDATE negocial.producao_campos
           SET valor_json = NULL
         WHERE valor_json::text = 'null'
        """
    )


def downgrade() -> None:
    # JSON null was invalid for scalar dynamic fields and must not be restored.
    pass
