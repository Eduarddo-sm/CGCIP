from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import re

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import flag_modified

from backend.models import (
    CarteiraColuna,
    CarteiraNegocial,
    CarteiraRegraCalculo,
    ProducaoGamma,
    ProducaoCampo,
    ProducaoAlpha,
    ProducaoRegistro,
    ProducaoBeta,
    ProducaoViradaExcecao,
    ProducaoViradaMensal,
    User,
)
from backend.schemas.producao import ProducaoCreate, ProducaoStatusUpdate, ProducaoUpdate
from backend.services.audit_service import record_audit
from backend.services.producao_calendar import (
    can_move_to_next_month as _can_move_to_next_month,
    current_month_start as _current_month_start,
    month_range as _month_range,
    previous_month_start as _previous_month_start,
    resolve_production_date as _resolve_production_date,
    rollover_deadline_reached as _rollover_deadline_reached,
    second_business_day as _second_business_day,
)
from backend.services.producao_serializer import dynamic_field_value as _dynamic_field_value, serialize_producao
from backend.services.producao_values import (
    STATUS_LABELS,
    TIPO_LABELS,
    date_from_dynamic_value as _date_from_dynamic_value,
    field_key as _field_key,
    field_value as _field_value,
    money as _money,
    money_from_any as _money_from_any,
    normalize_status_value as _normalize_status_value,
    normalize_text as _normalize_text,
    optional_text as _optional_text,
    percentual_ho as _percentual_ho,
    schema_option_text as _schema_option_text,
    schema_options as _schema_options,
)
from backend.services.version_service import bump_version


FLEX_AUTORIZACOES = {"DANIELLE", "ADRIANO", "GECOR"}
JUSTIFICATIVA_STATUS = {"QUEBRA", "PROPOSTA_NEGADA"}
AUTO_BREAK_STATUSES = {"PROPOSTA", "AGUARDANDO_PAGAMENTO"}
NEW_AGREEMENT_SOURCE_STATUSES = {"QUEBRA", "PROPOSTA_NEGADA"}
NEW_AGREEMENT_TARGET_STATUSES = {"AGUARDANDO_PAGAMENTO", "PAGAMENTO_REALIZADO"}
AUTO_BREAK_JUSTIFICATIVA = "Nao atualizado dentro do mes, quebra automatica"
ROLLOVER_TRANSFER_JUSTIFICATIVA = "Transferido para a competencia atual na virada mensal"
ROLLOVER_BREAK_JUSTIFICATIVA = "Quebra classificada no fechamento mensal"
ROLLOVER_DENIED_JUSTIFICATIVA = "Proposta negada no fechamento mensal"


def _active_rollover_exception(
    db: Session,
    user: User,
    reference: date,
) -> ProducaoViradaExcecao | None:
    return (
        db.query(ProducaoViradaExcecao)
        .filter(
            ProducaoViradaExcecao.user_id == user.id,
            ProducaoViradaExcecao.competencia_origem == _previous_month_start(reference),
            ProducaoViradaExcecao.competencia_destino == _current_month_start(reference),
            ProducaoViradaExcecao.valida_ate >= reference,
            ProducaoViradaExcecao.consumida_em.is_(None),
        )
        .first()
    )


def _user_carteira(user: User) -> str:
    return (user.carteira or "GAMMA").strip().upper()


def _is_alpha(user: User) -> bool:
    return _user_carteira(user) == "ALPHA"


def _is_beta(user: User) -> bool:
    return _user_carteira(user) == "BETA"


def _is_gamma(user: User) -> bool:
    return _user_carteira(user) == "GAMMA"


def _uses_schema_mode(db: Session, user: User) -> bool:
    wallet = _carteira_definition(db, user)
    if wallet is not None:
        return bool(wallet.modo_schema)
    return not _is_alpha(user) and not _is_beta(user)


def _carteira_definition(db: Session, user: User) -> CarteiraNegocial | None:
    carteira = _user_carteira(user)
    return (
        db.query(CarteiraNegocial)
        .options(
            selectinload(CarteiraNegocial.colunas),
            selectinload(CarteiraNegocial.regras_calculo).selectinload(
                CarteiraRegraCalculo.coluna_base
            ),
            selectinload(CarteiraNegocial.regras_calculo).selectinload(
                CarteiraRegraCalculo.coluna_destino
            ),
            selectinload(CarteiraNegocial.regras_calculo).selectinload(
                CarteiraRegraCalculo.coluna_base_vista
            ),
            selectinload(CarteiraNegocial.regras_calculo).selectinload(
                CarteiraRegraCalculo.coluna_base_parcelado
            ),
            selectinload(CarteiraNegocial.regras_calculo).selectinload(
                CarteiraRegraCalculo.coluna_valor_recebido
            ),
            selectinload(CarteiraNegocial.regras_calculo).selectinload(
                CarteiraRegraCalculo.coluna_percentual_efetivo
            ),
        )
        .filter(CarteiraNegocial.slug == carteira)
        .first()
    )


def _dynamic_columns(db: Session, user: User) -> list[CarteiraColuna]:
    carteira = _carteira_definition(db, user)
    if not carteira:
        return []
    return sorted(carteira.colunas, key=lambda column: (column.ordem, column.id))


def _identifier_column(db: Session, user: User) -> CarteiraColuna | None:
    columns = _dynamic_columns(db, user)
    return next((column for column in columns if column.identificador), columns[0] if columns else None)


def _payload_fields(payload: ProducaoCreate | ProducaoUpdate) -> dict[str, object]:
    fields = dict(payload.campos or {})
    aliases = {
        "NPJ": payload.npj,
        "SUITID": payload.npj,
        "DEBIT_ID": payload.npj,
        "CLIENTE": payload.cliente,
        "STATUS": payload.status,
        "DATA": payload.data_vencimento,
        "VENCIMENTO": payload.data_vencimento,
        "VALOR_TOTAL": payload.valor_total_acordo,
        "VALOR_TOTAL_DE_ACORDO": payload.valor_total_acordo,
        "VALOR_DA_ENTRADA": payload.valor_entrada,
        "ENTRADA": payload.valor_entrada,
        "TIPO": payload.tipo_acordo,
        "TIPO_DE_ACORDO": payload.tipo_acordo,
        "PARCELADO_OU_VISTA": payload.tipo_acordo,
        "DATA_DE_VENCIMENTO": payload.data_vencimento,
        "DATA_DO_PAGAMENTO": payload.data_pagamento,
        "JUSTIFICATIVA": payload.justificativa_status,
        "HONOR_RIOS_RECEBIDOS": payload.valor_ho,
        "HONORARIOS_RECEBIDOS": payload.valor_ho,
        "AUTORIZADO": payload.autorizacao_flexibilizacao,
    }
    for key, value in aliases.items():
        fields.setdefault(key, value)
    return fields


def _resolve_justificativa(status_value: str, justificativa: str | None) -> str | None:
    text = _normalize_text(justificativa or "")
    if status_value in JUSTIFICATIVA_STATUS:
        if not text:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Justificativa obrigatoria para Quebra ou Proposta negada.",
            )
        return text
    return None


