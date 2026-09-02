import { api } from "../core/api.js";
import { $ } from "../core/dom.js";
import { formatValue } from "../core/format.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { state } from "../core/state.js";
import { protocoloStatus, protocoloValue } from "./protocoloData.js";
import { renderProtocoloExcelGrid } from "./protocoloExcelGrid.js?v=20260717-unfreeze-last-1";
import { bindNotesButtons, notesButton } from "./notes.js";

const callbacks = {
  updateStatus: async () => false,
};

const SOLICITACAO_HEADERS = ["DATA DE SOLICITAÇÃO", "DATA DE SOLICITACAO", "DATA DE SOLICITAÃ‡ÃƒO"];
const OBSERVACAO_HEADERS = ["OBSERVAÇÃO", "OBSERVACAO", "OBSERVAÃ‡ÃƒO"];
const collapsedProtocolWallets = new Set();

export function configureProtocoloView(options = {}) {
  Object.assign(callbacks, options);
}

export function renderProtocoloPage() {
  const records = state.protocolo.records || [];
  if (state.protocolo.page === "monitoramento") {
    const pendingRows = records.filter((row) => protocoloStatus(row) === "PENDENTE");
    syncOpenCarteiraFilter(pendingRows);
    if (state.protocolo.pendingCarteiraFilter !== undefined) {
      $("#protocoloCarteiraOpen").value = state.protocolo.pendingCarteiraFilter;
      delete state.protocolo.pendingCarteiraFilter;
    }
    const rows = filterPendingProtocoloRows(pendingRows);
    renderProtocoloCards(rows);
  }
  if (state.protocolo.page === "concluidos") {
    const rows = records;
    renderProtocoloTable(rows, "#protocoloClosedGrid");
  }
}

function filterPendingProtocoloRows(rows) {
  const carteira = $("#protocoloCarteiraOpen").value.trim().toLowerCase();
  const search = $("#protocoloSearchOpen")?.value.trim().toLowerCase() || "";
  return rows.filter((row) => {
    const values = Object.values(row).map((value) => String(value ?? "").toLowerCase());
    return (!search || values.some((value) => value.includes(search)))
      && (!carteira || String(protocoloValue(row, ["CARTEIRA"])).trim().toLowerCase() === carteira);
  });
}

function syncOpenCarteiraFilter(rows) {
  const select = $("#protocoloCarteiraOpen");
  if (!select) return;
  const current = select.value;
  const carteiras = [...new Set(rows
    .map((row) => String(protocoloValue(row, ["CARTEIRA"]) || "").trim())
    .filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, "pt-BR"));
  select.innerHTML = `<option value="">Todas as carteiras</option>${carteiras.map((carteira) => `<option value="${escapeAttr(carteira.toLowerCase())}">${escapeHtml(carteira)}</option>`).join("")}`;
  if ([...select.options].some((option) => option.value === current)) select.value = current;
}

