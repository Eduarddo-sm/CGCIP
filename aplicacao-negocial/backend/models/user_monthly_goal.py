from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.user import utcnow


class UserMonthlyGoal(Base):
    __tablename__ = "user_monthly_goals"
    __table_args__ = (UniqueConstraint("user_id", "competencia", name="uq_user_monthly_goals_user_competencia"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    competencia: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    meta_pagamento: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user = relationship("User")
