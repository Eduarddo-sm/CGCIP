"""Remove legado de producao diaria e otimiza indices.

Revision ID: 20260707_0003
Revises: 20260707_0002
Create Date: 2026-07-07
"""

from __future__ import annotations

from alembic import op


revision = "20260707_0003"
down_revision = "20260707_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DROP TABLE IF EXISTS negocial.producao_diaria_legacy")
    op.execute("DROP TABLE IF EXISTS negocial.producao_diaria")

    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_producao_registros_data_acordo ON negocial.producao_registros (data_acordo)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_producao_registros_carteira_data ON negocial.producao_registros (carteira, data_acordo)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_producao_registros_user_data ON negocial.producao_registros (user_id, data_acordo)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_producao_registros_updated_at ON negocial.producao_registros (updated_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_producao_campos_coluna_texto ON negocial.producao_campos (coluna_id, valor_texto)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_producao_campos_valor_data ON negocial.producao_campos (valor_data)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_pareceres_status_approval ON negocial.pareceres (status, approval_status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_negocial_sessions_user_revoked ON negocial.sessions (user_id, revoked_at)")

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_negocial_producao_registros_status'
            ) THEN
                ALTER TABLE negocial.producao_registros
                ADD CONSTRAINT ck_negocial_producao_registros_status
                CHECK (status IN (
                    'PROPOSTA',
                    'AGUARDANDO_PAGAMENTO',
                    'PAGAMENTO_REALIZADO',
                    'PROPOSTA_NEGADA',
                    'QUEBRA'
                ));
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_negocial_carteira_colunas_tipo'
            ) THEN
                ALTER TABLE negocial.carteira_colunas
                ADD CONSTRAINT ck_negocial_carteira_colunas_tipo
                CHECK (tipo IN ('texto', 'numero', 'moeda', 'data', 'select', 'boolean'));
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        INSERT INTO negocial.schema_migrations_meta (revision, description)
        VALUES ('20260707_0003', 'Remove legado producao_diaria e adiciona indices/constraints')
        ON CONFLICT (revision) DO NOTHING
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DELETE FROM negocial.schema_migrations_meta WHERE revision = '20260707_0003'")
    op.execute("DROP INDEX IF EXISTS negocial.ix_negocial_sessions_user_revoked")
    op.execute("DROP INDEX IF EXISTS negocial.ix_negocial_pareceres_status_approval")
    op.execute("DROP INDEX IF EXISTS negocial.ix_negocial_producao_campos_valor_data")
    op.execute("DROP INDEX IF EXISTS negocial.ix_negocial_producao_campos_coluna_texto")
    op.execute("DROP INDEX IF EXISTS negocial.ix_negocial_producao_registros_updated_at")
    op.execute("DROP INDEX IF EXISTS negocial.ix_negocial_producao_registros_user_data")
    op.execute("DROP INDEX IF EXISTS negocial.ix_negocial_producao_registros_carteira_data")
    op.execute("DROP INDEX IF EXISTS negocial.ix_negocial_producao_registros_data_acordo")
    op.execute("ALTER TABLE negocial.carteira_colunas DROP CONSTRAINT IF EXISTS ck_negocial_carteira_colunas_tipo")
    op.execute("ALTER TABLE negocial.producao_registros DROP CONSTRAINT IF EXISTS ck_negocial_producao_registros_status")
