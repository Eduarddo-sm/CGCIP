"""Adiciona metas mensais por negociador e preserva o historico existente.

Revision ID: 20260810_0025
Revises: 20260810_0024
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260810_0025"
down_revision = "20260810_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    is_postgres = op.get_bind().dialect.name == "postgresql"
    table_schema = "negocial" if is_postgres else None
    users_table = "negocial.users.id" if is_postgres else "users.id"
    op.create_table(
        "user_monthly_goals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("competencia", sa.Date(), nullable=False),
        sa.Column("meta_pagamento", sa.Numeric(14, 2), nullable=False),
        sa.Column("updated_by", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], [users_table], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "competencia", name="uq_user_monthly_goals_user_competencia"),
        schema=table_schema,
    )
    schema = "negocial." if is_postgres else ""
    op.execute(f"CREATE INDEX ix_user_monthly_goals_user_id ON {schema}user_monthly_goals (user_id)")
    op.execute(f"CREATE INDEX ix_user_monthly_goals_competencia ON {schema}user_monthly_goals (competencia)")
    op.execute(
        f"""
        INSERT INTO {schema}user_monthly_goals (user_id, competencia, meta_pagamento, updated_by, created_at, updated_at)
        SELECT DISTINCT pr.user_id, pr.competencia, u.meta_pagamento, 'MIGRACAO', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM {schema}producao_registros pr
        JOIN {schema}users u ON u.id = pr.user_id
        WHERE pr.competencia IS NOT NULL
        """
    )


def downgrade() -> None:
    schema = "negocial." if op.get_bind().dialect.name == "postgresql" else ""
    op.execute(f"DROP INDEX IF EXISTS {schema}ix_user_monthly_goals_competencia")
    op.execute(f"DROP INDEX IF EXISTS {schema}ix_user_monthly_goals_user_id")
    op.drop_table("user_monthly_goals", schema="negocial" if op.get_bind().dialect.name == "postgresql" else None)
