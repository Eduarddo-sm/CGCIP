import { api } from "../core/api.js";
import { $ } from "../core/dom.js";
import { capitalize } from "../core/format.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { setLoading, skeletonList, skeletonStats } from "../core/loading.js";
import { saveNavigationState } from "../core/navigationPersistence.js";
import { state } from "../core/state.js";
import { toast } from "../core/toast.js";
import { approveParecer, configureParecerActions, markParecer, markSelectedParecer, rejectParecer } from "./parecerActions.js?v=20260717-css-cleanup-2";
import { configureParecerView, renderMetricRows, renderParecerAprovacao, renderParecerCompleta, renderParecerPendentes } from "./parecerView.js?v=20260717-unfreeze-last-1";

export { markParecer, markSelectedParecer } from "./parecerActions.js?v=20260717-css-cleanup-2";
export { renderParecerAprovacao, renderParecerCompleta, renderParecerPendentes } from "./parecerView.js?v=20260717-unfreeze-last-1";

let refreshRunning = false;

const callbacks = {
  onPowerQueryRefresh: async () => {},
  onHubRefresh: async () => {},
};

export function configureParecer(options = {}) {
  if (typeof options.onPowerQueryRefresh === "function") {
    callbacks.onPowerQueryRefresh = options.onPowerQueryRefresh;
  }
  if (typeof options.onHubRefresh === "function") {
    callbacks.onHubRefresh = options.onHubRefresh;
  }
  configureParecerView({ markParecer, approveParecer, rejectParecer });
  configureParecerActions({
    removeParecerNotifications: options.removeParecerNotifications,
    reloadPage: loadParecerPage,
    reloadDashboard: loadParecerDashboard,
    onHubRefresh: callbacks.onHubRefresh,
  });
}

export async function downloadParecerReport() {
  const button = $("#parecerReportFullBtn");
  const originalLabel = button?.textContent || "Gerar relatório";
  if (button) {
    button.disabled = true;
    button.textContent = "Gerando...";
  }

  try {
    const response = await fetch("/api/pareceres/relatorio.csv", {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "text/csv" },
    });
    if (!response.ok) throw new Error(await parecerReportError(response));

    const blob = await response.blob();
    if (!blob.size) throw new Error("O relatório foi gerado sem dados.");

    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = parecerReportFilename(response.headers.get("Content-Disposition"));
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 30_000);
    toast("Relatório de pareceres gerado.");
  } catch (error) {
    toast(error?.message || "Não foi possível gerar o relatório de pareceres.");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalLabel;
    }
  }
}

