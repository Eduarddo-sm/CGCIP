import { escapeHtml } from "../core/html.js";
import { state } from "../core/state.js";
import { toast } from "../core/toast.js";
import { closeDialog } from "../layout/dialogs.js";
import { MONTHS } from "./monitorPlanilhaConstants.js";

export function fillReportDateFilters() {
  const form = document.querySelector("#monitorReportForm");
  if (!form || form.dataset.ready === "true") return;
  const now = new Date();
  const currentYear = now.getFullYear();
  const years = [];
  for (let year = 2000; year <= currentYear + 1; year += 1) years.push(year);
  setupReportPeriodPicker(form, "month", MONTHS.map((label, index) => ({ value: String(index + 1), label })));
  setupReportPeriodPicker(form, "year", years.reverse().map((year) => ({ value: String(year), label: String(year) })));
  setReportPeriodSelection(form, "month", [String(now.getMonth() + 1)]);
  setReportPeriodSelection(form, "year", [String(currentYear)]);
  form.dataset.ready = "true";
}

export function fillReportDays() {
  const form = document.querySelector("#monitorReportForm");
  if (!form || form.dia.dataset.ready === "true") return;
  form.dia.innerHTML = `<option value="">Todos os dias</option>${Array.from({ length: 31 }, (_, index) => {
    const day = String(index + 1).padStart(2, "0");
    return `<option value="${day}">${day}</option>`;
  }).join("")}`;
  form.dia.dataset.ready = "true";
}

export function openMonitorReportDialog() {
  const dialog = document.querySelector("#monitorReportDialog");
  const form = document.querySelector("#monitorReportForm");
  if (!dialog || !form) return;
  form.carteira.value = document.querySelector("#monitorPlanilhaCarteira")?.value || "";
  setReportPeriodSelection(form, "month", [document.querySelector("#monitorPlanilhaMes")?.value || String(new Date().getMonth() + 1)]);
  setReportPeriodSelection(form, "year", [document.querySelector("#monitorPlanilhaAno")?.value || String(new Date().getFullYear())]);
  form.escopo.value = "carteira";
  form.usuario.value = "";
  form.dia.value = "";
  form.querySelectorAll('input[name="report_status"]').forEach((input) => { input.checked = false; });
  if (form.formato) form.formato.value = "xlsx";
  if (form.titulo) form.titulo.value = "Acompanhamento de casos da Produção Diária";
  if (form.observacoes) form.observacoes.value = "";
  updateReportScope();
  updateReportFormat();
  updateReportNegotiators();
  if (!dialog.open) dialog.showModal();
}

export function updateReportScope() {
  const form = document.querySelector("#monitorReportForm");
  const isNegotiator = form?.escopo.value === "negociador";
  document.querySelector("#monitorReportUsuarioField")?.classList.toggle("hidden", !isNegotiator);
  if (form?.usuario) form.usuario.required = isNegotiator;
}

export function updateReportFormat() {
  const form = document.querySelector("#monitorReportForm");
  const isPdf = form?.formato?.value === "pdf";
  document.querySelector("#monitorReportPdfOptions")?.classList.toggle("hidden", !isPdf);
  document.querySelector("#monitorReportDialog")?.classList.toggle("pdf-mode", isPdf);
}

export function updateReportNegotiators() {
  const form = document.querySelector("#monitorReportForm");
  if (!form) return;
  const carteira = String(form.carteira.value || "").toUpperCase();
  const select = form.usuario;
  const users = reportNegotiators(carteira);
  select.innerHTML = `<option value="">Selecione o negociador</option>${users.map((username) => `<option value="${escapeHtml(username)}">${escapeHtml(username)}</option>`).join("")}`;
}

export async function downloadMonitorReport(event) {
  event?.preventDefault();
  const form = document.querySelector("#monitorReportForm");
  if (!form) return;
  if (!form.reportValidity()) return;

  const params = new URLSearchParams({
    carteira: form.carteira.value,
    mes: form.mes.value,
    ano: form.ano.value,
  });
  if (form.escopo.value === "negociador") params.set("usuario", form.usuario.value);
  if (form.dia.value) params.set("dia", form.dia.value);
  const selectedStatuses = [...form.querySelectorAll('input[name="report_status"]:checked')];
  if (selectedStatuses.length) params.set("status", selectedStatuses.map((input) => input.value).join(","));

  const format = ["csv", "pdf"].includes(form.formato?.value) ? form.formato.value : "xlsx";
  if (format === "pdf") {
    const selectedFields = [...form.querySelectorAll('input[name="campos"]:checked')];
    if (!selectedFields.length) {
      toast("Selecione ao menos um campo para o documento.");
      return;
    }
    if (selectedStatuses.length) {
      params.set("status_label", selectedStatuses.map((input) => input.parentElement?.textContent?.trim() || input.value).join(" + "));
    } else {
      params.set("status_label", "Todos os status");
    }
    params.set("titulo", form.titulo.value.trim());
    params.set("observacoes", form.observacoes.value.trim());
    params.set("agrupar_por", form.agrupar_por.value);
    params.set("ordenacao", form.ordenacao.value);
    params.set("orientacao", form.orientacao.value);
    params.set("campos", selectedFields.map((input) => input.value).join(","));
    if (form.quebrar_grupo.checked) params.set("quebrar_grupo", "1");
  }

  const endpoint = `/api/monitoramento/planilha/relatorio.${format}?${params.toString()}`;
  const submitButton = form.querySelector('button[type="submit"]');
  const originalLabel = submitButton?.textContent || "Gerar relatorio";

  if (submitButton) {
    submitButton.disabled = true;
    submitButton.textContent = "Gerando...";
  }

  try {
    const response = await fetch(endpoint, {
      cache: "no-store",
      headers: { Accept: format === "csv" ? "text/csv" : format === "pdf" ? "application/pdf" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
    });
    if (!response.ok) throw new Error(await reportErrorMessage(response));

    const blob = await response.blob();
    if (!blob.size) throw new Error("O relatorio foi gerado sem dados.");

    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = reportFilename(response.headers.get("Content-Disposition"), format);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 30_000);

    closeDialog("#monitorReportDialog");
    toast("Relatorio gerado com sucesso.");
  } catch (error) {
    toast(error?.message || "Nao foi possivel gerar o relatorio.");
  } finally {
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.textContent = originalLabel;
    }
  }
}

