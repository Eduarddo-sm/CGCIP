"""Migra Pareceres para o dominio de ferramentas dinamicas.

Revision ID: 20260811_0031
Revises: 20260811_0030
Create Date: 2026-08-11
"""

from __future__ import annotations

import json

from alembic import op


revision = "20260811_0031"
down_revision = "20260811_0030"
branch_labels = None
depends_on = None


TOOL_SLUG = "pareceres"


def _screen_config() -> dict:
    common_fields = [
        "DATA_SOLICITACAO", "NPJ", "CLIENTE", "MOTIVO", "DESCRICAO",
        "NEGOCIADOR", "CARTEIRA", "JUSTIFICATIVA_DECISAO",
        "DATA_DECISAO", "DATA_SOLICITADO",
    ]
    return {
        "campo_titulo": "CLIENTE",
        "usar_status": True,
        "notificar_pendencias": True,
        "telas": [
            {
                "id": "dashboard",
                "nome": "Dashboard",
                "tipo": "dashboard",
                "visivel_negocial": False,
                "visivel_gerencial": True,
                "componentes": ["metricas", "filtros"],
                "dashboard": {
                    "columns": 12,
                    "blocks": [
                        {"id": "total", "tipo": "metric", "titulo": "Total de pareceres", "agregacao": "count", "largura": 4, "cor": "#2563eb"},
                        {"id": "aguardando", "tipo": "metric", "titulo": "Aguardando aprovacao", "agregacao": "count", "status_codes": ["PENDENTE_APROVACAO"], "largura": 4, "cor": "#d97706"},
                        {"id": "solicitados", "tipo": "metric", "titulo": "Solicitados", "agregacao": "count", "status_codes": ["SOLICITADO"], "largura": 4, "cor": "#059669"},
                    ],
                },
            },
            {
                "id": "pendentes",
                "nome": "Pendentes",
                "tipo": "lista",
                "visivel_negocial": True,
                "visivel_gerencial": True,
                "componentes": ["busca", "filtros", "lista", "acoes"],
                "status_codes": ["PENDENTE_SOLICITACAO"],
                "campos": common_fields,
                "layout": {"colunas_desktop": 1, "colunas_tablet": 1, "colunas_mobile": 1, "densidade": "compacta"},
                "filtros": {"mostrar_status": True, "mostrar_negociador": True, "mostrar_carteira": True, "mostrar_ordenacao": True, "campos": ["NPJ", "CLIENTE", "MOTIVO"]},
                "campo_layout": {
                    "CLIENTE": {"papel": "titulo", "largura": "full", "copiavel": True},
                    "NPJ": {"papel": "identificador", "copiavel": True},
                    "MOTIVO": {"papel": "destaque"},
                    "DESCRICAO": {"papel": "descricao", "largura": "full"},
                },
            },
            {
                "id": "aprovar",
                "nome": "Aprovar parecer",
                "tipo": "aprovacao",
                "visivel_negocial": False,
                "visivel_gerencial": True,
                "componentes": ["busca", "filtros", "lista", "acoes", "historico"],
                "status_codes": ["PENDENTE_APROVACAO"],
                "historico_status_codes": ["PENDENTE_SOLICITACAO", "SOLICITADO", "CANCELADO"],
                "campos": common_fields,
                "layout": {"colunas_desktop": 1, "colunas_tablet": 1, "colunas_mobile": 1, "densidade": "compacta"},
                "filtros": {"mostrar_status": True, "mostrar_negociador": True, "mostrar_carteira": True, "mostrar_ordenacao": True, "campos": ["NPJ", "CLIENTE", "MOTIVO"]},
            },
            {
                "id": "planilha",
                "nome": "Planilha de Pareceres",
                "tipo": "planilha",
                "visivel_negocial": True,
                "visivel_gerencial": True,
                "componentes": ["busca", "filtros", "planilha", "relatorio"],
                "campos": common_fields,
            },
        ],
    }


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    config_json = json.dumps(_screen_config(), ensure_ascii=False)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS negocial.parecer_ferramenta_migracao (
            parecer_id INTEGER PRIMARY KEY
                REFERENCES negocial.pareceres(id) ON DELETE RESTRICT,
            registro_id BIGINT NOT NULL UNIQUE
                REFERENCES negocial.ferramenta_registros(id) ON DELETE RESTRICT,
            migrated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        f"""
        INSERT INTO negocial.ferramentas
            (nome, slug, descricao, tipo, icone, cor, active, destaque_gerencial, created_at, updated_at)
        VALUES
            ('Pareceres', '{TOOL_SLUG}', 'Solicitacao, aprovacao e acompanhamento de pareceres.',
             'SOLICITACAO', 'file-check', '#2563eb', TRUE, TRUE, NOW(), NOW())
        ON CONFLICT (slug) DO UPDATE SET
            nome = EXCLUDED.nome,
            descricao = EXCLUDED.descricao,
            tipo = EXCLUDED.tipo,
            active = TRUE,
            deleted_at = NULL,
            purge_after = NULL
        """
    )
    op.execute(
        f"""
        INSERT INTO negocial.ferramenta_versoes
            (ferramenta_id, numero, status, configuracao_json, created_at, published_at)
        SELECT f.id, 1, 'PUBLICADA', $json${config_json}$json$::jsonb, NOW(), NOW()
        FROM negocial.ferramentas f
        WHERE f.slug = '{TOOL_SLUG}'
          AND NOT EXISTS (
              SELECT 1 FROM negocial.ferramenta_versoes v
              WHERE v.ferramenta_id = f.id
          )
        """
    )

    fields = [
        ("DATA_SOLICITACAO", "Data de solicitacao", "data", 1, 1, True, True, True, True, [], {"preenchimento_automatico": "today"}),
        ("NPJ", "NPJ", "texto", 2, 1, True, False, True, True, [], {"min_length": 14, "max_length": 14, "regex": "^[0-9]{14}$", "mensagem": "NPJ deve conter exatamente 14 digitos."}),
        ("CLIENTE", "Cliente", "texto", 3, 1, True, False, True, True, [], {"max_length": 180}),
        ("MOTIVO", "Motivo", "select", 4, 1, True, False, True, True, ["PISO NEGOCIAL", "PARECER", "REUNIAO", "EVENTO"], {}),
        ("DESCRICAO", "Descricao", "texto_longo", 5, 1, True, False, True, True, [], {"max_length": 1000}),
        ("NEGOCIADOR", "Negociador", "usuario", 6, 1, True, True, False, True, [], {}),
        ("CARTEIRA", "Carteira", "carteira", 7, 1, True, True, False, True, [], {}),
        ("JUSTIFICATIVA_DECISAO", "Justificativa da decisao", "texto_longo", 8, 2, False, True, True, True, [], {}),
        ("DATA_DECISAO", "Data de aprovacao/reprovacao", "data", 9, 2, False, True, True, True, [], {}),
        ("DATA_SOLICITADO", "Data de solicitacao efetiva", "data", 10, 2, False, True, True, True, [], {}),
    ]
    for key, name, kind, order, stage, required, readonly, visible_neg, visible_mgr, options, validation in fields:
        op.execute(
            f"""
            INSERT INTO negocial.ferramenta_campos
                (versao_id, chave, nome, tipo, ordem, etapa, obrigatorio, somente_leitura,
                 visivel_negocial, visivel_gerencial, opcoes_json, validacao_json,
                 condicao_json, valor_padrao_json)
            SELECT v.id, '{key}', '{name}', '{kind}', {order}, {stage},
                   {str(required).upper()}, {str(readonly).upper()}, {str(visible_neg).upper()},
                   {str(visible_mgr).upper()}, $json${json.dumps(options, ensure_ascii=False)}$json$::jsonb,
                   $json${json.dumps(validation, ensure_ascii=False)}$json$::jsonb, '{{}}'::jsonb, NULL
            FROM negocial.ferramenta_versoes v
            JOIN negocial.ferramentas f ON f.id = v.ferramenta_id
            WHERE f.slug = '{TOOL_SLUG}' AND v.status = 'PUBLICADA'
            ON CONFLICT (versao_id, chave) DO NOTHING
            """
        )

    statuses = [
        ("PENDENTE_APROVACAO", "Aguardando aprovacao", "#d97706", 1, True, False),
        ("PENDENTE_SOLICITACAO", "Pendente de solicitacao", "#2563eb", 2, False, False),
        ("SOLICITADO", "Solicitado", "#059669", 3, False, True),
        ("CANCELADO", "Cancelado", "#dc2626", 4, False, True),
    ]
    for code, name, color, order, initial, final in statuses:
        op.execute(
            f"""
            INSERT INTO negocial.ferramenta_status
                (versao_id, codigo, nome, cor, ordem, inicial, final)
            SELECT v.id, '{code}', '{name}', '{color}', {order},
                   {str(initial).upper()}, {str(final).upper()}
            FROM negocial.ferramenta_versoes v
            JOIN negocial.ferramentas f ON f.id = v.ferramenta_id
            WHERE f.slug = '{TOOL_SLUG}' AND v.status = 'PUBLICADA'
            ON CONFLICT (versao_id, codigo) DO NOTHING
            """
        )

    transitions = [
        ("PENDENTE_APROVACAO", "PENDENTE_SOLICITACAO", "Aprovar", True, False, True, "DATA_DECISAO"),
        ("PENDENTE_APROVACAO", "CANCELADO", "Reprovar", True, False, True, "DATA_DECISAO"),
        ("PENDENTE_APROVACAO", "CANCELADO", "Cancelar", True, True, True, "DATA_DECISAO"),
        ("PENDENTE_SOLICITACAO", "SOLICITADO", "Marcar como solicitado", False, False, True, "DATA_SOLICITADO"),
    ]
    # A restricao atual nao permite dois destinos iguais a partir da mesma origem. O cancelamento
    # gerencial tambem atende ao negociador, portanto a permissao e compartilhada nessa transicao.
    unique_transitions: dict[tuple[str, str], tuple] = {}
    for item in transitions:
        unique_transitions[(item[0], item[1])] = item
    for origin, target, name, reason, negotiator, manager, date_field in unique_transitions.values():
        transition_config = {"automacoes": [{"tipo": "data_atual", "campo": date_field}]}
        op.execute(
            f"""
            INSERT INTO negocial.ferramenta_transicoes
                (versao_id, origem_codigo, destino_codigo, nome, exige_justificativa,
                 permite_negociador, permite_gerencial, configuracao_json)
            SELECT v.id, '{origin}', '{target}', '{name}', {str(reason).upper()},
                   {str(negotiator).upper()}, {str(manager).upper()},
                   $json${json.dumps(transition_config)}$json$::jsonb
            FROM negocial.ferramenta_versoes v
            JOIN negocial.ferramentas f ON f.id = v.ferramenta_id
            WHERE f.slug = '{TOOL_SLUG}' AND v.status = 'PUBLICADA'
            ON CONFLICT (versao_id, origem_codigo, destino_codigo) DO NOTHING
            """
        )

    op.execute(
        f"""
        INSERT INTO negocial.ferramenta_permissoes
            (ferramenta_id, carteira, pode_visualizar, pode_criar, pode_editar,
             pode_transicionar, pode_exportar, created_at)
        SELECT f.id, wallets.carteira, TRUE, TRUE, TRUE, FALSE, TRUE, NOW()
        FROM negocial.ferramentas f
        CROSS JOIN (
            SELECT DISTINCT UPPER(BTRIM(carteira)) AS carteira
            FROM negocial.users
            WHERE COALESCE(BTRIM(carteira), '') <> ''
        ) wallets
        WHERE f.slug = '{TOOL_SLUG}'
        ON CONFLICT DO NOTHING
        """
    )

    op.execute(
        f"""
        WITH target AS (
            SELECT f.id AS ferramenta_id, v.id AS versao_id
            FROM negocial.ferramentas f
            JOIN negocial.ferramenta_versoes v ON v.ferramenta_id = f.id AND v.status = 'PUBLICADA'
            WHERE f.slug = '{TOOL_SLUG}'
        ), inserted AS (
            INSERT INTO negocial.ferramenta_registros
                (ferramenta_id, versao_id, owner_user_id, owner_username, carteira,
                 status_codigo, titulo, payload_json, active, created_at, updated_at)
            SELECT target.ferramenta_id, target.versao_id, p.user_id, u.username, p.carteira,
                   CASE
                     WHEN UPPER(COALESCE(p.approval_status, '')) = 'REPROVADO' OR UPPER(p.status) = 'CANCELADO' THEN 'CANCELADO'
                     WHEN UPPER(p.status) = 'SOLICITADO' THEN 'SOLICITADO'
                     WHEN UPPER(COALESCE(p.approval_status, '')) = 'APROVADO' THEN 'PENDENTE_SOLICITACAO'
                     ELSE 'PENDENTE_APROVACAO'
                   END,
                   p.cliente,
                   jsonb_strip_nulls(jsonb_build_object(
                     'DATA_SOLICITACAO', p.data_solicitacao,
                     'NPJ', p.npj,
                     'CLIENTE', p.cliente,
                     'MOTIVO', p.motivo,
                     'DESCRICAO', p.descricao,
                     'NEGOCIADOR', u.username,
                     'CARTEIRA', p.carteira,
                     'JUSTIFICATIVA_DECISAO', p.approval_reason,
                     'DATA_DECISAO', p.approval_decided_at::date,
                     'DATA_SOLICITADO', p.requested_at::date,
                     '_LEGACY_PARECER_ID', p.id
                   )),
                   TRUE, p.created_at, p.updated_at
            FROM negocial.pareceres p
            JOIN negocial.users u ON u.id = p.user_id
            CROSS JOIN target
            WHERE NOT EXISTS (
                SELECT 1 FROM negocial.parecer_ferramenta_migracao m WHERE m.parecer_id = p.id
            )
            RETURNING id, (payload_json->>'_LEGACY_PARECER_ID')::integer AS parecer_id
        )
        INSERT INTO negocial.parecer_ferramenta_migracao (parecer_id, registro_id)
        SELECT parecer_id, id FROM inserted
        ON CONFLICT (parecer_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO negocial.ferramenta_eventos
            (registro_id, actor_user_id, actor_username, tipo, status_novo,
             justificativa, after_json, created_at)
        SELECT m.registro_id, p.user_id, u.username, 'MIGRACAO_PARECER_LEGADO',
               r.status_codigo, p.approval_reason, r.payload_json, p.created_at
        FROM negocial.parecer_ferramenta_migracao m
        JOIN negocial.pareceres p ON p.id = m.parecer_id
        JOIN negocial.users u ON u.id = p.user_id
        JOIN negocial.ferramenta_registros r ON r.id = m.registro_id
        WHERE NOT EXISTS (
            SELECT 1 FROM negocial.ferramenta_eventos e
            WHERE e.registro_id = m.registro_id AND e.tipo = 'MIGRACAO_PARECER_LEGADO'
        )
        """
    )
    op.execute(
        """
        INSERT INTO negocial.operational_versions (scope, version, updated_at)
        VALUES ('ferramentas', 1, NOW()), ('pareceres', 1, NOW())
        ON CONFLICT (scope)
        DO UPDATE SET version = negocial.operational_versions.version + 1, updated_at = NOW()
        """
    )
    op.execute(
        """
        INSERT INTO negocial.schema_migrations_meta (revision, description)
        VALUES ('20260811_0031', 'Migra Pareceres para ferramenta dinamica oficial')
        ON CONFLICT (revision) DO NOTHING
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        f"""
        DELETE FROM negocial.ferramenta_eventos
        WHERE registro_id IN (SELECT registro_id FROM negocial.parecer_ferramenta_migracao)
        """
    )
    op.execute(
        "DELETE FROM negocial.ferramenta_registros WHERE id IN (SELECT registro_id FROM negocial.parecer_ferramenta_migracao)"
    )
    op.execute("DROP TABLE IF EXISTS negocial.parecer_ferramenta_migracao")
    op.execute(f"DELETE FROM negocial.ferramentas WHERE slug = '{TOOL_SLUG}'")
    op.execute("DELETE FROM negocial.schema_migrations_meta WHERE revision = '20260811_0031'")
