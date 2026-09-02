from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.user import utcnow


class AlphaMetaImport(Base):
    __tablename__ = "alpha_meta_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    quarter: Mapped[str] = mapped_column(String(8), index=True, nullable=False)
    office: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), index=True, default="RASCUNHO", nullable=False)
    raw_data_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    validation_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    applied_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    goals = relationship(
        "AlphaPortfolioGoal",
        back_populates="meta_import",
        cascade="all, delete-orphan",
    )


class AlphaPortfolioGoal(Base):
    __tablename__ = "alpha_portfolio_goals"
    __table_args__ = (
        UniqueConstraint("import_id", "portfolio_key", "competence", name="uq_alpha_goal_import_portfolio_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[int | None] = mapped_column(
        ForeignKey("alpha_meta_imports.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    portfolio: Mapped[str] = mapped_column(String(180), nullable=False)
    portfolio_key: Mapped[str] = mapped_column(String(180), index=True, nullable=False)
    group_name: Mapped[str] = mapped_column(String(80), nullable=False)
    competence: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    meta_caixa: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0, nullable=False)
    retomadas_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retomadas_value: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0, nullable=False)
    meta_pnt: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0, nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), default="PDF", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    supersedes_goal_id: Mapped[int | None] = mapped_column(
        ForeignKey("alpha_portfolio_goals.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    adjustment_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    meta_import = relationship("AlphaMetaImport", back_populates="goals")
    calculations = relationship("AlphaHoCalculation", back_populates="goal")


class AlphaHoRuleVersion(Base):
    __tablename__ = "alpha_ho_rule_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True, default="RASCUNHO", nullable=False)
    matrix_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    calculations = relationship("AlphaHoCalculation", back_populates="rule_version")


class AlphaHoCalculation(Base):
    __tablename__ = "alpha_ho_calculations"
    __table_args__ = (
        UniqueConstraint("producao_id", "calculation_mode", name="uq_alpha_ho_calculation_record_mode"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    producao_id: Mapped[int] = mapped_column(
        ForeignKey("producao_registros.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    competence: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    portfolio_key: Mapped[str] = mapped_column(String(180), index=True, nullable=False)
    goal_id: Mapped[int | None] = mapped_column(
        ForeignKey("alpha_portfolio_goals.id", ondelete="SET NULL"),
        nullable=True,
    )
    rule_version_id: Mapped[int] = mapped_column(
        ForeignKey("alpha_ho_rule_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    delay_days: Mapped[int] = mapped_column(Integer, nullable=False)
    accumulated_production: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    attainment_percent: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0, nullable=False)
    applied_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    base_value: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    calculated_honorarios: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    calculation_mode: Mapped[str] = mapped_column(String(20), default="CONFERENCIA", nullable=False)
    details_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    goal = relationship("AlphaPortfolioGoal", back_populates="calculations")
    rule_version = relationship("AlphaHoRuleVersion", back_populates="calculations")
