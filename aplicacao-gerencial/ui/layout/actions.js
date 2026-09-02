import { $ } from "../core/dom.js";
import { logout } from "../core/session.js";
import { state } from "../core/state.js";
import {
  createDatabaseBackup,
  applyBackupFilters,
  collectDatabaseMonitoring,
  discardConfigPermissionChanges,
  exportConfigAudit,
  loadConfigAudit,
  loadConfigBackups,
  loadConfigDiagnostic,
  loadConfigPermissions,
  loadConfigSchemaVersions,
  loadConfigUsers,
  openConfigUserDialog,
  renderConfigUserPermissions,
  saveConfigUser,
  saveBackupStorage,
  saveAttachmentStorage,
  saveDefasagemSource,
  saveConfigPermissions,
  saveConfigUserPermissions,
  setConfigPermissionSection,
  setConfigPermissionView,
  testDatabaseAlert,
  toggleBackupStorageEditor,
  toggleAttachmentStorageEditor,
  toggleDefasagemSourceEditor,
  updateConfigPermissionFilters,
  showConfigPage,
  updateConfigUserType,
} from "../features/configuracao.js?v=20260828-defasagem-source-1";
import { loadMainHub } from "../features/mainHub.js?v=20260810-dynamic-hub-1";
import { loadDynamicToolsAdmin, openToolBuilder } from "../features/ferramentaBuilder.js?v=20260812-multi-field-condition-1";
import {
  closeMonitorMonth,
  downloadMonitorClosingReport,
  loadMonitorFechamento,
} from "../features/monitorFechamento.js?v=20260713-monthly-close-1";
import {
  downloadMonitorReport,
  loadMonitorPlanilha,
  openMonitorClientDialog,
  openMonitorPlanilhaExpanded,
  openMonitorReportDialog,
  updateReportNegotiators,
  updateReportScope,
  updateReportFormat,
} from "../features/monitorPlanilha.js?v=20260825-beta-repurchase-1";
import {
  collapseCarteiraHistory,
  addCarteiraColumn,
  createCarteiraPrompt,
  expandCarteiraHistory,
  renderCarteiraMonitor,
  resetCarteiraSelection,
  saveCarteira,
  showCarteiras,
} from "../features/carteiras.js?v=20260825-beta-repurchase-1";
import {
  closeNotifications,
  toggleNotificationAlerts,
  toggleNotifications,
} from "../features/notifications.js";
import {
  closeOverviewDetails,
  loadOverview,
  markAllOverviewRead,
} from "../features/overview.js?v=20260717-overview-drawer-1";
import {
  downloadParecerReport,
  markSelectedParecer,
  refreshParecerPowerQuery,
  renderParecerAprovacao,
  renderParecerCompleta,
  renderParecerPendentes,
  showParecerPage,
  toggleParecerSheetFocus,
} from "../features/parecer.js?v=20260722-report-download-1";
import {
  downloadProtocoloReport,
  openProtocoloForm,
  renderProtocoloPage,
  saveProtocolo,
  showProtocoloPage,
  toggleProtocoloSheetFocus,
} from "../features/protocolo.js?v=20260717-css-cleanup-2";
import { bindNotesDialogActions } from "../features/notes.js?v=20260717-main-hub-audit-1";
import {
  clearColchaoQuickFilters,
  downloadColchaoReport,
  openColchaoSpreadsheet,
  renderPendencias as renderColchaoPendencias,
  resetColchaoCompletoPage,
  saveColchaoAgreement,
  saveColchaoBatchStatus,
  saveColchaoConfig,
  showColchaoProfiles,
  showColchaoPage,
  syncColchaoData,
} from "../features/colchao.js?v=20260814-client-finance-5";
import {
  collapseClientHistory,
  expandClientHistory,
  renderClientHistory,
} from "../features/negociadoresHistory.js?v=20260717-css-cleanup-2";
import {
  loadSheets,
  openActiveSpreadsheet,
  openForm,
  refreshActive,
  removeActive,
  renderGrid,
  renderNegociadores,
  saveForm,
  showNegociadores,
  updateFormSource,
} from "../features/negociadores.js?v=20260825-beta-repurchase-1";
import { showMainHub, showMonitorFechamento, showMonitorPlanilha, showOverview } from "./navigation.js?v=20260825-beta-repurchase-1";
import { bindAllDialogDismiss, closeDialog } from "./dialogs.js";
import { closeProfileMenu, toggleProfileMenu } from "./profile.js";
import { toggleSidebar } from "./sidebar.js";
import { toggleTheme } from "./theme.js";
import { closeToolMenu, selectTool, toggleToolMenu } from "./toolSwitcher.js?v=20260811-highlighted-active-1";

