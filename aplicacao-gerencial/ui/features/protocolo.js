import { api } from "../core/api.js";
import { $ } from "../core/dom.js";
import { capitalize } from "../core/format.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { setLoading, skeletonList, skeletonStats } from "../core/loading.js";
import { saveNavigationState } from "../core/navigationPersistence.js";
import { state } from "../core/state.js";
import { toast } from "../core/toast.js";
import { closeDialog } from "../layout/dialogs.js";
import { protocoloStatus, protocoloValue } from "./protocoloData.js";
import { configureProtocoloView, renderProtocoloPage } from "./protocoloView.js?v=20260717-unfreeze-last-1";

export { renderProtocoloPage } from "./protocoloView.js?v=20260717-unfreeze-last-1";

configureProtocoloView({ updateStatus: updateProtocoloStatus });

const callbacks = {
  onHubRefresh: async () => {},
};

export function configureProtocolo(options = {}) {
  if (typeof options.onHubRefresh === "function") {
    callbacks.onHubRefresh = options.onHubRefresh;
  }
}

export async function loadProtocoloPage() {
  if (state.mode !== "protocolo") return;
  if (state.protocolo.page === "configuracoes") state.protocolo.page = "dashboard";
  syncProtocoloPageVisibility();
  updateProtocoloStatsVisibility();
  try {
    if (state.protocolo.page === "dashboard") {
      setLoading("#protocoloStats", skeletonStats(4));
    }
    if (state.protocolo.page === "monitoramento") setLoading("#protocoloOpenGrid", skeletonList(5));
    if (state.protocolo.page === "concluidos") setLoading("#protocoloClosedGrid", skeletonList(5));
    state.protocolo.records = await api("/api/protocolo");
    if (state.protocolo.page === "dashboard") {
      await loadProtocoloDashboard();
    }
    renderProtocoloPage();
  } catch (error) {
    toast(error.message);
    renderProtocoloPage();
  }
}

export async function loadProtocoloDashboard() {
  renderProtocoloDashboard();
}

function renderProtocoloDashboard() {
  const records = state.protocolo.records || [];
  const periodInput = $("#protocoloDashboardPeriod");
  const walletSelect = $("#protocoloDashboardCarteira");
  if (!periodInput || !walletSelect) return;
  if (!periodInput.value) periodInput.value = currentPeriod();
  syncDashboardWallets(records, walletSelect);
  const selectedWallet = walletSelect.value;
  const walletRecords = records.filter((row) => !selectedWallet || protocolWallet(row) === selectedWallet);
  const pending = walletRecords.filter((row) => protocoloStatus(row) === "PENDENTE");
  const concludedInPeriod = walletRecords.filter((row) => (
    protocoloStatus(row) === "CONCLUIDO"
    && dateMatchesPeriod(protocolDate(row, ["DATA DE CONCLUSAO", "DATA DE CONCLUSÃO"]), periodInput.value)
  ));
  const oldPending = pending.filter((row) => protocolAgeDays(row) > 7);
  const durations = concludedInPeriod
    .map((row) => protocolDurationDays(row))
    .filter((value) => Number.isFinite(value) && value >= 0);
  const average = durations.length ? durations.reduce((sum, value) => sum + value, 0) / durations.length : null;

  $("#protocoloStats").innerHTML = [
    { label: "Pendentes", value: pending.length, hint: "Protocolos em aberto", tone: "orange", icon: "clock", target: "monitoramento" },
    { label: "Concluídos no período", value: concludedInPeriod.length, hint: formatDashboardPeriod(periodInput.value), tone: "green", icon: "check", target: "concluidos" },
    { label: "Acima de 7 dias", value: oldPending.length, hint: "Pendências que exigem atenção", tone: "danger", icon: "alert", target: "monitoramento" },
    { label: "Tempo médio", value: average === null ? "—" : `${formatDashboardNumber(average)} dias`, hint: "Da solicitação à conclusão", tone: "blue", icon: "stopwatch" },
  ].map(renderProtocoloStatCard).join("");

  renderDashboardWalletBreakdown(pending);
  renderDashboardAging(pending);
  renderDashboardPriority(pending);
  $("#protocoloDashboardUpdatedAt").textContent = `Atualizado ${new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date())}`;
  bindProtocoloDashboardActions();
}

