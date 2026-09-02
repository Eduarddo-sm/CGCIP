"""Adiciona o status terminal de operacao recomprada.

Revision ID: 20260825_0035
Revises: 20260811_0034
Create Date: 2026-08-25
"""
from __future__ import annotations

import json

from alembic import op
from sqlalchemy import text


revision = "20260825_0035"
down_revision = "20260811_0034"
branch_labels = None
depends_on = None


STATUS_OPTIONS = [
    "PROPOSTA",
    "AGUARDANDO_PAGAMENTO",
    "PAGAMENTO_REALIZADO",
    "PROPOSTA_NEGADA",
    "OPERACAO_RECOMPRADA",
    "QUEBRA",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE negocial.producao_registros "
        "DROP CONSTRAINT IF EXISTS ck_negocial_producao_registros_status"
    )
    op.execute(
        """
        ALTER TABLE negocial.producao_registros
        ADD CONSTRAINT ck_negocial_producao_registros_status
        CHECK (status IN (
            'PROPOSTA', 'AGUARDANDO_PAGAMENTO', 'PAGAMENTO_REALIZADO',
            'AGUARDANDO_LEVANTAMENTO', 'PROPOSTA_NEGADA',
            'OPERACAO_RECOMPRADA', 'QUEBRA'
        ))
        """
    )
    row = bind.execute(
        text(
            """
            SELECT column_def.id, column_def.opcoes_json
            FROM negocial.carteira_colunas column_def
            JOIN negocial.carteiras_negociais wallet ON wallet.id = column_def.carteira_id
            WHERE upper(wallet.slug) = 'BETA' AND column_def.chave = 'STATUS'
            """
        )
    ).mappings().first()
    if row:
        options = json.loads(row["opcoes_json"] or "[]")
        for status in STATUS_OPTIONS:
            if status not in options:
                options.append(status)
        bind.execute(
            text("UPDATE negocial.carteira_colunas SET opcoes_json = :options WHERE id = :id"),
            {"options": json.dumps(options, ensure_ascii=False), "id": int(row["id"])},
        )


def downgrade() -> None:
    # Registros recompra nao podem ser convertidos com seguranca para outro status.
    pass
