import { api } from "../core/api.js";
import { $ } from "../core/dom.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { state } from "../core/state.js";
import { toast } from "../core/toast.js";
import { money } from "./colchaoCore.js";

let searchTimer = null;
let bound = false;

export async function loadColchaoClients(force = false) {
  const root = $("#colchaoClientsGrid");
  if (!root) return;
  if (!force && state.colchao.cache.clients) {
    state.colchao.clients = state.colchao.cache.clients.items || [];
    renderColchaoClients();
    return;
  }
  root.innerHTML = `<div class="colchao-clients-loading">Carregando clientes e acordos...</div>`;
  const payload = await api(`/api/colchao/clientes?profile=${encodeURIComponent(state.colchao.profile || "alpha")}`);
  state.colchao.cache.clients = payload;
  state.colchao.clients = payload.items || [];
  renderColchaoClients();
}

export function bindColchaoClients() {
  if (bound || !$("#colchaoClientsGrid")) return;
  bound = true;
  $("#colchaoClientsSearch")?.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(renderColchaoClients, 120);
  });
  $("#colchaoClientsStatus")?.addEventListener("change", renderColchaoClients);
  $("#colchaoClientsSort")?.addEventListener("change", renderColchaoClients);
  $("#colchaoClientsRefreshBtn")?.addEventListener("click", async (event) => {
    event.currentTarget.disabled = true;
    try {
      await loadColchaoClients(true);
    } catch (error) {
      toast(error.message);
    } finally {
      event.currentTarget.disabled = false;
    }
  });
}

export function renderColchaoClients() {
  const root = $("#colchaoClientsGrid");
  if (!root) return;
  const query = normalize($("#colchaoClientsSearch")?.value);
  const status = $("#colchaoClientsStatus")?.value || "";
  const sort = $("#colchaoClientsSort")?.value || "priority";
  const items = (state.colchao.clients || []).filter((item) => {
    const matchesQuery = !query || normalize([item.client, item.identifier, item.document, item.operator].join(" ")).includes(query);
    const matchesStatus = !status
      || (status === "overdue" && item.overdue_count > 0)
      || (status === "active" && item.active_count > 0)
      || (status === "paid" && item.paid_count > 0)
      || (status === "broken" && item.broken_count > 0);
    return matchesQuery && matchesStatus;
  });
  sortClientItems(items, sort);
  const summary = $("#colchaoClientsSummary");
  if (summary) {
    const agreements = items.reduce((sum, item) => sum + numeric(item.agreement_count), 0);
    const overdue = items.reduce((sum, item) => sum + numeric(item.overdue_count), 0);
    const openValue = items.reduce((sum, item) => sum + numeric(item.open_value), 0);
    summary.innerHTML = `
      <span><small>Clientes</small><strong>${items.length.toLocaleString("pt-BR")}</strong></span>
      <span><small>Acordos</small><strong>${agreements.toLocaleString("pt-BR")}</strong></span>
      <span class="danger"><small>Parcelas vencidas</small><strong>${overdue.toLocaleString("pt-BR")}</strong></span>
      <span><small>Saldo em aberto</small><strong>${money(openValue)}</strong></span>`;
  }
  root.innerHTML = items.length ? `
    <div class="colchao-clients-list-head" aria-hidden="true">
      <span>Cliente</span><span>Situacao</span><span>Acordos</span><span>Vencidas</span><span>Saldo aberto</span><span>Proximo vencimento</span><span></span>
    </div>
    ${items.map(renderClientCard).join("")}` : `<div class="empty-state">Nenhum cliente encontrado para os filtros selecionados.</div>`;
  root.querySelectorAll("[data-colchao-client]").forEach((button) => {
    button.addEventListener("click", () => openClientDrawer(button.dataset.colchaoClient));
  });
}

