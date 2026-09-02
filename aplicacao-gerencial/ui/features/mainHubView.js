import { $, preserveScroll } from "../core/dom.js";
import { formatValue } from "../core/format.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { clearLoading } from "../core/loading.js";
import { state } from "../core/state.js";
import { closeDialog } from "../layout/dialogs.js";
import { findHubCard, hubCards } from "./mainHubCards.js";
import { renderChangesTable } from "./overview.js?v=20260717-overview-drawer-1";
import { parecerPk, parecerValue } from "./parecerData.js";
import { protocoloValue } from "./protocoloData.js";
import { renderNotesPanel } from "./notes.js?v=20260717-main-hub-audit-1";

const callbacks = {
  runAction: async () => {},
};

let selectedSource = "all";
let searchTerm = "";

export function configureMainHubView(options = {}) {
  Object.assign(callbacks, options);
}

export function renderMainHub() {
  const count = state.hub.overview.length + state.hub.pareceres.length + state.hub.protocolos.length + (state.hub.ferramentas || []).length;
  $("#mainHubBadge").textContent = count;
  $("#mainHubBadge").classList.toggle("hidden", count === 0);
  const allCards = hubCards();
  updateMainHubControls(allCards);
  bindMainHubControls();
  const cards = filterHubCards(allCards);
  const list = $("#mainHubList");
  const signature = JSON.stringify({
    selectedSource,
    searchTerm,
    cards: cards.map(({ id, source, title, subtitle, meta, action, tag, date }) => ({ id, source, title, subtitle, meta, action, tag, date })),
  });
  if (!list.classList.contains("is-loading") && list.dataset.signature === signature) return;
  preserveScroll("#mainHubList", () => {
    clearLoading("#mainHubList");
    list.classList.toggle("stable-render", list.dataset.rendered === "true");
    list.innerHTML = cards.length
      ? `<div class="hub-card-list">${groupHubCards(cards).map(renderHubGroup).join("")}</div>`
      : `<div class="empty-overview ds-card">Nenhuma pendencia encontrada.</div>`;
    list.dataset.signature = signature;
    list.dataset.rendered = "true";
  });
  if (!cards.length) return;
  document.querySelectorAll("[data-hub-card]").forEach((button) => {
    button.addEventListener("click", () => openMainHubDetails(button.dataset.hubCard));
  });
}

function bindMainHubControls() {
  const search = $("#mainHubSearch");
  if (search && search.dataset.bound !== "true") {
    search.dataset.bound = "true";
    search.addEventListener("input", () => {
      searchTerm = search.value.trim().toLocaleLowerCase("pt-BR");
      renderMainHub();
    });
  }
  document.querySelectorAll("[data-hub-source]").forEach((button) => {
    if (button.dataset.bound === "true") return;
    button.dataset.bound = "true";
    button.addEventListener("click", () => {
      selectedSource = button.dataset.hubSource || "all";
      renderMainHub();
    });
  });
}

function updateMainHubControls(cards) {
  const counts = {
    all: cards.length,
    monitoramento: cards.filter((card) => card.source === "monitoramento").length,
    parecer: cards.filter((card) => card.source === "parecer").length,
    protocolo: cards.filter((card) => card.source === "protocolo").length,
  };
  $("#mainHubCountAll").textContent = counts.all;
  $("#mainHubCountMonitoramento").textContent = counts.monitoramento;
  $("#mainHubCountParecer").textContent = counts.parecer;
  $("#mainHubCountProtocolo").textContent = counts.protocolo;
  $("#mainHubMetricPending").textContent = counts.all;
  $("#mainHubMetricCritical").textContent = cards.filter(isCriticalHubCard).length;
  $("#mainHubMetricToday").textContent = cards.filter((card) => hubPeriod(card.date) === "Hoje").length;
  $("#mainHubMetricUpdated").textContent = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  document.querySelectorAll("[data-hub-source]").forEach((button) => {
    button.classList.toggle("active", button.dataset.hubSource === selectedSource);
  });
}

