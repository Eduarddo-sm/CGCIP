import { api } from "../core/api.js";
import { $ } from "../core/dom.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { state } from "../core/state.js";
import { toast } from "../core/toast.js";
import { NON_EDITABLE_HEADERS, REASON_HEADERS, MONTHS } from "./monitorPlanilhaConstants.js?v=20260713-gerencial-edit-all-1";
import { fillReportDateFilters, fillReportDays } from "./monitorPlanilhaReport.js?v=20260825-report-periods-1";
import {
  clearMonitorPlanilhaExcelFilters,
  renderMonitorPlanilhaExcel,
  renderMonitorPlanilhaExcelEmpty,
  renderMonitorPlanilhaExpandedExcel,
} from "./monitorPlanilhaExcel.js?v=20260825-beta-repurchase-1";

export { downloadMonitorReport, openMonitorReportDialog, updateReportFormat, updateReportNegotiators, updateReportScope } from "./monitorPlanilhaReport.js?v=20260825-report-periods-1";



export function initMonitorPlanilha() {
  fillDateFilters();
  fillReportDateFilters();
  fillReportDays();
  bindMonitorPlanilhaShortcuts();
  bindMonitorClientForm();
}

export async function loadMonitorPlanilha() {
  const carteira = $("#monitorPlanilhaCarteira")?.value || "";
  const mes = $("#monitorPlanilhaMes")?.value || "";
  const ano = $("#monitorPlanilhaAno")?.value || "";

  if (!carteira) {
    state.monitorPlanilha.data = null;
    updateMonitorPlanilhaContext(null);
    renderMonitorPlanilhaExcelEmpty("Selecione uma carteira para carregar a producao mensal.");
    return;
  }

  updateMonitorPlanilhaContext(null, { loading: true, carteira, mes, ano });
  $("#monitorPlanilhaTable").innerHTML = `<div class="empty-overview">Carregando dados da producao...</div>`;
  try {
    const payload = await api(`/api/monitoramento/planilha?carteira=${encodeURIComponent(carteira)}&mes=${encodeURIComponent(mes)}&ano=${encodeURIComponent(ano)}`);
    state.monitorPlanilha.data = payload;
    updateMonitorPlanilhaContext(payload);
    renderMonitorPlanilhaExcel(payload, {
      onSave: saveMonitorPlanilhaCell,
      onDelete: deleteMonitorPlanilhaAgreement,
    });
  } catch (error) {
    updateMonitorPlanilhaContext(null, { error: true, carteira, mes, ano });
    renderMonitorPlanilhaExcelEmpty(error.message || "Nao foi possivel carregar a producao mensal.");
  }
}

function updateMonitorPlanilhaContext(payload, options = {}) {
  const title = $("#monitorPlanilhaContext");
  const updated = $("#monitorPlanilhaUpdatedAt");
  if (!title || !updated) return;
  const carteira = String(payload?.carteira || options.carteira || $("#monitorPlanilhaCarteira")?.value || "").toUpperCase();
  const monthNumber = Number(payload?.mes || options.mes || $("#monitorPlanilhaMes")?.value || 0);
  const year = String(payload?.ano || options.ano || $("#monitorPlanilhaAno")?.value || "");
  if (!carteira) {
    title.textContent = "Selecione uma carteira";
    updated.textContent = "Aguardando consulta";
    return;
  }
  const competence = `${MONTHS[monthNumber - 1] || "Período"} de ${year}`;
  const total = Number(payload?.rows?.length || 0);
  title.textContent = options.loading
    ? `${carteira} · ${competence}`
    : `${carteira} · ${competence} · ${total.toLocaleString("pt-BR")} registros`;
  updated.textContent = options.loading
    ? "Carregando dados..."
    : options.error
      ? "Não foi possível atualizar"
      : `Atualizado ${new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date())}`;
}

