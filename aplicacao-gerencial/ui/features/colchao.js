import { api } from "../core/api.js";
import { $ } from "../core/dom.js";
import { formatValue } from "../core/format.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { clearLoading, setLoading, skeletonList, skeletonStats } from "../core/loading.js";
import { saveNavigationState } from "../core/navigationPersistence.js";
import { state } from "../core/state.js";
import { toast } from "../core/toast.js";
import { bindNotesButtons, notesButton } from "./notes.js";
import { formatSheetValue } from "./sheetFormat.js";
import { renderColchaoExcelGrid, renderColchaoExpandedExcelGrid } from "./colchaoExcelGrid.js?v=20260814-due-date-1";
import { bindColchaoClients, loadColchaoClients } from "./colchaoClients.js?v=20260814-client-finance-5";
import {
  capitalize,
  clearColchaoCache,
  clearColchaoRuntimeData,
  currentProfile,
  dueDateIso,
  firstValue,
  formatDateTime,
  identifierValue,
  labelBucket,
  money,
  normalizePendingBucket,
  pages,
  profiles,
  replaceProfiles,
  selectedSheet,
  value,
} from "./colchaoCore.js?v=20260814-dynamic-wallets-1";
import {
  bindStatusButtons,
  configureColchaoStatus,
  renderStatusSelect,
  updateBatchSaveButton,
} from "./colchaoStatus.js?v=20260814-due-date-1";

configureColchaoStatus({ loadPage: loadColchaoPage });

export { saveColchaoBatchStatus } from "./colchaoStatus.js?v=20260814-due-date-1";

let profileHomeRequest = 0;
let profilesLoaded = false;
const collapsedPendingGroups = new Set();

export function showColchaoProfiles() {
  if (!confirmDiscardColchaoChanges()) return;
  state.colchao.profile = null;
  state.colchao.page = "profiles";
  clearColchaoRuntimeData(false);
  $("#colchaoStats").innerHTML = "";
  $("#colchaoRanking").innerHTML = "";
  $("#colchaoValidation").innerHTML = "";
  renderProfileHome();
}

export function downloadColchaoReport(profile = state.colchao.profile || "alpha") {
  const selected = profile || "alpha";
  const link = document.createElement("a");
  link.href = `/api/colchao/relatorio.csv?profile=${encodeURIComponent(selected)}`;
  link.download = "";
  document.body.appendChild(link);
  link.click();
  link.remove();
  toast(`Relatório do colchão ${selected.toUpperCase()} gerado.`);
}

export async function loadColchaoConfig() {
  state.colchao.config = await api(`/api/colchao/config?profile=${encodeURIComponent(state.colchao.profile || "alpha")}`);
  const profile = currentProfile();
  if (!state.colchao.sheet) state.colchao.sheet = state.colchao.config.main_sheet || profile.sheets[0] || "";
  const form = $("#colchaoConfigForm");
  Object.entries(state.colchao.config).forEach(([key, value]) => {
    if (form.elements[key]) form.elements[key].value = value ?? "";
  });
  renderSheetSelect();
}

export async function loadColchaoPage() {
  if (state.mode !== "colchao") return;
  if (!state.colchao.profile) {
    renderProfileHome();
    return;
  }
  try {
    bindColchaoClients();
    if (state.colchao.page === "dashboard") await loadDashboard();
    if (state.colchao.page === "clientes") await loadColchaoClients();
    if (state.colchao.page === "pendencias") await loadPendencias();
    if (state.colchao.page === "completo") await loadCompleto();
    if (state.colchao.page === "configuracoes") await loadValidation();
  } catch (error) {
    toast(error.message);
  }
}

export function showColchaoPage(page) {
  if (!state.colchao.profile) return renderProfileHome();
  if (page !== state.colchao.page && !confirmDiscardColchaoChanges()) return;
  state.colchao.page = page;
  saveNavigationState();
  document.querySelectorAll("[data-colchao-page]").forEach((button) => button.classList.toggle("active", button.dataset.colchaoPage === page));
  renderColchaoShell();
  loadColchaoPage();
}

export async function openColchaoProfile(profileId) {
  profileHomeRequest += 1;
  state.colchao.profile = profileId;
  state.colchao.sheet = currentProfile().sheets[0] || "";
  state.colchao.page = "dashboard";
  saveNavigationState();
  clearColchaoRuntimeData(true);
  renderColchaoShell();
  await loadColchaoConfig();
  await loadColchaoPage();
}

function renderProfileHome() {
  const requestId = ++profileHomeRequest;
  $("#pageTitle").textContent = "COLCHÃO";
  $("#colchaoProfiles").classList.remove("hidden");
  renderProfileHomeContent(state.colchao.profileSummaries, true);
  renderColchaoShell();
  void loadAvailableProfiles(requestId);
}

async function loadAvailableProfiles(requestId) {
  try {
    const payload = await api("/api/colchao/profiles");
    if (requestId !== profileHomeRequest || state.colchao.profile) return;
    replaceProfiles(payload.items || []);
    profilesLoaded = true;
    state.colchao.profileSummaries = {};
    renderProfileHomeContent({}, true);
    await loadProfileSummaries(requestId, true);
  } catch (error) {
    if (requestId !== profileHomeRequest || state.colchao.profile) return;
    profilesLoaded = true;
    renderProfileHomeContent({}, false, error.message);
  }
}

function confirmDiscardColchaoChanges() {
  const total = Object.keys(state.colchao.pendingStatusChanges || {}).length;
  if (!total) return true;
  if (!confirm(`Existem ${total} alteração(ões) não salvas. Descartar e continuar?`)) return false;
  state.colchao.pendingStatusChanges = {};
  updateBatchSaveButton();
  return true;
}

async function loadProfileSummaries(requestId, force = false) {
  if (!profilesLoaded) return;
  if (!force && Object.keys(state.colchao.profileSummaries || {}).length === profiles.length) {
    if (requestId === profileHomeRequest && !state.colchao.profile) renderProfileHomeContent(state.colchao.profileSummaries);
    return;
  }
  const results = await Promise.allSettled(profiles.map(async (profile) => ({
    profile,
    dashboard: await api(`/api/colchao/dashboard?profile=${encodeURIComponent(profile.id)}`),
  })));
  if (requestId !== profileHomeRequest || state.colchao.profile) return;
  const summaries = {};
  results.forEach((result, index) => {
    const profile = profiles[index];
    summaries[profile.id] = result.status === "fulfilled"
      ? { ...result.value.dashboard, available: true }
      : { available: false, error: result.reason?.message || "Não foi possível carregar o resumo." };
  });
  state.colchao.profileSummaries = summaries;
  renderProfileHomeContent(summaries);
}

