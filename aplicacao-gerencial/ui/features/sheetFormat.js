import { formatValue } from "../core/format.js";

export function formatSheetValue(header, value) {
  if (value === null || value === undefined || value === "") return "Vazio";
  if (isDateColumn(header) || isIsoDateValue(value)) return formatDateBr(value);
  if (isMoneyColumn(header) && isNumericValue(value)) {
    return parseNumericValue(value).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }
  return formatValue(value);
}

function isDateColumn(header) {
  const normalized = normalizeHeader(header);
  return normalized.includes("DATA") || normalized.includes("DT");
}

function isIsoDateValue(value) {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}(T|$)/.test(value);
}

function formatDateBr(value) {
  if (value instanceof Date && !Number.isNaN(value.getTime())) return value.toLocaleDateString("pt-BR");
  const text = String(value || "");
  const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (iso) return `${iso[3]}/${iso[2]}/${iso[1]}`;
  const parsed = new Date(text);
  if (!Number.isNaN(parsed.getTime())) return parsed.toLocaleDateString("pt-BR");
  return formatValue(value);
}

function isMoneyColumn(header) {
  const normalized = normalizeHeader(header);
  return ["VALOR", "SALDO", "PAGO", "PARCELA", "HONORARIO", "CUSTA", "DESPESA", "TOTAL", "BRL", "R$"].some((token) => normalized.includes(token));
}

function isNumericValue(value) {
  return Number.isFinite(parseNumericValue(value));
}

function parseNumericValue(value) {
  if (typeof value === "number") return value;
  if (typeof value !== "string") return Number.NaN;
  const text = value.trim().replace(/[R$\s]/g, "");
  if (!text) return Number.NaN;
  if (text.includes(",")) return Number(text.replace(/\./g, "").replace(",", "."));
  return Number(text);
}

function normalizeHeader(header) {
  return String(header || "")
    .toUpperCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}
