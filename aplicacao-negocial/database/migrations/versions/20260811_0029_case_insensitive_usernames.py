"""Normaliza e impede usernames duplicados por diferenca de caixa.

Revision ID: 20260811_0029
Revises: 20260810_0028
Create Date: 2026-08-11
"""
from alembic import op
import sqlalchemy as sa


revision = "20260811_0029"
down_revision = "20260810_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    schema = "negocial" if bind.dialect.name == "postgresql" else None
    prefix = f"{schema}." if schema else ""
    rows = bind.execute(sa.text(
        f"SELECT id, username, carteira FROM {prefix}users ORDER BY lower(username), id"
    )).fetchall()
    used = {str(row[1]).strip().lower() for row in rows}
    seen: set[str] = set()
    for user_id, username, carteira in rows:
        normalized = str(username or "").strip().lower()
        if normalized not in seen:
            seen.add(normalized)
            continue
        suffix = str(carteira or "usuario").strip().lower().replace(" ", "_") or "usuario"
        candidate = f"{normalized}.{suffix}"
        if candidate in used:
            candidate = f"{candidate}.{user_id}"
        bind.execute(
            sa.text(f"UPDATE {prefix}users SET username = :username WHERE id = :id"),
            {"username": candidate, "id": user_id},
        )
        used.add(candidate)
    index_name = "ux_negocial_users_username_lower"
    op.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {prefix}users (lower(username))")


def downgrade() -> None:
    prefix = "negocial." if op.get_bind().dialect.name == "postgresql" else ""
    op.execute(f"DROP INDEX IF EXISTS {prefix}ux_negocial_users_username_lower")
