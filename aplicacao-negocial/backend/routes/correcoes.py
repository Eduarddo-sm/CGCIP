from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.auth.security import get_current_user
from backend.database import DB_SCHEMA, IS_POSTGRES, get_db
from backend.models import User


router = APIRouter(prefix="/correcoes", tags=["correcoes"])


def table_name(name: str) -> str:
    return f"{DB_SCHEMA}.{name}" if IS_POSTGRES and DB_SCHEMA else name


@router.get("")
def listar_correcoes(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.execute(
        text(
            f"""
            SELECT
                c.id,
                c.producao_id,
                c.campo,
                c.valor_anterior,
                c.valor_novo,
                c.corrigido_por,
                c.motivo,
                c.criado_em,
                pr.cliente
            FROM {table_name("producao_correcoes")} c
            JOIN {table_name("producao_registros")} pr ON pr.id = c.producao_id
            WHERE pr.user_id = :user_id
              AND COALESCE(c.visualizado_pelo_negociador, FALSE) = FALSE
              AND UPPER(COALESCE(c.campo, '')) NOT IN ('GECOR', 'UF', 'URF', 'DT AJUIZAMENTO')
            ORDER BY c.criado_em DESC, c.id DESC
            LIMIT 50
            """
        ),
        {"user_id": user.id},
    ).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.post("/{correcao_id}/visualizar")
def marcar_visualizada(
    correcao_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = db.execute(
        text(
            f"""
            UPDATE {table_name("producao_correcoes")} c
            SET visualizado_pelo_negociador = TRUE
            FROM {table_name("producao_registros")} pr
            WHERE c.id = :correcao_id
              AND pr.id = c.producao_id
              AND pr.user_id = :user_id
            """
        ),
        {"correcao_id": correcao_id, "user_id": user.id},
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Correcao nao encontrada.")
    return {"ok": True}