def _resolve_data_pagamento(status_value: str, data_pagamento: date | None) -> date | None:
    if status_value == "PAGAMENTO_REALIZADO":
        if not data_pagamento:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Data de pagamento obrigatoria para Pagamento realizado.",
            )
        return data_pagamento
    return None


def _apply_formalized_new_agreement(
    item: ProducaoRegistro,
    previous_status: str,
    next_status: str,
    formalized: bool,
) -> bool:
    if not formalized:
        return False
    if (
        previous_status not in NEW_AGREEMENT_SOURCE_STATUSES
        or next_status not in NEW_AGREEMENT_TARGET_STATUSES
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "A formalizacao de novo acordo so pode ser marcada ao alterar "
                "Quebra ou Proposta negada para Aguardando pagamento ou Pagamento realizado."
            ),
        )
    today = date.today()
    item.data_acordo = today
    item.competencia = today.replace(day=1)
    return True


def _dynamic_value_priority(column: CarteiraColuna) -> int:
    text = f"{_field_key(column.chave)} {_field_key(column.nome)}"
    if "FECHADO" in text:
        return 0
    if "ACORDO" in text:
        return 1
    if "TOTAL" in text and "DEBIT" in text:
        return 2
    if "MINIMO" in text or "PRE_APROVADO" in text:
        return 3
    if "TOTAL" in text or "VALOR" in text:
        return 4
    return 9


def _resolve_dynamic_total_value(db: Session, payload: ProducaoCreate | ProducaoUpdate, user: User) -> Decimal:
    fields = _payload_fields(payload)
    columns = [
        column for column in _dynamic_columns(db, user)
        if column.tipo in {"moeda", "numero"}
    ]
    columns.sort(key=lambda column: (_dynamic_value_priority(column), column.ordem, column.id))
    for column in columns:
        candidate = _money_from_any(_field_value(fields, column.chave, column.nome))
        if candidate > 0:
            return _money(candidate)

    for key in (
        "VALOR_FECHADO",
        "VALOR_TOTAL_FECHADO",
        "VALOR_DO_ACORDO",
        "VALOR_TOTAL",
        "VALOR_TOTAL_DE_ACORDO",
        "VALOR_TOTAL_DO_DEBITO",
        "VALOR_TOTAL_DO_DÉBITO",
        "VALOR_MINIMO_PRE_APROVADO",
        "VALOR_MINIMO_PRÉ_APROVADO",
    ):
        candidate = _money_from_any(_field_value(fields, key))
        if candidate > 0:
            return _money(candidate)
    return Decimal("0.00")


def _validate_identifiers(db: Session, payload: ProducaoCreate | ProducaoUpdate, user: User) -> tuple[str, str | None, str, date | None]:
    if _uses_schema_mode(db, user):
        identifier = _identifier_column(db, user)
        if not identifier:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Carteira sem coluna identificadora configurada.",
            )
        fields = _payload_fields(payload)
        value = _normalize_text(str(_field_value(fields, identifier.chave, identifier.nome) or payload.npj or ""))
        if not value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{identifier.nome} e obrigatorio.",
            )
        if _is_alpha(user) and len(value) != 8:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="DEBIT ID deve conter exatamente 8 caracteres.",
            )
        if _is_alpha(user):
            cpf_value = str(_field_value(fields, "CPF_CNPJ", "CPF", "CNPJ") or "").strip()
            if not cpf_value.isdigit() or len(cpf_value) not in {11, 14}:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="CPF/CNPJ deve conter somente 11 ou 14 digitos.",
                )
        if _is_gamma(user) and (not value.isdigit() or len(value) != 14):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="NPJ deve conter exatamente 14 digitos.",
            )
        gecor = ""
        if _is_gamma(user):
            gecor = _normalize_text(str(_field_value(fields, "GECOR") or payload.gecor or ""))
            if not gecor.isdigit() or len(gecor) != 4:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="GECOR deve conter exatamente 4 digitos.",
                )
        return value, None, gecor, None

    if _is_alpha(user):
        if len(payload.npj) != 8:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="DEBIT ID deve conter exatamente 8 digitos.",
            )
        if not payload.cpf:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="CPF ou CNPJ e obrigatorio para carteira Alpha.",
            )
        if not payload.data_primeiro_atraso:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Data do 1o atraso e obrigatoria para carteira Alpha.",
            )
        if not payload.carteira_alpha:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Carteira AUTOS ou SME e obrigatoria para carteira Alpha.",
            )
        return payload.npj, payload.cpf, "", payload.data_primeiro_atraso

    if _is_beta(user):
        if not payload.npj.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="SUITID e obrigatorio para carteira Beta.",
            )
        return payload.npj.strip(), None, "", None

    if len(payload.npj) != 14:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="NPJ deve conter exatamente 14 digitos.",
        )
    if not payload.gecor:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="GECOR e obrigatorio para carteira GAMMA.",
        )
    return payload.npj, None, payload.gecor, None


def _resolve_values(db: Session, payload: ProducaoCreate | ProducaoUpdate, user: User):
    valor_total = _money(payload.valor_total_acordo)
    if _uses_schema_mode(db, user) and valor_total <= 0:
        valor_total = _resolve_dynamic_total_value(db, payload, user)
    if valor_total <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Valor total deve ser maior que zero.",
        )
    payload_fields = _payload_fields(payload)
    raw_ho = payload.valor_ho
    if raw_ho is None and _is_gamma(user):
        raw_ho = _field_value(
            payload_fields,
            "HONOR_RIOS_RECEBIDOS",
            "HONORARIOS_RECEBIDOS",
            "H_O",
            "HO",
            "VALOR_HO",
        )
    if _is_gamma(user) and raw_ho in (None, ""):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="H.O e obrigatorio para carteira GAMMA.",
        )
    valor_ho = _money(_money_from_any(raw_ho)) if _is_gamma(user) else Decimal("0.00")
    percentual = _percentual_ho(valor_ho, valor_total) if _is_gamma(user) else Decimal("0.00")

    if payload.tipo_acordo == "A_VISTA":
        valor_entrada = Decimal("0.00")
    else:
        if payload.valor_entrada is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Valor da entrada e obrigatorio para acordo parcelado.",
            )
        valor_entrada = _money(payload.valor_entrada)

    _validate_manual_ho_limit(
        db,
        payload,
        user,
        valor_total=valor_total,
        valor_entrada=valor_entrada,
        raw_ho=raw_ho,
    )

    raw_authorization = payload.autorizacao_flexibilizacao
    if raw_authorization in (None, "") and _is_gamma(user):
        raw_authorization = _field_value(payload_fields, "AUTORIZADO", "AUTORIZADO?")
    autorizacao = str(raw_authorization or "").strip().upper() if _is_gamma(user) else "NAO"
    if percentual < Decimal("9"):
        if _is_gamma(user) and autorizacao not in FLEX_AUTORIZACOES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Autorizacao de flexibilizacao obrigatoria quando H.O for menor que 9%.",
            )
    else:
        autorizacao = "NAO"

    return valor_total, valor_entrada, valor_ho, percentual, autorizacao


