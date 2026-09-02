"""Cria o dominio de ferramentas negociais dinamicas.

Revision ID: 20260727_0016
Revises: 20260723_0015
Create Date: 2026-07-27
"""

from __future__ import annotations

from alembic import op


revision = "20260727_0016"
down_revision = "20260723_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS negocial.ferramentas (
            id SERIAL PRIMARY KEY,
            nome VARCHAR(120) NOT NULL,
            slug VARCHAR(120) NOT NULL UNIQUE,
            descricao VARCHAR(500),
            tipo VARCHAR(30) NOT NULL DEFAULT 'CADASTRO',
            icone VARCHAR(80),
            cor VARCHAR(20),
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by INTEGER REFERENCES negocial.users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_ferramentas_tipo CHECK (tipo IN ('CADASTRO', 'SOLICITACAO'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS negocial.ferramenta_versoes (
            id SERIAL PRIMARY KEY,
            ferramenta_id INTEGER NOT NULL
                REFERENCES negocial.ferramentas(id) ON DELETE CASCADE,
            numero INTEGER NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'RASCUNHO',
            configuracao_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by INTEGER REFERENCES negocial.users(id) ON DELETE SET NULL,
            published_by INTEGER REFERENCES negocial.users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            published_at TIMESTAMPTZ,
            archived_at TIMESTAMPTZ,
            CONSTRAINT uq_ferramenta_versao UNIQUE (ferramenta_id, numero),
            CONSTRAINT ck_ferramenta_versao_status
                CHECK (status IN ('RASCUNHO', 'PUBLICADA', 'ARQUIVADA'))
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ferramenta_versao_publicada
        ON negocial.ferramenta_versoes(ferramenta_id)
        WHERE status = 'PUBLICADA'
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS negocial.ferramenta_campos (
            id SERIAL PRIMARY KEY,
            versao_id INTEGER NOT NULL
                REFERENCES negocial.ferramenta_versoes(id) ON DELETE CASCADE,
            chave VARCHAR(120) NOT NULL,
            nome VARCHAR(160) NOT NULL,
            tipo VARCHAR(30) NOT NULL DEFAULT 'texto',
            ordem INTEGER NOT NULL DEFAULT 0,
            etapa INTEGER NOT NULL DEFAULT 1,
            obrigatorio BOOLEAN NOT NULL DEFAULT FALSE,
            somente_leitura BOOLEAN NOT NULL DEFAULT FALSE,
            visivel_negocial BOOLEAN NOT NULL DEFAULT TRUE,
            visivel_gerencial BOOLEAN NOT NULL DEFAULT TRUE,
            opcoes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            validacao_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            condicao_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            valor_padrao_json JSONB,
            CONSTRAINT uq_ferramenta_campo_chave UNIQUE (versao_id, chave),
            CONSTRAINT ck_ferramenta_campo_tipo CHECK (
                tipo IN (
                    'texto', 'texto_longo', 'numero', 'moeda', 'data',
                    'select', 'multiselect', 'boolean', 'usuario', 'carteira'
                )
            ),
            CONSTRAINT ck_ferramenta_campo_etapa CHECK (etapa BETWEEN 1 AND 10)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS negocial.ferramenta_status (
            id SERIAL PRIMARY KEY,
            versao_id INTEGER NOT NULL
                REFERENCES negocial.ferramenta_versoes(id) ON DELETE CASCADE,
            codigo VARCHAR(80) NOT NULL,
            nome VARCHAR(120) NOT NULL,
            cor VARCHAR(20),
            ordem INTEGER NOT NULL DEFAULT 0,
            inicial BOOLEAN NOT NULL DEFAULT FALSE,
            final BOOLEAN NOT NULL DEFAULT FALSE,
            CONSTRAINT uq_ferramenta_status_codigo UNIQUE (versao_id, codigo)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ferramenta_status_inicial
        ON negocial.ferramenta_status(versao_id)
        WHERE inicial = TRUE
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS negocial.ferramenta_transicoes (
            id SERIAL PRIMARY KEY,
            versao_id INTEGER NOT NULL
                REFERENCES negocial.ferramenta_versoes(id) ON DELETE CASCADE,
            origem_codigo VARCHAR(80) NOT NULL,
            destino_codigo VARCHAR(80) NOT NULL,
            nome VARCHAR(120) NOT NULL,
            exige_justificativa BOOLEAN NOT NULL DEFAULT FALSE,
            permite_negociador BOOLEAN NOT NULL DEFAULT FALSE,
            permite_gerencial BOOLEAN NOT NULL DEFAULT TRUE,
            configuracao_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT uq_ferramenta_transicao
                UNIQUE (versao_id, origem_codigo, destino_codigo),
            CONSTRAINT ck_ferramenta_transicao_distinta
                CHECK (origem_codigo <> destino_codigo)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS negocial.ferramenta_permissoes (
            id SERIAL PRIMARY KEY,
            ferramenta_id INTEGER NOT NULL
                REFERENCES negocial.ferramentas(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES negocial.users(id) ON DELETE CASCADE,
            carteira VARCHAR(80),
            pode_visualizar BOOLEAN NOT NULL DEFAULT TRUE,
            pode_criar BOOLEAN NOT NULL DEFAULT TRUE,
            pode_editar BOOLEAN NOT NULL DEFAULT TRUE,
            pode_transicionar BOOLEAN NOT NULL DEFAULT FALSE,
            pode_exportar BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_ferramenta_permissao_escopo
                CHECK (user_id IS NOT NULL OR carteira IS NOT NULL)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ferramenta_permissao_usuario
        ON negocial.ferramenta_permissoes(ferramenta_id, user_id)
        WHERE user_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_ferramenta_permissao_carteira
        ON negocial.ferramenta_permissoes(ferramenta_id, UPPER(carteira))
        WHERE user_id IS NULL AND carteira IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS negocial.ferramenta_registros (
            id BIGSERIAL PRIMARY KEY,
            ferramenta_id INTEGER NOT NULL
                REFERENCES negocial.ferramentas(id) ON DELETE RESTRICT,
            versao_id INTEGER NOT NULL
                REFERENCES negocial.ferramenta_versoes(id) ON DELETE RESTRICT,
            owner_user_id INTEGER REFERENCES negocial.users(id) ON DELETE SET NULL,
            owner_username VARCHAR(80),
            carteira VARCHAR(80),
            status_codigo VARCHAR(80) NOT NULL,
            titulo VARCHAR(240),
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS negocial.ferramenta_eventos (
            id BIGSERIAL PRIMARY KEY,
            registro_id BIGINT NOT NULL
                REFERENCES negocial.ferramenta_registros(id) ON DELETE CASCADE,
            actor_user_id INTEGER REFERENCES negocial.users(id) ON DELETE SET NULL,
            actor_username VARCHAR(80),
            tipo VARCHAR(60) NOT NULL,
            status_anterior VARCHAR(80),
            status_novo VARCHAR(80),
            justificativa TEXT,
            before_json JSONB,
            after_json JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS negocial.ferramenta_comentarios (
            id BIGSERIAL PRIMARY KEY,
            registro_id BIGINT NOT NULL
                REFERENCES negocial.ferramenta_registros(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES negocial.users(id) ON DELETE SET NULL,
            username VARCHAR(80),
            texto TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_ferramenta_comentario_texto CHECK (LENGTH(BTRIM(texto)) > 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS negocial.ferramenta_anexos (
            id BIGSERIAL PRIMARY KEY,
            registro_id BIGINT NOT NULL
                REFERENCES negocial.ferramenta_registros(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES negocial.users(id) ON DELETE SET NULL,
            nome VARCHAR(255) NOT NULL,
            content_type VARCHAR(160),
            storage_key VARCHAR(500) NOT NULL,
            tamanho BIGINT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_ferramenta_anexo_tamanho CHECK (tamanho >= 0)
        )
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ferramenta_versoes_lookup "
        "ON negocial.ferramenta_versoes(ferramenta_id, status, numero DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ferramenta_campos_ordem "
        "ON negocial.ferramenta_campos(versao_id, etapa, ordem, id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ferramenta_status_ordem "
        "ON negocial.ferramenta_status(versao_id, ordem, id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ferramenta_registros_lista "
        "ON negocial.ferramenta_registros(ferramenta_id, carteira, status_codigo, updated_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ferramenta_registros_owner "
        "ON negocial.ferramenta_registros(owner_user_id, ferramenta_id, updated_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ferramenta_registros_payload "
        "ON negocial.ferramenta_registros USING GIN(payload_json)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ferramenta_eventos_registro "
        "ON negocial.ferramenta_eventos(registro_id, created_at DESC)"
    )
    op.execute(
        """
        INSERT INTO negocial.operational_versions (scope, version, updated_at)
        VALUES ('ferramentas', 1, NOW())
        ON CONFLICT (scope) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO negocial.db_retention_policies (scope, retention_days, keep_latest)
        VALUES ('ferramenta_eventos', 1825, 100)
        ON CONFLICT (scope) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO negocial.schema_migrations_meta (revision, description)
        VALUES ('20260727_0016', 'Dominio versionado de ferramentas negociais dinamicas')
        ON CONFLICT (revision) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS negocial.ferramenta_anexos")
    op.execute("DROP TABLE IF EXISTS negocial.ferramenta_comentarios")
    op.execute("DROP TABLE IF EXISTS negocial.ferramenta_eventos")
    op.execute("DROP TABLE IF EXISTS negocial.ferramenta_registros")
    op.execute("DROP TABLE IF EXISTS negocial.ferramenta_permissoes")
    op.execute("DROP TABLE IF EXISTS negocial.ferramenta_transicoes")
    op.execute("DROP TABLE IF EXISTS negocial.ferramenta_status")
    op.execute("DROP TABLE IF EXISTS negocial.ferramenta_campos")
    op.execute("DROP TABLE IF EXISTS negocial.ferramenta_versoes")
    op.execute("DROP TABLE IF EXISTS negocial.ferramentas")
