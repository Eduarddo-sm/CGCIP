import { api } from "../core/api.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { mountOperationalExcelGrid, headersFromRows, isGridDateHeader, isGridMoneyHeader, operationalColumnWidth } from "./operationalExcelGrid.js?v=20260727-carteira-workspace-5";
import { NON_EDITABLE_HEADERS } from "./monitorPlanilhaConstants.js?v=20260713-gerencial-edit-all-1";
import { saveMonitorPlanilhaCell } from "./monitorPlanilha.js?v=20260825-beta-repurchase-1";
import { renderAlphaHonorarios } from "./alphaHonorarios.js?v=20260728-alpha-ho-2";

const cache = new Map();
const grids = new Map();
const loading = new Set();
const productionPeriods = new Map();
const dynamicScreenState = new Map();
let focusPanel = null;

const FIXED_TABS = [
  ["overview", "Visao geral", "grid"],
  ["monitor", "Monitoramento", "activity"],
  ["production", "Producao diaria", "sheet"],
  ["pareceres", "Pareceres", "file"],
  ["colchao", "Colchao", "sheet"],
];

function icon(name) {
  const paths = {
    grid: '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>',
    activity: '<path d="M4 12h4l2-6 4 12 2-6h4"/>',
    sheet: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
    file: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.4-2.4 1a7 7 0 0 0-1.7-1L14.5 3h-5l-.4 3.1a7 7 0 0 0-1.7 1L5 6.1 3 9.5 5.1 11a7 7 0 0 0 0 2L3 14.5 5 18l2.4-1a7 7 0 0 0 1.7 1l.4 3h5l.4-3a7 7 0 0 0 1.7-1l2.4 1 2-3.5-2.1-1.5a7 7 0 0 0 .1-1z"/>',
    percent: '<path d="M19 5 5 19"/><circle cx="7" cy="7" r="2.5"/><circle cx="17" cy="17" r="2.5"/>',
  };
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.file}</svg>`;
}

function normalize(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toUpperCase();
}

function dynamicFilterConfig(raw = {}) {
  const explicit = ["mostrar_status", "mostrar_negociador", "mostrar_carteira", "mostrar_ordenacao", "campos"]
    .some((key) => Object.prototype.hasOwnProperty.call(raw, key));
  return {
    mostrar_status: explicit ? Boolean(raw.mostrar_status) : true,
    mostrar_negociador: explicit ? Boolean(raw.mostrar_negociador) : true,
    mostrar_carteira: Boolean(raw.mostrar_carteira),
    mostrar_ordenacao: explicit ? Boolean(raw.mostrar_ordenacao) : true,
    campos: Array.isArray(raw.campos) ? raw.campos : [],
    ...raw,
  };
}

function dynamicFilterText(value) {
  if (Array.isArray(value)) return value.map(dynamicFilterText).join(", ");
  if (value && typeof value === "object") return Object.values(value).map(dynamicFilterText).join(", ");
  return String(value ?? "").trim();
}

function dynamicGroupingConfig(screen, filters) {
  const raw = screen?.agrupamento || {};
  const allowed = new Set(["none", "deadline", "status", "field"]);
  return {
    modo: allowed.has(raw.modo) ? raw.modo : (filters?.agrupar_prazo ? "deadline" : "none"),
    campo: raw.campo || "",
    iniciar_recolhido: Object.prototype.hasOwnProperty.call(raw, "iniciar_recolhido")
      ? Boolean(raw.iniciar_recolhido) : Boolean(filters?.iniciar_recolhido),
  };
}

function dynamicCardActions(screen) {
  const raw = screen?.acoes_card || {};
  return {
    copiar: Boolean(raw.copiar),
    copiar_campos: Array.isArray(raw.copiar_campos) ? raw.copiar_campos : [],
    observacoes: Boolean(raw.observacoes),
    mostrar_atualizacao: Object.prototype.hasOwnProperty.call(raw, "mostrar_atualizacao")
      ? Boolean(raw.mostrar_atualizacao)
      : true,
    status_modo: ["none", "open", "select", "button"].includes(raw.status_modo) ? raw.status_modo : "open",
    status_origem: raw.status_origem === "field" ? "field" : "flow",
    status_campo: raw.status_campo || "",
    botao_rotulo: raw.botao_rotulo || "Abrir",
    botao_status: raw.botao_status || "",
  };
}

function dynamicRecordTimestamp(value) {
  const date = new Date(value || 0);
  return Number.isNaN(date.getTime()) ? 0 : date.getTime();
}

function dynamicRecordUpdatedLabel(value) {
  const timestamp = dynamicRecordTimestamp(value);
  if (!timestamp) return "Atualizacao nao informada";
  const elapsedMinutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60000));
  if (elapsedMinutes < 1) return "Atualizado agora";
  if (elapsedMinutes < 60) return `Atualizado ha ${elapsedMinutes} min`;
  const elapsedHours = Math.floor(elapsedMinutes / 60);
  if (elapsedHours < 24) return `Atualizado ha ${elapsedHours}h`;
  return `Atualizado em ${new Date(timestamp).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}`;
}

function dynamicDateValue(value) {
  if (!value) return null;
  const text = String(value).trim();
  const br = text.match(/^(\d{2})\/(\d{2})\/(\d{4})/);
  const date = br
    ? new Date(Number(br[3]), Number(br[2]) - 1, Number(br[1]))
    : new Date(text.length === 10 ? `${text}T12:00:00` : text);
  if (Number.isNaN(date.getTime())) return null;
  date.setHours(0, 0, 0, 0);
  return date;
}

function deadlineBucket(value, status = "", statuses = []) {
  if (statuses.some((item) => item.codigo === status && item.final)) return "completed";
  const date = dynamicDateValue(value);
  if (!date) return "no_date";
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = Math.round((date.getTime() - today.getTime()) / 86400000);
  if (days < 0) return "overdue";
  if (days === 0) return "today";
  if (days <= 3) return "next3";
  if (days <= 7) return "next7";
  if (days <= 30) return "next30";
  return "later";
}

const deadlineLabels = {
  overdue: "Vencidos",
  today: "Vence hoje",
  next3: "Proximos 3 dias",
  next7: "Proximos 7 dias",
  next30: "Proximos 30 dias",
  later: "Posteriores",
  no_date: "Sem data",
  completed: "Encerrados",
};

function visibleDeadlineEntries(filterConfig = {}) {
  const configured = filterConfig.prazos_visiveis;
  const allowed = Array.isArray(configured) ? new Set(configured) : null;
  return [["all", "Todos os prazos"], ...Object.entries(deadlineLabels)]
    .filter(([value]) => !allowed || allowed.has(value));
}

function rowsFrom(payload) {
  if (Array.isArray(payload)) return payload;
  return payload?.rows || payload?.items || payload?.records || [];
}

function currentPeriod() {
  const now = new Date();
  return { month: now.getMonth() + 1, year: now.getFullYear() };
}

function monthOptions(selected) {
  const formatter = new Intl.DateTimeFormat("pt-BR", { month: "long" });
  return Array.from({ length: 12 }, (_, index) => {
    const value = index + 1;
    const label = formatter.format(new Date(2026, index, 1)).replace(/^\w/, (char) => char.toUpperCase());
    return `<option value="${value}" ${value === selected ? "selected" : ""}>${escapeHtml(label)}</option>`;
  }).join("");
}

function yearOptions(selected) {
  const current = new Date().getFullYear();
  const years = new Set([selected, current - 2, current - 1, current, current + 1]);
  return [...years].sort((left, right) => right - left)
    .map((value) => `<option value="${value}" ${value === selected ? "selected" : ""}>${value}</option>`)
    .join("");
}

function publishedVersion(tool) {
  return (tool?.versoes || []).find((version) => version.status === "PUBLICADA");
}

function permissionAllows(definition, wallet) {
  const permissions = definition?.permissoes || [];
  if (!permissions.length) return true;
  const target = normalize(wallet);
  return permissions.some((permission) => {
    const permittedWallet = normalize(permission.carteira);
    return (!permittedWallet || permittedWallet === target) && permission.pode_visualizar !== false;
  });
}

async function loadWorkspace(group, force = false) {
  const key = normalize(group.carteira);
  if (!force && cache.has(key)) return cache.get(key);
  if (loading.has(key)) return cache.get(key) || null;
  loading.add(key);
  try {
    const { month, year } = productionPeriods.get(key) || currentPeriod();
    const [production, pareceres, toolList, toolSettings] = await Promise.all([
      api(`/api/monitoramento/planilha?carteira=${encodeURIComponent(group.carteira)}&mes=${month}&ano=${year}`).catch(() => ({ rows: [] })),
      api("/api/pareceres").catch(() => []),
      api("/api/config/ferramentas-negociais").catch(() => ({ items: [] })),
      api(`/api/config/carteiras/${encodeURIComponent(group.carteira)}/ferramentas`).catch(() => ({ items: [] })),
    ]);
    const summaries = (toolList.items || []).filter((tool) => tool.active && publishedVersion(tool));
    const definitions = await Promise.all(summaries.map(async (summary) => {
      try {
        const payload = await api(`/api/config/ferramentas-negociais/${summary.id}?version_id=${publishedVersion(summary).id}`);
        return { ...summary, ...(payload.item || payload) };
      } catch {
        return summary;
      }
    }));
    const allTools = definitions.filter((tool) => permissionAllows(tool, group.carteira));
    const configuredTools = toolSettings.items?.length
      ? toolSettings.items
        : [
          { key: "production", nome: "Producao diaria", enabled: true, locked: true },
          { key: "pareceres", nome: "Pareceres", enabled: true, locked: false },
          { key: "colchao", nome: "Colchao", enabled: ["ALPHA", "BETA"].includes(key), locked: false },
          ...allTools.map((tool) => ({
            key: `tool:${tool.id}`,
            nome: tool.nome,
            enabled: true,
            locked: false,
          })),
        ];
    const settings = new Map(configuredTools.map((item) => [String(item.key).toLowerCase(), item]));
    const tools = allTools.filter((tool) => settings.get(`tool:${tool.id}`)?.enabled !== false);
    const pareceresEnabled = settings.get("pareceres")?.enabled !== false;
    const colchaoEnabled = settings.get("colchao")?.enabled === true;
    const parecerRows = rowsFrom(pareceres).filter((row) => normalize(row.CARTEIRA || row.carteira || "GAMMA") === key);
    const data = {
      production,
      pareceres: parecerRows,
      pareceresEnabled,
      colchaoEnabled,
      tools,
      allTools,
      toolSettings: configuredTools,
      loadedAt: new Date(),
    };
    cache.set(key, data);
    return data;
  } finally {
    loading.delete(key);
  }
}

function tabButton(key, label, iconName, active, tool = null) {
  return `<button type="button" class="${active === key ? "active" : ""}" data-carteira-workspace-tab="${escapeAttr(key)}" ${tool ? `data-carteira-tool="${tool.id}"` : ""}>
    ${icon(iconName)}<span>${escapeHtml(label)}</span>
  </button>`;
}

function setPanelVisibility(active) {
  if (focusPanel && focusPanel.dataset.workspacePanel !== active) exitCarteiraWorkspaceFocus();
  const isMonitor = active === "monitor";
  document.querySelectorAll(".carteira-monitor-controls, #carteiraClientSummary, #carteiraMonitorTabs, #carteiraMonitor").forEach((element) => {
    element.classList.toggle("workspace-hidden", !isMonitor);
  });
  const panels = {
    overview: "#carteiraWorkspaceOverview",
    production: "#carteiraWorkspaceProduction",
    pareceres: "#carteiraWorkspacePareceres",
    colchao: "#carteiraWorkspaceColchao",
    honorarios: "#carteiraWorkspaceHonorarios",
    settings: "#carteiraWorkspaceSettings",
  };
  Object.entries(panels).forEach(([key, selector]) => {
    document.querySelector(selector)?.classList.toggle("hidden", active !== key);
  });
  document.querySelector("#carteiraWorkspaceDynamic")?.classList.toggle("hidden", !active.startsWith("tool:"));
  document.querySelectorAll(".carteira-workspace-panel").forEach((panel) => {
    panel.dataset.workspacePanel = panel.id === "carteiraWorkspaceProduction"
      ? "production"
      : panel.id === "carteiraWorkspacePareceres"
        ? "pareceres"
        : panel.id === "carteiraWorkspaceColchao"
          ? "colchao"
        : panel.id === "carteiraWorkspaceHonorarios"
          ? "honorarios"
        : panel.id === "carteiraWorkspaceSettings"
          ? "settings"
          : panel.id === "carteiraWorkspaceOverview"
            ? "overview"
            : active.startsWith("tool:")
              ? active
              : "";
  });
}

async function renderColchaoWorkspace(target, group) {
  if (!target) return;
  const profile = String(group.carteira || "").trim().toLowerCase();
  target.innerHTML = `<div class="workspace-loading">Carregando Colchao...</div>`;
  try {
    const [dashboard, pendencias, config] = await Promise.all([
      api(`/api/colchao/dashboard?profile=${encodeURIComponent(profile)}`),
      api(`/api/colchao/pendencias?profile=${encodeURIComponent(profile)}`),
      api(`/api/colchao/config?profile=${encodeURIComponent(profile)}`),
    ]);
    const pendingRows = rowsFrom(pendencias);
    target.innerHTML = `
      <section class="carteira-native-module">
        <header class="carteira-native-module-head">
          <div><span>MODULO NATIVO</span><h3>Colchao - ${escapeHtml(group.carteira)}</h3></div>
          <div class="carteira-native-module-actions"><strong>${Number(dashboard.total_registros || 0).toLocaleString("pt-BR")} registros</strong><button class="primary-btn ds-button compact" type="button" data-colchao-new>Novo acordo</button></div>
        </header>
        <nav class="carteira-native-tabs" aria-label="Paginas do Colchao">
          <button class="active" type="button" data-colchao-view="dashboard">Dashboard</button>
          <button type="button" data-colchao-view="pending">Pendencias <span>${Number(dashboard.pendencias || 0).toLocaleString("pt-BR")}</span></button>
          <button type="button" data-colchao-view="sheet">Planilha</button>
        </nav>
        <div class="carteira-native-view" data-colchao-content></div>
      </section>`;
    const content = target.querySelector("[data-colchao-content]");
    const renderDashboard = () => {
      content.innerHTML = `<div class="carteira-native-metrics">
        <div><span>Pendencias</span><strong>${Number(dashboard.pendencias || 0).toLocaleString("pt-BR")}</strong></div>
        <div><span>Vencidas</span><strong>${Number(dashboard.vencidas || 0).toLocaleString("pt-BR")}</strong></div>
        <div><span>Pagos</span><strong>${Number(dashboard.pagos || 0).toLocaleString("pt-BR")}</strong></div>
        <div><span>Valor em aberto</span><strong>${Number(dashboard.valor_aberto || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}</strong></div>
      </div>
      <div class="carteira-native-dashboard-grid">
        <article><span>Clientes ativos</span><strong>${Number(dashboard.clientes_ativos || 0).toLocaleString("pt-BR")}</strong><small>Com parcelas em aberto</small></article>
        <article><span>Valor pago</span><strong>${Number(dashboard.valor_pago || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}</strong><small>Consolidado da carteira</small></article>
        <article><span>Quebras</span><strong>${Number(dashboard.quebras || 0).toLocaleString("pt-BR")}</strong><small>Acordos identificados</small></article>
      </div>`;
    };
    const renderPending = () => {
      const rows = pendingRows.slice(0, 250);
      content.innerHTML = `<div class="carteira-native-list-head"><strong>${pendingRows.length.toLocaleString("pt-BR")} pendencias</strong><small>Ordenadas pelo vencimento mais proximo</small></div>
        <div class="carteira-native-list">
          ${rows.length ? rows.map((row) => `
            <article>
              <div><strong>${escapeHtml(row.CLIENTE || row.NOME || "Cliente nao informado")}</strong><small>${escapeHtml(row["DEBIT ID"] || row.SUITID || row.IDENTIFICADOR || "Sem identificador")}</small></div>
              <span>${escapeHtml(row.STATUS || "A VENCER")}</span>
              <small>${escapeHtml(String(row["DATA DO VENCIMENTO"] || row.MES || row.VENCIMENTO || "Sem vencimento"))}</small>
            </article>`).join("") : `<div class="empty-overview">Nenhuma pendencia nesta carteira.</div>`}
        </div>${pendingRows.length > rows.length ? `<p class="carteira-native-limit">Exibindo os primeiros ${rows.length.toLocaleString("pt-BR")} registros. Use a Planilha para consultar todos.</p>` : ""}`;
    };
    const renderSheet = async () => {
      content.innerHTML = `<div class="carteira-workspace-loading"><span></span><strong>Carregando planilha do Colchao...</strong></div>`;
      try {
        const payload = await api(`/api/colchao?profile=${encodeURIComponent(profile)}&all=1`);
        const rows = rowsFrom(payload);
        const gridTarget = renderSheetShell(
          content,
          `Colchao - ${group.carteira}`,
          `${rows.length.toLocaleString("pt-BR")} registros consolidados`,
          `<a class="secondary-btn ds-button compact" href="/api/colchao/relatorio.csv?profile=${encodeURIComponent(profile)}">Gerar relatorio</a>${focusButton()}`,
        );
        const gridKey = `colchao:${profile}`;
        grids.get(gridKey)?.destroy?.();
        grids.set(gridKey, mountOperationalExcelGrid(gridTarget, {
          id: `carteira-colchao-${normalize(group.carteira)}`,
          persistKey: `carteira-colchao-${normalize(group.carteira)}`,
          rows,
          columns: readonlyColumns(rows),
        }));
        bindFocus(content, gridKey);
      } catch (error) {
        content.innerHTML = `<div class="empty-overview">${escapeHtml(error.message || "Nao foi possivel carregar a planilha do Colchao.")}</div>`;
      }
    };
    const switchView = (view) => {
      target.querySelectorAll("[data-colchao-view]").forEach((button) => button.classList.toggle("active", button.dataset.colchaoView === view));
      if (view === "pending") renderPending();
      else if (view === "sheet") void renderSheet();
      else renderDashboard();
    };
    target.querySelectorAll("[data-colchao-view]").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.colchaoView)));
    renderDashboard();
    target.querySelector("[data-colchao-new]")?.addEventListener("click", () => openColchaoAgreementDialog(group, config, async () => {
      clearCarteiraWorkspaceCache(group.carteira);
      await renderColchaoWorkspace(target, group);
    }));
  } catch (error) {
    target.innerHTML = `<div class="empty-overview">${escapeHtml(error.message || "Nao foi possivel carregar o Colchao.")}</div>`;
  }
}

function ensureColchaoDialog(id, className) {
  let dialog = document.querySelector(`#${id}`);
  if (dialog) return dialog;
  dialog = document.createElement("dialog");
  dialog.id = id;
  dialog.className = className;
  document.body.appendChild(dialog);
  return dialog;
}

function fieldInput(field, value = "") {
  const attributes = `${field.required ? "required" : ""} data-colchao-field="${escapeAttr(field.key)}"`;
  if (field.type === "select") return `<select ${attributes}><option value="">Selecione</option>${(field.options || []).map((option) => `<option value="${escapeAttr(option)}">${escapeHtml(option)}</option>`).join("")}</select>`;
  if (field.type === "textarea") return `<textarea rows="3" ${attributes}>${escapeHtml(value)}</textarea>`;
  const type = field.type === "date" ? "date" : field.type === "number" ? "number" : "text";
  const inputMode = field.type === "money" ? ` inputmode="decimal"` : "";
  return `<input type="${type}" value="${escapeAttr(value)}"${inputMode} ${attributes}>`;
}

function openColchaoAgreementDialog(group, config, onSaved) {
  const dialog = ensureColchaoDialog("carteiraColchaoAgreementDialog", "carteira-colchao-dialog");
  const fields = (config.fields || []).filter((field) => field.enabled !== false).sort((left, right) => Number(left.order || 0) - Number(right.order || 0));
  dialog.innerHTML = `<form method="dialog" data-colchao-agreement-form>
    <header><div><span>Colchao - ${escapeHtml(group.carteira)}</span><h2>Novo acordo</h2></div><button class="icon-btn" type="button" data-close aria-label="Fechar">&times;</button></header>
    <section class="carteira-colchao-dialog-body"><div class="carteira-colchao-form-grid">${fields.map((field) => `<label class="${field.type === "textarea" ? "wide" : ""}"><span>${escapeHtml(field.label)}${field.required ? " *" : ""}</span>${fieldInput(field)}</label>`).join("")}</div><p class="carteira-colchao-form-error" data-error></p></section>
    <footer><button class="secondary-btn" type="button" data-close>Cancelar</button><button class="primary-btn fit" type="submit">Cadastrar acordo</button></footer>
  </form>`;
  dialog.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => dialog.close()));
  dialog.querySelector("form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = dialog.querySelector('[type="submit"]');
    const values = {};
    dialog.querySelectorAll("[data-colchao-field]").forEach((input) => { values[input.dataset.colchaoField] = input.value; });
    submit.disabled = true;
    try {
      await api("/api/colchao/acordos", { method: "POST", body: JSON.stringify({ profile: String(group.carteira).toLowerCase(), values }) });
      dialog.close();
      await onSaved?.();
    } catch (error) {
      dialog.querySelector("[data-error]").textContent = error.message || "Nao foi possivel cadastrar o acordo.";
      submit.disabled = false;
    }
  });
  if (!dialog.open) dialog.showModal();
}