export function openMonitorPlanilhaExpanded() {
  const payload = state.monitorPlanilha.data;
  if (!payload?.rows?.length) {
    toast("Carregue a planilha antes de expandir.");
    return;
  }
  const dialog = $("#monitorPlanilhaExpandedDialog");
  if (!dialog) return;
  dialog.showModal();
  renderMonitorPlanilhaExpandedExcel(payload, {
    onSave: saveMonitorPlanilhaCell,
    onDelete: deleteMonitorPlanilhaAgreement,
  });
}

function fillDateFilters() {
  const monthSelect = $("#monitorPlanilhaMes");
  const yearSelect = $("#monitorPlanilhaAno");
  if (!monthSelect || monthSelect.dataset.ready === "true") return;

  const now = new Date();
  monthSelect.innerHTML = MONTHS.map((month, index) => `<option value="${index + 1}">${month}</option>`).join("");
  monthSelect.value = String(now.getMonth() + 1);

  const currentYear = now.getFullYear();
  const years = [];
  for (let year = currentYear - 3; year <= currentYear + 1; year += 1) years.push(year);
  yearSelect.innerHTML = years.map((year) => `<option value="${year}">${year}</option>`).join("");
  yearSelect.value = String(currentYear);
  monthSelect.dataset.ready = "true";
}

function bindMonitorPlanilhaShortcuts() {
  if (document.body.dataset.monitorPlanilhaShortcuts === "true") return;
  document.body.dataset.monitorPlanilhaShortcuts = "true";
  document.addEventListener("keydown", (event) => {
    if (!(event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "l")) return;
    if (state.mode !== "monitorPlanilha") return;
    event.preventDefault();
    clearMonitorPlanilhaFilters();
  });
}

function clearMonitorPlanilhaFilters() {
  clearMonitorPlanilhaExcelFilters(Boolean($("#monitorPlanilhaExpandedDialog")?.open));
  toast("Filtros limpos.");
}

export async function saveMonitorPlanilhaCell(info) {
  const header = info.header;
  const id = Number(info.rowKey || 0);
  if (!id || NON_EDITABLE_HEADERS.has(header)) {
    throw new Error("Esta celula nao pode ser editada.");
  }
  let motivo = "";
  if (REASON_HEADERS.has(header)) {
    motivo = window.prompt("Informe o motivo da correcao para auditoria:") || "";
    if (!motivo.trim()) throw new Error("Motivo obrigatorio para corrigir valores.");
  }
  return api("/api/monitoramento/planilha/celula", {
    method: "POST",
    body: JSON.stringify({ id, header, value: info.value, motivo }),
  });
}

export function openMonitorClientDialog() {
  const dialog = $("#monitorClientDialog");
  const form = $("#monitorClientForm");
  if (!dialog || !form) return;
  form.reset();
  form.carteira.value = $("#monitorPlanilhaCarteira")?.value || "GAMMA";
  updateMonitorClientLayout(form);
  setMonitorClientStep(form, 1);
  dialog.showModal();
}

