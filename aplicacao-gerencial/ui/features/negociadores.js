import { api } from "../core/api.js";
import { readCache, writeCache } from "../core/cache.js";
import { $ } from "../core/dom.js";
import { escapeHtml } from "../core/html.js";
import { setLoading, skeletonList } from "../core/loading.js";
import { state } from "../core/state.js";
import { toast } from "../core/toast.js";
import { configureNegociadoresCrud } from "./negociadoresCrud.js";
import { renderFilters, renderGrid } from "./negociadoresGrid.js?v=20260728-next-month-fix-1";
import { renderTimeline } from "./negociadorTimeline.js?v=20260717-css-cleanup-2";
import { renderNegociadorProfile, showNegociadorProfileTab } from "./negociadorProfile.js?v=20260728-next-month-fix-1";
import { currentProfilePeriod } from "./negociadorPeriod.js?v=20260728-next-month-fix-1";
import { renderCarteiras } from "./carteiras.js?v=20260825-beta-repurchase-1";
import { syncCarteiraSelects } from "./carteiraOptions.js";

export { loadSheets, openForm, removeActive, saveForm, updateFormSource } from "./negociadoresCrud.js";
export { openEvent } from "./negociadoresEvents.js";
export { renderGrid } from "./negociadoresGrid.js?v=20260728-next-month-fix-1";

const hooks = {
  renderVisibility: () => {},
  loadOverview: async () => {},
  loadMainHub: async () => {},
};
const CACHE_KEY = "negociadores.list";

export function configureNegociadores(options = {}) {
  Object.assign(hooks, options);
  configureNegociadoresCrud({ reload: loadNegociadores });
}

export async function loadNegociadores() {
  if (!state.negociadores.length) {
    const cached = readCache(CACHE_KEY, 300000);
    if (cached) {
      state.negociadores = cached;
      renderNegociadores();
      renderCarteiras();
      syncCarteiraSelects();
      hooks.renderVisibility();
    } else if (state.mode === "negociadores") {
      setLoading("#negociadoresList", skeletonList(4));
    }
  }
  state.negociadores = await api("/api/negociadores");
  writeCache(CACHE_KEY, state.negociadores);
  renderNegociadores();
  renderCarteiras();
  syncCarteiraSelects();
  if (state.activeId && state.mode === "negociador") await loadActive();
  hooks.renderVisibility();
}

export function renderNegociadores() {
  $("#negociadoresBadge").textContent = state.negociadores.length;
  if (!state.negociadores.length) {
    $("#negociadoresList").innerHTML = `<div class="empty-overview">Nenhum negociador cadastrado.</div>`;
    return;
  }
  const groups = groupedNegociadores();
  if (!groups.length) {
    $("#negociadoresList").innerHTML = `<div class="empty-overview">Nenhum negociador encontrado para esta pesquisa.</div>`;
    return;
  }
  $("#negociadoresList").innerHTML = groups.map((group) => `
    <section class="negociador-group">
      <header>
        <strong>${escapeHtml(group.carteira)}</strong>
        <span>${group.items.length} negociadores</span>
      </header>
      <div class="negociador-cards">
        ${group.items.map((item) => `
          <button class="negociador-card ${item.online ? "online" : "offline"}" data-negociador="${item.id}">
            <span class="negociador-card-avatar" aria-hidden="true">
              <img src="/assets/icons/people-9.svg" alt="" />
            </span>
            <span class="negociador-card-main">
              <strong>${escapeHtml(item.nome)}</strong>
              <span class="negociador-card-presence"><i></i>${item.online ? "Online" : "Offline"}</span>
            </span>
            <span class="negociador-card-arrow" aria-hidden="true">&rsaquo;</span>
          </button>
        `).join("")}
      </div>
    </section>
  `).join("");
  document.querySelectorAll("[data-negociador]").forEach((button) => {
    button.addEventListener("click", () => openNegociador(Number(button.dataset.negociador)));
  });
}

