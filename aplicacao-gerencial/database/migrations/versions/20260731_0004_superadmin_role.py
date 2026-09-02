"""Adiciona o perfil superadministrador ao controle gerencial.

Revision ID: 20260731_0004
Revises: 20260720_0003
Create Date: 2026-07-31
"""
from alembic import op


revision = "20260731_0004"
down_revision = "20260720_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE gerencial.users DROP CONSTRAINT IF EXISTS gerencial_users_role_check")
    op.execute(
        """
        ALTER TABLE gerencial.users
        ADD CONSTRAINT gerencial_users_role_check
        CHECK (lower(role) IN ('superadmin', 'admin', 'gerencial', 'supervisor', 'user'))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE gerencial.users DROP CONSTRAINT IF EXISTS gerencial_users_role_check")
    op.execute("UPDATE gerencial.users SET role = 'admin' WHERE lower(role) = 'superadmin'")
    op.execute(
        """
        ALTER TABLE gerencial.users
        ADD CONSTRAINT gerencial_users_role_check
        CHECK (lower(role) IN ('admin', 'gerencial', 'supervisor', 'user'))
        """
    )
