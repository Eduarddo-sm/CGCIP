export const dynamicAgreementTypeKeys = new Set([
  "TIPO",
  "TIPO_DE_ACORDO",
  "PARCELADO_OU_VISTA",
  "PARCELADO_OU_A_VISTA",
]);

export const dynamicEntryValueKeys = new Set(["VALOR_DA_ENTRADA", "ENTRADA"]);
export const dynamicDigitsOnlyKeys = new Set(["NPJ", "CPF", "CNPJ", "CPF_CNPJ", "GECOR"]);

export function normalizedDynamicKey(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toUpperCase();
}

export function dynamicColumnMatches(column, acceptedKeys) {
  return acceptedKeys.has(normalizedDynamicKey(column?.chave))
    || acceptedKeys.has(normalizedDynamicKey(column?.nome));
}

export function isAgreementAtSight(value) {
  const normalized = normalizedDynamicKey(value);
  return normalized === "A_VISTA" || normalized.endsWith("_A_VISTA");
}
