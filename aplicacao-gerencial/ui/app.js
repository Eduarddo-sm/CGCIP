import { applyNavigationState, enableNavigationPersistence, loadNavigationState } from "./core/navigationPersistence.js";
import { loadSession } from "./core/session.js?v=20260731-superadmin-1";
import { state } from "./core/state.js";
import { toast } from "./core/toast.js";
import { startSyncCoordinator } from "./core/syncCoordinator.js?v=20260717-stable-negotiator-profile-1";
import { startBackgroundOptimization } from "./features/backgroundOptimization.js?v=20260717-css-cleanup-2";
import { loadCarteiras, syncCarteiraSelects } from "./features/carteiraOptions.js";
import { configureNotifications, initNotificationAlerts, loadNotifications, removeNotification, removeParecerNotifications } from "./features/notifications.js?v=20260727-dynamic-tools-2";
import { renderCarteiras, showCarteiras } from "./features/carteiras.js?v=20260825-beta-repurchase-1";
import { configureMainHub, loadMainHub } from "./features/mainHub.js?v=20260810-dynamic-hub-1";
import { initMonitorFechamento } from "./features/monitorFechamento.js?v=20260713-monthly-close-1";
import { initMonitorPlanilha } from "./features/monitorPlanilha.js?v=20260825-beta-repurchase-1";
import { configureNegociadores, loadNegociadores, openNegociador, openNegociadorWithClientFilter, refreshActive, renderGrid, showNegociadores } from "./features/negociadores.js?v=20260825-beta-repurchase-1";
import { setupNegociadorProfile } from "./features/negociadorProfile.js?v=20260716-negociador-profile-10";
import { renderTimeline } from "./features/negociadorTimeline.js?v=20260717-css-cleanup-2";
import { configureOverview, loadOverview } from "./features/overview.js?v=20260717-overview-drawer-1";
import { configureParecer, loadParecerConfig, showParecerPage } from "./features/parecer.js?v=20260722-report-download-1";
import { initProductionIntelligence } from "./features/productionIntelligence.js?v=20260902-agreement-identity-1";
import { initDefasagem } from "./features/defasagem.js?v=20260727-defasagem-links-rollback-2";
import { loadHighlightedToolNavigation, openToolRecords, showHighlightedTool } from "./features/ferramentaBuilder.js?v=20260825-beta-repurchase-1";
import { configureProtocolo } from "./features/protocolo.js?v=20260717-unfreeze-last-1";
import { configureSpreadsheetGrid } from "./features/spreadsheetGrid.js?v=20260826-edit-tab-1";
import { bindActions } from "./layout/actions.js?v=20260828-defasagem-source-1";
import { setupModuleTabs } from "./layout/moduleTabs.js?v=20260721-analysis-sidebar-1";
import { showAnalise, showDefasagem, showColchao, showConfiguracao, showMainHub, showMonitorFechamento, showMonitorPlanilha, showOverview, showParecer, showProtocolo } from "./layout/navigation.js?v=20260825-beta-repurchase-1";
import { applySidebarState } from "./layout/sidebar.js";
import { loadTemplates } from "./layout/templates.js?v=20260717-css-cleanup-2";
import { applyTheme } from "./layout/theme.js?v=20260715-executive-prototype-1";
import { configureToolSwitcher, selectTool } from "./layout/toolSwitcher.js?v=20260811-highlighted-active-1";
import { renderVisibility } from "./layout/visibility.js?v=20260810-highlighted-screens-1";

