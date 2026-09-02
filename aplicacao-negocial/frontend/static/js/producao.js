import { apiGet, apiPatch, apiPost, apiPut } from "./api.js?v=20260714-module-contract-1";
import { createExcelGrid } from "./excelGrid.js?v=20260730-inline-save-1";
import { buildProducaoColumns } from "./producao/columns.js?v=20260729-alpha-ho-accounting-1";
import { criticalStatuses, paymentStatus, statusLabels } from "./producao/constants.js?v=20260714-module-contract-1";
import { isAlphaCarteira, isBetaCarteira, normalizedCarteira } from "./producao/carteira.js?v=20260714-module-contract-1";
import {
  availableCompetenciasForItems,
  canMoveToNextMonth,
  competenciaItemCount,
  monthItemsForCompetencia,
  nextCompetenciaValue,
  pluralAcordos,
} from "./producao/competencias.js?v=20260714-module-contract-1";
import {
  competenciaLabel,
  currentCompetencia,
  escapeHtml,
  formatPercent,
  itemCompetencia,
  normalizeMoneyText,
  shortCompetenciaLabel,
  todayInputValue,
} from "./producao/formatters.js?v=20260714-module-contract-1";
import { renderProductionMetrics } from "./producao/metrics.js?v=20260717-production-executive-1";
import { normalizeStatusValue } from "./producao/options.js?v=20260714-module-contract-1";
import { buildProductionUpdatePayload } from "./producao/payload.js?v=20260714-schema-only-1";
import { createStatusDialogs } from "./producao/statusDialogs.js?v=20260828-new-agreement-1";
import { selectionSummary } from "./producao/selectionSummary.js?v=20260714-module-contract-1";
import { createProductionState } from "./producao/state.js?v=20260810-monthly-goals-1";
import { createDynamicFormController } from "./producao/dynamicForm.js?v=20260715-multiselect-2";

const state = createProductionState();

const els = {};
let statusDialogs = null;
let schemaLoadPromise = null;

function qs(selector) {
  return document.querySelector(selector);
}

function currentCarteira() {
  return normalizedCarteira(state.carteira);
}

function isAlpha() {
  return isAlphaCarteira(state.carteira);
}

function isBeta() {
  return isBetaCarteira(state.carteira);
}

function isGamma() {
  if (state.schema?.regra_tipo) return state.schema.regra_tipo === "gamma";
  if (state.schema?.tipo) return state.schema.tipo === "gamma";
  return !isAlpha() && !isBeta();
}

function isDynamicCarteira() {
  return state.schema?.tipo === "dinamica";
}

const {
  applyDynamicAgreementTypeRules,
  bindDynamicFormEvents,
  dynamicAgreementIsAtSight,
  dynamicAutomaticValue,
  dynamicColumns,
  dynamicGridColumns,
  dynamicIdentifierColumn,
  dynamicFieldFormValue,
  dynamicFieldIsEmpty,
  focusDynamicField,
  isAgreementAtSight,
  isDynamicJustificativaColumn,
  isDynamicOperatorColumn,
  normalizeDynamicInput,
  renderDynamicFields,
  dynamicColumnMatches,
  dynamicEntryValueKeys,
} = createDynamicFormController({ state, elements: els, isDynamicCarteira });

function dynamicStatusField() {
  if (!isDynamicCarteira()) return null;
  return document.querySelector('[data-dynamic-field="STATUS"]');
}

function currentFormStatus() {
  const dynamicStatus = dynamicStatusField()?.value;
  return normalizeStatusValue(dynamicStatus || "PROPOSTA", "PROPOSTA");
}

function setFormStatusValue(value) {
  const normalized = normalizeStatusValue(value, "PROPOSTA");
  const dynamicStatus = dynamicStatusField();
  if (dynamicStatus) dynamicStatus.value = normalized;
  return normalized;
}

function nextCompetenciaDisplay() {
  return competenciaLabel(nextCompetenciaValue());
}

function updateNextMonthOption() {
  if (!els.nextMonthField) return;
  const visible = !state.editingId && canMoveToNextMonth();
  els.nextMonthField.classList.toggle("hidden", !visible);
  if (!visible) {
    els.nextMonth.checked = false;
    return;
  }
  els.nextMonthHint.textContent = `O acordo sera salvo em ${nextCompetenciaDisplay()}.`;
}

function updateExpandedSelectionSummary(selection = { cells: [] }) {
  if (!els.expandedSummary) return;
  els.expandedSummary.textContent = selectionSummary(selection);
}

function updateFocusSelectionSummary(selection = { cells: [] }) {
  if (!els.focusSelection) return;
  els.focusSelection.textContent = selectionSummary(selection);
}

function showError(message) {
  els.error.textContent = message;
  els.error.hidden = false;
}

function clearError() {
  els.error.hidden = true;
  els.error.textContent = "";
}

function updateStateItem(updatedItem) {
  const index = state.items.findIndex((entry) => entry.id === updatedItem.id);
  if (index >= 0) {
    state.items[index] = updatedItem;
  }
}

function buildUpdatePayload(item, overrides = {}) {
  return buildProductionUpdatePayload(item, overrides, {
    isGamma: isGamma(),
    identifierKey: dynamicIdentifierColumn()?.chave || "",
  });
}

function isStatusCellField(field) {
  return String(field || "").split(".").pop().toUpperCase() === "STATUS";
}

