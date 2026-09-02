from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from backend.auth.security import get_current_user, require_permission, require_tool
from backend.database import get_db
from backend.models import User
from backend.schemas.parecer import ParecerCreate, ParecerStatusUpdate, ParecerUpdate
from backend.services.parecer_service import (
    create_parecer,
    delete_parecer,
    get_parecer,
    list_pareceres,
    serialize_parecer,
    update_parecer,
    update_parecer_status,
)


router = APIRouter(prefix="/pareceres", tags=["pareceres"])


@router.get("")
def listar_pareceres(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_tool(user, "pareceres", db)
    require_permission(user, "pareceres:read")
    return {"items": list_pareceres(db, user)}


@router.get("/{parecer_id}")
def obter_parecer(
    parecer_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_tool(user, "pareceres", db)
    require_permission(user, "pareceres:read")
    return {"item": serialize_parecer(get_parecer(db, user, parecer_id))}


@router.post("", status_code=status.HTTP_201_CREATED)
def cadastrar_parecer(
    payload: ParecerCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_tool(user, "pareceres", db)
    require_permission(user, "pareceres:write")
    return {"item": create_parecer(db, user, payload)}


@router.put("/{parecer_id}")
def atualizar_parecer(
    parecer_id: int,
    payload: ParecerUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_tool(user, "pareceres", db)
    require_permission(user, "pareceres:write")
    return {"item": update_parecer(db, user, parecer_id, payload)}


@router.patch("/{parecer_id}/status")
def atualizar_status_parecer(
    parecer_id: int,
    payload: ParecerStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_tool(user, "pareceres", db)
    require_permission(user, "pareceres:write")
    return {"item": update_parecer_status(db, user, parecer_id, payload)}


@router.delete("/{parecer_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_parecer(
    parecer_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_tool(user, "pareceres", db)
    require_permission(user, "pareceres:write")
    delete_parecer(db, user, parecer_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
