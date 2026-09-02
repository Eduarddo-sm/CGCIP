import { normalizeText } from "../core/format.js";
import { state } from "../core/state.js";

export function parecerHeader(row, name) {
  const normalized = normalizeText(name);
  return Object.keys(row || {}).find((key) => normalizeText(key).includes(normalized) || normalized.includes(normalizeText(key))) || name;
}

export function parecerPk(row) {
  return row[parecerHeader(row, state.parecer.config?.pk_column || "PK")] ?? "";
}

export function parecerValue(row, candidates) {
  const keys = Object.keys(row || {});
  const normalized = new Map(keys.map((key) => [normalizeText(key), key]));
  for (const candidate of candidates) {
    const match = normalized.get(normalizeText(candidate));
    if (match) return row[match];
  }
  return "";
}
