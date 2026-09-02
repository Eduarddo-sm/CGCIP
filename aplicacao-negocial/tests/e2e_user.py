from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.auth.security import hash_password
from backend.database import SessionLocal
from backend.models import ProducaoRegistro, User


def main() -> int:
    if len(sys.argv) < 3 or sys.argv[1] not in {"create", "delete"}:
        raise SystemExit("Uso: e2e_user.py create|delete USUARIO [SENHA]")
    action, username = sys.argv[1], sys.argv[2].strip()
    if not username.startswith("__e2e_negocial_"):
        raise SystemExit("Somente usuarios temporarios E2E podem ser gerenciados.")
    with SessionLocal() as db:
        existing = db.query(User).filter(User.username == username).first()
        if action == "delete":
            if existing:
                db.query(ProducaoRegistro).filter(ProducaoRegistro.user_id == existing.id).delete(synchronize_session=False)
                db.delete(existing)
                db.commit()
            return 0
        if len(sys.argv) < 4 or len(sys.argv[3]) < 12:
            raise SystemExit("Senha temporaria invalida.")
        if existing:
            db.delete(existing)
            db.flush()
        db.add(User(
            username=username,
            password_hash=hash_password(sys.argv[3]),
            role="USER",
            carteira="GAMMA",
            meta_pagamento=70000,
            enabled_tools="producao,pareceres",
            active=True,
        ))
        db.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
