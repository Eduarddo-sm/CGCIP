from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
import unicodedata
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, selectinload

from backend.models import (
    Ferramenta,
    FerramentaCampo,
    FerramentaComentario,
    FerramentaEvento,
    FerramentaPermissao,
    FerramentaRegistro,
    FerramentaStatus,
    FerramentaTransicao,
    FerramentaVersao,
    User,
)
from backend.models.user import utcnow
from backend.schemas.ferramenta import FerramentaDefinitionInput, FerramentaStatusInput
from backend.services.audit_service import record_audit
from backend.services.version_service import bump_version


def slugify(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def is_admin(user: User) -> bool:
    return str(user.role or "").upper() == "ADMIN"


def _definition_query(db: Session):
    return db.query(FerramentaVersao).options(
        selectinload(FerramentaVersao.ferramenta),
        selectinload(FerramentaVersao.campos),
        selectinload(FerramentaVersao.statuses),
        selectinload(FerramentaVersao.transicoes),
    )


def _permission(db: Session, tool: Ferramenta, user: User) -> FerramentaPermissao | None:
    if is_admin(user):
        return FerramentaPermissao(
            ferramenta_id=tool.id,
            user_id=user.id,
            pode_visualizar=True,
            pode_criar=True,
            pode_editar=True,
            pode_transicionar=True,
            pode_exportar=True,
        )
    rows = (
        db.query(FerramentaPermissao)
        .filter(
            FerramentaPermissao.ferramenta_id == tool.id,
            or_(
                FerramentaPermissao.user_id == user.id,
                and_(
                    FerramentaPermissao.user_id.is_(None),
                    func.upper(FerramentaPermissao.carteira) == str(user.carteira or "").upper(),
                ),
            ),
        )
        .all()
    )
    return next((row for row in rows if row.user_id == user.id), rows[0] if rows else None)


def require_tool_permission(db: Session, tool: Ferramenta, user: User, action: str) -> FerramentaPermissao:
    permission = _permission(db, tool, user)
    attr = {
        "view": "pode_visualizar",
        "create": "pode_criar",
        "edit": "pode_editar",
        "transition": "pode_transicionar",
        "export": "pode_exportar",
    }[action]
    if not permission or not getattr(permission, attr):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ferramenta nao habilitada para este usuario.")
    return permission


def serialize_permission(permission: FerramentaPermissao | None) -> dict[str, bool]:
    return {
        "visualizar": bool(permission and permission.pode_visualizar),
        "criar": bool(permission and permission.pode_criar),
        "editar": bool(permission and permission.pode_editar),
        "transicionar": bool(permission and permission.pode_transicionar),
        "exportar": bool(permission and permission.pode_exportar),
    }


def serialize_definition(version: FerramentaVersao, permission: FerramentaPermissao | None = None) -> dict[str, Any]:
    tool = version.ferramenta
    return {
        "id": tool.id,
        "nome": tool.nome,
        "slug": tool.slug,
        "descricao": tool.descricao,
        "tipo": tool.tipo,
        "icone": tool.icone,
        "cor": tool.cor,
        "active": tool.active,
        "destaque_gerencial": tool.destaque_gerencial,
        "versao": version.numero,
        "versao_id": version.id,
        "versao_status": version.status,
        "configuracao": version.configuracao_json or {},
        "campos": [
            {
                "id": field.id,
                "chave": field.chave,
                "nome": field.nome,
                "tipo": field.tipo,
                "ordem": field.ordem,
                "etapa": field.etapa,
                "obrigatorio": field.obrigatorio,
                "somente_leitura": field.somente_leitura,
                "visivel_negocial": field.visivel_negocial,
                "visivel_gerencial": field.visivel_gerencial,
                "opcoes": field.opcoes_json or [],
                "validacao": field.validacao_json or {},
                "condicao": field.condicao_json or {},
                "valor_padrao": field.valor_padrao_json,
            }
            for field in sorted(version.campos, key=lambda item: (item.etapa, item.ordem, item.id))
        ],
        "statuses": [
            {
                "codigo": item.codigo,
                "nome": item.nome,
                "cor": item.cor,
                "ordem": item.ordem,
                "inicial": item.inicial,
                "final": item.final,
            }
            for item in sorted(version.statuses, key=lambda item: (item.ordem, item.id))
        ],
        "transicoes": [
            {
                "origem_codigo": item.origem_codigo,
                "destino_codigo": item.destino_codigo,
                "nome": item.nome,
                "exige_justificativa": item.exige_justificativa,
                "permite_negociador": item.permite_negociador,
                "permite_gerencial": item.permite_gerencial,
                "configuracao": item.configuracao_json or {},
            }
            for item in version.transicoes
        ],
        "permissoes": serialize_permission(permission),
        "created_at": version.created_at.isoformat() if version.created_at else "",
        "published_at": version.published_at.isoformat() if version.published_at else None,
    }


def list_available_tools(db: Session, user: User) -> list[dict[str, Any]]:
    from backend.auth.security import wallet_tool_enabled
    versions = (
        _definition_query(db)
        .join(Ferramenta)
        .filter(
            Ferramenta.active.is_(True),
            Ferramenta.deleted_at.is_(None),
            FerramentaVersao.status == "PUBLICADA",
        )
        .order_by(Ferramenta.nome)
        .all()
    )
    result = []
    for version in versions:
        permission = _permission(db, version.ferramenta, user)
        if permission and permission.pode_visualizar and wallet_tool_enabled(db, user, f"tool:{version.ferramenta.id}"):
            result.append(serialize_definition(version, permission))
    return result


def get_published_tool(db: Session, slug: str, user: User, action: str = "view") -> tuple[Ferramenta, FerramentaVersao]:
    version = (
        _definition_query(db)
        .join(Ferramenta)
        .filter(
            Ferramenta.slug == slug,
            Ferramenta.active.is_(True),
            Ferramenta.deleted_at.is_(None),
            FerramentaVersao.status == "PUBLICADA",
        )
        .first()
    )
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ferramenta nao encontrada.")
    from backend.auth.security import wallet_tool_enabled
    if not wallet_tool_enabled(db, user, f"tool:{version.ferramenta.id}"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ferramenta desativada para esta carteira.")
    require_tool_permission(db, version.ferramenta, user, action)
    return version.ferramenta, version


def _condition_matches(condition: dict, payload: dict) -> bool:
    if not condition:
        return True
    key = str(condition.get("campo") or "")
    operator = str(condition.get("operador") or "igual")
    expected = condition.get("valor")
    actual = payload.get(key)
    normalize = lambda value: value.strip().casefold() if isinstance(value, str) else value
    def equals(left, right):
        if isinstance(left, list):
            return any(normalize(item) == normalize(right) for item in left)
        return normalize(left) == normalize(right)
    if operator == "em":
        expected_values = expected if isinstance(expected, list) else [expected]
        return any(equals(actual, item) for item in expected_values)
    if operator == "nao_em":
        expected_values = expected if isinstance(expected, list) else [expected]
        return not any(equals(actual, item) for item in expected_values)
    if operator == "diferente":
        return not equals(actual, expected)
    if operator == "preenchido":
        return actual not in (None, "", [])
    if operator == "vazio":
        return actual in (None, "", [])
    if operator == "contem":
        return str(expected or "").strip().casefold() in str(actual or "").strip().casefold()
    if operator in {"maior", "maior_igual", "menor", "menor_igual"}:
        try:
            actual_number = Decimal(str(actual).replace(",", "."))
            expected_number = Decimal(str(expected).replace(",", "."))
        except (InvalidOperation, TypeError, ValueError):
            return False
        if operator == "maior":
            return actual_number > expected_number
        if operator == "maior_igual":
            return actual_number >= expected_number
        if operator == "menor":
            return actual_number < expected_number
        return actual_number <= expected_number
    return equals(actual, expected)


def _decimal_value(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    cleaned = re.sub(r"[^0-9,.\-]", "", str(value))
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned or "0")
    except InvalidOperation as exc:
        raise ValueError("O calculo utiliza um campo que nao e numerico.") from exc


def _calculate_value(calculation: dict, payload: dict) -> str | None:
    if not calculation or not calculation.get("campo_base"):
        return None
    operation = str(calculation.get("operacao") or "percentual").lower()
    left = _decimal_value(payload.get(str(calculation.get("campo_base") or "")))
    secondary_key = str(calculation.get("campo_secundario") or "")
    right = _decimal_value(payload.get(secondary_key)) if secondary_key else _decimal_value(calculation.get("valor"))
    if operation == "percentual":
        result = left * right / Decimal("100")
    elif operation == "soma":
        result = left + right
    elif operation == "subtracao":
        result = left - right
    elif operation == "multiplicacao":
        result = left * right
    elif operation == "divisao":
        if right == 0:
            raise ValueError("Nao e possivel dividir por zero.")
        result = left / right
    else:
        raise ValueError("Operacao de calculo invalida.")
    return str(result.quantize(Decimal("0.01")))


def _apply_calculated_fields(version: FerramentaVersao, payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    # Repetir permite que um campo calculado dependa de outro, sem aceitar formulas livres.
    for _ in range(max(1, len(version.campos))):
        changed = False
        for field in version.campos:
            calculation = dict((field.validacao_json or {}).get("calculo") or {})
            if not calculation or not _condition_matches(calculation.get("condicao") or {}, result):
                continue
            value = _calculate_value(calculation, result)
            if value is not None and result.get(field.chave) != value:
                result[field.chave] = value
                changed = True
        if not changed:
            break
    return result


def _normalize_field_value(field: FerramentaCampo, value: Any) -> Any:
    if value in (None, ""):
        return None
    validation = field.validacao_json or {}
    if field.tipo in {"texto", "texto_longo", "select", "usuario", "carteira"}:
        result = " ".join(str(value).strip().split()) if field.tipo != "texto_longo" else str(value).strip()
        max_length = validation.get("max_length")
        min_length = validation.get("min_length")
        if min_length and len(result) < int(min_length):
            raise ValueError(f"{field.nome} exige ao menos {min_length} caracteres.")
        if max_length and len(result) > int(max_length):
            raise ValueError(f"{field.nome} aceita no maximo {max_length} caracteres.")
        if field.tipo == "select" and field.opcoes_json and result not in field.opcoes_json:
            raise ValueError(f"Opcao invalida para {field.nome}.")
        pattern = validation.get("regex")
        if pattern and not re.fullmatch(str(pattern), result):
            raise ValueError(validation.get("mensagem") or f"Valor invalido para {field.nome}.")
        return result
    if field.tipo in {"numero", "moeda"}:
        cleaned = re.sub(r"[^0-9,.\-]", "", str(value))
        if "," in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        try:
            number = Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError(f"{field.nome} deve ser numerico.") from exc
        minimum = validation.get("min")
        maximum = validation.get("max")
        if minimum is not None and number < Decimal(str(minimum)):
            raise ValueError(f"{field.nome} deve ser maior ou igual a {minimum}.")
        if maximum is not None and number > Decimal(str(maximum)):
            raise ValueError(f"{field.nome} deve ser menor ou igual a {maximum}.")
        return str(number.quantize(Decimal("0.01"))) if field.tipo == "moeda" else str(number)
    if field.tipo == "data":
        if isinstance(value, (date, datetime)):
            return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
        try:
            return date.fromisoformat(str(value)).isoformat()
        except ValueError as exc:
            raise ValueError(f"{field.nome} deve conter uma data valida.") from exc
    if field.tipo == "boolean":
        return value if isinstance(value, bool) else str(value).lower() in {"1", "true", "sim", "yes"}
    if field.tipo == "multiselect":
        values = value if isinstance(value, list) else [item.strip() for item in str(value).split(",")]
        values = list(dict.fromkeys(item for item in values if item not in (None, "")))
        invalid = [item for item in values if field.opcoes_json and item not in field.opcoes_json]
        if invalid:
            raise ValueError(f"Opcao invalida para {field.nome}: {invalid[0]}.")
        return values
    if field.tipo == "arquivo":
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return str(value).strip()
    return value


def validate_payload(version: FerramentaVersao, raw_payload: dict[str, Any], user: User, partial: bool = False) -> dict[str, Any]:
    fields = {field.chave: field for field in version.campos}
    unknown = set(raw_payload) - set(fields)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Campo desconhecido: {sorted(unknown)[0]}.",
        )
    prepared = dict(raw_payload)
    for field in version.campos:
        if field.chave not in prepared and not partial:
            prepared[field.chave] = field.valor_padrao_json
        automatic_fill = str((field.validacao_json or {}).get("preenchimento_automatico") or "").lower()
        if not partial and field.tipo == "data" and automatic_fill == "today" and prepared.get(field.chave) in (None, ""):
            prepared[field.chave] = date.today().isoformat()
        if field.tipo == "usuario" and field.somente_leitura:
            prepared[field.chave] = user.username
        if field.tipo == "carteira" and field.somente_leitura:
            prepared[field.chave] = user.carteira
    prepared = _apply_calculated_fields(version, prepared)
    payload: dict[str, Any] = {}
    for field in version.campos:
        calculation = dict((field.validacao_json or {}).get("calculo") or {})
        if partial and field.chave not in raw_payload and not calculation:
            continue
        raw_value = prepared.get(field.chave)
        required = field.obrigatorio and _condition_matches(field.condicao_json or {}, {**prepared, **payload})
        if required and raw_value in (None, "", []):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Preencha o campo obrigatorio: {field.nome}.",
            )
        try:
            payload[field.chave] = _normalize_field_value(field, raw_value)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return payload


def serialize_record(record: FerramentaRegistro, include_history: bool = False) -> dict[str, Any]:
    item = {
        "id": record.id,
        "ferramenta_id": record.ferramenta_id,
        "ferramenta": record.ferramenta.slug if record.ferramenta else None,
        "versao": record.versao.numero if record.versao else None,
        "owner_user_id": record.owner_user_id,
        "negociador": record.owner_username,
        "carteira": record.carteira,
        "status": record.status_codigo,
        "titulo": record.titulo,
        "payload": record.payload_json or {},
        "created_at": record.created_at.isoformat() if record.created_at else "",
        "updated_at": record.updated_at.isoformat() if record.updated_at else "",
    }
    if include_history:
        item["anexos"] = [
            {
                "id": attachment.id,
                "campo": attachment.campo_chave or "",
                "nome": attachment.nome,
                "content_type": attachment.content_type or "application/octet-stream",
                "tamanho": int(attachment.tamanho or 0),
                "sha256": attachment.sha256 or "",
                "usuario": attachment.username or "",
                "created_at": attachment.created_at.isoformat() if attachment.created_at else "",
            }
            for attachment in sorted(
                (attachment for attachment in record.anexos if attachment.active),
                key=lambda row: (row.created_at, row.id),
            )
        ]
        item["eventos"] = [
            {
                "id": event.id,
                "tipo": event.tipo,
                "usuario": event.actor_username,
                "status_anterior": event.status_anterior,
                "status_novo": event.status_novo,
                "justificativa": event.justificativa,
                "antes": event.before_json,
                "depois": event.after_json,
                "created_at": event.created_at.isoformat() if event.created_at else "",
            }
            for event in sorted(record.eventos, key=lambda row: row.created_at)
        ]
        item["comentarios"] = [
            {
                "id": comment.id,
                "usuario": comment.username,
                "texto": comment.texto,
                "created_at": comment.created_at.isoformat() if comment.created_at else "",
            }
            for comment in sorted(record.comentarios, key=lambda row: row.created_at)
        ]
    return item


def list_records(db: Session, tool: Ferramenta, user: User, status_code: str = "", limit: int = 500) -> list[dict]:
    require_tool_permission(db, tool, user, "view")
    query = db.query(FerramentaRegistro).options(
        selectinload(FerramentaRegistro.ferramenta),
        selectinload(FerramentaRegistro.versao),
    ).filter(FerramentaRegistro.ferramenta_id == tool.id, FerramentaRegistro.active.is_(True))
    if not is_admin(user):
        query = query.filter(FerramentaRegistro.owner_user_id == user.id)
    if status_code:
        query = query.filter(FerramentaRegistro.status_codigo == status_code.upper())
    records = query.order_by(FerramentaRegistro.updated_at.desc(), FerramentaRegistro.id.desc()).limit(limit).all()
    return [serialize_record(record) for record in records]


def get_record(db: Session, tool: Ferramenta, user: User, record_id: int) -> FerramentaRegistro:
    query = db.query(FerramentaRegistro).options(
        selectinload(FerramentaRegistro.ferramenta),
        selectinload(FerramentaRegistro.versao).selectinload(FerramentaVersao.campos),
        selectinload(FerramentaRegistro.versao).selectinload(FerramentaVersao.statuses),
        selectinload(FerramentaRegistro.versao).selectinload(FerramentaVersao.transicoes),
        selectinload(FerramentaRegistro.eventos),
        selectinload(FerramentaRegistro.comentarios),
        selectinload(FerramentaRegistro.anexos),
    ).filter(FerramentaRegistro.ferramenta_id == tool.id, FerramentaRegistro.id == record_id)
    if not is_admin(user):
        query = query.filter(FerramentaRegistro.owner_user_id == user.id)
    record = query.first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registro nao encontrado.")
    return record


def create_record(
    db: Session,
    tool: Ferramenta,
    version: FerramentaVersao,
    user: User,
    raw_payload: dict,
    requested_status: str | None = None,
) -> dict:
    require_tool_permission(db, tool, user, "create")
    payload = validate_payload(version, raw_payload, user)
    initial = next((item for item in version.statuses if item.inicial), None)
    if not initial:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ferramenta sem status inicial.")
    configuration = version.configuracao_json or {}
    use_status = tool.tipo != "CADASTRO" or configuration.get("usar_status", True)
    negotiator_selects_status = (
        tool.tipo == "CADASTRO"
        and use_status
        and bool(configuration.get("negociador_define_status"))
    )
    selected_status = initial
    if requested_status and negotiator_selects_status:
        selected_status = next((item for item in version.statuses if item.codigo == requested_status), None)
        if not selected_status:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Status inicial invalido.")
    title_key = str((version.configuracao_json or {}).get("campo_titulo") or "")
    title = str(payload.get(title_key) or "").strip() or None
    record = FerramentaRegistro(
        ferramenta_id=tool.id,
        versao_id=version.id,
        owner_user_id=user.id,
        owner_username=user.username,
        carteira=user.carteira,
        status_codigo=selected_status.codigo,
        titulo=title,
        payload_json=payload,
    )
    db.add(record)
    db.flush()
    event = FerramentaEvento(
        registro_id=record.id,
        actor_user_id=user.id,
        actor_username=user.username,
        tipo="CRIACAO",
        status_novo=selected_status.codigo,
        after_json=payload,
    )
    db.add(event)
    record_audit(db, user=user, action="create", entity_type=f"ferramenta:{tool.slug}", entity_id=record.id, after=payload)
    bump_version(db, f"ferramenta:{tool.slug}")
    bump_version(db, "ferramentas")
    db.commit()
    db.refresh(record)
    return serialize_record(record)


def update_record(
    db: Session,
    tool: Ferramenta,
    user: User,
    record_id: int,
    raw_payload: dict,
    requested_status: str | None = None,
    policy_version: FerramentaVersao | None = None,
) -> dict:
    require_tool_permission(db, tool, user, "edit")
    record = get_record(db, tool, user, record_id)
    before = dict(record.payload_json or {})
    previous_status = record.status_codigo
    changes = validate_payload(record.versao, raw_payload, user, partial=True)
    editable = {field.chave for field in record.versao.campos if not field.somente_leitura}
    changes = {key: value for key, value in changes.items() if key in editable}
    merged = {**before, **changes}
    merged = validate_payload(record.versao, merged, user)
    record.payload_json = merged
    title_key = str((record.versao.configuracao_json or {}).get("campo_titulo") or "")
    record.titulo = str(merged.get(title_key) or "").strip() or None
    if requested_status and requested_status != previous_status:
        current_policy = policy_version or record.versao
        configuration = current_policy.configuracao_json or {}
        if not configuration.get("negociador_altera_status"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Alteracao direta de status nao habilitada nesta ferramenta.",
            )
        require_tool_permission(db, tool, user, "transition")
        target = next((item for item in current_policy.statuses if item.codigo == requested_status), None)
        if not target:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Status informado nao existe nesta ferramenta.",
            )
        record.status_codigo = target.codigo
    db.add(FerramentaEvento(
        registro_id=record.id,
        actor_user_id=user.id,
        actor_username=user.username,
        tipo="STATUS_DIRETO" if record.status_codigo != previous_status else "EDICAO",
        status_anterior=previous_status,
        status_novo=record.status_codigo,
        before_json=before,
        after_json=merged,
    ))
    status_changed = record.status_codigo != previous_status
    record_audit(
        db,
        user=user,
        action="status_update" if status_changed else "update",
        entity_type=f"ferramenta:{tool.slug}",
        entity_id=record.id,
        before={"status": previous_status, "payload": before} if status_changed else before,
        after={"status": record.status_codigo, "payload": merged} if status_changed else merged,
    )
    bump_version(db, f"ferramenta:{tool.slug}")
    db.commit()
    db.refresh(record)
    return serialize_record(record)


