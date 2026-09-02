import { toast } from "../core/toast.js";
import { createExcelGrid } from "./excelGrid.js?v=20260826-edit-tab-1";

export function normalizeGridHeader(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toUpperCase();
}

export function headersFromRows(rows = []) {
  const headers = [];
  const known = new Set();
  rows.forEach((row) => {
    Object.keys(row || {}).forEach((header) => {
      if (!header || header.startsWith("__") || header.startsWith("_")) return;
      const key = normalizeGridHeader(header);
      if (!key || known.has(key)) return;
      known.add(key);
      headers.push(header);
    });
  });
  return headers;
}

export function isGridDateHeader(header) {
  const key = normalizeGridHeader(header);
  return key === "DATA" || key.includes("DATA_") || key.includes("VENCIMENTO") || key === "MES";
}

export function isGridMoneyHeader(header) {
  const key = normalizeGridHeader(header);
  return key.includes("VALOR") || key.includes("HONORARIO") || key === "CASH";
}

export function operationalColumnWidth(header) {
  const key = normalizeGridHeader(header);
  if (key.includes("DESCR") || key.includes("OBSERV") || key === "OBS") return 300;
  if (key === "CLIENTE" || key === "NOME" || key.includes("NOME_CLIENTE")) return 270;
  if (key === "STATUS" || key === "SOLICITADO" || key === "SOLICITADO_") return 176;
  if (key.includes("NEGOCIADOR") || key.includes("OPERADOR") || key.includes("USUARIO")) return 176;
  if (key.includes("NPJ") || key.includes("SUIT") || key.includes("DEBIT") || key.includes("CPF") || key === "PK") return 166;
  if (isGridDateHeader(header)) return 138;
  if (isGridMoneyHeader(header)) return 154;
  return 142;
}

export function mountOperationalExcelGrid(container, options = {}) {
  const element = typeof container === "string" ? document.querySelector(container) : container;
  if (!element) return null;
  const grid = createExcelGrid(element, {
    id: options.id,
    persistKey: options.persistKey,
    filters: options.filters !== false,
    toolbar: options.toolbar !== false,
    virtualThreshold: Number(options.virtualThreshold) || 350,
    onSelectionChange: options.onSelectionChange,
    onError: options.onError || ((error) => toast(error.message || "Nao foi possivel completar a acao.")),
  });
  element.classList.add("monitor-native-excel", "operational-native-excel");
  grid.render(options.rows || [], options.columns || [], { preservePosition: options.preservePosition !== false });
  window.requestAnimationFrame(() => window.requestAnimationFrame(() => grid.refreshLayout?.()));
  return grid;
}