function renderProfileHomeContent(summaries = {}, loading = false, loadError = "") {
  const root = $("#colchaoProfiles");
  if (!root) return;
  const loaded = profiles.map((profile) => summaries?.[profile.id]).filter((summary) => summary?.available);
  const totals = loaded.reduce((result, summary) => ({
    records: result.records + Number(summary.total_registros || 0),
    pending: result.pending + Number(summary.pendencias || 0),
    overdue: result.overdue + Number(summary.vencidas || 0),
    value: result.value + Number(summary.valor_aberto || 0),
  }), { records: 0, pending: 0, overdue: 0, value: 0 });
  root.innerHTML = `
    <section class="colchao-profile-home">
      <header class="colchao-profile-home-head">
        <div>
          <h2>Carteiras</h2>
          <span>Selecione uma carteira para acompanhar acordos, parcelas e pendências.</span>
        </div>
        <button class="secondary-btn ds-button" type="button" data-colchao-refresh-profiles>Atualizar resumo</button>
      </header>
      <div class="colchao-profile-summary ${loading ? "is-loading" : ""}">
        <span><strong>${profiles.length}</strong> carteiras</span>
        <span><strong>${totals.records.toLocaleString("pt-BR")}</strong> registros</span>
        <span><strong>${totals.pending.toLocaleString("pt-BR")}</strong> pendências</span>
        <span><strong>${totals.overdue.toLocaleString("pt-BR")}</strong> vencidos</span>
        <span><strong>${money(totals.value)}</strong> em aberto</span>
      </div>
      <div class="colchao-profile-list">
        ${profiles.length
          ? profiles.map((profile) => renderProfileCard(profile, summaries?.[profile.id], loading)).join("")
          : `<div class="empty-state">${escapeHtml(loadError || "Nenhuma carteira possui o Colchão habilitado.")}</div>`}
      </div>
    </section>
  `;
  root.querySelectorAll("[data-colchao-profile]").forEach((button) => {
    button.addEventListener("click", () => openColchaoProfile(button.dataset.colchaoProfile));
  });
  root.querySelector("[data-colchao-refresh-profiles]")?.addEventListener("click", (event) => {
    event.currentTarget.disabled = true;
    renderProfileHomeContent(state.colchao.profileSummaries, true);
    void loadAvailableProfiles(++profileHomeRequest);
  });
}

function renderProfileCard(profile, summary, loading) {
  const available = summary?.available;
  const descriptor = profile.id === "beta" ? `${profile.keyLabel} · Ativo e Passivo` : profile.keyLabel;
  const updatedAt = available && summary.updated_at ? formatDateTime(summary.updated_at) : "";
  return `
    <article class="colchao-wallet-card ${available ? "is-ready" : ""} ${summary && !available ? "has-error" : ""}">
      <button type="button" data-colchao-profile="${escapeAttr(profile.id)}">
        <span class="colchao-wallet-icon" aria-hidden="true"><img src="/assets/icons/mattress.svg" alt="" /></span>
        <span class="colchao-wallet-content">
          <span class="colchao-wallet-title-row">
            <span><strong>${escapeHtml(profile.name)}</strong><small>${escapeHtml(descriptor)}</small></span>
            <em class="colchao-wallet-state">${loading && !summary ? "Carregando" : available ? "Atualizado" : "Indisponível"}</em>
          </span>
          <span class="colchao-wallet-metrics">
            ${renderWalletMetric(summary?.total_registros, "registros", loading)}
            ${renderWalletMetric(summary?.pendencias, "pendências", loading)}
            ${renderWalletMetric(summary?.vencidas, "vencidos", loading)}
            ${renderWalletMetric(available ? money(summary?.valor_aberto) : null, "em aberto", loading)}
          </span>
          <span class="colchao-wallet-footer">
            <small>${available ? `Resumo atualizado em ${escapeHtml(updatedAt)}` : summary?.error ? escapeHtml(summary.error) : "Consultando indicadores..."}</small>
            <strong>Acessar <span aria-hidden="true">›</span></strong>
          </span>
        </span>
      </button>
    </article>
  `;
}

function renderWalletMetric(value, label, loading) {
  const display = value === null || value === undefined
    ? (loading ? "—" : "0")
    : typeof value === "number" ? value.toLocaleString("pt-BR") : value;
  return `<span><strong>${escapeHtml(String(display))}</strong><small>${escapeHtml(label)}</small></span>`;
}

function renderColchaoShell() {
  if (!pages.includes(state.colchao.page)) state.colchao.page = "dashboard";
  const insideProfile = Boolean(state.colchao.profile);
  document.querySelector(".module-tabs-row")?.classList.toggle("hidden", !insideProfile);
  document.querySelector(".topbar")?.classList.toggle("tabs-hidden", !insideProfile);
  $("#colchaoContent")?.classList.toggle("profile-home-active", !insideProfile);
  $("#colchaoProfiles").classList.toggle("hidden", insideProfile);
  $("#colchaoProfiles").style.display = insideProfile ? "none" : "";
  const contentHead = document.querySelector("#colchaoContent .overview-head");
  $("#colchaoDashboard .parecer-columns")?.classList.add("single-column");
  contentHead?.classList.add("hidden");
  if (contentHead) contentHead.style.display = "none";
  contentHead?.classList.toggle("colchao-profile-active", insideProfile);
  $("#colchaoStats")?.classList.toggle("hidden", !insideProfile || state.colchao.page !== "dashboard");
  $("#colchaoStats").style.display = insideProfile && state.colchao.page === "dashboard" ? "" : "none";
  pages.forEach((name) => $(`#colchao${capitalize(name)}`)?.classList.toggle("hidden", !insideProfile || name !== state.colchao.page));
  pages.forEach((name) => {
    const page = $(`#colchao${capitalize(name)}`);
    if (page) page.style.display = insideProfile && name === state.colchao.page ? "" : "none";
  });
  document.querySelectorAll("[data-colchao-page]").forEach((button) => button.classList.toggle("active", button.dataset.colchaoPage === state.colchao.page));
  const planilhaButton = document.querySelector("[data-colchao-page='completo']");
  if (planilhaButton) {
    planilhaButton.title = "Planilha";
    planilhaButton.setAttribute("aria-label", "Planilha");
  }
  $("#colchaoNav")?.classList.toggle("hidden", !insideProfile);
  document.querySelectorAll("#colchaoNav [data-colchao-page]").forEach((button) => button.classList.toggle("hidden", !insideProfile));
  moveValidationPanelToSettings();
  $("#colchaoBackProfilesTopBtn")?.classList.toggle("hidden", !insideProfile);
  const profile = currentProfile();
  $("#pageTitle").textContent = insideProfile ? `COLCHÃO - ${profile.name}` : "COLCHÃO";
  renderSheetSelect();
  renderAgreementForm();
}

