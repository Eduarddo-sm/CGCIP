"""Remove indices redundantes de PK e constraints unique.

Revision ID: 20260720_0010
Revises: 20260720_0009
Create Date: 2026-07-20
"""
from alembic import op


revision = "20260720_0010"
down_revision = "20260720_0009"
branch_labels = None
depends_on = None


REDUNDANT_INDEXES = (
    "ix_negocial_users_id",
    "ix_negocial_users_username",
    "ix_negocial_sessions_id",
    "ix_negocial_sessions_token",
    "ix_negocial_producao_registros_id",
    "ix_negocial_pareceres_id",
)


def upgrade() -> None:
    for name in REDUNDANT_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS negocial.{name}")


def downgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_users_id ON negocial.users(id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_negocial_users_username ON negocial.users(username)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_sessions_id ON negocial.sessions(id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_negocial_sessions_token ON negocial.sessions(token)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_producao_registros_id ON negocial.producao_registros(id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_pareceres_id ON negocial.pareceres(id)")