def _validate_manual_ho_limit(
    db: Session,
    payload: ProducaoCreate | ProducaoUpdate,
    user: User,
    *,
    valor_total: Decimal,
    valor_entrada: Decimal,
    raw_ho: object,
) -> None:
    wallet = _carteira_definition(db, user)
    if not wallet:
        return
    rule = _honorarios_rule(wallet)
    if not wallet.usa_percentual_ho and not rule:
        return
    maximum = (
        rule.percentual_maximo
        if rule and rule.percentual_maximo is not None
        else wallet.percentual_ho_maximo
    )
    if maximum is None:
        return

    fields = _payload_fields(payload)
    manual_value = _money_from_any(raw_ho) if _is_gamma(user) and raw_ho not in (None, "") else None
    if manual_value is None and rule:
        manual_column = rule.coluna_valor_recebido or (rule.coluna_destino if not rule.automatico else None)
        if manual_column:
            candidate = fields.get(manual_column.chave)
            if not _dynamic_value_is_empty(candidate):
                manual_value = _rule_decimal_value(manual_column, candidate)
    if manual_value is None and not rule:
        manual_column = next((column for column in wallet.colunas if _is_dynamic_honorarios_column(column)), None)
        if manual_column:
            candidate = fields.get(manual_column.chave)
            if not _dynamic_value_is_empty(candidate):
                manual_value = _rule_decimal_value(manual_column, candidate)
    if manual_value is None:
        return

    base_value = valor_total
    if rule:
        if str(rule.motor_calculo or "").upper() == "PERCENTUAL_CONDICIONAL":
            base_column = rule.coluna_base_parcelado if payload.tipo_acordo == "PARCELADO" else rule.coluna_base_vista
        else:
            base_column = rule.coluna_base
        if base_column:
            aliases = {
                "VALOR_DO_ACORDO": valor_total,
                "VALOR_TOTAL": valor_total,
                "VALOR_TOTAL_DE_ACORDO": valor_total,
                "VALOR_DA_ENTRADA": valor_entrada,
                "ENTRADA": valor_entrada,
            }
            candidate = aliases.get(base_column.chave, fields.get(base_column.chave))
            resolved_base = _rule_decimal_value(base_column, candidate)
            if resolved_base is not None:
                base_value = resolved_base
    if base_value <= 0:
        return

    maximum_decimal = Decimal(str(maximum))
    maximum_value = base_value * maximum_decimal / Decimal("100")
    if Decimal(str(manual_value)) > maximum_value + Decimal("0.005"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"H.O acima do limite da carteira. O maximo permitido e {format(maximum_decimal, 'f')}% "
                f"(R$ {_money(maximum_value):.2f})."
            ),
        )


def _ensure_current_month_editable(item: ProducaoRegistro) -> None:
    competence = item.competencia or item.data_acordo.replace(day=1)
    if competence < _current_month_start():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Competencias anteriores estao bloqueadas para alteracao pelo negociador.",
        )


def _visible_query(db: Session, user: User):
    query = db.query(ProducaoRegistro).options(
        selectinload(ProducaoRegistro.user),
        selectinload(ProducaoRegistro.gamma),
        selectinload(ProducaoRegistro.alpha),
        selectinload(ProducaoRegistro.beta_detail),
        selectinload(ProducaoRegistro.campos).selectinload(ProducaoCampo.coluna),
    )
    if user.role != "ADMIN":
        query = query.filter(ProducaoRegistro.user_id == user.id)
    return query


def list_producao(db: Session, user: User) -> list[dict]:
    auto_break_previous_month_items(db, user)
    items = (
        _visible_query(db, user)
        .order_by(ProducaoRegistro.data_acordo.desc(), ProducaoRegistro.created_at.desc())
        .all()
    )
    return [serialize_producao(item) for item in items]


def get_producao_schema(db: Session, user: User) -> dict:
    carteira = _user_carteira(user)
    columns = _dynamic_columns(db, user)
    wallet = _carteira_definition(db, user)
    explicit_rule = _honorarios_rule(wallet)
    return {
        "carteira": carteira,
        "tipo": "dinamica" if wallet and wallet.modo_schema else "gamma" if _is_gamma(user) else "alpha" if _is_alpha(user) else "beta" if _is_beta(user) else "dinamica",
        "regra_tipo": "gamma" if _is_gamma(user) else "alpha" if _is_alpha(user) else "beta" if _is_beta(user) else "padrao",
        "regras_ho": {
            "usa_percentual_ho": bool(wallet.usa_percentual_ho) if wallet else False,
            "percentual_ho_padrao": float(wallet.percentual_ho_padrao) if wallet and wallet.percentual_ho_padrao is not None else None,
            "percentual_ho_minimo": float(wallet.percentual_ho_minimo) if wallet and wallet.percentual_ho_minimo is not None else None,
            "percentual_ho_maximo": float(wallet.percentual_ho_maximo) if wallet and wallet.percentual_ho_maximo is not None else None,
            "calculo_automatico_ho": bool(wallet.calculo_automatico_ho) if wallet else False,
            "motor_calculo": explicit_rule.motor_calculo if explicit_rule else "PERCENTUAL_FIXO",
            "coluna_base": explicit_rule.coluna_base.chave if explicit_rule and explicit_rule.coluna_base else None,
            "coluna_base_vista": (
                explicit_rule.coluna_base_vista.chave
                if explicit_rule and explicit_rule.coluna_base_vista
                else None
            ),
            "coluna_base_parcelado": (
                explicit_rule.coluna_base_parcelado.chave
                if explicit_rule and explicit_rule.coluna_base_parcelado
                else None
            ),
            "coluna_destino": explicit_rule.coluna_destino.chave if explicit_rule and explicit_rule.coluna_destino else None,
            "coluna_valor_recebido": (
                explicit_rule.coluna_valor_recebido.chave
                if explicit_rule and explicit_rule.coluna_valor_recebido
                else None
            ),
            "coluna_percentual_efetivo": (
                explicit_rule.coluna_percentual_efetivo.chave
                if explicit_rule and explicit_rule.coluna_percentual_efetivo
                else None
            ),
            "casas_decimais": explicit_rule.casas_decimais if explicit_rule else 2,
        },
        "columns": [
            {
                "id": column.id,
                "nome": column.nome,
                "chave": column.chave,
                "tipo": column.tipo,
                "obrigatoria": column.obrigatoria,
                "identificador": column.identificador,
                "visivel": column.visivel,
                "ordem": column.ordem,
                "automatico": column.automatico,
                "auto_tipo": column.auto_tipo or "",
                "max_length": column.max_length,
                "mostrar_cadastro": column.mostrar_cadastro,
                "cadastro_etapa": column.cadastro_etapa,
                "opcoes": _schema_options(column),
            }
            for column in columns
        ],
    }