function moveValidationPanelToSettings() {
  const validation = $("#colchaoValidation");
  const settings = $("#colchaoConfiguracoes");
  if (!validation || !settings || settings.contains(validation)) return;
  const panel = document.createElement("section");
  panel.className = "mini-panel";
  panel.innerHTML = `<h2>Validação da planilha</h2>`;
  panel.appendChild(validation);
  settings.appendChild(panel);
}

export async function saveColchaoConfig(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  payload.profile = state.colchao.profile || "alpha";
  try {
    state.colchao.config = await api("/api/colchao/config", { method: "PUT", body: JSON.stringify(payload) });
    state.colchao.sheet = state.colchao.config.main_sheet || currentProfile().sheets[0] || "";
    clearColchaoCache();
    await loadColchaoConfig();
    state.colchao.page = "dashboard";
    renderColchaoShell();
    await loadColchaoPage();
    toast("Configurações do colchão salvas");
    return;
    toast("Configurações do colchão salvas");
  } catch (error) {
    toast(error.message);
    return;
  }
  toast("Configurações do colchão salvas");
}

export async function saveColchaoAgreement(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const validation = validateColchaoAgreement(form);
  if (!validation.valid) {
    showColchaoAgreementError(validation.message);
    validation.control?.focus();
    return;
  }
  showColchaoAgreementError("");
  const submitButton = $("#colchaoAgreementSubmitBtn");
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.textContent = "Salvando...";
  }
  const values = {};
  form.querySelectorAll("[data-colchao-field]").forEach((control) => {
    values[control.dataset.colchaoField] = control.value;
  });
  const payload = {
    profile: state.colchao.profile || "alpha",
    sheet: form.elements.sheet?.value || selectedSheet(),
    values,
  };
  try {
    const result = await api("/api/colchao/acordos", { method: "POST", body: JSON.stringify(payload) });
    clearColchaoCache();
    form.reset();
    toast(`${result.rows?.length || 0} parcela(s) cadastrada(s) no acordo ${result.agreement || ""}`);
    updateColchaoAgreementUX();
    await loadDashboard();
  } catch (error) {
    showColchaoAgreementError(error.message);
    toast(error.message);
  } finally {
    if (submitButton) submitButton.textContent = "Cadastrar acordo";
    updateColchaoAgreementUX();
  }
}

export async function openColchaoSpreadsheet() {
  try {
    await api("/api/colchao/abrir-planilha", {
      method: "POST",
      body: JSON.stringify({ profile: state.colchao.profile || "alpha" }),
    });
    toast("Planilha aberta");
  } catch (error) {
    toast(error.message);
  }
}

export async function syncColchaoData() {
  try {
    const result = await api("/api/colchao/sync", {
      method: "POST",
      body: JSON.stringify({ profile: state.colchao.profile || "alpha" }),
    });
    clearColchaoCache();
    toast(`${result.synced || 0} registro(s) sincronizado(s)`);
    await loadColchaoPage();
  } catch (error) {
    toast(error.message);
  }
}

async function loadDashboard() {
  if (!state.colchao.cache.dashboard) {
    setLoading("#colchaoStats", skeletonStats(4));
    state.colchao.cache.dashboard = await api(`/api/colchao/dashboard?profile=${encodeURIComponent(state.colchao.profile || "alpha")}`);
  }
  const dashboard = state.colchao.cache.dashboard;
  state.colchao.dashboard = dashboard;
  $("#colchaoStats").innerHTML = [
    { label: "A vencer hoje", value: dashboard.a_vencer_hoje, tone: "warn" },
    { label: "Vencidas", value: dashboard.vencidas, tone: "danger" },
    { label: "Acordos em quebra", value: dashboard.quebras, tone: "neutral" },
    { label: "Acordos pagos", value: dashboard.pagos, tone: "success" },
  ].map((item) => `
    <article class="stat-card dashboard-stat-card dashboard-tone-${item.tone}">
      <span>${escapeHtml(item.label)}</span>
      <strong>${escapeHtml(String(item.value))}</strong>
    </article>
  `).join("");
  const ranking = dashboard.ranking_operador || [];
  const rankingMax = Math.max(1, ...ranking.map((item) => Number(item.total || 0)));
  $("#colchaoRanking").innerHTML = ranking.length ? ranking.map((item, index) => `
    <div class="metric-row dashboard-rank-row ${index < 3 ? `dashboard-rank-top-${index + 1}` : ""}">
      <span class="dashboard-rank-number" aria-hidden="true">${String(index + 1).padStart(2, "0")}</span>
      <div class="dashboard-rank-identity">
        <strong>${escapeHtml(item.label)}</strong>
        <span>${money(item.valor)}</span>
      </div>
      <span class="dashboard-rank-track" aria-hidden="true"><i style="width:${Math.max(4, Math.round((Number(item.total || 0) / rankingMax) * 100))}%"></i></span>
      <strong class="dashboard-rank-total">${item.total}</strong>
    </div>
  `).join("") : `<div class="empty-overview">Sem dados para exibir.</div>`;
}

async function loadPendencias() {
  if (!state.colchao.cache.pendencias) {
    setLoading("#colchaoPendenciasGrid", skeletonList(5));
    state.colchao.cache.pendencias = await api(`/api/colchao/pendencias?profile=${encodeURIComponent(state.colchao.profile || "alpha")}`);
  }
  state.colchao.pendencias = state.colchao.cache.pendencias;
  renderPendencias();
}

