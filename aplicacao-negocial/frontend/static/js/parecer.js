import { apiGet, apiPatch, apiPost, apiPut } from "./api.js?v=20260714-module-contract-1";
import { createExcelGrid } from "./excelGrid.js?v=20260730-inline-save-1";

const state = {
  initialized: false,
  items: [],
  grid: null,
  editingId: null,
  statusFilter: "TODOS",
};

const els = {};

const statusLabels = {
  PENDENTE: "Pendente",
  SOLICITADO: "Solicitado",
  CANCELADO: "Cancelado",
};

const motivoOptions = [
  { value: "PISO NEGOCIAL", label: "Piso negocial" },
  { value: "PARECER", label: "Parecer" },
  { value: "REUNIAO", label: "Reuniao" },
  { value: "EVENTO", label: "Evento" },
];

function qs(selector) {
  return document.querySelector(selector);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function digitsOnly(value, maxLength) {
  return String(value ?? "").replace(/\D/g, "").slice(0, maxLength);
}

function normalizeDigitField(input, maxLength) {
  input.value = digitsOnly(input.value, maxLength);
}

function formatDate(value) {
  if (!value) return "-";
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

function showError(message) {
  els.error.textContent = message;
  els.error.hidden = false;
}

function clearError() {
  els.error.hidden = true;
  els.error.textContent = "";
}

function filteredItems() {
  const search = els.search.value.trim().toLowerCase();
  const motivo = els.motivoFilter.value;
  const period = els.periodFilter.value;
  return state.items.filter((item) => {
    const haystack = `${item.npj} ${item.cliente} ${item.motivo} ${item.descricao} ${item.approval_reason || ""}`.toLowerCase();
    const matchesStatus = state.statusFilter === "TODOS" || item.status === state.statusFilter;
    const matchesSearch = !search || haystack.includes(search);
    const matchesMotivo = !motivo || item.motivo === motivo;
    const matchesPeriod = !period || String(item.data_solicitacao || "").slice(0, 7) === period;
    return matchesStatus && matchesSearch && matchesMotivo && matchesPeriod;
  });
}

function updateStateItem(updatedItem) {
  const index = state.items.findIndex((item) => item.id === updatedItem.id);
  if (index >= 0) {
    state.items[index] = updatedItem;
  }
}

function parecerPayload(item, field, value) {
  const payload = {
    npj: item.npj,
    cliente: item.cliente,
    motivo: item.motivo,
    descricao: item.descricao,
    [field]: value,
  };

  if (field === "npj") {
    payload.npj = digitsOnly(value, 14);
  }

  return payload;
}

async function saveParecerCell(item, field, value) {
  const payload = parecerPayload(item, field, value);
  const response = await apiPut(`/api/pareceres/${item.id}`, payload);
  updateStateItem(response.item);
  renderStats();
  return response.item;
}

async function saveParecerStatus(item, status) {
  const response = await apiPatch(`/api/pareceres/${item.id}/status`, { status });
  updateStateItem(response.item);
  render();
  return response.item;
}

function parecerColumns() {
  return [
    {
      id: "data_solicitacao",
      title: "Data",
      width: 112,
      display: (item) => formatDate(item.data_solicitacao),
    },
    {
      id: "npj",
      title: "NPJ",
      width: 148,
      save: (item, value) => saveParecerCell(item, "npj", value),
    },
    {
      id: "cliente",
      title: "Cliente",
      width: 260,
      save: (item, value) => saveParecerCell(item, "cliente", value),
    },
    {
      id: "motivo",
      title: "Motivo",
      width: 164,
      type: "select",
      options: motivoOptions,
      save: (item, value) => saveParecerCell(item, "motivo", value),
    },
    {
      id: "descricao",
      title: "Descricao",
      width: 360,
      save: (item, value) => saveParecerCell(item, "descricao", value),
    },
    {
      id: "status",
      title: "Status",
      width: 144,
      display: (item) => statusLabels[item.status] || item.status,
      render: (item) => `
        <span class="status-fill status-${String(item.status).toLowerCase()}">
          ${escapeHtml(statusLabels[item.status] || item.status)}
        </span>
      `,
    },
    {
      id: "approval_reason",
      title: "Justificativa",
      width: 320,
      display: (item) => item.approval_reason || "",
      render: (item) => escapeHtml(item.approval_reason || ""),
    },
    {
      id: "acoes",
      title: "Acoes",
      width: 92,
      type: "action",
      render: (item) => `
        <div class="row-actions">
          <button class="table-btn parecer-edit-btn" type="button" data-action="edit" data-id="${item.id}" title="Editar parecer" aria-label="Editar parecer">&#9998;</button>
        </div>
      `,
    },
  ];
}

function renderStats() {
  const countByStatus = (status) => state.items.filter((item) => item.status === status).length;
  const tabs = [
    ["TODOS", "Todos", state.items.length],
    ["PENDENTE", "Pendentes", countByStatus("PENDENTE")],
    ["SOLICITADO", "Solicitados", countByStatus("SOLICITADO")],
    ["CANCELADO", "Cancelados", countByStatus("CANCELADO")],
  ];
  els.stats.innerHTML = `
    ${tabs.map(([value, label, count]) => `
      <button
        class="parecer-status-tab ${state.statusFilter === value ? "active" : ""}"
        type="button"
        role="tab"
        aria-selected="${state.statusFilter === value}"
        data-parecer-status="${value}"
      ><span>${label}</span><strong>${count}</strong></button>
    `).join("")}
  `;
}

function renderList() {
  const items = filteredItems();
  if (!state.grid) {
    state.grid = createExcelGrid(els.list, {
      id: "parecerGrid",
      persistKey: "negocial:pareceres:principal",
      onError: (error) => showError(error.message || "Nao foi possivel salvar a celula."),
    });
  }
  state.grid.render(items, parecerColumns());
}

function render() {
  renderStats();
  renderList();
}

function openDialog(item = null) {
  state.editingId = item?.id || null;
  els.form.reset();
  clearError();
  els.title.textContent = item ? "Editar parecer" : "Novo parecer";
  els.cancelStatusBtn.hidden = !item || item.status !== "PENDENTE";
  els.cancelStatusBtn.disabled = !item || item.status !== "PENDENTE";
  els.cancelStatusBtn.textContent = "Cancelar parecer";

  if (item) {
    els.id.value = item.id;
    els.npj.value = item.npj;
    els.cliente.value = item.cliente;
    els.motivo.value = item.motivo;
    els.descricao.value = item.descricao;
  } else {
    els.id.value = "";
  }

  els.dialog.showModal();
}

function closeDialog() {
  els.dialog.close();
}

function payloadFromForm() {
  normalizeDigitField(els.npj, 14);
  return {
    npj: els.npj.value.trim(),
    cliente: els.cliente.value.trim(),
    motivo: els.motivo.value.trim(),
    descricao: els.descricao.value.trim(),
  };
}

function validateForm() {
  normalizeDigitField(els.npj, 14);
  if (els.npj.value.length !== 14) {
    els.npj.focus();
    showError("NPJ deve conter exatamente 14 digitos.");
    return false;
  }
  if (!els.cliente.value.trim() || !els.motivo.value.trim() || !els.descricao.value.trim()) {
    showError("Preencha cliente, motivo e descricao.");
    return false;
  }
  clearError();
  return true;
}

async function loadPareceres() {
  els.list.innerHTML = `
    <div class="excel-grid-loading">
      <div class="table-loading skeleton"></div>
      <div class="table-loading skeleton"></div>
      <div class="table-loading skeleton"></div>
    </div>
  `;
  const data = await apiGet("/api/pareceres");
  state.items = data.items || [];
  render();
}

async function saveParecer(event) {
  event.preventDefault();
  if (!validateForm() || !els.form.reportValidity()) return;

  els.saveBtn.disabled = true;
  els.saveBtn.textContent = "Salvando...";
  try {
    const payload = payloadFromForm();
    if (state.editingId) {
      await apiPut(`/api/pareceres/${state.editingId}`, payload);
    } else {
      await apiPost("/api/pareceres", payload);
    }
    await loadPareceres();
    closeDialog();
  } catch (error) {
    showError(error.message);
  } finally {
    els.saveBtn.disabled = false;
    els.saveBtn.textContent = "Salvar";
  }
}

async function handleListClick(event) {
  const button = event.target.closest("[data-action]");
  if (!button || button.tagName === "SELECT") return;

  const id = Number(button.dataset.id);
  const item = state.items.find((entry) => entry.id === id);
  if (!item) return;

  if (button.dataset.action === "edit") {
    openDialog(item);
    return;
  }

}

async function cancelEditingParecer() {
  if (!state.editingId) return;
  const item = state.items.find((entry) => entry.id === state.editingId);
  if (!item || item.status !== "PENDENTE") return;

  els.cancelStatusBtn.disabled = true;
  els.cancelStatusBtn.textContent = "Cancelando...";
  try {
    await saveParecerStatus(item, "CANCELADO");
    closeDialog();
  } catch (error) {
    showError(error.message || "Nao foi possivel cancelar o parecer.");
    els.cancelStatusBtn.disabled = false;
    els.cancelStatusBtn.textContent = "Cancelar parecer";
  }
}

export function initPareceres() {
  if (state.initialized) return;
  state.initialized = true;

  Object.assign(els, {
    dialog: qs("#parecerDialog"),
    form: qs("#parecerForm"),
    title: qs("#parecerDialogTitle"),
    id: qs("#parecerId"),
    npj: qs("#parecerNpj"),
    cliente: qs("#parecerCliente"),
    motivo: qs("#parecerMotivo"),
    descricao: qs("#parecerDescricao"),
    error: qs("#parecerError"),
    saveBtn: qs("#saveParecerBtn"),
    cancelStatusBtn: qs("#cancelParecerStatusBtn"),
    closeBtn: qs("#closeParecerDialogBtn"),
    cancelBtn: qs("#cancelParecerBtn"),
    openBtn: qs("#openParecerDialogBtn"),
    stats: qs("#parecerStats"),
    list: qs("#parecerList"),
    search: qs("#parecerSearch"),
    motivoFilter: qs("#parecerMotivoFilter"),
    periodFilter: qs("#parecerPeriodFilter"),
  });

  els.openBtn.addEventListener("click", () => openDialog());
  els.closeBtn.addEventListener("click", closeDialog);
  els.cancelBtn.addEventListener("click", closeDialog);
  els.cancelStatusBtn.addEventListener("click", cancelEditingParecer);
  els.form.addEventListener("submit", saveParecer);
  els.npj.addEventListener("input", () => normalizeDigitField(els.npj, 14));
  els.list.addEventListener("click", handleListClick);
  els.search.addEventListener("input", renderList);
  els.motivoFilter.addEventListener("change", renderList);
  els.periodFilter.addEventListener("change", renderList);
  els.stats.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-parecer-status]");
    if (!tab) return;
    state.statusFilter = tab.dataset.parecerStatus;
    renderStats();
    renderList();
  });
}

export { loadPareceres };