def auto_break_previous_month_items(db: Session, user: User, reference: date | None = None) -> int:
    today = reference or date.today()
    if not _rollover_deadline_reached(today):
        return 0
    query = (
        _visible_query(db, user)
        .filter(
            ProducaoRegistro.user_id == user.id,
            ProducaoRegistro.competencia < _current_month_start(today),
            ProducaoRegistro.status.in_(tuple(AUTO_BREAK_STATUSES)),
        )
    )
    exception = _active_rollover_exception(db, user, today)
    if exception:
        query = query.filter(ProducaoRegistro.competencia != exception.competencia_origem)
    items = query.all()
    for item in items:
        before = serialize_producao(item)
        item.status = "QUEBRA"
        item.justificativa_status = AUTO_BREAK_JUSTIFICATIVA
        item.data_pagamento = None
        _sync_dynamic_system_fields(
            db,
            item,
            user,
            {"STATUS": item.status, "JUSTIFICATIVA": item.justificativa_status, "DATA_DO_PAGAMENTO": None},
        )
        record_audit(
            db,
            user=user,
            action="auto_break_month_close",
            entity_type="producao",
            entity_id=item.id,
            before=before,
            after=serialize_producao(item),
            reason=AUTO_BREAK_JUSTIFICATIVA,
        )
    if items:
        bump_version(db, "producao")
        db.commit()
    return len(items)


def get_producao(db: Session, user: User, producao_id: int) -> ProducaoRegistro:
    item = _visible_query(db, user).filter(ProducaoRegistro.id == producao_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Acordo nao encontrado.")
    return item


def _apply_common_fields(
    item: ProducaoRegistro,
    user: User,
    payload: ProducaoCreate | ProducaoUpdate,
    valor_total: Decimal,
    valor_entrada: Decimal,
    data_pagamento: date | None,
    justificativa: str | None,
) -> None:
    item.cliente = _normalize_text(payload.cliente)
    item.valor_total_acordo = valor_total
    item.valor_entrada = valor_entrada
    item.tipo_acordo = payload.tipo_acordo
    item.data_vencimento = payload.data_vencimento
    item.data_pagamento = data_pagamento
    item.status = payload.status
    item.justificativa_status = justificativa
    item.carteira = _user_carteira(user)


def _apply_detail(
    db: Session,
    item: ProducaoRegistro,
    user: User,
    payload: ProducaoCreate | ProducaoUpdate,
    npj: str,
    cpf: str | None,
    gecor: str,
    data_primeiro_atraso: date | None,
    valor_ho: Decimal,
    percentual: Decimal,
    autorizacao: str,
) -> None:
    if _uses_schema_mode(db, user):
        fields = _payload_fields(payload)
        if _is_alpha(user):
            cpf_value = _normalize_text(str(_field_value(fields, "CPF_CNPJ", "CPF", "CNPJ") or ""))
            first_delay = _date_from_dynamic_value(
                _field_value(fields, "DATA_DO_1_ATRASO", "DATA_PRIMEIRO_ATRASO"),
                "Data do 1o atraso",
            )
            wallet_value = _normalize_text(str(_field_value(fields, "CARTEIRA") or ""))
            if not item.alpha:
                item.alpha = ProducaoAlpha(
                    producao_id=item.id,
                    debit_id=npj,
                    cpf=cpf_value,
                    data_primeiro_atraso=first_delay,
                    carteira_alpha=wallet_value,
                )
            item.alpha.debit_id = _normalize_text(npj)
            item.alpha.cpf = cpf_value
            item.alpha.data_primeiro_atraso = first_delay
            item.alpha.portfolio = _optional_text(str(_field_value(fields, "PORTFOLIO") or ""))
            item.alpha.carteira_alpha = wallet_value
            if item.gamma:
                db.delete(item.gamma)
                item.gamma = None
            if item.beta_detail:
                db.delete(item.beta_detail)
                item.beta_detail = None
        elif _is_beta(user):
            if not item.beta_detail:
                item.beta_detail = ProducaoBeta(producao_id=item.id, suitid=npj)
            item.beta_detail.suitid = _normalize_text(npj)
            if item.gamma:
                db.delete(item.gamma)
                item.gamma = None
            if item.alpha:
                db.delete(item.alpha)
                item.alpha = None
        else:
            if item.alpha:
                db.delete(item.alpha)
                item.alpha = None
            if item.beta_detail:
                db.delete(item.beta_detail)
                item.beta_detail = None
            if _is_gamma(user):
                if not item.gamma:
                    item.gamma = ProducaoGamma(
                        producao_id=item.id,
                        npj=npj,
                        gecor=gecor or "",
                        valor_ho=valor_ho,
                        percentual_ho=percentual,
                        autorizacao_flexibilizacao=autorizacao,
                    )
                item.gamma.npj = _normalize_text(npj)
                item.gamma.gecor = _normalize_text(gecor or "")
                item.gamma.valor_ho = valor_ho
                item.gamma.percentual_ho = percentual
                item.gamma.autorizacao_flexibilizacao = autorizacao
        _upsert_dynamic_fields(db, item, user, payload)
        return

    if _is_alpha(user):
        if item.gamma:
            db.delete(item.gamma)
            item.gamma = None
        if item.beta_detail:
            db.delete(item.beta_detail)
            item.beta_detail = None
        if not item.alpha:
            item.alpha = ProducaoAlpha(producao_id=item.id, debit_id=npj, cpf=cpf or "", data_primeiro_atraso=data_primeiro_atraso, carteira_alpha=payload.carteira_alpha or "AUTOS")
        item.alpha.debit_id = _normalize_text(npj)
        item.alpha.cpf = cpf or ""
        item.alpha.data_primeiro_atraso = data_primeiro_atraso
        item.alpha.portfolio = _optional_text(payload.portfolio)
        item.alpha.carteira_alpha = payload.carteira_alpha or "AUTOS"
        _clear_dynamic_fields(db, item)
        return

    if _is_beta(user):
        if item.gamma:
            db.delete(item.gamma)
            item.gamma = None
        if item.alpha:
            db.delete(item.alpha)
            item.alpha = None
        if not item.beta_detail:
            item.beta_detail = ProducaoBeta(producao_id=item.id, suitid=npj)
        item.beta_detail.suitid = _normalize_text(npj)
        _clear_dynamic_fields(db, item)
        return

    if item.alpha:
        db.delete(item.alpha)
        item.alpha = None
    if item.beta_detail:
        db.delete(item.beta_detail)
        item.beta_detail = None
    _clear_dynamic_fields(db, item)
    if not item.gamma:
        item.gamma = ProducaoGamma(producao_id=item.id, npj=npj, gecor=gecor, valor_ho=valor_ho, percentual_ho=percentual, autorizacao_flexibilizacao=autorizacao)
    item.gamma.npj = _normalize_text(npj)
    item.gamma.gecor = _normalize_text(gecor)
    item.gamma.valor_ho = valor_ho
    item.gamma.percentual_ho = percentual
    item.gamma.autorizacao_flexibilizacao = autorizacao


def _clear_dynamic_fields(db: Session, item: ProducaoRegistro) -> None:
    for field in list(item.campos or []):
        db.delete(field)
    item.campos = []


def _dynamic_value_is_empty(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _normalize_multiselect_value(value: object) -> list[str]:
    if _dynamic_value_is_empty(value):
        return []
    source: object = value
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                source = json.loads(text)
            except json.JSONDecodeError:
                source = re.split(r"[;,]", text)
        else:
            source = re.split(r"[;,]", text)
    if not isinstance(source, (list, tuple, set)):
        source = [source]
    result: list[str] = []
    seen: set[str] = set()
    for item in source:
        normalized = _normalize_text(str(item))
        key = _field_key(normalized)
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def _coerce_dynamic_value(column: CarteiraColuna, value: object) -> tuple[str | None, Decimal | None, date | None, object | None]:
    if _dynamic_value_is_empty(value):
        return None, None, None, None
    if column.tipo == "multiselect":
        normalized = _normalize_multiselect_value(value)
        return None, None, None, normalized or None
    if column.tipo in {"numero", "moeda"}:
        if isinstance(value, Decimal):
            return None, _money(value), None, None
        text = re.sub(r"[^0-9,.\-]", "", str(value).strip())
        if not text:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{column.nome} deve conter um valor numerico valido.",
            )
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        elif text.count(".") > 1:
            parts = text.split(".")
            text = "".join(parts[:-1]) + "." + parts[-1] if len(parts[-1]) <= 2 else "".join(parts)
        elif "." in text:
            whole, decimal = text.rsplit(".", 1)
            if len(decimal) == 3 and whole.replace("-", "").isdigit():
                text = whole + decimal
        try:
            return None, _money(Decimal(text)), None, None
        except InvalidOperation as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{column.nome} deve conter um valor numerico valido.",
            ) from exc
    if column.tipo == "data":
        if isinstance(value, date):
            return None, None, value, None
        raw_value = str(value).strip()
        try:
            if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", raw_value):
                day, month, year = (int(part) for part in raw_value.split("/"))
                parsed_date = date(year, month, day)
            else:
                parsed_date = date.fromisoformat(raw_value[:10])
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{column.nome} deve ser uma data valida no formato DD/MM/AAAA.",
            ) from exc
        return None, None, parsed_date, None
    if column.tipo == "boolean":
        return "SIM" if bool(value) else "NAO", None, None, None
    return _normalize_text(str(value)), None, None, None