function syncDashboardWallets(records, select) {
  const selected = select.value;
  const wallets = [...new Set(records.map(protocolWallet).filter(Boolean))].sort((a, b) => a.localeCompare(b, "pt-BR"));
  const signature = wallets.join("\u001f");
  if (select.dataset.signature === signature) return;
  select.innerHTML = `<option value="">Todas as carteiras</option>${wallets.map((wallet) => `<option value="${escapeAttr(wallet)}">${escapeHtml(wallet)}</option>`).join("")}`;
  select.dataset.signature = signature;
  if (wallets.includes(selected)) select.value = selected;
}

function renderDashboardWalletBreakdown(pending) {
  const target = $("#protocoloDashboardCarteiras");
  const counts = new Map();
  pending.forEach((row) => counts.set(protocolWallet(row) || "Não informada", (counts.get(protocolWallet(row) || "Não informada") || 0) + 1));
  const rows = [...counts.entries()].sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0], "pt-BR"));
  const max = Math.max(1, ...rows.map(([, total]) => total));
  $("#protocoloCarteirasTotal").textContent = `${pending.length} em aberto`;
  target.innerHTML = rows.length ? rows.map(([wallet, total]) => `
    <button type="button" class="protocolo-breakdown-row" data-protocolo-dashboard-wallet="${escapeAttr(wallet)}">
      <strong>${escapeHtml(wallet)}</strong>
      <span><i style="width:${Math.max(5, Math.round((total / max) * 100))}%"></i></span>
      <b>${total}</b>
    </button>
  `).join("") : dashboardEmpty("Nenhuma pendência para a seleção atual.");
}

function renderDashboardAging(pending) {
  const buckets = [
    { label: "Até 2 dias", min: 0, max: 2, tone: "recent" },
    { label: "De 3 a 7 dias", min: 3, max: 7, tone: "warning" },
    { label: "Acima de 7 dias", min: 8, max: Number.POSITIVE_INFINITY, tone: "danger" },
  ];
  $("#protocoloDashboardAging").innerHTML = buckets.map((bucket) => {
    const total = pending.filter((row) => {
      const age = protocolAgeDays(row);
      return age >= bucket.min && age <= bucket.max;
    }).length;
    return `<article class="protocolo-aging-item ${bucket.tone}"><span></span><div><strong>${total}</strong><small>${bucket.label}</small></div></article>`;
  }).join("");
}

function renderDashboardPriority(pending) {
  const rows = [...pending]
    .sort((left, right) => protocolDate(left)?.getTime() - protocolDate(right)?.getTime())
    .slice(0, 8);
  $("#protocoloDashboardPriorityList").innerHTML = rows.length ? rows.map((row) => {
    const rowNumber = row.__row_number;
    return `
      <article class="protocolo-priority-row">
        <button type="button" class="protocolo-priority-main" data-protocolo-dashboard-open="${escapeAttr(rowNumber)}" data-wallet="${escapeAttr(protocolWallet(row))}">
          <span class="protocolo-priority-age">${protocolAgeLabel(row)}</span>
          <div><strong>${escapeHtml(String(protocoloValue(row, ["NOME"]) || "Cliente não informado"))}</strong><small>${escapeHtml(protocolWallet(row) || "Carteira não informada")} · PJ ${escapeHtml(String(protocoloValue(row, ["PJ"]) || "—"))}</small></div>
          <span>${escapeHtml(String(protocoloValue(row, ["DATA DE SOLICITACAO", "DATA DE SOLICITAÇÃO"]) || "Sem data"))}</span>
        </button>
        <button type="button" class="protocolo-priority-conclude" data-protocolo-dashboard-conclude="${escapeAttr(rowNumber)}">Concluir</button>
      </article>
    `;
  }).join("") : dashboardEmpty("Nenhum protocolo pendente no momento.");
}

