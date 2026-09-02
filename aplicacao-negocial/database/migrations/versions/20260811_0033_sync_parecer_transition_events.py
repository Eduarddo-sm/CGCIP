"""Espelha justificativas e datas das transicoes de Pareceres.

Revision ID: 20260811_0033
Revises: 20260811_0032
Create Date: 2026-08-11
"""

from alembic import op


revision = "20260811_0033"
down_revision = "20260811_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE OR REPLACE FUNCTION negocial.sync_parecer_transition_event()
        BETAS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = negocial, public
        AS $function$
        DECLARE
            v_parecer_id bigint;
            v_slug varchar(120);
        BEGIN
            IF NEW.tipo <> 'TRANSICAO' THEN
                BETA NEW;
            END IF;
            SELECT f.slug INTO v_slug
            FROM negocial.ferramenta_registros r
            JOIN negocial.ferramentas f ON f.id = r.ferramenta_id
            WHERE r.id = NEW.registro_id;
            IF v_slug IS DISTINCT FROM 'pareceres' THEN
                BETA NEW;
            END IF;
            SELECT parecer_id INTO v_parecer_id
            FROM negocial.parecer_ferramenta_migracao
            WHERE registro_id = NEW.registro_id;
            IF v_parecer_id IS NULL THEN
                BETA NEW;
            END IF;

            UPDATE negocial.pareceres
            SET approval_reason = CASE
                    WHEN NEW.status_novo IN ('PENDENTE_SOLICITACAO', 'CANCELADO')
                    THEN COALESCE(NULLIF(BTRIM(NEW.justificativa), ''), approval_reason)
                    ELSE approval_reason
                END,
                approval_decided_at = CASE
                    WHEN NEW.status_novo IN ('PENDENTE_SOLICITACAO', 'CANCELADO')
                    THEN NEW.created_at ELSE approval_decided_at
                END,
                requested_at = CASE
                    WHEN NEW.status_novo = 'SOLICITADO' THEN NEW.created_at ELSE requested_at
                END,
                data_conclusao = CASE
                    WHEN NEW.status_novo IN ('SOLICITADO', 'CANCELADO') THEN NEW.created_at::date
                    ELSE data_conclusao
                END,
                updated_at = NEW.created_at
            WHERE id = v_parecer_id;
            BETA NEW;
        END;
        $function$;

        DROP TRIGGER IF EXISTS trg_sync_parecer_transition_event ON negocial.ferramenta_eventos;
        CREATE TRIGGER trg_sync_parecer_transition_event
        AFTER INSERT ON negocial.ferramenta_eventos
        FOR EACH ROW EXECUTE FUNCTION negocial.sync_parecer_transition_event();

        INSERT INTO negocial.schema_migrations_meta (revision, description)
        VALUES ('20260811_0033', 'Espelha eventos de transicao da ferramenta Pareceres')
        ON CONFLICT (revision) DO NOTHING;
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS trg_sync_parecer_transition_event ON negocial.ferramenta_eventos")
    op.execute("DROP FUNCTION IF EXISTS negocial.sync_parecer_transition_event()")
    op.execute("DELETE FROM negocial.schema_migrations_meta WHERE revision = '20260811_0033'")
