import { $, preserveScroll } from "../core/dom.js";
import { formatValue } from "../core/format.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { clearLoading } from "../core/loading.js";
import { state } from "../core/state.js";

const callbacks = {
  markRead: async () => {},
  openNegociador: async () => {},
  openNegociadorWithClientFilter: async () => {},
};

export function configureOverviewView(options = {}) {
  Object.assign(callbacks, options);
}

export function renderOverview() {
  const unreadCount = state.overviewStatus === "unread" ? state.overview.length : state.overview.filter((item) => !item.lido).length;
  $("#overviewBadge").textContent = unreadCount;
  const summary = $("#overviewViewSummary");
  if (summary) {
    const label = state.overviewStatus === "unread" ? "nao lidas" : state.overviewStatus === "read" ? "lidas" : "alteracoes";
    summary.textContent = `${state.overview.length} ${label}`;
  }
  document.querySelectorAll("[data-overview-status]").forEach((button) => {
    button.classList.toggle("active", button.dataset.overviewStatus === state.overviewStatus);
  });
  $("#markAllOverviewBtn").classList.toggle("hidden", state.overviewStatus === "read");
  const list = $("#overviewList");
  const signature = overviewSignature();
  if (!list.classList.contains("is-loading") && list.dataset.signature === signature) return;
  if (!state.overview.length) {
    preserveScroll("#overviewList", () => {
      clearLoading("#overviewList");
      list.classList.toggle("stable-render", list.dataset.rendered === "true");
      list.innerHTML = `<div class="empty-overview">Nenhuma alteracao nesta visualizacao.</div>`;
      list.dataset.signature = signature;
      list.dataset.rendered = "true";
    });
    return;
  }
  preserveScroll("#overviewList", () => {
    clearLoading("#overviewList");
    list.classList.toggle("stable-render", list.dataset.rendered === "true");
    list.innerHTML = groupedOverview(state.overview).map((group) => `
      <section class="overview-group">
        <header>
          <strong>${escapeHtml(group.carteira)}</strong>
        <span>${escapeHtml(group.cliente)} · ${group.items.length} itens</span>
      </header>
      <div class="overview-group-list">
        ${group.items.map(renderOverviewItem).join("")}
      </div>
      </section>
    `).join("");
    list.dataset.signature = signature;
    list.dataset.rendered = "true";
  });
  document.querySelectorAll("[data-read]").forEach((button) => {
    button.addEventListener("click", async () => {
      await callbacks.markRead(button.dataset.read);
    });
  });
  document.querySelectorAll("[data-overview-detail]").forEach((button) => {
    button.addEventListener("click", () => openOverviewDetails(button.dataset.overviewDetail));
  });
  document.querySelectorAll("[data-overview-negociador]").forEach((button) => {
    button.addEventListener("click", () => openOverviewNegotiator(button.dataset.overviewNegociador));
  });
  document.querySelectorAll("[data-overview-client]").forEach((button) => {
    button.addEventListener("click", () => openOverviewClient(button.dataset.overviewClient));
  });
  document.querySelectorAll("[data-overview-row]").forEach((row) => {
    row.addEventListener("click", (event) => {
      if (event.target.closest("button, a, input, select, textarea")) return;
      openOverviewDetails(row.dataset.overviewRow);
    });
    row.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      openOverviewDetails(row.dataset.overviewRow);
    });
  });
}

function overviewSignature() {
  return JSON.stringify({
    status: state.overviewStatus,
    items: state.overview.map((item) => ({
      id: item.id,
      lido: item.lido,
      usuario: item.usuario,
      dataHora: item.dataHora,
      campo: item.campo,
      tipo: item.tipo,
      prioridade: item.prioridade,
      cliente: item.cliente,
      negociadorId: item.negociadorId,
      carteira: item.carteira,
      sheet: item.sheet,
      details: (item.details || []).map((detail) => [detail.campo, detail.linha, detail.antes, detail.depois]),
    })),
  });
}

export function closeOverviewDetails() {
  $("#overviewDrawer").classList.remove("open");
  $("#overviewDrawer").setAttribute("aria-hidden", "true");
  $("#drawerBackdrop").classList.remove("open");
  document.body.classList.remove("drawer-open");
}

export function renderChangesTable(details) {
  const groups = groupDetailsByLine(details);
  return `<div class="mini-row-diffs">${groups.map(renderDetailRowDiff).join("")}</div>`;
}

function groupDetailsByLine(details) {
  const groups = new Map();
  details.forEach((detail, index) => {
    const line = detail.linha || "";
    const key = String(line || index);
    if (!groups.has(key)) groups.set(key, { line, details: [] });
    groups.get(key).details.push(detail);
  });
  return [...groups.values()];
}

