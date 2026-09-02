from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.models import ParecerSolicitacao, User
from backend.schemas.parecer import ParecerCreate, ParecerStatusUpdate, ParecerUpdate
from backend.services.audit_service import record_audit
from backend.services.version_service import bump_version
from backend.models.user import utcnow


STATUS_LABELS = {
    "PENDENTE": "Pendente",
    "SOLICITADO": "Solicitado",
    "CANCELADO": "Cancelado",
}


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def _visible_query(db: Session, user: User):
    query = db.query(ParecerSolicitacao)
    if user.role.upper() != "ADMIN":
        query = query.filter(ParecerSolicitacao.user_id == user.id)
    return query


def _apply_status(item: ParecerSolicitacao, status_value: str):
    item.status = status_value
    item.data_conclusao = None
    if status_value == "SOLICITADO":
        item.requested_at = utcnow()
    if status_value == "CANCELADO":
        item.approval_status = "REPROVADO"
        item.approval_decided_at = utcnow()


def serialize_parecer(item: ParecerSolicitacao) -> dict:
    return {
        "id": item.id,
        "data_solicitacao": item.data_solicitacao.isoformat(),
        "data_conclusao": item.data_conclusao.isoformat() if item.data_conclusao else None,
        "npj": item.npj,
        "cliente": item.cliente,
        "motivo": item.motivo,
        "descricao": item.descricao,
        "status": item.status,
        "status_label": STATUS_LABELS.get(item.status, item.status),
        "approval_status": item.approval_status or "PENDENTE",
        "approval_reason": item.approval_reason,
        "requested_at": item.requested_at.isoformat() if item.requested_at else None,
        "approval_decided_at": item.approval_decided_at.isoformat() if item.approval_decided_at else None,
        "carteira": item.carteira,
        "user_id": item.user_id,
        "negociador": item.user.username if item.user else None,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def list_pareceres(db: Session, user: User) -> list[dict]:
    items = (
        _visible_query(db, user)
        .order_by(ParecerSolicitacao.created_at.desc(), ParecerSolicitacao.id.desc())
        .all()
    )
    return [serialize_parecer(item) for item in items]


def get_parecer(db: Session, user: User, parecer_id: int) -> ParecerSolicitacao:
    item = _visible_query(db, user).filter(ParecerSolicitacao.id == parecer_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parecer nao encontrado.")
    return item


def create_parecer(db: Session, user: User, payload: ParecerCreate) -> dict:
    item = ParecerSolicitacao(
        data_solicitacao=date.today(),
        npj=_normalize_text(payload.npj),
        cliente=_normalize_text(payload.cliente),
        motivo=_normalize_text(payload.motivo),
        descricao=_normalize_text(payload.descricao),
        status="PENDENTE",
        approval_status="PENDENTE",
        approval_reason=None,
        carteira=user.carteira or "GAMMA",
        user_id=user.id,
    )
    db.add(item)
    db.flush()
    record_audit(db, user=user, action="create", entity_type="parecer", entity_id=item.id, after=serialize_parecer(item))
    bump_version(db, "pareceres")
    db.commit()
    db.refresh(item)
    return serialize_parecer(item)


def update_parecer(db: Session, user: User, parecer_id: int, payload: ParecerUpdate) -> dict:
    item = get_parecer(db, user, parecer_id)
    before = serialize_parecer(item)
    item.npj = _normalize_text(payload.npj)
    item.cliente = _normalize_text(payload.cliente)
    item.motivo = _normalize_text(payload.motivo)
    item.descricao = _normalize_text(payload.descricao)
    item.carteira = user.carteira or item.carteira or "GAMMA"
    db.flush()
    record_audit(db, user=user, action="update", entity_type="parecer", entity_id=item.id, before=before, after=serialize_parecer(item))
    bump_version(db, "pareceres")
    db.commit()
    db.refresh(item)
    return serialize_parecer(item)


def update_parecer_status(
    db: Session,
    user: User,
    parecer_id: int,
    payload: ParecerStatusUpdate,
) -> dict:
    is_admin = user.role.upper() == "ADMIN"
    if not is_admin and payload.status != "CANCELADO":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Status do parecer so pode ser alterado pela aplicacao gerencial.",
        )
    item = get_parecer(db, user, parecer_id)
    if not is_admin and item.status != "PENDENTE":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Somente parecer pendente pode ser cancelado pelo negociador.",
        )
    before = serialize_parecer(item)
    _apply_status(item, payload.status)
    db.flush()
    record_audit(
        db,
        user=user,
        action="status_update",
        entity_type="parecer",
        entity_id=item.id,
        before=before,
        after=serialize_parecer(item),
    )
    bump_version(db, "pareceres")
    db.commit()
    db.refresh(item)
    return serialize_parecer(item)


def delete_parecer(db: Session, user: User, parecer_id: int):
    item = get_parecer(db, user, parecer_id)
    before = serialize_parecer(item)
    record_audit(db, user=user, action="delete", entity_type="parecer", entity_id=item.id, before=before)
    bump_version(db, "pareceres")
    db.delete(item)
    db.commit()
