from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.user import utcnow


class Ferramenta(Base):
    __tablename__ = "ferramentas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    descricao: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tipo: Mapped[str] = mapped_column(String(30), default="CADASTRO", nullable=False)
    icone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cor: Mapped[str | None] = mapped_column(String(20), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    destaque_gerencial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deletion_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    versoes = relationship("FerramentaVersao", back_populates="ferramenta", cascade="all, delete-orphan")
    permissoes = relationship("FerramentaPermissao", back_populates="ferramenta", cascade="all, delete-orphan")


class FerramentaVersao(Base):
    __tablename__ = "ferramenta_versoes"
    __table_args__ = (UniqueConstraint("ferramenta_id", "numero", name="uq_ferramenta_versao"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ferramenta_id: Mapped[int] = mapped_column(
        ForeignKey("ferramentas.id", ondelete="CASCADE"), index=True, nullable=False
    )
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="RASCUNHO", index=True, nullable=False)
    configuracao_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ferramenta = relationship("Ferramenta", back_populates="versoes")
    campos = relationship("FerramentaCampo", back_populates="versao", cascade="all, delete-orphan")
    statuses = relationship("FerramentaStatus", back_populates="versao", cascade="all, delete-orphan")
    transicoes = relationship("FerramentaTransicao", back_populates="versao", cascade="all, delete-orphan")


class FerramentaCampo(Base):
    __tablename__ = "ferramenta_campos"
    __table_args__ = (UniqueConstraint("versao_id", "chave", name="uq_ferramenta_campo_chave"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    versao_id: Mapped[int] = mapped_column(
        ForeignKey("ferramenta_versoes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chave: Mapped[str] = mapped_column(String(120), nullable=False)
    nome: Mapped[str] = mapped_column(String(160), nullable=False)
    tipo: Mapped[str] = mapped_column(String(30), default="texto", nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    etapa: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    obrigatorio: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    somente_leitura: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    visivel_negocial: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    visivel_gerencial: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    opcoes_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    validacao_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    condicao_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    valor_padrao_json: Mapped[object | None] = mapped_column(JSON, nullable=True)

    versao = relationship("FerramentaVersao", back_populates="campos")


class FerramentaStatus(Base):
    __tablename__ = "ferramenta_status"
    __table_args__ = (UniqueConstraint("versao_id", "codigo", name="uq_ferramenta_status_codigo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    versao_id: Mapped[int] = mapped_column(
        ForeignKey("ferramenta_versoes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    codigo: Mapped[str] = mapped_column(String(80), nullable=False)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    cor: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ordem: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inicial: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    versao = relationship("FerramentaVersao", back_populates="statuses")


class FerramentaTransicao(Base):
    __tablename__ = "ferramenta_transicoes"
    __table_args__ = (
        UniqueConstraint("versao_id", "origem_codigo", "destino_codigo", name="uq_ferramenta_transicao"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    versao_id: Mapped[int] = mapped_column(
        ForeignKey("ferramenta_versoes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    origem_codigo: Mapped[str] = mapped_column(String(80), nullable=False)
    destino_codigo: Mapped[str] = mapped_column(String(80), nullable=False)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    exige_justificativa: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    permite_negociador: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    permite_gerencial: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    configuracao_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    versao = relationship("FerramentaVersao", back_populates="transicoes")


class FerramentaPermissao(Base):
    __tablename__ = "ferramenta_permissoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ferramenta_id: Mapped[int] = mapped_column(
        ForeignKey("ferramentas.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    carteira: Mapped[str | None] = mapped_column(String(80), index=True)
    pode_visualizar: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pode_criar: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pode_editar: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pode_transicionar: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pode_exportar: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    ferramenta = relationship("Ferramenta", back_populates="permissoes")


class FerramentaRegistro(Base):
    __tablename__ = "ferramenta_registros"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ferramenta_id: Mapped[int] = mapped_column(ForeignKey("ferramentas.id", ondelete="RESTRICT"), index=True)
    versao_id: Mapped[int] = mapped_column(ForeignKey("ferramenta_versoes.id", ondelete="RESTRICT"), index=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    owner_username: Mapped[str | None] = mapped_column(String(80), index=True)
    carteira: Mapped[str | None] = mapped_column(String(80), index=True)
    status_codigo: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    titulo: Mapped[str | None] = mapped_column(String(240), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, index=True, nullable=False
    )

    ferramenta = relationship("Ferramenta")
    versao = relationship("FerramentaVersao")
    eventos = relationship("FerramentaEvento", back_populates="registro", cascade="all, delete-orphan")
    comentarios = relationship("FerramentaComentario", back_populates="registro", cascade="all, delete-orphan")
    anexos = relationship("FerramentaAnexo", back_populates="registro", cascade="all, delete-orphan")


class FerramentaEvento(Base):
    __tablename__ = "ferramenta_eventos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    registro_id: Mapped[int] = mapped_column(
        ForeignKey("ferramenta_registros.id", ondelete="CASCADE"), index=True, nullable=False
    )
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_username: Mapped[str | None] = mapped_column(String(80))
    tipo: Mapped[str] = mapped_column(String(60), nullable=False)
    status_anterior: Mapped[str | None] = mapped_column(String(80))
    status_novo: Mapped[str | None] = mapped_column(String(80))
    justificativa: Mapped[str | None] = mapped_column(Text)
    before_json: Mapped[dict | None] = mapped_column(JSON)
    after_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    registro = relationship("FerramentaRegistro", back_populates="eventos")


class FerramentaComentario(Base):
    __tablename__ = "ferramenta_comentarios"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    registro_id: Mapped[int] = mapped_column(
        ForeignKey("ferramenta_registros.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    username: Mapped[str | None] = mapped_column(String(80))
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    registro = relationship("FerramentaRegistro", back_populates="comentarios")


class FerramentaAnexo(Base):
    __tablename__ = "ferramenta_anexos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    registro_id: Mapped[int] = mapped_column(
        ForeignKey("ferramenta_registros.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    username: Mapped[str | None] = mapped_column(String(80))
    campo_chave: Mapped[str | None] = mapped_column(String(120), index=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(160))
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    tamanho: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    registro = relationship("FerramentaRegistro", back_populates="anexos")
