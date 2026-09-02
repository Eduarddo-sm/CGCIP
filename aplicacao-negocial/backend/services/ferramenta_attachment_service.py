from __future__ import annotations

import hashlib
import json
import mimetypes
from pathlib import Path
import re
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import Ferramenta, FerramentaAnexo, FerramentaCampo, FerramentaEvento, User
from backend.models.user import utcnow
from backend.services.audit_service import record_audit
from backend.services.version_service import bump_version


DEFAULT_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "csv", "txt", "png", "jpg", "jpeg"}
BLOCKED_EXTENSIONS = {"exe", "dll", "bat", "cmd", "com", "js", "jse", "msi", "ps1", "scr", "vbs"}


def attachment_roots() -> list[Path]:
    shared_data = Path(__file__).resolve().parents[3] / "data"
    default_root = shared_data / "ferramenta-anexos"
    config_path = shared_data / "ferramenta_attachment_storage.json"
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        payload = payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        payload = {}
    configured = str(payload.get("path") or settings.ferramenta_attachments_dir or "").strip()
    root = Path(configured).expanduser() if configured else default_root
    root.mkdir(parents=True, exist_ok=True)
    roots = [root.resolve()]
    for raw in payload.get("legacy_paths") or []:
        try:
            legacy = Path(str(raw)).expanduser().resolve()
        except (OSError, ValueError):
            continue
        if legacy not in roots:
            roots.append(legacy)
    return roots


def attachment_root() -> Path:
    return attachment_roots()[0]


def _safe_name(value: str) -> str:
    name = Path(str(value or "arquivo")).name.strip() or "arquivo"
    return re.sub(r"[\x00-\x1f]", "", name)[:255]


def _field_config(field: FerramentaCampo) -> tuple[set[str], int, bool, int]:
    validation = dict(field.validacao_json or {})
    extensions = validation.get("extensoes") or field.opcoes_json or DEFAULT_EXTENSIONS
    allowed = {str(item).lower().strip().lstrip(".") for item in extensions if str(item).strip()}
    allowed -= BLOCKED_EXTENSIONS
    max_mb = max(1, min(int(validation.get("max_mb") or 15), 100))
    multiple = bool(validation.get("multiplo", False))
    max_files = max(1, min(int(validation.get("max_arquivos") or (10 if multiple else 1)), 20))
    return allowed or DEFAULT_EXTENSIONS, max_mb * 1024 * 1024, multiple, max_files


def serialize_attachment(item: FerramentaAnexo) -> dict:
    return {
        "id": item.id,
        "campo": item.campo_chave or "",
        "nome": item.nome,
        "content_type": item.content_type or "application/octet-stream",
        "tamanho": int(item.tamanho or 0),
        "sha256": item.sha256 or "",
        "usuario": item.username or "",
        "created_at": item.created_at.isoformat() if item.created_at else "",
    }


def _attachment_field(record, field_key: str) -> FerramentaCampo:
    key = str(field_key or "").strip().upper()
    field = next((item for item in record.versao.campos if item.chave == key), None)
    if not field or field.tipo != "arquivo" or not field.visivel_negocial:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Campo de anexo invalido.")
    if field.somente_leitura:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Este anexo e somente leitura.")
    return field


