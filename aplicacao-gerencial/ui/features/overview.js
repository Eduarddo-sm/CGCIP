import { api } from "../core/api.js";
import { readCache, removeCache, removeCachePrefix, writeCache } from "../core/cache.js";
import { $, captureScrollState } from "../core/dom.js";
import { setLoading, skeletonList } from "../core/loading.js";
import { signatureOf } from "../core/signature.js?v=20260715-compact-cache-1";
import { state } from "../core/state.js";
import { toast } from "../core/toast.js";
import { configureOverviewView, renderOverview } from "./overviewView.js?v=20260717-overview-drawer-1";

export { closeOverviewDetails, renderChangesTable } from "./overviewView.js?v=20260717-overview-drawer-1";

const callbacks = {
  removeNotification: () => {},
  loadNotifications: async () => {},
  loadMainHub: async () => {},
  openNegociador: async () => {},
  openNegociadorWithClientFilter: async () => {},
};

let loadToken = 0;

function compactVersion(value) {
  const version = String(value || "");
  return version.length <= 128 ? version : signatureOf(version);
}

function invalidateOverviewCaches() {
  removeCache("mainhub.unread");
  removeCachePrefix("overview.");
  state.overviewVersion = "";
  state.overviewVersionKey = "";
  state.hubVersion = "";
}

function scheduleOverviewRefresh() {
  window.clearTimeout(state.overviewRefreshTimer);
  state.overviewRefreshTimer = window.setTimeout(() => {
    Promise.allSettled([
      loadOverview({ preserveScroll: state.mode === "overview" }),
      callbacks.loadNotifications(),
      callbacks.loadMainHub(),
    ]).then((results) => {
      if (results.some((result) => result.status === "rejected")) {
        console.warn("Falha ao sincronizar overview apos leitura", results);
      }
    });
  }, 120);
}

export function configureOverview(options = {}) {
  configureOverviewView({
    markRead: markOverviewRead,
    openNegociador: options.openNegociador,
    openNegociadorWithClientFilter: options.openNegociadorWithClientFilter,
  });
  if (typeof options.removeNotification === "function") callbacks.removeNotification = options.removeNotification;
  if (typeof options.loadNotifications === "function") callbacks.loadNotifications = options.loadNotifications;
  if (typeof options.loadMainHub === "function") callbacks.loadMainHub = options.loadMainHub;
  if (typeof options.openNegociador === "function") callbacks.openNegociador = options.openNegociador;
  if (typeof options.openNegociadorWithClientFilter === "function") callbacks.openNegociadorWithClientFilter = options.openNegociadorWithClientFilter;
}

export async function loadOverview(options = {}) {
  const { preserveScroll = true } = options;
  const token = ++loadToken;
  const hasRenderedList = Boolean($("#overviewList")?.children.length) && !$("#overviewList")?.classList.contains("is-loading");
  const params = new URLSearchParams({
    status: state.overviewStatus,
    usuario: $("#overviewFilterUser")?.value || "",
    data: $("#overviewFilterDate")?.value || "",
    tipo: $("#overviewFilterType")?.value || "",
    prioridade: $("#overviewFilterPriority")?.value || "",
  });
  const cacheKey = `overview.${params.toString()}`;
  let usedCache = false;
  if (state.mode === "overview" && !state.overview.length && !hasRenderedList) {
    const cached = readCache(cacheKey, 180000);
    if (cached) {
      state.overview = cached.items || cached;
      state.overviewVersion = compactVersion(cached.version || cached.signature || signatureOf(state.overview));
      state.overviewVersionKey = cacheKey;
      renderOverview();
      usedCache = true;
    }
  }
  if (state.mode === "overview" && !state.overview.length && !hasRenderedList) {
    if (!usedCache) setLoading("#overviewList", skeletonList(5));
  }
  if (state.overviewVersion && state.overviewVersionKey === cacheKey) {
    params.set("version", state.overviewVersion);
  }
  const payload = await api(`/api/overview?${params.toString()}`);
  if (token !== loadToken) return;
  if (payload && !Array.isArray(payload) && payload.changed === false) return;
  const overview = Array.isArray(payload) ? payload : payload.items || [];
  const signature = payload?.version || signatureOf({ key: cacheKey, overview });
  if (state.overviewVersion && state.overviewVersionKey === cacheKey && state.overviewVersion === signature) return;
  writeCache(cacheKey, { items: overview, signature, version: signature });
  const restoreScroll = preserveScroll ? captureScrollState([document.scrollingElement, "#overviewContent", "#overviewList"]) : () => {};
  state.overview = overview;
  state.overviewVersion = signature;
  state.overviewVersionKey = cacheKey;
  renderOverview();
  restoreScroll();
}

export async function markOverviewRead(itemId) {
  const previousOverview = state.overview;
  const previousHub = state.hub;
  invalidateOverviewCaches();
  state.overview = state.overviewStatus === "unread"
    ? state.overview.filter((item) => item.id !== itemId)
    : state.overview.map((item) => item.id === itemId ? { ...item, lido: true } : item);
  state.hub = {
    ...state.hub,
    overview: (state.hub.overview || []).filter((item) => item.id !== itemId),
  };
  if (state.mode === "overview") renderOverview();
  callbacks.removeNotification(itemId);
  try {
    await api("/api/overview/read", {
      method: "POST",
      body: JSON.stringify({ id: itemId, usuario: state.user?.username || "" }),
    });
    scheduleOverviewRefresh();
  } catch (error) {
    state.overview = previousOverview;
    state.hub = previousHub;
    if (state.mode === "overview") renderOverview();
    toast(error.message || "Nao foi possivel marcar como lido");
  }
}

export async function markAllOverviewRead() {
  const payload = {
    usuario: $("#overviewFilterUser")?.value || "",
    data: $("#overviewFilterDate")?.value || "",
    tipo: $("#overviewFilterType")?.value || "",
    prioridade: $("#overviewFilterPriority")?.value || "",
  };
  const previousOverview = state.overview;
  const previousHub = state.hub;
  const visibleCount = state.overviewStatus === "unread"
    ? state.overview.length
    : state.overview.filter((item) => !item.lido).length;
  invalidateOverviewCaches();
  state.overview = state.overviewStatus === "unread" ? [] : state.overview.map((item) => ({ ...item, lido: true }));
  state.hub = { ...state.hub, overview: [] };
  if (state.mode === "overview") renderOverview();
  try {
    const result = await api("/api/overview/read-all", { method: "POST", body: JSON.stringify(payload) });
    toast(`${result.items ?? visibleCount} itens marcados como lidos`);
    scheduleOverviewRefresh();
  } catch (error) {
    state.overview = previousOverview;
    state.hub = previousHub;
    if (state.mode === "overview") renderOverview();
    toast(error.message || "Nao foi possivel marcar tudo como lido");
  }
}
