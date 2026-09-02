import { expandChangeRows } from "./changeDiff.js";

export function groupTimelineChangesByLine(event) {
  const groups = new Map();
  (event.delta?.changes || []).forEach((change, changeIndex) => {
    expandChangeRows(change).forEach((rowChange, rowIndex) => {
      if (!isVisibleTimelineChange(rowChange)) return;
      const line = rowChange.excel_row || rowChange.row_id || "";
      const key = String(line || `${changeIndex}-${rowIndex}`);
      if (!groups.has(key)) {
        groups.set(key, { line, client: "", changes: [] });
      }
      const group = groups.get(key);
      if (!group.client) {
        group.client = clientNameFromChange(rowChange) || clientNameFromChange(change);
      }
      group.changes.push(rowChange);
    });
  });
  return [...groups.values()];
}

function isVisibleTimelineChange(change) {
  if (["column_added", "column_removed", "initial_snapshot"].includes(change.type)) return false;
  const before = normalizedValue(change.before);
  const after = normalizedValue(change.after);
  if (!before && !after) return false;
  if (change.type === "cell_changed" && before === after) return false;
  return true;
}

function normalizedValue(value) {
  if (value === null || value === undefined) return "";
  const text = String(value).trim();
  if (["", "none", "null", "nan", "vazio"].includes(text.toLowerCase())) return "";
  return text.replace(/\s+/g, " ");
}

function clientNameFromChange(change) {
  for (const key of ["row_after", "row_before", "after", "before"]) {
    const value = change[key];
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const name = clientNameFromRow(value);
      if (name) return name;
    }
  }
  if (isClientColumn(change.column)) {
    return String(change.after || change.before || "").trim();
  }
  return "";
}

function clientNameFromRow(row) {
  for (const [key, value] of Object.entries(row)) {
    if (!key.startsWith("_") && isClientColumn(key) && value !== null && value !== undefined && value !== "") {
      return String(value).trim();
    }
  }
  return "";
}

function isClientColumn(column) {
  const normalized = String(column || "").trim().toLowerCase();
  return normalized === "cliente"
    || normalized === "nome"
    || normalized === "nome do cliente"
    || normalized === "client"
    || normalized === "customer"
    || normalized.includes("cliente");
}
