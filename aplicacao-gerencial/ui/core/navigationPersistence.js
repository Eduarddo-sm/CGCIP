import { state } from "./state.js";

const STORAGE_KEY = "gerencial.navigation.v1";
const VALID_MODES = new Set([
  "mainhub",
  "overview",
  "negociadores",
  "carteiras",
  "monitorPlanilha",
  "monitorFechamento",
  "negociador",
  "parecer",
  "protocolo",
  "colchao",
  "analise",
  "defasagem",
  "configuracao",
  "dynamicTool",
]);
const VALID_GROUPS = new Set(["backoffice", "analise", "configuracao"]);

let enabled = false;

export function enableNavigationPersistence() {
  enabled = true;
}

export function loadNavigationState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const payload = JSON.parse(raw);
    if (!VALID_MODES.has(payload?.mode)) return null;
    return payload;
  } catch {
    return null;
  }
}

export function applyNavigationState(payload) {
  if (!payload) return;
  state.mode = payload.mode;
  state.activeGroup = VALID_GROUPS.has(payload.activeGroup) ? payload.activeGroup : groupForMode(payload.mode);
  state.activeId = payload.activeId || null;
  state.parecer.page = payload.parecerPage || state.parecer.page;
  state.protocolo.page = payload.protocoloPage || state.protocolo.page;
  state.colchao.page = payload.colchaoPage || state.colchao.page;
  state.colchao.profile = payload.colchaoProfile || state.colchao.profile;
  state.configPage = payload.configPage || state.configPage;
  state.dynamicToolId = payload.dynamicToolId || null;
}

export function saveNavigationState() {
  if (!enabled) return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      mode: state.mode,
      activeGroup: state.activeGroup || groupForMode(state.mode),
      activeId: state.activeId,
      parecerPage: state.parecer.page,
      protocoloPage: state.protocolo.page,
      colchaoPage: state.colchao.page,
      colchaoProfile: state.colchao.profile,
      configPage: state.configPage,
      dynamicToolId: state.dynamicToolId,
    }));
  } catch {
    // Local storage can be unavailable in restricted browser contexts.
  }
}

function groupForMode(mode) {
  if (mode === "analise" || mode === "defasagem") return "analise";
  if (mode === "configuracao") return "configuracao";
  return "backoffice";
}
