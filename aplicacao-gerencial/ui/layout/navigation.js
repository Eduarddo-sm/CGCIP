import { $ } from "../core/dom.js";
import { state } from "../core/state.js";
import { showColchaoProfiles } from "../features/colchao.js?v=20260814-client-finance-5";
import { showConfigPage } from "../features/configuracao.js?v=20260811-tool-trash-1";
import { loadMainHub } from "../features/mainHub.js?v=20260810-dynamic-hub-1";
import { loadMonitorFechamento } from "../features/monitorFechamento.js?v=20260713-monthly-close-1";
import { loadMonitorPlanilha } from "../features/monitorPlanilha.js?v=20260825-beta-repurchase-1";
import { loadOverview } from "../features/overview.js?v=20260717-overview-drawer-1";
import { loadParecerConfig, loadParecerPage } from "../features/parecer.js?v=20260722-report-download-1";
import { loadProtocoloPage } from "../features/protocolo.js?v=20260717-css-cleanup-2";
import { loadProductionIntelligence } from "../features/productionIntelligence.js?v=20260902-agreement-identity-1";
import { loadDefasagem } from "../features/defasagem.js?v=20260727-defasagem-links-rollback-2";
import { renderVisibility } from "./visibility.js";

function setSidebarContext(title, mark) {
  $("#activeToolName").textContent = title;
  $("#toolMenuBtn .brand-mark").textContent = mark;
}

function setBackofficeContext() {
  state.activeGroup = "backoffice";
  setSidebarContext("BACKOFFICE", "B");
}

function applyActiveGroupContext() {
  if (state.activeGroup === "analise") {
    setSidebarContext("AN\u00c1LISE DE DADOS", "A");
    return;
  }
  if (state.activeGroup === "configuracao") {
    setSidebarContext("CONFIGURA\u00c7\u00c3O", "C");
    return;
  }
  setBackofficeContext();
}

export async function showMainHub() {
  state.mode = "mainhub";
  $("#pageTitle").textContent = "Main Hub";
  applyActiveGroupContext();
  renderVisibility();
  loadMainHub({ preserveScroll: false }).catch(() => {});
}

export function showOverview() {
  state.mode = "overview";
  $("#pageTitle").textContent = "Monitoramento";
  setBackofficeContext();
  renderVisibility();
  loadOverview({ preserveScroll: false });
}

export async function showMonitorPlanilha() {
  state.mode = "monitorPlanilha";
  $("#pageTitle").textContent = "Monitoramento";
  setBackofficeContext();
  renderVisibility();
  await loadMonitorPlanilha();
}

export async function showMonitorFechamento() {
  state.mode = "monitorFechamento";
  $("#pageTitle").textContent = "Monitoramento";
  setBackofficeContext();
  renderVisibility();
  await loadMonitorFechamento();
}

export async function showParecer() {
  state.mode = "parecer";
  $("#pageTitle").textContent = "Pareceres";
  setBackofficeContext();
  renderVisibility();
  await loadParecerConfig();
  await loadParecerPage();
}

export async function showProtocolo() {
  state.mode = "protocolo";
  $("#pageTitle").textContent = "Protocolos";
  setBackofficeContext();
  renderVisibility();
  await loadProtocoloPage();
}

export async function showColchao() {
  state.mode = "colchao";
  $("#pageTitle").textContent = "COLCHÃƒO";
  setBackofficeContext();
  renderVisibility();
  showColchaoProfiles();
}

export async function showAnalise() {
  state.mode = "analise";
  state.activeGroup = "analise";
  $("#pageTitle").textContent = "Intelig\u00eancia de Produ\u00e7\u00e3o";
  setSidebarContext("AN\u00c1LISE DE DADOS", "A");
  renderVisibility();
  await loadProductionIntelligence();
}

export async function showDefasagem() {
  state.mode = "defasagem";
  state.activeGroup = "analise";
  $("#pageTitle").textContent = "Defasagem de Acionamentos";
  setSidebarContext("AN\u00c1LISE DE DADOS", "A");
  renderVisibility();
  await loadDefasagem();
}

export async function showConfiguracao() {
  state.mode = "configuracao";
  state.activeGroup = "configuracao";
  $("#pageTitle").textContent = "Configura\u00e7\u00e3o";
  setSidebarContext("CONFIGURA\u00c7\u00c3O", "C");
  renderVisibility();
  await showConfigPage(state.configPage || "usuarios");
}