async function openColchaoSettingsDialog(group, callbacks) {
  const profile = String(group.carteira || "").toLowerCase();
  const dialog = ensureColchaoDialog("carteiraColchaoSettingsDialog", "carteira-colchao-dialog settings");
  dialog.innerHTML = `<div class="workspace-loading">Carregando configuracao...</div>`;
  if (!dialog.open) dialog.showModal();
  try {
    const config = await api(`/api/colchao/config?profile=${encodeURIComponent(profile)}`);
    const fields = [...(config.fields || [])].sort((left, right) => Number(left.order || 0) - Number(right.order || 0));
    dialog.innerHTML = `<form method="dialog" data-colchao-settings-form>
      <header><div><span>Colchao - ${escapeHtml(group.carteira)}</span><h2>Estrutura do modulo</h2></div><button class="icon-btn" type="button" data-close aria-label="Fechar">&times;</button></header>
      <section class="carteira-colchao-dialog-body">
        <div class="carteira-colchao-settings-head"><span>Campo</span><span>Tipo</span><span>Obrigatorio</span><span>Exibir</span></div>
        <div class="carteira-colchao-settings-fields">${fields.map((field) => `<div data-config-field="${escapeAttr(field.key)}" data-role="${escapeAttr(field.role)}">
          <input name="label" value="${escapeAttr(field.label)}" aria-label="Nome do campo">
          <select name="type" aria-label="Tipo do campo">${["text", "number", "money", "date", "select", "textarea"].map((type) => `<option value="${type}" ${field.type === type ? "selected" : ""}>${type}</option>`).join("")}</select>
          <input name="required" type="checkbox" ${field.required ? "checked" : ""} aria-label="Campo obrigatorio">
          <input name="enabled" type="checkbox" ${field.enabled !== false ? "checked" : ""} aria-label="Exibir campo">
          ${field.type === "select" ? `<input class="wide" name="options" value="${escapeAttr((field.options || []).join(", "))}" placeholder="Opcoes separadas por virgula">` : ""}
        </div>`).join("")}</div>
        <label class="carteira-colchao-statuses"><span>Status permitidos</span><input name="statuses" value="${escapeAttr((config.statuses || []).join(", "))}"></label>
        <p class="carteira-colchao-form-error" data-error></p>
      </section>
      <footer><span>Versao ${Number(config.version || 0) || 1}</span><div><button class="secondary-btn" type="button" data-close>Cancelar</button><button class="primary-btn fit" type="submit">Salvar estrutura</button></div></footer>
    </form>`;
    dialog.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => dialog.close()));
    dialog.querySelector("form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const fieldsPayload = [...dialog.querySelectorAll("[data-config-field]")].map((row, index) => ({
        key: row.dataset.configField,
        role: row.dataset.role,
        label: row.querySelector('[name="label"]').value,
        type: row.querySelector('[name="type"]').value,
        required: row.querySelector('[name="required"]').checked,
        enabled: row.querySelector('[name="enabled"]').checked,
        order: index + 1,
        options: row.querySelector('[name="options"]')?.value || "",
      }));
      const submit = dialog.querySelector('[type="submit"]');
      submit.disabled = true;
      try {
        await api("/api/colchao/config", { method: "PUT", body: JSON.stringify({ profile, fields: fieldsPayload, statuses: dialog.querySelector('[name="statuses"]').value }) });
        dialog.close();
        clearCarteiraWorkspaceCache(group.carteira);
        await callbacks.onRefresh?.();
      } catch (error) {
        dialog.querySelector("[data-error]").textContent = error.message || "Nao foi possivel salvar a estrutura.";
        submit.disabled = false;
      }
    });
  } catch (error) {
    dialog.innerHTML = `<div class="empty-overview">${escapeHtml(error.message || "Nao foi possivel carregar a configuracao.")}</div><button class="secondary-btn" type="button" onclick="this.closest('dialog').close()">Fechar</button>`;
  }
}