function renderClientCard(item) {
  const nextDue = item.next_due_date ? formatDate(item.next_due_date) : "Sem parcela aberta";
  const statusClass = item.overdue_count ? "is-overdue" : item.active_count ? "is-active" : item.paid_count ? "is-paid" : "is-closed";
  const situation = item.overdue_count
    ? { label: "Vencido", className: "is-overdue" }
    : item.active_count
      ? { label: "Em dia", className: "is-current" }
      : item.paid_count
        ? { label: "Quitado", className: "is-paid" }
        : { label: "Encerrado", className: "is-closed" };
  return `
    <button class="colchao-client-card ${statusClass}" type="button" data-colchao-client="${escapeAttr(item.key)}">
      <span class="colchao-client-identity">
        <span class="colchao-client-avatar" aria-hidden="true">${escapeHtml(String(item.client || "C").slice(0, 1).toUpperCase())}</span>
        <span><strong>${escapeHtml(item.client)}</strong><small>${escapeHtml(item.identifier || "Sem identificador")}${item.document ? ` · ${escapeHtml(item.document)}` : ""}</small></span>
      </span>
      <span class="colchao-client-situation ${situation.className}">${situation.label}</span>
      <span class="colchao-client-metric"><strong>${numeric(item.agreement_count).toLocaleString("pt-BR")}</strong><small>${numeric(item.active_count)} ativo(s)</small></span>
      <span class="colchao-client-metric ${item.overdue_count ? "danger" : ""}"><strong>${numeric(item.overdue_count).toLocaleString("pt-BR")}</strong></span>
      <span class="colchao-client-metric"><strong>${money(numeric(item.open_value))}</strong></span>
      <span class="colchao-client-due"><strong>${escapeHtml(nextDue)}</strong></span>
      <span class="colchao-client-open" aria-hidden="true">›</span>
    </button>`;
}

function sortClientItems(items, sort) {
  const dateValue = (value) => value ? new Date(`${String(value).slice(0, 10)}T00:00:00`).getTime() : Number.MAX_SAFE_INTEGER;
  const nameSort = (left, right) => String(left.client || "").localeCompare(String(right.client || ""), "pt-BR", { sensitivity: "base" });
  const sorters = {
    next_due: (left, right) => dateValue(left.next_due_date) - dateValue(right.next_due_date) || nameSort(left, right),
    balance_desc: (left, right) => numeric(right.open_value) - numeric(left.open_value) || nameSort(left, right),
    agreements_desc: (left, right) => numeric(right.agreement_count) - numeric(left.agreement_count) || nameSort(left, right),
    name: nameSort,
    priority: (left, right) => numeric(right.overdue_count) - numeric(left.overdue_count)
      || numeric(right.active_count) - numeric(left.active_count)
      || dateValue(left.next_due_date) - dateValue(right.next_due_date)
      || nameSort(left, right),
  };
  items.sort(sorters[sort] || sorters.priority);
}