function filterHubCards(cards) {
  return cards.filter((card) => {
    if (selectedSource !== "all" && card.source !== selectedSource) return false;
    if (!searchTerm) return true;
    return [card.title, card.subtitle, card.meta, card.tag]
      .map((value) => String(value || "").toLocaleLowerCase("pt-BR"))
      .some((value) => value.includes(searchTerm));
  });
}

function renderHubGroup(group) {
  return `
    <section class="hub-period-group">
      <header><strong>${escapeHtml(group.label)}</strong><span>${group.cards.length} itens</span></header>
      <div class="hub-period-list">${group.cards.map(renderHubCard).join("")}</div>
    </section>
  `;
}

function renderHubCard(card) {
  return `
    <button class="hub-card ds-card ds-card--compact ${escapeAttr(card.source)}" type="button" data-hub-card="${escapeAttr(card.id)}">
      <span class="hub-source-tag">${escapeHtml(card.tag)}</span>
      <span class="hub-card-main">
        <strong>${escapeHtml(formatValue(card.title))}</strong>
        <small>${escapeHtml(formatValue(card.subtitle))} <span>&middot;</span> ${escapeHtml(formatValue(card.meta))}</small>
      </span>
      <span class="hub-card-side">
        <span class="hub-card-date">${escapeHtml(formatHubDateTime(card.date))}</span>
        <span class="hub-card-open" aria-hidden="true">&rsaquo;</span>
      </span>
    </button>
  `;
}

function groupHubCards(cards) {
  const labels = ["Hoje", "Ontem", "Esta semana", "Anteriores", "Sem data"];
  const groups = new Map(labels.map((label) => [label, []]));
  cards.forEach((card) => groups.get(hubPeriod(card.date)).push(card));
  return labels.map((label) => ({ label, cards: groups.get(label) })).filter((group) => group.cards.length);
}

function hubPeriod(value) {
  const date = parseHubDate(value);
  if (!date) return "Sem data";
  const today = startOfDay(new Date());
  const target = startOfDay(date);
  const diff = Math.round((today - target) / 86400000);
  if (diff === 0) return "Hoje";
  if (diff === 1) return "Ontem";
  if (diff > 1 && diff <= 6) return "Esta semana";
  return "Anteriores";
}

function parseHubDate(value) {
  const raw = String(value || "").trim();
  if (!raw) return null;
  const brDate = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})(?:\s+(\d{1,2}):(\d{2}))?/);
  if (brDate) return new Date(Number(brDate[3]), Number(brDate[2]) - 1, Number(brDate[1]), Number(brDate[4] || 0), Number(brDate[5] || 0));
  const date = new Date(raw.replace(" ", "T"));
  return Number.isNaN(date.getTime()) ? null : date;
}

function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function isCriticalHubCard(card) {
  return ["critica", "alta"].includes(String(card.raw?.prioridade || "").toLocaleLowerCase("pt-BR"));
}

async function openMainHubDetails(cardId) {
  const card = findHubCard(cardId);
  if (!card) return;
  const dialog = $("#mainHubDialog");
  dialog.dataset.source = card.source;
  $("#mainHubDialogIcon").innerHTML = sourceIcon(card.source);
  $("#mainHubDialogTitle").textContent = formatValue(card.title);
  $("#mainHubDialogBadge").textContent = hubDetailBadge(card);
  $("#mainHubDialogSubtitle").textContent = `${card.tag} · ${formatHubDateTime(card.date)}`;
  $("#mainHubDetails").innerHTML = `
    ${renderHubDetailBody(card)}
    <details class="hub-notes-disclosure">
      <summary><span>Observações</span><span data-notes-count>0 registros</span></summary>
      <div id="mainHubNotes"></div>
    </details>
  `;
  $("#mainHubDialogFooter").innerHTML = `
    <button class="secondary-btn ds-button" type="button" data-close-hub-action>Fechar</button>
    <button class="primary-btn ds-button ds-button--primary fit" type="button" data-hub-action="${escapeAttr(card.id)}">${svgIcon(actionIcon(card.source))}${escapeHtml(hubActionLabel(card))}</button>
  `;
  $("#mainHubDialogFooter").querySelector("[data-close-hub-action]").addEventListener("click", () => closeDialog("#mainHubDialog"));
  $("#mainHubDialogFooter").querySelector("[data-hub-action]").addEventListener("click", () => callbacks.runAction(card.id));
  dialog.showModal();
  const target = noteTargetForHubCard(card);
  if (target) await renderNotesPanel(target.type, target.id, "#mainHubNotes");
}

