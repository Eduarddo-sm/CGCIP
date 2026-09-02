from __future__ import annotations

from decimal import Decimal

from backend.models import ProducaoGamma, ProducaoCampo, ProducaoAlpha, ProducaoRegistro, ProducaoBeta
from backend.services.producao_values import STATUS_LABELS, TIPO_LABELS, money as _money

def _gamma_detail(item: ProducaoRegistro) -> ProducaoGamma | None:
    return item.gamma


def _alpha_detail(item: ProducaoRegistro) -> ProducaoAlpha | None:
    return item.alpha


def _beta_detail(item: ProducaoRegistro) -> ProducaoBeta | None:
    return item.beta_detail


def dynamic_field_value(field: ProducaoCampo):
    if field.valor_data is not None:
        return field.valor_data.isoformat()
    if field.valor_numero is not None:
        return float(field.valor_numero)
    if field.valor_json is not None:
        return field.valor_json
    return field.valor_texto


def _dynamic_fields(item: ProducaoRegistro) -> dict[str, object]:
    fields: dict[str, object] = {}
    for field in sorted(item.campos or [], key=lambda entry: (entry.coluna.ordem if entry.coluna else 0, entry.coluna_id)):
        if field.coluna:
            fields[field.coluna.chave] = dynamic_field_value(field)
    return fields


def _synchronized_dynamic_fields(item: ProducaoRegistro, fields: dict[str, object]) -> dict[str, object]:
    if not fields:
        return fields
    gamma = item.gamma
    alpha = item.alpha
    beta_detail = item.beta_detail
    values = {
        "DATA": item.data_acordo.isoformat(),
        "DATA_ACORDO": item.data_acordo.isoformat(),
        "CLIENTE": item.cliente,
        "VALOR_DO_ACORDO": float(item.valor_total_acordo),
        "VALOR_TOTAL": float(item.valor_total_acordo),
        "VALOR_TOTAL_DE_ACORDO": float(item.valor_total_acordo),
        "VALOR_DA_ENTRADA": float(item.valor_entrada),
        "ENTRADA": float(item.valor_entrada),
        "TIPO": item.tipo_acordo,
        "TIPO_DE_ACORDO": item.tipo_acordo,
        "PARCELADO_OU_VISTA": item.tipo_acordo,
        "PARCELADO_OU_A_VISTA": item.tipo_acordo,
        "DATA_DE_VENCIMENTO": item.data_vencimento.isoformat(),
        "DATA_DO_VENCIMENTO": item.data_vencimento.isoformat(),
        "DATA_DO_PAGAMENTO": item.data_pagamento.isoformat() if item.data_pagamento else "",
        "STATUS": item.status,
        "JUSTIFICATIVA": item.justificativa_status or "",
        "NEGOCIADOR": item.user.username if item.user else "",
        "OPERADOR": item.user.username if item.user else "",
    }
    if gamma:
        values.update({
            "NPJ": gamma.npj,
            "GECOR": gamma.gecor,
            "HONOR_RIOS": float(_money(item.valor_total_acordo) * Decimal("0.10")),
            "HONORARIOS": float(_money(item.valor_total_acordo) * Decimal("0.10")),
            "HONOR_RIOS_RECEBIDOS": float(gamma.valor_ho),
            "HONORARIOS_RECEBIDOS": float(gamma.valor_ho),
            "PERCENTUAL": float(gamma.percentual_ho),
            "AUTORIZADO": gamma.autorizacao_flexibilizacao,
        })
    if alpha:
        values.update({
            "DEBIT_ID": alpha.debit_id,
            "CPF_CNPJ": alpha.cpf,
            "DATA_DO_1_ATRASO": (
                alpha.data_primeiro_atraso.isoformat()
                if alpha.data_primeiro_atraso
                else ""
            ),
            "PORTFOLIO": alpha.portfolio or "",
            "CARTEIRA": alpha.carteira_alpha,
        })
    if beta_detail:
        values["SUITID"] = beta_detail.suitid
    synchronized = dict(fields)
    for key in synchronized:
        if key in values:
            synchronized[key] = values[key]
    return synchronized


def serialize_producao(item: ProducaoRegistro) -> dict:
    is_alpha = (item.carteira or "").upper() == "ALPHA"
    is_beta = (item.carteira or "").upper() == "BETA"
    gamma = _gamma_detail(item)
    alpha = _alpha_detail(item)
    beta_detail = _beta_detail(item)
    campos = _synchronized_dynamic_fields(item, _dynamic_fields(item))
    dynamic_identifier = next(iter(campos.values()), "") if campos else ""
    npj = (
        alpha.debit_id
        if is_alpha and alpha
        else beta_detail.suitid
        if is_beta and beta_detail
        else gamma.npj
        if gamma
        else str(dynamic_identifier or "")
    )
    valor_ho = Decimal("0.00") if not gamma else gamma.valor_ho
    percentual_ho = Decimal("0.00") if not gamma else gamma.percentual_ho

    data = {
        "id": item.id,
        "data_acordo": item.data_acordo.isoformat(),
        "competencia": (item.competencia or item.data_acordo).strftime("%Y-%m"),
        "npj": npj,
        "cpf": alpha.cpf if alpha else None,
        "cliente": item.cliente,
        "gecor": gamma.gecor if gamma else "",
        "dias_atraso": None,
        "data_primeiro_atraso": (
            alpha.data_primeiro_atraso.isoformat()
            if alpha and alpha.data_primeiro_atraso
            else None
        ),
        "portfolio": alpha.portfolio if alpha else None,
        "carteira_alpha": alpha.carteira_alpha if alpha else None,
        "valor_total_acordo": float(item.valor_total_acordo),
        "valor_entrada": float(item.valor_entrada),
        "valor_ho": float(valor_ho),
        "percentual_ho": float(percentual_ho),
        "tipo_acordo": item.tipo_acordo,
        "tipo_acordo_label": TIPO_LABELS.get(item.tipo_acordo, item.tipo_acordo),
        "data_vencimento": item.data_vencimento.isoformat(),
        "data_pagamento": item.data_pagamento.isoformat() if item.data_pagamento else None,
        "status": item.status,
        "status_label": STATUS_LABELS.get(item.status, item.status),
        "justificativa_status": item.justificativa_status,
        "autorizacao_flexibilizacao": gamma.autorizacao_flexibilizacao if gamma else "NAO",
        "carteira": item.carteira,
        "user_id": item.user_id,
        "usuario": item.user.username if item.user else None,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }
    if campos:
        data["campos"] = campos
        data.update({key.lower(): value for key, value in campos.items() if key.lower() not in data})
    return data
