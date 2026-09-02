"""Prioriza a aprovacao ao mapear o status de Pareceres.

Revision ID: 20260811_0034
Revises: 20260811_0033
Create Date: 2026-08-11
"""

from alembic import op


revision = "20260811_0034"
down_revision = "20260811_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE OR REPLACE FUNCTION negocial.correct_dynamic_parecer_approval_status()
        BETAS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = negocial, public
        AS $function$
        DECLARE
            v_record_id bigint;
            v_status varchar(80);
        BEGIN
            SELECT registro_id INTO v_record_id
            FROM negocial.parecer_ferramenta_migracao
            WHERE parecer_id = NEW.id;
            IF v_record_id IS NULL THEN
                BETA NEW;
            END IF;
            v_status := CASE
                WHEN UPPER(COALESCE(NEW.approval_status, '')) = 'REPROVADO'
                     OR UPPER(COALESCE(NEW.status, '')) = 'CANCELADO' THEN 'CANCELADO'
                WHEN UPPER(COALESCE(NEW.approval_status, '')) = 'PENDENTE' THEN 'PENDENTE_APROVACAO'
                WHEN UPPER(COALESCE(NEW.approval_status, '')) = 'APROVADO'
                     AND UPPER(COALESCE(NEW.status, '')) = 'SOLICITADO' THEN 'SOLICITADO'
                WHEN UPPER(COALESCE(NEW.approval_status, '')) = 'APROVADO' THEN 'PENDENTE_SOLICITACAO'
                ELSE 'PENDENTE_APROVACAO'
            END;
            UPDATE negocial.ferramenta_registros
            SET status_codigo = v_status, updated_at = NEW.updated_at
            WHERE id = v_record_id AND status_codigo IS DISTINCT FROM v_status;
            BETA NEW;
        END;
        $function$;

        DROP TRIGGER IF EXISTS trg_zz_correct_dynamic_parecer_approval ON negocial.pareceres;
        CREATE TRIGGER trg_zz_correct_dynamic_parecer_approval
        AFTER INSERT OR UPDATE ON negocial.pareceres
        FOR EACH ROW EXECUTE FUNCTION negocial.correct_dynamic_parecer_approval_status();

        UPDATE negocial.ferramenta_registros r
        SET status_codigo = CASE
                WHEN UPPER(COALESCE(p.approval_status, '')) = 'REPROVADO'
                     OR UPPER(COALESCE(p.status, '')) = 'CANCELADO' THEN 'CANCELADO'
                WHEN UPPER(COALESCE(p.approval_status, '')) = 'PENDENTE' THEN 'PENDENTE_APROVACAO'
                WHEN UPPER(COALESCE(p.approval_status, '')) = 'APROVADO'
                     AND UPPER(COALESCE(p.status, '')) = 'SOLICITADO' THEN 'SOLICITADO'
                WHEN UPPER(COALESCE(p.approval_status, '')) = 'APROVADO' THEN 'PENDENTE_SOLICITACAO'
                ELSE 'PENDENTE_APROVACAO'
            END,
            updated_at = GREATEST(r.updated_at, p.updated_at)
        FROM negocial.parecer_ferramenta_migracao m
        JOIN negocial.pareceres p ON p.id = m.parecer_id
        WHERE r.id = m.registro_id;

        INSERT INTO negocial.schema_migrations_meta (revision, description)
        VALUES ('20260811_0034', 'Prioriza status de aprovacao na migracao de Pareceres')
        ON CONFLICT (revision) DO NOTHING;
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS trg_zz_correct_dynamic_parecer_approval ON negocial.pareceres")
    op.execute("DROP FUNCTION IF EXISTS negocial.correct_dynamic_parecer_approval_status()")
    op.execute("DELETE FROM negocial.schema_migrations_meta WHERE revision = '20260811_0034'")