function numeric(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function openClientDrawer(key) {
  const client = (state.colchao.clients || []).find((item) => item.key === key);
  if (!client) return;
  document.querySelector("#colchaoClientDialog")?.remove();
  const dialog = document.createElement("dialog");
  dialog.id = "colchaoClientDialog";
  dialog.className = "colchao-client-dialog";
  const clientStatus = client.overdue_count
    ? { label: `${client.overdue_count} vencida(s)`, className: "is-overdue" }
    : client.active_count
      ? { label: "Em dia", className: "is-current" }
      : { label: "Sem acordos ativos", className: "is-closed" };
  const nextDue = client.next_due_date ? formatDate(client.next_due_date) : "Sem vencimento aberto";
  dialog.innerHTML = `
    <div class="colchao-client-dialog-shell">
      <header class="colchao-client-dialog-header">
        <span class="colchao-client-avatar" aria-hidden="true">${escapeHtml(String(client.client || "C").slice(0, 1).toUpperCase())}</span>
        <div class="colchao-client-dialog-title"><small>Cliente</small><h2>${escapeHtml(client.client)}</h2><p>${escapeHtml(client.identifier || "Sem identificador")}${client.document ? ` · ${escapeHtml(client.document)}` : ""}</p></div>
        <span class="colchao-client-health ${clientStatus.className}">${escapeHtml(clientStatus.label)}</span>
        <button class="icon-only-btn" type="button" data-close aria-label="Fechar">×</button>
      </header>
      <div class="colchao-client-workspace">
        <aside class="colchao-client-sidebar">
          <section class="colchao-client-dialog-summary">
            <div class="colchao-sidebar-heading"><small>Visão financeira</small><h3>Resumo do cliente</h3></div>
            <span><small>Acordos</small><strong>${client.agreement_count}</strong></span>
            <span><small>Parcelas</small><strong>${client.installment_count}</strong></span>
            <span class="wide"><small>Saldo aberto</small><strong>${money(client.open_value)}</strong></span>
            <span class="wide"><small>Total pago</small><strong>${money(client.paid_value)}</strong></span>
            <span class="wide"><small>Próximo vencimento</small><strong>${escapeHtml(nextDue)}</strong></span>
          </section>
          <nav class="colchao-agreement-selector" aria-label="Acordos do cliente">
            <div class="colchao-sidebar-heading"><small>Histórico financeiro</small><h3>Acordos</h3><em>${client.agreement_count}</em></div>
            ${client.agreements.map((agreement, index) => renderAgreementSelector(agreement, index)).join("")}
          </nav>
        </aside>
        <main class="colchao-client-dialog-content">
          ${client.agreements.length
            ? client.agreements.map((agreement, index) => renderAgreement(agreement, index)).join("")
            : `<div class="empty-state">Nenhum acordo encontrado para este cliente.</div>`}
        </main>
      </div>
    </div>`;
  document.body.appendChild(dialog);
  dialog.querySelector("[data-close]").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => dialog.remove(), { once: true });
  dialog.querySelectorAll("[data-select-agreement]").forEach((button) => {
    button.addEventListener("click", () => {
      dialog.querySelectorAll("[data-select-agreement]").forEach((item) => {
        const selected = item === button;
        item.classList.toggle("is-selected", selected);
        item.setAttribute("aria-current", selected ? "true" : "false");
      });
      dialog.querySelectorAll("[data-agreement-panel]").forEach((panel) => {
        panel.classList.toggle("hidden", panel.dataset.agreementPanel !== button.dataset.selectAgreement);
      });
    });
  });
  dialog.querySelectorAll("[data-reschedule-row]").forEach((button) => {
    button.addEventListener("click", () => openRescheduleDialog(client, button.dataset.rescheduleRow, button.dataset.rescheduleSheet));
  });
  dialog.showModal();
}

function renderAgreementSelector(agreement, index) {
  const paidCount = agreement.installments.filter((item) => ["PAGO", "QUITADO"].includes(item.status)).length;
  return `
    <button class="colchao-agreement-selector-item ${index === 0 ? "is-selected" : ""}" type="button"
      data-select-agreement="${escapeAttr(agreement.key)}" aria-current="${index === 0 ? "true" : "false"}">
      <span><strong>Acordo #${escapeHtml(agreement.number)}</strong>${agreement.type ? `<small>${escapeHtml(agreement.type)}</small>` : ""}</span>
      <em class="colchao-status-badge status-${statusToken(agreement.status)}">${escapeHtml(agreement.status)}</em>
      <span class="colchao-agreement-selector-meta"><small>${paidCount}/${agreement.installment_count} pagas</small><strong>${money(agreement.open_value)}</strong></span>
    </button>`;
}

