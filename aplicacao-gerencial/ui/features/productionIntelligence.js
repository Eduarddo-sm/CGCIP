import { api } from "../core/api.js";
import { $ } from "../core/dom.js";
import { state } from "../core/state.js";
import { toast } from "../core/toast.js";

const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 2 });
const integer = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
let initialized = false;
let filterTimer = null;
let drawerRequestId = 0;
let activeWallet = "";
let activeWalletTrendMetric = "total_value";
let activeExecutiveTrendMetric = "paid_honorarios";
let activeAnnualMetric = "total_value";
let activeMonthlyMetric = "total_value";
const allComparisonMonths = Array.from({ length: 12 }, (_, index) => index + 1);
const comparisonMonthNames = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
const activeAnnualMonths = new Set(allComparisonMonths);
const activeMonthlyMonths = new Set(allComparisonMonths);
const activeAnnualYears = new Set();
const activeMonthlyYears = new Set();
let agreementDetailState = { payload: null, context: "", sortKey: "", sortDirection: "" };

const walletPriority = ["GAMMA", "ALPHA", "BETA"];
const walletTrendMetrics = {
  total_value: { label: "Produção total", short: "Total" },
  paid_honorarios: { label: "Honorários recebidos", short: "H.O." },
  paid_value: { label: "Pagamentos realizados", short: "Pagamentos" },
  cash_value: { label: "Acordos à vista", short: "À vista" },
  installment_total: { label: "Acordos parcelados", short: "Parcelados" },
  breaks_value: { label: "Quebras", short: "Quebras" },
  negated_value: { label: "Propostas negadas", short: "Negadas" },
};
const advancedFilterConfig = [
  { id: "analyticsWalletFilter", label: "Carteira" },
  { id: "analyticsNegotiatorFilter", label: "Negociador" },
  { id: "analyticsStatusFilter", label: "Status" },
  { id: "analyticsTypeFilter", label: "Tipo" },
];
const walletDescriptions = {
  GAMMA: "Produção, entradas e evolução dos honorários da carteira Instituicao Gamma.",
  ALPHA: "Entradas, base negociada e atingimento das metas por portfólio.",
  BETA: "Composição entre acordos à vista e parcelados, entradas e relevância por polo.",
};

export function initProductionIntelligence() {
  if (initialized || !$("#productionIntelligenceContent")) return;
  initialized = true;
  const today = new Date();
  $("#analyticsMonthFilter").value = String(today.getMonth() + 1);
  $("#analyticsYearFilter").innerHTML = `<option value="${today.getFullYear()}">${today.getFullYear()}</option>`;

  document.querySelectorAll("[data-analysis-page]").forEach((button) => {
    button.addEventListener("click", () => showProductionIntelligencePage(button.dataset.analysisPage));
  });
  document.querySelectorAll("[data-analysis-jump]").forEach((button) => {
    button.addEventListener("click", () => showProductionIntelligencePage(button.dataset.analysisJump));
  });
  ["analyticsPeriodScopeFilter", "analyticsWalletFilter", "analyticsMonthFilter", "analyticsYearFilter", "analyticsNegotiatorFilter", "analyticsStatusFilter", "analyticsTypeFilter"].forEach((id) => {
    $(`#${id}`)?.addEventListener("change", () => {
      if (id === "analyticsPeriodScopeFilter") syncPeriodControls();
      updateActiveFilters();
      window.clearTimeout(filterTimer);
      filterTimer = window.setTimeout(() => loadProductionIntelligence({ force: true }), 120);
    });
  });
  $("#analyticsRefreshBtn")?.addEventListener("click", () => loadProductionIntelligence({ force: true }));
  $("#analyticsClearFiltersBtn")?.addEventListener("click", clearFilters);
  $("#analyticsFiltersToggleBtn")?.addEventListener("click", toggleAdvancedFilters);
  $("#analyticsPreviousMonthBtn")?.addEventListener("click", () => navigateMonth(-1));
  $("#analyticsNextMonthBtn")?.addEventListener("click", () => navigateMonth(1));
  $("#analyticsActiveFilters")?.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-clear-analytics-filter]");
    if (!chip) return;
    const control = $(`#${chip.dataset.clearAnalyticsFilter}`);
    if (!control) return;
    control.value = "";
    control.dispatchEvent(new Event("change", { bubbles: true }));
  });
  $("#analyticsDrawerClose")?.addEventListener("click", closeDrawer);
  $("#analyticsDrawerBody")?.addEventListener("click", handleAgreementSort);
  $("#analyticsWalletTrendMetric")?.addEventListener("change", (event) => {
    activeWalletTrendMetric = event.target.value;
    const wallet = (state.analytics.data?.wallet_analysis || []).find((entry) => entry.wallet === activeWallet);
    if (wallet) renderWalletTrend(wallet, activeWallet);
  });
  $("#analyticsExecutiveTrendMetric")?.addEventListener("change", (event) => {
    activeExecutiveTrendMetric = event.target.value;
    if (state.analytics.data) {
      renderTrend(
        state.analytics.data.daily || [],
        state.analytics.data.summary || {},
        state.analytics.data.period || {},
      );
    }
  });
  $("#analyticsAnnualMetric")?.addEventListener("change", (event) => {
    activeAnnualMetric = event.target.value;
    renderAnnualComparison(state.analytics.data?.comparisons || {});
  });
  $("#analyticsMonthlyMetric")?.addEventListener("change", (event) => {
    activeMonthlyMetric = event.target.value;
    renderMonthlyComparison(state.analytics.data?.comparisons || {});
  });
  setupComparisonMonthSelector("analyticsAnnualMonths", activeAnnualMonths, () => {
    renderAnnualComparison(state.analytics.data?.comparisons || {});
  });
  setupComparisonMonthSelector("analyticsMonthlyMonths", activeMonthlyMonths, () => {
    renderMonthlyComparison(state.analytics.data?.comparisons || {});
  });
  setupComparisonYearSelector("analyticsAnnualYears", activeAnnualYears, () => {
    renderAnnualComparison(state.analytics.data?.comparisons || {});
  });
  setupComparisonYearSelector("analyticsMonthlyYears", activeMonthlyYears, () => {
    renderMonthlyComparison(state.analytics.data?.comparisons || {});
  });
  $("#productionIntelligenceContent")?.addEventListener("click", handleInsightClick);
  $("#productionIntelligenceContent")?.addEventListener("keydown", (event) => {
    if (!["Enter", " "].includes(event.key)) return;
    const target = event.target.closest("[data-wallet-trend-date], [data-executive-trend-date]");
    if (!target) return;
    event.preventDefault();
    target.click();
  });
}

export async function loadProductionIntelligence({ force = false } = {}) {
  if (!$("#productionIntelligenceContent")) return;
  if (state.analytics.loading && !force) return;
  const requestId = ++state.analytics.requestId;
  state.analytics.loading = true;
  setLoading(true);
  const params = new URLSearchParams({
    periodo: $("#analyticsPeriodScopeFilter")?.value || "month",
    carteira: $("#analyticsWalletFilter")?.value || "",
    mes: $("#analyticsMonthFilter")?.value || String(new Date().getMonth() + 1),
    ano: $("#analyticsYearFilter")?.value || String(new Date().getFullYear()),
    negociador: $("#analyticsNegotiatorFilter")?.value || "",
    status: $("#analyticsStatusFilter")?.value || "",
    tipo: $("#analyticsTypeFilter")?.value || "",
  });
  try {
    const payload = await api(`/api/analise/producao?${params}`);
    if (requestId !== state.analytics.requestId) return;
    state.analytics.data = payload;
    populateOptions(payload.options || {}, payload.filters || {});
    render(payload);
  } catch (error) {
    if (requestId === state.analytics.requestId) {
      $("#analyticsWorkspace")?.classList.add("hidden");
      $("#analyticsEmpty")?.classList.remove("hidden");
      toast(error.message);
    }
  } finally {
    if (requestId === state.analytics.requestId) {
      state.analytics.loading = false;
      setLoading(false);
    }
  }
}

