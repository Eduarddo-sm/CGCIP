"""Registra a versao inicial do schema configuravel do GAMMA.

Revision ID: 20260714_0006
Revises: 20260714_0005
Create Date: 2026-07-14
"""

from __future__ import annotations

from alembic import op


revision = "20260714_0006"
down_revision = "20260714_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        INSERT INTO negocial.carteira_schema_versions (
            carteira_id, version_number, action, schema_json, created_at
        )
        SELECT c.id,
               COALESCE((
                   SELECT MAX(v.version_number)
                   FROM negocial.carteira_schema_versions v
                   WHERE v.carteira_id = c.id
               ), 0) + 1,
               'migration_gamma_schema',
               jsonb_build_object(
                   'carteira', to_jsonb(c),
                   'colunas', COALESCE((
                       SELECT jsonb_agg(to_jsonb(cc) ORDER BY cc.ordem, cc.id)
                       FROM negocial.carteira_colunas cc
                       WHERE cc.carteira_id = c.id
                   ), '[]'::jsonb)
               ),
               NOW()
        FROM negocial.carteiras_negociais c
        WHERE c.slug = 'GAMMA'
          AND NOT EXISTS (
              SELECT 1
              FROM negocial.carteira_schema_versions current_version
              WHERE current_version.carteira_id = c.id
                AND current_version.action = 'migration_gamma_schema'
          )
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            DELETE FROM negocial.carteira_schema_versions versions
            USING negocial.carteiras_negociais wallets
            WHERE versions.carteira_id = wallets.id
              AND wallets.slug = 'GAMMA'
              AND versions.action = 'migration_gamma_schema'
            """
        )
