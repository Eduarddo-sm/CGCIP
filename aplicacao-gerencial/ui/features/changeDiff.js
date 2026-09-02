import { formatValue } from "../core/format.js";
import { escapeHtml } from "../core/html.js";

export function renderMiniRowDiffs(changes) {
  const groups = groupExpandedChangesByLine(changes.flatMap(expandChangeRows));
  if (!groups.length) return "";
  return `<div class="mini-row-diffs">${groups.map((group) => renderMiniRowDiff(group.changes, group.line)).join("")}</div>`;
}

export function renderMiniRowDiff(changes, explicitLine = "") {
  const beforeRow = changes.find((change) => change.row_before)?.row_before || changes.find((change) => change.row_before || change.row_after)?.row_before || null;
  const afterRow = changes.find((change) => change.row_after)?.row_after || changes.find((change) => change.row_after || change.row_before)?.row_after || null;
  const line = explicitLine || changes.find((change) => change.excel_row || change.row_id)?.excel_row || changes.find((change) => change.row_id)?.row_id || "";
  const columns = rowPreviewColumns(beforeRow, afterRow, changes);
  if (!columns.length) return "";
  const changed = new Set(changes.map((change) => change.column).filter(Boolean));
  return `
    <div class="mini-row-diff">
      <div class="mini-row-title">Linha ${escapeHtml(line || "nao identificada")}</div>
      <div class="mini-row-scroll">
      <table>
      <thead>
      <tr><th>Estado</th>${columns.map((column) => `<th class="${changed.has(column) ? "changed-cell" : ""}">${escapeHtml(column)}</th>`).join("")}</tr>
      </thead>
      <tbody>
      <tr><td>Antes</td>${columns.map((column) => `<td class="${changed.has(column) ? "before changed-cell" : ""}">${escapeHtml(formatValue(beforeRow?.[column]))}</td>`).join("")}</tr>
      <tr><td>Depois</td>${columns.map((column) => `<td class="${changed.has(column) ? "after changed-cell" : ""}">${escapeHtml(formatValue(afterRow?.[column]))}</td>`).join("")}</tr>
      </tbody>
      </table>
      </div>
      </div>
      `;
}

function rowPreviewColumns(beforeRow, afterRow, changes) {
  const columns = [];
  [beforeRow, afterRow].forEach((row) => {
    Object.keys(publicRowValues(row || {})).forEach((column) => {
      if (!columns.includes(column)) columns.push(column);
    });
  });
  changes.forEach((change) => {
    if (change.column && !columns.includes(change.column)) columns.push(change.column);
  });
  return columns;
}

function groupExpandedChangesByLine(changes) {
  const groups = new Map();
  changes.forEach((change, index) => {
    const line = change.excel_row || change.row_id || "";
    const key = String(line || index);
    if (!groups.has(key)) groups.set(key, { line, changes: [] });
    groups.get(key).changes.push(change);
  });
  return [...groups.values()];
}

export function expandChangeRows(change) {
  if (change.type === "row_added") {
    return Object.entries(publicRowValues(change.after || {})).map(([column, value]) => ({
      type: "cell_filled",
      column,
      row_id: change.row_id,
      excel_row: change.after?._excel_row || change.row_id,
      before: null,
      after: value,
      row_after: change.after,
    }));
  }
  if (change.type === "row_removed") {
    return Object.entries(publicRowValues(change.before || {})).map(([column, value]) => ({
      type: "cell_cleared",
      column,
      row_id: change.row_id,
      excel_row: change.before?._excel_row || change.row_id,
      before: value,
      after: null,
      row_before: change.before,
    }));
  }
  if (change.type === "cell_changed") {
    return [change];
  }
  return [{
    ...change,
    column: change.column || labelChange(change),
    before: change.type === "column_added" ? null : change.before,
    after: change.type === "column_removed" ? null : change.after || change.message || change.column,
  }];
}

function publicRowValues(row) {
  return Object.fromEntries(Object.entries(row).filter(([key]) => !key.startsWith("_")));
}

export function labelChange(change) {
  return {
    initial_snapshot: "Snapshot inicial",
    row_added: "Registro adicionado",
    row_removed: "Registro removido",
    column_added: "Coluna adicionada",
    column_removed: "Coluna removida",
    new_month: "Novo Mês",
  }[change.type] || change.type;
}
