import { api } from "../core/api.js";
import { $ } from "../core/dom.js";
import { state } from "../core/state.js";
import { toast } from "../core/toast.js";

const integer = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
let initialized = false;
let filterTimer = null;
const dashboardLists = new Map();

const filterIds = ["defasagemWallet", "defasagemPhase", "defasagemPortfolioOperator", "defasagemUf", "defasagemGecor", "defasagemActionOperator", "defasagemRange", "defasagemAction"];
const reportFilterIds = ["defasagemReportOperational", "defasagemReportOperator", "defasagemReportType"];

export function initDefasagem() {
  if (initialized || !$("#defasagemContent")) return;
  initialized = true;
  document.querySelectorAll("[data-defasagem-page]").forEach((button) => button.addEventListener("click", () => showDefasagemPage(button.dataset.defasagemPage)));
  filterIds.forEach((id) => $(`#${id}`)?.addEventListener("change", scheduleReload));
  $("#defasagemSearch")?.addEventListener("input", scheduleReload);
  $("#defasagemRefreshBtn")?.addEventListener("click", () => loadDefasagem({ force: true }));
  $("#defasagemFiltersToggle")?.addEventListener("click", () => $("#defasagemFilters")?.classList.toggle("hidden"));
  $("#defasagemClearBtn")?.addEventListener("click", clearFilters);
  $("#defasagemError button")?.addEventListener("click", () => loadDefasagem({ force: true }));
  $("#defasagemCsvBtn")?.addEventListener("click", () => downloadReport("csv"));
  $("#defasagemXlsxBtn")?.addEventListener("click", () => downloadReport("xlsx"));
  $("#defasagemPrevBtn")?.addEventListener("click", () => changeRecordPage(-1));
  $("#defasagemNextBtn")?.addEventListener("click", () => changeRecordPage(1));
  $("#defasagemOpenRecordsBtn")?.addEventListener("click", () => openRecords());
  $("#defasagemPriorityClients")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-defasagem-client]");
    if (button) openRecords(button.dataset.defasagemClient || "");
  });
  $("#defasagemContent")?.addEventListener("click", (event) => {
    const metricButton = event.target.closest("[data-defasagem-operational]");
    if (metricButton) {
      openOperationalDetails(
        metricButton.dataset.defasagemOperational || "",
        metricButton.dataset.defasagemTitle || "Clientes monitorados",
      );
      return;
    }
    const listButton = event.target.closest("[data-defasagem-list]");
    if (listButton) openDashboardList(listButton.dataset.defasagemList);
  });
  $("#defasagemListDrawerClose")?.addEventListener("click", closeDashboardList);
  $("#defasagemListDrawer")?.addEventListener("click", (event) => {
    if (event.target.id === "defasagemListDrawer") closeDashboardList();
  });
}

function scheduleReload() {
  window.clearTimeout(filterTimer);
  state.defasagem.recordPage = 1;
  filterTimer = window.setTimeout(() => loadDefasagem({ forceView: true }), 220);
}

function params(extra = {}) {
  return new URLSearchParams({
    busca: $("#defasagemSearch")?.value || "",
    carteira: $("#defasagemWallet")?.value || "",
    fase: $("#defasagemPhase")?.value || "",
    nome_op: $("#defasagemPortfolioOperator")?.value || "",
    uf: $("#defasagemUf")?.value || "",
    gecor: $("#defasagemGecor")?.value || "",
    operador: $("#defasagemActionOperator")?.value || "",
    faixa: $("#defasagemRange")?.value || "",
    acionamento: $("#defasagemAction")?.value || "",
    ...extra,
  });
}

function reportParams() {
  const query = params();
  query.set("snapshot", state.defasagem.data?.meta?.snapshot_version || "");
  query.set("filtro_operacional", $("#defasagemReportOperational")?.value || "");
  query.set("operador_sem_retorno", $("#defasagemReportOperator")?.value || "");
  query.set("tipo_defasagem", $("#defasagemReportType")?.value || "");
  return query;
}

export async function loadDefasagem({ force = false, forceView = false } = {}) {
  if (!$("#defasagemContent")) return;
  if (state.defasagem.loading && !force) return;
  const requestId = ++state.defasagem.requestId;
  state.defasagem.loading = true;
  setLoading(true);
  hideError();
  try {
    const payload = await api(`/api/analise/defasagem/dashboard?${params(force ? { force: "1" } : {})}`);
    if (requestId !== state.defasagem.requestId) return;
    state.defasagem.data = payload;
    populateOptions(payload.options || {});
    renderDashboard(payload);
    if (forceView || state.defasagem.page !== "dashboard") await loadCurrentPage();
    showDefasagemPage(state.defasagem.page, { load: false });
  } catch (error) {
    if (requestId === state.defasagem.requestId) showError(error.message);
  } finally {
    if (requestId === state.defasagem.requestId) {
      state.defasagem.loading = false;
      setLoading(false);
    }
  }
}

