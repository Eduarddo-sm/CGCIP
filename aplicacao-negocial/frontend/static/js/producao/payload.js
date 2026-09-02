import { criticalStatuses, paymentStatus } from "./constants.js?v=20260714-schema-only-1";
import { datePayloadValue, decimalPayloadValue } from "./formatters.js?v=20260714-schema-only-1";
import { normalizeStatusValue, normalizeTipoValue } from "./options.js?v=20260714-schema-only-1";

function firstValue(fields, keys, fallback = null) {
  for (const key of keys) {
    const value = fields[key];
    if (value !== undefined && value !== null && String(value).trim() !== "") return value;
  }
  return fallback;
}

export function buildProductionUpdatePayload(item, overrides = {}, options = {}) {
  const fields = { ...(item.campos || {}), ...(overrides.campos || {}) };
  const identifier = fields[options.identifierKey] ?? item.npj ?? "";
  const status = normalizeStatusValue(overrides.status ?? fields.STATUS ?? item.status, item.status || "PROPOSTA");
  const agreementType = normalizeTipoValue(
    overrides.tipo_acordo ?? firstValue(fields, ["TIPO", "TIPO_DE_ACORDO", "PARCELADO_OU_VISTA", "PARCELADO_OU_A_VISTA"], item.tipo_acordo),
    item.tipo_acordo || "PARCELADO",
  );
  const total = overrides.valor_total_acordo ?? firstValue(fields, [
    "VALOR_FECHADO",
    "VALOR_TOTAL_FECHADO",
    "VALOR_DO_ACORDO",
    "VALOR_TOTAL",
    "VALOR_TOTAL_DE_ACORDO",
    "VALOR_TOTAL_DO_DEBITO",
    "VALOR_MINIMO_PRE_APROVADO",
  ], item.valor_total_acordo ?? 0);
  const entry = agreementType === "A_VISTA"
    ? 0
    : overrides.valor_entrada ?? firstValue(fields, ["VALOR_DA_ENTRADA", "ENTRADA", "VALOR_MINIMO_PRE_APROVADO"], item.valor_entrada ?? 0);
  const dueDate = overrides.data_vencimento ?? firstValue(fields, ["DATA_DE_VENCIMENTO", "DATA_DO_VENCIMENTO", "VENCIMENTO"], item.data_vencimento);
  const paymentDate = Object.hasOwn(overrides, "data_pagamento")
    ? overrides.data_pagamento
    : firstValue(fields, ["DATA_DO_PAGAMENTO", "PAGAMENTO"], item.data_pagamento);
  const justification = firstValue(fields, ["JUSTIFICATIVA"], item.justificativa_status);
  const isGamma = Boolean(options.isGamma);

  return {
    npj: String(identifier ?? "").trim(),
    cpf: null,
    cliente: String(firstValue(fields, ["CLIENTE", "NOME", "NOME_CLIENTE"], item.cliente || "Cliente nao informado")).trim(),
    gecor: isGamma ? String(firstValue(fields, ["GECOR"], item.gecor || "")).trim() || null : null,
    dias_atraso: null,
    data_primeiro_atraso: null,
    portfolio: null,
    carteira_alpha: null,
    tipo_acordo: agreementType,
    valor_total_acordo: decimalPayloadValue(total),
    valor_entrada: decimalPayloadValue(entry),
    valor_ho: isGamma
      ? decimalPayloadValue(firstValue(fields, ["HONOR_RIOS_RECEBIDOS", "HONORARIOS_RECEBIDOS", "H_O", "HO", "VALOR_HO"], item.valor_ho ?? 0))
      : null,
    data_vencimento: datePayloadValue(dueDate),
    data_pagamento: status === paymentStatus ? datePayloadValue(paymentDate) : null,
    status,
    justificativa_status: criticalStatuses.has(status) ? justification : null,
    autorizacao_flexibilizacao: isGamma
      ? overrides.autorizacao_flexibilizacao ?? fields.AUTORIZADO ?? item.autorizacao_flexibilizacao ?? null
      : null,
    campos: fields,
  };
}