def transition_record(
    db: Session,
    tool: Ferramenta,
    user: User,
    record_id: int,
    target_status: str,
    justification: str | None,
) -> dict:
    permission = require_tool_permission(db, tool, user, "view")
    record = get_record(db, tool, user, record_id)
    transition = next(
        (
            item for item in record.versao.transicoes
            if item.origem_codigo == record.status_codigo and item.destino_codigo == target_status
        ),
        None,
    )
    if not transition:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Transicao de status nao permitida.")
    allowed = is_admin(user) or (transition.permite_negociador and permission.pode_transicionar)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Transicao nao permitida para este usuario.")
    clean_reason = str(justification or "").strip()
    if transition.exige_justificativa and not clean_reason:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Justificativa obrigatoria.")
    previous = record.status_codigo
    before_payload = dict(record.payload_json or {})
    after_payload = dict(before_payload)
    automation_log: list[dict[str, Any]] = []
    for automation in (transition.configuracao_json or {}).get("automacoes") or []:
        action = str((automation or {}).get("tipo") or "").lower()
        field_key = str((automation or {}).get("campo") or "").upper()
        field = next((item for item in record.versao.campos if item.chave == field_key), None)
        if action == "notificar":
            automation_log.append({"tipo": action, "mensagem": str((automation or {}).get("valor") or "").strip()})
            continue
        if not field:
            continue
        if action == "data_atual":
            after_payload[field_key] = date.today().isoformat()
        elif action == "definir_valor":
            after_payload[field_key] = (automation or {}).get("valor")
        elif action == "limpar_campo":
            after_payload[field_key] = None
        else:
            continue
        automation_log.append({"tipo": action, "campo": field_key, "valor": after_payload.get(field_key)})
    after_payload = validate_payload(record.versao, after_payload, user)
    record.payload_json = after_payload
    record.status_codigo = target_status
    db.add(FerramentaEvento(
        registro_id=record.id,
        actor_user_id=user.id,
        actor_username=user.username,
        tipo="TRANSICAO",
        status_anterior=previous,
        status_novo=target_status,
        justificativa=clean_reason or None,
        before_json=before_payload,
        after_json={"payload": after_payload, "automacoes": automation_log},
    ))
    record_audit(
        db, user=user, action="status_update", entity_type=f"ferramenta:{tool.slug}",
        entity_id=record.id,
        before={"status": previous, "payload": before_payload},
        after={"status": target_status, "payload": after_payload, "automacoes": automation_log},
        reason=clean_reason or None
    )
    bump_version(db, f"ferramenta:{tool.slug}")
    db.commit()
    db.refresh(record)
    return serialize_record(record)