function bindMonitorClientForm() {
  const form = $("#monitorClientForm");
  if (!form || form.dataset.bound === "true") return;
  form.dataset.bound = "true";
  form.carteira?.addEventListener("change", () => {
    updateMonitorClientLayout(form);
    setMonitorClientStep(form, 1);
  });
  form.negociador?.addEventListener("change", () => applyMonitorClientNegotiatorRule(form));
  form.tipo_acordo?.addEventListener("change", () => applyMonitorClientAgreementRules(form));
  form.status?.addEventListener("change", () => applyMonitorClientAgreementRules(form));
  $("#monitorClientNextBtn")?.addEventListener("click", () => {
    if (validateMonitorClientStep(form, 1)) setMonitorClientStep(form, 2);
  });
  $("#monitorClientBackBtn")?.addEventListener("click", () => setMonitorClientStep(form, 1));
  document.querySelectorAll("[data-monitor-client-step-target]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = Number(button.dataset.monitorClientStepTarget || 1);
      if (target === 1 || validateMonitorClientStep(form, 1)) setMonitorClientStep(form, target);
    });
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!validateMonitorClientStep(form, 2)) return;
    try {
      const data = Object.fromEntries(new FormData(form).entries());
      data.campos = collectMonitorClientDynamicFields();
      if (String(data.negociador || "").toUpperCase() === "HONORARIOS") {
        data.valor_total_acordo = "0";
      }
      await api("/api/monitoramento/planilha/cliente", {
        method: "POST",
        body: JSON.stringify(data),
      });
      $("#monitorClientDialog")?.close();
      toast("Cliente cadastrado.");
      const carteiraSelect = $("#monitorPlanilhaCarteira");
      if (carteiraSelect) carteiraSelect.value = data.carteira;
      const createdDate = String(data.data_acordo || "");
      if (/^\d{4}-\d{2}-\d{2}$/.test(createdDate)) {
        const [year, month] = createdDate.split("-");
        const monthSelect = $("#monitorPlanilhaMes");
        const yearSelect = $("#monitorPlanilhaAno");
        if (monthSelect) monthSelect.value = String(Number(month));
        if (yearSelect) yearSelect.value = year;
      }
      await loadMonitorPlanilha();
    } catch (error) {
      toast(error.message || "Nao foi possivel cadastrar o cliente.");
    }
  });
}

function updateMonitorClientLayout(form) {
  syncMonitorClientNegotiators(form);
  const carteira = String(form.carteira?.value || "").toUpperCase();
  const isGamma = carteira === "GAMMA";
  const isAlpha = carteira === "ALPHA";
  const usesSchema = Boolean(walletByCarteira(carteira)?.negocial?.modo_schema);

  $("#monitorClientGammaIdentityFields")?.classList.toggle("hidden", !isGamma);
  $("#monitorClientGammaAgreementFields")?.classList.toggle("hidden", !isGamma);
  $("#monitorClientAlphaIdentityFields")?.classList.toggle("hidden", !isAlpha);
  $("#monitorClientDynamicFields")?.classList.toggle("hidden", !usesSchema);

  const identifierLabel = $("#monitorClientIdentifierLabel");
  const input = form.npj;
  if (!identifierLabel || !input) return;
  const firstTextNode = [...identifierLabel.childNodes].find((node) => node.nodeType === Node.TEXT_NODE);
  const setIdentifier = (label, placeholder, maxLength = "") => {
    if (firstTextNode) firstTextNode.textContent = label;
    input.placeholder = placeholder;
    if (maxLength) input.maxLength = Number(maxLength);
    else input.removeAttribute("maxlength");
  };
  if (carteira === "GAMMA") setIdentifier("NPJ", "14 digitos", 14);
  else if (carteira === "ALPHA") setIdentifier("DEBIT ID", "8 digitos", 8);
  else if (carteira === "BETA") setIdentifier("SUITID", "SUITID");
  else {
    const keyColumn = dynamicIdentifierColumn(carteira);
    setIdentifier(keyColumn?.nome || "Identificador", keyColumn?.nome || "Identificador", keyColumn?.max_length || "");
  }

  form.gecor.required = isGamma;
  form.valor_ho.required = isGamma;
  form.cpf.required = isAlpha;
  form.data_primeiro_atraso.required = isAlpha;
  form.carteira_alpha.required = isAlpha;
  if (usesSchema) renderMonitorClientDynamicFields(carteira);
  else {
    const dynamicFields = $("#monitorClientDynamicFields");
    if (dynamicFields) dynamicFields.classList.add("hidden");
    const stepOneFields = $("#monitorClientDynamicStepOneFields");
    const stepTwoFields = $("#monitorClientDynamicStepTwoFields");
    if (stepOneFields) stepOneFields.innerHTML = "";
    if (stepTwoFields) stepTwoFields.innerHTML = "";
  }
  applyMonitorClientNegotiatorRule(form);
  applyMonitorClientAgreementRules(form);
}