async function loadCompleto() {
  const params = colchaoQueryParams();
  const cacheKey = params.toString();
  if (!state.colchao.cache.records) state.colchao.cache.records = {};
  if (!state.colchao.cache.records[cacheKey]) {
    setLoading("#colchaoCompletoGrid", skeletonList(6));
    state.colchao.cache.records[cacheKey] = await api(`/api/colchao?${cacheKey}`);
  }
  const payload = state.colchao.cache.records[cacheKey];
  state.colchao.records = payload.rows || [];
  state.colchao.completo.page = payload.page || state.colchao.completo.page || 1;
  state.colchao.completo.pageSize = payload.page_size || state.colchao.completo.pageSize || 100;
  state.colchao.completo.total = payload.total || 0;
  state.colchao.completo.totalPages = payload.total_pages || 1;
  renderCompleto();
}

async function loadValidation() {
  if (!state.colchao.cache.validation) {
    $("#colchaoValidation").innerHTML = `<div class="empty-overview">Validando planilha...</div>`;
    state.colchao.cache.validation = await api(`/api/colchao/validar?profile=${encodeURIComponent(state.colchao.profile || "alpha")}`);
  }
  const validation = state.colchao.cache.validation;
  $("#colchaoValidation").innerHTML = validation.ok
    ? `<div class="metric-row"><div><strong>Planilha válida</strong><span>Colunas e dados principais OK</span></div><strong>OK</strong></div>`
    : validation.errors.map((error) => `<div class="metric-row"><div><strong>Alerta</strong><span>${escapeHtml(error)}</span></div></div>`).join("");
}

export function renderPendencias() {
  clearLoading("#colchaoPendenciasGrid");
  const sourceRows = state.colchao.pendencias || [];
  syncPendingOperatorFilter(sourceRows);
  const search = $("#colchaoPendingSearch").value.trim().toLowerCase();
  const bucket = $("#colchaoPendingBucket").value;
  const operator = $("#colchaoPendingOperator")?.value || "";
  const dateFilter = $("#colchaoPendingDate")?.value || "";
  const order = $("#colchaoPendingOrder")?.value || "due";
  const rows = sourceRows.filter((row) => {
    const values = Object.values(row).map((value) => String(value ?? "").toLowerCase());
    return (!search || values.some((value) => value.includes(search)))
      && (!bucket || pendingGroup(row).id === bucket)
      && (!operator || pendingOperator(row) === operator)
      && (!dateFilter || dueDateIso(row) === dateFilter);
  }).sort((left, right) => comparePendingRows(left, right, order));
  renderPendingQueueSummary(rows);
  if (!rows.length) {
    $("#colchaoPendenciasGrid").innerHTML = `<div class="empty-overview">Nenhuma parcela pendente encontrada.</div>`;
    restoreColchaoPendingScroll();
    return;
  }
  const grid = $("#colchaoPendenciasGrid");
  grid.innerHTML = groupPendingRows(rows).map((group) => {
    const collapsed = collapsedPendingGroups.has(group.id);
    const total = group.rows.reduce((sum, row) => sum + pendingAmount(row), 0);
    return `
      <section class="colchao-queue-group">
        <button class="colchao-queue-group-head" type="button" data-colchao-pending-group="${escapeAttr(group.id)}" aria-expanded="${String(!collapsed)}">
          <span class="colchao-queue-chevron" aria-hidden="true">${collapsed ? "›" : "⌄"}</span>
          <strong>${escapeHtml(group.label)}</strong>
          <span>${group.rows.length.toLocaleString("pt-BR")} parcela${group.rows.length === 1 ? "" : "s"}</span>
          <b>${escapeHtml(money(total))}</b>
        </button>
        <div class="colchao-queue-list${collapsed ? " hidden" : ""}">${group.rows.map(renderColchaoCard).join("")}</div>
      </section>
    `;
  }).join("");
  grid.querySelectorAll("[data-colchao-pending-group]").forEach((button) => {
    button.addEventListener("click", () => {
      const groupId = button.dataset.colchaoPendingGroup;
      const section = button.closest(".colchao-queue-group");
      const list = section?.querySelector(":scope > .colchao-queue-list");
      const chevron = button.querySelector(".colchao-queue-chevron");
      const collapsed = !collapsedPendingGroups.has(groupId);
      if (collapsed) collapsedPendingGroups.add(groupId);
      else collapsedPendingGroups.delete(groupId);
      button.setAttribute("aria-expanded", String(!collapsed));
      section?.classList.toggle("is-collapsed", collapsed);
      list?.classList.toggle("hidden", collapsed);
      if (chevron) chevron.textContent = collapsed ? "›" : "⌄";
    });
  });
  grid.querySelectorAll("[data-colchao-pending-expand]").forEach((button) => {
    button.addEventListener("click", () => {
      const row = button.closest(".colchao-queue-row");
      const details = row?.querySelector(".colchao-queue-details");
      if (!details) return;
      const expanded = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", String(!expanded));
      details.classList.toggle("hidden", expanded);
      row.classList.toggle("is-expanded", !expanded);
    });
  });
  grid.querySelectorAll("[data-colchao-select-value]").forEach((copyable) => {
    copyable.addEventListener("click", (event) => event.stopPropagation());
  });
  grid.querySelectorAll("[data-colchao-copy-id]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      const copied = await copyColchaoIdentifier(button.dataset.colchaoCopyId || "");
      if (!copied) return toast("Não foi possível copiar o identificador.");
      button.classList.add("is-copied");
      window.setTimeout(() => button.classList.remove("is-copied"), 1200);
      toast(`${button.dataset.colchaoCopyLabel || "Identificador"} copiado.`);
    });
  });
  bindStatusButtons("#colchaoPendenciasGrid");
  bindNotesButtons(grid);
  restoreColchaoPendingScroll();
}

