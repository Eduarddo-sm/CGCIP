from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.user import utcnow


class CarteiraNegocial(Base):
    __tablename__ = "carteiras_negociais"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    descricao: Mapped[str | None] = mapped_column(String(240), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    usa_percentual_ho: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    percentual_ho_padrao: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    percentual_ho_minimo: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    percentual_ho_maximo: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    calculo_automatico_ho: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    modo_schema: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    colunas = relationship("CarteiraColuna", back_populates="carteira", cascade="all, delete-orphan")
    regras_calculo = relationship(
        "CarteiraRegraCalculo",
        back_populates="carteira",
        cascade="all, delete-orphan",
    )


class CarteiraFerramentaConfig(Base):
    __tablename__ = "carteira_ferramentas_config"
    __table_args__ = (UniqueConstraint("carteira", "tool_key", name="uq_carteira_ferramenta_config"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    carteira: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    tool_key: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class CarteiraColuna(Base):
    __tablename__ = "carteira_colunas"
    __table_args__ = (UniqueConstraint("carteira_id", "chave", name="uq_carteira_coluna_chave"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    carteira_id: Mapped[int] = mapped_column(ForeignKey("carteiras_negociais.id", ondelete="CASCADE"), index=True, nullable=False)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    chave: Mapped[str] = mapped_column(String(120), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), default="texto", nullable=False)
    obrigatoria: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    identificador: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    visivel: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    automatico: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_tipo: Mapped[str | None] = mapped_column(String(40), nullable=True)
    max_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mostrar_cadastro: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cadastro_etapa: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    opcoes_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    carteira = relationship("CarteiraNegocial", back_populates="colunas")


class CarteiraRegraCalculo(Base):
    __tablename__ = "carteira_regras_calculo"
    __table_args__ = (
        UniqueConstraint("carteira_id", "codigo", name="uq_carteira_regra_calculo_codigo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    carteira_id: Mapped[int] = mapped_column(
        ForeignKey("carteiras_negociais.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    codigo: Mapped[str] = mapped_column(String(60), default="HONORARIOS", nullable=False)
    nome: Mapped[str] = mapped_column(String(120), default="Honorarios", nullable=False)
    tipo_calculo: Mapped[str] = mapped_column(String(30), default="percentual", nullable=False)
    motor_calculo: Mapped[str] = mapped_column(
        String(32),
        default="PERCENTUAL_FIXO",
        nullable=False,
    )
    coluna_base_id: Mapped[int | None] = mapped_column(
        ForeignKey("carteira_colunas.id", ondelete="SET NULL"),
        nullable=True,
    )
    coluna_destino_id: Mapped[int | None] = mapped_column(
        ForeignKey("carteira_colunas.id", ondelete="SET NULL"),
        nullable=True,
    )
    coluna_base_vista_id: Mapped[int | None] = mapped_column(
        ForeignKey("carteira_colunas.id", ondelete="SET NULL"),
        nullable=True,
    )
    coluna_base_parcelado_id: Mapped[int | None] = mapped_column(
        ForeignKey("carteira_colunas.id", ondelete="SET NULL"),
        nullable=True,
    )
    coluna_valor_recebido_id: Mapped[int | None] = mapped_column(
        ForeignKey("carteira_colunas.id", ondelete="SET NULL"),
        nullable=True,
    )
    coluna_percentual_efetivo_id: Mapped[int | None] = mapped_column(
        ForeignKey("carteira_colunas.id", ondelete="SET NULL"),
        nullable=True,
    )
    percentual_padrao: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    percentual_minimo: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    percentual_maximo: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    automatico: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    casas_decimais: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    carteira = relationship("CarteiraNegocial", back_populates="regras_calculo")
    coluna_base = relationship("CarteiraColuna", foreign_keys=[coluna_base_id])
    coluna_destino = relationship("CarteiraColuna", foreign_keys=[coluna_destino_id])
    coluna_base_vista = relationship("CarteiraColuna", foreign_keys=[coluna_base_vista_id])
    coluna_base_parcelado = relationship(
        "CarteiraColuna",
        foreign_keys=[coluna_base_parcelado_id],
    )
    coluna_valor_recebido = relationship("CarteiraColuna", foreign_keys=[coluna_valor_recebido_id])
    coluna_percentual_efetivo = relationship(
        "CarteiraColuna",
        foreign_keys=[coluna_percentual_efetivo_id],
    )