export async function showDefasagemPage(page = "dashboard", options = {}) {
  const allowed = new Set(["dashboard", "operators", "links", "reports", "records"]);
  state.defasagem.page = allowed.has(page) ? page : "dashboard";
  document.querySelectorAll("[data-defasagem-page]").forEach((button) => button.classList.toggle("active", button.dataset.defasagemPage === state.defasagem.page));
  document.querySelectorAll("[data-defasagem-panel]").forEach((panel) => panel.classList.toggle("hidden", panel.dataset.defasagemPanel !== state.defasagem.page));
  if (options.load !== false && state.defasagem.data) await loadCurrentPage();
}

async function loadCurrentPage() {
  if (state.defasagem.page === "operators") return loadOperators();
  if (state.defasagem.page === "records") return loadRecords();
}

async function loadOperators() {
  const payload = await api(`/api/analise/defasagem/operators?${params()}`);
  $("#defasagemOperatorTotal").textContent = `${integer.format(payload.total || 0)} operadores`;
  $("#defasagemOperatorRows").innerHTML = (payload.items || []).map((item, index) => `<tr><td>${index + 1}</td><td><strong>${escapeHtml(item.operator)}</strong></td><td>${number(item.total_clientes)}</td><td><span class="defasagem-critical">${number(item.critical)}</span></td><td>${number(item.sem_acionamento)}</td><td>${number(item.negociacao_sem_retorno)}</td><td>${number(item.possivel_negocio_sem_retorno)}</td><td>${number(item.faixa_apos_1_ano)}</td></tr>`).join("") || emptyRow(8);
}

async function loadRecords() {
  const payload = await api(`/api/analise/defasagem/records?${params({ page: String(state.defasagem.recordPage), page_size: "100" })}`);
  state.defasagem.recordPages = payload.pages || 1;
  $("#defasagemRecordTotal").textContent = `${number(payload.total)} registros`;
  $("#defasagemPageLabel").textContent = `Pagina ${payload.page} de ${payload.pages}`;
  $("#defasagemPrevBtn").disabled = payload.page <= 1;
  $("#defasagemNextBtn").disabled = payload.page >= payload.pages;
  $("#defasagemRecordRows").innerHTML = (payload.items || []).map((item) => `<tr><td>${escapeHtml(item.contrato)}</td><td><strong>${escapeHtml(item.cliente)}</strong></td><td>${escapeHtml(item.carteira)}</td><td>${escapeHtml(item.fase)}</td><td>${escapeHtml(item.uf)}</td><td>${escapeHtml(item.nome_op)}</td><td>${escapeHtml(item.ultimo_acionamento)}</td><td>${formatDate(item.data_ultimo_acionamento)}</td><td>${escapeHtml(item.operador)}</td><td>${item.dias_sem_acionamento ?? "-"}</td><td><span class="defasagem-range">${cleanLabel(item.faixa_defasagem)}</span></td><td title="${escapeAttribute(cleanLabel(item.alerta_oportunidade))}">${cleanLabel(item.alerta_oportunidade)}</td></tr>`).join("") || emptyRow(12);
}

function changeRecordPage(delta) {
  const next = Math.max(1, Math.min(state.defasagem.recordPages, state.defasagem.recordPage + delta));
  if (next === state.defasagem.recordPage) return;
  state.defasagem.recordPage = next;
  loadRecords().catch((error) => toast(error.message));
}

