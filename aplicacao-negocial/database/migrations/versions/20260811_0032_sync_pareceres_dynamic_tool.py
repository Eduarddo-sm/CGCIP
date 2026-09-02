"""Sincroniza Pareceres legado com a ferramenta dinamica oficial.

Revision ID: 20260811_0032
Revises: 20260811_0031
Create Date: 2026-08-11
"""

from alembic import op


revision = "20260811_0032"
down_revision = "20260811_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        CREATE OR REPLACE FUNCTION negocial.sync_parecer_to_dynamic()
        BETAS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = negocial, public
        AS $function$
        DECLARE
            v_tool_id integer;
            v_version_id integer;
            v_record_id bigint;
            v_username varchar(80);
            v_dynamic_status varchar(80);
        BEGIN
            IF pg_trigger_depth() > 1 THEN
                BETA NEW;
            END IF;

            SELECT f.id, v.id INTO v_tool_id, v_version_id
            FROM negocial.ferramentas f
            JOIN negocial.ferramenta_versoes v
              ON v.ferramenta_id = f.id AND v.status = 'PUBLICADA'
            WHERE f.slug = 'pareceres'
            ORDER BY v.numero DESC
            LIMIT 1;
            SELECT username INTO v_username FROM negocial.users WHERE id = NEW.user_id;

            v_dynamic_status := CASE
                WHEN UPPER(COALESCE(NEW.approval_status, '')) = 'REPROVADO'
                     OR UPPER(COALESCE(NEW.status, '')) = 'CANCELADO' THEN 'CANCELADO'
                WHEN UPPER(COALESCE(NEW.status, '')) = 'SOLICITADO' THEN 'SOLICITADO'
                WHEN UPPER(COALESCE(NEW.approval_status, '')) = 'APROVADO' THEN 'PENDENTE_SOLICITACAO'
                ELSE 'PENDENTE_APROVACAO'
            END;

            SELECT registro_id INTO v_record_id
            FROM negocial.parecer_ferramenta_migracao
            WHERE parecer_id = NEW.id;

            IF v_record_id IS NULL THEN
                INSERT INTO negocial.ferramenta_registros
                    (ferramenta_id, versao_id, owner_user_id, owner_username, carteira,
                     status_codigo, titulo, payload_json, active, created_at, updated_at)
                VALUES
                    (v_tool_id, v_version_id, NEW.user_id, v_username, NEW.carteira,
                     v_dynamic_status, NEW.cliente,
                     jsonb_strip_nulls(jsonb_build_object(
                        'DATA_SOLICITACAO', NEW.data_solicitacao,
                        'NPJ', NEW.npj, 'CLIENTE', NEW.cliente, 'MOTIVO', NEW.motivo,
                        'DESCRICAO', NEW.descricao, 'NEGOCIADOR', v_username,
                        'CARTEIRA', NEW.carteira,
                        'JUSTIFICATIVA_DECISAO', NEW.approval_reason,
                        'DATA_DECISAO', NEW.approval_decided_at::date,
                        'DATA_SOLICITADO', NEW.requested_at::date,
                        '_LEGACY_PARECER_ID', NEW.id
                     )), TRUE, NEW.created_at, NEW.updated_at)
                RETURNING id INTO v_record_id;

                INSERT INTO negocial.parecer_ferramenta_migracao (parecer_id, registro_id)
                VALUES (NEW.id, v_record_id)
                ON CONFLICT (parecer_id) DO UPDATE SET registro_id = EXCLUDED.registro_id;
            ELSE
                UPDATE negocial.ferramenta_registros
                SET owner_user_id = NEW.user_id,
                    owner_username = v_username,
                    carteira = NEW.carteira,
                    status_codigo = v_dynamic_status,
                    titulo = NEW.cliente,
                    payload_json = jsonb_strip_nulls(jsonb_build_object(
                        'DATA_SOLICITACAO', NEW.data_solicitacao,
                        'NPJ', NEW.npj, 'CLIENTE', NEW.cliente, 'MOTIVO', NEW.motivo,
                        'DESCRICAO', NEW.descricao, 'NEGOCIADOR', v_username,
                        'CARTEIRA', NEW.carteira,
                        'JUSTIFICATIVA_DECISAO', NEW.approval_reason,
                        'DATA_DECISAO', NEW.approval_decided_at::date,
                        'DATA_SOLICITADO', NEW.requested_at::date,
                        '_LEGACY_PARECER_ID', NEW.id
                    )),
                    updated_at = NEW.updated_at
                WHERE id = v_record_id;
            END IF;
            BETA NEW;
        END;
        $function$;

        CREATE OR REPLACE FUNCTION negocial.sync_dynamic_to_parecer()
        BETAS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = negocial, public
        AS $function$
        DECLARE
            v_slug varchar(120);
            v_parecer_id bigint;
            v_legacy_status varchar(30);
            v_approval_status varchar(30);
            v_user_id bigint;
        BEGIN
            IF pg_trigger_depth() > 1 THEN
                BETA NEW;
            END IF;
            SELECT slug INTO v_slug FROM negocial.ferramentas WHERE id = NEW.ferramenta_id;
            IF v_slug IS DISTINCT FROM 'pareceres' THEN
                BETA NEW;
            END IF;

            SELECT parecer_id INTO v_parecer_id
            FROM negocial.parecer_ferramenta_migracao
            WHERE registro_id = NEW.id;
            v_user_id := COALESCE(NEW.owner_user_id,
                (SELECT id FROM negocial.users WHERE username = NEW.owner_username LIMIT 1));
            v_legacy_status := CASE
                WHEN NEW.status_codigo = 'SOLICITADO' THEN 'SOLICITADO'
                WHEN NEW.status_codigo = 'CANCELADO' THEN 'CANCELADO'
                ELSE 'PENDENTE'
            END;
            v_approval_status := CASE
                WHEN NEW.status_codigo IN ('PENDENTE_SOLICITACAO', 'SOLICITADO') THEN 'APROVADO'
                WHEN NEW.status_codigo = 'CANCELADO' THEN 'REPROVADO'
                ELSE 'PENDENTE'
            END;

            IF v_parecer_id IS NULL THEN
                INSERT INTO negocial.pareceres
                    (data_solicitacao, data_conclusao, npj, cliente, motivo, descricao,
                     status, carteira, user_id, created_at, updated_at, approval_status,
                     approval_reason, requested_at, approval_decided_at)
                VALUES
                    (COALESCE(NULLIF(NEW.payload_json->>'DATA_SOLICITACAO', '')::date, CURRENT_DATE),
                     CASE WHEN NEW.status_codigo IN ('SOLICITADO', 'CANCELADO') THEN NEW.updated_at::date END,
                     COALESCE(NEW.payload_json->>'NPJ', ''), COALESCE(NEW.payload_json->>'CLIENTE', NEW.titulo, ''),
                     COALESCE(NEW.payload_json->>'MOTIVO', 'PARECER'), COALESCE(NEW.payload_json->>'DESCRICAO', ''),
                     v_legacy_status, COALESCE(NEW.carteira, NEW.payload_json->>'CARTEIRA', ''),
                     v_user_id, NEW.created_at, NEW.updated_at, v_approval_status,
                     NULLIF(NEW.payload_json->>'JUSTIFICATIVA_DECISAO', ''),
                     NULLIF(NEW.payload_json->>'DATA_SOLICITADO', '')::date,
                     NULLIF(NEW.payload_json->>'DATA_DECISAO', '')::date)
                RETURNING id INTO v_parecer_id;
                INSERT INTO negocial.parecer_ferramenta_migracao (parecer_id, registro_id)
                VALUES (v_parecer_id, NEW.id);
                UPDATE negocial.ferramenta_registros
                SET payload_json = payload_json || jsonb_build_object('_LEGACY_PARECER_ID', v_parecer_id)
                WHERE id = NEW.id;
            ELSE
                UPDATE negocial.pareceres
                SET data_solicitacao = COALESCE(NULLIF(NEW.payload_json->>'DATA_SOLICITACAO', '')::date, data_solicitacao),
                    data_conclusao = CASE WHEN NEW.status_codigo IN ('SOLICITADO', 'CANCELADO') THEN NEW.updated_at::date ELSE NULL END,
                    npj = COALESCE(NEW.payload_json->>'NPJ', npj),
                    cliente = COALESCE(NEW.payload_json->>'CLIENTE', NEW.titulo, cliente),
                    motivo = COALESCE(NEW.payload_json->>'MOTIVO', motivo),
                    descricao = COALESCE(NEW.payload_json->>'DESCRICAO', descricao),
                    status = v_legacy_status,
                    carteira = COALESCE(NEW.carteira, NEW.payload_json->>'CARTEIRA', carteira),
                    user_id = COALESCE(v_user_id, user_id),
                    updated_at = NEW.updated_at,
                    approval_status = v_approval_status,
                    approval_reason = COALESCE(NULLIF(NEW.payload_json->>'JUSTIFICATIVA_DECISAO', ''), approval_reason),
                    requested_at = COALESCE(NULLIF(NEW.payload_json->>'DATA_SOLICITADO', '')::date, requested_at),
                    approval_decided_at = COALESCE(NULLIF(NEW.payload_json->>'DATA_DECISAO', '')::date, approval_decided_at)
                WHERE id = v_parecer_id;
            END IF;
            BETA NEW;
        END;
        $function$;

        DROP TRIGGER IF EXISTS trg_sync_parecer_to_dynamic ON negocial.pareceres;
        CREATE TRIGGER trg_sync_parecer_to_dynamic
        AFTER INSERT OR UPDATE ON negocial.pareceres
        FOR EACH ROW EXECUTE FUNCTION negocial.sync_parecer_to_dynamic();

        DROP TRIGGER IF EXISTS trg_sync_dynamic_to_parecer ON negocial.ferramenta_registros;
        CREATE TRIGGER trg_sync_dynamic_to_parecer
        AFTER INSERT OR UPDATE ON negocial.ferramenta_registros
        FOR EACH ROW EXECUTE FUNCTION negocial.sync_dynamic_to_parecer();
        """
    )
    op.execute(
        """
        INSERT INTO negocial.schema_migrations_meta (revision, description)
        VALUES ('20260811_0032', 'Sincronizacao bidirecional temporaria de Pareceres')
        ON CONFLICT (revision) DO NOTHING
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS trg_sync_dynamic_to_parecer ON negocial.ferramenta_registros")
    op.execute("DROP TRIGGER IF EXISTS trg_sync_parecer_to_dynamic ON negocial.pareceres")
    op.execute("DROP FUNCTION IF EXISTS negocial.sync_dynamic_to_parecer()")
    op.execute("DROP FUNCTION IF EXISTS negocial.sync_parecer_to_dynamic()")
    op.execute("DELETE FROM negocial.schema_migrations_meta WHERE revision = '20260811_0032'")