def add_comment(db: Session, tool: Ferramenta, user: User, record_id: int, text: str) -> dict:
    require_tool_permission(db, tool, user, "view")
    record = get_record(db, tool, user, record_id)
    comment = FerramentaComentario(
        registro_id=record.id,
        user_id=user.id,
        username=user.username,
        texto=text.strip(),
    )
    db.add(comment)
    db.add(FerramentaEvento(
        registro_id=record.id,
        actor_user_id=user.id,
        actor_username=user.username,
        tipo="COMENTARIO",
        after_json={"texto": text.strip()},
    ))
    bump_version(db, f"ferramenta:{tool.slug}")
    db.commit()
    db.refresh(comment)
    return {
        "id": comment.id,
        "usuario": comment.username,
        "texto": comment.texto,
        "created_at": comment.created_at.isoformat(),
    }


def validate_definition(payload: FerramentaDefinitionInput) -> None:
    field_keys = [field.chave for field in payload.campos]
    if len(field_keys) != len(set(field_keys)):
        raise HTTPException(status_code=422, detail="Existem campos com a mesma chave.")
    known_fields = set(field_keys)
    allowed_operators = {"igual", "diferente", "preenchido", "vazio", "contem", "em", "nao_em", "maior", "maior_igual", "menor", "menor_igual"}
    allowed_calculations = {"percentual", "soma", "subtracao", "multiplicacao", "divisao"}
    for field in payload.campos:
        condition = dict(field.condicao or {})
        if condition and (condition.get("campo") not in known_fields or str(condition.get("operador") or "igual") not in allowed_operators):
            raise HTTPException(status_code=422, detail=f"Condicao invalida no campo {field.nome}.")
        validation = dict(field.validacao or {})
        if validation.get("regex"):
            try:
                re.compile(str(validation["regex"]))
            except re.error as exc:
                raise HTTPException(status_code=422, detail=f"Expressao invalida no campo {field.nome}.") from exc
        calculation = dict(validation.get("calculo") or {})
        if calculation:
            if str(calculation.get("operacao") or "percentual") not in allowed_calculations:
                raise HTTPException(status_code=422, detail=f"Calculo invalido no campo {field.nome}.")
            if calculation.get("campo_base") not in known_fields:
                raise HTTPException(status_code=422, detail=f"Campo base invalido no calculo de {field.nome}.")
            if calculation.get("campo_secundario") and calculation.get("campo_secundario") not in known_fields:
                raise HTTPException(status_code=422, detail=f"Campo secundario invalido no calculo de {field.nome}.")
    use_status = payload.tipo != "CADASTRO" or payload.configuracao.get("usar_status", True)
    statuses = payload.statuses if use_status else []
    status_codes = [item.codigo for item in statuses]
    if len(status_codes) != len(set(status_codes)):
        raise HTTPException(status_code=422, detail="Existem status duplicados.")
    if use_status and sum(1 for item in statuses if item.inicial) != 1:
        raise HTTPException(status_code=422, detail="Defina exatamente um status inicial.")
    known = set(status_codes)
    for transition in payload.transicoes if use_status else []:
        if transition.origem_codigo not in known or transition.destino_codigo not in known:
            raise HTTPException(status_code=422, detail="Transicao referencia status inexistente.")
        if transition.origem_codigo == transition.destino_codigo:
            raise HTTPException(status_code=422, detail="Transicao deve alterar o status.")
        for automation in (transition.configuracao or {}).get("automacoes") or []:
            action = str((automation or {}).get("tipo") or "")
            if action not in {"data_atual", "definir_valor", "limpar_campo", "notificar"}:
                raise HTTPException(status_code=422, detail="Automacao de transicao invalida.")
            if action != "notificar" and (automation or {}).get("campo") not in known_fields:
                raise HTTPException(status_code=422, detail="Automacao referencia campo inexistente.")
    for permission in payload.permissoes:
        if permission.user_id is None and not str(permission.carteira or "").strip():
            raise HTTPException(status_code=422, detail="Permissao deve indicar usuario ou carteira.")