function renderAgreement(agreement, index) {
  const openInstallment = agreement.installments.find((item) => ["A VENCER", "VENCIDO"].includes(item.status));
  const paidCount = agreement.installments.filter((item) => ["PAGO", "QUITADO"].includes(item.status)).length;
  const progress = agreement.installment_count ? Math.round((paidCount / agreement.installment_count) * 100) : 0;
  const scheduleLabel = agreement.overdue_count
    ? `${agreement.overdue_count} parcela(s) vencida(s)`
    : openInstallment ? "Cronograma em dia" : "Cronograma encerrado";
  return `
    <section class="colchao-agreement-workspace ${index === 0 ? "" : "hidden"}" data-agreement-panel="${escapeAttr(agreement.key)}">
      <header class="colchao-agreement-workspace-header">
        <div class="colchao-agreement-title"><small>Acordo selecionado</small><h3>Acordo #${escapeHtml(agreement.number)}</h3>${agreement.type ? `<p>${escapeHtml(agreement.type)}</p>` : ""}</div>
        <div class="colchao-agreement-header-actions">
          <strong class="colchao-status-badge status-${statusToken(agreement.status)}">${escapeHtml(agreement.status)}</strong>
          ${openInstallment ? `<button class="secondary-btn ds-button compact" type="button" data-reschedule-row="${openInstallment.row}" data-reschedule-sheet="${escapeAttr(openInstallment.sheet)}">Reprogramar vencimentos</button>` : ""}
        </div>
      </header>
      <section class="colchao-agreement-overview">
        <span><small>Progresso</small><strong>${paidCount}/${agreement.installment_count} pagas</strong></span>
        <span><small>Em aberto</small><strong>${money(agreement.open_value)}</strong></span>
        <span><small>Agenda</small><strong class="${agreement.overdue_count ? "danger" : ""}">${escapeHtml(scheduleLabel)}</strong></span>
        <div class="colchao-agreement-progress" aria-label="${progress}% das parcelas pagas"><span><i style="width:${progress}%"></i></span><small>${progress}% concluído</small></div>
      </section>
      <div class="colchao-installments-region">
        <div class="colchao-installments-title"><div><small>Cronograma financeiro</small><h3>Parcelas</h3></div><span>${agreement.installment_count} parcela(s)</span></div>
        <div class="colchao-installments-table">
          <div class="head"><span>Parcela</span><span>Vencimento</span><span>Valor</span><span>Status</span><span>Ações</span></div>
          ${agreement.installments.map((item) => `
            <div class="row status-row-${statusToken(item.status)} ${openInstallment && String(item.row) === String(openInstallment.row) ? "is-current-installment" : ""}">
              <span>${escapeHtml(item.label || "-")}${openInstallment && String(item.row) === String(openInstallment.row) ? `<small class="colchao-current-installment-label">Parcela atual</small>` : ""}</span><span>${escapeHtml(item.due_date_label)}</span><span>${money(item.value)}</span>
              <span><em class="colchao-installment-status status-${statusToken(item.status)}">${escapeHtml(item.status)}</em></span>
              <span>${["A VENCER", "VENCIDO"].includes(item.status) ? `<button class="colchao-installment-action" type="button" title="Reprogramar a partir desta parcela" aria-label="Reprogramar a partir desta parcela" data-reschedule-row="${item.row}" data-reschedule-sheet="${escapeAttr(item.sheet)}">Alterar</button>` : `<span class="colchao-installment-action-placeholder">—</span>`}</span>
            </div>`).join("")}
        </div>
      </div>
    </section>`;
}