def _sync_dynamic_system_fields(db: Session, item: ProducaoRegistro, user: User, values: dict[str, object]) -> None:
    columns = [column for column in _dynamic_columns(db, user) if column.chave in values]
    if not columns:
        return

    current = {field.coluna_id: field for field in item.campos or []}
    for column in columns:
        valor_texto, valor_numero, valor_data, valor_json = _coerce_dynamic_value(column, values[column.chave])
        field = current.get(column.id)
        existing_field = field is not None
        if not field:
            field = ProducaoCampo(producao_id=item.id, coluna_id=column.id)
            item.campos.append(field)
        field.valor_texto = valor_texto
        field.valor_numero = valor_numero
        field.valor_data = valor_data
        field.valor_json = valor_json
        if existing_field and valor_json is None:
            # Legacy rows may contain JSON literal null. It is loaded as Python
            # None, so SQLAlchemy needs an explicit dirty flag to write SQL NULL.
            flag_modified(field, "valor_json")


def _automatic_dynamic_value(column: CarteiraColuna, user: User) -> object | None:
    if not column.automatico:
        return None
    auto_tipo = str(column.auto_tipo or "").strip().lower()
    if auto_tipo == "today":
        return date.today()
    if auto_tipo == "usuario" and column.tipo in {"texto", "select"}:
        return user.username
    if auto_tipo == "carteira" and column.tipo in {"texto", "select"}:
        return _user_carteira(user)
    return None


def _is_dynamic_honorarios_column(column: CarteiraColuna) -> bool:
    key = str(column.chave or "").upper()
    name = str(column.nome or "").upper()
    return (
        "RECEBID" not in key
        and "RECEBID" not in name
        and (key in {"HONORARIOS", "HONOR_RIOS", "H_O", "HO", "VALOR_HO", "H_O_VALOR"} or "HONOR" in name)
    )


def _honorarios_rule(wallet: CarteiraNegocial | None) -> CarteiraRegraCalculo | None:
    if not wallet:
        return None
    return next(
        (
            rule
            for rule in wallet.regras_calculo
            if rule.codigo == "HONORARIOS" and rule.ativo
        ),
        None,
    )


def _rule_decimal_value(column: CarteiraColuna | None, value: object) -> Decimal | None:
    if not column or _dynamic_value_is_empty(value):
        return None
    _, numeric_value, _, _ = _coerce_dynamic_value(column, value)
    return numeric_value


def _quantized_rule_value(value: Decimal, decimal_places: int) -> Decimal:
    places = max(0, min(int(decimal_places), 6))
    quantum = Decimal("1").scaleb(-places)
    return value.quantize(quantum)


def _explicit_ho_values(
    rule: CarteiraRegraCalculo | None,
    system_values: dict[str, object],
    fields: dict[str, object],
) -> dict[int, Decimal]:
    if (
        not rule
        or not rule.automatico
        or rule.percentual_padrao is None
        or not rule.coluna_destino
    ):
        return {}
    engine = str(getattr(rule, "motor_calculo", None) or "PERCENTUAL_FIXO")
    if engine == "ALPHA_EXCEPCIONAL":
        return {}
    if engine == "PERCENTUAL_CONDICIONAL":
        agreement_type = _field_key(
            system_values.get("TIPO")
            or system_values.get("TIPO_DE_ACORDO")
            or system_values.get("PARCELADO_OU_A_VISTA")
        )
        base_column = (
            rule.coluna_base_parcelado
            if agreement_type == "PARCELADO"
            else rule.coluna_base_vista
        )
    else:
        base_column = rule.coluna_base
    if not base_column:
        return {}
    base_value = system_values.get(base_column.chave, fields.get(base_column.chave))
    base_number = _rule_decimal_value(base_column, base_value)
    if base_number is None:
        return {}

    result = {
        rule.coluna_destino_id: _quantized_rule_value(
            base_number * Decimal(str(rule.percentual_padrao)) / Decimal("100"),
            rule.casas_decimais,
        )
    }
    if (
        rule.coluna_valor_recebido
        and rule.coluna_percentual_efetivo
        and base_number != 0
    ):
        received_column = rule.coluna_valor_recebido
        received_value = system_values.get(
            received_column.chave,
            fields.get(received_column.chave),
        )
        received_number = _rule_decimal_value(received_column, received_value)
        if received_number is not None:
            result[rule.coluna_percentual_efetivo_id] = _quantized_rule_value(
                received_number * Decimal("100") / base_number,
                rule.casas_decimais,
            )
    return result


def _stored_dynamic_value(field: ProducaoCampo | None) -> object | None:
    if not field:
        return None
    if field.valor_data is not None:
        return field.valor_data
    if field.valor_numero is not None:
        return field.valor_numero
    if field.valor_texto not in (None, ""):
        return field.valor_texto
    if field.valor_json is not None:
        return field.valor_json
    return None


