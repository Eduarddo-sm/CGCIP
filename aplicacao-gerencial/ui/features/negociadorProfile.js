import { $ } from "../core/dom.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { state } from "../core/state.js";
import { availableProfileYears, currentProfilePeriod, monthOptions, periodRows } from "./negociadorPeriod.js?v=20260728-next-month-fix-1";

let initialized = false;

export function setupNegociadorProfile({ refresh, renderSheet, renderTimeline } = {}) {
  if (initialized) return;
  const content = $("#content");
  const mount = $("#negociadorProfileMount");
  if (!content || !mount) return;

  const legacyToolbar = content.querySelector(":scope > .negociador-toolbar");
  const historyPanel = $("#clientHistoryPanel");
  const timelinePanel = content.querySelector(":scope > .timeline-panel");
  const sheetPanel = $("#sheetPanel");
  if (!legacyToolbar || !timelinePanel || !sheetPanel) return;

  mount.innerHTML = `
    <header class="negociador-profile-header">
      <div class="negociador-profile-identity">
        <span data-profile-back-slot></span>
        <span id="negociadorProfileInitials" class="negociador-profile-avatar">N</span>
        <div>
          <h2 id="negociadorProfileName">Negociador</h2>
          <div class="negociador-profile-meta">
            <strong id="negociadorProfileWallet">-</strong>
            <span aria-hidden="true">&bull;</span>
            <span id="negociadorProfilePresenceDot" class="negociador-profile-online" aria-hidden="true"></span>
            <span id="negociadorProfilePresence">Offline</span>
            <span aria-hidden="true">&bull;</span>
            <span id="negociadorProfileUpdated">Atualizando dados</span>
          </div>
        </div>
      </div>
      <div class="negociador-profile-actions">
        <span data-profile-edit-slot></span>
        <button id="profileRefreshBtn" class="primary-btn ds-button ds-button--primary" type="button">Atualizar dados</button>
        <details class="negociador-profile-more">
          <summary class="icon-btn" title="Mais acoes" aria-label="Mais acoes">&hellip;</summary>
          <div data-profile-remove-slot></div>
        </details>
      </div>
    </header>
    <nav class="negociador-profile-tabs" aria-label="Paginas do negociador">
      <button class="active" type="button" data-negociador-profile-tab="producao">Producao</button>
      <button type="button" data-negociador-profile-tab="timeline">Timeline <strong id="negociadorTimelineCount">0</strong></button>
      <button type="button" data-negociador-profile-tab="correcoes">Correcoes <strong id="negociadorCorrectionsCount">0</strong></button>
      <button type="button" data-negociador-profile-tab="auditoria">Auditoria</button>
    </nav>
    <section id="negociadorMetrics" class="negociador-profile-metrics" aria-label="Resumo da producao"></section>
    <section class="negociador-profile-stage">
      <div class="negociador-profile-panel active" data-negociador-profile-panel="producao"><div data-profile-sheet-slot></div></div>
      <div class="negociador-profile-panel" data-negociador-profile-panel="timeline"><div data-profile-timeline-slot></div></div>
      <div class="negociador-profile-panel" data-negociador-profile-panel="correcoes">
        <div class="negociador-profile-log ds-card">
          <div class="panel-head"><h2>Correcoes enviadas ao negociador</h2><span id="negociadorCorrectionsMeta"></span></div>
          <div id="negociadorCorrectionsList" class="negociador-profile-log-body"></div>
        </div>
      </div>
      <div class="negociador-profile-panel" data-negociador-profile-panel="auditoria">
        <div class="negociador-profile-log ds-card">
          <div class="panel-head"><h2>Auditoria do perfil</h2><span id="negociadorAuditMeta"></span></div>
          <div id="negociadorAuditList" class="negociador-profile-log-body"></div>
        </div>
      </div>
      <div class="hidden" data-profile-legacy-history-slot></div>
    </section>
  `;

  const backButton = $("#backToNegociadoresBtn");
  const editButton = $("#editBtn");
  const removeButton = $("#removeBtn");
  backButton.className = "icon-btn negociador-profile-back";
  backButton.textContent = "\u2190";
  backButton.title = "Voltar aos negociadores";
  editButton.textContent = "Editar perfil";
  removeButton.textContent = "Remover negociador";
  mount.querySelector("[data-profile-back-slot]").replaceWith(backButton);
  mount.querySelector("[data-profile-edit-slot]").replaceWith(editButton);
  mount.querySelector("[data-profile-remove-slot]").append(removeButton);

  const sheetToolbar = document.createElement("div");
  sheetToolbar.className = "negociador-sheet-toolbar";
  const searchWrap = legacyToolbar.querySelector(".search-wrap");
  const periodControls = document.createElement("div");
  periodControls.className = "negociador-period-controls";
  periodControls.innerHTML = `
    <label><select id="negociadorProfileMonth" aria-label="Mes"></select></label>
    <label><select id="negociadorProfileYear" aria-label="Ano"></select></label>
  `;
  const oldPanelHead = sheetPanel.querySelector(":scope > .panel-head");
  const openButton = $("#openNegotiatorSpreadsheetBtn");
  const focusButton = $("#toggleSheetSizeBtn");
  const actions = document.createElement("div");
  actions.className = "negociador-sheet-actions";
  actions.append(openButton, focusButton);
  sheetToolbar.append(searchWrap, periodControls, actions);
  oldPanelHead?.remove();
  sheetPanel.prepend(sheetToolbar);
  sheetPanel.classList.remove("sheet-collapsed");
  focusButton.textContent = "Modo foco";
  focusButton.setAttribute("aria-expanded", "false");

  mount.querySelector("[data-profile-sheet-slot]").append(sheetPanel);
  mount.querySelector("[data-profile-timeline-slot]").append(timelinePanel);
  if (historyPanel) mount.querySelector("[data-profile-legacy-history-slot]").append(historyPanel);
  legacyToolbar.remove();

  mount.querySelectorAll("[data-negociador-profile-tab]").forEach((button) => {
    button.addEventListener("click", () => showNegociadorProfileTab(button.dataset.negociadorProfileTab));
  });
  $("#profileRefreshBtn")?.addEventListener("click", () => refresh?.(false));
  periodControls.addEventListener("change", () => {
    state.negociadorProfile.month = Number($("#negociadorProfileMonth")?.value || 0);
    state.negociadorProfile.year = Number($("#negociadorProfileYear")?.value || 0);
    document.dispatchEvent(new CustomEvent("negociador:period-change"));
  });
  document.addEventListener("negociador:period-change", () => {
    renderSheet?.();
    renderNegociadorProfile();
    renderTimeline?.();
  });
  focusButton.addEventListener("click", toggleNegociadorFocus);
  initialized = true;
}