async function saveProducaoCell(item, field, value) {
  if (itemCompetencia(item) < currentCompetencia()) {
    throw new Error("Competencias anteriores estao bloqueadas para alteracao.");
  }
  if (isStatusCellField(field)) {
    const currentStatus = normalizeStatusValue(item.status, item.status);
    const nextStatus = normalizeStatusValue(value, currentStatus);
    if (nextStatus === currentStatus) return item;

    if (criticalStatuses.has(nextStatus)) {
      openStatusJustificativaDialog(item, nextStatus, null);
      return false;
    }

    const formalizationTransition = criticalStatuses.has(currentStatus)
      && ["AGUARDANDO_PAGAMENTO", paymentStatus].includes(nextStatus);
    if (nextStatus === paymentStatus || formalizationTransition) {
      openStatusPaymentDialog(item, nextStatus, null);
      return false;
    }

    const updatedItem = await saveStatusChange(item.id, nextStatus, null, null);
    return updatedItem;
  }

  const overrides = field.startsWith("campos.")
    ? { campos: { ...(item.campos || {}), [field.slice(7)]: value } }
    : { [field]: value };
  const payload = buildUpdatePayload(item, overrides);
  const response = await apiPut(`/api/producao/${item.id}`, payload);
  updateStateItem(response.item);
  renderCompetenciaPicker();
  renderStats();
  return response.item;
}

function producaoColumns() {
  const columns = buildProducaoColumns({
    dynamicColumns: dynamicGridColumns(),
    saveCell: saveProducaoCell,
  });
  const normalizeField = (value) => String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]/g, "")
    .toLowerCase();
  return columns.map((column) => ({
    ...column,
    cellClass: (item) => {
      const columnKeys = [column.id, column.title, String(column.id || "").replace(/^campos\./, "")].map(normalizeField);
      const corrected = state.corrections.some((entry) => Number(entry.producao_id) === Number(item.id)
        && columnKeys.includes(normalizeField(entry.campo)));
      return corrected ? "recent-backoffice-correction" : "";
    },
  }));
}
function setStep(step) {
  state.step = step;
  document.querySelectorAll("[data-step]").forEach((section) => {
    section.classList.toggle("hidden", Number(section.dataset.step) !== step);
  });
  document.querySelectorAll("[data-step-dot]").forEach((dot) => {
    dot.classList.toggle("active", Number(dot.dataset.stepDot) <= step);
  });
  els.backBtn.classList.toggle("hidden", step === 1);
  els.nextBtn.classList.toggle("hidden", step === 2);
  els.saveBtn.classList.toggle("hidden", step !== 2);
}

async function ensureProductionSchema() {
  if (state.schema?.columns?.length) return state.schema;
  if (!schemaLoadPromise) {
    schemaLoadPromise = apiGet("/api/producao/schema")
      .then((schema) => {
        state.schema = schema;
        applyCarteiraLayout();
        return schema;
      })
      .catch((error) => {
        schemaLoadPromise = null;
        throw error;
      });
  }
  return schemaLoadPromise;
}

async function openDialog(item = null) {
  if (item && itemCompetencia(item) < currentCompetencia()) {
    window.alert("Competencias anteriores estao disponiveis somente para consulta.");
    return;
  }
  const openButton = els.openBtn;
  if (openButton) openButton.disabled = true;
  try {
    await ensureProductionSchema();
  } catch (error) {
    window.alert(error?.message || "Nao foi possivel carregar os campos da producao.");
    return;
  } finally {
    if (openButton) openButton.disabled = false;
  }
  state.editingId = item?.id || null;
  state.moveStatusToNextMonth = false;
  state.formalizadoNovoAcordo = false;
  els.form.reset();
  clearError();
  setStep(1);
  els.title.textContent = item ? "Editar acordo" : "Cadastrar acordo";
  renderDynamicFields(item);

  if (item) {
    els.id.value = item.id;
    els.dataPagamento.value = item.data_pagamento || "";
    els.justificativa.value = item.justificativa_status || "";
    els.flex.value = item.autorizacao_flexibilizacao === "NAO" ? "" : item.autorizacao_flexibilizacao;
    state.previousFormStatus = setFormStatusValue(item.status);
  } else {
    els.justificativa.value = "";
    els.dataPagamento.value = "";
    state.previousFormStatus = setFormStatusValue("PROPOSTA");
  }

  updateFinancialRules();
  updateNextMonthOption();
  els.dialog.showModal();
}

function closeDialog() {
  els.dialog.close();
}

function validateStepOne() {
  const fields = [...els.dynamicStepOne.querySelectorAll("[data-dynamic-field][required], [data-dynamic-field][data-required='true']")];
  const invalid = fields.find((field) => dynamicFieldIsEmpty(field));
  if (invalid) {
    focusDynamicField(invalid);
    showError("Preencha todos os campos obrigatorios antes de avancar.");
    return false;
  }
  clearError();
  return true;
}

function validateFinancialFieldsWithoutStatus() {
  const fields = [...els.dynamicStepTwo.querySelectorAll("[data-dynamic-field][required], [data-dynamic-field][data-required='true']")];
  const invalid = fields.find((field) => dynamicFieldIsEmpty(field));
  if (invalid) {
    focusDynamicField(invalid);
    showError("Preencha todos os campos obrigatorios antes de salvar.");
    return false;
  }
  if (els.flex.required && !els.flex.value) {
    els.flex.focus();
    showError("Informe a autorizacao de flexibilizacao.");
    return false;
  }

  clearError();
  return true;
}

function validateFinancialFields() {
  return validateFinancialFieldsWithoutStatus();
}

