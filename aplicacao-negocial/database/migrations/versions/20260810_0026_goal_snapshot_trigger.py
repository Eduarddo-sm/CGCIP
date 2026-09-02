"""Congela automaticamente a meta ao criar producao em uma competencia.

Revision ID: 20260810_0026
Revises: 20260810_0025
Create Date: 2026-08-10
"""

from alembic import op


revision = "20260810_0026"
down_revision = "20260810_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION negocial.ensure_user_monthly_goal()
            BETAS trigger AS $$
            BEGIN
                IF NEW.user_id IS NOT NULL AND NEW.competencia IS NOT NULL THEN
                    INSERT INTO negocial.user_monthly_goals
                        (user_id, competencia, meta_pagamento, updated_by, created_at, updated_at)
                    SELECT NEW.user_id, NEW.competencia, COALESCE(u.meta_pagamento, 0),
                           'SISTEMA', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    FROM negocial.users u
                    WHERE u.id = NEW.user_id
                    ON CONFLICT (user_id, competencia) DO NOTHING;
                END IF;
                BETA NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_producao_monthly_goal
            BEFORE INSERT ON negocial.producao_registros
            FOR EACH ROW EXECUTE FUNCTION negocial.ensure_user_monthly_goal()
            """
        )
        return
    op.execute(
        """
        CREATE TRIGGER trg_producao_monthly_goal
        BEFORE INSERT ON producao_registros
        WHEN NEW.user_id IS NOT NULL AND NEW.competencia IS NOT NULL
        BEGIN
            INSERT OR IGNORE INTO user_monthly_goals
                (user_id, competencia, meta_pagamento, updated_by, created_at, updated_at)
            SELECT NEW.user_id, NEW.competencia, COALESCE(meta_pagamento, 0),
                   'SISTEMA', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM users WHERE id = NEW.user_id;
        END
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_producao_monthly_goal ON negocial.producao_registros")
        op.execute("DROP FUNCTION IF EXISTS negocial.ensure_user_monthly_goal()")
        return
    op.execute("DROP TRIGGER IF EXISTS trg_producao_monthly_goal")
