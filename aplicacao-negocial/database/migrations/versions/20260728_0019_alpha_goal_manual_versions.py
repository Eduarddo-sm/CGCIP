"""Versionamento manual das metas de portfolio da Alpha.

Revision ID: 20260728_0019
Revises: 20260728_0018
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op


revision = "20260728_0019"
down_revision = "20260728_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        ALTER TABLE negocial.alpha_portfolio_goals
            ADD COLUMN IF NOT EXISTS supersedes_goal_id BIGINT
                REFERENCES negocial.alpha_portfolio_goals(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS adjustment_reason TEXT,
            ADD COLUMN IF NOT EXISTS created_by VARCHAR(80)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_alpha_goal_supersedes
        ON negocial.alpha_portfolio_goals(supersedes_goal_id)
        """
    )
    op.execute(
        """
        ALTER TABLE negocial.alpha_portfolio_goals
            DROP CONSTRAINT IF EXISTS ck_alpha_goal_manual_metadata
        """
    )
    op.execute(
        """
        ALTER TABLE negocial.alpha_portfolio_goals
            ADD CONSTRAINT ck_alpha_goal_manual_metadata
            CHECK (
                source_type <> 'MANUAL'
                OR (
                    supersedes_goal_id IS NOT NULL
                    AND NULLIF(BTRIM(adjustment_reason), '') IS NOT NULL
                    AND NULLIF(BTRIM(created_by), '') IS NOT NULL
                )
            )
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        ALTER TABLE negocial.alpha_portfolio_goals
            DROP CONSTRAINT IF EXISTS ck_alpha_goal_manual_metadata
        """
    )
    op.execute("DROP INDEX IF EXISTS negocial.ix_alpha_goal_supersedes")
    op.execute(
        """
        ALTER TABLE negocial.alpha_portfolio_goals
            DROP COLUMN IF EXISTS created_by,
            DROP COLUMN IF EXISTS adjustment_reason,
            DROP COLUMN IF EXISTS supersedes_goal_id
        """
    )