function renderDashboard(payload) {
  const metrics = payload.metrics || {};
  const cards = [
    ["Clientes monitorados", metrics.total_clientes, "Base ativa nos filtros atuais", "primary", ""],
    ["Sem acionamento", metrics.sem_acionamento, "Prioridade máxima", "danger", "cliente_sem_acionamento"],
    ["Negociação sem retorno", metrics.negociacao_sem_retorno, `de ${number(metrics.negociacao_total)} negociações`, "warning", "negociacao_sem_retorno"],
    ["Possível negócio sem retorno", metrics.possivel_negocio_sem_retorno, `de ${number(metrics.possivel_negocio_total)} oportunidades`, "violet", "possivel_negocio_sem_retorno"],
  ];
  $("#defasagemKpis").innerHTML = cards.map(([label, value, note, tone, operational]) => `
    <button class="defasagem-kpi tone-${tone}" type="button" data-defasagem-operational="${escapeAttribute(operational)}" data-defasagem-title="${escapeAttribute(label)}">
      <span>${label}</span><strong>${number(value)}</strong><small>${note}</small><i aria-hidden="true">Abrir</i>
    </button>`).join("");
  $("#defasagemSummary").innerHTML = [
    ["Desinteresse sem retorno", metrics.desinteresse_sem_retorno, "desinteresse_sem_retorno"],
    ["Clientes críticos", metrics.clientes_criticos, "clientes_criticos"],
    ["Gatilhos vinculados", metrics.gatilhos_total, ""],
    ["Garantias vinculadas", metrics.garantias_total, ""],
  ].map(([label, value, operational]) => operational
    ? `<button type="button" data-defasagem-operational="${operational}" data-defasagem-title="${label}"><strong>${number(value)}</strong><span>${label}</span></button>`
    : `<div><strong>${number(value)}</strong><span>${label}</span></div>`).join("");
  renderBars("#defasagemRanges", [
    { label: "Ate 3 meses", value: metrics.faixa_ate_3_meses }, { label: "Ate 6 meses", value: metrics.faixa_ate_6_meses },
    { label: "Ate 1 ano", value: metrics.faixa_ate_1_ano }, { label: "Apos 1 ano", value: metrics.faixa_apos_1_ano },
  ]);
  renderPriorityClients(payload.priority_clients || []);
  renderDashboardList("#defasagemAgreementsOperators", "operators", "Clientes por operador", payload.counts?.operadores || []);
  renderDashboardList("#defasagemAgreementsUf", "ufs", "Clientes por UF", payload.counts?.ufs || []);
  renderDashboardList("#defasagemAgreementsGecor", "gecors", "Clientes por GECOR", payload.counts?.gecors || []);
  renderDashboardList("#defasagemOperatorPortfolioAlerts", "operatorAlerts", "Negociacoes por operador e carteira", (payload.operator_portfolio_alerts || []).map((item) => ({
    label: `${item.nome_op || "Sem operador"} · ${item.carteira || "Sem carteira"}`,
    value: item.total,
  })));
  renderDashboardList("#defasagemTriggers", "triggers", "Gatilhos mais frequentes", (payload.triggers || []).map((item) => ({ label: item.gatilho, value: item.quantidade })));
  renderDashboardList("#defasagemGuarantees", "guarantees", "Garantias encontradas", (payload.guarantees || []).map((item) => ({ label: item.tipo_garantia, value: item.quantidade })));
  renderLinkedAnalysis(payload.linked_analysis || {}, payload.triggers || [], payload.guarantees || []);
  const meta = payload.meta || {};
  $("#defasagemSourceMeta").textContent = `${number(meta.filtered)} clientes | atualizado ${formatDateTime(meta.loaded_at)}`;
}

function renderPriorityClients(items) {
  const root = $("#defasagemPriorityClients");
  root.innerHTML = items.map((item) => {
    const client = cleanLabel(item.cliente || "Cliente nao identificado");
    const days = item.dias_sem_acionamento == null ? "Sem acionamento" : `${number(item.dias_sem_acionamento)} dias`;
    return `<article><span class="defasagem-priority-marker ${priorityTone(item.prioridade_fila)}"></span><div class="defasagem-priority-main"><strong>${client}</strong><small>${cleanLabel(item.prioridade_fila)} · ${cleanLabel(item.alerta_oportunidade)}</small></div><div class="defasagem-priority-meta"><span>${escapeHtml(item.operador || "Sem operador")}</span><b>${days}</b></div><button class="secondary-btn compact" type="button" data-defasagem-client="${escapeAttribute(item.cliente || "")}">Ver na base</button></article>`;
  }).join("") || `<p class="defasagem-inline-empty">Nenhum cliente critico para os filtros atuais.</p>`;
}

function priorityTone(value) {
  const label = String(value || "").toLowerCase();
  if (label.includes("sem acionamento")) return "is-danger";
  if (label.includes("negociacao") || label.includes("negociação")) return "is-warning";
  if (label.includes("possivel") || label.includes("possível")) return "is-violet";
  return "is-neutral";
}

function openRecords(client = "") {
  if (client && $("#defasagemSearch")) $("#defasagemSearch").value = client;
  state.defasagem.recordPage = 1;
  showDefasagemPage("records");
}