function focusButton() {
  return `<button class="secondary-btn ds-button compact" type="button" data-carteira-sheet-focus>Modo foco</button>`;
}

function bindFocus(target, gridKey) {
  target.querySelector("[data-carteira-sheet-focus]")?.addEventListener("click", () => {
    const active = focusPanel !== target;
    exitCarteiraWorkspaceFocus();
    if (active) {
      focusPanel = target;
      target.classList.add("workspace-focus-target");
      document.body.classList.add("carteira-workspace-focus-mode");
      const button = target.querySelector("[data-carteira-sheet-focus]");
      if (button) button.textContent = "Sair do foco";
      window.requestAnimationFrame(() => window.requestAnimationFrame(() => grids.get(gridKey)?.refreshLayout?.()));
    }
  });
}

export function exitCarteiraWorkspaceFocus() {
  if (focusPanel) {
    focusPanel.classList.remove("workspace-focus-target");
    const button = focusPanel.querySelector("[data-carteira-sheet-focus]");
    if (button) button.textContent = "Modo foco";
  }
  focusPanel = null;
  document.body.classList.remove("carteira-workspace-focus-mode");
}

function renderLoading(target, label) {
  target.innerHTML = `<div class="carteira-workspace-loading"><span></span><strong>Carregando ${escapeHtml(label)}...</strong></div>`;
}

function productionRows(data) {
  return rowsFrom(data?.production);
}

