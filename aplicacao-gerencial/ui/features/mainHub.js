import { api } from "../core/api.js";
import { readCache, writeCache } from "../core/cache.js";
import { $, captureScrollState } from "../core/dom.js";
import { setLoading, skeletonList } from "../core/loading.js";
import { signatureOf } from "../core/signature.js?v=20260715-compact-cache-1";
import { state } from "../core/state.js";
import { toast } from "../core/toast.js";
import { closeDialog } from "../layout/dialogs.js";
import { findHubCard } from "./mainHubCards.js";
import { configureMainHubView, renderMainHub } from "./mainHubView.js?v=20260810-dynamic-hub-1";
import { markOverviewRead } from "./overview.js?v=20260717-overview-drawer-1";
import { markParecer } from "./parecer.js?v=20260722-report-download-1";
import { parecerPk } from "./parecerData.js";
import { updateProtocoloStatus } from "./protocolo.js?v=20260717-css-cleanup-2";
import { protocoloStatus } from "./protocoloData.js";

export { renderMainHub } from "./mainHubView.js?v=20260810-dynamic-hub-1";

const callbacks = {
  reload: async () => loadMainHub(),
  openDynamicTool: async () => {},
};

let loadToken = 0;
const CACHE_KEY = "mainhub.unread";

export function configureMainHub(options = {}) {
  configureMainHubView({ runAction: runMainHubAction });
  if (typeof options.reload === "function") callbacks.reload = options.reload;
  if (typeof options.openDynamicTool === "function") callbacks.openDynamicTool = options.openDynamicTool;
}

export async function loadMainHub(options = {}) {
  const { preserveScroll = true } = options;
  const token = ++loadToken;
  const hasHubItems = state.hub.overview.length || state.hub.pareceres.length || state.hub.protocolos.length || (state.hub.ferramentas || []).length;
  const hasRenderedList = Boolean($("#mainHubList")?.children.length) && !$("#mainHubList")?.classList.contains("is-loading");
  let usedCache = false;
  if (!hasHubItems && !hasRenderedList) {
    const cached = readCache(CACHE_KEY, 180000);
    if (cached) {
      applyMainHubPayload(cached, preserveScroll);
      state.hubVersion = cached.signature || signatureOf(cached);
      usedCache = true;
    }
  }
  if (!hasHubItems && !hasRenderedList && !usedCache) {
    setLoading("#mainHubList", skeletonList(5));
  }
  const versionQuery = state.hubVersion ? `?version=${encodeURIComponent(state.hubVersion)}` : "";
  const response = await api(`/api/main-hub${versionQuery}`);
  if (token !== loadToken) return;
  if (response.changed === false) return;
  const overview = response.overview || [];
  const pareceres = response.pareceres || [];
  const protocolos = response.protocolos || [];
  const ferramentas = response.ferramentas || [];
  const payload = {
    overview: overview.filter((item) => !item.lido),
    pareceres,
    protocolos: protocolos.filter((row) => protocoloStatus(row) === "PENDENTE"),
    ferramentas,
    errors: response.errors || {},
  };
  payload.signature = response.version || signatureOf(payload);
  if (state.hubVersion && state.hubVersion === payload.signature) return;
  writeCache(CACHE_KEY, payload);
  applyMainHubPayload(payload, preserveScroll, overview, protocolos);
}

function applyMainHubPayload(payload, preserveScroll, overview = payload.overview || [], protocoloRecords = payload.protocolos || []) {
  const restoreScroll = preserveScroll ? captureScrollState([document.scrollingElement, "#mainHubContent", "#mainHubList", "#mainHubList .hub-card-list"]) : () => {};
  state.overview = overview;
  state.hub = {
    overview: payload.overview || [],
    pareceres: payload.pareceres || [],
    protocolos: payload.protocolos || [],
    ferramentas: payload.ferramentas || [],
    errors: payload.errors || {},
  };
  state.hubVersion = payload.signature || signatureOf(state.hub);
  state.parecer.pendentes = state.hub.pareceres;
  state.protocolo.records = protocoloRecords;
  renderMainHub();
  restoreScroll();
}

async function runMainHubAction(cardId) {
  const card = findHubCard(cardId);
  if (!card) return;
  try {
    let completed = true;
    if (card.source === "monitoramento") {
      await markOverviewRead(card.raw.id);
      toast("Alteracao marcada como lida");
    } else if (card.source === "parecer") {
      completed = await markParecer(parecerPk(card.raw));
    } else if (card.source === "protocolo") {
      completed = await updateProtocoloStatus(card.raw.__row_number, "CONCLUIDO", { value: "PENDENTE" });
    } else {
      closeDialog("#mainHubDialog");
      await callbacks.openDynamicTool(card.raw);
      return;
    }
    if (!completed) return;
    closeDialog("#mainHubDialog");
    await callbacks.reload();
  } catch (error) {
    toast(error.message);
  }
}
