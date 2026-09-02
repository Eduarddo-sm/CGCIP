import { api } from "../core/api.js";
import { formatValue } from "../core/format.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { state } from "../core/state.js";
import { bindNotesButtons, notesButton } from "./notes.js";
import { protocoloStatus } from "./protocoloData.js";
import {
  headersFromRows,
  isGridDateHeader,
  isGridMoneyHeader,
  mountOperationalExcelGrid,
  normalizeGridHeader,
  operationalColumnWidth,
} from "./operationalExcelGrid.js?v=20260717-unfreeze-last-1";

const STATUS_OPTIONS = [
  { value: "PENDENTE", label: "Pendente" },
  { value: "CONCLUIDO", label: "Concluido" },
];

const PREFERRED_HEADERS = [
  "DATA", "CARTEIRA", "NOME", "PJ", "PROCESSO", "DATA DE SOLICITACAO",
  "STATUS", "DATA DE CONCLUSAO",
];

function orderedHeaders(rows) {
  const rank = new Map(PREFERRED_HEADERS.map((header, index) => [normalizeGridHeader(header), index]));
  return headersFromRows(rows)
    .filter((header) => !normalizeGridHeader(header).includes("OBSERV"))
    .map((header, index) => ({ header, index, rank: rank.get(normalizeGridHeader(header)) ?? Number.MAX_SAFE_INTEGER }))
    .sort((left, right) => left.rank - right.rank || left.index - right.index)
    .map(({ header }) => header);
}

let protocoloGrid = null;
let statusCallback = async () => false;

function isStatusHeader(header) {
  return normalizeGridHeader(header) === "STATUS";
}

function protocolDisplayValue(header, value) {
  if (normalizeGridHeader(header) !== "PROCESSO") return formatValue(value);
  const raw = String(value ?? "").trim();
  const match = raw.match(/^([+-]?)(\d+)(?:\.(\d+))?[eE]([+-]?\d+)$/);
  if (!match) return formatValue(value);
  const sign = match[1];
  const digits = `${match[2]}${match[3] || ""}`;
  const decimal = match[2].length + Number(match[4]);
  if (decimal <= 0) return `${sign}0.${"0".repeat(-decimal)}${digits}`;
  if (decimal >= digits.length) return `${sign}${digits}${"0".repeat(decimal - digits.length)}`;
  return `${sign}${digits.slice(0, decimal)}.${digits.slice(decimal)}`;
}

function statusControl(row) {
  const current = protocoloStatus(row);
  return `
    <select class="status-fill status-fill-select status-${escapeAttr(current.toLowerCase())}" data-protocolo-excel-status="${escapeAttr(row.__row_number)}">
      ${STATUS_OPTIONS.map((item) => `<option value="${item.value}" ${item.value === current ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("")}
    </select>
  `;
}

async function saveCell(row, header, value) {
  await api("/api/protocolo/cell", {
    method: "POST",
    body: JSON.stringify({ row: row.__row_number, header, value }),
  });
  row[header] = value;
  const record = state.protocolo.records.find((item) => String(item.__row_number) === String(row.__row_number));
  if (record) record[header] = value;
  return row;
}

function bindActions(container) {
  if (!container || container.dataset.protocoloExcelActions === "true") return;
  container.dataset.protocoloExcelActions = "true";
  container.addEventListener("change", async (event) => {
    const select = event.target.closest("[data-protocolo-excel-status]");
    if (!select) return;
    select.disabled = true;
    const ok = await statusCallback(select.dataset.protocoloExcelStatus, select.value, select);
    if (!ok) select.disabled = false;
  });
}

export function renderProtocoloExcelGrid(rows = [], options = {}) {
  statusCallback = options.onStatusChange || statusCallback;
  const headers = orderedHeaders(rows);
  if (!headers.length) return null;
  const hasStatus = headers.some(isStatusHeader);
  const columns = headers.map((header) => {
    const status = isStatusHeader(header);
    return {
      id: header,
      title: header,
      width: status ? 176 : operationalColumnWidth(header),
      type: status ? "select" : isGridDateHeader(header) ? "date" : undefined,
      options: status ? STATUS_OPTIONS : undefined,
      value: (row) => status ? protocoloStatus(row) : row[header] ?? "",
      display: (row) => status ? protocoloStatus(row) : protocolDisplayValue(header, row[header]),
      render: status ? statusControl : undefined,
      save: status ? undefined : (row, value) => saveCell(row, header, value),
      cellClass: isGridMoneyHeader(header) ? "excel-cell-money" : "",
    };
  });
  if (!hasStatus) {
    columns.push({
      id: "STATUS",
      title: "Status",
      width: 176,
      type: "select",
      options: STATUS_OPTIONS,
      value: protocoloStatus,
      display: protocoloStatus,
      render: statusControl,
    });
  }
  columns.push({
    id: "__protocolo_observacoes",
    title: "Observacoes",
    width: 116,
    type: "action",
    render: (row) => notesButton("protocolo", row.__row_number, "Obs."),
  });
  protocoloGrid = mountOperationalExcelGrid("#protocoloClosedGrid", {
    id: "protocolo-concluidos-excel",
    persistKey: "gerencial:protocolos:planilha:v2",
    rows,
    columns,
  });
  const container = document.querySelector("#protocoloClosedGrid");
  bindActions(container);
  bindNotesButtons(container);
  return protocoloGrid;
}