function money(value) {
  const number = parseMoney(value);
  return number.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function parseMoney(value) {
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  const text = String(value ?? "").replace(/[^\d,.-]/g, "");
  if (!text) return 0;
  const normalized = text.includes(",") ? text.replace(/\./g, "").replace(",", ".") : text;
  return Number(normalized) || 0;
}

function dynamicDashboardAggregate(rows, block) {
  const aggregation = block.agregacao || "count";
  if (aggregation === "count") return rows.length;
  const values = rows.map((row) => parseMoney(row[block.campo])).filter(Number.isFinite);
  const secondary = rows.map((row) => parseMoney(row[block.campo_secundario])).filter(Number.isFinite);
  const total = values.reduce((sum, value) => sum + value, 0);
  const secondaryTotal = secondary.reduce((sum, value) => sum + value, 0);
  if (aggregation === "average") return values.length ? total / values.length : 0;
  if (aggregation === "min") return values.length ? Math.min(...values) : 0;
  if (aggregation === "max") return values.length ? Math.max(...values) : 0;
  if (aggregation === "ratio") return secondaryTotal ? (total / secondaryTotal) * 100 : 0;
  if (aggregation === "difference") return total - secondaryTotal;
  if (aggregation === "duration_average") {
    const durations = rows.map((row) => {
      const start = dynamicDateValue(row[block.campo]);
      const end = dynamicDateValue(row[block.campo_secundario]);
      return start && end ? Math.abs(end - start) / 86400000 : null;
    }).filter((value) => value !== null);
    return durations.length ? durations.reduce((sum, value) => sum + value, 0) / durations.length : 0;
  }
  return total;
}

function dynamicDashboardValue(value, block, fieldMap) {
  if ((block.agregacao || "count") === "count") return Number(value || 0).toLocaleString("pt-BR");
  if (block.agregacao === "ratio") return `${Number(value || 0).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
  if (block.agregacao === "duration_average") return `${Number(value || 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} dias`;
  const field = fieldMap.get(block.campo);
  return field?.tipo === "moeda"
    ? money(value)
    : Number(value || 0).toLocaleString("pt-BR", { maximumFractionDigits: 2 });
}

function renderDynamicDashboard(rows, definition, screen) {
  const statuses = definition.statuses || [];
  const fields = definition.campos || [];
  const fieldMap = new Map(fields.map((field) => [field.chave, field]));
  const fallback = [
    { id: "total", tipo: "metric", titulo: "Total de registros", agregacao: "count", cor: definition.cor || "#2563eb", largura: 3, status_codes: [] },
    { id: "status", tipo: "status", titulo: "Situacao dos registros", agregacao: "count", cor: definition.cor || "#2563eb", largura: 9, status_codes: [] },
  ];
  const blocks = screen.dashboard?.blocks?.length ? screen.dashboard.blocks : fallback;
  const scopedRows = (block) => rows.filter((row) => {
    if ((block.status_codes || []).length && !block.status_codes.includes(row.STATUS)) return false;
    if (!block.condicao_campo) return true;
    const raw = row[block.condicao_campo];
    const actual = dynamicFilterText(raw).toLocaleLowerCase("pt-BR");
    const expected = dynamicFilterText(block.condicao_valor).toLocaleLowerCase("pt-BR");
    const operator = block.condicao_operador || "eq";
    if (operator === "empty") return !actual;
    if (operator === "filled") return Boolean(actual);
    if (operator === "contains") return actual.includes(expected);
    if (operator === "neq") return actual !== expected;
    if (["gt", "gte", "lt", "lte"].includes(operator)) {
      const left = parseMoney(raw);
      const right = parseMoney(block.condicao_valor);
      return operator === "gt" ? left > right : operator === "gte" ? left >= right : operator === "lt" ? left < right : left <= right;
    }
    return actual === expected;
  });
  const groupedValues = (block, items) => {
    const groups = new Map();
    items.forEach((row) => {
      const label = dynamicFilterText(row[block.agrupador]) || "Nao informado";
      if (!groups.has(label)) groups.set(label, []);
      groups.get(label).push(row);
    });
    return [...groups.entries()]
      .map(([label, values]) => ({ label, value: dynamicDashboardAggregate(values, block), count: values.length, rows: values }))
      .sort((left, right) => right.value - left.value)
      .slice(0, Math.max(3, Number(block.limite || 8)));
  };
  const timelineValues = (block, items) => {
    const groups = new Map();
    items.forEach((row) => {
      const date = dynamicDateValue(row[block.agrupador]);
      if (!date) return;
      const key = block.periodo === "year"
        ? String(date.getFullYear())
        : block.periodo === "month"
          ? `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`
          : date.toISOString().slice(0, 10);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(row);
    });
    return [...groups.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .slice(-Math.max(3, Number(block.limite || 12)))
      .map(([label, values]) => ({ label, value: dynamicDashboardAggregate(values, block), count: values.length, rows: values }));
  };
  const barList = (values, block) => {
    const max = Math.max(...values.map((item) => item.value), 1);
    return `<div class="dynamic-dashboard-bars">${values.map((item) => `<button type="button" data-open-tool-record="${item.rows?.[0]?._record_id || ""}"><span><b>${escapeHtml(item.label)}</b><strong>${escapeHtml(dynamicDashboardValue(item.value, block, fieldMap))}</strong></span><i style="--bar-width:${Math.max(2, (item.value / max) * 100)}%"></i></button>`).join("") || '<small class="dynamic-dashboard-empty">Sem dados para este bloco.</small>'}</div>`;
  };
  const renderBlock = (block) => {
    const items = scopedRows(block);
    if (block.tipo === "metric") return `<button class="dynamic-dashboard-metric" type="button" data-open-tool-record="${items[0]?._record_id || ""}"><strong class="dynamic-dashboard-value">${escapeHtml(dynamicDashboardValue(dynamicDashboardAggregate(items, block), block, fieldMap))}</strong><small>${items.length.toLocaleString("pt-BR")} registro(s) considerados</small></button>`;
    if (["status", "funnel"].includes(block.tipo)) {
      const visible = (block.status_codes || []).length ? statuses.filter((status) => block.status_codes.includes(status.codigo)) : statuses;
      return `<div class="dynamic-dashboard-statuses ${block.tipo === "funnel" ? "funnel" : ""}">${visible.map((status) => { const statusRows = items.filter((row) => row.STATUS === status.codigo); return `<button type="button" data-open-tool-record="${statusRows[0]?._record_id || ""}" style="--item-color:${escapeAttr(status.cor || block.cor || "#2563eb")}"><i></i><b>${statusRows.length.toLocaleString("pt-BR")}</b><small>${escapeHtml(status.nome)}</small></button>`; }).join("") || '<small class="dynamic-dashboard-empty">Sem status configurados.</small>'}</div>`;
    }
    if (["distribution", "ranking"].includes(block.tipo)) return barList(groupedValues(block, items), block);
    if (block.tipo === "timeline") return barList(timelineValues(block, items), block);
    if (block.tipo === "comparison") {
      const timeline = timelineValues(block, items).slice(-2);
      const current = timeline.at(-1)?.value || 0;
      const previous = timeline.at(-2)?.value || 0;
      const variation = previous ? ((current - previous) / Math.abs(previous)) * 100 : 0;
      return `<div class="dynamic-dashboard-comparison"><strong>${escapeHtml(dynamicDashboardValue(current, block, fieldMap))}</strong><span class="${variation < 0 ? "negative" : "positive"}">${variation >= 0 ? "+" : ""}${variation.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%</span><small>Periodo anterior: ${escapeHtml(dynamicDashboardValue(previous, block, fieldMap))}</small></div>`;
    }
    if (block.tipo === "deadline") {
      const today = new Date(); today.setHours(0, 0, 0, 0);
      const buckets = [["Vencidos", (d) => d < today], ["Hoje", (d) => d.getTime() === today.getTime()], ["Proximos 7 dias", (d) => d > today && d <= new Date(today.getTime() + 7 * 86400000)], ["Posteriores", (d) => d > new Date(today.getTime() + 7 * 86400000)]];
      const values = buckets.map(([label, match]) => { const values = items.filter((row) => { const date = dynamicDateValue(row[block.agrupador]); return date && match(date); }); return { label, value: values.length, count: values.length, rows: values }; });
      return barList(values, { ...block, agregacao: "count" });
    }
    if (block.tipo === "validation") {
      const invalid = items.filter((row) => !dynamicFilterText(row[block.agrupador]));
      return `<button class="dynamic-dashboard-alert" type="button" data-open-tool-record="${invalid[0]?._record_id || ""}"><strong>${invalid.length.toLocaleString("pt-BR")}</strong><span>registro(s) sem ${escapeHtml(fieldMap.get(block.agrupador)?.nome || "valor obrigatorio")}</span></button>`;
    }
    const titleKey = definition.configuracao?.campo_titulo || "CLIENTE";
    const ordered = items.slice().sort((left, right) => dynamicRecordTimestamp(block.tipo === "queue" ? left.ATUALIZACAO : right.ATUALIZACAO) - dynamicRecordTimestamp(block.tipo === "queue" ? right.ATUALIZACAO : left.ATUALIZACAO));
    return `<div class="dynamic-dashboard-recent ${block.tipo === "queue" ? "queue" : ""}">${ordered.slice(0, Math.max(3, Number(block.limite || 6))).map((row) => `<button type="button" data-open-tool-record="${row._record_id}"><span><b>${escapeHtml(row[titleKey] || row.CLIENTE || `Registro ${row._record_id}`)}</b><small>${escapeHtml(row.NEGOCIADOR || "Nao informado")}</small></span><time>${escapeHtml(dynamicRecordUpdatedLabel(row.ATUALIZACAO))}</time></button>`).join("") || '<small class="dynamic-dashboard-empty">Nenhuma atualizacao encontrada.</small>'}</div>`;
  };
  return `<div class="carteira-dynamic-dashboard configurable">${blocks.map((block) => `<article class="block-${escapeAttr(block.tipo || "metric")}" style="--accent:${escapeAttr(block.cor || definition.cor || "#2563eb")};--dashboard-span:${Math.min(12, Math.max(3, Number(block.largura || 6)))}"><header><span>${escapeHtml(block.titulo || "Bloco")}</span><small>${rows.length.toLocaleString("pt-BR")} na tela</small></header>${renderBlock(block)}</article>`).join("")}</div>`;
}

function productionTotal(rows) {
  const keys = ["HONORARIOS_RECEBIDOS", "HONORÁRIOS RECEBIDOS", "HONORARIOS", "HONORÁRIOS", "VALOR DO ACORDO", "VALOR TOTAL"];
  return rows.reduce((total, row) => {
    const value = keys.map((key) => row[key]).find((item) => item !== undefined && item !== "");
    return total + parseMoney(value);
  }, 0);
}

function statusCount(rows, status) {
  return rows.filter((row) => normalize(row.STATUS || row.SITUACAO || row["SOLICITADO?"]) === status).length;
}

function renderOverview(target, group, data, active, callbacks) {
  const rows = productionRows(data);
  const eventCount = callbacks.eventCount?.(group.carteira) || 0;
  const toolLaunchers = [
    ["production", "Producao diaria", `${rows.length} registros`, "sheet"],
    ...(data.pareceresEnabled
      ? [["pareceres", "Pareceres", `${data.pareceres.length} registros`, "file"]]
      : []),
    ...data.tools.map((tool) => [`tool:${tool.id}`, tool.nome, `${tool.registros || 0} registros`, "file"]),
  ];
  const selectedPeriod = productionPeriods.get(normalize(group.carteira)) || currentPeriod();
  const month = new Date(selectedPeriod.year, selectedPeriod.month - 1, 1)
    .toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  target.innerHTML = `
    <div class="carteira-workspace-contextbar">
      <div><strong>Visao geral</strong><span>Indicadores e acessos da carteira ${escapeHtml(group.carteira)}</span></div>
      <button class="secondary-btn ds-button compact" type="button" data-refresh-carteira-workspace>Atualizar workspace</button>
    </div>
    <div class="carteira-workspace-summary">
      <article><span>Producao no mes</span><strong>${rows.length.toLocaleString("pt-BR")}</strong><small>${escapeHtml(month)}</small></article>
      <article><span>Valor consolidado</span><strong>${escapeHtml(money(productionTotal(rows)))}</strong><small>Registros ativos do periodo</small></article>
      ${data.pareceresEnabled
        ? `<article><span>Pareceres</span><strong>${data.pareceres.length.toLocaleString("pt-BR")}</strong><small>${statusCount(data.pareceres, "NAO")} pendentes</small></article>`
        : ""}
      <article><span>Alteracoes</span><strong>${eventCount.toLocaleString("pt-BR")}</strong><small>Historico monitorado</small></article>
    </div>
    <div class="carteira-workspace-overview-grid">
      <section class="carteira-workspace-card">
        <header><div><span>Operacao</span><h3>Ferramentas da carteira</h3></div></header>
        <div class="carteira-tool-launcher">
          ${toolLaunchers.map(([key, label, meta, iconName]) => `
            <button type="button" data-carteira-open-tab="${escapeAttr(key)}">
              <span>${icon(iconName)}</span><strong>${escapeHtml(label)}</strong><small>${escapeHtml(meta)}</small><b>›</b>
            </button>`).join("")}
        </div>
      </section>
      <section class="carteira-workspace-card">
        <header><div><span>Equipe</span><h3>Negociadores vinculados</h3></div><strong>${group.items.length}</strong></header>
        <div class="carteira-team-list">
          ${group.items.length ? group.items.slice(0, 8).map((item) => `
            <div><span>${escapeHtml(String(item.nome || "?").slice(0, 1).toUpperCase())}</span><strong>${escapeHtml(item.nome)}</strong><small>${item.online ? "Online" : "Offline"}</small></div>`).join("") : "<p>Nenhum negociador vinculado.</p>"}
        </div>
      </section>
    </div>`;
  target.querySelectorAll("[data-carteira-open-tab]").forEach((button) => {
    button.onclick = () => callbacks.onTabChange(button.dataset.carteiraOpenTab);
  });
  target.querySelector("[data-refresh-carteira-workspace]")?.addEventListener("click", callbacks.onRefresh);
}

function readonlyColumns(rows, preferred = []) {
  const headers = preferred.length ? preferred : headersFromRows(rows);
  return headers.filter((header) => header && !String(header).startsWith("_")).map((header) => ({
    id: header,
    title: header,
    width: operationalColumnWidth(header),
    type: isGridDateHeader(header) ? "date" : undefined,
    value: (row) => row[header] ?? "",
    display: (row) => row[header] ?? "",
    cellClass: isGridMoneyHeader(header) ? "excel-cell-money" : "",
  }));
}

function productionColumns(rows, preferred = []) {
  return readonlyColumns(rows, preferred).map((column) => ({
    ...column,
    save: NON_EDITABLE_HEADERS.has(column.id)
      ? undefined
      : async (row, value) => {
        const result = await saveMonitorPlanilhaCell({
          header: column.id,
          rowKey: row?._row_id || row?.id || row?.__row_number,
          value,
        });
        row[column.id] = result?.value ?? value;
        return row;
      },
  }));
}

function dynamicColumns(tool, fields, rows) {
  const used = new Set();
  const columns = [];
  fields.forEach((field) => {
    const key = field.chave || field.nome;
    const normalized = normalize(key);
    if (!key || used.has(normalized)) return;
    used.add(normalized);
    const editable = field.somente_leitura !== true;
    columns.push({
      id: key,
      title: field.nome || key,
      width: operationalColumnWidth(field.nome || key),
      type: field.tipo === "data" ? "date" : undefined,
      value: (row) => row[key] ?? "",
      display: (row) => row[key] ?? "",
      cellClass: field.tipo === "moeda" ? "excel-cell-money" : "",
      save: editable
        ? async (row, value) => {
          const recordId = Number(row?._record_id || 0);
          if (!recordId) throw new Error("Registro nao identificado.");
          const result = await api(`/api/config/ferramentas-negociais/${tool.id}/registros/${recordId}/campos`, {
            method: "POST",
            body: JSON.stringify({ campo: key, valor: value }),
          });
          const item = result?.item || {};
          Object.assign(row, item.payload || {});
          row.ATUALIZACAO = item.updated_at || row.ATUALIZACAO;
          return row;
        }
        : undefined,
    });
  });
  ["STATUS", "NEGOCIADOR", "ATUALIZACAO"].forEach((header) => {
    if (used.has(normalize(header))) return;
    columns.push(readonlyColumns(rows, [header])[0]);
  });
  return columns;
}

function renderSheetShell(target, title, meta, actions = "") {
  target.innerHTML = `
    <div class="carteira-sheet-head">
      <div><span>Carteira</span><h3>${escapeHtml(title)}</h3><small>${escapeHtml(meta)}</small></div>
      <div class="carteira-sheet-actions">${actions}</div>
    </div>
    <div class="carteira-workspace-grid"></div>`;
  return target.querySelector(".carteira-workspace-grid");
}

function renderProduction(target, group, data) {
  const key = normalize(group.carteira);
  const period = productionPeriods.get(key) || currentPeriod();
  productionPeriods.set(key, period);
  const rows = productionRows(data);
  const headers = data.production?.headers || [];
  const gridTarget = renderSheetShell(
    target,
    "Producao diaria",
    `${rows.length.toLocaleString("pt-BR")} registros no periodo`,
    `<select data-production-month aria-label="Mes">${monthOptions(period.month)}</select>
     <select data-production-year aria-label="Ano">${yearOptions(period.year)}</select>
     <a class="secondary-btn ds-button compact" href="/api/monitoramento/planilha/relatorio.xlsx?carteira=${encodeURIComponent(group.carteira)}&mes=${period.month}&ano=${period.year}">Gerar relatorio</a>
     ${focusButton()}`,
  );
  grids.get("production")?.destroy?.();
  grids.set("production", mountOperationalExcelGrid(gridTarget, {
    id: `carteira-production-${normalize(group.carteira)}`,
    persistKey: `carteira-production-${normalize(group.carteira)}`,
    rows,
    columns: productionColumns(rows, headers),
  }));
  const reloadPeriod = async () => {
    const month = Number(target.querySelector("[data-production-month]")?.value || period.month);
    const year = Number(target.querySelector("[data-production-year]")?.value || period.year);
    productionPeriods.set(key, { month, year });
    gridTarget.innerHTML = `<div class="carteira-workspace-loading"><span></span><strong>Carregando producao...</strong></div>`;
    try {
      data.production = await api(`/api/monitoramento/planilha?carteira=${encodeURIComponent(group.carteira)}&mes=${month}&ano=${year}`);
      renderProduction(target, group, data);
    } catch (error) {
      gridTarget.innerHTML = `<div class="empty-overview">${escapeHtml(error.message || "Nao foi possivel carregar o periodo.")}</div>`;
    }
  };
  target.querySelector("[data-production-month]")?.addEventListener("change", reloadPeriod);
  target.querySelector("[data-production-year]")?.addEventListener("change", reloadPeriod);
  bindFocus(target, "production");
}

function renderPareceres(target, group, data) {
  const rows = data.pareceres;
  const gridTarget = renderSheetShell(
    target,
    "Pareceres",
    `${rows.length.toLocaleString("pt-BR")} registros vinculados`,
    `<a class="secondary-btn ds-button compact" href="/api/pareceres/relatorio.csv?carteira=${encodeURIComponent(group.carteira)}">Gerar relatorio</a>
     ${focusButton()}`,
  );
  grids.get("pareceres")?.destroy?.();
  grids.set("pareceres", mountOperationalExcelGrid(gridTarget, {
    id: `carteira-pareceres-${normalize(group.carteira)}`,
    persistKey: `carteira-pareceres-${normalize(group.carteira)}`,
    rows,
    columns: readonlyColumns(rows),
  }));
  bindFocus(target, "pareceres");
}

async function renderDynamic(target, group, data, toolId, callbacks, options = {}) {
  const tool = data.tools.find((item) => Number(item.id) === Number(toolId));
  if (!tool) {
    target.innerHTML = `<div class="empty-overview">Ferramenta nao disponivel para esta carteira.</div>`;
    return;
  }
  renderLoading(target, tool.nome);
  try {
    const walletQuery = options.consolidated ? "" : `carteira=${encodeURIComponent(group.carteira)}&`;
    const payload = await api(`/api/config/ferramentas-negociais/${tool.id}/registros?${walletQuery}limit=10000`);
    const definition = payload.definition || tool;
    const fields = (definition.campos || []).filter((field) => field.visivel_gerencial !== false);
    const mapRows = (items) => (items || []).map((item) => ({
      ...item.payload,
      STATUS: item.status || "",
      NEGOCIADOR: item.negociador || "",
      CARTEIRA: item.carteira || "",
      ATUALIZACAO: item.updated_at || "",
      _record_id: item.id,
    }));
    let rows = mapRows(payload.items);
    const configured = Array.isArray(definition.configuracao?.telas)
      ? definition.configuracao.telas.filter((screen) => screen.visivel_gerencial !== false)
      : [];
    const screens = configured.length ? configured : [{ id: "planilha", nome: "Planilha", icone: "P", tipo: "planilha", componentes: ["busca", "filtros", "planilha", "relatorio"], status_codes: [], historico_status_codes: [], campos: [] }];
    const stateKey = `${tool.id}:${options.consolidated ? "CONSOLIDADO" : normalize(group.carteira)}`;
    const currentState = dynamicScreenState.get(stateKey) || {
      screenId: screens[0].id,
      history: false,
      search: "",
      status: "",
      operator: "",
      sort: "newest",
      deadline: "",
      date: "",
      dateFrom: "",
      dateTo: "",
      wallet: "",
      fieldFilters: {},
    };
    if (!screens.some((screen) => screen.id === currentState.screenId)) currentState.screenId = screens[0].id;
    dynamicScreenState.set(stateKey, currentState);

    let searchTimer = null;
    const renderScreen = () => {
      const screen = screens.find((item) => item.id === currentState.screenId) || screens[0];
      const statusCodes = screen.tipo === "aprovacao" && currentState.history
        ? (screen.historico_status_codes || [])
        : (screen.status_codes || []);
      const screenRows = statusCodes.length ? rows.filter((row) => statusCodes.includes(row.STATUS)) : rows;
      const selectedKeys = screen.campos || [];
      const screenFields = selectedKeys.length ? fields.filter((field) => selectedKeys.includes(field.chave)) : fields;
      const components = new Set(screen.componentes || []);
      const filterConfig = dynamicFilterConfig(screen.filtros || {});
      const groupingConfig = dynamicGroupingConfig(screen, filterConfig);
      const cardActions = dynamicCardActions(screen);
      const layoutConfig = screen.layout || {};
      const fieldLayout = screen.campo_layout || {};
      const dateKey = filterConfig.campo_data || "ATUALIZACAO";
      const isSheet = screen.tipo === "planilha" || components.has("planilha");
      const isDashboard = screen.tipo === "dashboard";
      const search = normalize(currentState.search);
      const visibleRows = screenRows
        .filter((row) => !filterConfig.mostrar_status || !currentState.status || row.STATUS === currentState.status)
        .filter((row) => !filterConfig.mostrar_negociador || !currentState.operator || normalize(row.NEGOCIADOR) === normalize(currentState.operator))
        .filter((row) => !filterConfig.mostrar_carteira || !currentState.wallet || normalize(row.CARTEIRA) === normalize(currentState.wallet))
        .filter((row) => (filterConfig.campos || []).every((key) => {
          const expected = currentState.fieldFilters?.[key];
          return !expected || normalize(dynamicFilterText(row[key])) === normalize(expected);
        }))
        .filter((row) => !search || normalize(Object.values(row).join(" ")).includes(search))
        .filter((row) => {
          if (filterConfig.modo_data === "deadline" && currentState.deadline) return deadlineBucket(row[dateKey], row.STATUS, definition.statuses || []) === currentState.deadline;
          const date = dynamicDateValue(row[dateKey]);
          if (filterConfig.modo_data === "date" && currentState.date) return date?.toISOString().slice(0, 10) === currentState.date;
          if (filterConfig.modo_data === "period") {
            if (currentState.dateFrom && (!date || date < dynamicDateValue(currentState.dateFrom))) return false;
            if (currentState.dateTo && (!date || date > dynamicDateValue(currentState.dateTo))) return false;
          }
          return true;
        })
        .slice()
        .sort((left, right) => {
          if (!filterConfig.mostrar_ordenacao) return 0;
          const delta = dynamicRecordTimestamp(right.ATUALIZACAO) - dynamicRecordTimestamp(left.ATUALIZACAO);
          return currentState.sort === "oldest" ? -delta : delta;
        });
      const screenCount = (item) => {
        const codes = item.status_codes || [];
        return codes.length ? rows.filter((row) => codes.includes(row.STATUS)).length : rows.length;
      };
      const availableStatuses = (definition.statuses || []).filter((status) => screenRows.some((row) => row.STATUS === status.codigo));
      const operators = [...new Set(screenRows.map((row) => row.NEGOCIADOR).filter(Boolean))]
        .sort((left, right) => String(left).localeCompare(String(right), "pt-BR"));
      const rowWallets = [...new Set(screenRows.map((row) => row.CARTEIRA).filter(Boolean))]
        .sort((left, right) => String(left).localeCompare(String(right), "pt-BR"));
      const customFilterFields = (filterConfig.campos || [])
        .map((key) => fields.find((field) => field.chave === key))
        .filter(Boolean);
      const customFilterOptions = (field) => [...new Set(screenRows.map((row) => dynamicFilterText(row[field.chave])).filter(Boolean))]
        .sort((left, right) => left.localeCompare(right, "pt-BR", { numeric: true }));
      const reportQuery = options.consolidated ? "" : `?carteira=${encodeURIComponent(group.carteira)}`;
      const actions = `
        <button class="secondary-btn ds-button compact" type="button" data-dynamic-refresh title="Atualizar registros">&#8635; Atualizar</button>
        ${components.has("relatorio") ? `<a class="secondary-btn ds-button compact" href="/api/config/ferramentas-negociais/${tool.id}/relatorio.xlsx${reportQuery}">Gerar relatorio</a>` : ""}
        ${isSheet ? focusButton() : ""}`;
      const screenTabs = screens.map((item) => {
        const count = screenCount(item);
        if (item.id === screen.id && item.tipo === "aprovacao") {
          const historyCount = (item.historico_status_codes || []).length
            ? rows.filter((row) => item.historico_status_codes.includes(row.STATUS)).length
            : 0;
          return `
            <button type="button" class="${!currentState.history ? "active" : ""}" data-dynamic-mode="pending"><b>${escapeHtml(item.icone || item.nome.slice(0, 1))}</b><span>${escapeHtml(item.nome)}</span><em>${count}</em></button>
            <button type="button" class="${currentState.history ? "active" : ""}" data-dynamic-mode="history"><b>H</b><span>Historico</span><em>${historyCount}</em></button>`;
        }
        return `<button type="button" class="${item.id === screen.id ? "active" : ""}" data-dynamic-screen="${escapeAttr(item.id)}"><b>${escapeHtml(item.icone || item.nome.slice(0, 1))}</b><span>${escapeHtml(item.nome)}</span><em>${count}</em></button>`;
      }).join("");
      target.innerHTML = `
        <div class="carteira-sheet-head carteira-dynamic-head"><div><span>${options.consolidated ? "Central operacional" : "Ferramenta da carteira"}</span><h3>${escapeHtml(tool.nome)}</h3><small>${visibleRows.length.toLocaleString("pt-BR")} registro(s) nesta tela</small></div><div class="carteira-sheet-actions">${actions}</div></div>
        <nav class="carteira-dynamic-screen-tabs">${screenTabs}</nav>
        ${components.has("busca") || components.has("filtros") ? `<div class="carteira-dynamic-toolbar">
          ${components.has("busca") ? `<label><span>Buscar</span><input type="search" data-dynamic-search value="${escapeAttr(currentState.search)}" placeholder="Cliente, contrato ou negociador"></label>` : ""}
          ${components.has("filtros") && filterConfig.mostrar_status && availableStatuses.length ? `<label><span>Status</span><select data-dynamic-status><option value="">Todos da etapa</option>${availableStatuses.map((status) => `<option value="${escapeAttr(status.codigo)}" ${currentState.status === status.codigo ? "selected" : ""}>${escapeHtml(status.nome)}</option>`).join("")}</select></label>` : ""}
          ${components.has("filtros") && filterConfig.mostrar_negociador ? `<label><span>Negociador</span><select data-dynamic-operator><option value="">Todos</option>${operators.map((operator) => `<option value="${escapeAttr(operator)}" ${currentState.operator === operator ? "selected" : ""}>${escapeHtml(operator)}</option>`).join("")}</select></label>` : ""}
          ${components.has("filtros") && filterConfig.mostrar_carteira ? `<label><span>Carteira</span><select data-dynamic-wallet><option value="">Todas</option>${rowWallets.map((wallet) => `<option value="${escapeAttr(wallet)}" ${currentState.wallet === wallet ? "selected" : ""}>${escapeHtml(wallet)}</option>`).join("")}</select></label>` : ""}
          ${components.has("filtros") ? customFilterFields.map((field) => `<label><span>${escapeHtml(field.nome)}</span><select data-dynamic-field-filter="${escapeAttr(field.chave)}"><option value="">Todos</option>${customFilterOptions(field).map((value) => `<option value="${escapeAttr(value)}" ${currentState.fieldFilters?.[field.chave] === value ? "selected" : ""}>${escapeHtml(value)}</option>`).join("")}</select></label>`).join("") : ""}
          ${filterConfig.modo_data === "date" ? `<label><span>Data</span><input type="date" data-dynamic-date value="${escapeAttr(currentState.date)}"></label>` : ""}
          ${filterConfig.modo_data === "period" ? `<label><span>De</span><input type="date" data-dynamic-date-from value="${escapeAttr(currentState.dateFrom)}"></label><label><span>Ate</span><input type="date" data-dynamic-date-to value="${escapeAttr(currentState.dateTo)}"></label>` : ""}
          ${filterConfig.modo_data === "deadline" ? `<label><span>Prazo</span><select data-dynamic-deadline>${visibleDeadlineEntries(filterConfig).map(([value, label]) => { const filterValue = value === "all" ? "" : value; return `<option value="${filterValue}" ${currentState.deadline === filterValue ? "selected" : ""}>${label}</option>`; }).join("")}</select></label>` : ""}
          ${components.has("filtros") && filterConfig.mostrar_ordenacao ? `<label><span>Ordenar</span><select data-dynamic-sort><option value="newest" ${currentState.sort === "newest" ? "selected" : ""}>Mais recentes</option><option value="oldest" ${currentState.sort === "oldest" ? "selected" : ""}>Mais antigos</option></select></label>` : ""}
        </div>` : ""}
        <div class="carteira-dynamic-screen-content"></div>`;
      const content = target.querySelector(".carteira-dynamic-screen-content");
      if (isDashboard) {
        content.innerHTML = renderDynamicDashboard(visibleRows, definition, screen);
      } else if (isSheet) {
        content.className = "carteira-dynamic-screen-content carteira-workspace-grid";
        grids.get(`tool:${tool.id}`)?.destroy?.();
        grids.set(`tool:${tool.id}`, mountOperationalExcelGrid(content, {
          id: `carteira-tool-${tool.id}-${options.consolidated ? "consolidado" : normalize(group.carteira)}`,
          persistKey: `carteira-tool-${tool.id}-${options.consolidated ? "consolidado" : normalize(group.carteira)}`,
          rows: visibleRows,
          columns: dynamicColumns(definition, screenFields, visibleRows),
        }));
        bindFocus(target, `tool:${tool.id}`);
      } else {
        const visibleCardFields = screenFields.filter((field) => fieldLayout[field.chave]?.papel !== "oculto");
        const titleKey = visibleCardFields.find((field) => fieldLayout[field.chave]?.papel === "titulo")?.chave || definition.configuracao?.campo_titulo;
        const subtitleKey = visibleCardFields.find((field) => fieldLayout[field.chave]?.papel === "subtitulo")?.chave;
        const cardFields = visibleCardFields.filter((field) => ![titleKey, subtitleKey, "STATUS", "NEGOCIADOR", "OPERADOR", "CARTEIRA"].includes(field.chave)).slice(0, 8);
        const selectedMetadataKeys = new Set(selectedKeys.map((key) => String(key || "").toUpperCase()));
        const showNegotiatorMeta = !selectedKeys.length || visibleCardFields.some((field) => {
          const key = String(field.chave || "").toUpperCase();
          return String(field.tipo || "").toLowerCase() === "usuario" || ["NEGOCIADOR", "OPERADOR", "USUARIO"].includes(key);
        }) || ["NEGOCIADOR", "OPERADOR", "USUARIO"].some((key) => selectedMetadataKeys.has(key));
        const showWalletMeta = !selectedKeys.length || visibleCardFields.some((field) => {
          const key = String(field.chave || "").toUpperCase();
          return String(field.tipo || "").toLowerCase() === "carteira" || key === "CARTEIRA";
        }) || selectedMetadataKeys.has("CARTEIRA");
        const actionField = (definition.campos || []).find((field) => field.chave === cardActions.status_campo);
        const actionOptions = cardActions.status_origem === "field"
          ? (actionField?.opcoes || []).map((value) => ({ codigo: value, nome: value, cor: tool.cor || "#2563eb" }))
          : (definition.statuses || []);
        const renderCardActions = (row, statusLabel) => {
          const currentActionValue = cardActions.status_origem === "field" ? row[cardActions.status_campo] : row.STATUS;
          const copyButton = cardActions.copiar ? `<button type="button" class="icon-btn" data-card-copy="${row._record_id}" title="Copiar dados" aria-label="Copiar dados">&#10697;</button>` : "";
          const notesButton = cardActions.observacoes ? `<button type="button" class="secondary-btn compact" data-card-notes="${row._record_id}">Obs.</button>` : "";
          let primary = "";
          if (cardActions.status_modo === "open") primary = `<button type="button" data-card-open="${row._record_id}">${escapeHtml(cardActions.botao_rotulo || "Abrir")} <b aria-hidden="true">&rsaquo;</b></button>`;
          if (cardActions.status_modo === "select") primary = `<select data-card-status="${row._record_id}" aria-label="Alterar status ou opcao">${actionOptions.map((option) => `<option value="${escapeAttr(option.codigo)}" ${String(currentActionValue || "") === String(option.codigo) ? "selected" : ""}>${escapeHtml(option.nome)}</option>`).join("")}</select>`;
          if (cardActions.status_modo === "button") primary = `<button type="button" class="secondary-btn compact" data-card-action="${row._record_id}">${escapeHtml(cardActions.botao_rotulo || statusLabel || "Executar")}</button>`;
          return `<div class="carteira-dynamic-card-action"><span>${escapeHtml(statusLabel)}</span><div class="carteira-dynamic-card-buttons">${copyButton}${notesButton}${primary}</div></div>`;
        };
        const renderCards = (items) => `<div class="carteira-dynamic-list density-${escapeAttr(layoutConfig.densidade || "compacta")} ${layoutConfig.altura_uniforme ? "uniform" : ""}" style="--card-cols-desktop:${Number(layoutConfig.colunas_desktop || 1)};--card-cols-tablet:${Number(layoutConfig.colunas_tablet || 1)};--card-cols-mobile:${Number(layoutConfig.colunas_mobile || 1)}">${items.map((row) => {
          const status = (definition.statuses || []).find((item) => item.codigo === row.STATUS);
          const statusColor = status?.cor || tool.cor || "#2563eb";
          const statusLabel = status?.nome || row.STATUS || "Sem status";
          return `<article class="carteira-dynamic-event-card" data-open-tool-record="${row._record_id}" tabindex="0" style="--status-color:${escapeAttr(statusColor)}">
            <span class="carteira-dynamic-card-marker" aria-hidden="true"></span>
            <div class="carteira-dynamic-card-main">
              <div class="carteira-dynamic-card-topline"><strong class="carteira-dynamic-card-title">${escapeHtml(row[titleKey] || row.CLIENTE || row.NOME || `Registro ${row._record_id}`)}</strong>${cardActions.mostrar_atualizacao ? `<time>${escapeHtml(dynamicRecordUpdatedLabel(row.ATUALIZACAO))}</time>` : ""}</div>
              ${subtitleKey ? `<p class="carteira-dynamic-card-subtitle">${escapeHtml(row[subtitleKey] ?? "")}</p>` : ""}
              <div class="carteira-dynamic-card-meta">${cardFields.map((field) => `<span class="role-${escapeAttr(fieldLayout[field.chave]?.papel || "info")} width-${escapeAttr(fieldLayout[field.chave]?.largura || "auto")} ${fieldLayout[field.chave]?.copiavel ? "copyable" : ""}" ${fieldLayout[field.chave]?.copiavel ? `title="Selecione para copiar"` : ""}><small>${escapeHtml(field.nome)}</small><b>${escapeHtml(row[field.chave] ?? "Vazio")}</b></span>`).join("")}${showNegotiatorMeta ? `<span><small>Negociador</small><b>${escapeHtml(row.NEGOCIADOR || "Nao informado")}</b></span>` : ""}${showWalletMeta ? `<span><small>Carteira</small><b>${escapeHtml(row.CARTEIRA || group.carteira || "Nao informada")}</b></span>` : ""}</div>
            </div>
            ${renderCardActions(row, statusLabel)}
          </article>`;
        }).join("")}</div>`;
        if (!visibleRows.length) content.innerHTML = '<div class="empty-overview">Nenhum registro encontrado para os filtros desta etapa.</div>';
        else if (groupingConfig.modo !== "none") {
          let grouped = [];
          if (groupingConfig.modo === "deadline") grouped = visibleDeadlineEntries(filterConfig).filter(([key]) => key !== "all").map(([key, label]) => [key, label, visibleRows.filter((row) => deadlineBucket(row[dateKey], row.STATUS, definition.statuses || []) === key)]);
          if (groupingConfig.modo === "status") grouped = (definition.statuses || []).map((status) => [status.codigo, status.nome, visibleRows.filter((row) => row.STATUS === status.codigo)]);
          if (groupingConfig.modo === "field") grouped = [...new Set(visibleRows.map((row) => dynamicFilterText(row[groupingConfig.campo]) || "Nao informado"))].sort((a, b) => a.localeCompare(b, "pt-BR", { numeric: true })).map((value) => [value, value, visibleRows.filter((row) => (dynamicFilterText(row[groupingConfig.campo]) || "Nao informado") === value)]);
          grouped = grouped.filter(([, , items]) => items.length);
          content.innerHTML = `<div class="carteira-dynamic-groups">${grouped.map(([key, label, items]) => `<details class="group-${escapeAttr(normalize(key).toLowerCase())}" ${groupingConfig.iniciar_recolhido ? "" : "open"}><summary><span>${escapeHtml(label)}</span><b>${items.length}</b></summary>${renderCards(items)}</details>`).join("")}</div>`;
        } else content.innerHTML = renderCards(visibleRows);
      }
      target.querySelectorAll("[data-open-tool-record]").forEach((card) => {
        const open = () => {
          const recordId = Number(card.dataset.openToolRecord);
          if (recordId) callbacks.onOpenToolRecord?.(tool.id, recordId);
        };
        card.addEventListener("click", (event) => {
          if (event.target.closest("button,select,input,a")) return;
          open();
        });
        card.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            open();
          }
        });
      });
      const refreshAfterCardAction = async () => {
        const refreshed = await api(`/api/config/ferramentas-negociais/${tool.id}/registros?${walletQuery}limit=10000&_=${Date.now()}`);
        rows = mapRows(refreshed.items);
        renderScreen();
      };
      target.querySelectorAll("[data-card-open],[data-card-notes]").forEach((button) => button.addEventListener("click", (event) => {
        event.stopPropagation();
        const recordId = Number(button.dataset.cardOpen || button.dataset.cardNotes);
        if (recordId) callbacks.onOpenToolRecord?.(tool.id, recordId, { focusComments: Boolean(button.dataset.cardNotes) });
      }));
      target.querySelectorAll("[data-card-copy]").forEach((button) => button.addEventListener("click", async (event) => {
        event.stopPropagation();
        const row = rows.find((item) => Number(item._record_id) === Number(button.dataset.cardCopy));
        if (!row) return;
        const keys = cardActions.copiar_campos.length ? cardActions.copiar_campos : [definition.configuracao?.campo_titulo].filter(Boolean);
        const text = keys.map((key) => dynamicFilterText(row[key])).filter(Boolean).join("\t");
        if (text) await navigator.clipboard.writeText(text);
        button.title = text ? "Copiado" : "Nenhum dado configurado para copiar";
      }));
      const applyCardValue = async (recordId, value) => {
        const row = rows.find((item) => Number(item._record_id) === Number(recordId));
        if (!row || !value) return;
        if (cardActions.status_origem === "field") {
          await api(`/api/config/ferramentas-negociais/${tool.id}/registros/${recordId}/campos`, { method: "POST", body: JSON.stringify({ campo: cardActions.status_campo, valor: value }) });
        } else {
          const transition = (definition.transicoes || []).find((item) => item.origem_codigo === row.STATUS && item.destino_codigo === value && item.permite_gerencial !== false);
          const reason = transition?.exige_justificativa ? window.prompt("Informe a justificativa:") : "";
          if (transition?.exige_justificativa && !reason?.trim()) return;
          await api(`/api/config/ferramentas-negociais/${tool.id}/registros/${recordId}/transicao`, { method: "POST", body: JSON.stringify({ status: value, justificativa: reason || "" }) });
        }
        await refreshAfterCardAction();
      };
      target.querySelectorAll("[data-card-status]").forEach((select) => select.addEventListener("change", async (event) => {
        event.stopPropagation();
        select.disabled = true;
        try { await applyCardValue(select.dataset.cardStatus, select.value); }
        catch (error) { select.disabled = false; select.title = error.message || "Nao foi possivel atualizar."; }
      }));
      target.querySelectorAll("[data-card-action]").forEach((button) => button.addEventListener("click", async (event) => {
        event.stopPropagation();
        const recordId = button.dataset.cardAction;
        if (!cardActions.botao_status) return callbacks.onOpenToolRecord?.(tool.id, Number(recordId));
        button.disabled = true;
        try { await applyCardValue(recordId, cardActions.botao_status); }
        catch (error) { button.disabled = false; button.title = error.message || "Nao foi possivel executar."; }
      }));
      target.querySelector("[data-dynamic-refresh]")?.addEventListener("click", async (event) => {
        const button = event.currentTarget;
        const originalLabel = button.innerHTML;
        button.disabled = true;
        button.innerHTML = "Atualizando...";
        try {
          const refreshed = await api(`/api/config/ferramentas-negociais/${tool.id}/registros?${walletQuery}limit=10000&_=${Date.now()}`);
          rows = mapRows(refreshed.items);
          renderScreen();
        } catch (error) {
          button.disabled = false;
          button.innerHTML = originalLabel;
          button.title = error.message || "Nao foi possivel atualizar os registros.";
        }
      });
      target.querySelector("[data-dynamic-search]")?.addEventListener("input", (event) => {
        currentState.search = event.currentTarget.value;
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(() => {
          renderScreen();
          const input = target.querySelector("[data-dynamic-search]");
          input?.focus();
          input?.setSelectionRange(input.value.length, input.value.length);
        }, 180);
      });
      target.querySelector("[data-dynamic-status]")?.addEventListener("change", (event) => {
        currentState.status = event.currentTarget.value;
        renderScreen();
      });
      target.querySelector("[data-dynamic-operator]")?.addEventListener("change", (event) => {
        currentState.operator = event.currentTarget.value;
        renderScreen();
      });
      target.querySelector("[data-dynamic-wallet]")?.addEventListener("change", (event) => {
        currentState.wallet = event.currentTarget.value;
        renderScreen();
      });
      target.querySelectorAll("[data-dynamic-field-filter]").forEach((select) => select.addEventListener("change", (event) => {
        currentState.fieldFilters = { ...(currentState.fieldFilters || {}), [event.currentTarget.dataset.dynamicFieldFilter]: event.currentTarget.value };
        renderScreen();
      }));
      target.querySelector("[data-dynamic-sort]")?.addEventListener("change", (event) => {
        currentState.sort = event.currentTarget.value;
        renderScreen();
      });
      [["[data-dynamic-date]", "date"], ["[data-dynamic-date-from]", "dateFrom"], ["[data-dynamic-date-to]", "dateTo"], ["[data-dynamic-deadline]", "deadline"]].forEach(([selector, key]) => {
        target.querySelector(selector)?.addEventListener("change", (event) => {
          currentState[key] = event.currentTarget.value;
          renderScreen();
        });
      });
      target.querySelectorAll("[data-dynamic-screen]").forEach((button) => button.addEventListener("click", () => {
        currentState.screenId = button.dataset.dynamicScreen;
        currentState.history = false;
        currentState.search = "";
        currentState.status = "";
        currentState.operator = "";
        currentState.wallet = "";
        currentState.fieldFilters = {};
        currentState.deadline = "";
        currentState.date = "";
        currentState.dateFrom = "";
        currentState.dateTo = "";
        renderScreen();
      }));
      target.querySelectorAll("[data-dynamic-mode]").forEach((button) => button.addEventListener("click", () => {
        currentState.history = button.dataset.dynamicMode === "history";
        currentState.status = "";
        renderScreen();
      }));
    };
    renderScreen();
  } catch (error) {
    target.innerHTML = `<div class="empty-overview">${escapeHtml(error.message || "Nao foi possivel carregar a ferramenta.")}</div>`;
  }
}

