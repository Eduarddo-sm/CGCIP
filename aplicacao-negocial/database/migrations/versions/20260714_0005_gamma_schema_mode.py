"""Migra a carteira GAMMA para campos orientados por schema.

Revision ID: 20260714_0005
Revises: 20260713_0004
Create Date: 2026-07-14
"""

from __future__ import annotations

from alembic import op


revision = "20260714_0005"
down_revision = "20260713_0004"
branch_labels = None
depends_on = None


def _upsert_field(column_key: str, value_column: str, value_expression: str) -> None:
    empty_columns = {
        "valor_texto": "NULL",
        "valor_numero": "NULL",
        "valor_data": "NULL",
        "valor_json": "NULL",
    }
    empty_columns[value_column] = value_expression
    op.execute(
        f"""
        INSERT INTO negocial.producao_campos (
            producao_id, coluna_id, valor_texto, valor_numero, valor_data, valor_json, updated_at
        )
        SELECT p.id, cc.id,
               {empty_columns['valor_texto']},
               {empty_columns['valor_numero']},
               {empty_columns['valor_data']},
               {empty_columns['valor_json']},
               COALESCE(p.updated_at, NOW())
        FROM negocial.producao_registros p
        JOIN negocial.carteiras_negociais c ON c.slug = 'GAMMA'
        JOIN negocial.carteira_colunas cc ON cc.carteira_id = c.id AND cc.chave = '{column_key}'
        LEFT JOIN negocial.producao_gamma gamma ON gamma.producao_id = p.id
        LEFT JOIN negocial.producao_gamma_gerencial g ON g.producao_id = p.id
        LEFT JOIN negocial.users u ON u.id = p.user_id
        WHERE UPPER(COALESCE(p.carteira, '')) = 'GAMMA'
        ON CONFLICT (producao_id, coluna_id)
        DO UPDATE SET
            valor_texto = COALESCE(producao_campos.valor_texto, EXCLUDED.valor_texto),
            valor_numero = COALESCE(producao_campos.valor_numero, EXCLUDED.valor_numero),
            valor_data = COALESCE(producao_campos.valor_data, EXCLUDED.valor_data),
            valor_json = COALESCE(producao_campos.valor_json, EXCLUDED.valor_json),
            updated_at = GREATEST(producao_campos.updated_at, EXCLUDED.updated_at)
        """
    )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE negocial.carteiras_negociais ADD COLUMN IF NOT EXISTS modo_schema BOOLEAN DEFAULT TRUE NOT NULL")
    op.execute("UPDATE negocial.carteiras_negociais SET modo_schema = FALSE WHERE slug IN ('ALPHA', 'BETA')")
    op.execute("UPDATE negocial.carteiras_negociais SET modo_schema = TRUE WHERE slug = 'GAMMA'")

    op.execute(
        """
        UPDATE negocial.carteira_colunas cc
        SET tipo = rules.tipo,
            obrigatoria = rules.obrigatoria,
            automatico = rules.automatico,
            auto_tipo = rules.auto_tipo,
            max_length = rules.max_length,
            mostrar_cadastro = rules.mostrar_cadastro,
            cadastro_etapa = rules.cadastro_etapa,
            opcoes_json = rules.opcoes_json
        FROM negocial.carteiras_negociais c,
             (VALUES
                ('NPJ', 'texto', TRUE, FALSE, NULL, 14, TRUE, 1, '[]'),
                ('CLIENTE', 'texto', TRUE, FALSE, NULL, 180, TRUE, 1, '[]'),
                ('GECOR', 'texto', TRUE, FALSE, NULL, 4, TRUE, 1, '[]'),
                ('UF', 'texto', FALSE, FALSE, NULL, 2, FALSE, 2, '[]'),
                ('DT_AJUIZAMENTO', 'data', FALSE, FALSE, NULL, NULL, FALSE, 2, '[]'),
                ('DIAS_DE_ATRASO', 'numero', FALSE, TRUE, 'calculated', NULL, FALSE, 2, '[]'),
                ('VALOR_DO_ACORDO', 'moeda', TRUE, FALSE, NULL, NULL, TRUE, 2, '[]'),
                ('VALOR_DA_ENTRADA', 'moeda', FALSE, FALSE, NULL, NULL, TRUE, 2, '[]'),
                ('PARCELADO_OU_VISTA', 'select', TRUE, FALSE, NULL, NULL, TRUE, 1, '["A VISTA", "PARCELADO"]'),
                ('DATA_ACORDO', 'data', FALSE, TRUE, 'today', NULL, FALSE, 1, '[]'),
                ('DATA_DE_VENCIMENTO', 'data', TRUE, FALSE, NULL, NULL, TRUE, 2, '[]'),
                ('DATA_DO_PAGAMENTO', 'data', FALSE, FALSE, NULL, NULL, FALSE, 2, '[]'),
                ('STATUS', 'select', TRUE, FALSE, NULL, NULL, TRUE, 2, '["PROPOSTA", "AGUARDANDO_PAGAMENTO", "PAGAMENTO_REALIZADO", "PROPOSTA_NEGADA", "QUEBRA"]'),
                ('JUSTIFICATIVA', 'texto', FALSE, FALSE, NULL, 600, FALSE, 2, '[]'),
                ('NEGOCIADOR', 'texto', TRUE, TRUE, 'usuario', 80, FALSE, 2, '[]'),
                ('HONOR_RIOS', 'moeda', FALSE, TRUE, 'calculated', NULL, FALSE, 2, '[]'),
                ('HONOR_RIOS_RECEBIDOS', 'moeda', TRUE, FALSE, NULL, NULL, TRUE, 2, '[]'),
                ('PERCENTUAL', 'numero', FALSE, TRUE, 'calculated', NULL, FALSE, 2, '[]'),
                ('AUTORIZADO', 'texto', FALSE, FALSE, NULL, 80, FALSE, 2, '[]')
             ) AS rules(chave, tipo, obrigatoria, automatico, auto_tipo, max_length, mostrar_cadastro, cadastro_etapa, opcoes_json)
        WHERE c.slug = 'GAMMA'
          AND cc.carteira_id = c.id
          AND cc.chave = rules.chave
        """
    )

    _upsert_field("NPJ", "valor_texto", "COALESCE(gamma.npj, '')")
    _upsert_field("CLIENTE", "valor_texto", "COALESCE(p.cliente, '')")
    _upsert_field("GECOR", "valor_texto", "COALESCE(gamma.gecor, '')")
    _upsert_field("UF", "valor_texto", "COALESCE(g.uf, '')")
    _upsert_field("DT_AJUIZAMENTO", "valor_data", "g.data_ajuizamento")
    _upsert_field("DIAS_DE_ATRASO", "valor_numero", "CASE WHEN g.data_ajuizamento IS NULL THEN NULL ELSE GREATEST(CURRENT_DATE - g.data_ajuizamento, 0) END")
    _upsert_field("VALOR_DO_ACORDO", "valor_numero", "p.valor_total_acordo")
    _upsert_field("VALOR_DA_ENTRADA", "valor_numero", "p.valor_entrada")
    _upsert_field("PARCELADO_OU_VISTA", "valor_texto", "p.tipo_acordo")
    _upsert_field("DATA_ACORDO", "valor_data", "p.data_acordo")
    _upsert_field("DATA_DE_VENCIMENTO", "valor_data", "p.data_vencimento")
    _upsert_field("DATA_DO_PAGAMENTO", "valor_data", "p.data_pagamento")
    _upsert_field("STATUS", "valor_texto", "p.status")
    _upsert_field("JUSTIFICATIVA", "valor_texto", "COALESCE(p.justificativa_status, '')")
    _upsert_field("NEGOCIADOR", "valor_texto", "COALESCE(u.username, '')")
    _upsert_field("HONOR_RIOS", "valor_numero", "ROUND(COALESCE(p.valor_total_acordo, 0) * 0.10, 2)")
    _upsert_field("HONOR_RIOS_RECEBIDOS", "valor_numero", "COALESCE(gamma.valor_ho, 0)")
    _upsert_field("PERCENTUAL", "valor_numero", "COALESCE(gamma.percentual_ho, 0)")
    _upsert_field("AUTORIZADO", "valor_texto", "COALESCE(gamma.autorizacao_flexibilizacao, 'NAO')")

    op.execute(
        """
        UPDATE negocial.operational_versions
        SET version = version + 1, updated_at = NOW()
        WHERE scope IN ('producao', 'carteiras')
        """
    )


def downgrade() -> None:
    # Os dados copiados permanecem para garantir que downgrade nao cause perda.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("UPDATE negocial.carteiras_negociais SET modo_schema = FALSE WHERE slug = 'GAMMA'")
