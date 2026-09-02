"""Preserva o status historico de aguardando levantamento.

Revision ID: 20260722_0014
Revises: 20260722_0013
Create Date: 2026-07-22
"""
from __future__ import annotations

from alembic import op


revision = "20260722_0014"
down_revision = "20260722_0013"
branch_labels = None
depends_on = None


STATUSES = (
    "PROPOSTA",
    "AGUARDANDO_PAGAMENTO",
    "PAGAMENTO_REALIZADO",
    "AGUARDANDO_LEVANTAMENTO",
    "PROPOSTA_NEGADA",
    "QUEBRA",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    allowed = ", ".join(f"'{status}'" for status in STATUSES)
    op.execute("ALTER TABLE negocial.producao_registros DROP CONSTRAINT IF EXISTS ck_negocial_producao_registros_status")
    op.execute(
        f"ALTER TABLE negocial.producao_registros ADD CONSTRAINT ck_negocial_producao_registros_status CHECK (status IN ({allowed}))"
    )
    op.execute(
        """
        INSERT INTO negocial.schema_migrations_meta (revision, description)
        VALUES ('20260722_0014', 'Preserva status historico de aguardando levantamento')
        ON CONFLICT (revision) DO NOTHING
        """
    )


def downgrade() -> None:
    # O status historico pode estar em uso e nao deve ser invalidado.
    pass