function renderBars(selector, items) {
  const max = Math.max(...items.map((item) => Number(item.value || 0)), 1);
  const root = $(selector);
  if (!root) return;
  root.innerHTML = items.map((item) => `<div><span><strong>${cleanLabel(item.label)}</strong><b>${number(item.value)}</b></span><i><em style="width:${Math.max(2, Number(item.value || 0) / max * 100)}%"></em></i></div>`).join("") || `<p class="defasagem-inline-empty">Sem dados para exibir.</p>`;
}

function renderDashboardList(selector, key, title, items) {
  dashboardLists.set(key, { title, items });
  const button = document.querySelector(`[data-defasagem-list="${key}"]`);
  button?.classList.toggle("hidden", items.length <= 5);
  renderBars(selector, items.slice(0, 5));
}

function openDashboardList(key) {
  const list = dashboardLists.get(key);
  if (!list) return;
  $("#defasagemListDrawerTitle").textContent = list.title;
  $("#defasagemListDrawerContent").className = "defasagem-bars";
  renderBars("#defasagemListDrawerContent", list.items);
  $("#defasagemListDrawer")?.classList.remove("hidden");
}

async function openOperationalDetails(operational, title) {
  const drawer = $("#defasagemListDrawer");
  const content = $("#defasagemListDrawerContent");
  if (!drawer || !content) return;
  $("#defasagemListDrawerTitle").textContent = title;
  content.className = "defasagem-operational-list";
  content.innerHTML = `<div class="defasagem-drawer-loading">Carregando clientes...</div>`;
  drawer.classList.remove("hidden");
  try {
    const query = params({ page: "1", page_size: "100" });
    if (operational) query.set("filtro_operacional", operational);
    const payload = await api(`/api/analise/defasagem/records?${query}`);
    renderDrawerRecords(content, payload);
    if (Number(payload.total || 0) > (payload.items || []).length) {
      content.insertAdjacentHTML("beforeend", `<button class="secondary-btn" type="button" data-defasagem-open-records>Ver ${number(payload.total)} clientes na base detalhada</button>`);
      content.querySelector("[data-defasagem-open-records]")?.addEventListener("click", () => {
        closeDashboardList();
        openRecords();
      });
    }
  } catch (error) {
    content.innerHTML = `<div class="defasagem-drawer-error">${escapeHtml(error.message || "Não foi possível carregar os clientes.")}</div>`;
  }
}

function renderDrawerRecords(content, payload) {
  content.innerHTML = (payload.items || []).map((item) => `
    <article>
      <span class="defasagem-operational-rank">${escapeHtml(item.prioridade_fila || item.faixa_defasagem || "Monitorado")}</span>
      <strong>${escapeHtml(item.cliente || "Cliente não identificado")}</strong>
      <small>${escapeHtml(item.contrato || "Sem contrato")} · ${escapeHtml(item.carteira || "Sem carteira")}</small>
      <div><span>${escapeHtml(item.nome_op || "Sem operador")}</span><b>${item.dias_sem_acionamento == null ? "Sem acionamento" : `${number(item.dias_sem_acionamento)} dias`}</b></div>
    </article>`).join("") || `<p class="defasagem-inline-empty">Nenhum cliente encontrado.</p>`;
}

function closeDashboardList() {
  $("#defasagemListDrawer")?.classList.add("hidden");
  const content = $("#defasagemListDrawerContent");
  if (content) content.className = "defasagem-bars";
}