function renderColchaoCard(row) {
  const profile = currentProfile();
  const group = pendingGroup(row);
  const tone = group.id === "overdue" ? "critical" : group.id === "today" || group.id === "next7" ? "warning" : "normal";
  const dueDate = firstValue(row, currentProfile().id === "beta"
    ? ["MÊS", "MES", "DATA DO VENCIMENTO", "MÊS DE EXPIRAÇÃO", "MES DE EXPIRACAO"]
    : ["DATA DO VENCIMENTO", "MÊS", "MES", "MÊS DE EXPIRAÇÃO", "MES DE EXPIRACAO"]);
  const observation = firstValue(row, ["OBS", "OBSERVAÇÕES", "OBSERVACOES"]);
  const client = firstValue(row, ["CLIENTE", "NOME"]) || "Cliente não identificado";
  const installment = firstValue(row, ["PARCELAS", "COND PARCELADAS", "COND PARCELAS"]);
  const amount = firstValue(row, ["VALOR DO ACORDO", "CASH"]);
  const identifier = identifierValue(row);
  const documentNumber = firstValue(row, ["CPF/CNPJ", "CPF", "CNPJ"]);
  return `
    <article class="colchao-queue-row urgency-${tone}" data-colchao-pending-row="${escapeAttr(row.__row_number)}">
      <button class="colchao-queue-main" type="button" data-colchao-pending-expand="${escapeAttr(row.__row_number)}" aria-expanded="false">
        <span class="colchao-queue-age">${escapeHtml(pendingAgeLabel(row))}</span>
        <span class="colchao-queue-identity">
          <strong class="colchao-copyable-value" data-colchao-select-value="${escapeAttr(client)}" title="Selecione o nome para copiar">${escapeHtml(client)}</strong>
          <small><span>${escapeHtml(profile.keyLabel)}</span> <span class="colchao-copyable-value colchao-copyable-id" data-colchao-select-id="${escapeAttr(identifier)}" data-colchao-select-value="${escapeAttr(identifier)}" title="Selecione para copiar">${escapeHtml(identifier)}</span> <i>·</i> <span>CPF/CNPJ</span> <span class="colchao-copyable-value" data-colchao-select-value="${escapeAttr(documentNumber)}" title="Selecione o CPF/CNPJ para copiar">${escapeHtml(documentNumber)}</span></small>
        </span>
        <span class="colchao-queue-agreement"><small>Acordo / parcela</small><b>${escapeHtml(value(row, "ACORDO"))} · ${escapeHtml(installment)}</b></span>
        <span class="colchao-queue-operator"><small>Operador</small><b>${escapeHtml(pendingOperator(row))}</b></span>
        <span class="colchao-queue-due"><small>Vencimento</small><b>${escapeHtml(formatPendingDueDate(row, dueDate))}</b></span>
        <span class="colchao-queue-amount">${escapeHtml(formatSheetValue("VALOR DO ACORDO", amount))}</span>
        <span class="colchao-queue-expand" aria-hidden="true">⌄</span>
      </button>
      <div class="colchao-queue-actions">
        ${identifier ? `
          <button class="colchao-copy-id-btn" type="button" data-colchao-copy-id="${escapeAttr(identifier)}" data-colchao-copy-label="${escapeAttr(profile.keyLabel)}" title="Copiar ${escapeAttr(profile.keyLabel)}" aria-label="Copiar ${escapeAttr(profile.keyLabel)}">
            <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M15 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3" /></svg>
          </button>
        ` : ""}
        ${notesButton("colchao", row.__row_number, "Obs.")}
        ${renderStatusSelect(row, "data-colchao-select")}
      </div>
      <div class="colchao-queue-details hidden">
        <strong>Detalhes</strong>
        <p>${escapeHtml(observation || "Sem observação cadastrada.")}${row.__sheet_name ? ` · Origem: ${escapeHtml(row.__sheet_name)}` : ""}</p>
      </div>
    </article>
  `;
}

async function copyColchaoIdentifier(text) {
  if (!text) return false;
  try {
    if (navigator.clipboard?.writeText) {
      await Promise.race([
        navigator.clipboard.writeText(text),
        new Promise((_, reject) => window.setTimeout(() => reject(new Error("clipboard_timeout")), 800)),
      ]);
      return true;
    }
  } catch (_error) {
    // HTTP intranet hosts may block the modern Clipboard API; use the legacy fallback below.
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  return copied;
}

function syncPendingOperatorFilter(rows) {
  const select = $("#colchaoPendingOperator");
  if (!select) return;
  const selected = select.value;
  const operators = [...new Set(rows.map(pendingOperator).filter(Boolean))].sort((left, right) => left.localeCompare(right, "pt-BR"));
  const signature = operators.join("\u001f");
  if (select.dataset.signature === signature) return;
  select.innerHTML = `<option value="">Todos os operadores</option>${operators.map((operator) => `<option value="${escapeAttr(operator)}">${escapeHtml(operator)}</option>`).join("")}`;
  select.dataset.signature = signature;
  if (operators.includes(selected)) select.value = selected;
}

function pendingOperator(row) {
  return firstValue(row, ["OPERADOR", "OPERADORES"]) || "Não informado";
}

function pendingDueDate(row) {
  const iso = dueDateIso(row);
  if (!iso) return null;
  const match = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return match ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3])) : null;
}

function pendingDayDelta(row) {
  const due = pendingDueDate(row);
  if (!due) return Number.POSITIVE_INFINITY;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((due.getTime() - today.getTime()) / 86400000);
}

function pendingGroup(row) {
  const delta = pendingDayDelta(row);
  if (delta < 0 || (!Number.isFinite(delta) && normalizePendingBucket(row.__bucket) === "vencida")) return { id: "overdue", label: "Vencidos", rank: 0 };
  if (delta === 0) return { id: "today", label: "Vence hoje", rank: 1 };
  if (delta <= 7) return { id: "next7", label: "Próximos 7 dias", rank: 2 };
  return { id: "future", label: "Vencimentos futuros", rank: 3 };
}

function pendingAgeLabel(row) {
  const delta = pendingDayDelta(row);
  if (!Number.isFinite(delta)) return labelBucket(row.__bucket);
  if (delta < 0) return `${Math.abs(delta)}d vencido`;
  if (delta === 0) return "Hoje";
  return `Em ${delta}d`;
}

