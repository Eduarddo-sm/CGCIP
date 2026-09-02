import { clampPercent, competenciaLabel, formatMoney, formatPercent } from "./formatters.js?v=20260714-module-contract-1";

export function renderProductionMetrics({ items, competencia, metaPagamento, isAlpha }) {
  const metricFor = (statusValue = null) => {
    const scopedItems = statusValue ? items.filter((item) => item.status === statusValue) : items;
    return {
      count: scopedItems.length,
      value: scopedItems.reduce((sum, item) => sum + Number(item.valor_total_acordo || 0), 0),
    };
  };
  const paidMetric = metricFor("PAGAMENTO_REALIZADO");
  const paidGoalValue = items
    .filter((item) => item.status === "PAGAMENTO_REALIZADO")
    .reduce((sum, item) => sum + Number(isAlpha ? item.valor_total_acordo || 0 : item.valor_ho || 0), 0);
  const projectedGoalValue = items
    .filter((item) => ["AGUARDANDO_PAGAMENTO", "PAGAMENTO_REALIZADO"].includes(item.status))
    .reduce((sum, item) => sum + Number(isAlpha ? item.valor_total_acordo || 0 : item.valor_ho || 0), 0);
  const meta = Number(metaPagamento || 0);
  const goalPercent = meta > 0 ? (paidGoalValue / meta) * 100 : 0;
  const projectionLabel = isAlpha ? "Projeção em pagamentos" : "Projeção em honorários";
  const paidCompactLabel = isAlpha ? "Total pago" : "Honorários pagos";

  return `
    <div class="metric-stack">
      ${renderMetricCard("Acordos", metricFor(), competenciaLabel(competencia), "total")}
      ${renderMetricCard("Pagamentos", paidMetric, "Realizados", "paid")}
      ${renderMetricCard("Aguardando pagamento", metricFor("AGUARDANDO_PAGAMENTO"), "Em acompanhamento", "waiting")}
      ${renderMetricCard("Quebras", metricFor("QUEBRA"), "Acordos quebrados", "broken")}
      ${renderMetricCard("Propostas", metricFor("PROPOSTA"), "Em aberto", "proposal")}
      ${renderMetricCard("Propostas negadas", metricFor("PROPOSTA_NEGADA"), "Negadas", "denied")}
    </div>
    <article class="production-goal-card">
      <div>
        <p class="goal-eyebrow">Meta do negociador</p>
        <strong>${formatMoney(meta)}</strong>
        <div class="goal-compact-row">
          <span>
            <small>Meta</small>
            <b>${formatMoney(meta)}</b>
          </span>
          <span>
            <small>${paidCompactLabel}</small>
            <b>${formatMoney(paidGoalValue)}</b>
          </span>
          <span>
            <small>Meta alcançada</small>
            <b>${formatPercent(goalPercent)}</b>
          </span>
        </div>
        <div class="goal-details">
          <span>
            <small>${projectionLabel}</small>
            <b>${formatMoney(projectedGoalValue)}</b>
          </span>
          <span>
            <small>Total pago em honorários</small>
            <b>${formatMoney(paidGoalValue)}</b>
          </span>
          <span>
            <small>Percentual da meta</small>
            <b>${formatPercent(goalPercent)}</b>
          </span>
        </div>
      </div>
      <div class="goal-progress" aria-label="Progresso da meta">
        <span style="width:${clampPercent(goalPercent)}%"></span>
      </div>
    </article>
  `;
}

function renderMetricCard(label, metric, note = "", tone = "neutral") {
  return `
    <article class="metric-card metric-card--${tone}">
      <div class="metric-topline">
        <span class="metric-dot"></span>
        <p class="metric-label">${label}</p>
      </div>
      <p class="metric-amount">${formatMoney(metric.value)}</p>
      <div class="metric-footer">
        <span>${note}</span>
        <strong>${metric.count} caso${metric.count === 1 ? "" : "s"}</strong>
      </div>
    </article>
  `;
}