export function showNegociadorProfileTab(tab) {
  const allowed = new Set(["producao", "timeline", "correcoes", "auditoria"]);
  state.negociadorProfile.tab = allowed.has(tab) ? tab : "producao";
  $("#negociadorMetrics")?.classList.toggle("hidden", state.negociadorProfile.tab !== "producao");
  document.querySelectorAll("[data-negociador-profile-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.negociadorProfileTab === state.negociadorProfile.tab);
  });
  document.querySelectorAll("[data-negociador-profile-panel]").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.negociadorProfilePanel === state.negociadorProfile.tab);
  });
}

export function renderNegociadorProfile() {
  const active = state.negociadores.find((item) => Number(item.id) === Number(state.activeId));
  if (!active || !state.data) return;
  $("#pageTitle").textContent = "Perfil do negociador";
  $("#negociadorProfileName").textContent = active.nome || active.negocial_username || "Negociador";
  $("#negociadorProfileWallet").textContent = active.carteira || "Carteira nao informada";
  $("#negociadorProfilePresence").textContent = active.online ? "Online" : "Offline";
  $("#negociadorProfilePresenceDot").classList.toggle("offline", !active.online);
  $("#negociadorProfileInitials").textContent = initials(active.nome || active.negocial_username);
  $("#negociadorProfileUpdated").textContent = updatedLabel(state.data.captured_at || active.updated_at || active.created_at);
  $("#negociadorTimelineCount").textContent = String(state.events.length);
  $("#negociadorCorrectionsCount").textContent = String(state.negociadorProfile.corrections.length);
  renderPeriodControls();
  renderMetrics(active);
  renderCorrections();
  renderAudit();
  showNegociadorProfileTab(state.negociadorProfile.tab || "producao");
}