export function showProductionIntelligencePage(page = "executive") {
  const allowed = new Set(["executive", "negotiators", "wallets", "pipeline"]);
  state.analytics.page = allowed.has(page) ? page : "executive";
  document.querySelectorAll("[data-analysis-page]").forEach((button) => {
    button.classList.toggle("active", button.dataset.analysisPage === state.analytics.page);
  });
  document.querySelectorAll("[data-analysis-panel]").forEach((panel) => {
    panel.classList.toggle("hidden", panel.dataset.analysisPanel !== state.analytics.page);
  });
}

function clearFilters() {
  const today = new Date();
  $("#analyticsWalletFilter").value = "";
  $("#analyticsPeriodScopeFilter").value = "month";
  $("#analyticsMonthFilter").value = String(today.getMonth() + 1);
  $("#analyticsYearFilter").value = String(today.getFullYear());
  $("#analyticsNegotiatorFilter").value = "";
  $("#analyticsStatusFilter").value = "";
  $("#analyticsTypeFilter").value = "";
  syncPeriodControls();
  updateActiveFilters();
  loadProductionIntelligence({ force: true });
}

function syncPeriodControls() {
  const scope = $("#analyticsPeriodScopeFilter")?.value || "month";
  const journey = scope === "journey";
  const annual = scope === "year";
  $("#analyticsMonthNavigation")?.classList.toggle("hidden", journey);
  document.querySelectorAll(".analytics-month-only").forEach((element) => {
    element.classList.toggle("hidden", annual);
  });
  if ($("#analyticsMonthFilter")) $("#analyticsMonthFilter").disabled = scope !== "month";
  if ($("#analyticsYearFilter")) $("#analyticsYearFilter").disabled = journey;
}

function toggleAdvancedFilters() {
  const panel = $("#analyticsAdvancedFilters");
  const button = $("#analyticsFiltersToggleBtn");
  if (!panel || !button) return;
  const expanded = button.getAttribute("aria-expanded") !== "true";
  panel.classList.toggle("hidden", !expanded);
  button.setAttribute("aria-expanded", String(expanded));
}

function navigateMonth(offset) {
  const monthControl = $("#analyticsMonthFilter");
  const yearControl = $("#analyticsYearFilter");
  if (!monthControl || !yearControl || $("#analyticsPeriodScopeFilter")?.value !== "month") return;
  const current = new Date(Number(yearControl.value), Number(monthControl.value) - 1 + offset, 1);
  const year = String(current.getFullYear());
  if (![...yearControl.options].some((option) => option.value === year)) {
    yearControl.add(new Option(year, year));
    [...yearControl.options]
      .sort((left, right) => Number(right.value) - Number(left.value))
      .forEach((option) => yearControl.append(option));
  }
  monthControl.value = String(current.getMonth() + 1);
  yearControl.value = year;
  updateActiveFilters();
  loadProductionIntelligence({ force: true });
}

function updateActiveFilters() {
  const active = advancedFilterConfig.flatMap(({ id, label }) => {
    const control = $(`#${id}`);
    if (!control?.value) return [];
    const option = control.selectedOptions?.[0];
    return [{ id, label, value: option?.textContent?.trim() || control.value }];
  });
  const count = $("#analyticsActiveFilterCount");
  const root = $("#analyticsActiveFilters");
  if (count) {
    count.textContent = String(active.length);
    count.classList.toggle("hidden", !active.length);
  }
  if (!root) return;
  root.classList.toggle("hidden", !active.length);
  root.innerHTML = active.map((item) => `
    <button type="button" data-clear-analytics-filter="${escapeAttribute(item.id)}" title="Remover filtro ${escapeAttribute(item.label)}">
      <span>${escapeHtml(item.label)}</span>
      <strong>${escapeHtml(item.value)}</strong>
      <b aria-hidden="true">&times;</b>
    </button>`).join("");
}

function setLoading(loading) {
  $("#analyticsLoading")?.classList.toggle("hidden", !loading);
  $("#analyticsRefreshBtn")?.classList.toggle("is-loading", loading);
  if (loading && !state.analytics.data) $("#analyticsWorkspace")?.classList.add("hidden");
}

function populateOptions(options, selected) {
  updateSelect("#analyticsWalletFilter", [{ value: "", label: "Todas as carteiras" }, ...(options.wallets || []).map((item) => ({ value: item, label: item }))], selected.wallet || "");
  updateSelect("#analyticsYearFilter", (options.years || []).map((item) => ({ value: String(item), label: String(item) })), String(selected.year || ""));
  const wallet = selected.wallet || "";
  const users = (options.negotiators || []).filter((item) => !wallet || String(item.carteira || "").toUpperCase() === wallet);
  updateSelect("#analyticsNegotiatorFilter", [{ value: "", label: "Todos os negociadores" }, ...users.map((item) => ({ value: item.username, label: item.username }))], selected.negotiator || "");
  updateSelect("#analyticsStatusFilter", [{ value: "", label: "Todos os status" }, ...(options.statuses || [])], selected.status || "");
  updateSelect("#analyticsTypeFilter", [{ value: "", label: "Todos os tipos" }, ...(options.agreement_types || [])], selected.agreement_type || "");
  syncPeriodControls();
  updateActiveFilters();
}

function updateSelect(selector, items, selected) {
  const select = $(selector);
  if (!select) return;
  select.innerHTML = items.map((item) => `<option value="${escapeAttribute(item.value)}">${escapeHtml(item.label)}</option>`).join("");
  if ([...select.options].some((option) => option.value === String(selected))) select.value = String(selected);
}

function render(payload) {
  const hasData = Number(payload.summary?.agreements || 0) > 0;
  $("#analyticsPeriodLabel").textContent = payload.period?.label || "-";
  $("#analyticsEmpty")?.classList.toggle("hidden", hasData);
  $("#analyticsWorkspace")?.classList.toggle("hidden", !hasData);
  if (!hasData) return;
  renderKpis(payload.summary, payload.period || {});
  renderTrend(payload.daily || [], payload.summary, payload.period || {});
  renderAnnualComparison(payload.comparisons || {});
  renderMonthlyComparison(payload.comparisons || {});
  renderStatus(payload.status || []);
  renderGoal(payload.summary);
  renderNegotiators(payload.negotiators || []);
  renderWallets(payload.wallet_analysis || []);
  renderPipeline(payload.pipeline || {}, payload.quality || {});
  showProductionIntelligencePage(state.analytics.page);
}

function renderKpis(summary, period) {
  const comparisonLabel = period.scope === "year" ? "ano anterior" : "mes anterior";
  const cards = [
    ["Produção total", formatMoney(summary.total_value), delta(summary.comparison?.total_value, comparisonLabel), "blue"],
    ["Honorários pagos", formatMoney(summary.paid_honorarios), delta(summary.comparison?.paid_honorarios, comparisonLabel), "green"],
    ["Honorários projetados", formatMoney(summary.projected_honorarios), `${integer.format(summary.awaiting_count || 0)} aguardando`, "cyan"],
    ["Acordos", integer.format(summary.agreements || 0), delta(summary.comparison?.agreements, comparisonLabel), "violet"],
    ["Conversão", `${formatNumber(summary.conversion_rate)}%`, `${signed(summary.comparison?.conversion_rate)} p.p.`, "amber"],
    ["Ticket médio", formatMoney(summary.average_ticket), `Atualizado ${formatDateTime(summary.last_update)}`, "neutral"],
  ];
  $("#analyticsKpis").innerHTML = cards.map(([label, value, note, tone]) => `
    <article class="analytics-kpi analytics-tone-${tone}">
      <span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small>
    </article>`).join("");
}