function updateFinancialRules() {
  applyDynamicAgreementTypeRules();
  const dynamicValues = dynamicPayloadFields();
  const total = moneyFieldNumber(firstPositiveMoneyField(dynamicValues, [
    "VALOR_FECHADO",
    "VALOR_TOTAL_FECHADO",
    "VALOR_DO_ACORDO",
    "VALOR_TOTAL",
    "VALOR_TOTAL_DE_ACORDO",
    "VALOR_TOTAL_DO_DEBITO",
    "VALOR_MINIMO_PRE_APROVADO",
  ], "0"));
  const ho = isGamma()
    ? moneyFieldNumber(firstFilledField(dynamicValues, ["HONOR_RIOS_RECEBIDOS", "HONORARIOS_RECEBIDOS", "H_O", "HO", "VALOR_HO"], "0"))
    : 0;
  const percent = total > 0 ? (ho / total) * 100 : 0;
  const needsFlex = isGamma() && total > 0 && percent < 9;
  const hasGammaFields = isGamma();
  els.percentualCard.classList.toggle("hidden", !hasGammaFields);
  if (!hasGammaFields) {
    els.flex.value = "";
  }

  els.flexField.classList.toggle("hidden", !needsFlex);
  els.flex.required = needsFlex;
  if (!needsFlex) {
    els.flex.value = "";
  }

  els.percentual.textContent = formatPercent(percent);
  els.percentualCard.classList.toggle("warning", needsFlex);
  els.flexHint.textContent = needsFlex
    ? "H.O menor que 9%. Informe a autorizacao de flexibilizacao."
    : "Autorizacao sera salva automaticamente como NAO.";
}

function dynamicPayloadFields() {
  const fields = {};
  if (!isDynamicCarteira()) return fields;
  const isAtSight = dynamicAgreementIsAtSight();
  dynamicColumns().forEach((column) => {
    const input = document.querySelector(`[data-dynamic-field="${column.chave}"]`);
    const automaticValue = dynamicAutomaticValue(column);
    if (automaticValue !== null) {
      fields[column.chave] = automaticValue;
      return;
    }
    if (isDynamicOperatorColumn(column)) {
      fields[column.chave] = state.user?.username || "";
      return;
    }
    if (isDynamicJustificativaColumn(column) && !input) {
      fields[column.chave] = "";
      return;
    }
    if (!input) return;
    let value = dynamicColumnMatches(column, dynamicEntryValueKeys) && isAtSight ? "0" : dynamicFieldFormValue(input);
    if (String(column.chave || "").toUpperCase() === "STATUS") {
      value = normalizeStatusValue(value, value);
    }
    if (column.tipo === "moeda" || column.tipo === "numero") {
      value = normalizeMoneyText(value).replace(",", ".");
    }
    fields[column.chave] = value;
  });
  return fields;
}

function firstFilledField(campos, keys, fallback = "") {
  for (const key of keys) {
    const value = campos[key];
    if (value !== undefined && value !== null && String(value).trim() !== "") return value;
  }
  return fallback;
}

function moneyFieldNumber(value) {
  const normalized = normalizeMoneyText(value).replace(",", ".");
  const number = Number(normalized || 0);
  return Number.isFinite(number) ? number : 0;
}

function firstPositiveMoneyField(campos, keys, fallback = "0") {
  for (const key of keys) {
    const value = campos[key];
    if (value === undefined || value === null || String(value).trim() === "") continue;
    if (moneyFieldNumber(value) > 0) return value;
  }
  return firstFilledField(campos, keys, fallback);
}

function payloadFromForm() {
  const shouldMoveToNextMonth = Boolean(
    canMoveToNextMonth()
      && (
        (!state.editingId && els.nextMonth?.checked)
        || state.moveStatusToNextMonth
      ),
  );

  const campos = dynamicPayloadFields();
  const identifier = dynamicIdentifierColumn();
  const cliente = firstFilledField(campos, ["CLIENTE", "NOME", "NOME_CLIENTE"], "");
  const valorTotal = firstPositiveMoneyField(campos, [
    "VALOR_FECHADO",
    "VALOR_TOTAL_FECHADO",
    "VALOR_DO_ACORDO",
    "VALOR_TOTAL",
    "VALOR_TOTAL_DE_ACORDO",
    "VALOR_TOTAL_DO_DEBITO",
    "VALOR_MINIMO_PRE_APROVADO",
  ], "0");
  const valorEntrada = firstFilledField(campos, ["VALOR_DA_ENTRADA", "ENTRADA", "VALOR_MINIMO_PRE_APROVADO"], "0");
  const vencimento = firstFilledField(campos, ["DATA_DE_VENCIMENTO", "DATA_DO_VENCIMENTO", "VENCIMENTO"], new Date().toISOString().slice(0, 10));
  const tipo = firstFilledField(campos, ["TIPO", "TIPO_DE_ACORDO", "PARCELADO_OU_VISTA", "PARCELADO_OU_A_VISTA"], "PARCELADO");
  const acordoAVista = isAgreementAtSight(tipo);
  const status = normalizeStatusValue(campos.STATUS || "PROPOSTA", "PROPOSTA");
  campos.STATUS = status;
  if (campos.JUSTIFICATIVA !== undefined && !criticalStatuses.has(status)) {
    campos.JUSTIFICATIVA = "";
  }
  return {
    npj: String(campos[identifier?.chave] || "").trim(),
    cpf: null,
    cliente: String(cliente || "Cliente nao informado").trim(),
    gecor: isGamma() ? String(campos.GECOR || "").trim() || null : null,
    dias_atraso: null,
    data_primeiro_atraso: null,
    portfolio: null,
    carteira_alpha: null,
    tipo_acordo: acordoAVista ? "A_VISTA" : "PARCELADO",
    valor_total_acordo: String(valorTotal || "0"),
    valor_entrada: acordoAVista ? "0" : String(valorEntrada || "0"),
    valor_ho: isGamma() ? String(firstFilledField(campos, ["HONOR_RIOS_RECEBIDOS", "HONORARIOS_RECEBIDOS", "H_O", "HO", "VALOR_HO"], "0")) : null,
    data_vencimento: String(vencimento).slice(0, 10),
    data_pagamento: status === paymentStatus ? els.dataPagamento.value : null,
    status,
    justificativa_status: criticalStatuses.has(status) ? String(campos.JUSTIFICATIVA || els.justificativa.value || "").trim() : null,
    autorizacao_flexibilizacao: isGamma() ? els.flex.value || String(campos.AUTORIZADO || "") || null : null,
    jogar_proximo_mes: shouldMoveToNextMonth,
    formalizado_novo_acordo: Boolean(state.formalizadoNovoAcordo),
    campos,
  };
}