function renderLinkedAnalysis(analysis, triggers, guarantees) {
  const metrics = analysis.metrics || {};
  if ($("#defasagemLinkedTotal")) $("#defasagemLinkedTotal").textContent = `${number(analysis.total)} clientes`;
  renderBars("#defasagemLinkedRanges", [
    { label: "Ate 3 meses", value: metrics.faixa_ate_3_meses },
    { label: "Ate 6 meses", value: metrics.faixa_ate_6_meses },
    { label: "Ate 1 ano", value: metrics.faixa_ate_1_ano },
    { label: "Apos 1 ano", value: metrics.faixa_apos_1_ano },
    { label: "Sem acionamento", value: metrics.sem_acionamento },
  ]);
  renderBars("#defasagemLinkedSituations", [
    { label: "Negociacao s/ retorno", value: metrics.negociacao_sem_retorno },
    { label: "Possivel negocio s/ retorno", value: metrics.possivel_negocio_sem_retorno },
    { label: "Desinteresse s/ retorno", value: metrics.desinteresse_sem_retorno },
  ]);
  renderBars("#defasagemLinkedWallets", analysis.counts?.carteiras || []);
  renderBars("#defasagemLinkedOperators", analysis.counts?.operadores || []);
  renderBars("#defasagemLinkedTriggers", triggers.map((item) => ({ label: item.gatilho, value: item.quantidade })));
  renderBars("#defasagemLinkedGuarantees", guarantees.map((item) => ({ label: item.tipo_garantia, value: item.quantidade })));
  const rows = $("#defasagemLinkedRows");
  if (rows) rows.innerHTML = (analysis.items || []).map((item) => `<tr><td>${escapeHtml(item.contrato)}</td><td><strong>${escapeHtml(item.cliente)}</strong></td><td>${escapeHtml(item.carteira)}</td><td>${escapeHtml(item.nome_op)}</td><td>${cleanLabel(item.gatilhos || "-")}</td><td>${cleanLabel(item.garantias || "-")}</td><td>${cleanLabel(item.ultimo_acionamento)}</td><td>${formatDate(item.data_ultimo_acionamento)}</td><td>${item.dias_sem_acionamento ?? "-"}</td><td>${cleanLabel(item.faixa_defasagem)}</td><td><span class="defasagem-range">${cleanLabel(item.prioridade_fila)}</span></td></tr>`).join("") || emptyRow(11);
}

function populateOptions(options) {
  const mapping = { defasagemWallet: ["carteira", "Todas as carteiras"], defasagemPhase: ["fase", "Todas as fases"], defasagemPortfolioOperator: ["nome_op", "Todos os operadores"], defasagemUf: ["uf", "Todas as UFs"], defasagemGecor: ["gecor", "Todos os Gecors"], defasagemActionOperator: ["operador", "Quem tabulou"], defasagemRange: ["faixa_defasagem", "Todas as faixas"], defasagemAction: ["ultimo_acionamento", "Todos os acionamentos"], defasagemReportOperator: ["operadores_sem_retorno", "Todos os operadores"] };
  Object.entries(mapping).forEach(([id, [key, label]]) => {
    const select = $(`#${id}`); if (!select) return;
    const current = select.value;
    select.innerHTML = `<option value="">${label}</option>${(options[key] || []).map((item) => `<option value="${escapeAttribute(item)}">${cleanLabel(item)}</option>`).join("")}`;
    if ([...select.options].some((option) => option.value === current)) select.value = current;
  });
}

function clearFilters() {
  $("#defasagemSearch").value = "";
  [...filterIds, ...reportFilterIds].forEach((id) => { if ($(`#${id}`)) $(`#${id}`).value = ""; });
  state.defasagem.recordPage = 1;
  loadDefasagem({ forceView: true });
}

function downloadReport(extension) {
  const link = document.createElement("a");
  link.href = `/api/analise/defasagem/report.${extension}?${reportParams()}`;
  link.click();
}

function setLoading(value) {
  $("#defasagemLoading")?.classList.toggle("hidden", !value);
  $("#defasagemRefreshBtn")?.classList.toggle("is-loading", value);
  if (value && !state.defasagem.data) document.querySelectorAll("[data-defasagem-panel]").forEach((panel) => panel.classList.add("hidden"));
}
function showError(message) { const root = $("#defasagemError"); root?.classList.remove("hidden"); root?.querySelector("span")?.replaceChildren(document.createTextNode(message)); }
function hideError() { $("#defasagemError")?.classList.add("hidden"); }
function emptyRow(columns) { return `<tr><td colspan="${columns}" class="defasagem-table-empty">Nenhum registro encontrado.</td></tr>`; }
function number(value) { return integer.format(Number(value || 0)); }
function cleanLabel(value) { return escapeHtml(String(value ?? "-").replaceAll("Ã§", "ç").replaceAll("Ã£", "ã").replaceAll("Ã³", "ó").replaceAll("Ã­", "í").replaceAll("Ã©", "é").replaceAll("Ãº", "ú").replaceAll("Ãª", "ê").replaceAll("Ã", "à")); }
function formatDate(value) { if (!value) return "-"; const raw = String(value).slice(0, 10); const [y, m, d] = raw.split("-"); return d ? `${d}/${m}/${y}` : raw; }
function formatDateTime(value) { if (!value) return "-"; return new Date(value).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }); }
function escapeHtml(value) { return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char])); }
function escapeAttribute(value) { return escapeHtml(value).replace(/`/g, "&#96;"); }
