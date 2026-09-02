from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.models import AuditLog, User


AUDIT_IGNORE_KEYS = {"updated_at"}


def public_diff(before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    before = before or {}
    after = after or {}
    keys = (set(before) | set(after)) - AUDIT_IGNORE_KEYS
    diff: dict[str, dict[str, Any]] = {}
    for key in sorted(keys):
        old_value = before.get(key)
        new_value = after.get(key)
        if old_value != new_value:
            diff[key] = {"antes": old_value, "depois": new_value}
    return diff


def record_audit(
    db: Session,
    *,
    user: User | None,
    action: str,
    entity_type: str,
    entity_id: int | str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
    source: str = "negocial",
) -> AuditLog:
    log = AuditLog(
        actor_user_id=getattr(user, "id", None),
        actor_username=getattr(user, "username", None),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        source=source,
        before_json=before,
        after_json=after,
        diff_json=public_diff(before, after),
        reason=reason,
    )
    db.add(log)
    return log


def serialize_audit(log: AuditLog) -> dict[str, Any]:
    return {
        "id": log.id,
        "actor_user_id": log.actor_user_id,
        "actor_username": log.actor_username,
        "action": log.action,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "source": log.source,
        "before": log.before_json,
        "after": log.after_json,
        "diff": log.diff_json,
        "reason": log.reason,
        "created_at": log.created_at.isoformat() if log.created_at else "",
    }