function renderHubDetailBody(card) {
  if (card.source === "monitoramento") {
    const item = card.raw;
    const details = item.details || [];
    return `
      <div class="hub-info-grid">
        ${renderHubInfoCard("Responsável", item.usuario)}
        ${renderHubInfoCard("Sheet", item.sheet)}
        ${renderHubInfoCard("Carteira", item.carteira || "Não informada")}
        ${renderHubInfoCard("Linha", detailLineLabel(details))}
      </div>
      <div class="hub-diff-section">
        ${renderSectionHead(item.campo || "Alteração", "Valores registrados antes e depois.", `${details.length || 1} campos`)}
        ${renderChangesTable(details)}
      </div>
    `;
  }
  if (card.source === "parecer") {
    const row = card.raw;
    return `
      <div class="hub-info-grid">
        ${renderHubInfoCard("Negociador", parecerValue(row, ["OPERADOR", "NEGOCIADOR"]))}
        ${renderHubInfoCard("NPJ", parecerValue(row, ["NPJ"]) || parecerPk(row))}
        ${renderHubInfoCard("Motivo", parecerValue(row, ["MOTIVO"]))}
        ${renderHubInfoCard("Situação", "Pendente")}
      </div>
      <div class="hub-text-section">
        ${renderSectionHead("Descrição", "Contexto informado na solicitação.")}
        <p>${escapeHtml(formatValue(parecerValue(row, ["DESCRICAO", "DESCRIÇÃO", "DESCRIÃ‡ÃƒO", "OBSERVACAO", "OBSERVAÇÃO", "OBSERVAÃ‡ÃƒO"])))}</p>
      </div>
    `;
  }
  if (card.source === "ferramenta") {
    const row = card.raw;
    return `
      <div class="hub-info-grid">
        ${renderHubInfoCard("Ferramenta", row.ferramenta)}
        ${renderHubInfoCard("Status", row.status_nome || row.status)}
        ${renderHubInfoCard("Negociador", row.negociador)}
        ${renderHubInfoCard("Carteira", row.carteira)}
      </div>
      <div class="hub-diff-section">
        ${renderSectionHead("Informacoes da pendencia", "Campos definidos na configuracao da ferramenta.", `${(row.fields || []).length} campos`)}
        <div class="hub-info-grid">${(row.fields || []).map((field) => renderHubInfoCard(field.label, field.value)).join("") || renderHubInfoCard("Registro", row.titulo)}</div>
      </div>
    `;
  }
  const row = card.raw;
  return `
    <div class="hub-info-grid">
      ${renderHubInfoCard("Data de solicitação", protocoloValue(row, ["DATA DE SOLICITAÇÃO", "DATA DE SOLICITACAO", "DATA DE SOLICITAÃ‡ÃƒO"]))}
      ${renderHubInfoCard("Carteira", protocoloValue(row, ["CARTEIRA"]))}
      ${renderHubInfoCard("PJ", protocoloValue(row, ["PJ"]))}
      ${renderHubInfoCard("Processo", protocoloValue(row, ["PROCESSO"]))}
    </div>
    <div class="hub-text-section">
      ${renderSectionHead("Observação", "Informações registradas no protocolo.")}
      <p>${escapeHtml(formatValue(protocoloValue(row, ["OBSERVAÇÃO", "OBSERVACAO", "OBSERVAÃ‡ÃƒO"])))}</p>
    </div>
  `;
}

function renderHubInfoCard(label, value) {
  return `
    <div class="hub-info-card ds-card ds-card--compact">
      <small>${escapeHtml(label)}</small>
      <strong title="${escapeAttr(formatValue(value))}">${escapeHtml(formatValue(value))}</strong>
    </div>
  `;
}

