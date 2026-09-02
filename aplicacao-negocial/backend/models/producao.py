from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.user import utcnow


class ProducaoRegistro(Base):
    __tablename__ = "producao_registros"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data_acordo: Mapped[date] = mapped_column(Date, nullable=False)
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    cliente: Mapped[str] = mapped_column(String(180), index=True, nullable=False)
    valor_total_acordo: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    valor_entrada: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tipo_acordo: Mapped[str] = mapped_column(String(20), nullable=False)
    data_vencimento: Mapped[date] = mapped_column(Date, nullable=False)
    data_pagamento: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    justificativa_status: Mapped[str | None] = mapped_column(String(600), nullable=True)
    carteira: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    origem_registro: Mapped[str] = mapped_column(String(32), default="SISTEMA", nullable=False)
    import_source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    import_source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    user = relationship("User")
    gamma = relationship(
        "ProducaoGamma",
        back_populates="registro",
        cascade="all, delete-orphan",
        uselist=False,
    )
    alpha = relationship(
        "ProducaoAlpha",
        back_populates="registro",
        cascade="all, delete-orphan",
        uselist=False,
    )
    beta_detail = relationship(
        "ProducaoBeta",
        back_populates="registro",
        cascade="all, delete-orphan",
        uselist=False,
    )
    campos = relationship(
        "ProducaoCampo",
        back_populates="registro",
        cascade="all, delete-orphan",
    )


class ProducaoGamma(Base):
    __tablename__ = "producao_gamma"

    producao_id: Mapped[int] = mapped_column(
        ForeignKey("producao_registros.id", ondelete="CASCADE"),
        primary_key=True,
    )
    npj: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    gecor: Mapped[str] = mapped_column(String(80), nullable=False)
    valor_ho: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    percentual_ho: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    autorizacao_flexibilizacao: Mapped[str] = mapped_column(String(80), default="NAO", nullable=False)

    registro = relationship("ProducaoRegistro", back_populates="gamma")


class ProducaoAlpha(Base):
    __tablename__ = "producao_alpha"

    producao_id: Mapped[int] = mapped_column(
        ForeignKey("producao_registros.id", ondelete="CASCADE"),
        primary_key=True,
    )
    debit_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    cpf: Mapped[str] = mapped_column(String(14), index=True, nullable=False)
    data_primeiro_atraso: Mapped[date | None] = mapped_column(Date, nullable=True)
    portfolio: Mapped[str | None] = mapped_column(String(120), nullable=True)
    carteira_alpha: Mapped[str] = mapped_column(String(20), nullable=False)
    ho_origem: Mapped[str] = mapped_column(String(32), default="CALCULADO", nullable=False)
    ho_legado: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    registro = relationship("ProducaoRegistro", back_populates="alpha")


class ProducaoBeta(Base):
    __tablename__ = "producao_beta"

    producao_id: Mapped[int] = mapped_column(
        ForeignKey("producao_registros.id", ondelete="CASCADE"),
        primary_key=True,
    )
    suitid: Mapped[str] = mapped_column(String(80), index=True, nullable=False)

    registro = relationship("ProducaoRegistro", back_populates="beta_detail")


class ProducaoCampo(Base):
    __tablename__ = "producao_campos"

    producao_id: Mapped[int] = mapped_column(
        ForeignKey("producao_registros.id", ondelete="CASCADE"),
        primary_key=True,
    )
    coluna_id: Mapped[int] = mapped_column(
        ForeignKey("carteira_colunas.id", ondelete="CASCADE"),
        primary_key=True,
    )
    valor_texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor_numero: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    valor_data: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Dynamic scalar fields must keep this column as SQL NULL. PostgreSQL
    # treats JSON "null" as a value, which would violate the single-value
    # constraint whenever valor_texto, valor_numero or valor_data is present.
    valor_json: Mapped[dict | list | str | None] = mapped_column(
        JSON(none_as_null=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    registro = relationship("ProducaoRegistro", back_populates="campos")
    coluna = relationship("CarteiraColuna")


class ProducaoViradaMensal(Base):
    __tablename__ = "producao_viradas_mensais"
    __table_args__ = (
        UniqueConstraint("user_id", "competencia_origem", "competencia_destino", name="uq_producao_virada_usuario_competencias"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    competencia_origem: Mapped[date] = mapped_column(Date, nullable=False)
    competencia_destino: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    total_candidatos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_transferidos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ids_transferidos: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    confirmado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User")


class ProducaoViradaExcecao(Base):
    __tablename__ = "producao_virada_excecoes"
    __table_args__ = (
        UniqueConstraint("user_id", "competencia_origem", "competencia_destino", name="uq_producao_virada_excecao_usuario_competencias"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    competencia_origem: Mapped[date] = mapped_column(Date, nullable=False)
    competencia_destino: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    valida_ate: Mapped[date] = mapped_column(Date, nullable=False)
    motivo: Mapped[str] = mapped_column(String(240), nullable=False)
    consumida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User")