def _replace_draft_definition(db: Session, version: FerramentaVersao, payload: FerramentaDefinitionInput) -> None:
    if version.status != "RASCUNHO":
        raise HTTPException(status_code=409, detail="Somente versoes em rascunho podem ser editadas.")
    configuration = dict(payload.configuracao or {})
    use_status = payload.tipo != "CADASTRO" or configuration.get("usar_status", True)
    configuration["usar_status"] = bool(use_status)
    if not use_status:
        configuration["negociador_define_status"] = False
        configuration["negociador_altera_status"] = False
    version.configuracao_json = configuration
    version.campos.clear()
    version.statuses.clear()
    version.transicoes.clear()
    db.flush()
    for field in payload.campos:
        version.campos.append(FerramentaCampo(
            chave=field.chave,
            nome=field.nome.strip(),
            tipo=field.tipo,
            ordem=field.ordem,
            etapa=field.etapa,
            obrigatorio=field.obrigatorio,
            somente_leitura=field.somente_leitura,
            visivel_negocial=field.visivel_negocial,
            visivel_gerencial=field.visivel_gerencial,
            opcoes_json=field.opcoes,
            validacao_json=field.validacao,
            condicao_json=field.condicao,
            valor_padrao_json=field.valor_padrao,
        ))
    status_items = payload.statuses if use_status else [
        FerramentaStatusInput(
            codigo="REGISTRADO",
            nome="Registrado",
            cor="#64748b",
            ordem=0,
            inicial=True,
            final=True,
        )
    ]
    for item in status_items:
        version.statuses.append(FerramentaStatus(**item.model_dump()))
    for item in payload.transicoes if use_status else []:
        data = item.model_dump()
        data["configuracao_json"] = data.pop("configuracao")
        version.transicoes.append(FerramentaTransicao(**data))