export function toggleNegociadorFocus() {
  const enabled = document.body.classList.toggle("negociador-focus-mode");
  const button = $("#toggleSheetSizeBtn");
  if (button) {
    button.textContent = enabled ? "Sair do foco" : "Modo foco";
    button.setAttribute("aria-expanded", String(enabled));
  }
}

function renderMetrics(active) {
  const rows = periodRows(state.data, state.negociadorProfile);
  const headers = state.data.headers || [];
  const statusHeader = findHeader(headers, ["STATUS", "SITUACAO"]);
  const honorHeader = findHeader(headers, ["HONORARIOS RECEBIDOS", "HONORARIOS", "H O", "VALOR H O"]);
  const totalHeader = findHeader(headers, ["VALOR DO ACORDO", "VALOR TOTAL DE ACORDO", "VALOR TOTAL", "VALOR FECHADO"]);
  let paid = 0;
  let awaiting = 0;
  let negotiated = 0;
  let paidCount = 0;
  let awaitingCount = 0;
  rows.forEach((row) => {
    const status = normalized(row[statusHeader]);
    const honor = sheetNumber(row[honorHeader]);
    negotiated += sheetNumber(row[totalHeader]);
    if (status.includes("PAGAMENTO REALIZADO") || status === "PAGO") {
      paid += honor;
      paidCount += 1;
    }
    if (status.includes("AGUARDANDO PAGAMENTO")) {
      awaiting += honor;
      awaitingCount += 1;
    }
  });
  const goal = sheetNumber(active.meta_pagamento);
  const progress = goal > 0 ? paid / goal * 100 : 0;
  $("#negociadorMetrics").innerHTML = `
    ${metricCard("Honorarios pagos", money(paid), `${paidCount} pagamentos realizados`, "success")}
    ${metricCard("Projecao em aberto", money(awaiting), `${awaitingCount} aguardando pagamento`, "warning")}
    ${metricCard("Acordos no periodo", String(rows.length), `${money(negotiated)} negociados`, "primary")}
    <article class="negociador-profile-metric success">
      <span>Meta de honorarios</span>
      <strong>${percent(progress)}</strong>
      <small>${money(paid)} de ${money(goal)}</small>
      <div class="negociador-profile-progress"><i style="width:${escapeAttr(String(Math.min(100, Math.max(0, progress))))}%"></i></div>
    </article>
  `;
}