def _upsert_dynamic_fields(db: Session, item: ProducaoRegistro, user: User, payload: ProducaoCreate | ProducaoUpdate) -> None:
    wallet = _carteira_definition(db, user)
    columns = sorted(wallet.colunas, key=lambda column: (column.ordem, column.id)) if wallet else []
    if not columns:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Carteira sem colunas configuradas.",
        )
    fields = _payload_fields(payload)
    current = {field.coluna_id: field for field in item.campos or []}
    status_value = _normalize_status_value(fields.get("STATUS") or payload.status)
    explicit_rule = _honorarios_rule(wallet)
    auto_ho_percent = (
        Decimal(str(wallet.percentual_ho_padrao))
        if wallet
        and explicit_rule is None
        and wallet.usa_percentual_ho
        and wallet.calculo_automatico_ho
        and wallet.percentual_ho_padrao is not None
        else None
    )
    gamma = item.gamma if _is_gamma(user) else None
    system_values = {
        "DATA": item.data_acordo,
        "DATA_ACORDO": item.data_acordo,
        "CLIENTE": item.cliente,
        "VALOR_DO_ACORDO": item.valor_total_acordo,
        "VALOR_TOTAL": item.valor_total_acordo,
        "VALOR_TOTAL_DE_ACORDO": item.valor_total_acordo,
        "VALOR_DA_ENTRADA": item.valor_entrada,
        "ENTRADA": item.valor_entrada,
        "TIPO": item.tipo_acordo,
        "TIPO_DE_ACORDO": item.tipo_acordo,
        "PARCELADO_OU_VISTA": item.tipo_acordo,
        "PARCELADO_OU_A_VISTA": item.tipo_acordo,
        "DATA_DE_VENCIMENTO": item.data_vencimento,
        "DATA_DO_VENCIMENTO": item.data_vencimento,
        "DATA_DO_PAGAMENTO": item.data_pagamento,
        "STATUS": item.status,
        "JUSTIFICATIVA": item.justificativa_status or "",
        "NEGOCIADOR": user.username,
        "OPERADOR": user.username,
        "NPJ": gamma.npj if gamma else fields.get("NPJ"),
        "GECOR": gamma.gecor if gamma else fields.get("GECOR"),
        "HONOR_RIOS": fields.get("HONOR_RIOS"),
        "HONORARIOS": fields.get("HONORARIOS"),
        "HONOR_RIOS_RECEBIDOS": gamma.valor_ho if gamma else fields.get("HONOR_RIOS_RECEBIDOS"),
        "HONORARIOS_RECEBIDOS": gamma.valor_ho if gamma else fields.get("HONORARIOS_RECEBIDOS"),
        "PERCENTUAL": gamma.percentual_ho if gamma else fields.get("PERCENTUAL"),
        "AUTORIZADO": gamma.autorizacao_flexibilizacao if gamma else fields.get("AUTORIZADO"),
    }
    calculated_values = _explicit_ho_values(explicit_rule, system_values, fields)

    for column in columns:
        value = system_values.get(column.chave, fields.get(column.chave))
        field = current.get(column.id)
        if column.chave not in system_values and column.automatico:
            value = _stored_dynamic_value(field) or _automatic_dynamic_value(column, user)
        if column.id in calculated_values:
            value = calculated_values[column.id]
        elif auto_ho_percent is not None and _is_dynamic_honorarios_column(column):
            value = (item.valor_total_acordo or Decimal("0")) * auto_ho_percent / Decimal("100")
        if column.chave == "STATUS":
            value = status_value
        is_justificativa = column.chave == "JUSTIFICATIVA"
        required_now = column.obrigatoria and column.mostrar_cadastro and (not is_justificativa or status_value in JUSTIFICATIVA_STATUS)
        if required_now and _dynamic_value_is_empty(value):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{column.nome} e obrigatorio.",
            )
        if is_justificativa and status_value not in JUSTIFICATIVA_STATUS:
            value = ""
        if column.tipo == "select" and value not in (None, ""):
            options = _schema_options(column)
            option_by_key = {_field_key(option): option for option in options}
            normalized_option = option_by_key.get(_field_key(value))
            if options and normalized_option is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Selecione uma opcao valida para {column.nome}.",
                )
            if normalized_option is not None and column.chave != "STATUS":
                value = normalized_option
        if column.tipo == "multiselect" and not _dynamic_value_is_empty(value):
            selected = _normalize_multiselect_value(value)
            options = _schema_options(column)
            option_by_key = {_field_key(option): option for option in options}
            invalid = [option for option in selected if options and _field_key(option) not in option_by_key]
            if invalid:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Selecione opcoes validas para {column.nome}.",
                )
            value = [option_by_key.get(_field_key(option), option) for option in selected]
        if column.max_length and not _dynamic_value_is_empty(value) and column.tipo in {"texto", "select", "multiselect"}:
            values = value if isinstance(value, list) else [value]
            if any(len(str(item)) > int(column.max_length) for item in values):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"{column.nome} deve ter no maximo {column.max_length} caracteres.",
                )
        valor_texto, valor_numero, valor_data, valor_json = _coerce_dynamic_value(column, value)
        existing_field = field is not None
        if not field:
            field = ProducaoCampo(producao_id=item.id, coluna_id=column.id)
            item.campos.append(field)
        field.valor_texto = valor_texto
        field.valor_numero = valor_numero
        field.valor_data = valor_data
        field.valor_json = valor_json
        if existing_field and valor_json is None:
            flag_modified(field, "valor_json")


def _ensure_unique_identifier(
    db: Session,
    user: User,
    identifier: str,
    competencia_date: date,
    current_id: int | None = None,
) -> None:
    month_start, next_month_start = _month_range(competencia_date)
    if _is_alpha(user):
        query = (
            db.query(ProducaoRegistro)
            .join(ProducaoAlpha)
            .filter(
                ProducaoRegistro.user_id == user.id,
                ProducaoRegistro.competencia >= month_start,
                ProducaoRegistro.competencia < next_month_start,
                ProducaoAlpha.debit_id == identifier,
            )
        )
        label = "DEBIT ID"
    elif _is_beta(user):
        query = (
            db.query(ProducaoRegistro)
            .join(ProducaoBeta)
            .filter(
                ProducaoRegistro.user_id == user.id,
                ProducaoRegistro.competencia >= month_start,
                ProducaoRegistro.competencia < next_month_start,
                ProducaoBeta.suitid == identifier,
            )
        )
        label = "SUITID"
    elif _uses_schema_mode(db, user):
        identifier_column = _identifier_column(db, user)
        if not identifier_column:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Carteira sem coluna identificadora configurada.",
            )
        query = (
            db.query(ProducaoRegistro)
            .join(ProducaoCampo)
            .filter(
                ProducaoRegistro.user_id == user.id,
                ProducaoRegistro.competencia >= month_start,
                ProducaoRegistro.competencia < next_month_start,
                ProducaoCampo.coluna_id == identifier_column.id,
                ProducaoCampo.valor_texto == identifier,
            )
        )
        label = identifier_column.nome
    else:
        query = (
            db.query(ProducaoRegistro)
            .join(ProducaoGamma)
            .filter(
                ProducaoRegistro.user_id == user.id,
                ProducaoRegistro.competencia >= month_start,
                ProducaoRegistro.competencia < next_month_start,
                ProducaoGamma.npj == identifier,
            )
        )
        label = "NPJ"

    if current_id:
        query = query.filter(ProducaoRegistro.id != current_id)

    existing = query.first()
    if existing:
        month_label = competencia_date.strftime("%m/%Y")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ja existe um cliente cadastrado com este {label} na competencia {month_label}.",
        )