function filteredItems() {
  const search = els.search?.value.trim().toLowerCase() || "";

  return monthItems().filter((item) => {
    const haystack = `${item.cliente || ""} ${Object.values(item.campos || {}).join(" ")}`.toLowerCase();
    const matchesSearch = !search || haystack.includes(search);
    const matchesAttention = state.attentionFilter !== "near-due" || isItemNearDue(item);
    return matchesSearch && matchesAttention;
  });
}

function itemDueDate(item) {
  const fields = item.campos || {};
  return item.data_vencimento
    || fields.DATA_DE_VENCIMENTO
    || fields.DATA_DO_VENCIMENTO
    || fields.VENCIMENTO
    || "";
}

function isItemNearDue(item) {
  if (["PAGAMENTO_REALIZADO", "QUEBRA", "PROPOSTA_NEGADA"].includes(item.status)) return false;
  const rawDate = String(itemDueDate(item)).slice(0, 10);
  if (!rawDate) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const fiveDays = new Date(today);
  fiveDays.setDate(today.getDate() + 5);
  const due = new Date(`${rawDate}T00:00:00`);
  return Number.isFinite(due.getTime()) && due >= today && due <= fiveDays;
}

function availableCompetencias() {
  return availableCompetenciasForItems(state.items);
}

function monthItems() {
  return monthItemsForCompetencia(state.items, state.selectedCompetencia);
}

function competenciaCount(competencia) {
  return competenciaItemCount(state.items, competencia);
}

function syncCompetenciaMenuState() {
  els.competenciaTriggerBtn?.setAttribute("aria-expanded", String(state.competenciaMenuOpen));
  els.competenciaMenu?.classList.toggle("hidden", !state.competenciaMenuOpen);
}

function closeCompetenciaMenu() {
  state.competenciaMenuOpen = false;
  syncCompetenciaMenuState();
}

function renderCompetenciaPicker() {
  const competencias = availableCompetencias();
  if (!competencias.includes(state.selectedCompetencia)) {
    state.selectedCompetencia = competencias[0] || currentCompetencia();
  }

  const selectedLabel = competenciaLabel(state.selectedCompetencia);
  const selectedCount = competenciaCount(state.selectedCompetencia);
  const groups = competencias.reduce((map, competencia) => {
    const [year] = competencia.split("-");
    if (!map.has(year)) map.set(year, []);
    map.get(year).push(competencia);
    return map;
  }, new Map());

  els.competenciaTriggerLabel.textContent = selectedLabel;
  els.competenciaTriggerCount.textContent = pluralAcordos(selectedCount);
  if (els.focusCompetencia) els.focusCompetencia.textContent = selectedLabel;
  if (els.focusRecords) els.focusRecords.textContent = pluralAcordos(selectedCount);
  els.currentCompetenciaBtn.disabled = state.selectedCompetencia === currentCompetencia();
  els.competenciaMenu.innerHTML = [...groups.entries()].map(([year, yearCompetencias]) => `
    <div class="competencia-year">${year}</div>
    ${yearCompetencias.map((competencia) => {
      const count = competenciaCount(competencia);
      const isCurrent = competencia === currentCompetencia();
      const active = competencia === state.selectedCompetencia ? "active" : "";
      return `
        <button class="competencia-option ${active}" type="button" data-competencia="${competencia}" role="menuitem">
          <span>${competenciaLabel(competencia)}</span>
          <small>${pluralAcordos(count)}${isCurrent ? " - atual" : ""}</small>
        </button>
      `;
    }).join("")}
  `).join("");
  syncCompetenciaMenuState();
}

function renderStats() {
  els.stats.classList.add("production-summary");
  els.stats.classList.toggle("production-summary-collapsed", state.summaryCollapsed);
  els.stats.innerHTML = renderProductionMetrics({
    items: monthItems(),
    competencia: state.selectedCompetencia,
    metaPagamento: state.monthlyGoals[state.selectedCompetencia] ?? state.metaPagamento,
    isAlpha: isAlpha(),
  });
  const toggleLabel = els.summaryToggleBtn?.querySelector("[data-summary-toggle-label]");
  if (toggleLabel) {
    toggleLabel.textContent = state.summaryCollapsed ? "Expandir resumo" : "Recolher resumo";
  }
  els.summaryToggleBtn?.setAttribute("aria-expanded", String(!state.summaryCollapsed));
}

function toggleSummaryView() {
  state.summaryCollapsed = !state.summaryCollapsed;
  localStorage.setItem("negocial.producaoSummaryCollapsed", state.summaryCollapsed ? "1" : "0");
  renderStats();
}