function renderPeriodControls() {
  const fallback = currentProfilePeriod();
  const month = Number(state.negociadorProfile.month) || fallback.month;
  const year = Number(state.negociadorProfile.year) || fallback.year;
  state.negociadorProfile.month = month;
  state.negociadorProfile.year = year;
  const monthSelect = $("#negociadorProfileMonth");
  const yearSelect = $("#negociadorProfileYear");
  if (!monthSelect || !yearSelect) return;
  monthSelect.innerHTML = monthOptions().map((item) => `<option value="${item.value}" ${item.value === month ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("");
  yearSelect.innerHTML = availableProfileYears(state.data).map((item) => `<option value="${item}" ${item === year ? "selected" : ""}>${item}</option>`).join("");
}

function metricCard(label, value, detail, tone) {
  return `<article class="negociador-profile-metric ${tone}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail)}</small></article>`;
}

function renderCorrections() {
  const rows = state.negociadorProfile.corrections || [];
  $("#negociadorCorrectionsMeta").textContent = `${rows.length} registros`;
  $("#negociadorCorrectionsList").innerHTML = rows.length ? `
    <div class="negociador-profile-table-scroll">
      <table class="negociador-profile-table">
        <thead><tr><th>Cliente</th><th>Campo</th><th>Antes</th><th>Depois</th><th>Responsavel</th><th>Data</th><th>Situacao</th></tr></thead>
        <tbody>${rows.map((row) => `
          <tr>
            <td>${escapeHtml(row.cliente || "Cliente nao identificado")}</td>
            <td>${escapeHtml(row.campo || "-")}</td>
            <td>${escapeHtml(displayValue(row.valor_anterior))}</td>
            <td>${escapeHtml(displayValue(row.valor_novo))}</td>
            <td>${escapeHtml(row.corrigido_por || "-")}</td>
            <td>${escapeHtml(dateTime(row.criado_em))}</td>
            <td><span class="negociador-profile-status ${row.visualizado_pelo_negociador ? "read" : "pending"}">${row.visualizado_pelo_negociador ? "Visualizada" : "Pendente"}</span></td>
          </tr>`).join("")}</tbody>
      </table>
    </div>` : `<div class="negociador-profile-empty">Nenhuma correcao enviada para este negociador.</div>`;
}

function renderAudit() {
  const events = [...(state.events || [])].sort((a, b) => new Date(b.changed_at) - new Date(a.changed_at));
  $("#negociadorAuditMeta").textContent = `${events.length} eventos`;
  $("#negociadorAuditList").innerHTML = events.length ? `
    <div class="negociador-profile-table-scroll">
      <table class="negociador-profile-table">
        <thead><tr><th>Data/Hora</th><th>Acao</th><th>Sheet</th><th>Responsavel</th><th>Alteracoes</th><th>Origem</th></tr></thead>
        <tbody>${events.map((event) => `
          <tr>
            <td>${escapeHtml(dateTime(event.changed_at))}</td>
            <td>${escapeHtml(eventLabel(event.event_type))}</td>
            <td>${escapeHtml(event.sheet || "-")}</td>
            <td>${escapeHtml(event.negociador_nome || "Sistema")}</td>
            <td>${escapeHtml(String(event.changes_count || 0))}</td>
            <td><span class="negociador-profile-status read">${escapeHtml(originLabel(event.event_type))}</span></td>
          </tr>`).join("")}</tbody>
      </table>
    </div>` : `<div class="negociador-profile-empty">Nenhum evento registrado para este negociador.</div>`;
}

function findHeader(headers, candidates) {
  const normalizedCandidates = candidates.map(normalized);
  return headers.find((header) => normalizedCandidates.includes(normalized(header)))
    || headers.find((header) => normalizedCandidates.some((candidate) => normalized(header).includes(candidate)))
    || "";
}

function normalized(value) {
  return String(value ?? "").trim().toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^A-Z0-9]+/g, " ").trim();
}

function sheetNumber(value) {
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  const cleaned = String(value ?? "").trim().replace(/[^\d,.-]/g, "");
  if (!cleaned) return 0;
  const parsed = cleaned.includes(",") ? Number(cleaned.replace(/\./g, "").replace(",", ".")) : Number(cleaned);
  return Number.isFinite(parsed) ? parsed : 0;
}

function money(value) {
  return Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function percent(value) {
  return `${Number(value || 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

function initials(value) {
  const pieces = String(value || "N").trim().split(/[.\s_-]+/).filter(Boolean);
  return pieces.slice(0, 2).map((piece) => piece[0]).join("").toUpperCase() || "N";
}

function updatedLabel(value) {
  if (!value) return "Dados sincronizados";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Dados sincronizados";
  const minutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
  if (minutes < 1) return "Atualizado agora";
  if (minutes < 60) return `Atualizado ha ${minutes} min`;
  return `Atualizado em ${date.toLocaleDateString("pt-BR")}`;
}

function dateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("pt-BR");
}

function displayValue(value) {
  return value === null || value === undefined || String(value).trim() === "" ? "Vazio" : String(value);
}

function eventLabel(type) {
  return {
    initial_snapshot: "Carga inicial",
    file_changed: "Atualizacao da producao",
    manual_update: "Atualizacao manual",
    sheet_changed: "Troca de sheet",
    new_month: "Novo mes",
  }[type] || "Alteracao de dados";
}

function originLabel(type) {
  return ["initial_snapshot", "sheet_changed", "new_month"].includes(type) ? "Sistema" : "Negocial";
}
