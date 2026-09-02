import { $ } from "../core/dom.js";
import { formatValue } from "../core/format.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { state } from "../core/state.js";
import { parecerPk, parecerValue } from "./parecerData.js";
import { renderParecerExcelGrid } from "./parecerExcelGrid.js?v=20260717-unfreeze-last-1";
import { bindNotesButtons, notesButton } from "./notes.js";

const callbacks = {
  markParecer: async () => false,
  approveParecer: async () => false,
  rejectParecer: async () => false,
};

export function configureParecerView(options = {}) {
  Object.assign(callbacks, options);
}

export function renderParecerPendentes() {
  const sourceRows = state.parecer.pendentes || [];
  syncPendingFilters(sourceRows);
  const search = $("#parecerPendingSearch")?.value.trim().toLowerCase() || "";
  const negotiator = $("#parecerPendingNegotiator")?.value || "";
  const reason = $("#parecerPendingReason")?.value || "";
  const order = $("#parecerPendingOrder")?.value || "oldest";
  const rows = sourceRows
    .filter((row) => !search || Object.values(row).some((value) => String(value ?? "").toLowerCase().includes(search)))
    .filter((row) => !negotiator || pendingNegotiator(row) === negotiator)
    .filter((row) => !reason || pendingReason(row) === reason)
    .sort((left, right) => {
      if (order === "name") return pendingClient(left).localeCompare(pendingClient(right), "pt-BR");
      const delta = pendingDate(left).getTime() - pendingDate(right).getTime();
      return order === "newest" ? -delta : delta;
    });
  renderPendingSummary(rows);
  if (!rows.length) {
    $("#parecerPendentesGrid").innerHTML = `
      <div class="parecer-empty-state">
        <span aria-hidden="true">
          <svg viewBox="0 0 24 24"><path d="M7 3h7l4 4v14H7V3Z" /><path d="M14 3v5h5" /><path d="M10 13h5" /><path d="M10 17h3" /><circle cx="17" cy="16" r="3" /><path d="m19.5 18.5 2 2" /></svg>
        </span>
        <strong>Nenhum parecer pendente encontrado.</strong>
        <p>Não há pareceres pendentes no momento.</p>
        <button class="secondary-btn ds-button parecer-empty-action" type="button" data-parecer-empty-completa>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h7l4 4v14H7V3Z" /><path d="M14 3v5h5" /><path d="M10 14h6" /><path d="M10 18h4" /></svg>
          Ver todos os pareceres
        </button>
      </div>
    `;
    $("#parecerPendentesGrid").querySelector("[data-parecer-empty-completa]")?.addEventListener("click", () => {
      document.querySelector('[data-parecer-page="completa"]')?.click();
    });
    updatePendingSelectionState();
    restorePendingScroll();
    return;
  }
  const grid = $("#parecerPendentesGrid");
  grid.innerHTML = rows.map(renderPendingClient).join("");
  grid.querySelectorAll("[data-parecer-mark]").forEach((button) => {
    button.addEventListener("click", () => callbacks.markParecer(button.dataset.parecerMark, button));
  });
  grid.querySelectorAll("[data-parecer-expand]").forEach((button) => {
    button.addEventListener("click", () => {
      const row = button.closest(".parecer-queue-row");
      const details = row?.querySelector(".parecer-queue-details");
      if (!details) return;
      const expanded = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", String(!expanded));
      details.classList.toggle("hidden", expanded);
      row.classList.toggle("is-expanded", !expanded);
    });
  });
  grid.querySelectorAll("[data-pending-select-value]").forEach((value) => {
    value.addEventListener("click", (event) => event.stopPropagation());
  });
  grid.querySelectorAll(".parecer-row-check").forEach((checkbox) => checkbox.addEventListener("change", updatePendingSelectionState));
  updatePendingSelectionState();
  bindNotesButtons(grid);
  restorePendingScroll();
}