def create_tool_draft(db: Session, user: User, payload: FerramentaDefinitionInput) -> dict:
    validate_definition(payload)
    slug = slugify(payload.slug or payload.nome)
    if not slug:
        raise HTTPException(status_code=422, detail="Slug da ferramenta invalido.")
    if db.query(Ferramenta).filter(Ferramenta.slug == slug).first():
        raise HTTPException(status_code=409, detail="Ja existe uma ferramenta com este nome.")
    tool = Ferramenta(
        nome=payload.nome.strip(),
        slug=slug,
        descricao=(payload.descricao or "").strip() or None,
        tipo=payload.tipo,
        icone=payload.icone,
        cor=payload.cor,
        created_by=user.id,
    )
    version = FerramentaVersao(numero=1, status="RASCUNHO", created_by=user.id)
    tool.versoes.append(version)
    db.add(tool)
    db.flush()
    _replace_draft_definition(db, version, payload)
    for permission in payload.permissoes:
        tool.permissoes.append(FerramentaPermissao(**permission.model_dump()))
    record_audit(db, user=user, action="create_draft", entity_type="ferramenta", entity_id=tool.id, after={"slug": slug})
    bump_version(db, "ferramentas")
    db.commit()
    return serialize_definition(
        _definition_query(db).filter(FerramentaVersao.id == version.id).one(),
        _permission(db, tool, user),
    )