def _item_identifier(item: ProducaoRegistro, user: User) -> str:
    identifier = next((field for field in item.campos if field.coluna and field.coluna.identificador), None)
    if identifier:
        return str(_dynamic_field_value(identifier) or "")
    if _is_alpha(user):
        return item.alpha.debit_id if item.alpha else ""
    if _is_beta(user):
        return item.beta_detail.suitid if item.beta_detail else ""
    return item.gamma.npj if item.gamma else ""


def _next_month_dynamic_system_values(clone: ProducaoRegistro, user: User) -> dict[str, object]:
    return {
        "DATA": clone.data_acordo,
        "DATA_ACORDO": clone.data_acordo,
        "STATUS": clone.status,
        "JUSTIFICATIVA": "",
        "DATA_DO_PAGAMENTO": None,
        "NEGOCIADOR": user.username,
        "OPERADOR": user.username,
    }


def _clone_to_next_month(db: Session, user: User, item: ProducaoRegistro, next_date: date) -> ProducaoRegistro:
    identifier = _item_identifier(item, user)
    if identifier:
        _ensure_unique_identifier(db, user, identifier, next_date)

    clone = ProducaoRegistro(
        data_acordo=next_date,
        competencia=next_date.replace(day=1),
        cliente=item.cliente,
        valor_total_acordo=item.valor_total_acordo,
        valor_entrada=item.valor_entrada,
        tipo_acordo=item.tipo_acordo,
        data_vencimento=item.data_vencimento,
        data_pagamento=None,
        status="PROPOSTA",
        justificativa_status=None,
        carteira=item.carteira,
        user_id=item.user_id,
    )
    db.add(clone)
    db.flush()

    if item.alpha:
        clone.alpha = ProducaoAlpha(
            producao_id=clone.id,
            debit_id=item.alpha.debit_id,
            cpf=item.alpha.cpf,
            data_primeiro_atraso=item.alpha.data_primeiro_atraso,
            portfolio=item.alpha.portfolio,
            carteira_alpha=item.alpha.carteira_alpha,
        )

    if item.beta_detail:
        clone.beta_detail = ProducaoBeta(
            producao_id=clone.id,
            suitid=item.beta_detail.suitid,
        )

    if item.gamma:
        clone.gamma = ProducaoGamma(
            producao_id=clone.id,
            npj=item.gamma.npj,
            gecor=item.gamma.gecor,
            valor_ho=item.gamma.valor_ho,
            percentual_ho=item.gamma.percentual_ho,
            autorizacao_flexibilizacao=item.gamma.autorizacao_flexibilizacao,
        )

    if item.campos:
        for field in item.campos:
            clone.campos.append(
                ProducaoCampo(
                    producao_id=clone.id,
                    coluna_id=field.coluna_id,
                    valor_texto=field.valor_texto,
                    valor_numero=field.valor_numero,
                    valor_data=field.valor_data,
                    valor_json=field.valor_json,
                )
            )
        _sync_dynamic_system_fields(db, clone, user, _next_month_dynamic_system_values(clone, user))
    return clone


def _rollover_candidates(db: Session, user: User, reference: date) -> list[ProducaoRegistro]:
    source = _previous_month_start(reference)
    return (
        _visible_query(db, user)
        .filter(
            ProducaoRegistro.user_id == user.id,
            ProducaoRegistro.competencia == source,
            ProducaoRegistro.status.in_(tuple(AUTO_BREAK_STATUSES)),
        )
        .order_by(ProducaoRegistro.cliente.asc(), ProducaoRegistro.id.asc())
        .all()
    )


def _rollover_batch(db: Session, user: User, reference: date) -> ProducaoViradaMensal | None:
    return (
        db.query(ProducaoViradaMensal)
        .filter(
            ProducaoViradaMensal.user_id == user.id,
            ProducaoViradaMensal.competencia_origem == _previous_month_start(reference),
            ProducaoViradaMensal.competencia_destino == _current_month_start(reference),
        )
        .first()
    )


def _validated_rollover_decisions(
    candidates: list[ProducaoRegistro],
    decisions: list[tuple[int, str, bool]],
) -> dict[int, tuple[str, bool]]:
    candidate_ids = {item.id for item in candidates}
    decisions_by_id = {item_id: (decision, move_next_month) for item_id, decision, move_next_month in decisions}
    if len(decisions_by_id) != len(decisions) or set(decisions_by_id) != candidate_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Classifique todos os acordos da virada mensal antes de continuar.",
        )
    if any(value[0] not in {"QUEBRA", "PROPOSTA_NEGADA"} for value in decisions_by_id.values()):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Classificacao mensal invalida.")
    return decisions_by_id


def get_month_rollover(db: Session, user: User, reference: date | None = None) -> dict:
    today = reference or date.today()
    auto_broken = auto_break_previous_month_items(db, user, today)
    source = _previous_month_start(today)
    target = _current_month_start(today)
    deadline = _second_business_day(today)
    batch = _rollover_batch(db, user, today)
    exception = _active_rollover_exception(db, user, today)
    candidates = [] if batch or (today >= deadline and not exception) else _rollover_candidates(db, user, today)
    return {
        "required": bool(candidates),
        "competencia_origem": source.isoformat(),
        "competencia_destino": target.isoformat(),
        "prazo": deadline.isoformat(),
        "confirmado": bool(batch),
        "quebras_automaticas": auto_broken,
        "excecao_temporaria": bool(exception),
        "items": [
            {
                "id": item.id,
                "cliente": item.cliente,
                "identificador": _item_identifier(item, user),
                "status": item.status,
                "valor_total_acordo": float(item.valor_total_acordo or 0),
                "valor_entrada": float(item.valor_entrada or 0),
                "data_vencimento": item.data_vencimento.isoformat() if item.data_vencimento else None,
            }
            for item in candidates
        ],
    }