export async function renderConsolidatedDynamicTool(target, tool, callbacks = {}) {
  if (!target || !tool) return;
  return renderDynamic(
    target,
    { carteira: "" },
    { tools: [tool] },
    tool.id,
    callbacks,
    { consolidated: true },
  );
}

function renderSettings(target, group, data, callbacks) {
  const columns = group.negocial?.colunas || [];
  target.innerHTML = `
    <div class="carteira-settings-grid">
      <section class="carteira-workspace-card">
        <header><div><span>Estrutura</span><h3>Schema negocial</h3></div><strong>v${Number(group.negocial?.schema_version || 0) || "-"}</strong></header>
        <dl>
          <div><dt>Colunas</dt><dd>${columns.length}</dd></div>
          <div><dt>Chave</dt><dd>${escapeHtml(columns.find((column) => column.identificador)?.nome || "Nao definida")}</dd></div>
          <div><dt>Regra de H.O</dt><dd>${group.negocial?.regras_ho?.usa_percentual_ho ? "Ativa" : "Manual"}</dd></div>
        </dl>
        <div class="carteira-schema-tags">${columns.map((column) => `<span>${escapeHtml(column.nome)}</span>`).join("")}</div>
        <button class="primary-btn ds-button compact" type="button" data-edit-workspace-schema>Editar schema</button>
      </section>
      <section class="carteira-workspace-card">
        <header><div><span>Ferramentas</span><h3>Acessos da carteira</h3></div><strong>${data.toolSettings.filter((item) => item.enabled).length}</strong></header>
        <div class="carteira-settings-tools">
          ${data.toolSettings.map((item) => `
            <div class="carteira-tool-setting-row"><label class="carteira-tool-toggle ${item.locked ? "is-locked" : ""}">
              <span>
                <strong>${escapeHtml(item.nome)}</strong>
                <small>${item.locked ? "Ferramenta essencial" : item.enabled ? "Disponivel no gerencial e negocial" : "Oculta para esta carteira"}</small>
              </span>
              <input type="checkbox" data-wallet-tool-toggle="${escapeAttr(item.key)}" ${item.enabled ? "checked" : ""} ${item.locked ? "disabled" : ""}>
              <i aria-hidden="true"></i>
            </label>${String(item.key).toLowerCase() === "colchao" && item.enabled ? `<button class="secondary-btn compact" type="button" data-configure-colchao>Configurar campos</button>` : ""}</div>`).join("")}
        </div>
      </section>
    </div>`;
  target.querySelector("[data-edit-workspace-schema]")?.addEventListener("click", callbacks.onEditSchema);
  target.querySelector("[data-configure-colchao]")?.addEventListener("click", () => openColchaoSettingsDialog(group, callbacks));
  target.querySelectorAll("[data-wallet-tool-toggle]").forEach((input) => {
    input.addEventListener("change", async () => {
      input.disabled = true;
      try {
        await api(`/api/config/carteiras/${encodeURIComponent(group.carteira)}/ferramentas`, {
          method: "POST",
          body: JSON.stringify({ tool_key: input.dataset.walletToolToggle, enabled: input.checked }),
        });
        clearCarteiraWorkspaceCache(group.carteira);
        await callbacks.onRefresh?.();
      } catch (error) {
        input.checked = !input.checked;
        input.disabled = false;
        callbacks.onError?.(error);
      }
    });
  });
}