def update_tool_draft(db: Session, user: User, tool_id: int, payload: FerramentaDefinitionInput) -> dict:
    validate_definition(payload)
    tool = db.query(Ferramenta).filter(Ferramenta.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="Ferramenta nao encontrada.")
    version = (
        _definition_query(db)
        .filter(FerramentaVersao.ferramenta_id == tool.id, FerramentaVersao.status == "RASCUNHO")
        .order_by(FerramentaVersao.numero.desc())
        .first()
    )
    if not version:
        raise HTTPException(status_code=409, detail="Crie uma nova versao antes de editar.")
    tool.nome = payload.nome.strip()
    tool.descricao = (payload.descricao or "").strip() or None
    tool.tipo = payload.tipo
    tool.icone = payload.icone
    tool.cor = payload.cor
    _replace_draft_definition(db, version, payload)
    db.query(FerramentaPermissao).filter(FerramentaPermissao.ferramenta_id == tool.id).delete()
    for permission in payload.permissoes:
        db.add(FerramentaPermissao(ferramenta_id=tool.id, **permission.model_dump()))
    record_audit(db, user=user, action="update_draft", entity_type="ferramenta", entity_id=tool.id)
    bump_version(db, "ferramentas")
    db.commit()
    return serialize_definition(
        _definition_query(db).filter(FerramentaVersao.id == version.id).one(),
        _permission(db, tool, user),
    )