function syncMonitorClientNegotiators(form) {
  const carteira = String(form.carteira?.value || "").toUpperCase();
  const previous = form.negociador?.value || "";
  const names = new Set();
  if (carteira === "GAMMA") {
    names.add("HONORARIOS");
    names.add("ESCRITORIO");
  }
  [...(state.configUsers?.negociadores || []), ...(state.negociadores || [])].forEach((item) => {
    const itemCarteira = String(item.carteira || "").toUpperCase();
    const username = item.username || item.negocial_username || item.nome;
    if (username && (!carteira || itemCarteira === carteira)) names.add(String(username));
  });
  const options = [...names].sort((a, b) => a.localeCompare(b, "pt-BR"));
  form.negociador.innerHTML = `<option value="">Selecione</option>${options.map((name) => `<option value="${escapeAttr(name)}">${escapeHtml(name)}</option>`).join("")}`;
  if (previous && options.includes(previous)) form.negociador.value = previous;
  else if (carteira === "GAMMA" && options.includes("HONORARIOS")) form.negociador.value = "HONORARIOS";
  else if (options.length === 1) form.negociador.value = options[0];
}

function walletByCarteira(carteira) {
  const key = String(carteira || "").toUpperCase();
  return (state.carteiras || []).find((item) => (
    String(item.nome || "").toUpperCase() === key
    || String(item.negocial?.slug || "").toUpperCase() === key
    || String(item.negocial?.nome || "").toUpperCase() === key
  ));
}

function dynamicIdentifierColumn(carteira) {
  const columns = dynamicSchemaColumns(carteira, true);
  return columns.find((column) => column.identificador) || columns[0] || null;
}

function dynamicSchemaColumns(carteira, includeHidden = false) {
  const wallet = walletByCarteira(carteira);
  const columns = wallet?.negocial?.colunas || wallet?.colunas || [];
  return columns.filter((column) => (
    (includeHidden || column.visivel !== false)
    && column.mostrar_cadastro !== false
    && !column.automatico
    && (includeHidden || !column.identificador)
    && !["NEGOCIADOR", "OPERADOR", "JUSTIFICATIVA"].includes(String(column.chave || "").toUpperCase())
    && (includeHidden || !monitorClientFieldIsAlreadyRepresented(column))
  ));
}

const MONITOR_CLIENT_REPRESENTED_FIELDS = new Set([
  "NPJ", "DEBIT_ID", "SUITID", "IDENTIFICADOR",
  "CLIENTE", "NOME", "NOME_CLIENTE", "GECOR", "UF", "DT_AJUIZAMENTO",
  "VALOR_DO_ACORDO", "VALOR_TOTAL_ACORDO", "VALOR_TOTAL", "VALOR_FECHADO",
  "VALOR_DA_ENTRADA", "VALOR_ENTRADA", "ENTRADA",
  "PARCELADO_OU_VISTA", "TIPO_DE_ACORDO", "TIPO",
  "DATA", "DATA_ACORDO", "DATA_DE_VENCIMENTO", "DATA_VENCIMENTO",
  "DATA_DO_PAGAMENTO", "DATA_PAGAMENTO", "STATUS",
  "HONORARIOS_RECEBIDOS", "HONOR_RIOS_RECEBIDOS", "H_O", "VALOR_HO",
  "AUTORIZADO", "AUTORIZACAO_FLEXIBILIZACAO",
  "CPF", "CPF_CNPJ", "CNPJ", "DATA_PRIMEIRO_ATRASO", "DATA_DO_1_ATRASO",
  "PORTFOLIO", "CARTEIRA_ALPHA",
]);

