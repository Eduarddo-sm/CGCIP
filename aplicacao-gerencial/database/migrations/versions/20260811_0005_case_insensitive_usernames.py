"""Impede usernames duplicados por diferenca de caixa.

Revision ID: 20260811_0005
Revises: 20260731_0004
Create Date: 2026-08-11
"""
from alembic import op


revision = "20260811_0005"
down_revision = "20260731_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_gerencial_users_username_lower "
        "ON gerencial.users (lower(username))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS gerencial.ux_gerencial_users_username_lower")