def publish_tool(db: Session, user: User, tool_id: int) -> dict:
    version = (
        _definition_query(db)
        .filter(FerramentaVersao.ferramenta_id == tool_id, FerramentaVersao.status == "RASCUNHO")
        .order_by(FerramentaVersao.numero.desc())
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="Rascunho nao encontrado.")
    if not version.ferramenta.permissoes:
        raise HTTPException(status_code=422, detail="Defina ao menos uma permissao antes de publicar.")
    current = db.query(FerramentaVersao).filter(
        FerramentaVersao.ferramenta_id == tool_id,
        FerramentaVersao.status == "PUBLICADA",
    ).first()
    now = utcnow()
    if current:
        current.status = "ARQUIVADA"
        current.archived_at = now
    version.status = "PUBLICADA"
    version.published_by = user.id
    version.published_at = now
    record_audit(
        db, user=user, action="publish", entity_type="ferramenta",
        entity_id=tool_id, after={"versao": version.numero}
    )
    bump_version(db, "ferramentas")
    db.commit()
    return serialize_definition(
        _definition_query(db).filter(FerramentaVersao.id == version.id).one(),
        _permission(db, version.ferramenta, user),
    )


def create_next_draft(db: Session, user: User, tool_id: int) -> dict:
    existing = db.query(FerramentaVersao).filter(
        FerramentaVersao.ferramenta_id == tool_id,
        FerramentaVersao.status == "RASCUNHO",
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="A ferramenta ja possui um rascunho.")
    source = (
        _definition_query(db)
        .filter(FerramentaVersao.ferramenta_id == tool_id, FerramentaVersao.status == "PUBLICADA")
        .first()
    )
    if not source:
        raise HTTPException(status_code=404, detail="Versao publicada nao encontrada.")
    next_number = (
        db.query(func.max(FerramentaVersao.numero))
        .filter(FerramentaVersao.ferramenta_id == tool_id)
        .scalar() or 0
    ) + 1
    version = FerramentaVersao(
        ferramenta_id=tool_id,
        numero=next_number,
        status="RASCUNHO",
        configuracao_json=source.configuracao_json,
        created_by=user.id,
    )
    db.add(version)
    db.flush()
    for field in source.campos:
        version.campos.append(FerramentaCampo(
            chave=field.chave, nome=field.nome, tipo=field.tipo, ordem=field.ordem, etapa=field.etapa,
            obrigatorio=field.obrigatorio, somente_leitura=field.somente_leitura,
            visivel_negocial=field.visivel_negocial, visivel_gerencial=field.visivel_gerencial,
            opcoes_json=field.opcoes_json, validacao_json=field.validacao_json,
            condicao_json=field.condicao_json, valor_padrao_json=field.valor_padrao_json,
        ))
    for item in source.statuses:
        version.statuses.append(FerramentaStatus(
            codigo=item.codigo, nome=item.nome, cor=item.cor, ordem=item.ordem,
            inicial=item.inicial, final=item.final,
        ))
    for item in source.transicoes:
        version.transicoes.append(FerramentaTransicao(
            origem_codigo=item.origem_codigo, destino_codigo=item.destino_codigo, nome=item.nome,
            exige_justificativa=item.exige_justificativa, permite_negociador=item.permite_negociador,
            permite_gerencial=item.permite_gerencial, configuracao_json=item.configuracao_json,
        ))
    bump_version(db, "ferramentas")
    db.commit()
    return serialize_definition(
        _definition_query(db).filter(FerramentaVersao.id == version.id).one(),
        _permission(db, source.ferramenta, user),
    )


def list_admin_tools(db: Session, user: User) -> list[dict]:
    tools = db.query(Ferramenta).order_by(Ferramenta.nome).all()
    items = []
    for tool in tools:
        versions = (
            _definition_query(db)
            .filter(FerramentaVersao.ferramenta_id == tool.id)
            .order_by(FerramentaVersao.numero.desc())
            .all()
        )
        items.append({
            "id": tool.id,
            "nome": tool.nome,
            "slug": tool.slug,
            "tipo": tool.tipo,
            "active": tool.active,
            "destaque_gerencial": tool.destaque_gerencial,
            "versoes": [serialize_definition(version, _permission(db, tool, user)) for version in versions],
            "permissoes_configuradas": len(tool.permissoes),
        })
    return items