async def store_attachments(db: Session, tool: Ferramenta, user: User, record, field_key: str, uploads: list[UploadFile]) -> list[dict]:
    field = _attachment_field(record, field_key)
    allowed, max_bytes, multiple, max_files = _field_config(field)
    files = [item for item in uploads if item and item.filename]
    if not files:
        raise HTTPException(status_code=422, detail="Selecione ao menos um arquivo.")
    if len(files) > max_files or (not multiple and len(files) > 1):
        raise HTTPException(status_code=422, detail=f"Este campo aceita no maximo {max_files} arquivo(s).")

    existing = [item for item in record.anexos if item.active and item.campo_chave == field.chave]
    if multiple and len(existing) + len(files) > max_files:
        raise HTTPException(status_code=422, detail=f"Este campo aceita no maximo {max_files} arquivo(s).")

    root = attachment_root()
    relative_dir = Path(str(tool.id)) / str(record.id) / utcnow().strftime("%Y/%m")
    target_dir = root / relative_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    created_paths: list[Path] = []
    created_rows: list[FerramentaAnexo] = []
    try:
        for upload in files:
            original_name = _safe_name(upload.filename or "arquivo")
            extension = Path(original_name).suffix.lower().lstrip(".")
            if not extension or extension not in allowed or extension in BLOCKED_EXTENSIONS:
                raise HTTPException(status_code=422, detail=f"Formato nao permitido: {original_name}.")
            content = await upload.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise HTTPException(status_code=413, detail=f"{original_name} excede o limite de {max_bytes // (1024 * 1024)} MB.")
            if not content:
                raise HTTPException(status_code=422, detail=f"{original_name} esta vazio.")
            stored_name = f"{uuid4().hex}.{extension}"
            target = target_dir / stored_name
            target.write_bytes(content)
            created_paths.append(target)
            row = FerramentaAnexo(
                registro_id=record.id,
                user_id=user.id,
                username=user.username,
                campo_chave=field.chave,
                nome=original_name,
                content_type=upload.content_type or mimetypes.guess_type(original_name)[0],
                storage_key=str(relative_dir / stored_name).replace("\\", "/"),
                tamanho=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                active=True,
            )
            db.add(row)
            created_rows.append(row)

        if not multiple:
            for item in existing:
                item.active = False
                item.removed_at = utcnow()

        active_names = ([item.nome for item in existing] if multiple else []) + [item.nome for item in created_rows]
        payload = dict(record.payload_json or {})
        payload[field.chave] = active_names if multiple else active_names[-1]
        record.payload_json = payload
        record.updated_at = utcnow()
        db.add(FerramentaEvento(
            registro_id=record.id,
            actor_user_id=user.id,
            actor_username=user.username,
            tipo="ANEXO_ADICIONADO",
            after_json={"campo": field.chave, "arquivos": [item.nome for item in created_rows]},
        ))
        db.flush()
        record_audit(
            db, user=user, action="attachment_add", entity_type=f"ferramenta:{tool.slug}",
            entity_id=record.id, after={"campo": field.chave, "arquivos": [item.nome for item in created_rows]},
        )
        bump_version(db, f"ferramenta:{tool.slug}")
        db.commit()
        return [serialize_attachment(item) for item in created_rows]
    except Exception:
        db.rollback()
        for target in created_paths:
            target.unlink(missing_ok=True)
        raise


def attachment_file(db: Session, record, attachment_id: int) -> tuple[Path, FerramentaAnexo]:
    item = db.query(FerramentaAnexo).filter(
        FerramentaAnexo.id == attachment_id,
        FerramentaAnexo.registro_id == record.id,
        FerramentaAnexo.active.is_(True),
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Anexo nao encontrado.")
    target = None
    for root in attachment_roots():
        candidate = (root / item.storage_key).resolve()
        if root in candidate.parents and candidate.is_file():
            target = candidate
            break
    if target is None:
        raise HTTPException(status_code=404, detail="Arquivo do anexo nao encontrado.")
    return target, item


def remove_attachment(db: Session, tool: Ferramenta, user: User, record, attachment_id: int) -> None:
    item = db.query(FerramentaAnexo).filter(
        FerramentaAnexo.id == attachment_id,
        FerramentaAnexo.registro_id == record.id,
        FerramentaAnexo.active.is_(True),
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Anexo nao encontrado.")
    item.active = False
    item.removed_at = utcnow()
    active = db.query(FerramentaAnexo).filter(
        FerramentaAnexo.registro_id == record.id,
        FerramentaAnexo.campo_chave == item.campo_chave,
        FerramentaAnexo.active.is_(True),
        FerramentaAnexo.id != item.id,
    ).all()
    field = next((field for field in record.versao.campos if field.chave == item.campo_chave), None)
    payload = dict(record.payload_json or {})
    multiple = bool((field.validacao_json or {}).get("multiplo", False)) if field else False
    payload[item.campo_chave] = [row.nome for row in active] if multiple else (active[-1].nome if active else None)
    record.payload_json = payload
    record.updated_at = utcnow()
    db.add(FerramentaEvento(
        registro_id=record.id, actor_user_id=user.id, actor_username=user.username,
        tipo="ANEXO_REMOVIDO", before_json={"campo": item.campo_chave, "arquivo": item.nome},
    ))
    record_audit(
        db, user=user, action="attachment_remove", entity_type=f"ferramenta:{tool.slug}",
        entity_id=record.id, before={"campo": item.campo_chave, "arquivo": item.nome},
    )
    bump_version(db, f"ferramenta:{tool.slug}")
    db.commit()
