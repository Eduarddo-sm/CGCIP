import { apiGet, apiPost } from "./api.js?v=20260714-module-contract-1";

const monthFormatter = new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric", timeZone: "UTC" });
const dateFormatter = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" });
const moneyFormatter = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

function parseDate(value) {
  return new Date(`${value}T12:00:00Z`);
}

function monthLabel(value) {
  const text = monthFormatter.format(parseDate(value));
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function normalizeSearch(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function statusLabel(value) {
  return value === "AGUARDANDO_PAGAMENTO" ? "Aguardando pagamento" : "Proposta";
}

export async function initMonthRollover({ onConfirmed } = {}) {
  const dialog = document.querySelector("#monthRolloverDialog");
  if (!dialog || dialog.open) return false;
  const data = await apiGet("/api/producao/virada-mensal");
  if (!data.required) return false;

  const form = dialog.querySelector("#monthRolloverForm");
  const list = dialog.querySelector("#monthRolloverList");
  const search = dialog.querySelector("#monthRolloverSearch");
  const selectAll = dialog.querySelector("#monthRolloverSelectAll");
  const acknowledgement = dialog.querySelector("#monthRolloverAcknowledgement");
  const submit = dialog.querySelector("#monthRolloverConfirmBtn");
  const error = dialog.querySelector("#monthRolloverError");
  const selectedCount = dialog.querySelector("#monthRolloverSelectedCount");
  const remainingCount = dialog.querySelector("#monthRolloverRemainingCount");

  dialog.querySelector("#monthRolloverSource").textContent = monthLabel(data.competencia_origem);
  dialog.querySelector("#monthRolloverTarget").textContent = monthLabel(data.competencia_destino);
  dialog.querySelector("#monthRolloverDeadline").textContent = `2o dia util - ${dateFormatter.format(parseDate(data.prazo))}`;
  dialog.querySelector("#monthRolloverDescription").textContent = `Classifique os casos encerrados em ${monthLabel(data.competencia_origem)}.`;
  list.innerHTML = data.items.map((item) => `
    <article class="month-rollover-row" data-rollover-id="${item.id}" data-search="${escapeHtml(normalizeSearch(`${item.cliente} ${item.identificador}`))}">
      <span class="month-rollover-client"><strong>${escapeHtml(item.cliente)}</strong><small>${escapeHtml(item.identificador || "Sem identificador")}</small></span>
      <span class="month-rollover-detail"><small>Valor do acordo</small><strong>${moneyFormatter.format(Number(item.valor_total_acordo || 0))}</strong></span>
      <span class="month-rollover-detail"><small>Vencimento</small><strong>${item.data_vencimento ? dateFormatter.format(parseDate(item.data_vencimento)) : "Nao informado"}</strong></span>
      <span class="month-rollover-original"><small>Status anterior</small><strong>${statusLabel(item.status)}</strong></span>
      <span class="month-rollover-decision" role="radiogroup" aria-label="Classificacao de ${escapeHtml(item.cliente)}">
        <label><input type="radio" name="rolloverDecision-${item.id}" value="QUEBRA"><span>Quebra</span></label>
        <label><input type="radio" name="rolloverDecision-${item.id}" value="PROPOSTA_NEGADA"><span>Proposta negada</span></label>
      </span>
      <label class="month-rollover-next-month">
        <input type="checkbox" name="rolloverNextMonth-${item.id}">
        <span>Levar para ${escapeHtml(monthLabel(data.competencia_destino))}</span>
      </label>
    </article>
  `).join("");

  const rows = () => [...list.querySelectorAll(".month-rollover-row")];
  const decisions = () => rows().map((row) => ({
    producao_id: Number(row.dataset.rolloverId),
    status: row.querySelector("input[type=radio]:checked")?.value || "",
    jogar_proximo_mes: row.querySelector('.month-rollover-next-month input[type="checkbox"]').checked,
  }));
  const updateCounts = () => {
    const classified = decisions().filter((item) => item.status).length;
    selectedCount.textContent = `${classified} classificado${classified === 1 ? "" : "s"}`;
    remainingCount.textContent = `${data.items.length - classified} aguardam decisao`;
  };

  list.onchange = updateCounts;
  search.oninput = () => {
    const query = normalizeSearch(search.value);
    list.querySelectorAll(".month-rollover-row").forEach((row) => {
      row.hidden = Boolean(query) && !row.dataset.search.includes(query);
    });
  };
  selectAll.onclick = () => {
    rows().filter((row) => !row.hidden).forEach((row) => {
      row.querySelector('input[value="QUEBRA"]').checked = true;
    });
    updateCounts();
  };
  dialog.oncancel = (event) => event.preventDefault();
  dialog.onclick = (event) => {
    if (event.target === dialog) event.preventDefault();
  };
  form.onsubmit = async (event) => {
    event.preventDefault();
    error.hidden = true;
    if (!acknowledgement.checked) {
      acknowledgement.reportValidity();
      return;
    }
    const monthlyDecisions = decisions();
    if (monthlyDecisions.some((item) => !item.status)) {
      error.textContent = "Classifique todos os casos como Quebra ou Proposta negada.";
      error.hidden = false;
      return;
    }
    submit.disabled = true;
    submit.textContent = "Processando virada...";
    try {
      await apiPost("/api/producao/virada-mensal/confirmar", { decisoes: monthlyDecisions });
      dialog.close();
      await onConfirmed?.();
    } catch (requestError) {
      error.textContent = requestError.message;
      error.hidden = false;
    } finally {
      submit.disabled = false;
      submit.textContent = "Confirmar e continuar";
    }
  };
  search.value = "";
  acknowledgement.checked = false;
  error.hidden = true;
  updateCounts();
  dialog.showModal();
  return true;
}
