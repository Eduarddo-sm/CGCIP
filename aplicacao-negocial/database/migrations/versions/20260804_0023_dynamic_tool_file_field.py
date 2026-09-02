"""Permite campos de anexo nas ferramentas dinamicas.

Revision ID: 20260804_0023
Revises: 20260804_0022
Create Date: 2026-08-04
"""

from alembic import op


revision = "20260804_0023"
down_revision = "20260804_0022"
branch_labels = None
depends_on = None


FIELD_TYPES = (
    "'texto', 'texto_longo', 'numero', 'moeda', 'data', "
    "'select', 'multiselect', 'boolean', 'usuario', 'carteira', 'arquivo'"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        f"""
        ALTER TABLE negocial.ferramenta_campos
            DROP CONSTRAINT IF EXISTS ck_ferramenta_campo_tipo;
        ALTER TABLE negocial.ferramenta_campos
            ADD CONSTRAINT ck_ferramenta_campo_tipo
            CHECK (tipo IN ({FIELD_TYPES}));
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "UPDATE negocial.ferramenta_campos SET tipo = 'texto' WHERE tipo = 'arquivo'"
    )
    op.execute(
        """
        ALTER TABLE negocial.ferramenta_campos
            DROP CONSTRAINT IF EXISTS ck_ferramenta_campo_tipo;
        ALTER TABLE negocial.ferramenta_campos
            ADD CONSTRAINT ck_ferramenta_campo_tipo
            CHECK (
                tipo IN (
                    'texto', 'texto_longo', 'numero', 'moeda', 'data',
                    'select', 'multiselect', 'boolean', 'usuario', 'carteira'
                )
            );
        """
    )