function renderAttentionBar() {
  if (!els.attentionBar) return;
  const items = monthItems();
  const countStatus = (status) => items.filter((item) => item.status === status).length;
  const nearDue = items.filter(isItemNearDue).length;
  const entries = [
    { label: "Correcoes do backoffice", value: state.corrections.length, corrections: true, tone: "danger" },
    { label: "Aguardando pagamento", value: countStatus("AGUARDANDO_PAGAMENTO"), status: "AGUARDANDO_PAGAMENTO", tone: "warning" },
    { label: "Propostas abertas", value: countStatus("PROPOSTA"), status: "PROPOSTA", tone: "" },
    { label: "Vencem em 5 dias", value: nearDue, due: true, tone: nearDue ? "danger" : "" },
  ];
  const visible = entries.filter((entry) => entry.value > 0);
  els.attentionBar.classList.toggle("hidden", !visible.length);
  els.attentionBar.innerHTML = visible.length ? `
    <span class="production-attention-label">Atenção</span>
    ${visible.map((entry) => `
      <button class="production-attention-chip ${entry.tone} ${entry.due && state.attentionFilter === "near-due" ? "active" : ""}" type="button" ${entry.status ? `data-attention-status="${entry.status}"` : ""} ${entry.corrections ? "data-attention-corrections" : ""} ${entry.due ? "data-attention-due" : ""}>
        <span>${entry.label}</span><strong>${entry.value}</strong>
      </button>
    `).join("")}
  ` : "";
}

function setProductionFocusMode(enabled) {
  state.focusMode = Boolean(enabled);
  document.querySelector(".app-shell")?.classList.toggle("production-focus-mode", state.focusMode);
  document.body.classList.toggle("production-focus-active", state.focusMode);
  els.focusHeader?.setAttribute("aria-hidden", String(!state.focusMode));
  els.expandBtn.textContent = state.focusMode ? "Sair do foco" : "Modo foco";
  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(() => {
      renderTable();
      window.dispatchEvent(new Event("resize"));
    });
  });
}

function toggleProductionFocusMode() {
  setProductionFocusMode(!state.focusMode);
}

function cycleCompetencia(direction) {
  const competencias = availableCompetencias();
  if (!competencias.length) return;
  const currentIndex = Math.max(0, competencias.indexOf(state.selectedCompetencia));
  const nextIndex = Math.min(competencias.length - 1, Math.max(0, currentIndex + direction));
  if (nextIndex === currentIndex) return;
  state.selectedCompetencia = competencias[nextIndex];
  closeCompetenciaMenu();
  render();
}

function gridPersistKey(scope = "principal") {
  const user = String(state.user?.username || "anonimo").toLowerCase();
  const carteira = currentCarteira() || "GAMMA";
  const schemaType = state.schema?.tipo || "padrao";
  return `negocial:producao:${scope}:${user}:${carteira}:${schemaType}`;
}

function renderTable() {
  const items = filteredItems();
  if (!state.grid) {
    state.grid = createExcelGrid(els.grid, {
      id: "producaoGrid",
      persistKey: gridPersistKey("principal"),
      filters: true,
      emptyActionLabel: "Cadastrar primeiro acordo",
      onEmptyAction: () => openDialog(),
      onSelectionChange: updateFocusSelectionSummary,
      onError: (error) => window.alert(error.message || "Nao foi possivel salvar a celula."),
    });
  }
  state.grid.render(items, producaoColumns(), { preservePosition: true });
  updateFocusSelectionSummary({ cells: state.grid.getSelectedCells?.() || [] });
  renderExpandedGrid();
}

function renderExpandedGrid() {
  if (!els.expandedDialog?.open) return;
  if (!state.expandedGrid) {
    state.expandedGrid = createExcelGrid(els.expandedGrid, {
      id: "producaoExpandedGrid",
      persistKey: gridPersistKey("expandida"),
      filters: true,
      onSelectionChange: updateExpandedSelectionSummary,
      onError: (error) => window.alert(error.message || "Nao foi possivel salvar a celula."),
    });
  }
  const items = filteredItems();
  els.expandedTitle.textContent = competenciaLabel(state.selectedCompetencia);
  state.expandedGrid.render(items, producaoColumns(), { preservePosition: true });
  updateExpandedSelectionSummary({ cells: state.expandedGrid.getSelectedCells?.() || [] });
}

function openExpandedGrid() {
  if (!els.expandedDialog) return;
  els.expandedDialog.showModal();
  renderExpandedGrid();
}

function closeExpandedGrid() {
  els.expandedDialog?.close();
}

function render() {
  renderCompetenciaPicker();
  renderStats();
  renderAttentionBar();
  renderTable();
}

export function canAutoRefreshProducao() {
  return Boolean(
    state.initialized
      && !els.dialog?.open
      && els.statusJustificativaDialog?.classList.contains("hidden")
      && els.pagamentoDialog?.classList.contains("hidden"),
  );
}

export async function loadProducao(options = {}) {
  const silent = Boolean(options.silent);
  if (!silent) {
    els.grid.innerHTML = `
      <div class="excel-grid-loading">
        <div class="table-loading skeleton"></div>
        <div class="table-loading skeleton"></div>
        <div class="table-loading skeleton"></div>
      </div>
    `;
  }
  await ensureProductionSchema();
  const data = await apiGet("/api/producao");
  state.items = data.items || [];
  state.monthlyGoals = data.metas || {};
  render();
}

async function submitProducaoPayload() {
  const payload = payloadFromForm();
  if (state.editingId) {
    await apiPut(`/api/producao/${state.editingId}`, payload);
    if (state.moveStatusToNextMonth && payload.status === "QUEBRA") {
      await saveStatusChange(state.editingId, payload.status, payload.justificativa_status, null, { jogarProximoMes: true });
    }
  } else {
    await apiPost("/api/producao", payload);
  }
  state.moveStatusToNextMonth = false;
  state.formalizadoNovoAcordo = false;
  await loadProducao();
}

