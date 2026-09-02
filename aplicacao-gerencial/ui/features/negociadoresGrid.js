import { $ } from "../core/dom.js";
import { escapeHtml } from "../core/html.js";
import { state } from "../core/state.js";
import { filterRowsBySearch } from "./searchIndex.js";
import { formatSheetValue } from "./sheetFormat.js";
import { periodRows } from "./negociadorPeriod.js?v=20260728-next-month-fix-1";
import {
  isGridDateHeader,
  isGridMoneyHeader,
  mountOperationalExcelGrid,
  normalizeGridHeader,
  operationalColumnWidth,
} from "./operationalExcelGrid.js?v=20260717-unfreeze-last-1";

let negociadorGrid = null;

export function renderFilters() {
  const filterBar = $("#filterBar");
  if (!filterBar) return;
  filterBar.innerHTML = "";
  filterBar.classList.add("hidden");
}

export function renderGrid() {
  if (!state.data) return;
  const headers = (state.data.headers || []).filter((header) => header && !String(header).startsWith("_"));
  const search = $("#quickSearch")?.value.trim().toLowerCase() || "";
  const rows = filterRowsBySearch(
    periodRows(state.data, state.negociadorProfile),
    headers,
    search,
    (value, header) => formatSheetValue(header, value),
  );

  $("#openNegotiatorSpreadsheetBtn")?.classList.toggle(
    "hidden",
    state.negociadores.find((item) => item.id === state.activeId)?.source_type === "sistema",
  );

  const columns = headers.map((header) => ({
    id: header,
    title: header,
    width: operationalColumnWidth(header),
    type: isGridDateHeader(header) ? "date" : undefined,
    editable: false,
    value: (row) => row[header] ?? "",
    display: (row) => formatSheetValue(header, row[header]),
    render: isStatusHeader(header)
      ? (row) => renderStatus(formatSheetValue(header, row[header]))
      : undefined,
    cellClass: isGridMoneyHeader(header) ? "excel-cell-money" : "",
  }));

  negociadorGrid = mountOperationalExcelGrid("#grid", {
    id: "negociador-profile-excel",
    persistKey: `gerencial:negociador:${state.activeId || "perfil"}:planilha`,
    rows,
    columns,
    preservePosition: true,
  });
  $("#grid")?.classList.add("negociador-sheet-grid", "operational-grid-host");
  return negociadorGrid;
}

function isStatusHeader(header) {
  const key = normalizeGridHeader(header);
  return key === "STATUS" || key === "SITUACAO";
}

function renderStatus(value) {
  const key = normalizeGridHeader(value);
  const tone = key.includes("PAGAMENTO_REALIZADO") || key === "PAGO"
    ? "paid"
    : key.includes("AGUARDANDO")
      ? "waiting"
      : key.includes("NEGADA") || key.includes("QUEBRA")
        ? "negative"
        : "proposal";
  return `<span class="negociador-grid-status ${tone}">${escapeHtml(value)}</span>`;
}
