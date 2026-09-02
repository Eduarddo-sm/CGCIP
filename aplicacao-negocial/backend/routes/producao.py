from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from backend.auth.security import get_current_user, require_permission, require_tool
from backend.database import get_db
from backend.models import User
from backend.schemas.producao import (
    ProducaoCreate,
    ProducaoStatusUpdate,
    ProducaoUpdate,
    ProducaoViradaMensalConfirm,
)
from backend.services.producao_service import (
    confirm_month_rollover,
    create_producao,
    delete_producao,
    get_producao,
    get_producao_schema,
    get_month_rollover,
    list_producao,
    serialize_producao,
    update_producao,
    update_producao_status,
)
from backend.services.user_goal_service import goals_by_competence


router = APIRouter(prefix="/producao", tags=["producao"])


@router.get("")
def listar_producao(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_tool(user, "producao")
    require_permission(user, "producao:read")
    items = list_producao(db, user)
    competences = {str(item.get("competencia") or "")[:7] for item in items}
    return {"items": items, "metas": goals_by_competence(db, user, competences)}


@router.get("/schema")
def obter_schema_producao(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_tool(user, "producao")
    require_permission(user, "producao:read")
    return get_producao_schema(db, user)


@router.get("/virada-mensal")
def obter_virada_mensal(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_tool(user, "producao")
    require_permission(user, "producao:read")
    return get_month_rollover(db, user)


@router.post("/virada-mensal/confirmar")
def confirmar_virada_mensal(
    payload: ProducaoViradaMensalConfirm,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_tool(user, "producao")
    require_permission(user, "producao:write")
    return confirm_month_rollover(
        db,
        user,
        [
            (decisao.producao_id, decisao.status, decisao.jogar_proximo_mes)
            for decisao in payload.decisoes
        ],
    )


@router.get("/{producao_id}")
def obter_producao(
    producao_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_tool(user, "producao")
    require_permission(user, "producao:read")
    return {"item": serialize_producao(get_producao(db, user, producao_id))}


@router.post("", status_code=status.HTTP_201_CREATED)
def cadastrar_producao(
    payload: ProducaoCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_tool(user, "producao")
    require_permission(user, "producao:write")
    return {"item": create_producao(db, user, payload)}


@router.put("/{producao_id}")
def atualizar_producao(
    producao_id: int,
    payload: ProducaoUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_tool(user, "producao")
    require_permission(user, "producao:write")
    return {"item": update_producao(db, user, producao_id, payload)}


@router.patch("/{producao_id}/status")
def atualizar_status_producao(
    producao_id: int,
    payload: ProducaoStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_tool(user, "producao")
    require_permission(user, "producao:write")
    return {"item": update_producao_status(db, user, producao_id, payload)}


@router.delete("/{producao_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_producao(
    producao_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_tool(user, "producao")
    require_permission(user, "producao:write")
    delete_producao(db, user, producao_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