def confirm_month_rollover(
    db: Session,
    user: User,
    decisoes: list[tuple[int, str, bool]],
    reference: date | None = None,
) -> dict:
    today = reference or date.today()
    deadline = _second_business_day(today)
    exception = _active_rollover_exception(db, user, today)
    if today >= deadline and not exception:
        auto_break_previous_month_items(db, user, today)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O prazo da virada mensal foi encerrado e os casos restantes foram quebrados automaticamente.",
        )
    if _rollover_batch(db, user, today):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A virada deste mes ja foi confirmada.")

    candidates = _rollover_candidates(db, user, today)
    by_id = {item.id: item for item in candidates}
    decisions_by_id = _validated_rollover_decisions(candidates, decisoes)

    target = _current_month_start(today)
    transferred_ids: list[int] = []
    denied_ids: list[int] = []
    for item_id, (decision, move_next_month) in decisions_by_id.items():
        item = by_id[item_id]
        before = serialize_producao(item)
        item.status = decision
        item.justificativa_status = (
            ROLLOVER_BREAK_JUSTIFICATIVA
            if decision == "QUEBRA"
            else ROLLOVER_DENIED_JUSTIFICATIVA
        )
        item.data_pagamento = None
        _sync_dynamic_system_fields(
            db,
            item,
            user,
            {"STATUS": item.status, "JUSTIFICATIVA": item.justificativa_status, "DATA_DO_PAGAMENTO": None},
        )
        db.flush()
        record_audit(
            db,
            user=user,
            action="month_rollover_classification",
            entity_type="producao",
            entity_id=item.id,
            before=before,
            after=serialize_producao(item),
            reason=item.justificativa_status,
        )
        if move_next_month:
            clone = _clone_to_next_month(db, user, item, target)
            db.flush()
            transferred_ids.append(item.id)
            record_audit(
                db,
                user=user,
                action="month_rollover_clone",
                entity_type="producao",
                entity_id=clone.id,
                after=serialize_producao(clone),
                reason=ROLLOVER_TRANSFER_JUSTIFICATIVA,
            )
        else:
            denied_ids.append(item.id)

    if exception:
        exception.consumida_em = datetime.now(timezone.utc)

    db.add(
        ProducaoViradaMensal(
            user_id=user.id,
            competencia_origem=_previous_month_start(today),
            competencia_destino=target,
            total_candidatos=len(candidates),
            total_transferidos=len(transferred_ids),
            ids_transferidos=transferred_ids,
        )
    )
    bump_version(db, "producao")
    db.commit()
    return {
        "confirmado": True,
        "total_candidatos": len(candidates),
        "total_transferidos": len(transferred_ids),
        "total_propostas_negadas": len(denied_ids),
        "aguardando_quebra_automatica": 0,
        "quebrados_automaticamente": 0,
        "competencia_destino": target.isoformat(),
    }


def create_producao(db: Session, user: User, payload: ProducaoCreate) -> dict:
    payload.status = _normalize_status_value(payload.status, payload.status)
    npj, cpf, gecor, data_primeiro_atraso = _validate_identifiers(db, payload, user)
    data_acordo = _resolve_production_date(payload.jogar_proximo_mes)
    _ensure_unique_identifier(db, user, npj, data_acordo)
    valor_total, valor_entrada, valor_ho, percentual, autorizacao = _resolve_values(db, payload, user)
    justificativa = _resolve_justificativa(payload.status, payload.justificativa_status)
    data_pagamento = _resolve_data_pagamento(payload.status, payload.data_pagamento)
    item = ProducaoRegistro(
        data_acordo=data_acordo,
        competencia=data_acordo.replace(day=1),
        cliente=_normalize_text(payload.cliente),
        valor_total_acordo=valor_total,
        valor_entrada=valor_entrada,
        tipo_acordo=payload.tipo_acordo,
        data_vencimento=payload.data_vencimento,
        data_pagamento=data_pagamento,
        status=payload.status,
        justificativa_status=justificativa,
        carteira=_user_carteira(user),
        user_id=user.id,
    )
    db.add(item)
    db.flush()
    _apply_detail(db, item, user, payload, npj, cpf, gecor, data_primeiro_atraso, valor_ho, percentual, autorizacao)
    db.flush()
    after = serialize_producao(item)
    record_audit(db, user=user, action="create", entity_type="producao", entity_id=item.id, after=after)
    bump_version(db, "producao")
    db.commit()
    db.refresh(item)
    return serialize_producao(get_producao(db, user, item.id))


def update_producao(db: Session, user: User, producao_id: int, payload: ProducaoUpdate) -> dict:
    payload.status = _normalize_status_value(payload.status, payload.status)
    item = get_producao(db, user, producao_id)
    _ensure_current_month_editable(item)
    before = serialize_producao(item)
    previous_status = _normalize_status_value(item.status, item.status)
    npj, cpf, gecor, data_primeiro_atraso = _validate_identifiers(db, payload, user)
    _ensure_unique_identifier(db, user, npj, item.data_acordo, current_id=item.id)
    valor_total, valor_entrada, valor_ho, percentual, autorizacao = _resolve_values(db, payload, user)
    justificativa = _resolve_justificativa(payload.status, payload.justificativa_status)
    data_pagamento = _resolve_data_pagamento(payload.status, payload.data_pagamento)

    _apply_common_fields(item, user, payload, valor_total, valor_entrada, data_pagamento, justificativa)
    _apply_formalized_new_agreement(
        item,
        previous_status,
        payload.status,
        payload.formalizado_novo_acordo,
    )
    _apply_detail(db, item, user, payload, npj, cpf, gecor, data_primeiro_atraso, valor_ho, percentual, autorizacao)
    db.flush()
    after = serialize_producao(item)
    record_audit(db, user=user, action="update", entity_type="producao", entity_id=item.id, before=before, after=after)
    bump_version(db, "producao")

    db.commit()
    db.refresh(item)
    return serialize_producao(get_producao(db, user, item.id))


def update_producao_status(
    db: Session,
    user: User,
    producao_id: int,
    payload: ProducaoStatusUpdate,
) -> dict:
    payload.status = _normalize_status_value(payload.status, payload.status)
    item = get_producao(db, user, producao_id)
    _ensure_current_month_editable(item)
    before = serialize_producao(item)
    previous_status = _normalize_status_value(item.status, item.status)
    move_to_next_month = payload.status == "QUEBRA" and payload.jogar_proximo_mes
    next_month_date = _resolve_production_date(True) if move_to_next_month else None
    item.status = payload.status
    item.justificativa_status = _resolve_justificativa(payload.status, payload.justificativa_status)
    item.data_pagamento = _resolve_data_pagamento(payload.status, payload.data_pagamento)
    _apply_formalized_new_agreement(
        item,
        previous_status,
        payload.status,
        payload.formalizado_novo_acordo,
    )
    _sync_dynamic_system_fields(
        db,
        item,
        user,
        {
            "STATUS": item.status,
            "JUSTIFICATIVA": item.justificativa_status or "",
            "DATA_DO_PAGAMENTO": item.data_pagamento,
        },
    )
    if move_to_next_month and next_month_date:
        _clone_to_next_month(db, user, item, next_month_date)
    db.flush()
    after = serialize_producao(item)
    record_audit(
        db,
        user=user,
        action="status_update",
        entity_type="producao",
        entity_id=item.id,
        before=before,
        after=after,
        reason=payload.justificativa_status,
    )
    bump_version(db, "producao")
    db.commit()
    db.refresh(item)
    return serialize_producao(get_producao(db, user, item.id))


def delete_producao(db: Session, user: User, producao_id: int):
    item = get_producao(db, user, producao_id)
    _ensure_current_month_editable(item)
    before = serialize_producao(item)
    record_audit(db, user=user, action="delete", entity_type="producao", entity_id=item.id, before=before)
    bump_version(db, "producao")
    db.delete(item)
    db.commit()