function syncPendingFilters(rows) {
  syncSelectOptions("#parecerPendingNegotiator", rows.map(pendingNegotiator), "Todos os negociadores");
  syncSelectOptions("#parecerPendingReason", rows.map(pendingReason), "Todos os motivos");
}

function renderPendingSummary(rows) {
  const target = $("#parecerPendingSummary");
  if (!target) return;
  const ages = rows.map(pendingAgeDays);
  const overdue = ages.filter((age) => age > 5).length;
  const oldest = ages.length ? Math.max(...ages) : 0;
  target.innerHTML = `
    <span><b>${rows.length}</b> pendentes</span>
    <span class="is-critical"><b>${overdue}</b> acima de 5 dias</span>
    <span><b>${oldest}</b> dia${oldest === 1 ? "" : "s"} mais antigo</span>
  `;
}

function updatePendingSelectionState() {
  const selected = document.querySelectorAll("#parecerPendentesGrid .parecer-row-check:checked").length;
  const button = $("#parecerPendingMarkSelected");
  if (!button) return;
  button.disabled = selected === 0;
  button.textContent = selected ? `Solicitar selecionados (${selected})` : "Solicitar selecionados";
}

function restorePendingScroll() {
  if (!Number.isFinite(state.parecer.pendingScrollTop)) return;
  const scrollTop = state.parecer.pendingScrollTop;
  delete state.parecer.pendingScrollTop;
  requestAnimationFrame(() => requestAnimationFrame(() => window.scrollTo(0, scrollTop)));
}

export function renderParecerAprovacao() {
  const search = ($("#parecerApprovalSearch")?.value || "").trim().toLowerCase();
  const tab = state.parecer.approvalTab || "pendentes";
  document.querySelectorAll("[data-parecer-approval-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.parecerApprovalTab === tab);
    button.onclick = () => {
      state.parecer.approvalTab = button.dataset.parecerApprovalTab || "pendentes";
      renderParecerAprovacao();
    };
  });
  const sourceRows = tab === "historico" ? (state.parecer.aprovacaoHistorico || []) : (state.parecer.aprovacao || []);
  syncApprovalFilters(sourceRows);
  renderApprovalSummary();
  const negotiator = $("#parecerApprovalNegotiator")?.value || "";
  const reason = $("#parecerApprovalReason")?.value || "";
  const order = $("#parecerApprovalOrder")?.value || "oldest";
  const rows = sourceRows
    .filter((row) => !search || Object.values(row).some((value) => String(value ?? "").toLowerCase().includes(search)))
    .filter((row) => !negotiator || approvalNegotiator(row) === negotiator)
    .filter((row) => !reason || approvalReason(row) === reason)
    .sort((left, right) => {
      const delta = approvalDate(left).getTime() - approvalDate(right).getTime();
      return order === "newest" ? -delta : delta;
    });
  if (!rows.length) {
    $("#parecerAprovacaoGrid").innerHTML = `
      <div class="parecer-empty-state">
        <span aria-hidden="true">
          <svg viewBox="0 0 24 24"><path d="M9 12l2 2 4-5" /><path d="M7 3h7l4 4v14H7V3Z" /><path d="M14 3v5h5" /></svg>
        </span>
        <strong>${tab === "historico" ? "Nenhuma decisão registrada." : "Nenhum parecer aguardando aprovação."}</strong>
        <p>${tab === "historico" ? "Pareceres aprovados e reprovados aparecerão aqui com a justificativa." : "Solicitações aprovadas aparecem em Pendentes para serem marcadas como solicitadas."}</p>
      </div>
    `;
    return;
  }
  $("#parecerAprovacaoGrid").innerHTML = tab === "historico"
    ? rows.map(renderApprovalHistoryClient).join("")
    : rows.map(renderApprovalClient).join("");
  if (tab !== "historico") {
    document.querySelectorAll("[data-parecer-approval]").forEach((button) => {
      button.addEventListener("click", () => openParecerApprovalDialog(button.dataset.parecerApproval));
    });
  }
}

