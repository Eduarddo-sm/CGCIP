import { criticalStatuses, normalStatusValues, statusLabels, tipoLabels } from "./constants.js?v=20260714-module-contract-1";

export function statusOptions(selectedStatus, includeCritical = true) {
  const values = includeCritical
    ? Object.keys(statusLabels)
    : [...normalStatusValues, ...(criticalStatuses.has(selectedStatus) ? [selectedStatus] : [])];

  return values.map((value) => `
    <option value="${value}" ${value === selectedStatus ? "selected" : ""}>${statusLabels[value]}</option>
  `).join("");
}

export function normalizeOptionValue(value, labels, fallback = "") {
  const raw = String(value ?? "").trim();
  if (!raw) return fallback;
  if (labels[raw]) return raw;

  const comparable = raw
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .replace(/\s+/g, "_");

  const direct = Object.keys(labels).find((key) => key === comparable);
  if (direct) return direct;

  const byLabel = Object.entries(labels).find(([, label]) => label
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .replace(/\s+/g, "_") === comparable);

  return byLabel?.[0] || fallback;
}

export function normalizeStatusValue(value, fallback) {
  return normalizeOptionValue(value, statusLabels, fallback);
}

export function normalizeTipoValue(value, fallback) {
  return normalizeOptionValue(value, tipoLabels, fallback);
}
