import { api } from "../core/api.js";
import { $ } from "../core/dom.js";
import { formatValue } from "../core/format.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { state } from "../core/state.js";
import { labelChange, renderMiniRowDiff } from "./changeDiff.js";
import { groupTimelineChangesByLine } from "./timelineData.js?v=20260717-css-cleanup-2";

const expanded = new Set();
const collapsedMonths = new Set();
let visibleLimit = 50;
let lastQuery = "";
let globalEventsLoaded = false;
let globalEventsLoading = false;

export function renderClientHistory() {
  const query = $("#quickSearch")?.value.trim().toLowerCase() || "";
  const panel = $("#clientHistoryPanel");
  if (!query) {
    panel.classList.add("hidden");
    expanded.clear();
    return;
  }
  if (query !== lastQuery) {
    visibleLimit = 50;
    expanded.clear();
    collapsedMonths.clear();
    lastQuery = query;
  }
  if (!activeNegotiadorHasQuery(query)) {
    panel.classList.add("hidden");
    return;
  }
  panel.classList.remove("hidden");
  ensureGlobalHistoryEvents();
  const filters = historyFilters();
  const allEntries = clientHistoryEntries(query).filter((entry) => matchesHistoryFilters(entry, filters));
  const entries = allEntries.slice(0, visibleLimit);
  $("#clientHistoryTitle").textContent = `Histórico de Alterações - ${$("#quickSearch").value.trim()}`;
  $("#clientHistoryMeta").textContent = `${allEntries.length} eventos encontrados${globalEventsLoading ? " - carregando outros negociadores..." : ""}`;
  $("#clientHistoryTimeline").innerHTML = entries.length
    ? `${renderGroupedHistory(entries)}${allEntries.length > entries.length ? `<button id="loadMoreClientHistoryBtn" class="secondary-btn history-load-more" type="button">Carregar mais ${Math.min(50, allEntries.length - entries.length)}</button>` : ""}`
    : `<div class="empty-overview">Nenhum histórico encontrado para esta busca.</div>`;
  bindHistoryToggles();
  bindMonthToggles();
  $("#loadMoreClientHistoryBtn")?.addEventListener("click", () => {
    visibleLimit += 50;
    renderClientHistory();
  });
}

export function expandClientHistory() {
  clientHistoryEntries($("#quickSearch")?.value.trim().toLowerCase() || "").forEach((entry) => expanded.add(entry.id));
  renderClientHistory();
}

export function collapseClientHistory() {
  expanded.clear();
  renderClientHistory();
}

function historyFilters() {
  return {
    period: $("#historyPeriodFilter")?.value.trim().toLowerCase() || "",
    user: $("#historyUserFilter")?.value.trim().toLowerCase() || "",
    type: $("#historyTypeFilter")?.value.trim().toLowerCase() || "",
    text: $("#historyTextFilter")?.value.trim().toLowerCase() || "",
  };
}