configureSpreadsheetGrid({ toast });
configureParecer({
  removeParecerNotifications,
  onPowerQueryRefresh: loadNotifications,
  onHubRefresh: () => loadMainHub({ preserveScroll: true }),
});
configureOverview({
  removeNotification,
  loadNotifications,
  loadMainHub: () => loadMainHub({ preserveScroll: true }),
  openNegociador,
  openNegociadorWithClientFilter,
});
configureNegociadores({
  renderVisibility,
  loadOverview: () => loadOverview({ preserveScroll: state.mode === "overview" }),
  loadMainHub: () => loadMainHub({ preserveScroll: true }),
});
configureProtocolo({
  onHubRefresh: () => loadMainHub({ preserveScroll: true }),
});
configureMainHub({
  reload: async () => {
    await loadMainHub({ preserveScroll: true });
    await loadNotifications(true);
  },
  openDynamicTool: async (item) => {
    state.configPage = "ferramentas";
    await showConfiguracao();
    await openToolRecords(Number(item.tool_id));
  },
});
configureToolSwitcher({ showMainHub, showOverview, showParecer, showProtocolo, showColchao, showAnalise, showDefasagem, showConfiguracao });
configureNotifications({
  openOverview: () => showOverview(),
  openParecerPendentes: () => {
    selectTool("parecer");
    showParecerPage("pendentes");
  },
  openProtocoloPendentes: () => {
    selectTool("protocolo");
  },
  openDynamicTool: async (item) => {
    state.configPage = "ferramentas";
    await showConfiguracao();
    await openToolRecords(Number(item.tool_id));
  },
});

async function boot() {
  const storedNavigation = loadNavigationState();
  applyNavigationState(storedNavigation);
  applyTheme();
  applySidebarState();
  await loadTemplates([
    { path: "/templates/modules/backoffice/index.html", target: ".workspace", position: "beforeend" },
    { path: "/templates/modules/analise/index.html", target: ".workspace", position: "beforeend" },
    { path: "/templates/modules/analise/defasagem.html", target: ".workspace", position: "beforeend" },
    { path: "/templates/groups/empty.html?v=20260731-permissions-center-1", target: "#content", position: "beforebegin" },
    { path: "/templates/shell/dialogs.html?v=20260731-superadmin-1", target: "body", position: "beforeend" },
  ]);
  setupModuleTabs();
  initProductionIntelligence();
  initDefasagem();
  setupNegociadorProfile({ refresh: refreshActive, renderSheet: renderGrid, renderTimeline });
  bindActions();
  await loadCarteiras().catch((error) => toast(error.message));
  initNotificationAlerts();
  initMonitorPlanilha();
  initMonitorFechamento();
  startBackgroundOptimization();
  enableNavigationPersistence();
  await loadSession().catch((error) => toast(error.message));
  await loadHighlightedToolNavigation();

  if (storedNavigation?.mode === "negociador") {
    await loadNegociadores();
    syncCarteiraSelects();
  }
  restoreNavigation(storedNavigation).catch((error) => toast(error.message));

  if (storedNavigation?.mode !== "negociador") {
    loadNegociadores()
      .then(() => syncCarteiraSelects())
      .catch((error) => toast(error.message));
  }
  if (state.mode !== "parecer") {
    loadParecerConfig().catch((error) => toast(error.message));
  }
  renderCarteiras();
  startSyncCoordinator({
    getMode: () => state.mode,
    refreshOverview: () => loadOverview({ preserveScroll: true }),
    refreshMainHub: () => loadMainHub({ preserveScroll: true }),
    refreshNotifications: () => loadNotifications(true),
  });
}

async function restoreNavigation(storedNavigation) {
  const mode = storedNavigation?.mode || state.mode || "mainhub";
  if (mode === "overview") return showOverview();
  if (mode === "negociadores") return showNegociadores();
  if (mode === "carteiras") return showCarteiras();
  if (mode === "monitorPlanilha") return showMonitorPlanilha();
  if (mode === "monitorFechamento") return showMonitorFechamento();
  if (mode === "negociador" && state.activeId && state.negociadores.some((item) => String(item.id) === String(state.activeId))) {
    return openNegociador(state.activeId);
  }
  if (mode === "parecer") return showParecer();
  if (mode === "protocolo") return showProtocolo();
  if (mode === "colchao") return showColchao();
  if (mode === "analise") return showAnalise();
  if (mode === "defasagem") return showDefasagem();
  if (mode === "configuracao") return showConfiguracao();
  if (mode === "dynamicTool" && state.dynamicToolId) return showHighlightedTool(state.dynamicToolId);
  return showMainHub();
}

boot().catch((error) => toast(error.message));