export async function renderCarteiraWorkspace(group, options = {}) {
  const active = options.active || "overview";
  const tabs = document.querySelector("#carteiraWorkspaceTabs");
  if (!tabs) return;
  setPanelVisibility(active);
  const initialTarget = active === "overview"
    ? document.querySelector("#carteiraWorkspaceOverview")
    : active === "production"
      ? document.querySelector("#carteiraWorkspaceProduction")
      : active === "pareceres"
        ? document.querySelector("#carteiraWorkspacePareceres")
        : active === "colchao"
          ? document.querySelector("#carteiraWorkspaceColchao")
        : active === "honorarios"
          ? document.querySelector("#carteiraWorkspaceHonorarios")
        : active === "settings"
          ? document.querySelector("#carteiraWorkspaceSettings")
          : document.querySelector("#carteiraWorkspaceDynamic");
  if (active !== "monitor" && initialTarget) renderLoading(initialTarget, "a carteira");
  const data = await loadWorkspace(group);
  if (!data) return;
  const allowedTabs = new Set([
    "overview",
    "monitor",
    "production",
    "settings",
    ...(normalize(group.carteira) === "ALPHA" ? ["honorarios"] : []),
    ...(data.pareceresEnabled ? ["pareceres"] : []),
    ...(data.colchaoEnabled ? ["colchao"] : []),
    ...data.tools.map((tool) => `tool:${tool.id}`),
  ]);
  if (!allowedTabs.has(active)) {
    options.onTabChange?.("overview");
    return;
  }
  tabs.innerHTML = [
    ...FIXED_TABS
      .filter(([key]) => (key !== "pareceres" || data.pareceresEnabled) && (key !== "colchao" || data.colchaoEnabled))
      .map(([key, label, iconName]) => tabButton(key, label, iconName, active)),
    ...data.tools.map((tool) => tabButton(`tool:${tool.id}`, tool.nome, "file", active, tool)),
    ...(normalize(group.carteira) === "ALPHA" ? [tabButton("honorarios", "Metas e H.O.", "percent", active)] : []),
    tabButton("settings", "Configuracoes", "settings", active),
  ].join("");
  tabs.querySelectorAll("[data-carteira-workspace-tab]").forEach((button) => {
    button.onclick = () => options.onTabChange?.(button.dataset.carteiraWorkspaceTab);
  });
  const callbacks = { ...options, onTabChange: options.onTabChange };
  if (active === "overview") renderOverview(document.querySelector("#carteiraWorkspaceOverview"), group, data, active, callbacks);
  if (active === "production") renderProduction(document.querySelector("#carteiraWorkspaceProduction"), group, data);
  if (active === "pareceres") renderPareceres(document.querySelector("#carteiraWorkspacePareceres"), group, data);
  if (active === "colchao") await renderColchaoWorkspace(document.querySelector("#carteiraWorkspaceColchao"), group);
  if (active === "honorarios") await renderAlphaHonorarios(document.querySelector("#carteiraWorkspaceHonorarios"), callbacks);
  if (active.startsWith("tool:")) await renderDynamic(document.querySelector("#carteiraWorkspaceDynamic"), group, data, active.split(":")[1], callbacks);
  if (active === "settings") renderSettings(document.querySelector("#carteiraWorkspaceSettings"), group, data, callbacks);
}

export function clearCarteiraWorkspaceCache(carteira = "") {
  if (carteira) cache.delete(normalize(carteira));
  else cache.clear();
}