function syncApprovalFilters(rows) {
  syncSelectOptions("#parecerApprovalNegotiator", rows.map(approvalNegotiator), "Todos os negociadores");
  syncSelectOptions("#parecerApprovalReason", rows.map(approvalReason), "Todos os motivos");
  ["#parecerApprovalNegotiator", "#parecerApprovalReason", "#parecerApprovalOrder"].forEach((selector) => {
    const element = $(selector);
    if (element) element.onchange = renderParecerAprovacao;
  });
}

function syncSelectOptions(selector, rawValues, emptyLabel) {
  const select = $(selector);
  if (!select) return;
  const selected = select.value;
  const values = [...new Set(rawValues.filter(Boolean))].sort((left, right) => left.localeCompare(right, "pt-BR"));
  const signature = values.join("\u001f");
  if (select.dataset.signature === signature) return;
  select.innerHTML = `<option value="">${escapeHtml(emptyLabel)}</option>${values.map((value) => `<option value="${escapeAttr(value)}">${escapeHtml(value)}</option>`).join("")}`;
  select.dataset.signature = signature;
  if (values.includes(selected)) select.value = selected;
}

function renderApprovalSummary() {
  const target = $("#parecerApprovalStats");
  if (!target) return;
  const pending = state.parecer.aprovacao || [];
  const allRows = state.parecer.aprovacaoTodos || [];
  const now = new Date();
  const decidedThisMonth = allRows.filter((row) => {
    const date = approvalUpdatedDate(row);
    return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth();
  });
  const approved = decidedThisMonth.filter((row) => String(row.APROVACAO || "").toUpperCase() === "APROVADO").length;
  const rejected = decidedThisMonth.filter((row) => String(row.APROVACAO || "").toUpperCase() === "REPROVADO").length;
  const durations = decidedThisMonth.map(approvalDurationHours).filter((value) => Number.isFinite(value) && value >= 0);
  const average = durations.length ? durations.reduce((sum, value) => sum + value, 0) / durations.length : null;
  const items = [
    ["Aguardando aprovação", pending.length, "pending"],
    ["Aprovados no mês", approved, "approved"],
    ["Reprovados no mês", rejected, "rejected"],
    ["Tempo médio de análise", average === null ? "—" : formatDuration(average), "time"],
  ];
  target.innerHTML = items.map(([label, value, tone]) => `
    <article class="parecer-approval-stat ${tone}">
      <span class="parecer-approval-stat-icon" aria-hidden="true"></span>
      <div><strong>${escapeHtml(String(value))}</strong><span>${escapeHtml(label)}</span></div>
    </article>
  `).join("");
}

function approvalDurationHours(row) {
  const created = parseApprovalDate(row.__created_at);
  const updated = parseApprovalDate(row.__updated_at);
  if (!created || !updated) return Number.NaN;
  return (updated.getTime() - created.getTime()) / 3600000;
}