async function reportErrorMessage(response) {
  const fallback = `Nao foi possivel gerar o relatorio (erro ${response.status}).`;
  try {
    const contentType = String(response.headers.get("Content-Type") || "").toLowerCase();
    if (contentType.includes("application/json")) {
      const payload = await response.json();
      return payload?.error || payload?.message || fallback;
    }
    return (await response.text()).trim() || fallback;
  } catch {
    return fallback;
  }
}

function reportFilename(disposition, format) {
  const encodedMatch = String(disposition || "").match(/filename\*=UTF-8''([^;]+)/i);
  if (encodedMatch?.[1]) {
    try {
      return decodeURIComponent(encodedMatch[1]);
    } catch {
      // Fall through to the safe local name.
    }
  }
  return `relatorio_producao.${format}`;
}

function reportNegotiators(carteira) {
  const fromMonthlyData = (state.monitorPlanilha.data?.report?.negociadores || [])
    .map((item) => item.negociador)
    .filter(Boolean);
  const fromRegistry = (state.negociadores || [])
    .filter((item) => !carteira || String(item.carteira || "").toUpperCase() === carteira)
    .map((item) => item.negocial_username || item.nome)
    .filter(Boolean);
  return [...new Set([...fromMonthlyData, ...fromRegistry])]
    .map((item) => String(item))
    .sort((a, b) => a.localeCompare(b, "pt-BR"));
}

function setupReportPeriodPicker(form, type, options) {
  const picker = form.querySelector(`[data-report-${type}-picker]`);
  const menu = form.querySelector(`[data-report-${type}-options]`);
  if (!picker || !menu) return;
  const inputName = type === "month" ? "report_month" : "report_year";
  const allLabel = type === "month" ? "Todos os meses" : "Todos os anos";
  menu.innerHTML = `
    <label class="is-all"><input type="checkbox" data-report-period-all><span>${allLabel}</span></label>
    <div>${options.map((option) => `<label><input type="checkbox" name="${inputName}" value="${escapeHtml(option.value)}"><span>${escapeHtml(option.label)}</span></label>`).join("")}</div>`;
  menu.addEventListener("change", (event) => {
    const changed = event.target.closest("input");
    if (!changed) return;
    const items = [...menu.querySelectorAll(`input[name="${inputName}"]`)];
    if (changed.matches("[data-report-period-all]")) {
      items.forEach((item) => { item.checked = changed.checked; });
    }
    if (!items.some((item) => item.checked)) {
      if (changed.matches("[data-report-period-all]")) {
        items.forEach((item) => { item.checked = true; });
      } else {
        changed.checked = true;
      }
    }
    syncReportPeriodPicker(form, type);
  });
}

function setReportPeriodSelection(form, type, values) {
  const inputName = type === "month" ? "report_month" : "report_year";
  const menu = form.querySelector(`[data-report-${type}-options]`);
  if (!menu) return;
  const selected = new Set(values.map(String));
  menu.querySelectorAll(`input[name="${inputName}"]`).forEach((input) => {
    input.checked = selected.has(input.value);
  });
  syncReportPeriodPicker(form, type);
}

function syncReportPeriodPicker(form, type) {
  const inputName = type === "month" ? "report_month" : "report_year";
  const menu = form.querySelector(`[data-report-${type}-options]`);
  const picker = form.querySelector(`[data-report-${type}-picker]`);
  const hidden = form[type === "month" ? "mes" : "ano"];
  if (!menu || !picker || !hidden) return;
  const items = [...menu.querySelectorAll(`input[name="${inputName}"]`)];
  const selected = items.filter((item) => item.checked);
  const all = menu.querySelector("[data-report-period-all]");
  if (all) {
    all.checked = selected.length === items.length;
    all.indeterminate = selected.length > 0 && selected.length < items.length;
  }
  hidden.value = selected.length === items.length ? "todos" : selected.map((item) => item.value).join(",");
  const summary = picker.querySelector("summary span");
  if (!summary) return;
  if (selected.length === items.length) {
    summary.textContent = type === "month" ? "Todos os meses" : "Todos os anos";
  } else if (selected.length === 1) {
    summary.textContent = selected[0].parentElement?.textContent?.trim() || selected[0].value;
  } else {
    summary.textContent = `${selected.length} ${type === "month" ? "meses" : "anos"}`;
  }
}
