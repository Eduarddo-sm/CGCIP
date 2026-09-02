import { escapeAttr, escapeHtml } from "../core/html.js";
import { toast } from "../core/toast.js";
import { createExcelGrid } from "./excelGrid.js?v=20260826-edit-tab-1";
import {
  DATE_FILTER_HEADERS,
  MONEY_FILTER_HEADERS,
  NON_EDITABLE_HEADERS,
  NUMBER_FILTER_HEADERS,
  TABLE_HEADERS,
} from "./monitorPlanilhaConstants.js?v=20260713-gerencial-edit-all-1";
import { displayCellValue } from "./monitorPlanilhaFormat.js?v=20260717-css-cleanup-2";

const STATUS_LABELS = {
  PROPOSTA: "Proposta",
  AGUARDANDO_PAGAMENTO: "Aguardando pagamento",
  PAGAMENTO_REALIZADO: "Pagamento realizado",
  PROPOSTA_NEGADA: "Proposta negada",
  OPERACAO_RECOMPRADA: "Operação recomprada",
  QUEBRA: "Quebra",
};

let mainGrid = null;
let expandedGrid = null;
const gridContexts = new WeakMap();
let rowActionPopover = null;
let rowActionTarget = null;

function rowId(row) {
  return Number(row?._row_id || row?.id || row?.__row_number || 0);
}

function normalizeKey(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toUpperCase();
}

function statusValue(row) {
  return normalizeKey(row?.STATUS || row?.status || "PROPOSTA");
}

function statusOptions(rows) {
  const values = new Set([...Object.keys(STATUS_LABELS), ...rows.map(statusValue).filter(Boolean)]);
  return [...values].map((value) => ({ value, label: STATUS_LABELS[value] || String(value).replaceAll("_", " ") }));
}

function statusSelect(row, header) {
  const value = statusValue(row);
  const client = row.CLIENTE || row.NOME || "cliente";
  return `
    <select
      class="status-fill status-fill-select status-${escapeAttr(value.toLowerCase())}"
      data-monitor-excel-status="${escapeAttr(rowId(row))}"
      data-monitor-excel-header="${escapeAttr(header)}"
      aria-label="Status de ${escapeAttr(client)}"
    >
      ${Object.entries(STATUS_LABELS).map(([optionValue, label]) => `
        <option value="${escapeAttr(optionValue)}" ${optionValue === value ? "selected" : ""}>${escapeHtml(label)}</option>
      `).join("")}
    </select>
  `;
}

function headerWidth(header) {
  const key = normalizeKey(header);
  if (["CLIENTE", "NOME", "NOME_CLIENTE", "DESCRICAO", "JUSTIFICATIVA"].includes(key)) return 260;
  if (["STATUS", "SITUACAO"].includes(key)) return 190;
  if (DATE_FILTER_HEADERS.has(header)) return 136;
  if (MONEY_FILTER_HEADERS.has(header)) return 154;
  if (key.includes("NEGOCIADOR") || key.includes("OPERADOR") || key.includes("USUARIO")) return 170;
  if (key.includes("NPJ") || key.includes("SUITID") || key.includes("DEBIT") || key.includes("CPF")) return 166;
  return 148;
}

function headersFor(payload, rows) {
  const base = (payload?.headers?.length ? payload.headers : TABLE_HEADERS)
    .filter((header) => header && !String(header).startsWith("_"));
  if (String(payload?.carteira || "").toUpperCase() === "GAMMA") return base;
  const extras = ["ULTIMA ATUALIZACAO"].filter((header) => rows.some((row) => row[header] !== undefined && row[header] !== ""));
  return [...new Set([...base, ...extras])];
}

async function saveCell(context, row, header, value) {
  const result = await context.onSave?.({
    header,
    rowKey: rowId(row),
    value,
  });
  row[header] = result?.value ?? value;
  return row;
}

function columnsFor(payload, rows, context) {
  const closed = Boolean(payload?.fechamento?.closed);
  const statuses = statusOptions(rows);
  const columns = headersFor(payload, rows).map((header) => {
    const key = normalizeKey(header);
    const isStatus = key === "STATUS" || key === "SITUACAO";
    const editable = !closed && !NON_EDITABLE_HEADERS.has(header);
    return {
      id: header,
      title: header,
      width: headerWidth(header),
      type: isStatus ? "select" : DATE_FILTER_HEADERS.has(header) ? "date" : undefined,
      options: isStatus ? statuses : undefined,
      value: (row) => isStatus ? statusValue(row) : row[header] ?? "",
      display: (row) => isStatus ? (STATUS_LABELS[statusValue(row)] || row[header] || "") : displayCellValue(header, row[header]),
      render: isStatus ? (row) => statusSelect(row, header) : undefined,
      save: editable ? (row, value) => saveCell(context, row, header, value) : undefined,
      cellClass: MONEY_FILTER_HEADERS.has(header)
        ? "excel-cell-money"
        : NUMBER_FILTER_HEADERS.has(header)
          ? "excel-cell-number"
          : "",
    };
  });
  if (context.onDelete) {
    columns.push({
      id: "acoes",
      title: "Acoes",
      width: 64,
      type: "action",
      editable: false,
      render: (row) => `
        <div class="row-actions">
          <button
            class="monitor-row-menu-btn"
            type="button"
            data-monitor-excel-menu="${escapeAttr(rowId(row))}"
            data-monitor-excel-client="${escapeAttr(row.CLIENTE || row.NOME || "")}"
            aria-label="Ações da linha"
            title="Ações"
            ${rowId(row) > 0 ? "" : "disabled"}
          >•••</button>
        </div>
      `,
    });
  }
  return columns;
}

