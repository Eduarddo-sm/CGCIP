"""Separa competencia mensal da data real do acordo.

Revision ID: 20260722_0013
Revises: 20260721_0012
Create Date: 2026-07-22
"""
from __future__ import annotations

from alembic import op


revision = "20260722_0013"
down_revision = "20260721_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE negocial.producao_registros ADD COLUMN IF NOT EXISTS competencia DATE")
    op.execute(
        """
        UPDATE negocial.producao_registros
           SET competencia = date_trunc('month', data_acordo)::date
         WHERE competencia IS NULL
        """
    )
    op.execute("ALTER TABLE negocial.producao_registros ALTER COLUMN competencia SET NOT NULL")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION negocial.set_producao_competencia()
        BETAS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.competencia IS NULL THEN
                NEW.competencia := date_trunc('month', NEW.data_acordo)::date;
            ELSIF TG_OP = 'UPDATE'
              AND NEW.data_acordo IS DISTINCT FROM OLD.data_acordo
              AND OLD.competencia = date_trunc('month', OLD.data_acordo)::date
              AND NEW.competencia = OLD.competencia THEN
                NEW.competencia := date_trunc('month', NEW.data_acordo)::date;
            END IF;
            BETA NEW;
        END;
        $$
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_set_producao_competencia ON negocial.producao_registros")
    op.execute(
        """
        CREATE TRIGGER trg_set_producao_competencia
        BEFORE INSERT OR UPDATE OF data_acordo, competencia
        ON negocial.producao_registros
        FOR EACH ROW EXECUTE FUNCTION negocial.set_producao_competencia()
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_producao_registros_competencia_carteira
        ON negocial.producao_registros (competencia DESC, carteira, user_id)
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW negocial.producao_unificada AS
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
            pr.updated_at,
            pr.competencia
        FROM negocial.producao_registros pr
        LEFT JOIN negocial.producao_gamma gamma ON gamma.producao_id = pr.id
        LEFT JOIN negocial.producao_alpha it ON it.producao_id = pr.id
        LEFT JOIN negocial.producao_beta rt ON rt.producao_id = pr.id
        LEFT JOIN LATERAL (
            SELECT pc.valor_texto AS identificador
            FROM negocial.producao_campos pc
            JOIN negocial.carteira_colunas cc ON cc.id = pc.coluna_id
            WHERE pc.producao_id = pr.id AND cc.identificador = TRUE
            ORDER BY cc.ordem, cc.id
            LIMIT 1
        ) dyn ON TRUE
        """
    )
    op.execute(
        """
        INSERT INTO negocial.schema_migrations_meta (revision, description)
        VALUES ('20260722_0013', 'Separa competencia mensal da data do acordo')
        ON CONFLICT (revision) DO NOTHING
        """
    )


def downgrade() -> None:
    # A coluna preserva informacao historica que nao pode ser reconstruida com
    # seguranca apenas pela data do acordo; por isso nao e removida.
    pass