function bindProtocoloDashboardActions() {
  $("#protocoloDashboardPeriod").onchange = renderProtocoloDashboard;
  $("#protocoloDashboardCarteira").onchange = renderProtocoloDashboard;
  $("#protocoloDashboardViewPending").onclick = () => openDashboardPending();
  document.querySelectorAll("[data-protocolo-dashboard-target]").forEach((button) => {
    button.onclick = () => showProtocoloPage(button.dataset.protocoloDashboardTarget);
  });
  document.querySelectorAll("[data-protocolo-dashboard-wallet]").forEach((button) => {
    button.onclick = () => openDashboardPending(button.dataset.protocoloDashboardWallet);
  });
  document.querySelectorAll("[data-protocolo-dashboard-open]").forEach((button) => {
    button.onclick = () => openDashboardPending(button.dataset.wallet, button.dataset.protocoloDashboardOpen);
  });
  document.querySelectorAll("[data-protocolo-dashboard-conclude]").forEach((button) => {
    button.onclick = () => updateProtocoloStatus(button.dataset.protocoloDashboardConclude, "CONCLUIDO", button);
  });
}

function openDashboardPending(wallet = "", rowNumber = "") {
  state.protocolo.pendingCarteiraFilter = String(wallet || "").toLowerCase();
  state.protocolo.pendingTargetRow = String(rowNumber || "");
  showProtocoloPage("monitoramento");
}

function protocolWallet(row) {
  return String(protocoloValue(row, ["CARTEIRA"]) || "").trim();
}

function protocolDate(row, headers = ["DATA DE SOLICITACAO", "DATA DE SOLICITAÇÃO"]) {
  const raw = String(protocoloValue(row, headers) || "").trim();
  let match = raw.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (match) return new Date(Number(match[3]), Number(match[2]) - 1, Number(match[1]));
  match = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (match) return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return null;
}

function protocolAgeDays(row) {
  const requested = protocolDate(row);
  if (!requested) return 0;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.max(0, Math.floor((today.getTime() - requested.getTime()) / 86400000));
}

function protocolDurationDays(row) {
  const requested = protocolDate(row);
  const concluded = protocolDate(row, ["DATA DE CONCLUSAO", "DATA DE CONCLUSÃO"]);
  return requested && concluded ? Math.max(0, (concluded.getTime() - requested.getTime()) / 86400000) : Number.NaN;
}

function protocolAgeLabel(row) {
  const days = protocolAgeDays(row);
  return days === 1 ? "1 dia" : `${days} dias`;
}

function dateMatchesPeriod(date, period) {
  if (!date || !/^\d{4}-\d{2}$/.test(period)) return false;
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}` === period;
}

function currentPeriod() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function formatDashboardPeriod(period) {
  const [year, month] = String(period || "").split("-").map(Number);
  if (!year || !month) return "Período atual";
  return new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric" }).format(new Date(year, month - 1, 1));
}

function formatDashboardNumber(value) {
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(value);
}

function dashboardEmpty(message) {
  return `<div class="protocolo-dashboard-empty">${escapeHtml(message)}</div>`;
}

export function showProtocoloPage(page) {
  if (page === "configuracoes") page = "dashboard";
  if (page !== "concluidos") setProtocoloSheetFocus(false);
  state.protocolo.page = page;
  saveNavigationState();
  syncProtocoloPageVisibility();
  updateProtocoloStatsVisibility();
  loadProtocoloPage();
}

function syncProtocoloPageVisibility() {
  const page = state.protocolo.page || "dashboard";
  const content = $("#protocoloContent");
  if (content) content.dataset.page = page;
  document.querySelectorAll("[data-protocolo-page]").forEach((button) => {
    button.classList.toggle("active", button.dataset.protocoloPage === page);
  });
  ["dashboard", "monitoramento", "concluidos"].forEach((name) => {
    $(`#protocolo${capitalize(name)}`)?.classList.toggle("hidden", name !== page);
  });
  const globalNewButton = $("#protocoloNewBtn");
  globalNewButton?.classList.toggle("hidden", page === "concluidos");
  if (globalNewButton) globalNewButton.style.display = page === "concluidos" ? "none" : "";
}

