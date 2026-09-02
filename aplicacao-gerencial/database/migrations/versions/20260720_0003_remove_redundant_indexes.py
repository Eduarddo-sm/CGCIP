"""Remove indice redundante coberto pela constraint unique.

Revision ID: 20260720_0003
Revises: 20260720_0002
Create Date: 2026-07-20
"""
from alembic import op


revision = "20260720_0003"
down_revision = "20260720_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS gerencial.ix_gerencial_users_username")


def downgrade() -> None:
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_gerencial_users_username ON gerencial.users(username)")