async function saveProducao(event) {
  event.preventDefault();
  clearError();
  updateFinancialRules();

  if (!validateStepOne() || !validateFinancialFields() || !els.form.reportValidity()) {
    return;
  }

  const statusValue = currentFormStatus();
  if (criticalStatuses.has(statusValue) && !els.justificativa.value.trim()) {
    openFormSaveJustificativaDialog(statusValue);
    return;
  }

  if (statusValue === paymentStatus && !els.dataPagamento.value) {
    openFormSavePaymentDialog(statusValue);
    return;
  }

  els.saveBtn.disabled = true;
  els.saveBtn.textContent = "Salvando...";
  try {
    await submitProducaoPayload();
    closeDialog();
  } catch (error) {
    showError(error.message);
  } finally {
    els.saveBtn.disabled = false;
    els.saveBtn.textContent = "Salvar";
  }
}

async function handleTableClick(event) {
  const button = event.target.closest("[data-action]");
  if (!button) return;

  const id = Number(button.dataset.id);
  const item = state.items.find((entry) => entry.id === id);
  if (!item) return;
  if (itemCompetencia(item) < currentCompetencia()) {
    window.alert("Competencias anteriores estao disponiveis somente para consulta.");
    return;
  }

  if (button.dataset.action === "edit") {
    openDialog(item);
    return;
  }

}

function openStatusPaymentDialog(...args) {
  return statusDialogs.openStatusPaymentDialog(...args);
}

function openFormSavePaymentDialog(...args) {
  return statusDialogs.openFormSavePaymentDialog(...args);
}

function openFormPaymentDialog(...args) {
  return statusDialogs.openFormPaymentDialog(...args);
}

function openStatusJustificativaDialog(...args) {
  return statusDialogs.openStatusJustificativaDialog(...args);
}

function openFormJustificativaDialog(...args) {
  return statusDialogs.openFormJustificativaDialog(...args);
}

function openFormSaveJustificativaDialog(...args) {
  return statusDialogs.openFormSaveJustificativaDialog(...args);
}

function cancelStatusJustificativa(...args) {
  return statusDialogs.cancelStatusJustificativa(...args);
}

function cancelPaymentDate(...args) {
  return statusDialogs.cancelPaymentDate(...args);
}

function submitPaymentDate(...args) {
  return statusDialogs.submitPaymentDate(...args);
}

function submitStatusJustificativa(...args) {
  return statusDialogs.submitStatusJustificativa(...args);
}
async function saveStatusChange(id, statusValue, justificativa = null, dataPagamento = null, options = {}) {
  const response = await apiPatch(`/api/producao/${id}/status`, {
    status: statusValue,
    justificativa_status: justificativa,
    data_pagamento: dataPagamento,
    jogar_proximo_mes: Boolean(options.jogarProximoMes),
    formalizado_novo_acordo: Boolean(options.formalizadoNovoAcordo),
  });
  const index = state.items.findIndex((entry) => entry.id === id);
  if (index >= 0) {
    state.items[index] = response.item;
  }
  renderCompetenciaPicker();
  renderStats();
  renderAttentionBar();
  state.grid?.updateRow?.(response.item);
  state.expandedGrid?.updateRow?.(response.item);
  return response.item;
}

function applyCarteiraLayout() {
  if (els.search) {
    els.search.placeholder = "Pesquisar em todas as colunas";
  }
  updateFinancialRules();
}

async function handleStatusSelectChange(event) {
  const select = event.target.closest("[data-action='status']");
  if (!select) return;
  await handleStatusSelectElement(select);
}

async function handleStatusSelectElement(select) {
  if (state.pendingStatusChange || state.pendingPaymentChange) return;

  const id = Number(select.dataset.id);
  const item = state.items.find((entry) => entry.id === id);
  if (!item) return;
  if (itemCompetencia(item) < currentCompetencia()) {
    select.value = item.status;
    window.alert("Competencias anteriores estao disponiveis somente para consulta.");
    return;
  }

  const currentStatus = normalizeStatusValue(item.status, item.status);
  const nextStatus = normalizeStatusValue(select.value, currentStatus);
  if (nextStatus === currentStatus) return;

  if (criticalStatuses.has(nextStatus)) {
    select.blur();
    openStatusJustificativaDialog(item, nextStatus, select);
    return;
  }

  const formalizationTransition = criticalStatuses.has(currentStatus)
    && ["AGUARDANDO_PAGAMENTO", paymentStatus].includes(nextStatus);
  if (nextStatus === paymentStatus || formalizationTransition) {
    select.blur();
    openStatusPaymentDialog(item, nextStatus, select);
    return;
  }

  select.disabled = true;
  try {
    await saveStatusChange(id, nextStatus, null);
  } catch (error) {
    select.value = item.status;
    window.alert(error.message);
  } finally {
    select.disabled = false;
  }
}

