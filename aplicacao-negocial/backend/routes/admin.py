from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.auth.security import get_current_user, require_admin
from backend.database import get_db
from backend.models import AuditLog, User
from backend.services.audit_service import serialize_audit
from backend.services.version_service import get_versions


router = APIRouter(tags=["admin"])


@router.get("/auditoria")
def listar_auditoria(
    entity_type: str = "",
    entity_id: str = "",
    action: str = "",
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    query = db.query(AuditLog)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    if action:
        query = query.filter(AuditLog.action == action)
    items = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).all()
    return {"items": [serialize_audit(item) for item in items]}


@router.get("/sync/version")
def versoes_operacionais(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return {"versions": get_versions(db)}
