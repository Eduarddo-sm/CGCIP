from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database import DB_SCHEMA, IS_POSTGRES


VERSION_TABLE = f"{DB_SCHEMA}.operational_versions" if DB_SCHEMA else "operational_versions"


def bump_version(db: Session, scope: str) -> None:
    now_expr = "NOW()" if IS_POSTGRES else "CURRENT_TIMESTAMP"
    db.execute(
        text(
            f"""
            INSERT INTO {VERSION_TABLE} (scope, version, updated_at)
            VALUES (:scope, 1, {now_expr})
            ON CONFLICT (scope)
            DO UPDATE SET version = operational_versions.version + 1, updated_at = {now_expr}
            """
        ),
        {"scope": scope},
    )


def get_versions(db: Session) -> dict[str, dict[str, str | int]]:
    rows = db.execute(
        text(
            f"""
            SELECT scope, version, updated_at
            FROM {VERSION_TABLE}
            ORDER BY scope
            """
        )
    ).mappings().all()
    return {
        row["scope"]: {
            "version": int(row["version"]),
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else "",
        }
        for row in rows
    }