function clientHistoryEntries(query) {
  return historyEvents()
    .flatMap((event) => {
      const date = new Date(event.changed_at);
      if (Number.isNaN(date.getTime())) return [];
      return groupTimelineChangesByLine(event)
        .filter((group) => groupMatchesQuery(group, query))
        .map((group, index) => {
          const type = historyType(group.changes);
          return {
            id: `${event.id || event.changed_at}-${group.line || index}`,
            event,
            group,
            date,
            monthKey: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`,
            monthLabel: date.toLocaleDateString("pt-BR", { month: "long", year: "numeric" }).replace(/^\w/, (char) => char.toUpperCase()),
            user: event.negociador_nome || "Responsável",
            type,
            priority: priorityClass(group.changes),
            description: historyDescription(group, type),
          };
        });
    })
    .sort((a, b) => b.date - a.date);
}

function historyEvents() {
  const byId = new Map();
  const active = state.negociadores.find((item) => item.id === state.activeId);
  const activeWallet = normalizeWallet(active?.carteira || "");
  [...(state.allEvents || []), ...(state.events || [])].forEach((event) => {
    if (activeWallet && normalizeWallet(event.carteira || event.metadata?.carteira || "") !== activeWallet) return;
    byId.set(String(event.id || event.changed_at), event);
  });
  return [...byId.values()];
}

function normalizeWallet(value) {
  return String(value || "Carteira nao informada").trim().toLowerCase();
}

function activeNegotiadorHasQuery(query) {
  if (!query) return false;
  const headers = state.data?.headers || [];
  const rows = state.data?.rows || [];
  const clientHeaders = headers.filter((header) => isClientHeader(header));
  const searchableHeaders = clientHeaders.length ? clientHeaders : headers;
  const hasCurrentRow = rows.some((row) => searchableHeaders.some((header) => String(row[header] ?? "").toLowerCase().includes(query)));
  if (hasCurrentRow) return true;
  return (state.events || []).some((event) => groupTimelineChangesByLine(event).some((group) => groupMatchesQuery(group, query)));
}

function isClientHeader(header) {
  const normalized = String(header || "").trim().toLowerCase();
  return normalized === "cliente"
    || normalized === "nome"
    || normalized === "nome do cliente"
    || normalized === "client"
    || normalized === "customer"
    || normalized.includes("cliente");
}

async function ensureGlobalHistoryEvents() {
  if (globalEventsLoaded || globalEventsLoading) return;
  globalEventsLoading = true;
  try {
    state.allEvents = await api("/api/events?limit=3000");
    globalEventsLoaded = true;
  } catch {
    state.allEvents = state.events || [];
  } finally {
    globalEventsLoading = false;
    renderClientHistory();
  }
}

function groupMatchesQuery(group, query) {
  if (!query) return false;
  const haystack = [
    group.client,
    group.line,
    ...group.changes.flatMap((change) => [change.column, change.before, change.after, change.type]),
  ].map((value) => String(value ?? "").toLowerCase()).join(" ");
  return haystack.includes(query);
}

function matchesHistoryFilters(entry, filters) {
  const dateText = entry.date.toLocaleDateString("pt-BR").toLowerCase();
  const isoText = entry.date.toISOString().slice(0, 10).toLowerCase();
  const monthText = entry.monthKey.toLowerCase();
  const haystack = [
    entry.description,
    entry.user,
    entry.type,
    entry.group.client,
    entry.group.line,
    entry.event.sheet,
    ...entry.group.changes.flatMap((change) => [change.column, change.before, change.after, change.type]),
  ].map((value) => String(value ?? "").toLowerCase()).join(" ");
  return (!filters.period || dateText.includes(filters.period) || isoText.includes(filters.period) || monthText.includes(filters.period))
    && (!filters.user || entry.user.toLowerCase().includes(filters.user))
    && (!filters.type || entry.type.toLowerCase().includes(filters.type))
    && (!filters.text || haystack.includes(filters.text));
}

function renderGroupedHistory(entries) {
  const groups = new Map();
  entries.forEach((entry) => {
    if (!groups.has(entry.monthKey)) groups.set(entry.monthKey, { label: entry.monthLabel, entries: [] });
    groups.get(entry.monthKey).entries.push(entry);
  });
  return [...groups.entries()].map(([monthKey, group]) => {
    const isCollapsed = collapsedMonths.has(monthKey);
    return `
    <section class="history-month ${isCollapsed ? "collapsed" : ""}">
      <button class="history-month-toggle" type="button" data-history-month="${escapeAttr(monthKey)}" aria-expanded="${String(!isCollapsed)}">
        <span>${escapeHtml(group.label)}</span>
        <strong>${group.entries.length} eventos</strong>
        <b>${isCollapsed ? "Expandir" : "Recolher"}</b>
      </button>
      ${isCollapsed ? "" : `
        <div class="history-events">
          ${group.entries.map(renderHistoryEntry).join("")}
        </div>
      `}
    </section>
  `;
  }).join("");
}

function renderHistoryEntry(entry) {
  const isExpanded = expanded.has(entry.id);
  return `
    <article class="history-event ${escapeAttr(entry.priority)}">
      <button class="history-summary" type="button" data-history-toggle="${escapeAttr(entry.id)}" aria-expanded="${String(isExpanded)}">
        <span class="history-dot"></span>
        <span>
          <strong>${escapeHtml(entry.date.toLocaleString("pt-BR"))} - ${escapeHtml(entry.user)}</strong>
          <em>${escapeHtml(entry.type)}</em>
          <small>${escapeHtml(entry.description)}</small>
        </span>
        <b>${isExpanded ? "Recolher" : "Expandir"}</b>
      </button>
      ${isExpanded ? renderHistoryDetails(entry) : ""}
    </article>
  `;
}

function renderHistoryDetails(entry) {
  return `
    <div class="history-details">
      <div class="meta-grid">
        <div><strong>Data e hora exata</strong><br>${escapeHtml(entry.date.toLocaleString("pt-BR"))}</div>
        <div><strong>Usuário responsável</strong><br>${escapeHtml(entry.user)}</div>
        <div><strong>Origem</strong><br>${escapeHtml(originLabel(entry.event.event_type))}</div>
        <div><strong>ID do log</strong><br>${escapeHtml(String(entry.event.id || entry.id))}</div>
        <div><strong>Sheet</strong><br>${escapeHtml(entry.event.sheet || "")}</div>
        <div><strong>Linha/registro</strong><br>${escapeHtml(formatValue(entry.group.line || "Não localizado"))}</div>
      </div>
      ${renderMiniRowDiff(entry.group.changes, entry.group.line)}
      <p class="history-note"><strong>Observações:</strong> ${escapeHtml(entry.event.metadata?.message || "Sem observações vinculadas.")}</p>
    </div>
  `;
}

function bindHistoryToggles() {
  document.querySelectorAll("[data-history-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.dataset.historyToggle;
      if (expanded.has(id)) expanded.delete(id);
      else expanded.add(id);
      renderClientHistory();
    });
  });
}

function bindMonthToggles() {
  document.querySelectorAll("[data-history-month]").forEach((button) => {
    button.addEventListener("click", () => {
      const monthKey = button.dataset.historyMonth;
      if (collapsedMonths.has(monthKey)) collapsedMonths.delete(monthKey);
      else collapsedMonths.add(monthKey);
      renderClientHistory();
    });
  });
}

function historyType(changes) {
  if (changes.some((change) => change.type === "row_added")) return "Cadastro";
  if (changes.some((change) => change.type === "row_removed")) return "Exclusão";
  const columns = changes.map((change) => String(change.column || "").toLowerCase()).join(" ");
  if (columns.includes("telefone") || columns.includes("fone") || columns.includes("celular")) return "Telefone";
  if (columns.includes("email") || columns.includes("e-mail")) return "E-mail";
  if (columns.includes("endereco") || columns.includes("endereço") || columns.includes("cidade") || columns.includes("uf")) return "Endereço";
  if (columns.includes("contrato") || columns.includes("npj") || columns.includes("processo")) return "Contrato";
  if (columns.includes("status") || columns.includes("situacao") || columns.includes("situação")) return "Status";
  if (columns.includes("observacao") || columns.includes("observação") || columns.includes("obs")) return "Observação";
  if (changes.some((change) => change.type === "cell_filled")) return "Cadastro";
  return "Alteração";
}

function historyDescription(group, type) {
  const first = group.changes[0] || {};
  const field = first.column || labelChange(first);
  const client = group.client || `Linha ${group.line || "não localizada"}`;
  if (group.changes.length > 1) return `${type}: ${group.changes.length} campos alterados em ${client}`;
  return `${type}: ${field} de "${formatValue(first.before)}" para "${formatValue(first.after)}"`;
}

function priorityClass(changes) {
  if (changes.some((change) => change.type === "row_removed" || change.type === "cell_cleared")) return "removed";
  if (changes.some((change) => change.type === "row_added" || change.type === "cell_filled")) return "added";
  return "changed";
}

function originLabel(eventType) {
  return {
    file_changed: "Importação/arquivo monitorado",
    manual_update: "Atualização manual",
    initial_snapshot: "Sistema",
    sheet_changed: "Sistema",
    new_month: "Sistema",
  }[eventType] || "Sistema";
}
