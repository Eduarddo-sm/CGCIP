import { $ } from "../core/dom.js";
import { formatValue } from "../core/format.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { state } from "../core/state.js";
import { availableProfileYears, monthOptions } from "./negociadorPeriod.js?v=20260716-negociador-period-2";
import { bindNotesButtons, notesButton } from "./notes.js";
import { groupTimelineChangesByLine } from "./timelineData.js?v=20260717-css-cleanup-2";

const TYPE_FILTERS = [
  ["all", "Todos os eventos"],
  ["new", "Novos clientes"],
  ["status", "Status"],
  ["payment", "Pagamentos"],
  ["value", "Valores"],
  ["critical", "Quebras e exclusoes"],
  ["update", "Atualizacoes"],
];
let feedScrollTop = 0;

export function renderTimeline() {
  const root = $("#timeline");
  if (!root) return;
  const currentFeed = root.querySelector(".negociador-timeline-feed");
  if (currentFeed) feedScrollTop = currentFeed.scrollTop;
  const allItems = buildActivityItems(state.events || []);
  const periodItems = allItems.filter(matchesPeriod);
  const items = periodItems.filter(matchesFilters);
  const days = groupItemsByDay(items);
  const active = selectActiveItem(items);
  const totalChanges = periodItems.reduce((sum, item) => sum + item.changes.length, 0);
  const yearOptions = timelineYears();

  $("#timelineHint").textContent = `${periodItems.length} registros · ${totalChanges} alteracoes`;
  root.innerHTML = `
    <div class="negociador-timeline-shell">
      <header class="negociador-timeline-toolbar">
        <div class="negociador-timeline-title">
          <strong>Atividade</strong>
          <span>${periodItems.length} registros no periodo</span>
        </div>
        <div class="negociador-timeline-filters">
          <select data-timeline-month aria-label="Mes da timeline">
            ${monthOptions().map((item) => `<option value="${item.value}" ${item.value === Number(state.negociadorProfile.month) ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("")}
          </select>
          <select data-timeline-year aria-label="Ano da timeline">
            ${yearOptions.map((year) => `<option value="${year}" ${year === Number(state.negociadorProfile.year) ? "selected" : ""}>${year}</option>`).join("")}
          </select>
          <select data-timeline-type aria-label="Tipo da alteracao">
            ${TYPE_FILTERS.map(([value, label]) => `<option value="${value}" ${value === (state.timeline.activityType || "all") ? "selected" : ""}>${label}</option>`).join("")}
          </select>
          <input data-timeline-search type="search" placeholder="Cliente, campo ou responsavel" value="${escapeAttr(state.timeline.activitySearch || "")}" />
        </div>
      </header>
      <div class="negociador-timeline-workspace">
        <aside class="negociador-timeline-feed" aria-label="Eventos cronologicos">
          ${days.length ? days.map((day, dayIndex) => renderDay(day, dayIndex)).join("") : renderEmptyFeed()}
        </aside>
        <section class="negociador-timeline-detail" aria-live="polite">
          ${active ? renderDetail(active) : renderEmptyDetail()}
        </section>
      </div>
    </div>
  `;
  bindTimelineActions(root);
  bindNotesButtons(root);
  const feed = root.querySelector(".negociador-timeline-feed");
  if (feed) {
    feed.scrollTop = feedScrollTop;
    feed.addEventListener("scroll", () => { feedScrollTop = feed.scrollTop; }, { passive: true });
  }
}

function buildActivityItems(events) {
  const items = [];
  [...events].sort((a, b) => eventDate(b) - eventDate(a)).forEach((event) => {
    if (event.event_type === "new_month") {
      items.push(itemFromGroup(event, { line: "", client: "Novo mes", changes: event.delta?.changes || [] }, 0));
      return;
    }
    groupTimelineChangesByLine(event).forEach((group, index) => items.push(itemFromGroup(event, group, index)));
  });
  return items;
}

function itemFromGroup(event, group, index) {
  const date = eventDate(event);
  const type = activityType(event, group.changes || []);
  return {
    key: `${event.id}:${group.line || index}`,
    event,
    date,
    line: group.line || "",
    client: group.client || "",
    changes: group.changes || [],
    type,
    typeLabel: activityTypeLabel(type, event.event_type),
  };
}

function groupItemsByDay(items) {
  const days = new Map();
  items.forEach((item) => {
    const dayKey = localDateKey(item.date);
    if (!days.has(dayKey)) days.set(dayKey, { key: dayKey, date: item.date, hours: new Map(), changes: 0 });
    const day = days.get(dayKey);
    const hourKey = timestampKey(item.date);
    if (!day.hours.has(hourKey)) day.hours.set(hourKey, { key: hourKey, date: item.date, items: [], changes: 0 });
    const hour = day.hours.get(hourKey);
    hour.items.push(item);
    hour.changes += item.changes.length;
    day.changes += item.changes.length;
  });
  return [...days.values()].map((day) => ({
    ...day,
    hours: [...day.hours.values()].sort((a, b) => b.date - a.date),
  })).sort((a, b) => b.date - a.date);
}

function renderDay(day, dayIndex) {
  const clients = new Set(day.hours.flatMap((hour) => hour.items.map((item) => item.client).filter(Boolean))).size;
  const containsActive = day.hours.some((hour) => hour.items.some((item) => item.key === state.timeline.activeItem));
  return `
    <details class="negociador-timeline-day" ${dayIndex < 2 || containsActive ? "open" : ""}>
      <summary>
        <span><strong>${escapeHtml(dayTitle(day.date))}</strong><small>${clients} clientes envolvidos</small></span>
        <span>${day.changes} alteracoes</span>
      </summary>
      <div class="negociador-timeline-hours">
        ${day.hours.map(renderHour).join("")}
      </div>
    </details>
  `;
}

function renderHour(hour) {
  const priority = hour.items.some((item) => item.type === "critical") ? "critical"
    : hour.items.some((item) => item.type === "new" || item.type === "payment") ? "important" : "normal";
  return `
    <article class="negociador-timeline-hour ${priority}">
      <div class="negociador-timeline-hour-head">
        <span class="negociador-timeline-dot"></span>
        <time>${escapeHtml(timeLabel(hour.date))}</time>
        <span>${hour.changes} alteracoes</span>
      </div>
      <div class="negociador-timeline-clients">
        ${hour.items.map(renderActivityButton).join("")}
      </div>
    </article>
  `;
}

function renderActivityButton(item) {
  const active = state.timeline.activeItem === item.key;
  const client = item.client || "Cliente nao localizado";
  return `
    <button class="negociador-timeline-client ${active ? "active" : ""}" type="button" data-timeline-item="${escapeAttr(item.key)}">
      <span class="negociador-timeline-type ${escapeAttr(item.type)}"></span>
      <span>
        <strong>${escapeHtml(client)}</strong>
        <small>${item.line ? `Linha ${escapeHtml(item.line)} · ` : ""}${escapeHtml(item.typeLabel)}</small>
      </span>
      <b>${item.changes.length}</b>
    </button>
  `;
}

function renderDetail(item) {
  const event = item.event;
  const responsible = event.negociador_nome || event.metadata?.negociador || "Sistema";
  const client = item.client || "Cliente nao localizado";
  return `
    <div class="negociador-timeline-detail-head">
      <div>
        <span class="negociador-timeline-detail-eyebrow">${escapeHtml(item.typeLabel)}</span>
        <h3>${escapeHtml(client)}</h3>
        <p>${item.line ? `Linha ${escapeHtml(item.line)} · ` : ""}${item.changes.length} alteracoes</p>
      </div>
      ${notesButton("event", event.id, "Observacoes")}
    </div>
    <div class="negociador-timeline-meta">
      ${metaItem("Responsavel", responsible)}
      ${metaItem("Data e hora", dateTimeLabel(item.date))}
      ${metaItem("Sheet", event.sheet || event.metadata?.sheet || "-")}
      ${metaItem("Origem", originLabel(event.event_type))}
    </div>
    <div class="negociador-timeline-comparison">
      <div class="negociador-timeline-comparison-head">
        <strong>Comparativo da linha</strong>
        <span>Somente campos alterados</span>
      </div>
      ${renderComparison(item)}
    </div>
  `;
}

function renderComparison(item) {
  if (item.event.event_type === "new_month") {
    const change = item.event.delta?.changes?.[0] || {};
    return comparisonTable([{
      column: "Sheet ativa",
      before: change.before || change.before_sheet,
      after: change.after || change.after_sheet || item.event.sheet,
    }]);
  }
  return comparisonTable(uniqueChanges(item.changes));
}

function comparisonTable(changes) {
  if (!changes.length) return `<div class="negociador-timeline-no-changes">Nenhuma alteracao detalhada disponivel.</div>`;
  return `
    <div class="negociador-timeline-table-scroll">
      <table class="negociador-timeline-table">
        <thead><tr><th>Estado</th>${changes.map((change) => `<th>${escapeHtml(change.column || "Campo")}</th>`).join("")}</tr></thead>
        <tbody>
          <tr><th>Antes</th>${changes.map((change) => `<td class="before">${escapeHtml(formatValue(change.before))}</td>`).join("")}</tr>
          <tr><th>Depois</th>${changes.map((change) => `<td class="after">${escapeHtml(formatValue(change.after))}</td>`).join("")}</tr>
        </tbody>
      </table>
    </div>
  `;
}

function uniqueChanges(changes) {
  const byColumn = new Map();
  changes.forEach((change, index) => {
    const column = change.column || `Campo ${index + 1}`;
    if (!byColumn.has(column)) byColumn.set(column, { ...change, column });
    else {
      const current = byColumn.get(column);
      current.after = change.after;
    }
  });
  return [...byColumn.values()];
}

function bindTimelineActions(root) {
  root.querySelectorAll("[data-timeline-item]").forEach((button) => {
    button.addEventListener("click", () => {
      state.timeline.activeItem = button.dataset.timelineItem;
      renderTimeline();
    });
  });
  root.querySelector("[data-timeline-month]")?.addEventListener("change", updatePeriodFromTimeline);
  root.querySelector("[data-timeline-year]")?.addEventListener("change", updatePeriodFromTimeline);
  root.querySelector("[data-timeline-type]")?.addEventListener("change", (event) => {
    state.timeline.activityType = event.target.value;
    state.timeline.activeItem = null;
    feedScrollTop = 0;
    renderTimeline();
  });
  root.querySelector("[data-timeline-search]")?.addEventListener("input", (event) => {
    const position = event.target.selectionStart ?? event.target.value.length;
    state.timeline.activitySearch = event.target.value;
    state.timeline.activeItem = null;
    feedScrollTop = 0;
    renderTimeline();
    const input = root.querySelector("[data-timeline-search]");
    input?.focus({ preventScroll: true });
    input?.setSelectionRange(position, position);
  });
}

function updatePeriodFromTimeline() {
  state.negociadorProfile.month = Number($("#timeline [data-timeline-month]")?.value || 0);
  state.negociadorProfile.year = Number($("#timeline [data-timeline-year]")?.value || 0);
  state.timeline.activeItem = null;
  feedScrollTop = 0;
  document.dispatchEvent(new CustomEvent("negociador:period-change"));
}

function selectActiveItem(items) {
  const selected = items.find((item) => item.key === state.timeline.activeItem) || items[0] || null;
  state.timeline.activeItem = selected?.key || null;
  return selected;
}

function matchesPeriod(item) {
  return item.date.getMonth() + 1 === Number(state.negociadorProfile.month)
    && item.date.getFullYear() === Number(state.negociadorProfile.year);
}

function matchesFilters(item) {
  const type = state.timeline.activityType || "all";
  if (type !== "all" && item.type !== type) return false;
  const query = normalize(state.timeline.activitySearch);
  if (!query) return true;
  const haystack = [
    item.client,
    item.line,
    item.event.negociador_nome,
    item.event.sheet,
    item.typeLabel,
    ...item.changes.flatMap((change) => [change.column, change.before, change.after]),
  ].map(normalize).join(" ");
  return haystack.includes(query);
}

function activityType(event, changes) {
  if (event.event_type === "new_month") return "update";
  if (changes.some((change) => change.type === "row_added" || change.type === "cell_filled" && !change.before)) return "new";
  if (changes.some((change) => change.type === "row_removed" || statusText(change).includes("QUEBRA") || statusText(change).includes("NEGADA"))) return "critical";
  if (changes.some((change) => statusText(change).includes("PAGAMENTO REALIZADO") || statusText(change) === "PAGO")) return "payment";
  if (changes.some((change) => normalize(change.column).includes("STATUS"))) return "status";
  if (changes.some((change) => /VALOR|HONOR|ENTRADA/.test(normalize(change.column)))) return "value";
  return "update";
}

function activityTypeLabel(type, eventType) {
  if (eventType === "new_month") return "Novo mes";
  return { new: "Novo cliente", status: "Status alterado", value: "Valor alterado", critical: "Alteracao critica", payment: "Pagamento realizado", update: "Campos alterados" }[type] || "Atualizacao";
}

function statusText(change) {
  return normalize(change.column).includes("STATUS") ? normalize(change.after) : "";
}

function timelineYears() {
  const years = new Set(availableProfileYears(state.data));
  (state.events || []).forEach((event) => years.add(eventDate(event).getFullYear()));
  return [...years].filter((year) => year >= 2000).sort((a, b) => b - a);
}

function metaItem(label, value) {
  return `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function renderEmptyFeed() {
  return `<div class="negociador-timeline-empty"><strong>Nenhuma atividade encontrada</strong><span>Altere o periodo ou limpe os filtros.</span></div>`;
}

function renderEmptyDetail() {
  return `<div class="negociador-timeline-empty"><strong>Sem evento selecionado</strong><span>Selecione uma alteracao para consultar o comparativo.</span></div>`;
}

function eventDate(event) {
  const date = new Date(event.changed_at);
  return Number.isNaN(date.getTime()) ? new Date(0) : date;
}

function localDateKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function timestampKey(date) {
  return `${localDateKey(date)}T${timeLabel(date)}`;
}

function dayTitle(date) {
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (localDateKey(date) === localDateKey(today)) return "Hoje";
  if (localDateKey(date) === localDateKey(yesterday)) return "Ontem";
  return date.toLocaleDateString("pt-BR", { day: "2-digit", month: "long" });
}

function timeLabel(date) {
  return date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function dateTimeLabel(date) {
  return date.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "medium" });
}

function originLabel(eventType) {
  return { file_changed: "Sistema negocial", manual_update: "Atualizacao manual", initial_snapshot: "Snapshot", sheet_changed: "Troca de sheet", new_month: "Sistema" }[eventType] || "Monitoramento";
}

function normalize(value) {
  return String(value ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/\s+/g, " ").trim().toUpperCase();
}
