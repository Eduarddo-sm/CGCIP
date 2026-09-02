"""Separa Beta e formaliza campos dinamicos.

Revision ID: 20260707_0002
Revises: 20260707_0001
Create Date: 2026-07-07
"""

from __future__ import annotations

from alembic import op


revision = "20260707_0002"
down_revision = "20260707_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("CREATE SCHEMA IF NOT EXISTS negocial")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS negocial.producao_beta (
            producao_id INTEGER PRIMARY KEY REFERENCES negocial.producao_registros(id) ON DELETE CASCADE,
            suitid VARCHAR(80) NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_producao_beta_suitid ON negocial.producao_beta (suitid)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS negocial.producao_campos (
            producao_id INTEGER NOT NULL REFERENCES negocial.producao_registros(id) ON DELETE CASCADE,
            coluna_id INTEGER NOT NULL REFERENCES negocial.carteira_colunas(id) ON DELETE CASCADE,
            valor_texto TEXT,
            valor_numero NUMERIC(18, 4),
            valor_data DATE,
            valor_json JSONB,
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (producao_id, coluna_id)
        )
        """
    )

    # Beta estava usando producao_gamma apenas para armazenar o SUITID no campo npj.
    op.execute(
        """
        INSERT INTO negocial.producao_beta (producao_id, suitid)
        SELECT pr.id, gamma.npj
        FROM negocial.producao_registros pr
        JOIN negocial.producao_gamma gamma ON gamma.producao_id = pr.id
        LEFT JOIN negocial.producao_beta rt ON rt.producao_id = pr.id
        WHERE upper(coalesce(pr.carteira, '')) = 'BETA'
          AND rt.producao_id IS NULL
        """
    )
    op.execute(
        """
        DELETE FROM negocial.producao_gamma gamma
        USING negocial.producao_registros pr
        WHERE pr.id = gamma.producao_id
          AND upper(coalesce(pr.carteira, '')) = 'BETA'
        """
    )

    op.execute("DROP VIEW IF EXISTS negocial.producao_diaria_unificada")
    op.execute("DROP VIEW IF EXISTS negocial.producao_unificada")
    op.execute(
        """
        CREATE VIEW negocial.producao_unificada AS
        SELECT
            pr.id,
            pr.data_acordo,
            COALESCE(it.debit_id, rt.suitid, gamma.npj, dyn.identificador, '') AS npj,
            it.cpf,
            pr.cliente,
            COALESCE(gamma.gecor, '') AS gecor,
            NULL::INTEGER AS dias_atraso,
            it.data_primeiro_atraso,
            it.portfolio,
            it.carteira_alpha,
            pr.valor_total_acordo,
            pr.valor_entrada,
            COALESCE(gamma.valor_ho, 0) AS valor_ho,
            COALESCE(gamma.percentual_ho, 0) AS percentual_ho,
            pr.tipo_acordo,
            pr.data_vencimento,
            pr.data_pagamento,
            pr.status,
            pr.justificativa_status,
            COALESCE(gamma.autorizacao_flexibilizacao, 'NAO') AS autorizacao_flexibilizacao,
            pr.carteira,
            pr.user_id,
            pr.created_at,
            pr.updated_at
        FROM negocial.producao_registros pr
        LEFT JOIN negocial.producao_gamma gamma ON gamma.producao_id = pr.id
        LEFT JOIN negocial.producao_alpha it ON it.producao_id = pr.id
        LEFT JOIN negocial.producao_beta rt ON rt.producao_id = pr.id
        LEFT JOIN LATERAL (
            SELECT pc.valor_texto AS identificador
            FROM negocial.producao_campos pc
            JOIN negocial.carteira_colunas cc ON cc.id = pc.coluna_id
            WHERE pc.producao_id = pr.id
              AND cc.identificador = TRUE
            ORDER BY cc.ordem, cc.id
            LIMIT 1
        ) dyn ON TRUE
        """
    )
    op.execute(
        """
        INSERT INTO negocial.schema_migrations_meta (revision, description)
        VALUES ('20260707_0002', 'Separacao da carteira Beta e campos dinamicos')
        ON CONFLICT (revision) DO NOTHING
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DELETE FROM negocial.schema_migrations_meta WHERE revision = '20260707_0002'")
    op.execute("DROP VIEW IF EXISTS negocial.producao_unificada")
    op.execute("DROP TABLE IF EXISTS negocial.producao_beta")