function monitorClientSchemaKey(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function monitorClientFieldIsAlreadyRepresented(column) {
  return MONITOR_CLIENT_REPRESENTED_FIELDS.has(monitorClientSchemaKey(column?.chave || column?.nome));
}

function renderMonitorClientDynamicFields(carteira) {
  const target = $("#monitorClientDynamicFields");
  const stepOneTarget = $("#monitorClientDynamicStepOneFields");
  const stepTwoTarget = $("#monitorClientDynamicStepTwoFields");
  if (!target || !stepOneTarget || !stepTwoTarget) return;
  const columns = dynamicSchemaColumns(carteira);
  if (!columns.length) {
    stepOneTarget.innerHTML = "";
    stepTwoTarget.innerHTML = "";
    stepOneTarget.classList.add("hidden");
    target.classList.add("hidden");
    return;
  }
  target.classList.remove("hidden");
  const renderField = (column) => {
    const required = column.obrigatoria ? "required" : "";
    const max = column.max_length ? `maxlength="${Number(column.max_length)}"` : "";
    const name = escapeAttr(column.chave || column.nome);
    if (column.tipo === "select") {
      const options = (column.opcoes || []).map(monitorClientOptionText).filter(Boolean);
      return `<label>${escapeHtml(column.nome)}<select data-monitor-dynamic="${name}" ${required}><option value="">Selecione</option>${options.map((option) => `<option value="${escapeAttr(option)}">${escapeHtml(option)}</option>`).join("")}</select></label>`;
    }
    if (column.tipo === "multiselect") {
      const options = (column.opcoes || []).map(monitorClientOptionText).filter(Boolean);
      return `
        <fieldset class="monitor-multiselect" data-monitor-dynamic="${name}" data-required="${column.obrigatoria ? "true" : "false"}">
          <legend>${escapeHtml(column.nome)}</legend>
          <div>
            ${options.map((option) => `<label><input type="checkbox" value="${escapeAttr(option)}"><span>${escapeHtml(option)}</span></label>`).join("") || '<span class="muted">Nenhuma opcao configurada.</span>'}
          </div>
        </fieldset>`;
    }
    const type = column.tipo === "data" ? "date" : "text";
    const inputMode = ["moeda", "numero"].includes(String(column.tipo || "").toLowerCase()) ? 'inputmode="decimal"' : "";
    return `<label>${escapeHtml(column.nome)}<input data-monitor-dynamic="${name}" type="${type}" ${required} ${max} ${inputMode} /></label>`;
  };
  const stepOne = columns.filter((column) => Number(column.cadastro_etapa || 2) === 1);
  const stepTwo = columns.filter((column) => !stepOne.includes(column));
  stepOneTarget.innerHTML = stepOne.map(renderField).join("");
  stepTwoTarget.innerHTML = stepTwo.map(renderField).join("");
  stepOneTarget.classList.toggle("hidden", stepOne.length === 0);
  target.classList.toggle("hidden", stepTwo.length === 0);
}

function monitorClientOptionText(option) {
  if (option && typeof option === "object") {
    return String(option.value ?? option.label ?? option.nome ?? option.name ?? option.text ?? "").trim();
  }
  return String(option ?? "").trim();
}

function collectMonitorClientDynamicFields() {
  const fields = {};
  document.querySelectorAll("#monitorClientForm [data-monitor-dynamic]").forEach((input) => {
    if (input.classList.contains("monitor-multiselect")) {
      const selected = [...input.querySelectorAll("input:checked")].map((option) => option.value);
      if (input.dataset.required === "true" && selected.length === 0) {
        throw new Error(`Selecione ao menos uma opcao em ${input.querySelector("legend")?.textContent || "selecao multipla"}.`);
      }
      fields[input.dataset.monitorDynamic] = selected;
      return;
    }
    fields[input.dataset.monitorDynamic] = input.value;
  });
  return fields;
}

function applyMonitorClientNegotiatorRule(form) {
  const isHonorarios = String(form.negociador?.value || "").toUpperCase() === "HONORARIOS";
  if (isHonorarios) {
    form.valor_total_acordo.value = "0,00";
    form.valor_total_acordo.readOnly = true;
  } else {
    form.valor_total_acordo.readOnly = false;
    if (form.valor_total_acordo.value === "0,00") form.valor_total_acordo.value = "";
  }
}

async function deleteMonitorPlanilhaAgreement(info) {
  const id = Number(info?.id || 0);
  if (!id) return;
  const cliente = String(info?.cliente || "este acordo").trim() || "este acordo";
  const motivo = window.prompt(`Motivo para deletar definitivamente ${cliente}:`);
  if (!motivo) return;
  const confirmacao = window.prompt("Digite CONFIRMAR para deletar este acordo:");
  if (String(confirmacao || "").toUpperCase() !== "CONFIRMAR") return;
  try {
    await api("/api/monitoramento/planilha/deletar", {
      method: "POST",
      body: JSON.stringify({ id, motivo, confirmacao }),
    });
    toast("Acordo deletado.");
    await loadMonitorPlanilha();
  } catch (error) {
    toast(error.message || "Nao foi possivel deletar o acordo.");
  }
}

function applyMonitorClientAgreementRules(form) {
  const isAtSight = String(form.tipo_acordo?.value || "").toUpperCase() === "A_VISTA";
  const entryLabel = $("#monitorClientEntryLabel");
  entryLabel?.classList.toggle("hidden", isAtSight);
  if (form.valor_entrada) {
    form.valor_entrada.disabled = isAtSight;
    if (isAtSight) form.valor_entrada.value = "0";
    else if (form.valor_entrada.value === "0") form.valor_entrada.value = "";
  }

  const isPaid = String(form.status?.value || "").toUpperCase() === "PAGAMENTO_REALIZADO";
  const paymentLabel = $("#monitorClientPaymentDateLabel");
  paymentLabel?.classList.toggle("hidden", !isPaid);
  if (form.data_pagamento) {
    form.data_pagamento.disabled = !isPaid;
    form.data_pagamento.required = isPaid;
    if (!isPaid) form.data_pagamento.value = "";
  }
}

function setMonitorClientStep(form, step) {
  const activeStep = Number(step) === 2 ? 2 : 1;
  form.dataset.currentStep = String(activeStep);
  document.querySelectorAll("[data-monitor-client-step]").forEach((panel) => {
    panel.classList.toggle("hidden", Number(panel.dataset.monitorClientStep) !== activeStep);
  });
  document.querySelectorAll("[data-monitor-client-step-target]").forEach((button) => {
    const buttonStep = Number(button.dataset.monitorClientStepTarget || 1);
    button.classList.toggle("active", buttonStep === activeStep);
    button.classList.toggle("complete", buttonStep < activeStep);
    button.setAttribute("aria-current", buttonStep === activeStep ? "step" : "false");
  });
  $("#monitorClientBackBtn")?.classList.toggle("hidden", activeStep === 1);
  $("#monitorClientNextBtn")?.classList.toggle("hidden", activeStep === 2);
  $("#monitorClientSubmitBtn")?.classList.toggle("hidden", activeStep !== 2);
}

function validateMonitorClientStep(form, step) {
  const panel = form.querySelector(`[data-monitor-client-step="${Number(step)}"]`);
  if (!panel) return true;
  const controls = [...panel.querySelectorAll("input, select, textarea")]
    .filter((control) => !control.disabled && !control.closest(".hidden"));
  const invalid = controls.find((control) => !control.checkValidity());
  if (invalid) {
    invalid.reportValidity();
    invalid.focus();
    return false;
  }
  const requiredMultiselect = [...panel.querySelectorAll(".monitor-multiselect[data-required='true']")]
    .find((field) => !field.querySelector("input:checked"));
  if (requiredMultiselect) {
    toast(`Selecione ao menos uma opcao em ${requiredMultiselect.querySelector("legend")?.textContent || "selecao multipla"}.`);
    requiredMultiselect.scrollIntoView({ block: "center", behavior: "smooth" });
    return false;
  }
  return true;
}