function renderProtocoloCards(rows) {
  const grid = $("#protocoloOpenGrid");
  const sortedRows = sortPendingRows(rows);
  renderPendingSummary(sortedRows);
  if (!rows.length) {
    grid.innerHTML = `
      <div class="protocolo-empty-state ds-card">
        <span aria-hidden="true">${protocoloCardIcon("file-search")}</span>
        <strong>Nenhum protocolo pendente encontrado.</strong>
        <p>Nao ha protocolos aguardando conclusao no momento.</p>
      </div>
    `;
    return;
  }
  grid.innerHTML = groupProtocoloRowsByCarteira(sortedRows).map((group) => {
    const groupKey = group.carteira.toLocaleLowerCase("pt-BR");
    const collapsed = collapsedProtocolWallets.has(groupKey);
    return `
    <section class="protocolo-carteira-group protocolo-queue-group">
      <button class="protocolo-queue-group-head" type="button" data-protocolo-group-toggle="${escapeAttr(groupKey)}" aria-expanded="${String(!collapsed)}">
        <span class="protocolo-queue-chevron" aria-hidden="true">${collapsed ? "›" : "⌄"}</span>
        <strong>${escapeHtml(group.carteira)}</strong>
        <span>${group.rows.length} pendente${group.rows.length === 1 ? "" : "s"}</span>
      </button>
      <div class="protocolo-task-list${collapsed ? " hidden" : ""}">
        ${group.rows.map(renderCompactProtocoloCard).join("")}
      </div>
    </section>
  `;
  }).join("");
  grid.querySelectorAll("[data-protocolo-group-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.protocoloGroupToggle;
      if (collapsedProtocolWallets.has(key)) collapsedProtocolWallets.delete(key);
      else collapsedProtocolWallets.add(key);
      renderProtocoloPage();
    });
  });
  grid.querySelectorAll("[data-protocolo-expand]").forEach((button) => {
    button.addEventListener("click", () => {
      const row = button.closest(".protocolo-queue-row");
      const details = row?.querySelector(".protocolo-queue-details");
      if (!details) return;
      const expanded = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", String(!expanded));
      details.classList.toggle("hidden", expanded);
      row.classList.toggle("is-expanded", !expanded);
    });
  });
  grid.querySelectorAll("[data-pending-select-value]").forEach((value) => {
    value.addEventListener("click", (event) => event.stopPropagation());
  });
  grid.querySelectorAll("[data-protocolo-conclude]").forEach((button) => {
    button.addEventListener("click", () => callbacks.updateStatus(button.dataset.protocoloConclude, "CONCLUIDO", button));
  });
  bindNotesButtons(grid);
  const targetRow = String(state.protocolo.pendingTargetRow || "");
  if (targetRow) {
    const target = grid.querySelector(`[data-protocolo-row="${CSS.escape(targetRow)}"]`);
    target?.scrollIntoView({ block: "center", behavior: "smooth" });
    target?.classList.add("is-highlighted");
    delete state.protocolo.pendingTargetRow;
  }
}

function groupProtocoloRowsByCarteira(rows) {
  const groups = new Map();
  rows.forEach((row) => {
    const carteira = String(protocoloValue(row, ["CARTEIRA"]) || "Carteira nao informada").trim() || "Carteira nao informada";
    if (!groups.has(carteira)) groups.set(carteira, []);
    groups.get(carteira).push(row);
  });
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b, "pt-BR"))
    .map(([carteira, groupRows]) => ({ carteira, rows: groupRows }));
}

function renderCompactProtocoloCard(row) {
  const observation = String(protocoloValue(row, OBSERVACAO_HEADERS) || "").trim();
  const age = protocolAgeDays(row);
  const ageLabel = age === 0 ? "Hoje" : `${age} dia${age === 1 ? "" : "s"}`;
  const urgency = age > 7 ? "critical" : age >= 3 ? "warning" : "normal";
  const wallet = formatValue(protocoloValue(row, ["CARTEIRA"]));
  const clientName = formatValue(protocoloValue(row, ["NOME"]));
  const pj = formatValue(protocoloValue(row, ["PJ"]));
  return `
    <article class="protocolo-queue-row urgency-${urgency}" data-protocolo-row="${escapeAttr(row.__row_number)}">
      <button class="protocolo-queue-main" type="button" data-protocolo-expand="${escapeAttr(row.__row_number)}" aria-expanded="false">
        <span class="protocolo-queue-age">${escapeHtml(ageLabel)}</span>
        <span class="protocolo-queue-identity">
          <strong class="pending-copyable-value" data-pending-select-value="${escapeAttr(clientName)}" title="Selecione o nome para copiar">${escapeHtml(clientName)}</strong>
          <small>PJ <span class="pending-copyable-value" data-pending-select-value="${escapeAttr(pj)}" title="Selecione o PJ para copiar">${escapeHtml(pj)}</span> <i>·</i> Processo ${escapeHtml(formatValue(protocoloValue(row, ["PROCESSO"])))}</small>
        </span>
        <span class="protocolo-queue-requested"><small>Solicitado</small><b>${escapeHtml(formatValue(protocoloValue(row, SOLICITACAO_HEADERS)))}</b></span>
        <span class="protocolo-queue-wallet">${escapeHtml(wallet)}</span>
        <span class="protocolo-queue-expand" aria-hidden="true">⌄</span>
      </button>
      <div class="protocolo-queue-actions">
        ${notesButton("protocolo", row.__row_number, "Obs.")}
        <button class="secondary-btn ds-button protocolo-conclude-btn" type="button" data-protocolo-conclude="${escapeAttr(row.__row_number)}">
          ${protocoloCardIcon("check")} Concluído
        </button>
      </div>
      <div class="protocolo-queue-details hidden">
        <strong>Observação</strong>
        <p>${escapeHtml(observation ? formatValue(observation) : "Sem observação cadastrada.")}</p>
      </div>
    </article>
  `;
}