function openRescheduleDialog(client, row, sheet) {
  document.querySelector("#colchaoRescheduleDialog")?.remove();
  const dialog = document.createElement("dialog");
  dialog.id = "colchaoRescheduleDialog";
  dialog.className = "colchao-reschedule-dialog";
  dialog.innerHTML = `
    <form method="dialog" class="colchao-reschedule-shell">
      <header><div><small>Reprogramação em lote</small><h2>Alterar vencimentos</h2><p>${escapeHtml(client.client)}</p></div><button class="icon-only-btn" value="cancel" aria-label="Fechar">×</button></header>
      <div class="colchao-reschedule-fields">
        <label>Nova data<input name="new_date" type="date" required /></label>
        <label>Aplicação<select name="mode"><option value="schedule">Novo cronograma mensal</option><option value="day">Alterar somente o dia</option></select></label>
        <label>Escopo<select name="scope"><option value="selected">Somente esta parcela</option><option value="from_current_month">Deste mês em diante</option><option value="from_next_month">A partir do próximo mês</option><option value="all_open">Todas as parcelas abertas</option></select></label>
        <label class="wide">Motivo<textarea name="reason" rows="2" placeholder="Opcional, será registrado na auditoria"></textarea></label>
      </div>
      <section class="colchao-reschedule-preview"><h3>Prévia das alterações</h3><div data-preview><p>Informe a nova data e gere a prévia antes de confirmar.</p></div></section>
      <footer><button class="secondary-btn ds-button" value="cancel">Cancelar</button><button class="secondary-btn ds-button" type="button" data-preview-btn>Gerar prévia</button><button class="primary-btn ds-button ds-button--primary" type="button" data-confirm-btn disabled>Confirmar alterações</button></footer>
    </form>`;
  document.body.appendChild(dialog);
  const form = dialog.querySelector("form");
  let previewSignature = "";
  const payload = () => ({
    profile: state.colchao.profile,
    row: Number(row),
    sheet,
    new_date: form.elements.new_date.value,
    mode: form.elements.mode.value,
    scope: form.elements.scope.value,
    reason: form.elements.reason.value,
  });
  form.addEventListener("input", () => {
    previewSignature = "";
    form.querySelector("[data-confirm-btn]").disabled = true;
  });
  form.querySelector("[data-preview-btn]").addEventListener("click", async (event) => {
    if (!form.reportValidity()) return;
    event.currentTarget.disabled = true;
    try {
      const plan = await api("/api/colchao/vencimentos/preview", { method: "POST", body: JSON.stringify(payload()) });
      previewSignature = JSON.stringify(payload());
      renderPreview(form.querySelector("[data-preview]"), plan);
      form.querySelector("[data-confirm-btn]").disabled = !plan.total;
    } catch (error) {
      toast(error.message);
    } finally {
      event.currentTarget.disabled = false;
    }
  });
  form.querySelector("[data-confirm-btn]").addEventListener("click", async (event) => {
    if (!previewSignature || previewSignature !== JSON.stringify(payload())) return toast("Gere uma nova prévia antes de confirmar.");
    event.currentTarget.disabled = true;
    try {
      const result = await api("/api/colchao/vencimentos/reprogramar", { method: "POST", body: JSON.stringify(payload()) });
      state.colchao.cache.clients = null;
      toast(`${result.total} parcela(s) reprogramada(s).`);
      dialog.close();
      document.querySelector("#colchaoClientDialog")?.close();
      await loadColchaoClients(true);
    } catch (error) {
      toast(error.message);
      event.currentTarget.disabled = false;
    }
  });
  dialog.addEventListener("close", () => dialog.remove(), { once: true });
  dialog.showModal();
}

function renderPreview(root, plan) {
  root.innerHTML = plan.total ? `
    <p><strong>${plan.total}</strong> parcela(s) serão alteradas no acordo #${escapeHtml(plan.agreement)}.</p>
    <div class="colchao-preview-table"><div class="head"><span>Parcela</span><span>Antes</span><span>Depois</span></div>${plan.changes.map((item) => `<div><span>${escapeHtml(item.parcela || "-")}</span><span>${escapeHtml(item.antes || "Sem data")}</span><strong>${escapeHtml(item.depois)}</strong></div>`).join("")}</div>`
    : `<p>Nenhuma parcela aberta precisa ser alterada para este escopo.</p>`;
}

function formatDate(value) {
  const parts = String(value || "").split("-");
  return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0]}` : String(value || "");
}

function normalize(value) {
  return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase().trim();
}

function statusToken(value) {
  return normalize(value).toLowerCase().replace(/[^a-z0-9]+/g, "");
}
