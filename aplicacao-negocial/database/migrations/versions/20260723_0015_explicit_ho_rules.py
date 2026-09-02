"""Cria vinculos explicitos para regras de honorarios.

Revision ID: 20260723_0015
Revises: 20260722_0014
Create Date: 2026-07-23
"""

from __future__ import annotations

from alembic import op


revision = "20260723_0015"
down_revision = "20260722_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS negocial.carteira_regras_calculo (
            id SERIAL PRIMARY KEY,
            carteira_id INTEGER NOT NULL
                REFERENCES negocial.carteiras_negociais(id) ON DELETE CASCADE,
            codigo VARCHAR(60) NOT NULL DEFAULT 'HONORARIOS',
            nome VARCHAR(120) NOT NULL DEFAULT 'Honorarios',
            tipo_calculo VARCHAR(30) NOT NULL DEFAULT 'percentual',
            coluna_base_id INTEGER
                REFERENCES negocial.carteira_colunas(id) ON DELETE SET NULL,
            coluna_destino_id INTEGER
                REFERENCES negocial.carteira_colunas(id) ON DELETE SET NULL,
            coluna_valor_recebido_id INTEGER
                REFERENCES negocial.carteira_colunas(id) ON DELETE SET NULL,
            coluna_percentual_efetivo_id INTEGER
                REFERENCES negocial.carteira_colunas(id) ON DELETE SET NULL,
            percentual_padrao NUMERIC(8, 4),
            percentual_minimo NUMERIC(8, 4),
            percentual_maximo NUMERIC(8, 4),
            automatico BOOLEAN NOT NULL DEFAULT FALSE,
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            casas_decimais INTEGER NOT NULL DEFAULT 2,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_carteira_regra_calculo_codigo UNIQUE (carteira_id, codigo),
            CONSTRAINT ck_carteira_regra_calculo_tipo
                CHECK (tipo_calculo IN ('percentual')),
            CONSTRAINT ck_carteira_regra_calculo_percentuais
                CHECK (
                    (percentual_padrao IS NULL OR percentual_padrao BETWEEN 0 AND 100)
                    AND (percentual_minimo IS NULL OR percentual_minimo BETWEEN 0 AND 100)
                    AND (percentual_maximo IS NULL OR percentual_maximo BETWEEN 0 AND 100)
                    AND (
                        percentual_minimo IS NULL
                        OR percentual_maximo IS NULL
                        OR percentual_minimo <= percentual_maximo
                    )
                ),
            CONSTRAINT ck_carteira_regra_calculo_casas
                CHECK (casas_decimais BETWEEN 0 AND 6)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_carteira_regras_calculo_carteira "
        "ON negocial.carteira_regras_calculo(carteira_id)"
    )

    # Migra as configuracoes existentes sem depender apenas de nomes no runtime.
    op.execute(
        """
        INSERT INTO negocial.carteira_regras_calculo (
            carteira_id, codigo, nome, tipo_calculo,
            coluna_base_id, coluna_destino_id,
            coluna_valor_recebido_id, coluna_percentual_efetivo_id,
            percentual_padrao, percentual_minimo, percentual_maximo,
            automatico, ativo, casas_decimais
        )
        SELECT
            wallet.id,
            'HONORARIOS',
            'Honorarios',
            'percentual',
            base.id,
            destination.id,
            received.id,
            effective.id,
            wallet.percentual_ho_padrao,
            wallet.percentual_ho_minimo,
            wallet.percentual_ho_maximo,
            wallet.calculo_automatico_ho,
            wallet.usa_percentual_ho,
            2
        FROM negocial.carteiras_negociais wallet
        LEFT JOIN LATERAL (
            SELECT column_def.id
            FROM negocial.carteira_colunas column_def
            WHERE column_def.carteira_id = wallet.id
              AND column_def.tipo IN ('moeda', 'numero')
              AND (
                    (wallet.slug = 'GAMMA' AND column_def.chave = 'VALOR_DO_ACORDO')
                 OR (wallet.slug = 'BETA' AND column_def.chave = 'VALOR_TOTAL_DE_ACORDO')
                 OR (wallet.slug = 'CAIXA' AND column_def.chave = 'VALOR_FECHADO')
                 OR column_def.chave IN (
                        'VALOR_DO_ACORDO', 'VALOR_TOTAL_DE_ACORDO',
                        'VALOR_TOTAL', 'VALOR_FECHADO'
                    )
              )
            ORDER BY
                CASE
                    WHEN wallet.slug = 'GAMMA' AND column_def.chave = 'VALOR_DO_ACORDO' THEN 0
                    WHEN wallet.slug = 'BETA' AND column_def.chave = 'VALOR_TOTAL_DE_ACORDO' THEN 0
                    WHEN wallet.slug = 'CAIXA' AND column_def.chave = 'VALOR_FECHADO' THEN 0
                    ELSE 1
                END,
                column_def.ordem,
                column_def.id
            LIMIT 1
        ) base ON TRUE
        LEFT JOIN LATERAL (
            SELECT column_def.id
            FROM negocial.carteira_colunas column_def
            WHERE column_def.carteira_id = wallet.id
              AND column_def.tipo IN ('moeda', 'numero')
              AND column_def.chave IN ('HONOR_RIOS', 'HONORARIOS', 'H_O', 'HO', 'VALOR_HO')
            ORDER BY
                CASE WHEN column_def.chave IN ('HONOR_RIOS', 'HONORARIOS') THEN 0 ELSE 1 END,
                column_def.ordem,
                column_def.id
            LIMIT 1
        ) destination ON TRUE
        LEFT JOIN LATERAL (
            SELECT column_def.id
            FROM negocial.carteira_colunas column_def
            WHERE column_def.carteira_id = wallet.id
              AND column_def.chave IN ('HONOR_RIOS_RECEBIDOS', 'HONORARIOS_RECEBIDOS')
            ORDER BY column_def.ordem, column_def.id
            LIMIT 1
        ) received ON TRUE
        LEFT JOIN LATERAL (
            SELECT column_def.id
            FROM negocial.carteira_colunas column_def
            WHERE column_def.carteira_id = wallet.id
              AND column_def.chave IN ('PERCENTUAL', 'PERCENTUAL_HO')
            ORDER BY column_def.ordem, column_def.id
            LIMIT 1
        ) effective ON TRUE
        WHERE wallet.usa_percentual_ho = TRUE
        ON CONFLICT (carteira_id, codigo) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO negocial.schema_migrations_meta (revision, description)
        VALUES ('20260723_0015', 'Vincula explicitamente base, destino e percentual das regras de H.O')
        ON CONFLICT (revision) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS negocial.carteira_regras_calculo")