function sortPendingRows(rows) {
  const mode = $("#protocoloSortOpen")?.value || "oldest";
  return [...rows].sort((a, b) => {
    if (mode === "name") {
      return String(protocoloValue(a, ["NOME"]) || "").localeCompare(String(protocoloValue(b, ["NOME"]) || ""), "pt-BR");
    }
    const delta = protocolDate(a).getTime() - protocolDate(b).getTime();
    return mode === "newest" ? -delta : delta;
  });
}

function renderPendingSummary(rows) {
  const summary = $("#protocoloPendingSummary");
  if (!summary) return;
  const ages = rows.map(protocolAgeDays);
  const overdue = ages.filter((age) => age > 7).length;
  const oldest = ages.length ? Math.max(...ages) : 0;
  summary.innerHTML = `
    <span><b>${rows.length}</b> pendentes</span>
    <span class="is-critical"><b>${overdue}</b> acima de 7 dias</span>
    <span><b>${oldest}</b> dia${oldest === 1 ? "" : "s"} mais antigo</span>
  `;
}

function protocolDate(row) {
  const raw = String(protocoloValue(row, SOLICITACAO_HEADERS) || "").trim();
  let match = raw.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (match) return new Date(Number(match[3]), Number(match[2]) - 1, Number(match[1]));
  match = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (match) return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return new Date(8640000000000000);
}

function protocolAgeDays(row) {
  const requested = protocolDate(row);
  if (!Number.isFinite(requested.getTime())) return 0;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.max(0, Math.floor((today.getTime() - requested.getTime()) / 86400000));
}

function renderProtocoloTable(rows, target) {
  const count = $("#protocoloSheetCount");
  if (count) count.textContent = `${rows.length.toLocaleString("pt-BR")} registro${rows.length === 1 ? "" : "s"}`;
  const updatedAt = $("#protocoloSheetUpdatedAt");
  if (updatedAt) updatedAt.textContent = `Atualizado ${new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" }).format(new Date())}`;
  if (!rows.length) {
    $(target).classList.remove("monitor-native-excel", "operational-native-excel", "excel-grid");
    $(target).innerHTML = `<div class="empty-overview">Nenhum protocolo encontrado.</div>`;
    return;
  }
  renderProtocoloExcelGrid(rows, { onStatusChange: callbacks.updateStatus });
}

function protocoloCardIcon(name) {
  const icons = {
    calendar: `<svg viewBox="0 0 24 24"><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M8 3v4" /><path d="M16 3v4" /><path d="M4 10h16" /></svg>`,
    check: `<svg viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5" /></svg>`,
    "file-search": `<svg viewBox="0 0 24 24"><path d="M7 3h7l4 4v14H7V3Z" /><path d="M14 3v5h5" /><path d="M10 13h5" /><circle cx="17" cy="16" r="3" /><path d="m19.5 18.5 2 2" /></svg>`,
  };
  return icons[name] || icons.calendar;
}







