import { formatSheetValue } from "./sheetFormat.js";

const MONEY_HEADERS = new Set([
  "HONORARIOS",
  "HONORÃRIOS",
  "HONORÁRIOS",
  "HONORÃRIOS RECEBIDOS",
  "HONORÁRIOS RECEBIDOS",
  "VALOR TOTAL",
  "VALOR DO ACORDO",
  "ENTRADA",
  "VALOR DA ENTRADA",
]);

export function displayCellValue(header, value) {
  if (Array.isArray(value)) return value.map((item) => String(item || "").trim()).filter(Boolean).join("; ");
  if (MONEY_HEADERS.has(header)) return money(value);
  if (header === "%" || header === "% H.O") return `${Number(value || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
  if (header === "ULTIMA ATUALIZACAO") return dateTime(value);
  return formatSheetValue(header, value);
}

export function money(value) {
  const number = Number(value || 0);
  return number.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function dateTime(value) {
  if (!value) return "Vazio";
  const date = new Date(String(value).replace(" ", "T"));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("pt-BR");
}
