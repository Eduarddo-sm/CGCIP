import { escapeAttr, escapeHtml } from "../core/html.js";
import { state } from "../core/state.js";
import { bindNotesButtons, notesButton } from "./notes.js";
import { formatSheetValue } from "./sheetFormat.js";
import { bindBatchStatusSelects, renderDueDateInput, renderStatusSelect } from "./colchaoStatus.js?v=20260814-due-date-1";
import {
  isGridDateHeader,
  isGridMoneyHeader,
  mountOperationalExcelGrid,
  normalizeGridHeader,
  operationalColumnWidth,
} from "./operationalExcelGrid.js?v=20260717-unfreeze-last-1";

let mainGrid = null;
let expandedGrid = null;

function isStatusHeader(header) {
  return normalizeGridHeader(header) === "STATUS";
}

function isDueDateHeader(header) {
  const key = normalizeGridHeader(header);
  return key === "DATA_DO_VENCIMENTO" || key === "VENCIMENTO" || key === "MES";
}

function isObservationHeader(header) {
  const key = normalizeGridHeader(header);
  return key === "OBS" || key === "OBSERVACAO" || key === "OBSERVACOES";
}

function observationValue(row) {
  const key = Object.keys(row || {}).find((header) => isObservationHeader(header) && String(row[header] ?? "").trim());
  return key ? String(row[key] ?? "").trim() : "";
}

function columnsFor(rows, headers) {
  const hasStatus = headers.some(isStatusHeader);
  const columns = headers.filter((header) => !isObservationHeader(header)).map((header) => {
    const status = isStatusHeader(header);
    const dueDate = isDueDateHeader(header);
    return {
      id: header,
      title: header,
      width: status ? 176 : operationalColumnWidth(header),
      type: status ? "select" : isGridDateHeader(header) ? "date" : undefined,
      value: (row) => status ? String(row[header] || "").toUpperCase() : row[header] ?? "",
      display: (row) => formatSheetValue(header, row[header]),
      render: status
        ? (row) => renderStatusSelect(row, "data-colchao-batch-select")
        : dueDate ? (row) => renderDueDateInput(row, header) : undefined,
      cellClass: isGridMoneyHeader(header) ? "excel-cell-money" : "",
    };
  });
  if (!hasStatus) {
    columns.push({
      id: "STATUS",
      title: "Status",
      width: 176,
      type: "select",
      value: (row) => String(row.STATUS || "").toUpperCase(),
      display: (row) => String(row.STATUS || "").toUpperCase(),
      render: (row) => renderStatusSelect(row, "data-colchao-batch-select"),
    });
  }
  columns.push({
    id: "__colchao_observacoes",
    title: "Observações",
    width: 250,
    type: "action",
    render: (row) => {
      const observation = observationValue(row);
      return `
        <div class="colchao-observation-action" title="${escapeAttr(observation || "Sem observação registrada")}">
          <span>${escapeHtml(observation || "Sem observação")}</span>
          ${notesButton("colchao", row.__row_number, "Obs.")}
        </div>
      `;
    },
  });
  return columns;
}

function bindGrid(container) {
  if (!container) return;
  bindBatchStatusSelects(container);
  bindNotesButtons(container);
  container.setAttribute("aria-label", `Planilha do colchao ${escapeAttr(state.colchao.profile || "")}`);
}

export function renderColchaoExcelGrid(rows = [], headers = []) {
  mainGrid = mountOperationalExcelGrid("#colchaoCompletoGrid", {
    id: "colchao-completo-excel",
    persistKey: `gerencial:colchao:${state.colchao.profile || "geral"}:planilha`,
    rows,
    columns: columnsFor(rows, headers),
  });
  bindGrid(document.querySelector("#colchaoCompletoGrid"));
  return mainGrid;
}

export function renderColchaoExpandedExcelGrid(rows = [], headers = []) {
  expandedGrid = mountOperationalExcelGrid("#colchaoExpandedTable", {
    id: "colchao-expandido-excel",
    persistKey: `gerencial:colchao:${state.colchao.profile || "geral"}:expandida`,
    rows,
    columns: columnsFor(rows, headers),
    virtualThreshold: 300,
  });
  if (mainGrid) expandedGrid.applyViewState(mainGrid.getViewState());
  bindGrid(document.querySelector("#colchaoExpandedTable"));
  return expandedGrid;
}