async function parecerReportError(response) {
  const fallback = `Não foi possível gerar o relatório (erro ${response.status}).`;
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

function parecerReportFilename(disposition) {
  const encodedMatch = String(disposition || "").match(/filename\*=UTF-8''([^;]+)/i);
  if (encodedMatch?.[1]) {
    try {
      return decodeURIComponent(encodedMatch[1]);
    } catch {
      // Fall through to a stable local filename.
    }
  }
  return "relatorio_pareceres.csv";
}

export function showParecerPage(page) {
  if (page === "configuracoes") page = "dashboard";
  state.parecer.page = page;
  state.parecer.pageIndex = 1;
  if (page !== "completa") setParecerSheetFocus(false);
  saveNavigationState();
  updateParecerHeader(page);
  document.querySelectorAll("[data-parecer-page]").forEach((button) => {
    button.classList.toggle("active", button.dataset.parecerPage === page);
  });
  ["dashboard", "pendentes", "aprovacao", "completa"].forEach((name) => {
    $(`#parecer${capitalize(name)}`)?.classList.toggle("hidden", name !== page);
  });
  loadParecerPage();
}

function setParecerSheetFocus(active) {
  document.body.classList.toggle("parecer-sheet-focus-mode", active);
  const button = $("#parecerSheetFocusBtn");
  if (!button) return;
  button.setAttribute("aria-pressed", String(active));
  const label = button.querySelector("span");
  if (label) label.textContent = active ? "Sair do foco" : "Modo foco";
}

export function toggleParecerSheetFocus() {
  setParecerSheetFocus(!document.body.classList.contains("parecer-sheet-focus-mode"));
}

function updateParecerHeader(page) {
  $("#parecerContent").dataset.page = page;
}

export async function loadParecerPage() {
  if (state.mode !== "parecer") return;
  if (state.parecer.page === "configuracoes") state.parecer.page = "dashboard";
  try {
    updateParecerHeader(state.parecer.page || "dashboard");
    if (state.parecer.page === "dashboard") await loadParecerDashboard();
    if (state.parecer.page === "pendentes") await loadParecerPendentes();
    if (state.parecer.page === "aprovacao") await loadParecerAprovacao();
    if (state.parecer.page === "completa") await loadParecerCompleta();
  } catch (error) {
    toast(error.message);
  }
}

export async function loadParecerConfig() {
  state.parecer.config = await api("/api/parecer/config");
  setupParecerAutoRefresh();
}

function setupParecerAutoRefresh() {
  clearInterval(state.parecer.autoTimer);
  const minutes = Number(state.parecer.config?.auto_refresh_minutes || 0);
  if (minutes > 0) {
    state.parecer.autoTimer = setInterval(() => {
      refreshParecerPowerQuery(true);
    }, minutes * 60000);
  }
}

export async function loadParecerDashboard() {
  setLoading("#parecerStats", skeletonStats(5));
  setLoading("#parecerFlow", skeletonList(1));
  setLoading("#parecerAttention", skeletonList(3));
  setLoading("#parecerRecent", skeletonList(4));
  setLoading("#parecerByNegociador", skeletonList(3));
  setLoading("#parecerByData", skeletonList(3));
  const dashboard = await api("/api/dashboard");
  const stats = [
    { label: "Total de pareceres", value: dashboard.total, tone: "blue", icon: "file", percent: 100 },
    { label: "Aguardando aprovação", value: dashboard.aguardando_aprovacao, tone: "warn", icon: "clock", percent: percent(dashboard.aguardando_aprovacao, dashboard.total) },
    { label: "Pendentes", value: dashboard.pendentes, tone: "orange", icon: "clock", percent: percent(dashboard.pendentes, dashboard.total) },
    { label: "Solicitados", value: dashboard.solicitados, tone: "green", icon: "check", percent: percent(dashboard.solicitados, dashboard.total) },
    { label: "Reprovados", value: dashboard.reprovados, tone: "danger", icon: "file", percent: percent(dashboard.reprovados, dashboard.total) },
  ];
  $("#parecerStats").innerHTML = stats.map(renderParecerStatCard).join("");
  $("#parecerFlow").innerHTML = renderParecerFlow(dashboard);
  $("#parecerAttentionCount").textContent = String((dashboard.fila_atencao || []).length);
  $("#parecerAttention").innerHTML = renderParecerAttention(dashboard.fila_atencao || []);
  $("#parecerRecent").innerHTML = renderParecerRecent(dashboard.atividade_recente || []);
  $("#parecerByNegociador").innerHTML = renderMetricRows(dashboard.por_negociador, { filter: "negociador" });
  $("#parecerByData").innerHTML = renderMetricRows(dashboard.tendencia || dashboard.por_data);
  $("#parecerNegotiatorPanel").classList.toggle("hidden", !(dashboard.por_negociador || []).length);
  $("#parecerAnalyticsGrid").classList.toggle("single-column", !(dashboard.por_negociador || []).length);
  const updatedAt = new Date(dashboard.updated_at || "");
  $("#parecerDashboardUpdatedAt").textContent = Number.isNaN(updatedAt.getTime())
    ? ""
    : `Atualizado às ${updatedAt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
  bindParecerDashboardActions();
}

function renderParecerFlow(dashboard) {
  const stages = [
    ["Recebidos", dashboard.total, "received"],
    ["Em aprovação", dashboard.aguardando_aprovacao, "approval"],
    ["Aprovados", dashboard.aprovados, "approved"],
    ["Solicitados", dashboard.solicitados, "requested"],
  ];
  return `
    <div class="parecer-flow-track">
      ${stages.map(([label, value, tone], index) => `
        <div class="parecer-flow-stage ${escapeAttr(tone)}">
          <span>${escapeHtml(label)}</span><strong>${Number(value || 0).toLocaleString("pt-BR")}</strong>
        </div>${index < stages.length - 1 ? `<i aria-hidden="true">→</i>` : ""}
      `).join("")}
    </div>
    <div class="parecer-flow-rejected"><span>Reprovados</span><strong>${Number(dashboard.reprovados || 0).toLocaleString("pt-BR")}</strong></div>`;
}

function renderParecerAttention(items) {
  if (!items.length) {
    return `<div class="parecer-operation-ok"><span aria-hidden="true">✓</span><div><strong>Operação em dia</strong><small>Nenhum parecer exige ação no momento.</small></div></div>`;
  }
  return items.map((item) => `
    <button class="parecer-attention-item" type="button" data-parecer-dashboard-target="${escapeAttr(item.target || "pendentes")}">
      <span class="parecer-dashboard-avatar" aria-hidden="true">${escapeHtml(dashboardInitials(item.cliente))}</span>
      <span class="parecer-attention-main"><strong>${escapeHtml(item.cliente)}</strong><small>${escapeHtml(item.negociador)} · ${escapeHtml(item.motivo)}</small></span>
      <span class="parecer-attention-stage">${escapeHtml(item.acao)}</span>
      <time>${escapeHtml(item.data || "Sem data")}</time>
    </button>`).join("");
}

function renderParecerRecent(items) {
  if (!items.length) return `<div class="parecer-dashboard-empty">Nenhuma movimentação registrada.</div>`;
  return items.map((item) => `
    <div class="parecer-recent-item">
      <span class="parecer-recent-dot" aria-hidden="true"></span>
      <span><strong>${escapeHtml(item.acao)}</strong><small>${escapeHtml(item.cliente)} · ${escapeHtml(item.negociador)}</small></span>
      <time>${escapeHtml(item.data || "Sem data")}</time>
    </div>`).join("");
}

function bindParecerDashboardActions() {
  document.querySelectorAll("[data-parecer-dashboard-target]").forEach((button) => {
    button.onclick = () => showParecerPage(button.dataset.parecerDashboardTarget || "pendentes");
  });
  document.querySelectorAll("[data-parecer-dashboard-filter]").forEach((button) => {
    button.onclick = () => {
      showParecerPage("pendentes");
      const search = $("#parecerPendingSearch");
      if (search) {
        search.value = button.dataset.parecerDashboardFilter || "";
        renderParecerPendentes();
      }
    };
  });
}

function dashboardInitials(value) {
  return String(value || "C").trim().split(/\s+/).slice(0, 2).map((part) => part[0] || "").join("").toUpperCase();
}

export async function loadParecerPendentes() {
  setLoading("#parecerPendentesGrid", skeletonList(5));
  state.parecer.pendentes = await api("/api/pareceres/pendentes");
  renderParecerPendentes();
}

export async function loadParecerAprovacao() {
  setLoading("#parecerAprovacaoGrid", skeletonList(5));
  const [aprovacao, historico, todos] = await Promise.all([
    api("/api/pareceres/aprovacao"),
    api("/api/pareceres/aprovacao/historico"),
    api("/api/pareceres"),
  ]);
  state.parecer.aprovacao = aprovacao;
  state.parecer.aprovacaoHistorico = historico;
  state.parecer.aprovacaoTodos = todos;
  renderParecerAprovacao();
}

export async function loadParecerCompleta() {
  setLoading("#parecerCompletaGrid", skeletonList(6));
  state.parecer.records = await api("/api/pareceres");
  renderParecerCompleta();
}

function percent(value, total) {
  const base = Number(total || 0);
  if (!base) return 0;
  return Math.max(0, Math.min(100, Math.round((Number(value || 0) / base) * 100)));
}

function renderParecerStatCard(stat) {
  return `
    <article class="stats-card parecer-stat-card dashboard-stat-card dashboard-tone-${stat.tone} ${stat.tone}">
      <span class="parecer-stat-icon" aria-hidden="true">${parecerHeadIcon(stat.icon)}</span>
      <div>
        <span>${escapeHtml(stat.label)}</span>
        <strong>${escapeHtml(String(stat.value ?? 0))}</strong>
        <em>${stat.percent}% do total</em>
      </div>
      <i style="--progress:${stat.percent}%"></i>
    </article>
  `;
}

function parecerHeadIcon(name) {
  const icons = {
    check: `<svg viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5" /></svg>`,
    clock: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>`,
    file: `<svg viewBox="0 0 24 24"><path d="M7 3h7l4 4v14H7V3Z" /><path d="M14 3v5h5" /><path d="M10 13h6" /><path d="M10 17h4" /></svg>`,
    settings: `<svg viewBox="0 0 24 24"><path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" /><path d="M19 13.6c.1-.5.1-1.1 0-1.6l2-1.5-2-3.4-2.4 1a7 7 0 0 0-1.4-.8L14.9 5H9.1l-.4 2.3c-.5.2-1 .5-1.4.8l-2.4-1-2 3.4 2 1.5a7 7 0 0 0 0 1.6l-2 1.5 2 3.4 2.4-1c.4.3.9.6 1.4.8l.4 2.3h5.8l.4-2.3c.5-.2 1-.5 1.4-.8l2.4 1 2-3.4-2.1-1.5Z" /></svg>`,
    table: `<svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M4 10h16" /><path d="M4 16h16" /><path d="M10 4v16" /><path d="M16 4v16" /></svg>`,
  };
  return icons[name] || icons.file;
}

export async function refreshParecerPowerQuery(silent = false) {
  if (refreshRunning) return;
  refreshRunning = true;
  const button = $("#parecerRefreshBtn");
  const oldHtml = button.innerHTML;
  if (!silent) {
    button.disabled = true;
    button.innerHTML = `${parecerHeadIcon("clock")} Atualizando...`;
  }
  try {
    const result = await api("/api/powerquery/atualizar", { method: "POST", body: "{}" });
    await loadParecerPage();
    await callbacks.onPowerQueryRefresh();
    await callbacks.onHubRefresh();
    if (!silent) toast(`Power Query atualizado: ${result.records} registros`);
  } catch (error) {
    if (!silent) toast(error.message);
  } finally {
    button.disabled = false;
    button.innerHTML = oldHtml;
    refreshRunning = false;
  }
}
