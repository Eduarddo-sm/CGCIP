"""Registra as decisoes de virada mensal da producao.

Revision ID: 20260810_0027
Revises: 20260810_0026
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260810_0027"
down_revision = "20260810_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    is_postgres = op.get_bind().dialect.name == "postgresql"
    table_schema = "negocial" if is_postgres else None
    users_table = "negocial.users.id" if is_postgres else "users.id"
    op.create_table(
        "producao_viradas_mensais",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("competencia_origem", sa.Date(), nullable=False),
        sa.Column("competencia_destino", sa.Date(), nullable=False),
        sa.Column("total_candidatos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_transferidos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ids_transferidos", sa.JSON(), nullable=False),
        sa.Column("confirmado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], [users_table], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id",
            "competencia_origem",
            "competencia_destino",
            name="uq_producao_virada_usuario_competencias",
        ),
        schema=table_schema,
    )
    schema = "negocial." if is_postgres else ""
    op.execute(f"CREATE INDEX ix_producao_viradas_mensais_user_id ON {schema}producao_viradas_mensais (user_id)")
    op.execute(f"CREATE INDEX ix_producao_viradas_mensais_destino ON {schema}producao_viradas_mensais (competencia_destino)")


def downgrade() -> None:
    schema = "negocial." if op.get_bind().dialect.name == "postgresql" else ""
    op.execute(f"DROP INDEX IF EXISTS {schema}ix_producao_viradas_mensais_destino")
    op.execute(f"DROP INDEX IF EXISTS {schema}ix_producao_viradas_mensais_user_id")
    op.drop_table("producao_viradas_mensais", schema="negocial" if op.get_bind().dialect.name == "postgresql" else None)