function pendingAmount(row) {
  const raw = firstValue(row, ["VALOR DO ACORDO", "CASH"]);
  if (typeof raw === "number") return Number.isFinite(raw) ? raw : 0;
  const text = String(raw ?? "").replace(/R\$/gi, "").replace(/\s/g, "");
  const normalized = text.includes(",") ? text.replace(/\./g, "").replace(",", ".") : text;
  const parsed = Number(normalized.replace(/[^0-9.-]/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

function comparePendingRows(left, right, order) {
  if (order === "name") return String(firstValue(left, ["CLIENTE", "NOME"])).localeCompare(String(firstValue(right, ["CLIENTE", "NOME"])), "pt-BR");
  if (order === "value") return pendingAmount(right) - pendingAmount(left);
  return pendingDayDelta(left) - pendingDayDelta(right);
}

function groupPendingRows(rows) {
  const groups = new Map();
  rows.forEach((row) => {
    const group = pendingGroup(row);
    if (!groups.has(group.id)) groups.set(group.id, { ...group, rows: [] });
    groups.get(group.id).rows.push(row);
  });
  return [...groups.values()].sort((left, right) => left.rank - right.rank);
}

function renderPendingQueueSummary(rows) {
  const target = $("#colchaoPendingSummary");
  if (!target) return;
  const overdue = rows.filter((row) => pendingGroup(row).id === "overdue").length;
  const total = rows.reduce((sum, row) => sum + pendingAmount(row), 0);
  target.innerHTML = `<span><b>${rows.length.toLocaleString("pt-BR")}</b> pendências</span><span class="is-critical"><b>${overdue.toLocaleString("pt-BR")}</b> vencidas</span><span><b>${escapeHtml(money(total))}</b> em aberto</span>`;
}

function formatPendingDueDate(row, fallback) {
  const date = pendingDueDate(row);
  return date ? new Intl.DateTimeFormat("pt-BR").format(date) : formatValue(fallback);
}

function restoreColchaoPendingScroll() {
  if (!Number.isFinite(state.colchao.pendingScrollTop)) return;
  const scrollTop = state.colchao.pendingScrollTop;
  delete state.colchao.pendingScrollTop;
  requestAnimationFrame(() => requestAnimationFrame(() => window.scrollTo(0, scrollTop)));
}

export function renderCompleto() {
  const rows = state.colchao.records;
  const headers = orderedColchaoHeaders(rows);
  syncCompletoOperatorFilter(rows);
  renderCompletoPagination();
  if (!headers.length) {
    $("#colchaoCompletoGrid").classList.remove("monitor-native-excel", "operational-native-excel", "excel-grid");
    $("#colchaoCompletoGrid").innerHTML = `<div class="empty-overview">Nenhum registro encontrado.</div>`;
    return;
  }
  renderColchaoExcelGrid(rows, headers);
  const expandButton = $("#colchaoExpandSpreadsheetBtn");
  if (expandButton && expandButton.dataset.expandedBound !== "true") {
    expandButton.dataset.expandedBound = "true";
    expandButton.addEventListener("click", openColchaoExpanded);
  }
  updateBatchSaveButton();
}

function openColchaoExpanded() {
  if (!state.colchao.records?.length) {
    toast("Carregue a planilha do colchão antes de expandir.");
    return;
  }
  const dialog = $("#colchaoExpandedDialog");
  if (!dialog) return;
  const rows = state.colchao.records;
  const headers = orderedColchaoHeaders(rows);
  renderColchaoExpandedExcelGrid(rows, headers);
  if (!dialog.open) dialog.showModal();
  const closeButton = $("#colchaoExpandedDialog [data-close-colchao-expanded]");
  if (closeButton && closeButton.dataset.bound !== "true") {
    closeButton.dataset.bound = "true";
    closeButton.addEventListener("click", () => dialog.close());
  }
}

function orderedColchaoHeaders(rows = []) {
  const allHeaders = [];
  rows.forEach((row) => {
    Object.keys(row || {}).forEach((header) => {
      if (header.startsWith("__")) return;
      if (!allHeaders.some((item) => normalizeSheetHeader(item) === normalizeSheetHeader(header))) {
        allHeaders.push(header);
      }
    });
  });
  const preferred = currentProfile().id === "beta"
    ? ["SUITID", "SUIT", "CLIENTE", "NOME", "CPF/CNPJ", "ACORDO", "PARCELAS", "COND PARCELADAS", "MÊS", "MES", "DATA DO VENCIMENTO", "CASH", "VALOR DO ACORDO", "STATUS", "OPERADOR", "OPERADORES", "OBS", "OBSERVAÇÕES", "OBSERVACOES"]
    : ["DEBIT ID", "CLIENTE", "NOME", "CPF/CNPJ", "ACORDO", "PARCELAS", "COND PARCELADAS", "DATA DO VENCIMENTO", "MÊS", "MES", "VALOR DO ACORDO", "STATUS", "OPERADOR", "OPERADORES", "OBS", "OBSERVAÇÕES", "OBSERVACOES"];
  const ordered = [];
  preferred.forEach((wanted) => {
    const found = allHeaders.find((header) => normalizeSheetHeader(header) === normalizeSheetHeader(wanted));
    if (found && !ordered.some((header) => normalizeSheetHeader(header) === normalizeSheetHeader(found))) {
      ordered.push(found);
    }
  });
  allHeaders
    .filter((header) => !ordered.some((item) => normalizeSheetHeader(item) === normalizeSheetHeader(header)))
    .sort((a, b) => a.localeCompare(b, "pt-BR", { numeric: true }))
    .forEach((header) => ordered.push(header));
  return ordered;
}

function normalizeSheetHeader(header) {
  return String(header || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .trim();
}

export function resetColchaoCompletoPage() {
  state.colchao.completo.page = 1;
  loadColchaoPage();
}

export function clearColchaoQuickFilters() {
  ["colchaoFullSearch", "colchaoFilterOperador", "colchaoFilterStatus", "colchaoFilterVencimento"].forEach((id) => {
    const control = $(`#${id}`);
    if (control) control.value = "";
  });
  resetColchaoCompletoPage();
}

function colchaoQueryParams() {
  return new URLSearchParams({
    all: "1",
    profile: state.colchao.profile || "alpha",
    sheet: selectedSheet(),
    search: $("#colchaoFullSearch")?.value.trim() || "",
    operador: $("#colchaoFilterOperador")?.value.trim() || "",
    status: $("#colchaoFilterStatus")?.value.trim() || "",
    vencimento: $("#colchaoFilterVencimento")?.value.trim() || "",
  });
}

function renderCompletoPagination() {
  const info = $("#colchaoPageInfo");
  if (!info) return;
  const total = state.colchao.completo.total || 0;
  info.textContent = `${total.toLocaleString("pt-BR")} registro(s)`;
  const activeFilters = [
    $("#colchaoFullSearch")?.value,
    $("#colchaoFilterOperador")?.value,
    $("#colchaoFilterStatus")?.value,
    $("#colchaoFilterVencimento")?.value,
  ].filter(Boolean).length;
  const clearButton = $("#colchaoClearQuickFiltersBtn");
  clearButton?.classList.toggle("hidden", activeFilters === 0);
  if (!Object.keys(state.colchao.pendingStatusChanges).length) {
    const stateLabel = $("#colchaoSheetState");
    if (stateLabel) stateLabel.textContent = activeFilters ? `${activeFilters} filtro(s) ativo(s)` : "Sem alterações pendentes";
  }
}

function syncCompletoOperatorFilter(rows = []) {
  const select = $("#colchaoFilterOperador");
  if (!select) return;
  const selected = select.value;
  const operators = new Set([...select.options].map((option) => option.value).filter(Boolean));
  rows.forEach((row) => {
    const operator = firstValue(row, ["OPERADOR", "OPERADORES"]);
    if (operator) operators.add(operator);
  });
  select.innerHTML = `<option value="">Todos os operadores</option>${[...operators]
    .sort((left, right) => left.localeCompare(right, "pt-BR"))
    .map((operator) => `<option value="${escapeAttr(operator)}">${escapeHtml(operator)}</option>`)
    .join("")}`;
  if (operators.has(selected)) select.value = selected;
}

function renderSheetSelect() {
  const select = $("#colchaoSheetSelect");
  if (!select) return;
  const profile = currentProfile();
  select.classList.toggle("hidden", profile.sheets.length === 0 || state.colchao.page !== "completo");
  if (!profile.sheets.length) {
    select.innerHTML = "";
    return;
  }
  if (!state.colchao.sheet) state.colchao.sheet = profile.sheets[0];
  select.innerHTML = profile.sheets.map((sheet) => `<option value="${escapeAttr(sheet)}" ${selectedSheet() === sheet ? "selected" : ""}>${escapeHtml(sheet)}</option>`).join("");
}

function renderAgreementForm() {
  const form = $("#colchaoAgreementForm");
  if (!form) return;
  const profileId = state.colchao.profile || "alpha";
  const fields = agreementFields();
  const mount = $("#colchaoDynamicAgreementFields");
  if (!mount) return;
  if (form.dataset.profile !== profileId) form.reset();
  form.dataset.profile = profileId;
  const sections = agreementSections(fields);
  mount.innerHTML = sections.map(({ title, fields: sectionFields }) => `<section class="colchao-form-section ${sectionFields.some((field) => field.type === "textarea") ? "colchao-observation-section" : ""}">
    <h2>${escapeHtml(title)}</h2>
    <div class="colchao-form-grid">${sectionFields.map(renderAgreementField).join("")}</div>
  </section>`).join("");
  const sheets = (state.colchao.config?.sheet_options || currentProfile().sheets || []).filter(Boolean);
  if (sheets.length > 1) {
    mount.querySelector(".colchao-form-section .colchao-form-grid")?.insertAdjacentHTML("beforeend", `<label>Base de destino<select name="sheet">${sheets.map((sheet) => `<option value="${escapeAttr(sheet)}" ${selectedSheet() === sheet ? "selected" : ""}>${escapeHtml(sheet)}</option>`).join("")}</select></label>`);
  }
  renderAgreementSummaryStructure(fields);
  bindColchaoAgreementUX(form);
  updateColchaoAgreementUX();
}

function agreementFields() {
  return [...(state.colchao.config?.fields || [])]
    .filter((field) => field.enabled !== false)
    .sort((left, right) => Number(left.order || 0) - Number(right.order || 0));
}

function agreementSections(fields) {
  const groups = [
    { title: "Identificação", roles: new Set(["identifier", "client", "document", "process"]) },
    { title: "Condições do acordo", roles: new Set(["agreement_type", "total_value", "entry_value", "installment_count", "first_due_date", "operator"]) },
    { title: "Informações complementares", roles: new Set(["notes"]) },
  ];
  const assigned = new Set();
  const result = groups.map((group) => {
    const sectionFields = fields.filter((field) => group.roles.has(String(field.role || "").toLowerCase()));
    sectionFields.forEach((field) => assigned.add(field.key));
    return { title: group.title, fields: sectionFields };
  }).filter((group) => group.fields.length);
  const extras = fields.filter((field) => !assigned.has(field.key));
  if (extras.length) result.push({ title: "Outros dados", fields: extras });
  return result;
}

function renderAgreementField(field) {
  const required = field.required ? " required" : "";
  const common = `name="${escapeAttr(field.key)}" data-colchao-field="${escapeAttr(field.key)}" data-colchao-role="${escapeAttr(field.role || "")}"${required}`;
  let control = `<input type="text" ${common}>`;
  if (field.type === "select") {
    control = `<select ${common}><option value="">Selecione</option>${(field.options || []).map((option) => `<option value="${escapeAttr(option)}">${escapeHtml(option)}</option>`).join("")}</select>`;
  } else if (field.type === "textarea") {
    control = `<textarea rows="2" ${common} placeholder="Informações complementares"></textarea>`;
  } else if (field.type === "date") {
    control = `<input type="date" ${common}>`;
  } else if (field.type === "number") {
    control = `<input type="number" inputmode="numeric" min="0" step="1" ${common}>`;
  } else if (field.type === "money") {
    control = `<input type="text" inputmode="decimal" placeholder="0,00" ${common}>`;
  }
  return `<label class="${field.type === "textarea" ? "wide" : ""}">${escapeHtml(field.label || field.key)}${field.required ? " *" : ""}${control}</label>`;
}

function agreementControlByRole(form, role) {
  return form.querySelector(`[data-colchao-role="${role}"]`);
}

function renderAgreementSummaryStructure(fields) {
  const summary = $("#colchaoAgreementSummary");
  if (!summary) return;
  const roles = new Set(fields.map((field) => String(field.role || "").toLowerCase()));
  const items = [];
  if (roles.has("total_value")) items.push(["Valor total", "colchaoSummaryTotal"]);
  if (roles.has("entry_value")) items.push(["Entrada", "colchaoSummaryEntry"]);
  if (roles.has("total_value")) items.push(["Saldo parcelado", "colchaoSummaryBalance"]);
  if (roles.has("installment_count")) items.push(["Parcelas", "colchaoSummaryInstallments"]);
  if (roles.has("total_value") && roles.has("installment_count")) items.push(["Valor estimado", "colchaoSummaryInstallmentValue"]);
  if (roles.has("first_due_date")) {
    items.push(["Primeiro vencimento", "colchaoSummaryFirstDue"]);
    if (roles.has("installment_count")) items.push(["Último vencimento", "colchaoSummaryLastDue"]);
  }
  if (roles.has("operator")) items.push(["Operador", "colchaoSummaryOperator"]);
  if (!items.length) items.push(["Campos preenchidos", "colchaoSummaryFilled"]);
  summary.innerHTML = items.map(([label, id]) => `<div><dt>${label}</dt><dd id="${id}">-</dd></div>`).join("");
}

function bindColchaoAgreementUX(form) {
  if (form.dataset.uxBound === "true") return;
  form.dataset.uxBound = "true";
  form.addEventListener("input", (event) => {
    event.target.classList.remove("is-invalid");
    event.target.removeAttribute("aria-invalid");
    showColchaoAgreementError("");
    if (event.target.tagName === "TEXTAREA") {
      event.target.style.height = "auto";
      event.target.style.height = `${Math.max(58, Math.min(event.target.scrollHeight, 130))}px`;
    }
    updateColchaoAgreementUX();
  });
  form.addEventListener("change", updateColchaoAgreementUX);
  form.addEventListener("reset", () => window.requestAnimationFrame(() => {
    form.querySelectorAll(".is-invalid").forEach((control) => control.classList.remove("is-invalid"));
    showColchaoAgreementError("");
    updateColchaoAgreementUX();
  }));
}

function updateColchaoAgreementUX() {
  const form = $("#colchaoAgreementForm");
  if (!form) return;
  const required = visibleRequiredAgreementControls(form);
  const filled = required.filter((control) => String(control.value || "").trim()).length;
  const progress = $("#colchaoAgreementProgress");
  if (progress) progress.textContent = `${filled} de ${required.length} campos obrigatórios preenchidos`;
  const submit = $("#colchaoAgreementSubmitBtn");
  if (submit && submit.textContent !== "Salvando...") submit.disabled = filled < required.length;

  const totalControl = agreementControlByRole(form, "total_value");
  const entryControl = agreementControlByRole(form, "entry_value");
  const installmentControl = agreementControlByRole(form, "installment_count");
  const dueControl = agreementControlByRole(form, "first_due_date");
  const operatorControl = agreementControlByRole(form, "operator");
  const total = parseAgreementMoney(totalControl?.value);
  const entry = parseAgreementMoney(entryControl?.value);
  const installments = Math.max(0, Number.parseInt(installmentControl?.value || "0", 10) || 0);
  const balance = Math.max(0, total - entry);
  const estimated = installments <= 1 ? total : balance / Math.max(1, installments - 1);
  const firstDue = parseAgreementDate(dueControl?.value);
  const lastDue = firstDue && installments ? addAgreementMonths(firstDue, installments - 1) : null;

  setAgreementSummary("#colchaoSummaryProfile", currentProfile().name);
  setAgreementSummary("#colchaoSummaryTotal", formatAgreementMoney(total));
  setAgreementSummary("#colchaoSummaryEntry", formatAgreementMoney(entry));
  setAgreementSummary("#colchaoSummaryBalance", formatAgreementMoney(balance));
  setAgreementSummary("#colchaoSummaryInstallments", installments ? String(installments) : "0");
  setAgreementSummary("#colchaoSummaryInstallmentValue", formatAgreementMoney(estimated));
  setAgreementSummary("#colchaoSummaryFirstDue", formatAgreementDate(firstDue));
  setAgreementSummary("#colchaoSummaryLastDue", formatAgreementDate(lastDue));
  setAgreementSummary("#colchaoSummaryOperator", operatorControl?.value.trim() || "Não informado");
  setAgreementSummary("#colchaoSummaryFilled", `${filled} de ${required.length}`);
}

function validateColchaoAgreement(form) {
  form.querySelectorAll(".is-invalid").forEach((control) => {
    control.classList.remove("is-invalid");
    control.removeAttribute("aria-invalid");
  });
  const missing = visibleRequiredAgreementControls(form).find((control) => !String(control.value || "").trim());
  if (missing) return invalidAgreement("Preencha todos os campos obrigatórios.", missing);
  const totalControl = agreementControlByRole(form, "total_value");
  const entryControl = agreementControlByRole(form, "entry_value");
  const installmentControl = agreementControlByRole(form, "installment_count");
  const dueControl = agreementControlByRole(form, "first_due_date");
  const total = parseAgreementMoney(totalControl?.value);
  const entry = parseAgreementMoney(entryControl?.value);
  const installments = Number.parseInt(installmentControl?.value || "0", 10) || 0;
  if (totalControl && total <= 0) return invalidAgreement("O valor total deve ser maior que zero.", totalControl);
  if (entryControl && entry < 0) return invalidAgreement("O valor da entrada não pode ser negativo.", entryControl);
  if (entryControl && totalControl && entry > total) return invalidAgreement("O valor da entrada não pode superar o valor total.", entryControl);
  if (installmentControl && installments <= 0) return invalidAgreement("A quantidade de parcelas deve ser maior que zero.", installmentControl);
  if (dueControl && !parseAgreementDate(dueControl.value)) return invalidAgreement("Informe uma data de vencimento válida.", dueControl);
  return { valid: true };
}

function invalidAgreement(message, control) {
  control?.classList.add("is-invalid");
  control?.setAttribute("aria-invalid", "true");
  return { valid: false, message, control };
}

function visibleRequiredAgreementControls(form) {
  return [...form.querySelectorAll("input[required], select[required], textarea[required]")]
    .filter((control) => !control.disabled && !control.closest(".hidden"));
}

function showColchaoAgreementError(message) {
  const target = $("#colchaoAgreementError");
  if (!target) return;
  target.textContent = message || "";
  target.classList.toggle("hidden", !message);
}

function parseAgreementMoney(value) {
  const text = String(value || "").replace(/R\$/gi, "").replace(/\s/g, "").trim();
  if (!text) return 0;
  const normalized = text.includes(",") ? text.replace(/\./g, "").replace(",", ".") : text;
  const number = Number(normalized.replace(/[^\d.-]/g, ""));
  return Number.isFinite(number) ? number : 0;
}

function formatAgreementMoney(value) {
  return Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function parseAgreementDate(value) {
  if (!value) return null;
  const date = new Date(`${value}T12:00:00`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatAgreementDate(value) {
  return value ? value.toLocaleDateString("pt-BR") : "-";
}

function addAgreementMonths(value, months) {
  const result = new Date(value);
  const day = result.getDate();
  result.setDate(1);
  result.setMonth(result.getMonth() + months);
  result.setDate(Math.min(day, new Date(result.getFullYear(), result.getMonth() + 1, 0).getDate()));
  return result;
}

function setAgreementSummary(selector, value) {
  const target = $(selector);
  if (target) target.textContent = value;
}