export function initProducao(user = null) {
  if (state.initialized) return;
  state.initialized = true;
  state.metaPagamento = Number(user?.meta_pagamento ?? state.metaPagamento ?? 70000);
  state.carteira = String(user?.carteira || "GAMMA").trim().toUpperCase();
  state.user = user;

  Object.assign(els, {
    dialog: qs("#producaoDialog"),
    form: qs("#producaoForm"),
    title: qs("#producaoDialogTitle"),
    id: qs("#producaoId"),
    dataPagamento: qs("#producaoDataPagamento"),
    justificativa: qs("#producaoJustificativa"),
    flex: qs("#producaoFlex"),
    flexField: qs("#flexField"),
    percentual: qs("#percentualHo"),
    percentualCard: qs("#percentualCard"),
    flexHint: qs("#flexHint"),
    dynamicStepOne: qs("#dynamicStepOneFields"),
    dynamicStepTwo: qs("#dynamicStepTwoFields"),
    nextMonthField: qs("#nextMonthField"),
    nextMonth: qs("#producaoNextMonth"),
    nextMonthHint: qs("#nextMonthHint"),
    error: qs("#producaoError"),
    backBtn: qs("#backProducaoStepBtn"),
    nextBtn: qs("#nextProducaoStepBtn"),
    saveBtn: qs("#saveProducaoBtn"),
    cancelBtn: qs("#cancelProducaoBtn"),
    closeBtn: qs("#closeProducaoDialogBtn"),
    openBtn: qs("#openProducaoDialogBtn"),
    summaryToggleBtn: qs("#summaryToggleBtn"),
    expandBtn: qs("#expandProducaoGridBtn"),
    exitFocusBtn: qs("#exitProductionFocusBtn"),
    focusHeader: qs("#productionFocusHeader"),
    focusCompetencia: qs("#productionFocusCompetencia"),
    focusRecords: qs("#productionFocusRecords"),
    focusSelection: qs("#productionFocusSelection"),
    attentionBar: qs("#producaoAttentionBar"),
    shortcutsBtn: qs("#productionShortcutsBtn"),
    shortcutsDialog: qs("#productionShortcutsDialog"),
    closeShortcutsBtn: qs("#closeProductionShortcutsBtn"),
    grid: qs("#producaoGrid"),
    expandedDialog: qs("#producaoExpandedDialog"),
    expandedGrid: qs("#producaoExpandedGrid"),
    expandedTitle: qs("#producaoExpandedTitle"),
    expandedSummary: qs("#producaoExpandedSummary"),
    closeExpandedBtn: qs("#closeProducaoExpandedBtn"),
    stats: qs("#producaoStats"),
    competenciaTriggerBtn: qs("#competenciaTriggerBtn"),
    competenciaTriggerLabel: qs("#competenciaTriggerLabel"),
    competenciaTriggerCount: qs("#competenciaTriggerCount"),
    competenciaMenu: qs("#competenciaMenu"),
    currentCompetenciaBtn: qs("#currentCompetenciaBtn"),
    search: qs("#producaoSearch"),
    statusJustificativaDialog: qs("#statusJustificativaDialog"),
    statusJustificativaForm: qs("#statusJustificativaForm"),
    statusJustificativaTitle: qs("#statusJustificativaTitle"),
    statusJustificativaTexto: qs("#statusJustificativaTexto"),
    statusNextMonthField: qs("#statusNextMonthField"),
    statusNextMonth: qs("#statusNextMonth"),
    statusNextMonthHint: qs("#statusNextMonthHint"),
    statusJustificativaError: qs("#statusJustificativaError"),
    statusJustificativaSaveBtn: qs("#saveStatusJustificativaBtn"),
    statusJustificativaCloseBtn: qs("#closeStatusJustificativaBtn"),
    statusJustificativaCancelBtn: qs("#cancelStatusJustificativaBtn"),
    pagamentoDialog: qs("#pagamentoDialog"),
    pagamentoForm: qs("#pagamentoForm"),
    pagamentoTitle: qs("#pagamentoTitle"),
    pagamentoDataField: qs("#pagamentoDataField"),
    pagamentoData: qs("#pagamentoData"),
    formalizacaoNovoAcordoField: qs("#formalizacaoNovoAcordoField"),
    formalizacaoNovoAcordo: qs("#formalizacaoNovoAcordo"),
    pagamentoError: qs("#pagamentoError"),
    pagamentoSaveBtn: qs("#savePagamentoBtn"),
    pagamentoCloseBtn: qs("#closePagamentoBtn"),
    pagamentoCancelBtn: qs("#cancelPagamentoBtn"),
  });
  bindDynamicFormEvents();
  statusDialogs = createStatusDialogs({
    state,
    els,
    statusLabels,
    todayInputValue,
    submitProducaoPayload,
    saveStatusChange,
    closeDialog,
    clearError,
    updateFinancialRules,
    setFormStatusValue,
    canMoveToNextMonth,
    nextCompetenciaDisplay,
  });
  applyCarteiraLayout();

  els.openBtn.addEventListener("click", () => { void openDialog(); });
  els.expandBtn?.addEventListener("click", toggleProductionFocusMode);
  els.exitFocusBtn?.addEventListener("click", () => setProductionFocusMode(false));
  els.attentionBar?.addEventListener("click", (event) => {
    if (event.target.closest("[data-attention-corrections]")) {
      qs("#correctionAlertBtn")?.click();
      return;
    }
    if (event.target.closest("[data-attention-due]")) {
      state.grid?.clearFilters();
      state.attentionFilter = state.attentionFilter === "near-due" ? null : "near-due";
      renderAttentionBar();
      renderTable();
      return;
    }
    const status = event.target.closest("[data-attention-status]")?.dataset.attentionStatus;
    if (!status) return;
    state.attentionFilter = null;
    renderAttentionBar();
    state.grid?.clearFilters();
    state.grid?.setColumnFilter("status", [statusLabels[status] || status]);
  });
  els.shortcutsBtn?.addEventListener("click", () => els.shortcutsDialog?.showModal());
  els.closeShortcutsBtn?.addEventListener("click", () => els.shortcutsDialog?.close());
  els.closeExpandedBtn?.addEventListener("click", closeExpandedGrid);
  els.closeBtn.addEventListener("click", closeDialog);
  els.cancelBtn.addEventListener("click", closeDialog);
  els.nextBtn.addEventListener("click", () => {
    if (validateStepOne()) setStep(2);
  });
  els.backBtn.addEventListener("click", () => setStep(1));
  els.form.addEventListener("submit", saveProducao);
  els.saveBtn.addEventListener("click", (event) => {
    if (state.step !== 2) return;
    const statusValue = currentFormStatus();
    if (
      (!criticalStatuses.has(statusValue) || els.justificativa.value.trim())
      && (statusValue !== paymentStatus || els.dataPagamento.value)
    ) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    clearError();

    if (!validateStepOne() || !validateFinancialFieldsWithoutStatus()) {
      return;
    }

    if (criticalStatuses.has(statusValue) && !els.justificativa.value.trim()) {
      openFormSaveJustificativaDialog(statusValue);
      return;
    }

    openFormSavePaymentDialog(statusValue);
  }, true);
  const handleFormStatusChange = (value) => {
    state.formalizadoNovoAcordo = false;
    const nextStatus = setFormStatusValue(value);
    if (!criticalStatuses.has(nextStatus)) {
      els.justificativa.value = "";
    }
    if (nextStatus !== paymentStatus) {
      els.dataPagamento.value = "";
    }

    if (criticalStatuses.has(nextStatus) && nextStatus !== state.previousFormStatus) {
      els.justificativa.value = "";
      if (!validateStepOne() || !validateFinancialFieldsWithoutStatus()) {
        setFormStatusValue(state.previousFormStatus);
        updateFinancialRules();
        return;
      }
      openFormSaveJustificativaDialog(nextStatus);
      return;
    }

    const formalizationTransition = criticalStatuses.has(state.previousFormStatus)
      && ["AGUARDANDO_PAGAMENTO", paymentStatus].includes(nextStatus);
    if ((nextStatus === paymentStatus || formalizationTransition) && nextStatus !== state.previousFormStatus) {
      openFormPaymentDialog(nextStatus);
      return;
    }
    updateFinancialRules();
  };
  els.form.addEventListener("input", (event) => {
    if (event.target.matches?.("[data-dynamic-field]")) {
      normalizeDynamicInput(event.target);
      updateFinancialRules();
    }
  });
  els.form.addEventListener("focusout", (event) => {
    const input = event.target.closest?.("[data-dynamic-field]");
    if (!input) return;
    const column = dynamicColumns().find((item) => item.chave === input.dataset.dynamicField);
    if (column?.tipo !== "moeda") return;
    input.value = normalizeMoneyText(input.value);
    updateFinancialRules();
  });
  els.form.addEventListener("change", (event) => {
    const field = event.target.closest?.("[data-dynamic-field]");
    if (!field) return;
    if (field.dataset.dynamicField === "STATUS") {
      handleFormStatusChange(field.value);
      return;
    }
    updateFinancialRules();
  });
  els.grid.addEventListener("click", handleTableClick);
  els.expandedGrid?.addEventListener("click", handleTableClick);
  els.summaryToggleBtn?.addEventListener("click", toggleSummaryView);
  els.competenciaTriggerBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    state.competenciaMenuOpen = !state.competenciaMenuOpen;
    syncCompetenciaMenuState();
  });
  els.competenciaMenu.addEventListener("click", (event) => {
    const button = event.target.closest("[data-competencia]");
    if (!button) return;
    state.selectedCompetencia = button.dataset.competencia;
    closeCompetenciaMenu();
    render();
  });
  els.currentCompetenciaBtn.addEventListener("click", () => {
    state.selectedCompetencia = currentCompetencia();
    closeCompetenciaMenu();
    render();
  });
  els.search?.addEventListener("input", renderTable);
  els.statusJustificativaForm.addEventListener("submit", submitStatusJustificativa);
  els.statusJustificativaCloseBtn.addEventListener("click", cancelStatusJustificativa);
  els.statusJustificativaCancelBtn.addEventListener("click", cancelStatusJustificativa);
  els.pagamentoForm.addEventListener("submit", submitPaymentDate);
  els.pagamentoCloseBtn.addEventListener("click", cancelPaymentDate);
  els.pagamentoCancelBtn.addEventListener("click", cancelPaymentDate);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !els.statusJustificativaDialog.classList.contains("hidden")) {
      cancelStatusJustificativa();
    }
    if (event.key === "Escape" && !els.pagamentoDialog.classList.contains("hidden")) {
      cancelPaymentDate();
    }
    if (event.key === "Escape" && state.competenciaMenuOpen) {
      closeCompetenciaMenu();
    }
    if (event.key === "Escape" && state.focusMode) {
      setProductionFocusMode(false);
    }

    const productionVisible = !qs("#producaoPage")?.classList.contains("hidden");
    const typing = event.target instanceof HTMLInputElement
      || event.target instanceof HTMLTextAreaElement
      || event.target instanceof HTMLSelectElement;
    if (!productionVisible || typing || els.dialog?.open || els.shortcutsDialog?.open) return;

    if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === "n") {
      event.preventDefault();
      openDialog();
    }
    if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === "f") {
      event.preventDefault();
      toggleProductionFocusMode();
    }
    if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === "l") {
      event.preventDefault();
      state.grid?.clearFilters();
    }
    if (event.altKey && event.key === "ArrowUp") {
      event.preventDefault();
      cycleCompetencia(-1);
    }
    if (event.altKey && event.key === "ArrowDown") {
      event.preventDefault();
      cycleCompetencia(1);
    }
  });
  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;
    if (state.competenciaMenuOpen && !event.target.closest(".competencia-picker")) {
      closeCompetenciaMenu();
    }
  });
  document.addEventListener("negocial:correcoes", (event) => {
    state.corrections = Array.isArray(event.detail?.items) ? event.detail.items : [];
    renderAttentionBar();
    if (state.grid) renderTable();
  });

  window.negocialProducaoStatusChange = (select) => {
    handleStatusSelectElement(select).catch((error) => window.alert(error.message));
  };
}


