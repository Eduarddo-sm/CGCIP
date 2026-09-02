import { api } from "../core/api.js";
import { $ } from "../core/dom.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { state } from "../core/state.js";
import { toast } from "../core/toast.js";
import { clearColchaoCache, selectedSheet, statuses, value } from "./colchaoCore.js";

let callbacks = {
  loadPage: async () => {},
};

window.addEventListener("beforeunload", (event) => {
  if (!Object.keys(state.colchao.pendingStatusChanges || {}).length) return;
  event.preventDefault();
  event.returnValue = "";
});

export function configureColchaoStatus(options = {}) {
  callbacks = { ...callbacks, ...options };
}

export function bindStatusButtons(selector) {
  bindStatusSelects(selector);
}

export function bindStatusSelects(selector) {
  document.querySelectorAll(`${selector} [data-colchao-select]`).forEach((select) => {
    select.addEventListener("change", () => updateStatus(select.dataset.colchaoSelect, select.value, select));
  });
}

export function bindBatchStatusSelects(selector) {
  const root = typeof selector === "string" ? document.querySelector(selector) : selector;
  if (!root || root.dataset.colchaoBatchDelegated === "true") return;
  root.dataset.colchaoBatchDelegated = "true";
  root.addEventListener("change", (event) => {
    const select = event.target.closest("[data-colchao-batch-select]");
    if (select && root.contains(select)) {
      stageStatusChange(select);
      return;
    }
    const dueDate = event.target.closest("[data-colchao-due-date]");
    if (dueDate && root.contains(dueDate)) stageDueDateChange(dueDate);
  });
}

export function renderStatusSelect(row, attrName) {
  const rowNumber = String(row.__row_number);
  const pending = state.colchao.pendingStatusChanges[rowNumber];
  const current = (pending?.status || value(row, "STATUS")).toUpperCase();
  const original = value(row, "STATUS").toUpperCase();
  return `
    <select class="status-select ${pending?.status ? "pending-change" : ""}" ${attrName}="${escapeAttr(row.__row_number)}" data-colchao-profile="${escapeAttr(row.__profile || state.colchao.profile || "alpha")}" data-colchao-sheet="${escapeAttr(row.__sheet_name || selectedSheet())}" data-previous-value="${escapeAttr(original)}" aria-label="Alterar status">
      ${statuses.map((status) => `<option value="${status}" ${current === status ? "selected" : ""}>${escapeHtml(status)}</option>`).join("")}
    </select>
  `;
}

export function renderDueDateInput(row, header) {
  const rowNumber = String(row.__row_number);
  const pending = state.colchao.pendingStatusChanges[rowNumber];
  const original = dateInputValue(row[header]);
  const current = pending?.vencimento || original;
  return `<input class="colchao-due-date-input ${pending?.vencimento ? "pending-change" : ""}"
    type="date" value="${escapeAttr(current)}" data-colchao-due-date="${escapeAttr(rowNumber)}"
    data-previous-value="${escapeAttr(original)}" aria-label="Alterar data de vencimento" />`;
}

export async function saveColchaoBatchStatus() {
  const changes = Object.values(state.colchao.pendingStatusChanges);
  if (!changes.length) return;
  const hasQuebra = changes.some((item) => item.status === "QUEBRA");
  let observacao = "";
  if (hasQuebra) {
    if (!confirm("Salvar QUEBRA aplicara a regra em todas as parcelas abertas do mesmo acordo. Continuar?")) return;
    observacao = prompt("Observação da quebra, se houver:", "") || "";
  }
  try {
    const result = await api("/api/colchao/status-batch", {
      method: "POST",
      body: JSON.stringify({
        profile: state.colchao.profile || "alpha",
        sheet: selectedSheet(),
        changes: changes.map((item) => ({ ...item, observacao: item.status === "QUEBRA" ? observacao : item.observacao || "" })),
      }),
    });
    state.colchao.pendingStatusChanges = {};
    clearColchaoCache();
    toast(`${result.changed?.length || changes.length} alteração(ões) salva(s)`);
    await callbacks.loadPage();
  } catch (error) {
    toast(error.message);
  }
}

export function updateBatchSaveButton() {
  const button = $("#colchaoSaveChangesBtn");
  if (!button) return;
  const total = Object.keys(state.colchao.pendingStatusChanges).length;
  button.disabled = total === 0;
  button.classList.toggle("hidden", total === 0);
  button.textContent = total ? `Salvar ${total} alteração(ões)` : "Salvar alterações";
  const stateLabel = $("#colchaoSheetState");
  if (stateLabel) {
    const activeFilters = [
      $("#colchaoFullSearch")?.value,
      $("#colchaoFilterOperador")?.value,
      $("#colchaoFilterStatus")?.value,
      $("#colchaoFilterVencimento")?.value,
    ].filter(Boolean).length;
    stateLabel.textContent = total
      ? `${total} alteração(ões) pendente(s)`
      : activeFilters ? `${activeFilters} filtro(s) ativo(s)` : "Sem alterações pendentes";
  }
}

function stageStatusChange(select) {
  const row = String(select.dataset.colchaoBatchSelect);
  const previous = select.dataset.previousValue || "";
  const pending = { ...(state.colchao.pendingStatusChanges[row] || {}), row: Number(row) };
  if (select.value === previous) {
    delete pending.status;
    delete pending.observacao;
  } else {
    pending.status = select.value;
    pending.observacao = "";
  }
  commitPendingRow(row, pending);
  select.classList.toggle("pending-change", Boolean(pending.status));
  updateBatchSaveButton();
}

function stageDueDateChange(input) {
  const row = String(input.dataset.colchaoDueDate);
  const previous = input.dataset.previousValue || "";
  if (!input.value) {
    input.value = previous;
    toast("Informe uma data de vencimento valida.");
    return;
  }
  const pending = { ...(state.colchao.pendingStatusChanges[row] || {}), row: Number(row) };
  if (input.value === previous) delete pending.vencimento;
  else pending.vencimento = input.value;
  commitPendingRow(row, pending);
  input.classList.toggle("pending-change", Boolean(pending.vencimento));
  updateBatchSaveButton();
}

function commitPendingRow(row, pending) {
  if (pending.status || pending.vencimento) state.colchao.pendingStatusChanges[row] = pending;
  else delete state.colchao.pendingStatusChanges[row];
}

function dateInputValue(value) {
  if (value instanceof Date && !Number.isNaN(value.getTime())) return value.toISOString().slice(0, 10);
  const text = String(value || "").trim().slice(0, 10);
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
  const match = text.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  return match ? `${match[3]}-${match[2]}-${match[1]}` : "";
}

async function updateStatus(row, status, control = null) {
  const previous = control?.dataset.previousValue || "";
  const observacao = status === "QUEBRA" ? prompt("Observação da quebra, se houver:", "") || "" : "";
  if (status === "QUEBRA" && !confirm("Marcar como QUEBRA todas as parcelas abertas deste acordo?")) {
    if (control) control.value = previous;
    return;
  }
  try {
    if (state.colchao.page === "pendencias") state.colchao.pendingScrollTop = window.scrollY;
    const result = await api("/api/colchao/status", {
      method: "POST",
      body: JSON.stringify({
        row,
        status,
        observacao,
        profile: control?.dataset.colchaoProfile || state.colchao.profile || "alpha",
        sheet: control?.dataset.colchaoSheet || selectedSheet(),
      }),
    });
    clearColchaoCache();
    toast(`${result.changed?.length || 1} parcela(s) atualizada(s)`);
    await callbacks.loadPage();
  } catch (error) {
    if (control) control.value = previous;
    toast(error.message);
  }
}
