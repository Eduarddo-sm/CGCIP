from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base
from backend.models.user import utcnow


class ParecerSolicitacao(Base):
    __tablename__ = "pareceres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data_solicitacao: Mapped[date] = mapped_column(Date, nullable=False)
    data_conclusao: Mapped[date | None] = mapped_column(Date, nullable=True)
    npj: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    cliente: Mapped[str] = mapped_column(String(180), index=True, nullable=False)
    motivo: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    descricao: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(40), default="PENDENTE", index=True, nullable=False)
    approval_reason: Mapped[str | None] = mapped_column(String(600), nullable=True)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    carteira: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    user = relationship("User")