function setProtocoloSheetFocus(active) {
  document.body.classList.toggle("protocolo-sheet-focus-mode", active);
  const button = $("#protocoloSheetFocusBtn");
  if (!button) return;
  button.setAttribute("aria-pressed", String(active));
  const label = button.querySelector("span");
  if (label) label.textContent = active ? "Sair do foco" : "Modo foco";
}

export function toggleProtocoloSheetFocus() {
  setProtocoloSheetFocus(!document.body.classList.contains("protocolo-sheet-focus-mode"));
}

export function downloadProtocoloReport() {
  const rows = state.protocolo.records || [];
  if (!rows.length) {
    toast("Nenhum protocolo disponível para o relatório");
    return;
  }
  const headers = [];
  const known = new Set();
  rows.forEach((row) => Object.keys(row).forEach((header) => {
    if (header.startsWith("_") || known.has(header)) return;
    known.add(header);
    headers.push(header);
  }));
  const csvCell = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  const csv = [headers.map(csvCell).join(";"), ...rows.map((row) => headers.map((header) => csvCell(row[header])).join(";"))].join("\r\n");
  const url = URL.createObjectURL(new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `protocolos-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function updateProtocoloStatsVisibility() {
  const stats = $("#protocoloStats");
  const visible = state.protocolo.page === "dashboard";
  stats?.classList.toggle("hidden", !visible);
  if (stats) stats.style.display = visible ? "" : "none";
}

export function openProtocoloForm() {
  $("#protocoloForm").reset();
  $("#protocoloDialog").showModal();
}

export async function saveProtocolo(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  try {
    await api("/api/protocolo", { method: "POST", body: JSON.stringify(payload) });
    closeDialog("#protocoloDialog");
    toast("Protocolo cadastrado no banco de dados");
    state.protocolo.page = "monitoramento";
    await loadProtocoloPage();
    await callbacks.onHubRefresh();
  } catch (error) {
    toast(error.message);
  }
}

export async function updateProtocoloStatus(rowNumber, status, select) {
  const previous = protocoloStatus(state.protocolo.records.find((row) => String(row.__row_number) === String(rowNumber)) || {});
  if (status === "CONCLUIDO" && previous !== "CONCLUIDO" && !confirm("Marcar este protocolo como CONCLUIDO?")) {
    if (select && "value" in select) select.value = previous;
    return false;
  }
  const preserveScroll = state.protocolo.page === "monitoramento";
  const scrollTop = window.scrollY;
  try {
    await api("/api/protocolo/status", { method: "POST", body: JSON.stringify({ row: rowNumber, status }) });
    toast("Status salvo no banco de dados");
    await loadProtocoloPage();
    await callbacks.onHubRefresh();
    if (preserveScroll) {
      requestAnimationFrame(() => requestAnimationFrame(() => {
        const maxScroll = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
        window.scrollTo(0, Math.min(scrollTop, maxScroll));
      }));
    }
    return true;
  } catch (error) {
    if (select && "value" in select) select.value = previous;
    toast(error.message);
    return false;
  }
}

function renderProtocoloStatCard(stat) {
  return `
    <button type="button" class="stats-card protocolo-stat-card dashboard-stat-card dashboard-tone-${stat.tone} ${stat.tone}" ${stat.target ? `data-protocolo-dashboard-target="${stat.target}"` : "disabled"}>
      <span class="protocolo-stat-icon" aria-hidden="true">${protocoloIcon(stat.icon)}</span>
      <div>
        <span>${stat.label}</span>
        <strong>${stat.value ?? 0}</strong>
        <em>${stat.hint}</em>
      </div>
    </button>
  `;
}

function protocoloIcon(name) {
  const icons = {
    check: `<svg viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5" /></svg>`,
    clock: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>`,
    alert: `<svg viewBox="0 0 24 24"><path d="M12 3 2 21h20L12 3Z" /><path d="M12 9v5" /><path d="M12 18h.01" /></svg>`,
    stopwatch: `<svg viewBox="0 0 24 24"><circle cx="12" cy="13" r="8" /><path d="M12 9v4l3 2" /><path d="M9 2h6" /></svg>`,
  };
  return icons[name] || icons.clock;
}


