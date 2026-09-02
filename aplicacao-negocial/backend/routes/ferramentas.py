from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
import csv
from io import StringIO
import re
from sqlalchemy.orm import Session

from backend.auth.security import get_current_user, require_admin
from backend.database import get_db
from backend.models import User
from backend.schemas.ferramenta import (
    FerramentaCommentInput,
    FerramentaDefinitionInput,
    FerramentaRecordInput,
    FerramentaTransitionInput,
)
from backend.services.ferramenta_service import (
    add_comment,
    create_next_draft,
    create_record,
    create_tool_draft,
    get_published_tool,
    get_record,
    list_admin_tools,
    list_available_tools,
    list_records,
    publish_tool,
    serialize_definition,
    serialize_record,
    transition_record,
    update_record,
    update_tool_draft,
)
from backend.services.ferramenta_attachment_service import attachment_file, remove_attachment, store_attachments


router = APIRouter(prefix="/ferramentas", tags=["ferramentas"])


@router.get("")
def listar_ferramentas(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"items": list_available_tools(db, user)}


@router.get("/{slug}")
def obter_ferramenta(slug: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tool, version = get_published_tool(db, slug, user)
    from backend.services.ferramenta_service import _permission
    return {"item": serialize_definition(version, _permission(db, tool, user))}


@router.get("/{slug}/registros")
def listar_registros(
    slug: str,
    status_codigo: str = "",
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tool, _ = get_published_tool(db, slug, user)
    return {"items": list_records(db, tool, user, status_codigo.upper(), limit)}


@router.get("/{slug}/relatorio.csv")
def exportar_registros(
    slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tool, version = get_published_tool(db, slug, user, "export")
    items = list_records(db, tool, user, limit=5000)
    fields = sorted(
        (field for field in version.campos if field.visivel_negocial),
        key=lambda field: (field.etapa, field.ordem, field.id),
    )
    output = StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(["STATUS", *(field.nome for field in fields), "ATUALIZADO EM"])
    for item in items:
        payload = item.get("payload") or {}
        values = []
        for field in fields:
            value = payload.get(field.chave, "")
            values.append(", ".join(map(str, value)) if isinstance(value, list) else value)
        writer.writerow([item.get("status") or "", *values, item.get("updated_at") or ""])
    safe_slug = re.sub(r"[^a-z0-9_-]+", "_", slug.lower())
    return Response(
        content=("\ufeff" + output.getvalue()).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="relatorio_{safe_slug}.csv"'},
    )


@router.get("/{slug}/registros/{record_id}")
def obter_registro(
    slug: str,
    record_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tool, _ = get_published_tool(db, slug, user)
    return {"item": serialize_record(get_record(db, tool, user, record_id), include_history=True)}


@router.post("/{slug}/registros", status_code=status.HTTP_201_CREATED)
def cadastrar_registro(
    slug: str,
    payload: FerramentaRecordInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tool, version = get_published_tool(db, slug, user, "create")
    return {"item": create_record(db, tool, version, user, payload.payload, payload.status)}


@router.put("/{slug}/registros/{record_id}")
def atualizar_registro(
    slug: str,
    record_id: int,
    payload: FerramentaRecordInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tool, version = get_published_tool(db, slug, user, "edit")
    return {
        "item": update_record(
            db,
            tool,
            user,
            record_id,
            payload.payload,
            payload.status,
            policy_version=version,
        )
    }


@router.post("/{slug}/registros/{record_id}/transicoes")
def transicionar_registro(
    slug: str,
    record_id: int,
    payload: FerramentaTransitionInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tool, _ = get_published_tool(db, slug, user)
    return {"item": transition_record(db, tool, user, record_id, payload.status, payload.justificativa)}


@router.post("/{slug}/registros/{record_id}/comentarios", status_code=status.HTTP_201_CREATED)
def comentar_registro(
    slug: str,
    record_id: int,
    payload: FerramentaCommentInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tool, _ = get_published_tool(db, slug, user)
    return {"item": add_comment(db, tool, user, record_id, payload.texto)}


@router.post("/{slug}/registros/{record_id}/anexos", status_code=status.HTTP_201_CREATED)
async def anexar_arquivos(
    slug: str,
    record_id: int,
    campo: str = Form(...),
    arquivos: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tool, _ = get_published_tool(db, slug, user, "edit")
    record = get_record(db, tool, user, record_id)
    return {"items": await store_attachments(db, tool, user, record, campo, arquivos)}


@router.get("/{slug}/registros/{record_id}/anexos/{attachment_id}")
def baixar_anexo(
    slug: str,
    record_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tool, _ = get_published_tool(db, slug, user)
    record = get_record(db, tool, user, record_id)
    target, attachment = attachment_file(db, record, attachment_id)
    return FileResponse(target, media_type=attachment.content_type, filename=attachment.nome)


@router.delete("/{slug}/registros/{record_id}/anexos/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_anexo(
    slug: str,
    record_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tool, _ = get_published_tool(db, slug, user, "edit")
    record = get_record(db, tool, user, record_id)
    remove_attachment(db, tool, user, record, attachment_id)


@router.get("/admin/definicoes/todas")
def listar_definicoes_admin(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    return {"items": list_admin_tools(db, user)}


@router.post("/admin/definicoes", status_code=status.HTTP_201_CREATED)
def criar_definicao_admin(
    payload: FerramentaDefinitionInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    return {"item": create_tool_draft(db, user, payload)}


@router.put("/admin/definicoes/{tool_id}")
def atualizar_definicao_admin(
    tool_id: int,
    payload: FerramentaDefinitionInput,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    return {"item": update_tool_draft(db, user, tool_id, payload)}


@router.post("/admin/definicoes/{tool_id}/publicar")
def publicar_definicao_admin(
    tool_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    return {"item": publish_tool(db, user, tool_id)}


@router.post("/admin/definicoes/{tool_id}/nova-versao", status_code=status.HTTP_201_CREATED)
def nova_versao_admin(
    tool_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    return {"item": create_next_draft(db, user, tool_id)}