function renderTrend(daily, summary, period) {
  const journey = period.granularity === "month";
  const metric = walletTrendMetrics[activeExecutiveTrendMetric] || walletTrendMetrics.paid_honorarios;
  const field = activeExecutiveTrendMetric;
  $("#analyticsTrendEyebrow").textContent = journey ? "Evolução histórica" : "Evolução no mês";
  $("#analyticsTrendTitle").textContent = metric.label;
  $("#analyticsTrendTotal").textContent = formatMoney(daily.reduce(
    (total, item) => total + Number(item[field] || 0),
    0,
  ));
  const root = $("#analyticsTrendChart");
  if (!daily.length) {
    root.innerHTML = emptyInline("Sem produção no período");
    return;
  }
  const visible = journey ? daily.slice(-24) : daily;
  const values = visible.map((item) => Number(item[field] || 0));
  const max = Math.max(...values, 1);
  const width = 920;
  const height = 270;
  const padding = { top: 28, right: 24, bottom: 44, left: 76 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const xAt = (index) => padding.left + (visible.length === 1 ? chartWidth / 2 : index * chartWidth / (visible.length - 1));
  const yAt = (value) => padding.top + chartHeight - (value / max * chartHeight);
  const points = visible.map((item, index) => ({
    item,
    value: values[index],
    x: xAt(index),
    y: yAt(values[index]),
  }));
  const line = points.map((point) => `${point.x},${point.y}`).join(" ");
  const area = `${padding.left},${padding.top + chartHeight} ${line} ${padding.left + chartWidth},${padding.top + chartHeight}`;
  const labelIndexes = new Set([0, Math.floor((visible.length - 1) / 2), visible.length - 1]);
  const grid = [0, .25, .5, .75, 1].map((ratio) => {
    const y = padding.top + chartHeight - chartHeight * ratio;
    return `<g class="analytics-wallet-chart-grid">
      <line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}"></line>
      <text x="${padding.left - 10}" y="${y + 3}" text-anchor="end">${escapeHtml(compactMoney(max * ratio))}</text>
    </g>`;
  }).join("");
  root.innerHTML = `
    <svg class="analytics-wallet-trend-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeAttribute(`Evolução de ${metric.label}`)}">
      ${grid}
      <polygon class="analytics-wallet-chart-area" points="${area}"></polygon>
      <polyline class="analytics-wallet-chart-line" points="${line}"></polyline>
      ${points.map(({ item, value, x, y }, index) => `
        <g class="analytics-wallet-chart-point" tabindex="0" role="button"
          aria-label="${escapeAttribute(`${formatTrendDate(item.date, period.granularity)}: ${formatMoney(value)}`)}"
          data-executive-trend-date="${escapeAttribute(item.date)}"
          data-executive-trend-metric="${escapeAttribute(field)}">
          <circle class="analytics-wallet-chart-hit" cx="${x}" cy="${y}" r="12"></circle>
          <circle class="analytics-wallet-chart-dot" cx="${x}" cy="${y}" r="4"></circle>
          <title>${escapeHtml(`${formatTrendDate(item.date, period.granularity)} · ${formatMoney(value)} · ${integer.format(trendMetricCount(item, field))} casos`)}</title>
          ${labelIndexes.has(index) ? `<text class="analytics-wallet-chart-label" x="${x}" y="${height - 15}" text-anchor="middle">${escapeHtml(formatTrendDate(item.date, period.granularity))}</text>` : ""}
        </g>`).join("")}
    </svg>
    <footer class="analytics-wallet-chart-footer">
      <span>${escapeHtml(metric.short)}</span>
      <strong>${integer.format(visible.reduce((total, item) => total + trendMetricCount(item, field), 0))} casos no período</strong>
    </footer>`;
}

function trendMetricCount(item, metricKey) {
  return Number(["paid_honorarios", "paid_value"].includes(metricKey) ? item.paid : item.agreements) || 0;
}

function renderAnnualComparison(comparisons) {
  const root = $("#analyticsAnnualComparison");
  if (!root) return;
  syncComparisonYearSelector("analyticsAnnualYears", activeAnnualYears, comparisons.years || []);
  const selectedMonths = (comparisons.monthly || []).filter((item) => activeAnnualMonths.has(Number(item.month)));
  const rows = selectedMonths.length
    ? [...activeAnnualYears].sort((left, right) => left - right).map((year) => ({
        year,
        ...aggregateComparisonYearMonths(selectedMonths, year),
      }))
    : [];
  if (!rows.length) {
    root.innerHTML = emptyInline("Sem base anual para comparar");
    return;
  }
  const values = rows.map((item) => Number(item[activeAnnualMetric] || 0));
  const max = Math.max(...values, 1);
  const previous = values.at(-2) || 0;
  const current = values.at(-1) || 0;
  const variation = previous ? ((current - previous) / previous) * 100 : null;
  root.innerHTML = `
    <div class="analytics-annual-summary">
      <span>${escapeHtml(metricLabel(activeAnnualMetric))}</span>
      <strong>${escapeHtml(formatComparisonValue(activeAnnualMetric, current))}</strong>
      <b class="${variation !== null && variation < 0 ? "is-negative" : ""}">${variation === null || rows.length < 2 ? "Sem base anterior" : `${signed(variation)}% vs. ${rows.at(-2).year}`}</b>
    </div>
    <div class="analytics-annual-bars">
      ${rows.map((item) => {
        const value = Number(item[activeAnnualMetric] || 0);
        return `<div class="analytics-annual-row">
          <strong>${escapeHtml(item.year)}</strong>
          <span><i style="width:${Math.max(value ? 2 : 0, value / max * 100)}%"></i></span>
          <b>${escapeHtml(formatComparisonValue(activeAnnualMetric, value))}</b>
        </div>`;
      }).join("")}
    </div>`;
}

function renderMonthlyComparison(comparisons) {
  const root = $("#analyticsMonthlyComparison");
  if (!root) return;
  syncComparisonYearSelector("analyticsMonthlyYears", activeMonthlyYears, comparisons.years || []);
  const rows = (comparisons.monthly || []).filter((item) => activeMonthlyMonths.has(Number(item.month)));
  if (!rows.length) {
    root.innerHTML = emptyInline("Sem base mensal para comparar");
    return;
  }
  const selectedYears = [...activeMonthlyYears].sort((left, right) => left - right);
  const values = rows.flatMap((item) => selectedYears.map((year) => Number(item.years?.[String(year)]?.[activeMonthlyMetric] || 0)));
  const max = Math.max(...values, 1);
  const width = 920;
  const height = 255;
  const padding = { top: 20, right: 18, bottom: 42, left: 58 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const groupWidth = chartWidth / rows.length;
  const barWidth = Math.min(20, Math.max(4, groupWidth * .72 / Math.max(selectedYears.length, 1)));
  const bars = rows.map((item, index) => {
    const center = padding.left + groupWidth * index + groupWidth / 2;
    const seriesWidth = selectedYears.length * barWidth;
    return `<g class="analytics-month-comparison-group">
      ${selectedYears.map((year, yearIndex) => {
        const value = Number(item.years?.[String(year)]?.[activeMonthlyMetric] || 0);
        const barHeight = value / max * chartHeight;
        const x = center - seriesWidth / 2 + yearIndex * barWidth;
        return `<rect x="${x}" y="${padding.top + chartHeight - barHeight}" width="${Math.max(2, barWidth - 2)}" height="${barHeight}" style="fill:${comparisonYearColor(yearIndex)}"><title>${escapeHtml(`${item.label} ${year}: ${formatComparisonValue(activeMonthlyMetric, value)}`)}</title></rect>`;
      }).join("")}
      <text x="${center}" y="${height - 16}" text-anchor="middle">${escapeHtml(String(item.label || "").slice(0, 3))}</text>
    </g>`;
  }).join("");
  root.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Comparativo mensal de ${escapeAttribute(metricLabel(activeMonthlyMetric))}">
      ${[0, .5, 1].map((ratio) => {
        const y = padding.top + chartHeight - chartHeight * ratio;
        return `<g class="analytics-comparison-grid-line"><line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}"></line><text x="${padding.left - 8}" y="${y + 3}" text-anchor="end">${escapeHtml(compactComparisonValue(activeMonthlyMetric, max * ratio))}</text></g>`;
      }).join("")}
      ${bars}
    </svg>
    <footer>${selectedYears.map((year, index) => `<span><i style="background:${comparisonYearColor(index)}"></i>${escapeHtml(year)}</span>`).join("")}</footer>`;
}

function setupComparisonMonthSelector(id, selectedMonths, onChange) {
  const root = $(`#${id}`);
  const menu = root?.querySelector(".analytics-month-selector-menu");
  if (!root || !menu) return;
  menu.innerHTML = `
    <label class="is-all"><input type="checkbox" data-all-months checked><span>Todos os meses</span></label>
    <div>${comparisonMonthNames.map((name, index) => `<label><input type="checkbox" value="${index + 1}" checked><span>${name}</span></label>`).join("")}</div>`;
  menu.addEventListener("change", (event) => {
    const input = event.target.closest("input");
    if (!input) return;
    const monthInputs = [...menu.querySelectorAll('input[value]')];
    if (input.matches("[data-all-months]")) {
      monthInputs.forEach((monthInput) => { monthInput.checked = input.checked; });
    }
    const checkedMonths = monthInputs.filter((monthInput) => monthInput.checked);
    if (!checkedMonths.length) {
      input.checked = true;
      return;
    }
    selectedMonths.clear();
    checkedMonths.forEach((monthInput) => selectedMonths.add(Number(monthInput.value)));
    const allInput = menu.querySelector("[data-all-months]");
    allInput.checked = selectedMonths.size === allComparisonMonths.length;
    allInput.indeterminate = selectedMonths.size > 0 && selectedMonths.size < allComparisonMonths.length;
    updateComparisonMonthSummary(root, selectedMonths);
    onChange();
  });
  updateComparisonMonthSummary(root, selectedMonths);
}

function updateComparisonMonthSummary(root, selectedMonths) {
  const summary = root.querySelector("summary span");
  if (!summary) return;
  if (selectedMonths.size === allComparisonMonths.length) {
    summary.textContent = "Todos os meses";
    return;
  }
  if (selectedMonths.size === 1) {
    const month = [...selectedMonths][0];
    summary.textContent = comparisonMonthNames[month - 1];
    return;
  }
  summary.textContent = `${selectedMonths.size} meses`;
}

function setupComparisonYearSelector(id, selectedYears, onChange) {
  const root = $(`#${id}`);
  const menu = root?.querySelector(".analytics-month-selector-menu");
  if (!root || !menu) return;
  menu.addEventListener("change", (event) => {
    const input = event.target.closest("input");
    if (!input) return;
    const yearInputs = [...menu.querySelectorAll('input[value]')];
    if (input.matches("[data-all-years]")) {
      yearInputs.forEach((yearInput) => { yearInput.checked = input.checked; });
    }
    const checkedYears = yearInputs.filter((yearInput) => yearInput.checked);
    if (!checkedYears.length) {
      input.checked = true;
      return;
    }
    selectedYears.clear();
    checkedYears.forEach((yearInput) => selectedYears.add(Number(yearInput.value)));
    syncComparisonYearChecks(root, selectedYears);
    updateComparisonYearSummary(root, selectedYears, yearInputs.length);
    onChange();
  });
}

function syncComparisonYearSelector(id, selectedYears, availableYears) {
  const root = $(`#${id}`);
  const menu = root?.querySelector(".analytics-month-selector-menu");
  if (!root || !menu) return;
  const years = [...new Set(availableYears.map(Number).filter(Boolean))].sort((left, right) => right - left);
  const signature = years.join(",");
  if (menu.dataset.years !== signature) {
    const previous = new Set([...selectedYears].filter((year) => years.includes(year)));
    selectedYears.clear();
    (previous.size ? previous : years).forEach((year) => selectedYears.add(year));
    menu.dataset.years = signature;
    menu.innerHTML = `<label class="is-all"><input type="checkbox" data-all-years><span>Todos os anos</span></label><div>${years.map((year) => `<label><input type="checkbox" value="${year}"><span>${year}</span></label>`).join("")}</div>`;
  }
  syncComparisonYearChecks(root, selectedYears);
  updateComparisonYearSummary(root, selectedYears, years.length);
}

function syncComparisonYearChecks(root, selectedYears) {
  const inputs = [...root.querySelectorAll('.analytics-month-selector-menu input[value]')];
  inputs.forEach((input) => { input.checked = selectedYears.has(Number(input.value)); });
  const allInput = root.querySelector("[data-all-years]");
  if (!allInput) return;
  allInput.checked = inputs.length > 0 && selectedYears.size === inputs.length;
  allInput.indeterminate = selectedYears.size > 0 && selectedYears.size < inputs.length;
}

function updateComparisonYearSummary(root, selectedYears, availableCount) {
  const summary = root.querySelector("summary span");
  if (!summary) return;
  if (selectedYears.size === availableCount) summary.textContent = "Todos os anos";
  else if (selectedYears.size === 1) summary.textContent = String([...selectedYears][0]);
  else summary.textContent = `${selectedYears.size} anos`;
}

function aggregateComparisonYearMonths(rows, year) {
  return aggregateComparisonMonths(rows.map((item) => ({ selected: item.years?.[String(year)] || {} })), "selected");
}

function comparisonYearColor(index) {
  return ["#94a3b8", "#7c3aed", "#0891b2", "#2563eb", "#10b981", "#d97706", "#dc2626"][index % 7];
}

function aggregateComparisonMonths(rows, side) {
  const result = {
    agreements: 0,
    total_value: 0,
    paid_honorarios: 0,
    paid_value: 0,
    cash_value: 0,
    installment_total: 0,
    breaks_value: 0,
    negated_value: 0,
    paid_count: 0,
    breaks_count: 0,
  };
  rows.forEach((item) => {
    const values = item[side] || {};
    Object.keys(result).forEach((key) => { result[key] += Number(values[key] || 0); });
  });
  const concluded = result.paid_count + result.breaks_count;
  result.conversion_rate = concluded ? result.paid_count / concluded * 100 : 0;
  return result;
}

function metricLabel(metric) {
  if (metric === "agreements") return "Quantidade de acordos";
  if (metric === "conversion_rate") return "Conversao";
  return walletTrendMetrics[metric]?.label || "Producao total";
}

function formatComparisonValue(metric, value) {
  if (metric === "agreements") return `${integer.format(Number(value || 0))} acordos`;
  if (metric === "conversion_rate") return `${formatNumber(value)}%`;
  return formatMoney(value);
}

function compactComparisonValue(metric, value) {
  if (metric === "agreements") return integer.format(Number(value || 0));
  if (metric === "conversion_rate") return `${formatNumber(value)}%`;
  return compactMoney(value);
}

function renderStatus(items) {
  const root = $("#analyticsStatusChart");
  root.innerHTML = items.map((item) => `
    <button type="button" class="analytics-status-row status-${escapeAttribute(item.key.toLowerCase())}" data-analytics-kind="status" data-analytics-key="${escapeAttribute(item.key)}">
      <span class="analytics-status-label"><i></i><strong>${escapeHtml(item.label)}</strong><small>${integer.format(item.count)} casos</small></span>
      <span class="analytics-status-value">${formatMoney(item.value)}</span>
      <span class="analytics-status-track"><i style="width:${Math.max(2, Number(item.share || 0))}%"></i></span>
    </button>`).join("") || emptyInline("Sem status no periodo");
}

function renderGoal(summary) {
  const percent = Number(summary.goal_percent || 0);
  const projectedPercent = Number(summary.goal) ? Number(summary.forecast || 0) / Number(summary.goal) * 100 : 0;
  $("#analyticsGoalContent").innerHTML = `
    <div class="analytics-goal-main"><strong>${formatNumber(percent)}%</strong><span>${formatMoney(summary.paid_honorarios)} de ${formatMoney(summary.goal)}</span></div>
    <div class="analytics-progress"><i style="width:${Math.min(100, percent)}%"></i></div>
    <div class="analytics-goal-foot"><span>Proje&ccedil;&atilde;o <strong>${formatMoney(summary.forecast)}</strong></span><span>Ritmo <strong>${formatNumber(projectedPercent)}%</strong></span></div>`;
}

function renderNegotiators(items) {
  $("#analyticsNegotiatorCount").textContent = `${integer.format(items.length)} profissionais`;
  $("#analyticsTopNegotiators").innerHTML = items.slice(0, 5).map((item, index) => `
    <button type="button" data-analytics-kind="negotiator" data-analytics-key="${escapeAttribute(item.username)}"><span>${index + 1}</span><div><strong>${escapeHtml(item.username)}</strong><small>${escapeHtml(item.wallet)} · ${formatNumber(item.goal_percent)}% da meta</small></div><b>${formatMoney(item.paid_honorarios)}</b></button>`).join("") || emptyInline("Sem negociadores no periodo");
  $("#analyticsNegotiatorRows").innerHTML = items.map((item, index) => `
    <tr tabindex="0" data-analytics-kind="negotiator" data-analytics-key="${escapeAttribute(item.username)}">
      <td>${index + 1}</td><td><strong>${escapeHtml(item.username)}</strong></td><td><span class="analytics-badge">${escapeHtml(item.wallet)}</span></td>
      <td>${integer.format(item.agreements)}</td><td>${formatMoney(item.total_value)}</td><td>${formatMoney(item.paid_honorarios)}</td>
      <td><span class="analytics-table-progress"><i style="width:${Math.min(100, item.goal_percent)}%"></i></span>${formatNumber(item.goal_percent)}%</td>
      <td>${formatNumber(item.conversion_rate)}%</td><td>${integer.format(item.breaks)}</td><td>${formatDateTime(item.last_update)}</td>
    </tr>`).join("");
}

function renderWallets(items) {
  const ordered = [...items].sort((left, right) => {
    const leftIndex = walletPriority.indexOf(left.wallet);
    const rightIndex = walletPriority.indexOf(right.wallet);
    if (leftIndex >= 0 || rightIndex >= 0) {
      return (leftIndex >= 0 ? leftIndex : 99) - (rightIndex >= 0 ? rightIndex : 99);
    }
    return String(left.wallet).localeCompare(String(right.wallet), "pt-BR");
  });
  if (!ordered.some((item) => item.wallet === activeWallet)) {
    activeWallet = ordered.find((item) => item.wallet === "GAMMA")?.wallet || ordered[0]?.wallet || "";
  }
  $("#analyticsWalletCount").textContent = `${integer.format(ordered.length)} carteiras`;
  $("#analyticsWalletTabs").innerHTML = ordered.map((item) => `
    <button type="button" data-wallet-tab="${escapeAttribute(item.wallet)}" class="${item.wallet === activeWallet ? "active" : ""}">
      <span>${escapeHtml(item.wallet.slice(0, 2))}</span>
      <strong>${escapeHtml(item.wallet)}</strong>
      <small>${integer.format(item.agreements)} acordos</small>
    </button>`).join("") || emptyInline("Sem carteiras no período");
  renderWalletDetail(ordered.find((item) => item.wallet === activeWallet));
}

function renderWalletDetail(item) {
  if (!item) return;
  const wallet = String(item.wallet || "").toUpperCase();
  const isGamma = wallet === "GAMMA";
  const portfolios = item.portfolios || [];
  const portfolioGoal = portfolios.reduce((total, entry) => total + Number(entry.goal || 0), 0);
  const portfolioBase = portfolios.reduce((total, entry) => total + Number(entry.base_value || 0), 0);
  const portfolioAttainment = portfolioGoal ? portfolioBase / portfolioGoal * 100 : 0;

  $("#analyticsWalletTitle").textContent = wallet;
  $("#analyticsWalletDescription").textContent = walletDescriptions[wallet]
    || "Produção, conversão, honorários e concentração da carteira.";
  $("#analyticsWalletExecutiveGrid")?.classList.toggle("wallet-gamma", isGamma);
  document.querySelectorAll(".analytics-wallet-gamma-panel").forEach((panel) => {
    panel.classList.toggle("hidden", !isGamma);
  });

  const common = {
    total: ["Produção total", formatMoney(item.total_value), `${integer.format(item.agreements)} acordos`, "blue"],
    entry: ["Entradas", formatMoney(item.entry_value), `${integer.format(item.installment_count)} parcelados`, "cyan"],
    paidHo: ["H.O. recebido", formatMoney(item.paid_honorarios), `${integer.format(item.paid_count)} pagamentos`, "green"],
    projectedHo: ["H.O. projetado", formatMoney(item.projected_honorarios), "Base válida no período", "violet"],
    conversion: ["Conversão", `${formatNumber(item.conversion_rate)}%`, `${integer.format(item.breaks)} quebras`, "amber"],
  };
  const cards = wallet === "ALPHA"
    ? [
        ["Base negociada", formatMoney(portfolioBase), "À vista + entradas parceladas", "blue"],
        common.entry,
        common.paidHo,
        ["Meta dos portfólios", formatMoney(portfolioGoal), `${formatNumber(portfolioAttainment)}% alcançado`, "violet"],
        common.projectedHo,
        common.conversion,
      ]
    : wallet === "BETA"
      ? [
          ["Produção total", formatMoney(item.total_value), `${integer.format(item.agreements)} acordos`, "blue"],
          ["À vista", formatMoney(item.cash_value), `${integer.format(item.cash_count)} acordos`, "green"],
          ["Entradas parceladas", formatMoney(item.installment_entry), `${integer.format(item.installment_count)} acordos`, "cyan"],
          common.paidHo,
          common.projectedHo,
          common.conversion,
        ]
      : [
          common.total,
          common.entry,
          ["Pagamentos realizados", formatMoney(item.paid_value), `${integer.format(item.paid_count)} acordos`, "green"],
          common.paidHo,
          common.projectedHo,
          common.conversion,
        ];
  $("#analyticsWalletKpis").innerHTML = cards.map(([label, value, note, tone]) => `
    <article class="analytics-wallet-kpi analytics-tone-${tone}">
      <span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small>
    </article>`).join("");

  renderWalletTrend(item, wallet);
  renderWalletMix(item, wallet);
  renderWalletPortfolios(portfolios, wallet);
  renderWalletNegotiators(item.negotiators || []);
  if (isGamma) renderWalletGamma(item);
}

function renderWalletTrend(item, wallet) {
  const trend = item.trend || [];
  const journey = state.analytics.data?.period?.granularity === "month";
  const metric = walletTrendMetrics[activeWalletTrendMetric] || walletTrendMetrics.total_value;
  const field = activeWalletTrendMetric;
  $("#analyticsWalletTrendTitle").textContent = metric.label;
  $("#analyticsWalletTrendTotal").textContent = formatMoney(trend.reduce(
    (total, entry) => total + Number(entry[field] || 0),
    0,
  ));
  if (!trend.length) {
    $("#analyticsWalletTrend").innerHTML = emptyInline("Sem evolução no período");
    return;
  }
  const visible = journey ? trend.slice(-18) : trend;
  const values = visible.map((entry) => Number(entry[field] || 0));
  const max = Math.max(...values, 1);
  const width = 920;
  const height = 270;
  const padding = { top: 28, right: 24, bottom: 44, left: 76 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const xAt = (index) => padding.left + (visible.length === 1 ? chartWidth / 2 : index * chartWidth / (visible.length - 1));
  const yAt = (value) => padding.top + chartHeight - (value / max * chartHeight);
  const points = visible.map((entry, index) => ({
    entry,
    value: values[index],
    x: xAt(index),
    y: yAt(values[index]),
  }));
  const line = points.map((point) => `${point.x},${point.y}`).join(" ");
  const area = `${padding.left},${padding.top + chartHeight} ${line} ${padding.left + chartWidth},${padding.top + chartHeight}`;
  const labelIndexes = new Set([0, Math.floor((visible.length - 1) / 2), visible.length - 1]);
  const grid = [0, .25, .5, .75, 1].map((ratio) => {
    const y = padding.top + chartHeight - chartHeight * ratio;
    return `<g class="analytics-wallet-chart-grid">
      <line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}"></line>
      <text x="${padding.left - 10}" y="${y + 3}" text-anchor="end">${escapeHtml(compactMoney(max * ratio))}</text>
    </g>`;
  }).join("");
  const pointMarkup = points.map(({ entry, value, x, y }, index) => `
    <g class="analytics-wallet-chart-point" tabindex="0" role="button"
      aria-label="${escapeAttribute(`${formatTrendDate(entry.date, journey ? "month" : "day")}: ${formatMoney(value)}`)}"
      data-wallet-trend-date="${escapeAttribute(entry.date)}"
      data-wallet-trend-metric="${escapeAttribute(field)}">
      <circle class="analytics-wallet-chart-hit" cx="${x}" cy="${y}" r="12"></circle>
      <circle class="analytics-wallet-chart-dot" cx="${x}" cy="${y}" r="4"></circle>
      <title>${escapeHtml(`${formatTrendDate(entry.date, journey ? "month" : "day")} · ${formatMoney(value)} · ${integer.format(trendMetricCount(entry, field))} casos`)}</title>
      ${labelIndexes.has(index) ? `<text class="analytics-wallet-chart-label" x="${x}" y="${height - 15}" text-anchor="middle">${escapeHtml(formatTrendDate(entry.date, journey ? "month" : "day"))}</text>` : ""}
    </g>`).join("");
  $("#analyticsWalletTrend").innerHTML = `
    <svg class="analytics-wallet-trend-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeAttribute(`Evolução de ${metric.label}`)}">
      ${grid}
      <polygon class="analytics-wallet-chart-area" points="${area}"></polygon>
      <polyline class="analytics-wallet-chart-line" points="${line}"></polyline>
      ${pointMarkup}
    </svg>
    <footer class="analytics-wallet-chart-footer">
      <span>${escapeHtml(metric.short)}</span>
      <strong>${integer.format(visible.reduce((total, entry) => total + trendMetricCount(entry, field), 0))} casos no período</strong>
    </footer>`;
}

function renderWalletMix(item, wallet) {
  const groups = [
    ["À vista", item.cash_count, item.cash_value, "green"],
    ["Parcelados", item.installment_count, item.installment_total, "blue"],
    ["Entradas parceladas", item.installment_count, item.installment_entry, "cyan"],
    ["Pagamentos", item.paid_count, item.paid_value, "violet"],
  ];
  const max = Math.max(...groups.map(([, , value]) => Number(value || 0)), 1);
  $("#analyticsWalletMixTitle").textContent = wallet === "ALPHA"
    ? "Origem da base negociada"
    : "Perfil financeiro dos acordos";
  $("#analyticsWalletMix").innerHTML = groups.map(([label, count, value, tone]) => `
    <article class="analytics-wallet-mix-row analytics-tone-${tone}">
      <div><span>${escapeHtml(label)}</span><strong>${formatMoney(value)}</strong></div>
      <small>${integer.format(count || 0)} casos</small>
      <i><b style="width:${Math.max(1.5, Number(value || 0) / max * 100)}%"></b></i>
    </article>`).join("");
}

function renderWalletPortfolios(items, wallet) {
  const panel = $("#analyticsWalletPortfolioPanel");
  const meaningful = items.filter((item) => item.portfolio_key !== "NAOINFORMADO");
  panel.classList.toggle("hidden", wallet === "GAMMA" || !meaningful.length);
  if (wallet === "GAMMA" || !meaningful.length) return;
  const alpha = wallet === "ALPHA";
  $("#analyticsWalletPortfolioEyebrow").textContent = alpha ? "Metas por portfólio" : "Distribuição por polo";
  $("#analyticsWalletPortfolioTitle").textContent = alpha
    ? "Produção e atingimento por portfólio"
    : "Relevância financeira por polo";
  $("#analyticsWalletPortfolioCount").textContent = `${integer.format(meaningful.length)} grupos`;
  $("#analyticsWalletPortfolioHead").innerHTML = `<tr>
    <th>Portfólio</th><th>Acordos</th><th>Base relevante</th><th>H.O. recebido</th>
    ${alpha ? "<th>Meta</th><th>Atingimento</th>" : "<th>Participação</th>"}
  </tr>`;
  $("#analyticsWalletPortfolioRows").innerHTML = meaningful.slice(0, 18).map((entry) => `
    <tr>
      <td><strong title="${escapeAttribute(entry.portfolio)}">${escapeHtml(entry.portfolio)}</strong></td>
      <td>${integer.format(entry.agreements)}</td>
      <td>${formatMoney(entry.base_value)}</td>
      <td>${formatMoney(entry.paid_honorarios)}</td>
      ${alpha
        ? `<td>${entry.goal ? formatMoney(entry.goal) : "-"}</td><td><span class="analytics-wallet-goal"><i style="width:${Math.min(100, Number(entry.goal_attainment || 0))}%"></i></span>${formatNumber(entry.goal_attainment)}%</td>`
        : `<td>${formatNumber(entry.share)}%</td>`}
    </tr>`).join("");
}

function renderWalletNegotiators(items) {
  $("#analyticsWalletNegotiators").innerHTML = items.slice(0, 8).map((item, index) => `
    <button type="button" data-analytics-kind="negotiator" data-analytics-key="${escapeAttribute(item.username)}">
      <span>${index + 1}</span>
      <div><strong>${escapeHtml(item.username)}</strong><small>${integer.format(item.agreements)} acordos · ${formatNumber(item.conversion_rate)}% conversão</small></div>
      <b>${formatMoney(item.paid_honorarios)}</b>
    </button>`).join("") || emptyInline("Sem negociadores no período");
}

function renderWalletGamma(item) {
  const honorarios = item.honorarios || {};
  const honorarioItems = [
    ["H.O. esperado", honorarios.expected, "Referência contratual de 10%"],
    ["H.O. flexibilizado", honorarios.flexibilized, `${formatNumber(honorarios.effective_percent)}% efetivos`],
    ["H.O. recebido", honorarios.received, `${integer.format(item.paid_count || 0)} pagamentos`],
    ["Aguardando pagamento", honorarios.awaiting, "Potencial ainda não realizado"],
    ["Diferença para referência", honorarios.difference, "Esperado menos flexibilizado"],
  ];
  $("#analyticsWalletGammaHonorarios").innerHTML = honorarioItems.map(([label, value, note], index) => `
    <article class="${index === 2 ? "is-highlight" : ""}">
      <span>${escapeHtml(label)}</span>
      <strong>${formatMoney(value)}</strong>
      <small>${escapeHtml(note)}</small>
    </article>`).join("");

  const funnel = item.funnel || [];
  const maxFunnel = Math.max(...funnel.map((stage) => Number(stage.count || 0)), 1);
  $("#analyticsWalletGammaFunnel").innerHTML = funnel.map((stage, index) => `
    <button type="button" data-analytics-kind="status" data-analytics-key="${escapeAttribute(stage.key)}">
      <span>${index + 1}</span>
      <div><strong>${escapeHtml(stage.label)}</strong><small>${formatMoney(stage.total_value)} · H.O. ${formatMoney(stage.honorarios)}</small></div>
      <b>${integer.format(stage.count)} casos</b>
      <i><u style="width:${Math.max(2, Number(stage.count || 0) / maxFunnel * 100)}%"></u></i>
    </button>`).join("") || emptyInline("Sem movimentações no funil");

  const gecors = item.gecors || [];
  $("#analyticsWalletGammaGecorCount").textContent = `${integer.format(gecors.length)} grupos`;
  $("#analyticsWalletGammaGecors").innerHTML = gecors.slice(0, 12).map((entry) => `
    <button type="button" data-analytics-kind="wallet-dimension" data-dimension="gecor" data-analytics-key="${escapeAttribute(entry.value)}">
      <strong>${escapeHtml(entry.value)}</strong>
      <span><i style="width:${Math.max(2, Number(entry.share || 0))}%"></i></span>
      <b>${formatMoney(entry.total_value)}</b>
      <small>${integer.format(entry.agreements)} acordos · ${formatNumber(entry.conversion_rate)}%</small>
    </button>`).join("") || emptyInline("Nenhum GECOR informado");

  const states = item.states || [];
  $("#analyticsWalletGammaStatesCount").textContent = `${integer.format(states.length)} estados`;
  $("#analyticsWalletGammaStates").innerHTML = states.map((entry) => `
    <tr tabindex="0" data-analytics-kind="wallet-dimension" data-dimension="uf" data-analytics-key="${escapeAttribute(entry.value)}">
      <td><strong>${escapeHtml(entry.value)}</strong></td>
      <td>${integer.format(entry.agreements)}</td>
      <td>${formatMoney(entry.total_value)}</td>
      <td>${formatMoney(entry.entry_value)}</td>
      <td>${formatMoney(entry.paid_honorarios)}</td>
      <td>${formatNumber(entry.conversion_rate)}%</td>
      <td><span class="analytics-wallet-state-share"><i style="width:${Math.min(100, Number(entry.share || 0))}%"></i></span>${formatNumber(entry.share)}%</td>
    </tr>`).join("") || `<tr><td colspan="7">Nenhum estado informado no período.</td></tr>`;
}

function renderPipeline(pipeline, quality) {
  const counts = pipeline.counts || {};
  $("#analyticsOverdueCount").textContent = integer.format(counts.overdue || 0);
  $("#analyticsDueSoonCount").textContent = integer.format(counts.due_soon || 0);
  $("#analyticsStagnantCount").textContent = integer.format(counts.stagnant || 0);
  $("#analyticsQualityScore").textContent = `${formatNumber(quality.score || 0)}%`;
  const issues = Number(quality.missing_client || 0) + Number(quality.missing_identifier || 0) + Number(quality.zero_value || 0);
  $("#analyticsQualityCaption").textContent = issues ? `${integer.format(issues)} inconsistencias` : "sem inconsistencias";
  renderRiskList("#analyticsOverdueList", pipeline.overdue || [], "vencido");
  renderRiskList("#analyticsDueSoonList", pipeline.due_soon || [], "vence em");
  renderRiskList("#analyticsStagnantList", pipeline.stagnant || [], "sem atualizar ha");
  $("#analyticsQualityDetails").innerHTML = [
    ["Cliente ausente", quality.missing_client], ["Identificador ausente", quality.missing_identifier],
    ["Valor zerado", quality.zero_value], ["Ocorrencias duplicadas", quality.duplicate_occurrences],
  ].map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${integer.format(value || 0)}</strong></article>`).join("");
}

function renderRiskList(selector, items, prefix) {
  $(selector).innerHTML = items.slice(0, 12).map((item) => `
    <button type="button" data-analytics-kind="risk" data-analytics-key="${item.id}"><span><strong>${escapeHtml(item.client)}</strong><small>${escapeHtml(item.negotiator)} · ${escapeHtml(item.wallet)}</small></span><b>${formatMoney(item.value)}<small>${escapeHtml(prefix)} ${integer.format(item.days || 0)} dias</small></b></button>`).join("") || emptyInline("Nenhum caso nesta fila");
}

async function handleInsightClick(event) {
  const executiveTrendPoint = event.target.closest("[data-executive-trend-date]");
  if (executiveTrendPoint && state.analytics.data) {
    const date = executiveTrendPoint.dataset.executiveTrendDate;
    const metricKey = executiveTrendPoint.dataset.executiveTrendMetric || activeExecutiveTrendMetric;
    const metric = walletTrendMetrics[metricKey] || walletTrendMetrics.paid_honorarios;
    const item = (state.analytics.data.daily || []).find((entry) => entry.date === date);
    if (!item) return;
    openDrawer(metric.label, formatTrendDate(date, state.analytics.data?.period?.granularity || "day"), {
      data: date,
      metrica: metric.label,
      valor: item[metricKey] || 0,
      casos: trendMetricCount(item, metricKey),
    });
    await loadAgreementDetails({
      selectedDate: date,
      metric: metricKey,
      wallet: $("#analyticsWalletFilter")?.value || "",
      context: "day",
    });
    return;
  }
  const trendPoint = event.target.closest("[data-wallet-trend-date]");
  if (trendPoint && state.analytics.data) {
    const date = trendPoint.dataset.walletTrendDate;
    const metricKey = trendPoint.dataset.walletTrendMetric || activeWalletTrendMetric;
    const metric = walletTrendMetrics[metricKey] || walletTrendMetrics.total_value;
    const wallet = (state.analytics.data.wallet_analysis || []).find((entry) => entry.wallet === activeWallet);
    const item = (wallet?.trend || []).find((entry) => entry.date === date);
    if (!item) return;
    openDrawer(metric.label, formatTrendDate(date, state.analytics.data?.period?.granularity || "day"), {
      carteira: activeWallet,
      data: date,
      metrica: metric.label,
      valor: item[metricKey] || 0,
      casos: trendMetricCount(item, metricKey),
    });
    await loadAgreementDetails({
      selectedDate: date,
      metric: metricKey,
      wallet: activeWallet,
      context: "day",
    });
    return;
  }
  const walletTab = event.target.closest("[data-wallet-tab]");
  if (walletTab && state.analytics.data) {
    activeWallet = walletTab.dataset.walletTab;
    renderWallets(state.analytics.data.wallet_analysis || []);
    return;
  }
  const target = event.target.closest("[data-analytics-kind]");
  if (!target || !state.analytics.data) return;
  const kind = target.dataset.analyticsKind;
  const key = target.dataset.analyticsKey;
  let item;
  let eyebrow;
  if (kind === "negotiator") {
    item = state.analytics.data.negotiators.find((entry) => entry.username === key);
    eyebrow = "Negociador";
  } else if (kind === "wallet") {
    item = state.analytics.data.wallets.find((entry) => entry.wallet === key);
    eyebrow = "Carteira";
  } else if (kind === "status") {
    item = state.analytics.data.status.find((entry) => entry.key === key);
    eyebrow = "Status";
  } else if (kind === "risk") {
    const groups = state.analytics.data.pipeline || {};
    item = [...(groups.overdue || []), ...(groups.due_soon || []), ...(groups.stagnant || [])].find((entry) => String(entry.id) === key);
    eyebrow = "Caso em atencao";
  } else if (kind === "wallet-dimension") {
    const wallet = (state.analytics.data.wallet_analysis || []).find((entry) => entry.wallet === activeWallet);
    const dimension = target.dataset.dimension;
    const collection = dimension === "uf" ? wallet?.states : wallet?.gecors;
    item = (collection || []).find((entry) => String(entry.value) === key);
    eyebrow = dimension === "uf" ? "Estado" : "GECOR";
  }
  if (!item) return;
  openDrawer(eyebrow, item.username || item.wallet || item.label || item.client || "Detalhes", item);
  if (kind === "negotiator") await loadAgreementDetails({ username: key, context: "negotiator" });
  if (kind === "status") await loadAgreementDetails({ status: key, context: "status" });
  if (kind === "wallet-dimension") {
    await loadAgreementDetails({
      dimension: target.dataset.dimension,
      dimensionValue: key,
      wallet: activeWallet,
      context: "dimension",
    });
  }
}

function openDrawer(eyebrow, title, item) {
  agreementDetailState = { payload: null, context: "", sortKey: "", sortDirection: "" };
  $("#analyticsDrawerEyebrow").textContent = eyebrow;
  $("#analyticsDrawerTitle").textContent = title;
  $("#analyticsDrawerBody").innerHTML = Object.entries(item).filter(([, value]) => typeof value !== "object").map(([key, value]) => `
    <div><span>${escapeHtml(labelFor(key))}</span><strong>${escapeHtml(formatDetail(key, value))}</strong></div>`).join("");
  $("#analyticsDrawer").classList.remove("hidden");
  $("#analyticsDrawer").setAttribute("aria-hidden", "false");
}

async function loadAgreementDetails({
  username = "",
  status = "",
  dimension = "",
  dimensionValue = "",
  wallet = "",
  selectedDate = "",
  metric = "",
  context,
}) {
  const requestId = ++drawerRequestId;
  const body = $("#analyticsDrawerBody");
  if (!body) return;
  const sectionTitle = context === "status"
    ? "Acordos neste status"
    : context === "dimension"
      ? "Acordos deste agrupamento"
      : context === "day"
        ? "Casos do período selecionado"
      : "Acordos do periodo";
  body.insertAdjacentHTML("beforeend", `
    <section class="analytics-drawer-agreements" data-negotiator-agreements>
      <header><div><span>${sectionTitle}</span><strong>Carregando...</strong></div></header>
      <div class="analytics-agreements-loading" aria-label="Carregando acordos"></div>
    </section>`);
  const params = currentAnalyticsParams();
  const endpoint = context === "status"
    ? "status"
    : context === "dimension"
      ? "dimensao"
      : context === "day"
        ? "dia"
        : "negociador";
  if (username) params.set("negociador", username);
  if (status) params.set("status", status);
  if (wallet) params.set("carteira", wallet);
  if (dimension) params.set("dimensao", dimension);
  if (dimensionValue) params.set("valor_dimensao", dimensionValue);
  if (selectedDate) params.set("data", selectedDate);
  if (metric) params.set("metrica", metric);
  try {
    const payload = await api(`/api/analise/producao/${endpoint}?${params}`);
    if (requestId !== drawerRequestId || $("#analyticsDrawer")?.classList.contains("hidden")) return;
    renderAgreementDetails(payload, context);
  } catch (error) {
    if (requestId !== drawerRequestId) return;
    const root = document.querySelector("[data-negotiator-agreements]");
    if (root) root.innerHTML = `<div class="analytics-agreements-empty">${escapeHtml(error.message || "Nao foi possivel carregar os acordos.")}</div>`;
  }
}

function currentAnalyticsParams() {
  return new URLSearchParams({
    periodo: $("#analyticsPeriodScopeFilter")?.value || "month",
    carteira: $("#analyticsWalletFilter")?.value || "",
    mes: $("#analyticsMonthFilter")?.value || String(new Date().getMonth() + 1),
    ano: $("#analyticsYearFilter")?.value || String(new Date().getFullYear()),
    negociador: $("#analyticsNegotiatorFilter")?.value || "",
    status: $("#analyticsStatusFilter")?.value || "",
    tipo: $("#analyticsTypeFilter")?.value || "",
  });
}

function formatTrendDate(value, granularity) {
  if (granularity !== "month") return formatDate(value);
  const date = new Date(`${String(value).slice(0, 10)}T12:00:00`);
  return Number.isNaN(date.getTime())
    ? String(value)
    : date.toLocaleDateString("pt-BR", { month: "short", year: "numeric" });
}

function renderAgreementDetails(payload, context) {
  const root = document.querySelector("[data-negotiator-agreements]");
  if (!root) return;
  agreementDetailState = { ...agreementDetailState, payload, context };
  const agreements = sortAgreementDetails(payload.agreements || []);
  const totalValue = agreements.reduce((total, item) => total + Number(item.agreement_value || 0), 0);
  const received = agreements.reduce((total, item) => total + Number(item.received_honorarios || 0), 0);
  const isStatus = context === "status";
  const showNegotiator = isStatus || context === "dimension" || context === "day";
  const sectionTitle = isStatus
    ? escapeHtml(payload.status_label || "Acordos neste status")
    : context === "dimension"
      ? "Acordos do agrupamento"
      : context === "day"
        ? "Casos do período selecionado"
        : "Acordos do periodo";
  root.innerHTML = `
    <header>
      <div><span>${sectionTitle}</span><strong>${integer.format(agreements.length)} acordos</strong></div>
      <small>${escapeHtml(payload.period?.label || "")}</small>
    </header>
    <div class="analytics-agreements-summary">
      <span>Valor total <strong>${formatMoney(totalValue)}</strong></span>
      <span>Honorarios recebidos <strong>${formatMoney(received)}</strong></span>
    </div>
    ${agreements.length ? `<div class="analytics-agreements-table-wrap"><table class="analytics-agreements-table">
      <thead><tr>
        ${agreementSortHeader("client", "Cliente", "text")}
        ${agreementSortHeader("identifier", "Contrato", "text")}
        ${agreementSortHeader("status_label", "Status", "text")}
        ${showNegotiator ? agreementSortHeader("negotiator", "Negociador", "text") : ""}
        ${agreementSortHeader("agreement_value", "Valor do acordo", "number")}
        ${agreementSortHeader("received_honorarios", "Honorarios recebidos", "number")}
      </tr></thead>
      <tbody>${agreements.map((item) => `<tr>
        <td title="${escapeAttribute(item.client)}">${escapeHtml(item.client)}</td>
        <td title="${escapeAttribute(item.identifier)}">${escapeHtml(item.identifier)}</td>
        <td title="${escapeAttribute(item.status_label)}">${escapeHtml(item.status_label)}</td>
        ${showNegotiator ? `<td title="${escapeAttribute(item.negotiator)}">${escapeHtml(item.negotiator)}</td>` : ""}
        <td>${formatMoney(item.agreement_value)}</td>
        <td>${formatMoney(item.received_honorarios)}</td>
      </tr>`).join("")}</tbody>
    </table></div>` : `<div class="analytics-agreements-empty">Nenhum acordo encontrado para o periodo.</div>`}`;
}

function handleAgreementSort(event) {
  const button = event.target.closest("[data-agreement-sort]");
  if (!button || !agreementDetailState.payload) return;
  const sortKey = button.dataset.agreementSort;
  const sortType = button.dataset.sortType || "text";
  const isSameColumn = agreementDetailState.sortKey === sortKey;
  agreementDetailState.sortKey = sortKey;
  agreementDetailState.sortDirection = isSameColumn
    ? (agreementDetailState.sortDirection === "asc" ? "desc" : "asc")
    : (sortType === "number" ? "desc" : "asc");
  renderAgreementDetails(agreementDetailState.payload, agreementDetailState.context);
}

function sortAgreementDetails(agreements) {
  const { sortKey, sortDirection } = agreementDetailState;
  if (!sortKey || !sortDirection) return agreements;
  const direction = sortDirection === "asc" ? 1 : -1;
  return agreements
    .map((agreement, index) => ({ agreement, index }))
    .sort((left, right) => {
      const leftValue = left.agreement[sortKey];
      const rightValue = right.agreement[sortKey];
      const comparison = ["agreement_value", "received_honorarios"].includes(sortKey)
        ? Number(leftValue || 0) - Number(rightValue || 0)
        : String(leftValue || "").localeCompare(String(rightValue || ""), "pt-BR", {
            sensitivity: "base",
            numeric: true,
          });
      return comparison === 0 ? left.index - right.index : comparison * direction;
    })
    .map(({ agreement }) => agreement);
}

function agreementSortHeader(key, label, type) {
  const active = agreementDetailState.sortKey === key;
  const direction = active ? agreementDetailState.sortDirection : "";
  const ariaSort = direction === "asc" ? "ascending" : direction === "desc" ? "descending" : "none";
  const nextDirection = active
    ? (direction === "asc" ? "decrescente" : "crescente")
    : (type === "number" ? "do maior para o menor" : "de A a Z");
  return `<th aria-sort="${ariaSort}"><button type="button" class="analytics-agreement-sort${active ? " is-active" : ""}" data-agreement-sort="${key}" data-sort-type="${type}" title="Ordenar ${nextDirection}"><span>${label}</span><i aria-hidden="true" data-direction="${direction}"></i></button></th>`;
}

function closeDrawer() {
  drawerRequestId += 1;
  agreementDetailState = { payload: null, context: "", sortKey: "", sortDirection: "" };
  $("#analyticsDrawer")?.classList.add("hidden");
  $("#analyticsDrawer")?.setAttribute("aria-hidden", "true");
}

function formatDetail(key, value) {
  if (["total_value", "paid_honorarios", "goal", "average_ticket", "value", "valor"].includes(key)) return formatMoney(value);
  if (key.includes("rate") || key.includes("percent") || key === "share") return `${formatNumber(value)}%`;
  if (key.includes("date") || key.includes("update")) return formatDateTime(value);
  return String(value ?? "-");
}

function labelFor(key) {
  const labels = { agreements: "Acordos", wallet: "Carteira", paid_count: "Pagamentos", paid_honorarios: "Honorarios pagos", total_value: "Producao total", goal: "Meta", goal_percent: "Percentual da meta", conversion_rate: "Conversao", average_ticket: "Ticket medio", breaks: "Quebras", negated: "Propostas negadas", last_update: "Ultima atualizacao", client: "Cliente", identifier: "Identificador", negotiator: "Negociador", status: "Status", due_date: "Vencimento", value: "Valor", count: "Quantidade", share: "Participacao", honorarios: "Honorarios" };
  return labels[key] || key.replaceAll("_", " ");
}

function delta(value, comparisonLabel = "mes anterior") {
  if (value === null || value === undefined) return "Sem base anterior";
  return `${signed(value)}% vs. ${comparisonLabel}`;
}

function signed(value) {
  const number = Number(value || 0);
  return `${number > 0 ? "+" : ""}${formatNumber(number)}`;
}

function formatMoney(value) { return money.format(Number(value || 0)); }
function compactMoney(value) {
  const number = Number(value || 0);
  if (Math.abs(number) >= 1_000_000) return `R$ ${formatNumber(number / 1_000_000)} mi`;
  if (Math.abs(number) >= 1_000) return `R$ ${formatNumber(number / 1_000)} mil`;
  return formatMoney(number);
}
function formatNumber(value) { return Number(value || 0).toLocaleString("pt-BR", { maximumFractionDigits: 2 }); }
function formatDate(value) {
  if (!value) return "-";
  const [year, month, day] = String(value).slice(0, 10).split("-");
  return year && month && day ? `${day}/${month}/${year}` : String(value);
}
function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? formatDate(value) : date.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}
function emptyInline(text) { return `<div class="analytics-inline-empty">${escapeHtml(text)}</div>`; }
function escapeHtml(value) { return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]); }
function escapeAttribute(value) { return escapeHtml(value).replace(/`/g, "&#96;"); }