function bindGridActions(container) {
  if (!container || container.dataset.monitorExcelActions === "true") return;
  container.dataset.monitorExcelActions = "true";
  container.addEventListener("click", (event) => {
    const button = event.target.closest("[data-monitor-excel-menu]");
    if (!button) return;
    event.stopPropagation();
    openRowActionPopover(button, container);
  });
  container.addEventListener("change", async (event) => {
    const select = event.target.closest("[data-monitor-excel-status]");
    if (!select) return;
    const context = gridContexts.get(container);
    const id = Number(select.dataset.monitorExcelStatus || 0);
    const row = context?.grid?.instance?.sourceRows?.find((item) => rowId(item) === id);
    if (!context || !row) return;
    const previousStatus = statusValue(row);
    select.disabled = true;
    try {
      await saveCell(context, row, select.dataset.monitorExcelHeader || "STATUS", select.value);
      const nextStatus = statusValue(row);
      select.className = `status-fill status-fill-select status-${nextStatus.toLowerCase()}`;
    } catch (error) {
      select.value = previousStatus;
      toast(error.message || "Nao foi possivel atualizar o status.");
    } finally {
      select.disabled = false;
    }
  });
}

function ensureRowActionPopover() {
  if (rowActionPopover) return rowActionPopover;
  rowActionPopover = document.createElement("div");
  rowActionPopover.className = "monitor-row-actions-popover hidden";
  rowActionPopover.innerHTML = `
    <button type="button" data-monitor-row-action="edit">Editar linha</button>
    <button type="button" class="danger" data-monitor-row-action="delete">Excluir</button>
  `;
  document.body.appendChild(rowActionPopover);
  rowActionPopover.addEventListener("click", (event) => {
    const action = event.target.closest("[data-monitor-row-action]")?.dataset.monitorRowAction;
    if (!action || !rowActionTarget) return;
    const { button, container } = rowActionTarget;
    const context = gridContexts.get(container);
    if (action === "edit") {
      const editableCell = button.closest("tr")?.querySelector("td.excel-cell.editable:not(.action-cell)");
      closeRowActionPopover();
      editableCell?.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
      return;
    }
    const id = Number(button.dataset.monitorExcelMenu || 0);
    const cliente = button.dataset.monitorExcelClient || "";
    closeRowActionPopover();
    context?.onDelete?.({ id, cliente });
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".monitor-row-actions-popover, [data-monitor-excel-menu]")) closeRowActionPopover();
  });
  window.addEventListener("resize", closeRowActionPopover);
  return rowActionPopover;
}

function openRowActionPopover(button, container) {
  const popover = ensureRowActionPopover();
  if (rowActionTarget?.button === button && !popover.classList.contains("hidden")) {
    closeRowActionPopover();
    return;
  }
  rowActionTarget = { button, container };
  popover.classList.remove("hidden");
  const rect = button.getBoundingClientRect();
  const width = popover.offsetWidth;
  const height = popover.offsetHeight;
  popover.style.left = `${Math.max(8, Math.min(window.innerWidth - width - 8, rect.right - width))}px`;
  popover.style.top = `${Math.max(8, Math.min(window.innerHeight - height - 8, rect.bottom + 4))}px`;
}

function closeRowActionPopover() {
  rowActionPopover?.classList.add("hidden");
  rowActionTarget = null;
}

function renderGrid(container, payload, options = {}) {
  const rows = [...(payload?.rows || [])];
  const scope = options.scope || "principal";
  const context = {
    onSave: options.onSave,
    onDelete: options.onDelete,
    grid: null,
  };
  const grid = createExcelGrid(container, {
    id: `monitor-planilha-${scope}`,
    persistKey: `gerencial:monitoramento:${scope}:${String(payload?.carteira || "geral").toLowerCase()}`,
    filters: true,
    virtualThreshold: 350,
    toolbar: true,
    onSelectionChange: options.onSelectionChange,
    onError: (error) => toast(error.message || "Nao foi possivel salvar a celula."),
  });
  context.grid = grid;
  gridContexts.set(typeof container === "string" ? document.querySelector(container) : container, context);
  const columns = columnsFor(payload, rows, context);
  grid.render(rows, columns, { preservePosition: true });
  const element = typeof container === "string" ? document.querySelector(container) : container;
  element?.classList.add("monitor-native-excel");
  bindGridActions(element);
  return grid;
}

export function renderMonitorPlanilhaExcel(payload, options = {}) {
  mainGrid = renderGrid("#monitorPlanilhaTable", payload, { ...options, scope: "principal" });
  return mainGrid;
}

export function renderMonitorPlanilhaExpandedExcel(payload, options = {}) {
  expandedGrid = renderGrid("#monitorPlanilhaExpandedTable", payload, { ...options, scope: "expandida" });
  if (mainGrid) expandedGrid.applyViewState(mainGrid.getViewState());
  return expandedGrid;
}

export function clearMonitorPlanilhaExcelFilters(expanded = false) {
  (expanded ? expandedGrid : mainGrid)?.clearFilters();
}

export function renderMonitorPlanilhaExcelEmpty(message) {
  const target = document.querySelector("#monitorPlanilhaTable");
  if (!target) return;
  target.classList.remove("monitor-native-excel", "excel-grid");
  target.innerHTML = `<div class="empty-overview">${escapeHtml(message)}</div>`;
}