function renderDetailRowDiff(group) {
  const columns = group.details.map((detail) => detail.campo || "Campo");
  return `
    <div class="mini-row-diff">
      <div class="mini-row-title">Linha ${escapeHtml(group.line || "nao identificada")}</div>
      <div class="mini-row-scroll">
        <table>
          <thead>
            <tr><th>Estado</th>${columns.map((column) => `<th class="changed-cell">${escapeHtml(column)}</th>`).join("")}</tr>
          </thead>
          <tbody>
            <tr><td>Antes</td>${group.details.map((detail) => `<td class="before changed-cell">${escapeHtml(formatValue(detail.antes))}</td>`).join("")}</tr>
            <tr><td>Depois</td>${group.details.map((detail) => `<td class="after changed-cell">${escapeHtml(formatValue(detail.depois))}</td>`).join("")}</tr>
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderOverviewItem(item) {
  const date = new Date(item.dataHora);
  const clientLabel = item.cliente || formatValue(item.depois) || formatValue(item.antes);
  const negotiatorLabel = item.negociadorId
    ? `<button class="link-btn overview-link" type="button" data-overview-negociador="${escapeAttr(item.id)}">${escapeHtml(item.usuario)}</button>`
    : `<strong>${escapeHtml(item.usuario)}</strong>`;
  const clientButton = item.negociadorId
    ? `<button class="link-btn overview-link" type="button" data-overview-client="${escapeAttr(item.id)}">${escapeHtml(clientLabel)}</button>`
    : `<button class="link-btn" type="button" data-overview-detail="${escapeAttr(item.id)}">${escapeHtml(clientLabel)}</button>`;
  return `
    <article class="overview-item ${escapeAttr(item.prioridade)} ${item.lido ? "read" : ""}" data-id="${escapeAttr(item.id)}" data-overview-row="${escapeAttr(item.id)}" tabindex="0">
      <span class="overview-dot"></span>
      <div class="overview-main">
        <div class="overview-summary">
          <span class="overview-event-label">${escapeHtml(item.campo)}</span>
          ${clientButton}
          <span class="overview-meta">${escapeHtml(item.tipo)} &middot; ${item.details?.length || 1} campos</span>
        </div>
        <div class="overview-title">
          ${negotiatorLabel}
          <span class="overview-sheet-badge">${escapeHtml(item.sheet)}</span>
          <time>${date.toLocaleDateString()} ${date.toLocaleTimeString()}</time>
        </div>
      </div>
      <div class="overview-row-actions">
        <span class="overview-priority">${escapeHtml(item.prioridade || "normal")}</span>
        ${item.lido ? `<span class="read-pill">Lido</span>` : `<button class="overview-read" type="button" data-read="${escapeAttr(item.id)}" title="Marcar como lido" aria-label="Marcar como lido">&#10003;</button>`}
      </div>
    </article>
  `;
}

function groupedOverview(items) {
  const groups = new Map();
  items.forEach((item) => {
    const carteira = item.carteira || "Carteira nao informada";
    const cliente = item.cliente || "Cliente nao identificado";
    const key = `${carteira}||${cliente}`;
    if (!groups.has(key)) groups.set(key, { carteira, cliente, items: [] });
    groups.get(key).items.push(item);
  });
  return [...groups.values()];
}

async function openOverviewNegotiator(itemId) {
  const item = state.overview.find((overviewItem) => overviewItem.id === itemId);
  if (!item?.negociadorId) return;
  await callbacks.openNegociador(Number(item.negociadorId));
}

async function openOverviewClient(itemId) {
  const item = state.overview.find((overviewItem) => overviewItem.id === itemId);
  if (!item?.negociadorId) return;
  await callbacks.openNegociadorWithClientFilter(Number(item.negociadorId), item.cliente || "");
}

function openOverviewDetails(itemId) {
  const item = state.overview.find((overviewItem) => overviewItem.id === itemId);
  if (!item) return;
  const date = new Date(item.dataHora);
  const details = item.details || [];
  const lineCount = new Set(details.map((detail) => String(detail.linha || "nao identificada"))).size;
  const client = item.cliente || "Cliente nao identificado";
  $("#overviewDrawerEyebrow").textContent = item.campo || item.tipo || "Alteracao";
  $("#overviewDrawerTitle").textContent = client;
  $("#overviewDrawerSubtitle").textContent = `${date.toLocaleDateString()} as ${date.toLocaleTimeString()}`;
  $("#overviewDetails").innerHTML = `
    <div class="overview-audit-meta">
      <div><span>Responsavel</span><strong>${escapeHtml(item.usuario)}</strong></div>
      <div><span>Sheet</span><strong>${escapeHtml(item.sheet)}</strong></div>
      <div><span>Carteira</span><strong>${escapeHtml(item.carteira || "Nao informada")}</strong></div>
      <div><span>Linha</span><strong>${lineCount === 1 ? escapeHtml(details[0]?.linha || "Nao identificada") : `${lineCount} linhas`}</strong></div>
    </div>
    <section class="overview-audit-comparison">
      <div class="overview-audit-summary">
        <div>
          <h3>${escapeHtml(item.campo || "Alteracao")}</h3>
          <p>Comparativo dos dados registrados nesta alteracao.</p>
        </div>
        <div class="overview-audit-badges">
          <span>${details.length || 1} campos</span>
          <span>${escapeHtml(item.tipo || "Atualizacao")}</span>
        </div>
      </div>
      ${renderChangesTable(details)}
    </section>
  `;
  $("#overviewDrawerFooter").innerHTML = `
    <button type="button" class="secondary-btn ds-button" data-overview-drawer-close>Fechar</button>
    <div class="overview-drawer-primary-actions">
      ${item.negociadorId ? `<button type="button" class="secondary-btn ds-button" data-overview-drawer-negotiator>Abrir negociador</button>` : ""}
      ${item.lido ? "" : `<button type="button" class="primary-btn ds-button ds-button--primary" data-overview-drawer-read>Marcar como lido</button>`}
    </div>
  `;
  $("#overviewDrawerFooter").querySelector("[data-overview-drawer-close]")?.addEventListener("click", closeOverviewDetails);
  $("#overviewDrawerFooter").querySelector("[data-overview-drawer-negotiator]")?.addEventListener("click", async () => {
    closeOverviewDetails();
    await callbacks.openNegociador(Number(item.negociadorId));
  });
  $("#overviewDrawerFooter").querySelector("[data-overview-drawer-read]")?.addEventListener("click", async () => {
    await callbacks.markRead(item.id);
    closeOverviewDetails();
  });
  $("#overviewDrawer").classList.add("open");
  $("#overviewDrawer").setAttribute("aria-hidden", "false");
  $("#drawerBackdrop").classList.add("open");
  document.body.classList.add("drawer-open");
}
