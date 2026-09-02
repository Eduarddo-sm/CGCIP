import { state } from "../core/state.js";

export const pages = ["dashboard", "clientes", "pendencias", "completo", "cadastro", "configuracoes"];
export const statuses = ["PAGO", "VENCIDO", "A VENCER", "QUEBRA"];
export const profiles = [
  { id: "alpha", name: "Alpha", description: "Carteira Alpha - acordos e parcelas por DEBIT ID", keyLabel: "DEBIT ID", sheets: [] },
  { id: "beta", name: "Beta", description: "Carteira Beta - acordos por SUITID em ATIVO e PASSIVO", keyLabel: "SUITID", sheets: ["ATIVO", "PASSIVO"] },
];

export function replaceProfiles(items = []) {
  const normalized = (Array.isArray(items) ? items : []).map((item) => ({
    id: String(item.id || "").trim().toLowerCase(),
    name: String(item.name || item.id || "").trim(),
    description: String(item.description || "").trim(),
    keyLabel: String(item.keyLabel || "Identificador").trim(),
    sheets: Array.isArray(item.sheets) ? item.sheets.filter(Boolean) : [],
  })).filter((item) => item.id && item.name);
  profiles.splice(0, profiles.length, ...normalized);
}

export function value(row, header) {
  const key = Object.keys(row).find((item) => normalize(item) === normalize(header));
  return String(row[key] ?? "");
}

export function firstValue(row, headers) {
  for (const header of headers) {
    const result = value(row, header);
    if (result) return result;
  }
  return "";
}

export function identifierValue(row) {
  return firstValue(row, ["DEBIT ID", "SUITID", "SUIT"]);
}

export function currentProfile() {
  return profiles.find((profile) => profile.id === state.colchao.profile)
    || profiles[0]
    || { id: String(state.colchao.profile || "").toLowerCase(), name: "Carteira", keyLabel: "Identificador", sheets: [] };
}

export function selectedSheet() {
  const profile = currentProfile();
  if (!profile.sheets.length) return "";
  return state.colchao.sheet || state.colchao.config?.main_sheet || profile.sheets[0];
}

export function labelBucket(bucket) {
  const normalized = normalizePendingBucket(bucket);
  if (normalized === "a_vencer") return "A vencer";
  if (normalized === "vencida") return "Vencida";
  return {
    a_vencer_hoje: "A vencer hoje",
    a_vencer_anterior: "A vencer anterior",
    vencida_hoje: "Vencida hoje",
    vencida_anterior: "Vencida anterior",
  }[bucket] || "Parcela";
}

export function normalizePendingBucket(bucket) {
  const value = String(bucket || "");
  if (value.startsWith("a_vencer")) return "a_vencer";
  if (value.startsWith("vencida")) return "vencida";
  return value;
}

export function dueDateIso(row) {
  const raw = firstValue(row, currentProfile().id === "beta"
    ? ["MÊS", "MES", "DATA DO VENCIMENTO", "MÊS DE EXPIRAÇÃO", "MES DE EXPIRACAO"]
    : ["DATA DO VENCIMENTO", "MÊS", "MES", "MÊS DE EXPIRAÇÃO", "MES DE EXPIRACAO"]);
  const date = parseDateValue(raw);
  return date ? localDateIso(date) : "";
}

export function parseDateValue(value) {
  if (!value) return null;
  if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
  const text = String(value).trim();
  const brDate = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$/);
  if (brDate) {
    const year = Number(brDate[3].length === 2 ? `20${brDate[3]}` : brDate[3]);
    return new Date(year, Number(brDate[2]) - 1, Number(brDate[1]));
  }
  const isoDate = text.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (isoDate) return new Date(Number(isoDate[1]), Number(isoDate[2]) - 1, Number(isoDate[3]));
  const parsed = new Date(text);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function formatDateTime(value) {
  const date = parseDateValue(String(value || "").split("T")[0]);
  const time = String(value || "").match(/(\d{2}:\d{2}(?::\d{2})?)/)?.[1] || "";
  if (!date) return String(value || "");
  return `${date.toLocaleDateString("pt-BR")}${time ? ` ${time}` : ""}`;
}

export function localDateIso(date) {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

export function money(value) {
  return Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function normalize(value) {
  return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-zA-Z0-9]/g, "").toUpperCase();
}

export function capitalize(value) {
  return String(value || "").slice(0, 1).toUpperCase() + String(value || "").slice(1);
}

export function clearColchaoCache() {
  state.colchao.cache = { dashboard: null, records: {}, pendencias: null, clients: null, validation: null };
}

export function clearColchaoRuntimeData(clearCache = true) {
  state.colchao.records = [];
  state.colchao.clients = [];
  state.colchao.pendencias = [];
  state.colchao.dashboard = null;
  state.colchao.completo = { page: 1, pageSize: 100, total: 0, totalPages: 1 };
  state.colchao.pendingStatusChanges = {};
  if (clearCache) clearColchaoCache();
}