function renderSectionHead(title, subtitle, count = "") {
  return `
    <div class="hub-section-head">
      <div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(subtitle)}</p></div>
      ${count ? `<span>${escapeHtml(count)}</span>` : ""}
    </div>
  `;
}

function detailLineLabel(details) {
  const lines = [...new Set(details.map((detail) => String(detail.linha || "").trim()).filter(Boolean))];
  if (!lines.length) return "Não identificada";
  return lines.length === 1 ? lines[0] : `${lines.length} linhas`;
}

function hubDetailBadge(card) {
  if (card.source === "ferramenta") return formatValue(card.raw?.status_nome || card.raw?.status || "Pendente");
  if (card.source === "monitoramento") return formatValue(card.raw?.campo || card.raw?.tipo || "Alteração");
  return card.source === "parecer" ? "Parecer pendente" : "Protocolo pendente";
}

function hubActionLabel(card) {
  if (card.source === "ferramenta") return "Abrir ferramenta";
  if (card.source === "monitoramento") return "Marcar como lido";
  if (card.source === "parecer") return "Marcar como solicitado";
  return "Marcar como concluído";
}

function formatHubDateTime(value) {
  const raw = String(value || "").trim();
  if (!raw) return "Pendente";
  const normalized = raw.includes("/") ? "" : raw.replace(" ", "T");
  const date = normalized ? new Date(normalized) : new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  const datePart = date.toLocaleDateString("pt-BR");
  const time = /\d{1,2}:\d{2}/.test(raw) ? date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "";
  if (hubPeriod(value) === "Hoje") return time ? `Hoje, ${time}` : "Hoje";
  if (hubPeriod(value) === "Ontem") return time ? `Ontem, ${time}` : "Ontem";
  return time ? `${datePart} \u2022 ${time}` : datePart;
}

function actionIcon(source) {
  return ["monitoramento", "ferramenta"].includes(source) ? "eye" : "check";
}

function sourceIcon(source) {
  return svgIcon(source === "monitoramento" ? "user" : ["parecer", "ferramenta"].includes(source) ? "eye" : "file");
}

function svgIcon(name) {
  const icons = {
    bank: `<svg viewBox="0 0 24 24" fill="none"><path d="M3 10h18"></path><path d="M5 10v8"></path><path d="M9 10v8"></path><path d="M15 10v8"></path><path d="M19 10v8"></path><path d="M4 18h16"></path><path d="M12 4 4 8h16l-8-4Z"></path></svg>`,
    briefcase: `<svg viewBox="0 0 24 24" fill="none"><path d="M9 7V5h6v2"></path><rect x="4" y="7" width="16" height="12" rx="2"></rect><path d="M4 12h16"></path><path d="M10 12v2h4v-2"></path></svg>`,
    calendar: `<svg viewBox="0 0 24 24" fill="none"><rect x="4" y="5" width="16" height="15" rx="2"></rect><path d="M8 3v4"></path><path d="M16 3v4"></path><path d="M4 10h16"></path></svg>`,
    chart: `<svg viewBox="0 0 24 24" fill="none"><path d="M5 19V9"></path><path d="M12 19V5"></path><path d="M19 19v-7"></path><path d="M3 19h18"></path></svg>`,
    check: `<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9"></circle><path d="m8 12 3 3 5-6"></path></svg>`,
    eye: `<svg viewBox="0 0 24 24" fill="none"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="3"></circle></svg>`,
    file: `<svg viewBox="0 0 24 24" fill="none"><path d="M6 3h8l4 4v14H6V3Z"></path><path d="M14 3v5h5"></path></svg>`,
    info: `<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9"></circle><path d="M12 10v6"></path><path d="M12 7h.01"></path></svg>`,
    user: `<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="8" r="4"></circle><path d="M4 21a8 8 0 0 1 16 0"></path></svg>`,
  };
  return icons[name] || icons.info;
}

function noteTargetForHubCard(card) {
  if (card.source === "monitoramento") return { type: "event", id: card.raw?.eventId || card.raw?.id || card.id };
  if (card.source === "parecer") return { type: "parecer", id: parecerPk(card.raw) };
  if (card.source === "protocolo") return { type: "protocolo", id: card.raw?.__row_number };
  return null;
}
