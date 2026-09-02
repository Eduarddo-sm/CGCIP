import { normalizeText } from "../core/format.js";

export function protocoloStatus(row) {
  const value = normalizeText(protocoloValue(row, ["STATUS"]));
  if (value === "CONCLUIDO") return "CONCLUIDO";
  return "PENDENTE";
}

export function protocoloValue(row, candidates) {
  const keys = Object.keys(row || {});
  const normalized = new Map(keys.map((key) => [normalizeText(key), key]));
  for (const candidate of candidates) {
    const match = normalized.get(normalizeText(candidate));
    if (match) return row[match];
  }
  return "";
}