function formatDuration(hours) {
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min`;
  if (hours < 24) return `${Math.round(hours)} h`;
  return `${Math.round(hours / 24)} d`;
}

export function renderParecerCompleta() {
  const allRows = state.parecer.records || [];
  const info = $("#parecerPageInfo");
  if (info) info.textContent = `${allRows.length.toLocaleString("pt-BR")} registro(s)`;
  const updatedAt = $("#parecerSheetUpdatedAt");
  if (updatedAt) {
    updatedAt.textContent = `Atualizado ${new Intl.DateTimeFormat("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date())}`;
  }
  if (!allRows.length) {
    $("#parecerCompletaGrid").classList.remove("monitor-native-excel", "operational-native-excel", "excel-grid");
    $("#parecerCompletaGrid").innerHTML = `<div class="empty-overview">Nenhum registro encontrado.</div>`;
    return;
  }
  renderParecerExcelGrid(allRows);
}

export function renderMetricRows(items = [], options = {}) {
  const max = Math.max(1, ...items.map((item) => Number(item.total || 0)));
  const interactive = Boolean(options.filter);
  const tag = interactive ? "button" : "div";
  return items.length ? items.map((item, index) => `
    <${tag} ${interactive ? `type="button" data-parecer-dashboard-filter="${escapeAttr(item.label)}"` : ""} class="metric-row parecer-metric-row dashboard-rank-row ${interactive ? "is-interactive" : ""} ${index < 3 ? `dashboard-rank-top-${index + 1}` : ""}">
      <span class="dashboard-rank-number" aria-hidden="true">${String(index + 1).padStart(2, "0")}</span>
      <div class="dashboard-rank-content">
        <strong>${escapeHtml(item.label)}</strong>
        <span class="dashboard-rank-track" aria-hidden="true"><i style="width:${Math.max(4, Math.round((Number(item.total || 0) / max) * 100))}%"></i></span>
      </div>
      <strong class="dashboard-rank-total">${item.total}</strong>
    </${tag}>
  `).join("") : `
    <div class="parecer-empty-state compact">
      <span aria-hidden="true">
        <svg viewBox="0 0 24 24"><rect x="5" y="5" width="10" height="12" rx="2" /><path d="M8 9h4" /><path d="M8 13h3" /><circle cx="16" cy="16" r="3" /><path d="m18.5 18.5 2 2" /></svg>
      </span>
      <strong>Sem dados para exibir.</strong>
      <p>Não há registros pendentes no momento.</p>
    </div>
  `;
}

function renderPendingClient(row) {
  const pk = parecerPk(row);
  const npj = parecerValue(row, ["NPJ"]);
  const cliente = pendingClient(row);
  const negociador = pendingNegotiator(row);
  const motivo = pendingReason(row);
  const descricao = parecerValue(row, ["DESCRICAO", "DESCRIÇÃO", "DESCRIACAO", "DESCRIÇÃO DO PARECER", "OBS", "OBSERVACAO", "OBSERVAÇÃO"]) || "Descrição não informada";
  const date = pendingDate(row);
  const age = pendingAgeDays(row);
  const ageLabel = age === 0 ? "Hoje" : `${age} dia${age === 1 ? "" : "s"}`;
  const urgency = age > 5 ? "critical" : age >= 3 ? "warning" : "normal";
  const displayNpj = formatValue(npj || pk);
  return `
    <article class="parecer-queue-row urgency-${urgency}" data-parecer-pk="${escapeAttr(pk)}">
      <label class="parecer-queue-check" title="Selecionar parecer">
        <input class="parecer-row-check" type="checkbox" value="${escapeAttr(pk)}" aria-label="Selecionar ${escapeAttr(cliente)}" />
      </label>
      <button class="parecer-queue-main" type="button" data-parecer-expand="${escapeAttr(pk)}" aria-expanded="false">
        <span class="parecer-queue-age">${escapeHtml(ageLabel)}</span>
        <span class="parecer-queue-identity">
          <strong class="pending-copyable-value" data-pending-select-value="${escapeAttr(cliente)}" title="Selecione o nome para copiar">${escapeHtml(cliente)}</strong>
          <small>NPJ <span class="pending-copyable-value" data-pending-select-value="${escapeAttr(displayNpj)}" title="Selecione o NPJ para copiar">${escapeHtml(displayNpj)}</span> <i>·</i> ${escapeHtml(motivo)}</small>
        </span>
        <span class="parecer-queue-negotiator"><small>Negociador</small><b>${escapeHtml(negociador)}</b></span>
        <span class="parecer-queue-requested"><small>Recebido</small><b>${escapeHtml(formatPendingDate(date))}</b></span>
        <span class="parecer-queue-expand" aria-hidden="true">⌄</span>
      </button>
      <div class="parecer-queue-actions">
        ${notesButton("parecer", pk, "Obs.")}
        <button class="primary-btn ds-button ds-button--primary" type="button" data-parecer-mark="${escapeAttr(pk)}">Solicitado</button>
      </div>
      <div class="parecer-queue-details hidden"><strong>Descrição</strong><p>${escapeHtml(descricao)}</p></div>
    </article>
  `;
}

function pendingClient(row) {
  return parecerValue(row, ["CLIENTE", "NOME", "NOME CLIENTE", "NOME DO CLIENTE"]) || "Cliente não identificado";
}

function pendingNegotiator(row) {
  return parecerValue(row, ["OPERADOR", "NEGOCIADOR", "RESPONSAVEL", "RESPONSÁVEL", "SOLICITANTE", "USUARIO", "USUÁRIO"]) || "Negociador não informado";
}

function pendingReason(row) {
  return parecerValue(row, ["MOTIVO", "MOTIVO PARECER", "TIPO MOTIVO"]) || "Motivo não informado";
}

function pendingDate(row) {
  return parseApprovalDate(row.__created_at)
    || parseApprovalDate(parecerValue(row, ["DATA", "DATA SOLICITACAO", "DATA DE SOLICITAÇÃO", "DATA APROVADO/REPROVADO"]))
    || new Date(8640000000000000);
}

function pendingAgeDays(row) {
  const date = pendingDate(row);
  if (date.getFullYear() > 9999) return 0;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const start = new Date(date);
  start.setHours(0, 0, 0, 0);
  return Math.max(0, Math.floor((today.getTime() - start.getTime()) / 86400000));
}

function formatPendingDate(date) {
  if (!date || date.getFullYear() > 9999) return "Não informada";
  return new Intl.DateTimeFormat("pt-BR").format(date);
}

function renderApprovalClient(row) {
  const pk = parecerPk(row);
  const npj = parecerValue(row, ["NPJ"]);
  const cliente = parecerValue(row, ["CLIENTE", "NOME", "NOME CLIENTE", "NOME DO CLIENTE"]) || "Cliente nao identificado";
  const negociador = approvalNegotiator(row);
  const motivo = approvalReason(row);
  const descricao = parecerValue(row, ["DESCRICAO", "DESCRIÇÃO", "DESCRIACAO", "DESCRIÇÃO DO PARECER", "OBS", "OBSERVACAO", "OBSERVAÇÃO"]) || "Descricao nao informada";
  const requestedAt = approvalDate(row);
  return `
    <button class="parecer-approval-card" type="button" data-parecer-approval="${escapeAttr(pk)}">
      <span class="parecer-approval-card-marker" aria-hidden="true"></span>
      <div class="parecer-approval-card-main">
        <div class="parecer-approval-card-topline">
          <strong>${escapeHtml(cliente)}</strong>
          <span class="parecer-approval-date">${escapeHtml(formatApprovalDate(requestedAt))}</span>
        </div>
        <div class="parecer-approval-card-meta">
          <span>${escapeHtml(negociador)}</span>
          <span>NPJ ${escapeHtml(formatValue(npj || pk))}</span>
          <span>${escapeHtml(motivo)}</span>
        </div>
        <p>${escapeHtml(descricao)}</p>
      </div>
      <div class="parecer-approval-card-action">
        <span class="parecer-approval-waiting">Aguardando aprovação</span>
        <strong>Analisar <span aria-hidden="true">›</span></strong>
      </div>
    </button>
  `;
}

function renderApprovalHistoryClient(row) {
  const pk = parecerPk(row);
  const npj = parecerValue(row, ["NPJ"]);
  const cliente = parecerValue(row, ["CLIENTE", "NOME", "NOME CLIENTE", "NOME DO CLIENTE"]) || "Cliente nao identificado";
  const negociador = approvalNegotiator(row);
  const motivo = approvalReason(row);
  const justificativa = parecerValue(row, ["JUSTIFICATIVA APROVACAO/REPROVACAO", "JUSTIFICATIVA APROVAÇÃO/REPROVAÇÃO", "JUSTIFICATIVA REPROVACAO", "JUSTIFICATIVA REPROVAÇÃO", "approval_reason"]) || "Justificativa nao informada";
  const approved = String(row.APROVACAO || "").toUpperCase() === "APROVADO";
  const statusLabel = approved ? "Aprovado" : "Reprovado";
  const decidedAt = approvalUpdatedDate(row);
  return `
    <article class="parecer-approval-card parecer-history-card ${approved ? "parecer-approved-card" : "parecer-rejected-card"}">
      <span class="parecer-approval-card-marker" aria-hidden="true"></span>
      <div class="parecer-approval-card-main">
        <div class="parecer-approval-card-topline">
          <strong>${escapeHtml(cliente)}</strong>
          <span class="parecer-history-decision">
            <time>${escapeHtml(formatApprovalDate(decidedAt))}</time>
            <b class="${approved ? "parecer-approved-label" : "parecer-rejected-label"}">${statusLabel}</b>
          </span>
        </div>
        <div class="parecer-approval-card-meta">
          <span>${escapeHtml(negociador)}</span>
          <span>NPJ ${escapeHtml(formatValue(npj || pk))}</span>
          <span>${escapeHtml(motivo)}</span>
        </div>
        <p><strong>Justificativa da ${approved ? "aprovação" : "reprovação"}:</strong> ${escapeHtml(justificativa)}</p>
      </div>
    </article>
  `;
}

function approvalNegotiator(row) {
  return parecerValue(row, ["OPERADOR", "NEGOCIADOR", "RESPONSAVEL", "RESPONSÁVEL", "SOLICITANTE", "USUARIO", "USUÁRIO"]) || "Negociador não informado";
}

function approvalReason(row) {
  return parecerValue(row, ["MOTIVO", "MOTIVO PARECER", "TIPO MOTIVO"]) || "Motivo não informado";
}

function approvalDate(row) {
  return parseApprovalDate(row.__created_at)
    || parseApprovalDate(parecerValue(row, ["DATA", "DATA SOLICITACAO", "DATA DE SOLICITAÇÃO"]))
    || new Date(0);
}

function approvalUpdatedDate(row) {
  return parseApprovalDate(row.__updated_at) || approvalDate(row);
}

function parseApprovalDate(value) {
  if (!value) return null;
  const raw = String(value).trim();
  const br = raw.match(/^(\d{2})\/(\d{2})\/(\d{4})(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?/);
  if (br) return new Date(Number(br[3]), Number(br[2]) - 1, Number(br[1]), Number(br[4] || 0), Number(br[5] || 0), Number(br[6] || 0));
  const parsed = new Date(raw.includes(" ") && !raw.includes("T") ? raw.replace(" ", "T") : raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatApprovalDate(date) {
  if (!date || date.getTime() === 0) return "Data não informada";
  return `${date.toLocaleDateString("pt-BR")} · ${date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
}

function openParecerApprovalDialog(pk) {
  const row = (state.parecer.aprovacao || []).find((item) => String(parecerPk(item)) === String(pk));
  if (!row) return;
  const dialog = ensureParecerApprovalDialog();
  const npj = parecerValue(row, ["NPJ"]);
  const cliente = parecerValue(row, ["CLIENTE", "NOME", "NOME CLIENTE", "NOME DO CLIENTE"]) || "Cliente nao identificado";
  const negociador = parecerValue(row, ["OPERADOR", "NEGOCIADOR", "RESPONSAVEL", "RESPONSÁVEL", "SOLICITANTE", "USUARIO", "USUÁRIO"]) || "Negociador nao informado";
  const motivo = parecerValue(row, ["MOTIVO", "MOTIVO PARECER", "TIPO MOTIVO"]) || "Motivo nao informado";
  const descricao = parecerValue(row, ["DESCRICAO", "DESCRIÇÃO", "DESCRIACAO", "DESCRIÇÃO DO PARECER", "OBS", "OBSERVACAO", "OBSERVAÇÃO"]) || "Descricao nao informada";
  const data = approvalDate(row);
  dialog.dataset.pk = pk;
  dialog.querySelector("[data-approval-title]").textContent = cliente;
  dialog.querySelector("[data-approval-meta]").innerHTML = `
    <div><strong>Negociador</strong><span>${escapeHtml(negociador)}</span></div>
    <div><strong>NPJ</strong><span>${escapeHtml(formatValue(npj || pk))}</span></div>
    <div><strong>Motivo</strong><span>${escapeHtml(motivo)}</span></div>
    <div><strong>Solicitado em</strong><span>${escapeHtml(formatApprovalDate(data))}</span></div>
  `;
  dialog.querySelector("[data-approval-description]").value = descricao;
  dialog.querySelector("[data-approval-reason]").value = "";
  dialog.querySelector("[data-approval-error]").textContent = "";
  if (!dialog.open) dialog.showModal();
}

function ensureParecerApprovalDialog() {
  let dialog = document.querySelector("#parecerApprovalDialog");
  if (dialog) return dialog;
  dialog = document.createElement("dialog");
  dialog.id = "parecerApprovalDialog";
  dialog.className = "dialog parecer-approval-dialog parecer-approval-drawer";
  dialog.innerHTML = `
    <form method="dialog">
      <header>
        <div>
          <span class="parecer-drawer-eyebrow">Análise de solicitação</span>
          <h2>Revisar parecer</h2>
        </div>
        <button type="button" class="icon-btn ds-button" data-approval-close aria-label="Fechar">&times;</button>
      </header>
      <section class="approval-dialog-body">
        <div class="parecer-drawer-client">
          <span class="parecer-approval-waiting">Aguardando aprovação</span>
          <h3 data-approval-title></h3>
        </div>
        <div class="approval-meta-grid" data-approval-meta></div>
        <label class="parecer-drawer-field"><span>Descrição do parecer</span>
          <textarea data-approval-description rows="6" maxlength="1000"></textarea>
        </label>
        <label class="parecer-drawer-field"><span>Justificativa da decisão</span>
          <textarea data-approval-reason rows="5" maxlength="600" placeholder="Informe o motivo da aprovação ou reprovação"></textarea>
        </label>
        <p class="form-error" data-approval-error></p>
      </section>
      <footer>
        <button type="button" class="secondary-btn ds-button" data-approval-close>Cancelar</button>
        <div class="parecer-drawer-decisions">
          <button type="button" class="danger-btn ds-button ds-button--danger" data-approval-reject>Reprovar</button>
          <button type="button" class="primary-btn ds-button ds-button--primary" data-approval-approve>Aprovar</button>
        </div>
      </footer>
    </form>
  `;
  document.body.appendChild(dialog);
  dialog.querySelectorAll("[data-approval-close]").forEach((button) => button.addEventListener("click", () => dialog.close()));
  dialog.querySelector("[data-approval-approve]").addEventListener("click", async (event) => {
    const reason = dialog.querySelector("[data-approval-reason]").value.trim();
    const descricao = dialog.querySelector("[data-approval-description]").value.trim();
    if (!descricao) {
      dialog.querySelector("[data-approval-error]").textContent = "Informe a descrição do parecer.";
      return;
    }
    if (!reason) {
      dialog.querySelector("[data-approval-error]").textContent = "Informe a justificativa para aprovar.";
      return;
    }
    const ok = await callbacks.approveParecer(dialog.dataset.pk, reason, descricao, event.currentTarget);
    if (ok) dialog.close();
  });
  dialog.querySelector("[data-approval-reject]").addEventListener("click", async (event) => {
    const reason = dialog.querySelector("[data-approval-reason]").value.trim();
    const descricao = dialog.querySelector("[data-approval-description]").value.trim();
    if (!descricao) {
      dialog.querySelector("[data-approval-error]").textContent = "Informe a descrição do parecer.";
      return;
    }
    if (!reason) {
      dialog.querySelector("[data-approval-error]").textContent = "Informe a justificativa para reprovar.";
      return;
    }
    const ok = await callbacks.rejectParecer(dialog.dataset.pk, reason, descricao, event.currentTarget);
    if (ok) dialog.close();
  });
  return dialog;
}