export function bindActions() {
  document.addEventListener("click", (event) => {
    const addCarteiraButton = event.target.closest("#addCarteiraBtn");
    if (!addCarteiraButton) return;
    event.preventDefault();
    createCarteiraPrompt();
  });
  bindAllDialogDismiss();
  bindNotesDialogActions();
  $("#sidebarToggleBtn").addEventListener("click", toggleSidebar);
  document.getElementById("addBtn")?.addEventListener("click", () => openForm());
  $("#addFromListBtn").addEventListener("click", () => openForm());
  $("#mainHubBtn").addEventListener("click", showMainHub);
  $("#overviewBtn").addEventListener("click", showOverview);
  $("#negociadoresBtn").addEventListener("click", showNegociadores);
  $("#carteirasBtn").addEventListener("click", showCarteiras);
  $("#carteiraForm")?.addEventListener("submit", saveCarteira);
  $("#addCarteiraColumnBtn")?.addEventListener("click", addCarteiraColumn);
  document.querySelectorAll("[data-close-carteira]").forEach((button) => {
    button.addEventListener("click", () => closeDialog("#carteiraDialog"));
  });
  $("#monitorPlanilhaBtn")?.addEventListener("click", showMonitorPlanilha);
  $("#monitorFechamentoBtn")?.addEventListener("click", showMonitorFechamento);
  $("#notificationBtn").addEventListener("click", toggleNotifications);
  $("#notificationAlertsBtn").addEventListener("click", toggleNotificationAlerts);
  $("#toolMenuBtn").addEventListener("click", toggleToolMenu);
  document.querySelectorAll("[data-tool]").forEach((button) => {
    button.addEventListener("click", () => selectTool(button.dataset.tool));
  });
  document.querySelectorAll("[data-group-tool]").forEach((button) => {
    button.addEventListener("click", () => selectTool(button.dataset.groupTool));
  });
  $("#backToNegociadoresBtn").addEventListener("click", showNegociadores);
  $("#reloadMainHubBtn").addEventListener("click", () => loadMainHub({ preserveScroll: true }));
  $("#reloadOverviewBtn").addEventListener("click", () => loadOverview({ preserveScroll: true }));
  $("#reloadConfigUsersBtn")?.addEventListener("click", loadConfigUsers);
  $("#reloadConfigAuditBtn")?.addEventListener("click", loadConfigAudit);
  $("#exportConfigAuditCsvBtn")?.addEventListener("click", () => exportConfigAudit("csv"));
  $("#exportConfigAuditXlsxBtn")?.addEventListener("click", () => exportConfigAudit("xlsx"));
  ["configAuditSearch", "configAuditActor", "configAuditAction", "configAuditEntity", "configAuditOutcome", "configAuditFrom", "configAuditTo"].forEach((id) => {
    $(`#${id}`)?.addEventListener("input", loadConfigAudit);
    $(`#${id}`)?.addEventListener("change", loadConfigAudit);
  });
  $("#reloadConfigPermissionsBtn")?.addEventListener("click", loadConfigPermissions);
  $("#saveConfigPermissionsBtn")?.addEventListener("click", saveConfigPermissions);
  $("#discardConfigPermissionsBtn")?.addEventListener("click", discardConfigPermissionChanges);
  $("#configPermissionSearch")?.addEventListener("input", updateConfigPermissionFilters);
  $("#configPermissionModuleFilter")?.addEventListener("change", updateConfigPermissionFilters);
  $("#configPermissionStateFilter")?.addEventListener("change", updateConfigPermissionFilters);
  $("#configPermissionProfile")?.addEventListener("change", updateConfigPermissionFilters);
  document.querySelectorAll("[data-permission-view]").forEach((button) => button.addEventListener("click", () => setConfigPermissionView(button.dataset.permissionView)));
  document.querySelectorAll("[data-permission-section]").forEach((button) => button.addEventListener("click", () => setConfigPermissionSection(button.dataset.permissionSection)));
  $("#saveConfigUserPermissionsBtn")?.addEventListener("click", saveConfigUserPermissions);
  $("#configUserPermissionSelect")?.addEventListener("change", renderConfigUserPermissions);
  $("#reloadConfigSchemasBtn")?.addEventListener("click", loadConfigSchemaVersions);
  $("#reloadDynamicToolsBtn")?.addEventListener("click", loadDynamicToolsAdmin);
  $("#openDynamicToolBuilderBtn")?.addEventListener("click", () => openToolBuilder());
  $("#configSchemaCarteira")?.addEventListener("change", loadConfigSchemaVersions);
  $("#reloadDatabaseBackupsBtn")?.addEventListener("click", loadConfigBackups);
  $("#createDatabaseBackupBtn")?.addEventListener("click", createDatabaseBackup);
  $("#saveBackupStorageBtn")?.addEventListener("click", saveBackupStorage);
  $("#editBackupStorageBtn")?.addEventListener("click", () => toggleBackupStorageEditor(true));
  $("#cancelBackupStorageBtn")?.addEventListener("click", () => toggleBackupStorageEditor(false));
  $("#saveAttachmentStorageBtn")?.addEventListener("click", saveAttachmentStorage);
  $("#editAttachmentStorageBtn")?.addEventListener("click", () => toggleAttachmentStorageEditor(true));
  $("#cancelAttachmentStorageBtn")?.addEventListener("click", () => toggleAttachmentStorageEditor(false));
  $("#saveDefasagemSourceBtn")?.addEventListener("click", saveDefasagemSource);
  $("#editDefasagemSourceBtn")?.addEventListener("click", () => toggleDefasagemSourceEditor(true));
  $("#cancelDefasagemSourceBtn")?.addEventListener("click", () => toggleDefasagemSourceEditor(false));
  $("#backupSearchInput")?.addEventListener("input", applyBackupFilters);
  $("#backupSourceFilter")?.addEventListener("change", applyBackupFilters);
  $("#backupPeriodFilter")?.addEventListener("change", applyBackupFilters);
  $("#reloadConfigDiagnosticBtn")?.addEventListener("click", loadConfigDiagnostic);
  $("#collectDatabaseMonitoringBtn")?.addEventListener("click", collectDatabaseMonitoring);
  $("#testDatabaseAlertBtn")?.addEventListener("click", testDatabaseAlert);
  $("#openConfigUserDialogBtn")?.addEventListener("click", openConfigUserDialog);
  document.querySelectorAll("[data-config-page]").forEach((button) => {
    button.addEventListener("click", () => showConfigPage(button.dataset.configPage));
  });
  $("#configUserForm")?.addEventListener("submit", saveConfigUser);
  $("#configUserForm")?.type?.addEventListener("change", updateConfigUserType);
  document.querySelectorAll("[data-close-config-user]").forEach((button) => {
    button.addEventListener("click", () => closeDialog("#configUserDialog"));
  });
  $("#monitorPlanilhaReloadBtn")?.addEventListener("click", loadMonitorPlanilha);
  $("#monitorPlanilhaAddClientBtn")?.addEventListener("click", openMonitorClientDialog);
  $("#monitorPlanilhaOpenReportBtn")?.addEventListener("click", openMonitorReportDialog);
  $("#monitorPlanilhaExpandBtn")?.addEventListener("click", openMonitorPlanilhaExpanded);
  ["monitorPlanilhaCarteira", "monitorPlanilhaMes", "monitorPlanilhaAno"].forEach((id) => {
    $(`#${id}`)?.addEventListener("change", loadMonitorPlanilha);
  });
  $("#monitorFechamentoReloadBtn")?.addEventListener("click", loadMonitorFechamento);
  $("#monitorFechamentoCloseBtn")?.addEventListener("click", closeMonitorMonth);
  $("#monitorFechamentoReportBtn")?.addEventListener("click", downloadMonitorClosingReport);
  ["monitorFechamentoCarteira", "monitorFechamentoMes", "monitorFechamentoAno"].forEach((id) => {
    $(`#${id}`)?.addEventListener("change", loadMonitorFechamento);
  });
  $("#monitorReportForm")?.addEventListener("submit", downloadMonitorReport);
  $("#monitorReportForm")?.carteira?.addEventListener("change", updateReportNegotiators);
  $("#monitorReportForm")?.escopo?.addEventListener("change", updateReportScope);
  $("#monitorReportForm")?.formato?.addEventListener("change", updateReportFormat);
  document.querySelectorAll("[data-close-monitor-report]").forEach((button) => {
    button.addEventListener("click", () => closeDialog("#monitorReportDialog"));
  });
  document.querySelectorAll("[data-close-monitor-client]").forEach((button) => {
    button.addEventListener("click", () => closeDialog("#monitorClientDialog"));
  });
  document.querySelectorAll("[data-close-monitor-planilha-expanded]").forEach((button) => {
    button.addEventListener("click", () => closeDialog("#monitorPlanilhaExpandedDialog"));
  });
  $("#markAllOverviewBtn").addEventListener("click", markAllOverviewRead);
  document.querySelectorAll("[data-overview-status]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.overviewStatus = button.dataset.overviewStatus;
      await loadOverview({ preserveScroll: false });
    });
  });
  $("#profileBtn").addEventListener("click", toggleProfileMenu);
  $("#logoutBtn").addEventListener("click", logout);
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".profile-menu")) closeProfileMenu();
    if (!event.target.closest(".tool-switcher")) closeToolMenu();
    if (!event.target.closest(".notification-menu")) closeNotifications();
  });
  document.querySelectorAll("[data-parecer-page]").forEach((button) => {
    button.addEventListener("click", () => showParecerPage(button.dataset.parecerPage));
  });
  document.querySelectorAll("[data-protocolo-page]").forEach((button) => {
    button.addEventListener("click", () => showProtocoloPage(button.dataset.protocoloPage));
  });
  document.querySelectorAll("[data-colchao-page]").forEach((button) => {
    button.addEventListener("click", () => showColchaoPage(button.dataset.colchaoPage));
  });
  $("#parecerRefreshBtn")?.addEventListener("click", refreshParecerPowerQuery);
  $("#parecerReportFullBtn")?.addEventListener("click", downloadParecerReport);
  $("#parecerSheetFocusBtn")?.addEventListener("click", toggleParecerSheetFocus);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && document.body.classList.contains("parecer-sheet-focus-mode")) {
      toggleParecerSheetFocus();
    }
  });
  $("#protocoloNewBtn")?.addEventListener("click", openProtocoloForm);
  $("#protocoloSheetNewBtn")?.addEventListener("click", openProtocoloForm);
  $("#protocoloSheetReportBtn")?.addEventListener("click", downloadProtocoloReport);
  $("#protocoloSheetFocusBtn")?.addEventListener("click", toggleProtocoloSheetFocus);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && document.body.classList.contains("protocolo-sheet-focus-mode")) {
      toggleProtocoloSheetFocus();
    }
  });
  $("#colchaoReloadBtn").addEventListener("click", syncColchaoData);
  $("#colchaoBackProfilesTopBtn").addEventListener("click", showColchaoProfiles);
  $("#colchaoOpenSpreadsheetBtn").addEventListener("click", openColchaoSpreadsheet);
  $("#colchaoReportBtn")?.addEventListener("click", () => downloadColchaoReport());
  $("#colchaoConfigForm").addEventListener("submit", saveColchaoConfig);
  $("#colchaoAgreementForm").addEventListener("submit", saveColchaoAgreement);
  $("#protocoloForm").addEventListener("submit", saveProtocolo);
  document.querySelectorAll("[data-close-protocolo]").forEach((button) => button.addEventListener("click", () => closeDialog("#protocoloDialog")));
  document.querySelector("[data-close-hub]").addEventListener("click", () => closeDialog("#mainHubDialog"));
  $("#parecerPendingSearch").addEventListener("input", renderParecerPendentes);
  ["parecerPendingNegotiator", "parecerPendingReason", "parecerPendingOrder"].forEach((id) => {
    $(`#${id}`)?.addEventListener("change", renderParecerPendentes);
  });
  $("#parecerPendingMarkSelected")?.addEventListener("click", markSelectedParecer);
  $("#parecerApprovalSearch")?.addEventListener("input", renderParecerAprovacao);
  ["parecerFullSearch", "parecerFilterNegociador", "parecerFilterData", "parecerFilterStatus", "parecerFilterSolicitado"].forEach((id) => {
    $(`#${id}`)?.addEventListener("input", () => {
      state.parecer.pageIndex = 1;
      renderParecerCompleta();
    });
  });
  ["colchaoPendingSearch", "colchaoPendingBucket", "colchaoPendingOperator", "colchaoPendingDate", "colchaoPendingOrder"].forEach((id) => {
    $(`#${id}`).addEventListener("input", renderColchaoPendencias);
  });
  let colchaoSearchTimer = 0;
  $("#colchaoFullSearch")?.addEventListener("input", () => {
    window.clearTimeout(colchaoSearchTimer);
    colchaoSearchTimer = window.setTimeout(resetColchaoCompletoPage, 250);
  });
  ["colchaoFilterOperador", "colchaoFilterStatus", "colchaoFilterVencimento"].forEach((id) => {
    $(`#${id}`)?.addEventListener("change", resetColchaoCompletoPage);
  });
  $("#colchaoClearQuickFiltersBtn")?.addEventListener("click", clearColchaoQuickFilters);
  $("#colchaoSaveChangesBtn").addEventListener("click", saveColchaoBatchStatus);
  $("#colchaoSheetSelect").addEventListener("change", (event) => {
    state.colchao.sheet = event.currentTarget.value;
    state.colchao.pendingStatusChanges = {};
    resetColchaoCompletoPage();
  });
  ["overviewFilterUser", "overviewFilterDate", "overviewFilterType", "overviewFilterPriority"].forEach((id) => {
    $(`#${id}`).addEventListener("input", () => loadOverview({ preserveScroll: false }));
  });
  [
    "protocoloCarteiraOpen",
    "protocoloSearchOpen",
    "protocoloSortOpen",
  ].forEach((id) => {
    const element = $(`#${id}`);
    if (!element) return;
    element.addEventListener("input", renderProtocoloPage);
    element.addEventListener("change", renderProtocoloPage);
  });
  $("#editBtn").addEventListener("click", () => openForm(state.negociadores.find((item) => item.id === state.activeId)));
  $("#removeBtn").addEventListener("click", removeActive);
  $("#refreshBtn").addEventListener("click", () => refreshActive(false));
  $("#openNegotiatorSpreadsheetBtn").addEventListener("click", openActiveSpreadsheet);
  $("#themeBtn").addEventListener("click", toggleTheme);
  $("#quickSearch").addEventListener("input", renderGrid);
  ["historyPeriodFilter", "historyUserFilter", "historyTypeFilter", "historyTextFilter"].forEach((id) => {
    $(`#${id}`)?.addEventListener("input", renderClientHistory);
  });
  $("#expandClientHistoryBtn")?.addEventListener("click", expandClientHistory);
  $("#collapseClientHistoryBtn")?.addEventListener("click", collapseClientHistory);
  $("#negociadoresSearch").addEventListener("input", renderNegociadores);
  $("#backToCarteirasBtn").addEventListener("click", resetCarteiraSelection);
  ["carteiraClientSearch", "carteiraPeriodFilter", "carteiraUserFilter", "carteiraTypeFilter"].forEach((id) => {
    $(`#${id}`).addEventListener("input", renderCarteiraMonitor);
  });
  $("#expandCarteiraHistoryBtn").addEventListener("click", expandCarteiraHistory);
  $("#collapseCarteiraHistoryBtn").addEventListener("click", collapseCarteiraHistory);
  $("#negociadorForm").addEventListener("submit", saveForm);
  document.querySelectorAll("input[name='source_type']").forEach((input) => {
    input.addEventListener("change", updateFormSource);
  });
  $("#loadSheetsBtn").addEventListener("click", loadSheets);
  document.querySelectorAll("[data-close]").forEach((btn) => btn.addEventListener("click", () => closeDialog("#negociadorDialog")));
  document.querySelector("[data-close-event]").addEventListener("click", () => closeDialog("#eventDialog"));
  document.querySelectorAll("[data-close-overview]").forEach((button) => button.addEventListener("click", closeOverviewDetails));
}