function groupedNegociadores() {
  const groups = new Map();
  const search = ($("#negociadoresSearch")?.value || "").trim().toLowerCase();
  [...state.negociadores]
    .sort((a, b) => String(a.nome).localeCompare(String(b.nome)))
    .forEach((item) => {
      const carteira = item.carteira || "Carteira nao informada";
      const matchesSearch = !search
        || String(item.nome || "").toLowerCase().includes(search)
        || String(carteira).toLowerCase().includes(search);
      if (!matchesSearch) return;
      if (!groups.has(carteira)) groups.set(carteira, []);
      groups.get(carteira).push(item);
    });
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([carteira, items]) => ({ carteira, items }));
}

export async function openNegociador(id) {
  const period = currentProfilePeriod();
  state.mode = "negociador";
  state.activeId = id;
  state.negociadorProfile.tab = "producao";
  state.negociadorProfile.corrections = [];
  state.negociadorProfile.month = period.month;
  state.negociadorProfile.year = period.year;
  state.timeline.activeItem = null;
  state.timeline.activityType = "all";
  state.timeline.activitySearch = "";
  state.filters = {};
  state.sort = { column: null, dir: 1 };
  document.body.classList.remove("negociador-focus-mode");
  showNegociadorProfileTab("producao");
  await loadActive();
}

export async function openNegociadorWithClientFilter(id, clientName = "") {
  await openNegociador(id);
  const search = $("#quickSearch");
  if (search && clientName) {
    search.value = clientName;
    renderGrid();
  }
}

async function loadActive() {
  if (!state.activeId) return;
  const active = state.negociadores.find((item) => item.id === state.activeId);
  if (state.mode === "negociador") $("#pageTitle").textContent = "Perfil do negociador";
  setLoading("#timeline", skeletonList(3));
  setLoading("#grid", skeletonList(6));
  state.timeline.sheetCache.clear();
  state.timeline.sheetSnapshot = null;
  const [data, timeline, corrections] = await Promise.all([
    api(`/api/negociadores/${state.activeId}/data`),
    loadTimelinePayload(state.activeId),
    loadCorrectionsPayload(state.activeId),
  ]);
  state.data = data;
  state.events = timeline.events || [];
  state.timeline.months = timeline.months || [];
  state.timeline.version = timeline.version || "";
  state.timeline.totalChanges = Number(timeline.total_changes || 0);
  state.negociadorProfile.corrections = corrections;
  renderTimeline();
  renderFilters();
  renderGrid();
  renderNegociadorProfile();
  hooks.renderVisibility();
}

async function loadTimelinePayload(negociadorId) {
  try {
    return await api(`/api/negociadores/${negociadorId}/timeline`);
  } catch {
    const events = await api(`/api/negociadores/${negociadorId}/events`);
    return { events, months: [], total_changes: 0, version: "" };
  }
}

async function loadCorrectionsPayload(negociadorId) {
  try {
    const payload = await api(`/api/negociadores/${negociadorId}/corrections?limit=300`);
    return Array.isArray(payload) ? payload : [];
  } catch {
    return [];
  }
}

export function showNegociadores() {
  state.mode = "negociadores";
  document.body.classList.remove("negociador-focus-mode");
  $("#pageTitle").textContent = "Negociadores";
  renderNegociadores();
  hooks.renderVisibility();
}

export async function refreshActive(silent = false) {
  if (!state.activeId) return;
  try {
    await api(`/api/negociadores/${state.activeId}/refresh`);
    await loadActive();
    await hooks.loadOverview();
    await hooks.loadMainHub();
    if (!silent) toast("Dados atualizados");
  } catch (error) {
    if (!silent) toast(error.message);
  }
}

export async function openActiveSpreadsheet() {
  if (!state.activeId) {
    toast("Selecione um negociador");
    return;
  }
  try {
    await api(`/api/negociadores/${state.activeId}/abrir-planilha`, { method: "POST", body: "{}" });
    toast("Planilha aberta");
  } catch (error) {
    toast(error.message);
  }
}
