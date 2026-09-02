import { apiGet, apiPost, apiPut } from "./api.js?v=20260714-module-contract-1";
import { createExcelGrid } from "./excelGrid.js?v=20260730-inline-save-1";
import { validateSelectedFiles } from "./fileValidation.js?v=20260811-attachment-preflight-1";

const host = document.querySelector("#dynamicToolPage");
let definitions = [];
let activeDefinition = null;
let records = [];
let activeStatus = "";
let activeScreenId = "";
let screenHistoryMode = false;
let searchTerm = "";
let dateTerm = "";
let dateFromTerm = "";
let dateToTerm = "";
let deadlineTerm = "";
let operatorTerm = "";
let walletTerm = "";
let sortTerm = "newest";
let fieldFilterTerms = {};
let toolGrid = null;
let gridMountSequence = 0;
let lastLoadedAt = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatValue(value, field) {
  if (value === null || value === undefined || value === "") return "Vazio";
  if (field?.tipo === "boolean") return value ? "Sim" : "Nao";
  if (field?.tipo === "multiselect") return Array.isArray(value) ? value.join(", ") : String(value);
  if (field?.tipo === "moeda") {
    const number = Number(String(value).replace(",", "."));
    return Number.isFinite(number)
      ? number.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
      : String(value);
  }
  if (field?.tipo === "data") {
    const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
    return match ? `${match[3]}/${match[2]}/${match[1]}` : String(value);
  }
  return String(value);
}

function visibleFields() {
  return (activeDefinition?.campos || []).filter((field) => field.visivel_negocial);
}

function configuredScreens() {
  const configured = activeDefinition?.configuracao?.telas;
  const screens = Array.isArray(configured)
    ? configured.filter((screen) => screen.visivel_negocial !== false)
    : [];
  if (screens.length) return screens;
  return [{
    id: "registros", nome: activeDefinition?.nome || "Registros", icone: activeDefinition?.icone || "R",
    tipo: "planilha", componentes: ["metricas", "busca", "filtros", "planilha", "acoes"],
    status_codes: [], historico_status_codes: [], campos: [],
  }];
}

function activeScreen() {
  const screens = configuredScreens();
  return screens.find((screen) => screen.id === activeScreenId) || screens[0];
}

function screenHas(component) {
  return (activeScreen()?.componentes || []).includes(component);
}

function configuredFilters() {
  const raw = activeScreen()?.filtros || {};
  const configured = (key, fallback) => (
    Object.prototype.hasOwnProperty.call(raw, key) ? Boolean(raw[key]) : fallback
  );
  return {
    mostrar_status: configured("mostrar_status", true),
    mostrar_negociador: configured("mostrar_negociador", true),
    mostrar_carteira: configured("mostrar_carteira", false),
    mostrar_ordenacao: configured("mostrar_ordenacao", true),
    campos: Array.isArray(raw.campos) ? raw.campos : [],
    ...raw,
  };
}

function configuredGrouping() {
  const screen = activeScreen();
  const raw = screen?.agrupamento || {};
  const allowed = new Set(["none", "deadline", "status", "field"]);
  return {
    modo: allowed.has(raw.modo) ? raw.modo : (screen?.filtros?.agrupar_prazo ? "deadline" : "none"),
    campo: raw.campo || "",
    iniciar_recolhido: Object.prototype.hasOwnProperty.call(raw, "iniciar_recolhido")
      ? Boolean(raw.iniciar_recolhido) : Boolean(screen?.filtros?.iniciar_recolhido),
  };
}

function configuredCardActions() {
  const raw = activeScreen()?.acoes_card || {};
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

function recordFilterValue(item, key) {
  if (key === "STATUS") return item.status;
  if (key === "NEGOCIADOR") return item.negociador;
  if (key === "CARTEIRA") return item.carteira;
  const value = item.payload?.[key];
  if (Array.isArray(value)) return value.join(", ");
  if (value && typeof value === "object") return Object.values(value).join(", ");
  return String(value ?? "").trim();
}

function uniqueFilterValues(key) {
  return [...new Set(records.map((item) => recordFilterValue(item, key)).filter(Boolean))]
    .sort((left, right) => left.localeCompare(right, "pt-BR", { numeric: true }));
}

function screenStatusCodes() {
  const screen = activeScreen();
  if (!screen) return [];
  if (screen.tipo === "aprovacao" && screenHistoryMode) return screen.historico_status_codes || [];
  return screen.status_codes || [];
}

function screenFields() {
  const keys = activeScreen()?.campos || [];
  const fields = visibleFields();
  return keys.length ? fields.filter((field) => keys.includes(field.chave)) : fields;
}

function usesVisibleStatus() {
  if (!activeDefinition) return false;
  return activeDefinition.tipo !== "CADASTRO" || activeDefinition.configuracao?.usar_status !== false;
}

function negotiatorSelectsInitialStatus() {
  return (
    activeDefinition?.tipo === "CADASTRO"
    && usesVisibleStatus()
    && activeDefinition.configuracao?.negociador_define_status === true
  );
}

function negotiatorCanChangeStatus() {
  return (
    usesVisibleStatus()
    && activeDefinition?.configuracao?.negociador_altera_status === true
    && activeDefinition?.permissoes?.editar
    && activeDefinition?.permissoes?.transicionar
  );
}

function statusDefinition(code) {
  return (activeDefinition?.statuses || []).find((item) => item.codigo === code);
}

function isFinalStatus(code) {
  return statusDefinition(code)?.final === true;
}

function renderStatusBadge(code) {
  const status = statusDefinition(code);
  const color = status?.cor || "#2563eb";
  return `<span class="dynamic-status-badge" style="--status-color:${escapeHtml(color)}">${escapeHtml(status?.nome || code)}</span>`;
}

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("pt-BR");
}

function recordDate(item) {
  const key = activeScreen()?.filtros?.campo_data;
  const value = key ? item.payload?.[key] : (item.updated_at || item.created_at);
  if (!value) return null;
  const text = String(value).trim();
  const br = text.match(/^(\d{2})\/(\d{2})\/(\d{4})/);
  const date = br ? new Date(Number(br[3]), Number(br[2]) - 1, Number(br[1])) : new Date(text.length === 10 ? `${text}T12:00:00` : text);
  if (Number.isNaN(date.getTime())) return null;
  date.setHours(0, 0, 0, 0);
  return date;
}

function deadlineBucket(item) {
  if (isFinalStatus(item.status)) return "completed";
  const date = recordDate(item);
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
  overdue: "Vencidos", today: "Vence hoje", next3: "Proximos 3 dias",
  next7: "Proximos 7 dias", next30: "Proximos 30 dias", later: "Posteriores",
  no_date: "Sem data", completed: "Encerrados",
};

function visibleDeadlineEntries() {
  const configured = activeScreen()?.filtros?.prazos_visiveis;
  const allowed = Array.isArray(configured) ? new Set(configured) : null;
  return [["all", "Todos"], ...Object.entries(deadlineLabels)]
    .filter(([value]) => !allowed || allowed.has(value));
}

function hasActiveCommandFilters() {
  return Boolean(
    searchTerm || dateTerm || dateFromTerm || dateToTerm || deadlineTerm
    || operatorTerm || walletTerm || sortTerm !== "newest"
    || Object.values(fieldFilterTerms).some(Boolean)
  );
}

function clearCommandFilters() {
  searchTerm = "";
  dateTerm = "";
  dateFromTerm = "";
  dateToTerm = "";
  deadlineTerm = "";
  operatorTerm = "";
  walletTerm = "";
  sortTerm = "newest";
  fieldFilterTerms = {};
}

function syncClearFiltersButton() {
  const button = host?.querySelector("[data-clear-tool-filters]");
  if (button) button.hidden = !hasActiveCommandFilters();
}

function fieldOptions(field) {
  return (field?.opcoes || []).map((option) => {
    if (option && typeof option === "object") {
      const value = option.value ?? option.codigo ?? option.nome ?? "";
      return { value: String(value), label: String(option.label ?? option.nome ?? value) };
    }
    return { value: String(option), label: String(option) };
  });
}

function fieldWidth(field) {
  if (field.tipo === "texto_longo") return 340;
  if (field.tipo === "moeda") return 150;
  if (field.tipo === "data") return 122;
  if (["select", "multiselect"].includes(field.tipo)) return 180;
  const labelLength = String(field.nome || "").length;
  return Math.min(300, Math.max(130, labelLength * 9 + 42));
}

function filteredRecords() {
  const query = searchTerm.trim().toLowerCase();
  const allowedStatuses = screenStatusCodes();
  const filters = configuredFilters();
  const items = records.filter((item) => {
    if (allowedStatuses.length && !allowedStatuses.includes(item.status)) return false;
    if (filters.mostrar_status && activeStatus && item.status !== activeStatus) return false;
    if (filters.mostrar_negociador && operatorTerm && item.negociador !== operatorTerm) return false;
    if (filters.mostrar_carteira && walletTerm && item.carteira !== walletTerm) return false;
    if (!(filters.campos || []).every((key) => !fieldFilterTerms[key] || recordFilterValue(item, key) === fieldFilterTerms[key])) return false;
    const mode = activeScreen()?.filtros?.modo_data || "none";
    const date = recordDate(item);
    if (mode === "date" && dateTerm && date?.toISOString().slice(0, 10) !== dateTerm) return false;
    if (mode === "period" && dateFromTerm && (!date || date < recordDate({ payload: { [activeScreen()?.filtros?.campo_data]: dateFromTerm }, updated_at: dateFromTerm }))) return false;
    if (mode === "period" && dateToTerm && (!date || date > recordDate({ payload: { [activeScreen()?.filtros?.campo_data]: dateToTerm }, updated_at: dateToTerm }))) return false;
    if (mode === "deadline" && deadlineTerm && deadlineBucket(item) !== deadlineTerm) return false;
    if (!query) return true;
    return [item.titulo, item.negociador, item.status, ...Object.values(item.payload || {})]
      .some((value) => String(value ?? "").toLowerCase().includes(query));
  });
  if (!filters.mostrar_ordenacao) return items;
  return items.sort((left, right) => {
    const delta = new Date(right.updated_at || right.created_at || 0) - new Date(left.updated_at || left.created_at || 0);
    return sortTerm === "oldest" ? -delta : delta;
  });
}

function renderScreenNavigation() {
  const target = host.querySelector("[data-screen-navigation]");
  if (!target) return;
  target.innerHTML = configuredScreens().map((screen) => `
    <button type="button" class="dynamic-tool-screen-tab ${activeScreen()?.id === screen.id ? "active" : ""}" data-screen="${escapeHtml(screen.id)}">
      <b>${escapeHtml(screen.icone || screen.nome?.slice(0, 1) || "T")}</b><span>${escapeHtml(screen.nome)}</span>
    </button>
  `).join("");
  target.querySelectorAll("[data-screen]").forEach((button) => button.addEventListener("click", () => {
    activeScreenId = button.dataset.screen;
    activeStatus = "";
    searchTerm = "";
    dateTerm = "";
    dateFromTerm = "";
    dateToTerm = "";
    deadlineTerm = "";
    operatorTerm = "";
    walletTerm = "";
    sortTerm = "newest";
    fieldFilterTerms = {};
    screenHistoryMode = false;
    renderTool();
  }));
}

function renderScreenRecords() {
  const target = host.querySelector("[data-tool-list]");
  if (!target) return;
  const items = filteredRecords();
  const screen = activeScreen();
  const layout = screen.layout || {};
  const grouping = configuredGrouping();
  const cardActions = configuredCardActions();
  const fieldLayout = screen.campo_layout || {};
  const fields = screenFields().filter((field) => fieldLayout[field.chave]?.papel !== "oculto");
  const titleField = fields.find((field) => fieldLayout[field.chave]?.papel === "titulo");
  const subtitleField = fields.find((field) => fieldLayout[field.chave]?.papel === "subtitulo");
  const details = fields.filter((field) => ![titleField?.chave, subtitleField?.chave].includes(field.chave)).slice(0, 8);
  const actionField = (activeDefinition.campos || []).find((field) => field.chave === cardActions.status_campo);
  const actionOptions = cardActions.status_origem === "field"
    ? (actionField?.opcoes || []).map((value) => ({ codigo: value, nome: value }))
    : (activeDefinition.statuses || []);
  const renderActions = (item) => {
    const currentValue = cardActions.status_origem === "field" ? item.payload?.[cardActions.status_campo] : item.status;
    const copy = cardActions.copiar ? `<button type="button" class="dynamic-card-icon-action" data-record-copy="${item.id}" title="Copiar dados" aria-label="Copiar dados">&#10697;</button>` : "";
    const notes = cardActions.observacoes ? `<button type="button" class="secondary-btn" data-record-notes="${item.id}">Obs.</button>` : "";
    let primary = "";
    if (cardActions.status_modo === "open") primary = `<button type="button" class="secondary-btn" data-record-details="${item.id}">${escapeHtml(cardActions.botao_rotulo || "Abrir")}</button>`;
    if (cardActions.status_modo === "select") primary = `<select data-record-card-status="${item.id}" aria-label="Alterar status ou opcao">${actionOptions.map((option) => `<option value="${escapeHtml(option.codigo)}" ${String(currentValue || "") === String(option.codigo) ? "selected" : ""}>${escapeHtml(option.nome)}</option>`).join("")}</select>`;
    if (cardActions.status_modo === "button") primary = `<button type="button" class="secondary-btn" data-record-card-action="${item.id}">${escapeHtml(cardActions.botao_rotulo || "Executar")}</button>`;
    return `${copy}${notes}${primary}`;
  };
  const renderCards = (cardItems) => `<div class="dynamic-tool-record-grid density-${escapeHtml(layout.densidade || "compacta")} ${layout.altura_uniforme ? "uniform" : ""}" style="--card-cols-desktop:${Number(layout.colunas_desktop || 1)};--card-cols-tablet:${Number(layout.colunas_tablet || 1)};--card-cols-mobile:${Number(layout.colunas_mobile || 1)}">${cardItems.map((item) => `
    <article class="dynamic-tool-record-card ${isFinalStatus(item.status) ? "is-final" : ""}" data-record-card="${item.id}" style="--record-status:${escapeHtml(statusDefinition(item.status)?.cor || activeDefinition.cor || "#2563eb")}">
      <div class="dynamic-tool-record-copy">
        ${usesVisibleStatus() ? `<div class="dynamic-tool-record-status">${renderStatusBadge(item.status)}</div>` : ""}
        <div class="dynamic-tool-record-heading">
          <strong>${escapeHtml(item.payload?.[titleField?.chave] || item.titulo || `Registro ${item.id}`)}</strong>
        </div>
        ${subtitleField ? `<p class="dynamic-tool-record-subtitle">${escapeHtml(formatValue(item.payload?.[subtitleField.chave], subtitleField))}</p>` : ""}
        <div class="dynamic-tool-record-fields">
          ${details.map((field) => `<span class="role-${escapeHtml(fieldLayout[field.chave]?.papel || "info")} width-${escapeHtml(fieldLayout[field.chave]?.largura || "auto")} ${fieldLayout[field.chave]?.copiavel ? "copyable" : ""}"><small>${escapeHtml(field.nome)}</small><b>${escapeHtml(formatValue(item.payload?.[field.chave], field))}</b></span>`).join("")}
        </div>
        ${cardActions.mostrar_atualizacao ? `<small class="dynamic-tool-record-meta">Atualizado ${escapeHtml(formatDateTime(item.updated_at))}</small>` : ""}
      </div>
      <aside class="dynamic-tool-record-actions">
        ${screenHas("acoes") ? renderActions(item) : ""}
      </aside>
    </article>`).join("")}</div>`;
  if (!items.length) target.innerHTML = `<div class="dynamic-tool-empty"><strong>Nenhum registro nesta tela</strong><span>Altere os filtros ou aguarde uma nova movimentacao.</span></div>`;
  else if (grouping.modo !== "none") {
    let groups = [];
    if (grouping.modo === "deadline") groups = visibleDeadlineEntries().filter(([key]) => key !== "all").map(([key, label]) => [key, label, items.filter((item) => deadlineBucket(item) === key)]);
    if (grouping.modo === "status") groups = (activeDefinition.statuses || []).map((status) => [status.codigo, status.nome, items.filter((item) => item.status === status.codigo)]);
    if (grouping.modo === "field") {
      const fieldGroupValue = (item) => recordFilterValue(item, grouping.campo) || "Nao informado";
      const values = [...new Set(items.map(fieldGroupValue))]
        .sort((left, right) => left.localeCompare(right, "pt-BR", { numeric: true }));
      groups = values.map((value) => [value, value, items.filter((item) => fieldGroupValue(item) === value)]);
    }
    groups = groups.filter(([, , values]) => values.length);
    target.innerHTML = `<div class="dynamic-tool-deadline-groups">${groups.map(([, label, values]) => `<details ${grouping.iniciar_recolhido ? "" : "open"}><summary><span>${escapeHtml(label || "Nao informado")}</span><b>${values.length}</b></summary>${renderCards(values)}</details>`).join("")}</div>`;
  } else target.innerHTML = renderCards(items);
  target.querySelectorAll("[data-record-details]").forEach((button) => button.addEventListener("click", () => {
    openRecordDetails(button.dataset.recordDetails).catch((error) => window.alert(error.message));
  }));
  target.querySelectorAll("[data-record-notes]").forEach((button) => button.addEventListener("click", () => {
    openRecordDetails(button.dataset.recordNotes).catch((error) => window.alert(error.message));
  }));
  target.querySelectorAll("[data-record-copy]").forEach((button) => button.addEventListener("click", async () => {
    const item = records.find((record) => Number(record.id) === Number(button.dataset.recordCopy));
    if (!item) return;
    const keys = cardActions.copiar_campos.length ? cardActions.copiar_campos : [titleField?.chave].filter(Boolean);
    const text = keys.map((key) => recordFilterValue(item, key)).filter(Boolean).join("\t");
    if (text) await navigator.clipboard.writeText(text);
    button.title = text ? "Copiado" : "Nenhum dado configurado para copiar";
  }));
  const updateCardValue = async (item, value) => {
    if (cardActions.status_origem === "field") {
      const response = await apiPut(`/api/ferramentas/${activeDefinition.slug}/registros/${item.id}`, { payload: { [cardActions.status_campo]: value } });
      const index = records.findIndex((record) => record.id === item.id);
      if (index >= 0) records[index] = response.item;
    } else await saveDirectStatus(item, value);
    renderRecords();
  };
  target.querySelectorAll("[data-record-card-status]").forEach((select) => select.addEventListener("change", async () => {
    const item = records.find((record) => Number(record.id) === Number(select.dataset.recordCardStatus));
    if (!item) return;
    select.disabled = true;
    try { await updateCardValue(item, select.value); }
    catch (error) { select.disabled = false; window.alert(error.message); }
  }));
  target.querySelectorAll("[data-record-card-action]").forEach((button) => button.addEventListener("click", async () => {
    const item = records.find((record) => Number(record.id) === Number(button.dataset.recordCardAction));
    if (!item) return;
    if (!cardActions.botao_status) return openRecordDetails(item.id).catch((error) => window.alert(error.message));
    button.disabled = true;
    try { await updateCardValue(item, cardActions.botao_status); }
    catch (error) { button.disabled = false; window.alert(error.message); }
  }));
  const count = host.querySelector("[data-visible-count]");
  if (count) count.textContent = `${items.length} de ${records.length} registros`;
  syncClearFiltersButton();
}

function renderDashboard() {
  const target = host.querySelector("[data-tool-dashboard]");
  if (!target) return;
  const fields = activeDefinition.campos || [];
  const fieldMap = new Map(fields.map((field) => [field.chave, field]));
  const dashboardRecords = filteredRecords();
  const rows = dashboardRecords.map((record) => ({
    ...(record.payload || {}),
    STATUS: record.status,
    NEGOCIADOR: record.negociador,
    CARTEIRA: record.carteira,
    ATUALIZACAO: record.updated_at,
    _record_id: record.id,
    _title: record.titulo,
  }));
  const fallback = [
    { id: "total", tipo: "metric", titulo: "Total de registros", agregacao: "count", largura: 3, cor: activeDefinition.cor, status_codes: [] },
    { id: "status", tipo: "status", titulo: "Situacao dos registros", agregacao: "count", largura: 9, cor: activeDefinition.cor, status_codes: [] },
  ];
  const blocks = activeScreen()?.dashboard?.blocks?.length ? activeScreen().dashboard.blocks : fallback;
  const parseNumber = (value) => {
    if (typeof value === "number") return Number.isFinite(value) ? value : 0;
    const text = String(value ?? "").replace(/[^\d,.-]/g, "");
    if (!text) return 0;
    const normalized = text.includes(",") ? text.replace(/\./g, "").replace(",", ".") : text;
    return Number(normalized) || 0;
  };
  const parseDateValue = (value) => {
    if (!value) return null;
    if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
    const br = String(value).match(/^(\d{2})\/(\d{2})\/(\d{4})/);
    const date = br ? new Date(Number(br[3]), Number(br[2]) - 1, Number(br[1])) : new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  };
  const aggregate = (items, block) => {
    const aggregation = block.agregacao || "count";
    if (aggregation === "count") return items.length;
    const values = items.map((row) => parseNumber(row[block.campo]));
    const secondary = items.map((row) => parseNumber(row[block.campo_secundario]));
    const total = values.reduce((sum, value) => sum + value, 0);
    const secondaryTotal = secondary.reduce((sum, value) => sum + value, 0);
    if (aggregation === "average") return values.length ? total / values.length : 0;
    if (aggregation === "min") return values.length ? Math.min(...values) : 0;
    if (aggregation === "max") return values.length ? Math.max(...values) : 0;
    if (aggregation === "ratio") return secondaryTotal ? (total / secondaryTotal) * 100 : 0;
    if (aggregation === "difference") return total - secondaryTotal;
    if (aggregation === "duration_average") {
      const durations = items.map((row) => {
        const start = parseDateValue(row[block.campo]);
        const end = parseDateValue(row[block.campo_secundario]);
        return start && end ? Math.abs(end - start) / 86400000 : null;
      }).filter((value) => value !== null);
      return durations.length ? durations.reduce((sum, value) => sum + value, 0) / durations.length : 0;
    }
    return total;
  };
  const displayValue = (value, block) => {
    if ((block.agregacao || "count") === "count") return Number(value || 0).toLocaleString("pt-BR");
    if (block.agregacao === "ratio") return `${Number(value || 0).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
    if (block.agregacao === "duration_average") return `${Number(value || 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} dias`;
    return fieldMap.get(block.campo)?.tipo === "moeda"
      ? Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
      : Number(value || 0).toLocaleString("pt-BR", { maximumFractionDigits: 2 });
  };
  const scopedRows = (block) => rows.filter((row) => {
    if ((block.status_codes || []).length && !block.status_codes.includes(row.STATUS)) return false;
    if (!block.condicao_campo) return true;
    const actual = String(row[block.condicao_campo] ?? "").trim().toLocaleLowerCase("pt-BR");
    const expected = String(block.condicao_valor ?? "").trim().toLocaleLowerCase("pt-BR");
    const operator = block.condicao_operador || "eq";
    if (operator === "empty") return !actual;
    if (operator === "filled") return Boolean(actual);
    if (operator === "contains") return actual.includes(expected);
    if (operator === "neq") return actual !== expected;
    if (["gt", "gte", "lt", "lte"].includes(operator)) {
      const left = parseNumber(row[block.condicao_campo]);
      const right = parseNumber(block.condicao_valor);
      return operator === "gt" ? left > right : operator === "gte" ? left >= right : operator === "lt" ? left < right : left <= right;
    }
    return actual === expected;
  });
  const grouped = (items, block) => {
    const groups = new Map();
    items.forEach((row) => {
      const label = String(row[block.agrupador] ?? "").trim() || "Nao informado";
      if (!groups.has(label)) groups.set(label, []);
      groups.get(label).push(row);
    });
    return [...groups.entries()]
      .map(([label, values]) => ({ label, value: aggregate(values, block), count: values.length, rows: values }))
      .sort((left, right) => right.value - left.value)
      .slice(0, Math.max(3, Number(block.limite || 8)));
  };
  const timeline = (items, block) => {
    const groups = new Map();
    items.forEach((row) => {
      const raw = row[block.agrupador];
      const br = String(raw ?? "").match(/^(\d{2})\/(\d{2})\/(\d{4})/);
      const date = br ? new Date(Number(br[3]), Number(br[2]) - 1, Number(br[1])) : new Date(raw);
      if (Number.isNaN(date.getTime())) return;
      const key = block.periodo === "year"
        ? String(date.getFullYear())
        : block.periodo === "month"
          ? `${String(date.getMonth() + 1).padStart(2, "0")}/${date.getFullYear()}`
          : date.toLocaleDateString("pt-BR");
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(row);
    });
    return [...groups.entries()]
      .map(([label, values]) => ({ label, value: aggregate(values, block), count: values.length, rows: values }))
      .slice(-Math.max(3, Number(block.limite || 12)));
  };
  const bars = (values, block) => {
    const maximum = Math.max(...values.map((item) => item.value), 1);
    return `<div class="dynamic-dashboard-bars">${values.map((item) => `<button type="button" data-record-details="${item.rows?.[0]?._record_id || ""}"><span><b>${escapeHtml(item.label)}</b><strong>${escapeHtml(displayValue(item.value, block))}</strong></span><i style="--bar-width:${Math.max(2, (item.value / maximum) * 100)}%"></i></button>`).join("") || '<small class="dynamic-dashboard-empty">Sem dados para este bloco.</small>'}</div>`;
  };
  const blockContent = (block) => {
    const items = scopedRows(block);
    if (block.tipo === "metric") return `<button class="dynamic-dashboard-metric" type="button" data-record-details="${items[0]?._record_id || ""}"><strong class="dynamic-dashboard-value">${escapeHtml(displayValue(aggregate(items, block), block))}</strong><small>${items.length.toLocaleString("pt-BR")} registro(s) considerados</small></button>`;
    if (["status", "funnel"].includes(block.tipo)) {
      const statuses = (block.status_codes || []).length
        ? (activeDefinition.statuses || []).filter((status) => block.status_codes.includes(status.codigo))
        : (activeDefinition.statuses || []);
      return `<div class="dynamic-dashboard-statuses ${block.tipo === "funnel" ? "funnel" : ""}">${statuses.map((status) => { const statusRows = items.filter((row) => row.STATUS === status.codigo); return `<button type="button" data-record-details="${statusRows[0]?._record_id || ""}" style="--item-color:${escapeHtml(status.cor || block.cor || "#2563eb")}"><i></i><b>${statusRows.length.toLocaleString("pt-BR")}</b><small>${escapeHtml(status.nome)}</small></button>`; }).join("") || '<small class="dynamic-dashboard-empty">Sem status configurados.</small>'}</div>`;
    }
    if (["distribution", "ranking"].includes(block.tipo)) return bars(grouped(items, block), block);
    if (block.tipo === "timeline") return bars(timeline(items, block), block);
    if (block.tipo === "comparison") {
      const values = timeline(items, block).slice(-2);
      const current = values.at(-1)?.value || 0;
      const previous = values.at(-2)?.value || 0;
      const variation = previous ? ((current - previous) / Math.abs(previous)) * 100 : 0;
      return `<div class="dynamic-dashboard-comparison"><strong>${escapeHtml(displayValue(current, block))}</strong><span class="${variation < 0 ? "negative" : "positive"}">${variation >= 0 ? "+" : ""}${variation.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%</span><small>Periodo anterior: ${escapeHtml(displayValue(previous, block))}</small></div>`;
    }
    if (block.tipo === "deadline") {
      const today = new Date(); today.setHours(0, 0, 0, 0);
      const bucketDefinitions = [["Vencidos", (date) => date < today], ["Hoje", (date) => date.getTime() === today.getTime()], ["Proximos 7 dias", (date) => date > today && date <= new Date(today.getTime() + 7 * 86400000)], ["Posteriores", (date) => date > new Date(today.getTime() + 7 * 86400000)]];
      const values = bucketDefinitions.map(([label, matches]) => { const bucketRows = items.filter((row) => { const date = parseDateValue(row[block.agrupador]); return date && matches(date); }); return { label, value: bucketRows.length, count: bucketRows.length, rows: bucketRows }; });
      return bars(values, { ...block, agregacao: "count" });
    }
    if (block.tipo === "validation") {
      const invalid = items.filter((row) => !String(row[block.agrupador] ?? "").trim());
      return `<button class="dynamic-dashboard-alert" type="button" data-record-details="${invalid[0]?._record_id || ""}"><strong>${invalid.length.toLocaleString("pt-BR")}</strong><span>registro(s) sem ${escapeHtml(fieldMap.get(block.agrupador)?.nome || "valor obrigatorio")}</span></button>`;
    }
    const titleKey = activeDefinition.configuracao?.campo_titulo || "CLIENTE";
    const ordered = items.slice().sort((left, right) => block.tipo === "queue" ? new Date(left.ATUALIZACAO) - new Date(right.ATUALIZACAO) : new Date(right.ATUALIZACAO) - new Date(left.ATUALIZACAO));
    return `<div class="dynamic-dashboard-recent ${block.tipo === "queue" ? "queue" : ""}">${ordered.slice(0, Math.max(3, Number(block.limite || 6))).map((row) => `<button type="button" data-record-details="${row._record_id}"><span><b>${escapeHtml(row[titleKey] || row.CLIENTE || row._title || `Registro ${row._record_id}`)}</b><small>${escapeHtml(row.NEGOCIADOR || "Nao informado")}</small></span><time>${escapeHtml(formatDateTime(row.ATUALIZACAO))}</time></button>`).join("") || '<small class="dynamic-dashboard-empty">Nenhuma atualizacao encontrada.</small>'}</div>`;
  };
  target.innerHTML = `<section class="dynamic-tool-dashboard-configurable">${blocks.map((block) => `<article class="block-${escapeHtml(block.tipo || "metric")}" style="--metric-color:${escapeHtml(block.cor || activeDefinition.cor || "#2563eb")};--dashboard-span:${Math.min(12, Math.max(3, Number(block.largura || 6)))}"><header><span>${escapeHtml(block.titulo || "Bloco")}</span><small>${rows.length.toLocaleString("pt-BR")} na tela</small></header>${blockContent(block)}</article>`).join("")}</section>`;
  target.querySelectorAll("[data-record-details]").forEach((button) => button.addEventListener("click", () => {
    if (button.dataset.recordDetails) openRecordDetails(button.dataset.recordDetails).catch((error) => window.alert(error.message));
  }));
}

function statusCounts() {
  return Object.fromEntries(
    (activeDefinition?.statuses || []).map((status) => [
      status.codigo,
      records.filter((record) => record.status === status.codigo).length,
    ])
  );
}

function configuredMetricKeys() {
  const configured = activeDefinition?.configuracao?.metricas_cards;
  if (Array.isArray(configured)) return configured;
  if (usesVisibleStatus() && activeDefinition?.statuses?.length) {
    return activeDefinition.statuses.map((status) => `STATUS:${status.codigo}`);
  }
  return ["TOTAL", "MES_ATUAL"];
}

function dynamicColumns() {
  const columns = visibleFields().map((field) => ({
    id: `payload:${field.chave}`,
    title: field.nome,
    width: fieldWidth(field),
    type: field.tipo === "data"
      ? "date"
      : (["select", "multiselect"].includes(field.tipo) ? field.tipo : undefined),
    options: fieldOptions(field),
    value: (item) => item.payload?.[field.chave],
    display: (item) => formatValue(item.payload?.[field.chave], field),
  }));
  if (usesVisibleStatus()) {
    columns.push({
      id: "status",
      title: "Status",
      width: 156,
      type: "select",
      options: (activeDefinition.statuses || []).map((status) => ({
        value: status.codigo,
        label: status.nome,
      })),
      editable: negotiatorCanChangeStatus(),
      value: (item) => item.status,
      display: (item) => statusDefinition(item.status)?.nome || item.status,
      render: (item) => renderStatusBadge(item.status),
      save: negotiatorCanChangeStatus()
        ? (item, value) => saveDirectStatus(item, value)
        : undefined,
    });
  }
  columns.push(
    {
      id: "updated_at",
      title: "Atualizacao",
      width: 154,
      type: "date",
      value: (item) => item.updated_at,
      display: (item) => formatDateTime(item.updated_at),
    },
    {
      id: "acoes",
      title: "Acoes",
      width: 76,
      type: "action",
      render: (item) => `
        <button
          class="dynamic-row-action"
          type="button"
          data-record-details="${escapeHtml(item.id)}"
          title="Abrir registro"
          aria-label="Abrir registro"
        >&#8943;</button>
      `,
    },
  );
  return columns;
}

async function saveDirectStatus(item, statusCode) {
  const transition = (activeDefinition.transicoes || []).find((candidate) => (
    candidate.origem_codigo === item.status && candidate.destino_codigo === statusCode
  ));
  let response;
  if (transition) {
    const reason = transition.exige_justificativa ? window.prompt("Informe a justificativa:") : "";
    if (transition.exige_justificativa && !reason?.trim()) throw new Error("Justificativa obrigatoria.");
    response = await apiPost(`/api/ferramentas/${activeDefinition.slug}/registros/${item.id}/transicoes`, {
      status: statusCode,
      justificativa: reason,
    });
  } else {
    response = await apiPut(
      `/api/ferramentas/${activeDefinition.slug}/registros/${item.id}`,
      { payload: {}, status: statusCode },
    );
  }
  const index = records.findIndex((record) => record.id === item.id);
  if (index >= 0) records[index] = response.item;
  renderStatusNavigation();
  renderMetrics();
  if (activeStatus && response.item.status !== activeStatus) {
    window.setTimeout(() => renderRecords(), 0);
  }
  return response.item;
}

function fieldControl(field, value = null) {
  const required = field.obrigatorio ? "required" : "";
  const validation = field.validacao || {};
  const calculated = Boolean(validation.calculo);
  const constraints = [
    validation.min_length != null ? `minlength="${Number(validation.min_length)}"` : "",
    validation.max_length != null ? `maxlength="${Number(validation.max_length)}"` : "",
    validation.regex ? `pattern="${escapeHtml(validation.regex)}"` : "",
  ].filter(Boolean).join(" ");
  const name = `data-tool-field="${escapeHtml(field.chave)}"`;
  const normalized = value ?? field.valor_padrao ?? "";
  const automaticDate = field.tipo === "data" && field.validacao?.preenchimento_automatico === "today";
  if (field.tipo === "arquivo") {
    const extensions = validation.extensoes || field.opcoes || [];
    const accept = extensions.map((item) => `.${String(item).replace(/^\./, "")}`).join(",");
    const current = Array.isArray(normalized) ? normalized : normalized ? [normalized] : [];
    return `<div class="dynamic-file-control">
      <input type="file" ${name} ${accept ? `accept="${escapeHtml(accept)}"` : ""} ${validation.multiplo ? "multiple" : ""} ${required && !current.length ? "required" : ""}>
      <small>${current.length ? `Atual: ${escapeHtml(current.join(", "))}` : `Limite: ${Number(validation.max_mb || 15)} MB`}</small>
    </div>`;
  }
  if (field.tipo === "texto_longo") {
    return `<textarea ${name} ${required} ${constraints} ${calculated ? "readonly" : ""}>${escapeHtml(normalized)}</textarea>`;
  }
  if (field.tipo === "select") {
    return `<select ${name} ${required}>
      <option value="">Selecione</option>
      ${(field.opcoes || []).map((option) => `
        <option value="${escapeHtml(option)}" ${String(normalized) === String(option) ? "selected" : ""}>${escapeHtml(option)}</option>
      `).join("")}
    </select>`;
  }
  if (field.tipo === "multiselect") {
    const selected = new Set(Array.isArray(normalized) ? normalized : []);
    return `<div class="dynamic-multiselect" ${name}>
      ${(field.opcoes || []).map((option) => `
        <label><input type="checkbox" value="${escapeHtml(option)}" ${selected.has(option) ? "checked" : ""}> ${escapeHtml(option)}</label>
      `).join("")}
    </div>`;
  }
  if (field.tipo === "boolean") {
    return `<label class="dynamic-multiselect"><input type="checkbox" ${name} ${normalized ? "checked" : ""}> Sim</label>`;
  }
  const type = field.tipo === "data" ? "date" : "text";
  const inputMode = ["numero", "moeda"].includes(field.tipo) ? 'inputmode="decimal"' : "";
  if (automaticDate) {
    const now = new Date();
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    return `<input type="date" ${name} value="${escapeHtml(normalized || today)}" readonly>
      <small class="dynamic-field-hint">Preenchido automaticamente ao cadastrar</small>`;
  }
  return `<input type="${type}" ${inputMode} ${name} value="${escapeHtml(normalized)}" ${required} ${constraints} ${calculated ? "readonly" : ""}>
    ${calculated ? '<small class="dynamic-field-hint">Calculado automaticamente</small>' : ""}`;
}

function readFormPayload(form, record = null) {
  const payload = {};
  visibleFields().forEach((field) => {
    const control = form.querySelector(`[data-tool-field="${CSS.escape(field.chave)}"]`);
    const wrapper = control?.closest("[data-field-wrap]");
    const automaticDate = field.tipo === "data" && field.validacao?.preenchimento_automatico === "today";
    if (!control || wrapper?.hidden || field.somente_leitura || automaticDate) return;
    if (field.tipo === "arquivo") {
      const names = [...(control.files || [])].map((file) => file.name);
      const multiple = Boolean(field.validacao?.multiplo);
      payload[field.chave] = names.length
        ? (multiple ? names : names[0])
        : (record?.payload?.[field.chave] ?? null);
    } else if (field.tipo === "multiselect") {
      payload[field.chave] = [...control.querySelectorAll('input[type="checkbox"]:checked')].map((input) => input.value);
    } else if (field.tipo === "boolean") {
      payload[field.chave] = control.checked;
    } else {
      payload[field.chave] = control.value;
    }
  });
  return payload;
}

function selectedFileFields(form) {
  return visibleFields().filter((field) => field.tipo === "arquivo").map((field) => {
    const control = form.querySelector(`[data-tool-field="${CSS.escape(field.chave)}"]`);
    if (control?.closest("[data-field-wrap]")?.hidden) return { field, files: [] };
    return { field, files: [...(control?.files || [])] };
  }).filter((item) => item.files.length);
}

async function uploadRecordFiles(recordId, fileFields) {
  for (const { field, files } of fileFields) {
    const body = new FormData();
    body.append("campo", field.chave);
    files.forEach((file) => body.append("arquivos", file, file.name));
    const response = await fetch(`/api/ferramentas/${activeDefinition.slug}/registros/${recordId}/anexos`, {
      method: "POST",
      credentials: "include",
      body,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `Nao foi possivel anexar ${field.nome}.`);
    }
  }
}

function conditionMatches(condition, payload) {
  if (!condition?.campo) return true;
  const actual = payload[condition.campo];
  const normalize = (value) => typeof value === "string" ? value.trim().toLocaleLowerCase("pt-BR") : value;
  const equals = (left, right) => {
    if (Array.isArray(left)) return left.some((item) => normalize(item) === normalize(right));
    return normalize(left) === normalize(right);
  };
  if (condition.operador === "diferente") return !equals(actual, condition.valor);
  if (condition.operador === "preenchido") return ![null, undefined, "", false].includes(actual);
  if (condition.operador === "vazio") return [null, undefined, "", false].includes(actual);
  if (condition.operador === "contem") return normalize(String(actual || "")).includes(normalize(String(condition.valor || "")));
  if (condition.operador === "em") return (Array.isArray(condition.valor) ? condition.valor : [condition.valor]).some((item) => equals(actual, item));
  if (condition.operador === "nao_em") return !(Array.isArray(condition.valor) ? condition.valor : [condition.valor]).some((item) => equals(actual, item));
  const actualNumber = Number(String(actual ?? "").replace(/\./g, "").replace(",", "."));
  const expectedNumber = Number(String(condition.valor ?? "").replace(/\./g, "").replace(",", "."));
  if (condition.operador === "maior") return actualNumber > expectedNumber;
  if (condition.operador === "maior_igual") return actualNumber >= expectedNumber;
  if (condition.operador === "menor") return actualNumber < expectedNumber;
  if (condition.operador === "menor_igual") return actualNumber <= expectedNumber;
  return equals(actual, condition.valor);
}

function numericValue(value) {
  const normalized = String(value ?? "").replace(/[^0-9,.\-]/g, "");
  const parsed = Number(normalized.includes(",") ? normalized.replace(/\./g, "").replace(",", ".") : normalized);
  return Number.isFinite(parsed) ? parsed : 0;
}

function calculateField(calculation, payload) {
  const left = numericValue(payload[calculation.campo_base]);
  const right = calculation.campo_secundario ? numericValue(payload[calculation.campo_secundario]) : numericValue(calculation.valor);
  if (calculation.operacao === "soma") return left + right;
  if (calculation.operacao === "subtracao") return left - right;
  if (calculation.operacao === "multiplicacao") return left * right;
  if (calculation.operacao === "divisao") return right ? left / right : 0;
  return left * right / 100;
}

function syncCalculatedFields(form, payload) {
  for (let pass = 0; pass < visibleFields().length; pass += 1) {
    let changed = false;
    visibleFields().forEach((field) => {
      const calculation = field.validacao?.calculo;
      if (!calculation?.campo_base || !conditionMatches(calculation.condicao, payload)) return;
      const result = calculateField(calculation, payload).toFixed(2).replace(".", ",");
      const control = form.querySelector(`[data-tool-field="${CSS.escape(field.chave)}"]`);
      if (control && control.value !== result) control.value = result;
      if (payload[field.chave] !== result) {
        payload[field.chave] = result;
        changed = true;
      }
    });
    if (!changed) break;
  }
}

export function syncConditionalControlState(wrapper, visible) {
  wrapper.hidden = !visible;
  wrapper.querySelectorAll("input, select, textarea, button").forEach((control) => {
    if (control.dataset.conditionRequired === undefined) {
      control.dataset.conditionRequired = control.required ? "true" : "false";
    }
    if (control.dataset.conditionDisabled === undefined) {
      control.dataset.conditionDisabled = control.disabled ? "true" : "false";
    }
    control.required = visible && control.dataset.conditionRequired === "true";
    control.disabled = !visible || control.dataset.conditionDisabled === "true";
  });
}

function syncConditionalFields(form) {
  const payload = readFormPayload(form);
  syncCalculatedFields(form, payload);
  form.querySelectorAll("[data-field-wrap]").forEach((wrapper) => {
    const field = activeDefinition.campos.find((item) => item.chave === wrapper.dataset.fieldWrap);
    const visible = conditionMatches(field?.condicao, payload);
    syncConditionalControlState(wrapper, visible);
  });
}

function createDialog(id, content) {
  document.querySelector(`#${id}`)?.remove();
  const dialog = document.createElement("dialog");
  dialog.id = id;
  dialog.className = "modal";
  dialog.innerHTML = content;
  document.body.append(dialog);
  return dialog;
}

function openRecordForm(record = null) {
  const fields = visibleFields().filter((field) => !field.somente_leitura || field.validacao?.calculo);
  const steps = [...new Set(fields.map((field) => field.etapa))].sort((a, b) => a - b);
  const hasEditableStatus = (
    (!record && negotiatorSelectsInitialStatus())
    || (record && negotiatorCanChangeStatus())
  );
  const dialog = createDialog("dynamicToolFormDialog", `
    <form class="modal-card dynamic-tool-dialog" id="dynamicToolForm">
      <div class="modal-header">
        <div class="dynamic-form-title">
          <div><p class="eyebrow">${escapeHtml(activeDefinition.nome)}</p><h2>${record ? "Editar registro" : "Novo registro"}</h2></div>
        </div>
        <button class="icon-btn" type="button" data-close aria-label="Fechar">x</button>
      </div>
      <nav class="dynamic-form-progress" aria-label="Etapas do cadastro">
        ${steps.map((step, index) => `
          ${index ? '<span class="dynamic-form-progress-line" aria-hidden="true"></span>' : ""}
          <button type="button" class="${index === 0 ? "active" : ""}" data-form-step-link="${step}" data-step-index="${index}">
            <span>${index + 1}</span><small>Etapa ${step}</small>
          </button>
        `).join("")}
      </nav>
      <div class="dynamic-form-layout">
        <div class="dynamic-tool-form">
          ${steps.map((step, index) => `
            <section class="dynamic-tool-form-section" data-form-step-section="${step}" ${index === 0 ? "" : "hidden"}>
              <div class="dynamic-tool-form-step">
                <div><strong>Etapa ${step}</strong><small data-form-step-count></small></div>
                <small data-form-step-hint></small>
              </div>
              <div class="dynamic-tool-form-fields">
                ${index === 0 && hasEditableStatus ? `
                  <label class="dynamic-tool-field wide dynamic-form-status">
                    <span>${record ? "Status do registro" : "Status inicial"}<b aria-hidden="true">*</b></span>
                    <select data-tool-status required>
                      ${(activeDefinition.statuses || []).map((status) => `
                        <option value="${escapeHtml(status.codigo)}" ${
                          (record ? record.status === status.codigo : status.inicial) ? "selected" : ""
                        }>${escapeHtml(status.nome)}</option>
                      `).join("")}
                    </select>
                  </label>
                ` : ""}
                ${fields.filter((field) => field.etapa === step).map((field) => `
                  <label class="dynamic-tool-field ${["texto_longo", "multiselect", "arquivo"].includes(field.tipo) ? "wide" : ""}" data-field-wrap="${escapeHtml(field.chave)}">
                    <span>${escapeHtml(field.nome)}${field.obrigatorio ? '<b aria-hidden="true">*</b>' : ""}</span>
                    ${fieldControl(field, record?.payload?.[field.chave])}
                  </label>
                `).join("")}
              </div>
            </section>
          `).join("")}
        </div>
      </div>
      <div class="modal-actions">
        <button class="secondary-btn" type="button" data-close>Cancelar</button>
        <button class="secondary-btn" type="button" data-form-back hidden>Voltar</button>
        <button class="primary-btn" type="button" data-form-next ${steps.length > 1 ? "" : "hidden"}>Avancar</button>
        <button class="primary-btn" type="submit" data-form-submit ${steps.length > 1 ? "hidden" : ""}>${record ? "Salvar alteracoes" : "Cadastrar"}</button>
      </div>
    </form>
  `);
  dialog.classList.add("dynamic-tool-modal", "dynamic-tool-drawer");
  dialog.style.setProperty("--primary", activeDefinition.cor || "#2563eb");
  const form = dialog.querySelector("#dynamicToolForm");
  const progress = dialog.querySelector(".dynamic-form-progress");
  const firstConfiguredStep = steps[0];
  let effectiveSteps = [...steps];
  let activeStepIndex = 0;
  const renderProgress = () => {
    progress.innerHTML = effectiveSteps.map((step, index) => `
      ${index ? '<span class="dynamic-form-progress-line" aria-hidden="true"></span>' : ""}
      <button type="button" data-form-step-link="${step}" data-step-index="${index}">
        <span>${index + 1}</span><small>Etapa ${step}</small>
      </button>
    `).join("");
    progress.hidden = effectiveSteps.length <= 1;
  };
  const showStep = (nextIndex, { scroll = true } = {}) => {
    activeStepIndex = Math.max(0, Math.min(effectiveSteps.length - 1, nextIndex));
    const activeStep = effectiveSteps[activeStepIndex];
    dialog.querySelectorAll("[data-form-step-section]").forEach((section) => {
      section.hidden = Number(section.dataset.formStepSection) !== activeStep;
    });
    dialog.querySelectorAll("[data-form-step-link]").forEach((button, index) => {
      button.classList.toggle("active", index === activeStepIndex);
      button.classList.toggle("complete", index < activeStepIndex);
      button.setAttribute("aria-current", index === activeStepIndex ? "step" : "false");
    });
    dialog.querySelector("[data-form-back]").hidden = activeStepIndex === 0;
    dialog.querySelector("[data-form-next]").hidden = activeStepIndex >= effectiveSteps.length - 1;
    dialog.querySelector("[data-form-submit]").hidden = activeStepIndex < effectiveSteps.length - 1;
    if (scroll) dialog.querySelector(".dynamic-tool-form")?.scrollTo({ top: 0, behavior: "smooth" });
  };
  const syncFormFlow = ({ scroll = false } = {}) => {
    const previousStep = effectiveSteps[activeStepIndex];
    syncConditionalFields(form);
    const nextSteps = [];
    dialog.querySelectorAll("[data-form-step-section]").forEach((section) => {
      const step = Number(section.dataset.formStepSection);
      const visibleFieldCount = [...section.querySelectorAll("[data-field-wrap]")]
        .filter((wrapper) => !wrapper.hidden).length;
      const includesStatus = hasEditableStatus && step === firstConfiguredStep;
      const count = section.querySelector("[data-form-step-count]");
      if (count) count.textContent = `${visibleFieldCount} ${visibleFieldCount === 1 ? "campo" : "campos"}`;
      if (visibleFieldCount || includesStatus) nextSteps.push(step);
    });
    effectiveSteps = nextSteps.length ? nextSteps : [firstConfiguredStep];
    const preservedIndex = effectiveSteps.indexOf(previousStep);
    activeStepIndex = preservedIndex >= 0
      ? preservedIndex
      : Math.min(activeStepIndex, effectiveSteps.length - 1);
    dialog.querySelectorAll("[data-form-step-section]").forEach((section) => {
      const step = Number(section.dataset.formStepSection);
      const effectiveIndex = effectiveSteps.indexOf(step);
      const hint = section.querySelector("[data-form-step-hint]");
      if (hint) hint.textContent = effectiveIndex < effectiveSteps.length - 1
        ? "Preencha os campos para avancar."
        : "Revise os dados antes de salvar.";
    });
    renderProgress();
    showStep(activeStepIndex, { scroll });
  };
  const validateCurrentStep = () => {
    syncFormFlow();
    const activeStep = effectiveSteps[activeStepIndex];
    const section = dialog.querySelector(`[data-form-step-section="${activeStep}"]`);
    if (!section) return true;
    const invalid = [...section.querySelectorAll("input, select, textarea")]
      .find((control) => !control.disabled && !control.checkValidity());
    if (!invalid) return true;
    invalid.reportValidity();
    invalid.focus();
    return false;
  };
  dialog.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => dialog.close()));
  progress.addEventListener("click", (event) => {
    const button = event.target.closest("[data-form-step-link]");
    if (!button) return;
    const nextIndex = Number(button.dataset.stepIndex);
    if (nextIndex <= activeStepIndex || validateCurrentStep()) showStep(nextIndex);
  });
  dialog.querySelector("[data-form-back]")?.addEventListener("click", () => showStep(activeStepIndex - 1));
  dialog.querySelector("[data-form-next]")?.addEventListener("click", () => {
    if (validateCurrentStep()) showStep(activeStepIndex + 1);
  });
  form.addEventListener("input", () => syncFormFlow());
  form.addEventListener("change", () => syncFormFlow());
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    syncFormFlow();
    if (activeStepIndex < effectiveSteps.length - 1) {
      if (validateCurrentStep()) showStep(activeStepIndex + 1);
      return;
    }
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    try {
      const payload = {
        payload: readFormPayload(form, record),
        status: form.querySelector("[data-tool-status]")?.value || null,
      };
      const fileFields = selectedFileFields(form);
      validateSelectedFiles(fileFields);
      const response = record
        ? await apiPut(`/api/ferramentas/${activeDefinition.slug}/registros/${record.id}`, payload)
        : await apiPost(`/api/ferramentas/${activeDefinition.slug}/registros`, payload);
      await uploadRecordFiles(response.item.id, fileFields);
      dialog.close();
      await loadDynamicTool(activeDefinition.slug);
    } catch (error) {
      window.alert(error.message);
    } finally {
      submit.disabled = false;
    }
  });
  syncFormFlow();
  dialog.showModal();
}

async function openRecordDetails(recordId) {
  const { item } = await apiGet(`/api/ferramentas/${activeDefinition.slug}/registros/${recordId}`);
  const transitions = (activeDefinition.transicoes || []).filter(
    (transition) => transition.origem_codigo === item.status && transition.permite_negociador
  );
  const fields = visibleFields();
  const fieldLayout = activeScreen()?.campo_layout || {};
  const titleField = fields.find((field) => fieldLayout[field.chave]?.papel === "titulo");
  const subtitleField = fields.find((field) => fieldLayout[field.chave]?.papel === "subtitulo");
  const headerFields = new Set([titleField?.chave, subtitleField?.chave].filter(Boolean));
  const documentFields = fields.filter((field) => field.tipo === "arquivo" && !headerFields.has(field.chave));
  const financialFields = fields.filter((field) => {
    if (headerFields.has(field.chave) || field.tipo === "arquivo") return false;
    return field.tipo === "moeda" || /(VALOR|HONOR|H\.?O\.?|CUSTA|ENTRADA|PAGAMENTO|OFERTA)/i.test(`${field.chave} ${field.nome}`);
  });
  const financialKeys = new Set(financialFields.map((field) => field.chave));
  const generalFields = fields.filter((field) => (
    !headerFields.has(field.chave)
    && field.tipo !== "arquivo"
    && !financialKeys.has(field.chave)
  ));
  const identifierField = fields.find((field) => /(NPJ|CPF|CNPJ|DEBIT|SUIT|PROCESSO|CONTRATO|\bPJ\b)/i.test(`${field.chave} ${field.nome}`));
  const detailValue = (field) => {
    const formatted = formatValue(item.payload?.[field.chave], field);
    return formatted === "Vazio" ? "Nao informado" : formatted;
  };
  const renderDetailFields = (items) => items.map((field) => {
    const value = detailValue(field);
    const isEmpty = value === "Nao informado";
    const wide = ["texto_longo", "multiselect"].includes(field.tipo) || String(value).length > 80;
    return `<div class="dynamic-record-value ${wide ? "wide" : ""} ${isEmpty ? "is-empty" : ""}">
      <small>${escapeHtml(field.nome)}</small>
      <strong>${escapeHtml(value)}</strong>
    </div>`;
  }).join("");
  const title = item.payload?.[titleField?.chave] || item.titulo || `Registro ${item.id}`;
  const subtitle = item.payload?.[subtitleField?.chave];
  const identifier = identifierField ? detailValue(identifierField) : "";
  const updatedAt = item.updated_at ? new Date(item.updated_at).toLocaleString("pt-BR") : "Nao informado";
  const createdAt = item.created_at ? new Date(item.created_at).toLocaleString("pt-BR") : "Nao informado";
  const dialog = createDialog("dynamicToolDetailsDialog", `
    <div class="modal-card dynamic-tool-dialog dynamic-record-dialog">
      <div class="modal-header dynamic-record-header">
        <div class="dynamic-record-heading-copy">
          <span class="dynamic-record-tool-mark" aria-hidden="true">${escapeHtml(activeDefinition.icone || activeDefinition.nome?.[0] || "R")}</span>
          <div>
            <p class="eyebrow">${escapeHtml(activeDefinition.nome)}</p>
            <h2>${escapeHtml(title)}</h2>
            <p class="dynamic-record-kicker">${[
              subtitle ? String(subtitle) : "",
              identifier && identifier !== "Nao informado" ? `${identifierField?.nome}: ${identifier}` : "",
              item.carteira ? `Carteira ${item.carteira}` : "",
            ].filter(Boolean).map(escapeHtml).join(" &middot; ")}</p>
          </div>
        </div>
        <div class="dynamic-record-header-actions">
          ${usesVisibleStatus() ? renderStatusBadge(item.status) : ""}
          <button class="icon-btn" type="button" data-close aria-label="Fechar">x</button>
        </div>
      </div>
      <div class="dynamic-record-body">
        <div class="dynamic-record-meta">
          <div><small>Criado</small><strong>${escapeHtml(createdAt)}</strong></div>
          <div><small>Atualizado</small><strong>${escapeHtml(updatedAt)}</strong></div>
          <div><small>Responsavel</small><strong>${escapeHtml(item.negociador || "Nao informado")}</strong></div>
        </div>

        ${generalFields.length ? `<section class="dynamic-record-section">
          <div class="dynamic-record-section-heading"><span>Dados do registro</span><small>${generalFields.length} campos</small></div>
          <div class="dynamic-record-values">${renderDetailFields(generalFields)}</div>
        </section>` : ""}

        ${financialFields.length ? `<section class="dynamic-record-section">
          <div class="dynamic-record-section-heading"><span>Valores</span><small>${financialFields.length} campos</small></div>
          <div class="dynamic-record-values financial">${renderDetailFields(financialFields)}</div>
        </section>` : ""}

        ${(documentFields.length || (item.anexos || []).length) ? `<section class="dynamic-record-section">
          <div class="dynamic-record-section-heading"><span>Documentos</span><small>${(item.anexos || []).length} anexos</small></div>
          ${documentFields.length ? `<div class="dynamic-record-values compact">${renderDetailFields(documentFields)}</div>` : ""}
          <div class="dynamic-attachment-list">
            ${(item.anexos || []).map((attachment) => `<article class="dynamic-attachment-item">
              <div><strong>${escapeHtml(attachment.nome)}</strong><span>${escapeHtml(attachment.usuario || "Usuario")} &middot; ${Math.max(1, Math.round(Number(attachment.tamanho || 0) / 1024))} KB</span></div>
              <a class="secondary-btn" href="/api/ferramentas/${encodeURIComponent(activeDefinition.slug)}/registros/${item.id}/anexos/${attachment.id}" download>Baixar</a>
            </article>`).join("") || '<p class="dynamic-record-empty">Nenhum arquivo anexado.</p>'}
          </div>
        </section>` : ""}

        ${transitions.length ? `<section class="dynamic-record-section dynamic-record-actions-section">
          <div class="dynamic-record-section-heading"><span>Proximas acoes</span></div>
          <div class="dynamic-transition-list">
            ${transitions.map((transition) => `<button class="dynamic-transition-action" type="button" data-transition="${escapeHtml(transition.destino_codigo)}" data-reason="${transition.exige_justificativa ? "1" : "0"}" style="--transition-color:${escapeHtml(statusDefinition(transition.destino_codigo)?.cor || "#2563eb")}">${escapeHtml(transition.nome)}</button>`).join("")}
          </div>
        </section>` : ""}

        <details class="dynamic-record-disclosure">
          <summary><span>Historico do fluxo</span><small>${(item.eventos || []).length} eventos</small></summary>
          <div class="dynamic-event-list">
            ${(item.eventos || []).slice().reverse().map((event) => `
              <article class="dynamic-event-item">
                <i></i>
                <div><strong>${escapeHtml(event.tipo === "TRANSICAO" ? `${statusDefinition(event.status_anterior)?.nome || event.status_anterior || "Inicio"} -> ${statusDefinition(event.status_novo)?.nome || event.status_novo || ""}` : event.tipo)}</strong>
                <span>${escapeHtml(event.usuario || "Sistema")} &middot; ${escapeHtml(new Date(event.created_at).toLocaleString("pt-BR"))}</span>
                ${event.justificativa ? `<p>${escapeHtml(event.justificativa)}</p>` : ""}</div>
              </article>
            `).join("") || "<p>Nenhuma movimentacao registrada.</p>"}
          </div>
        </details>

        <details class="dynamic-record-disclosure">
          <summary><span>Comentarios</span><small>${(item.comentarios || []).length} registros</small></summary>
          <div class="dynamic-comment-list">
            ${(item.comentarios || []).map((comment) => `<div class="dynamic-comment"><strong>${escapeHtml(comment.usuario || "Usuario")}</strong><p>${escapeHtml(comment.texto)}</p></div>`).join("") || "<p>Nenhum comentario.</p>"}
          </div>
          <form class="dynamic-tool-toolbar dynamic-comment-form" data-comment-form>
            <input name="texto" placeholder="Adicionar comentario" required>
            <button class="secondary-btn" type="submit">Comentar</button>
          </form>
        </details>
      </div>
      <div class="modal-actions">
        <button class="secondary-btn" type="button" data-close>Fechar</button>
        ${activeDefinition.permissoes.editar ? '<button class="primary-btn" type="button" data-edit>Editar registro</button>' : ""}
      </div>
    </div>
  `);
  dialog.classList.add("dynamic-tool-modal", "dynamic-tool-details-modal");
  dialog.style.setProperty("--primary", activeDefinition.cor || "#2563eb");
  dialog.style.setProperty("--tool-color", activeDefinition.cor || "#2563eb");
  dialog.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => dialog.close()));
  dialog.querySelector("[data-edit]")?.addEventListener("click", () => {
    dialog.close();
    openRecordForm(item);
  });
  dialog.querySelectorAll("[data-transition]").forEach((button) => {
    button.addEventListener("click", async () => {
      const reason = button.dataset.reason === "1" ? window.prompt("Informe a justificativa:") : "";
      if (button.dataset.reason === "1" && !reason?.trim()) return;
      await apiPost(`/api/ferramentas/${activeDefinition.slug}/registros/${item.id}/transicoes`, {
        status: button.dataset.transition,
        justificativa: reason,
      });
      dialog.close();
      await loadDynamicTool(activeDefinition.slug);
    });
  });
  dialog.querySelector("[data-comment-form]")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await apiPost(`/api/ferramentas/${activeDefinition.slug}/registros/${item.id}/comentarios`, {
      texto: event.currentTarget.elements.texto.value,
    });
    dialog.close();
    await openRecordDetails(item.id);
  });
  dialog.showModal();
}

function renderRecords() {
  if (activeScreen()?.tipo === "dashboard") {
    renderDashboard();
    const count = host.querySelector("[data-visible-count]");
    if (count) count.textContent = `${filteredRecords().length} de ${records.length} registros`;
    syncClearFiltersButton();
    return;
  }
  const gridHost = host.querySelector("[data-tool-grid]");
  if (!gridHost) {
    renderScreenRecords();
    return;
  }
  if (!toolGrid) {
    gridMountSequence += 1;
    toolGrid = createExcelGrid(gridHost, {
      id: `dynamic-tool-grid:${activeDefinition.slug}:${gridMountSequence}`,
      persistKey: `negocial:ferramenta:${activeDefinition.slug}`,
      filters: true,
      virtualThreshold: 250,
      emptyTitle: "Nenhum registro nesta visualizacao",
      emptyDescription: "Altere os filtros ou cadastre um novo registro para continuar.",
      onError: (error) => window.alert(error.message || error),
    });
  }
  toolGrid.render(filteredRecords(), dynamicColumns(), { preservePosition: true });
  const count = host.querySelector("[data-visible-count]");
  if (count) count.textContent = `${filteredRecords().length} de ${records.length} registros`;
  syncClearFiltersButton();
}

function renderStatusNavigation() {
  const counts = statusCounts();
  const statusHost = host.querySelector("[data-status-navigation]");
  if (!statusHost) return;
  statusHost.innerHTML = usesVisibleStatus() ? `
    <button class="dynamic-tool-status-tab ${!activeStatus ? "active" : ""}" data-status=""><strong>Todos</strong><span>${records.length}</span></button>
    ${(activeDefinition.statuses || []).map((status) => `
      <button class="dynamic-tool-status-tab ${activeStatus === status.codigo ? "active" : ""}" data-status="${escapeHtml(status.codigo)}" style="--status-color:${escapeHtml(status.cor || "#2563eb")}">
        <i aria-hidden="true"></i><strong>${escapeHtml(status.nome)}</strong><span>${counts[status.codigo] || 0}</span>
      </button>
    `).join("")}
  ` : `<strong>${records.length} registro(s)</strong>`;
  statusHost.querySelectorAll("[data-status]").forEach((button) => {
    button.addEventListener("click", () => {
      activeStatus = button.dataset.status;
      renderStatusNavigation();
      renderRecords();
    });
  });
}

function renderMetrics() {
  const metricsHost = host.querySelector("[data-tool-metrics]");
  if (!metricsHost) return;
  const metricKeys = configuredMetricKeys();
  const counts = statusCounts();
  const now = new Date();
  const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const monthCount = records.filter((item) => String(item.created_at || item.updated_at || "").startsWith(currentMonth)).length;
  metricsHost.innerHTML = metricKeys.map((key) => {
    if (key === "TOTAL") {
      return `<div class="dynamic-tool-metric" style="--metric-color:${escapeHtml(activeDefinition.cor || "#2563eb")}">
        <span>Total de registros</span><strong>${records.length}</strong><small>Base desta ferramenta</small>
      </div>`;
    }
    if (key === "MES_ATUAL") {
      return `<div class="dynamic-tool-metric" style="--metric-color:#0f9f6e">
        <span>Criados neste mes</span><strong>${monthCount}</strong><small>Competencia atual</small>
      </div>`;
    }
    if (key.startsWith("STATUS:")) {
      const statusCode = key.slice(7);
      const status = statusDefinition(statusCode);
      if (!status || !usesVisibleStatus()) return "";
      return `<button type="button" class="dynamic-tool-metric" data-metric-status="${escapeHtml(status.codigo)}" style="--metric-color:${escapeHtml(status.cor || "#2563eb")}">
        <span>${escapeHtml(status.nome)}</span>
        <strong>${counts[status.codigo] || 0}</strong>
        <small>${records.length ? Math.round(((counts[status.codigo] || 0) / records.length) * 100) : 0}% do total</small>
      </button>`;
    }
    return "";
  }).join("");
  metricsHost.querySelectorAll("[data-metric-status]").forEach((button) => {
    button.addEventListener("click", () => {
      activeStatus = button.dataset.metricStatus;
      renderStatusNavigation();
      renderRecords();
    });
  });
}

function setFocusMode(enabled) {
  host.classList.toggle("dynamic-tool-focus", enabled);
  document.body.classList.toggle("dynamic-tool-focus-open", enabled);
  host.querySelector("[data-focus-tool]")?.setAttribute("aria-pressed", String(enabled));
  const label = host.querySelector("[data-focus-label]");
  if (label) label.textContent = enabled ? "Sair do modo foco" : "Modo foco";
}

export function exitDynamicToolFocus() {
  setFocusMode(false);
}

function renderTool() {
  toolGrid = null;
  const screen = activeScreen();
  if (!activeScreenId) activeScreenId = screen.id;
  const isSpreadsheet = screen.tipo === "planilha" || screenHas("planilha");
  const isDashboard = screen.tipo === "dashboard";
  const showSearch = screenHas("busca");
  const showFilters = screenHas("filtros");
  const filterConfig = configuredFilters();
  const showStatusFilters = showFilters && filterConfig.mostrar_status && usesVisibleStatus();
  const showCommandBar = showSearch || showFilters;
  const configuredMetrics = configuredMetricKeys();
  const showMetricCards = screenHas("metricas")
    && activeDefinition.configuracao?.mostrar_cards !== false
    && configuredMetrics.length;
  const customFilterFields = (filterConfig.campos || []).map((key) => visibleFields().find((field) => field.chave === key)).filter(Boolean);
  host.innerHTML = `
    <div class="dynamic-tool-summary">
      <div class="dynamic-tool-summary-meta">
        <span data-visible-count>${records.length} registros</span>
        <small>Atualizado ${escapeHtml(lastLoadedAt?.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) || "agora")}</small>
      </div>
      <div class="dynamic-tool-summary-actions">
        <button class="secondary-btn" type="button" data-refresh-tool title="Atualizar registros">&#8635; Atualizar</button>
        ${activeDefinition.permissoes.exportar ? '<button class="secondary-btn" type="button" data-export-tool>Gerar relatorio</button>' : ""}
        ${isSpreadsheet ? '<button class="secondary-btn dynamic-focus-btn" type="button" data-focus-tool aria-pressed="false"><span data-focus-label>Modo foco</span></button>' : ""}
        ${activeDefinition.permissoes.criar ? '<button class="primary-btn" type="button" data-new-record><span aria-hidden="true">+</span> Novo registro</button>' : ""}
      </div>
    </div>
    <nav class="dynamic-tool-screen-tabs" data-screen-navigation></nav>
    ${!isDashboard ? `<div class="dynamic-tool-screen-label"><strong>${escapeHtml(screen.nome)}</strong><small>${isSpreadsheet ? "Planilha" : screen.tipo === "aprovacao" ? "Fluxo de aprovacao" : "Lista operacional"}</small></div>` : ""}
    ${showMetricCards ? '<div class="dynamic-tool-metrics" data-tool-metrics></div>' : ""}
    ${screen.tipo === "aprovacao" ? `<div class="dynamic-tool-view-switch"><button type="button" data-screen-mode="pending" class="${!screenHistoryMode ? "active" : ""}">Pendentes</button><button type="button" data-screen-mode="history" class="${screenHistoryMode ? "active" : ""}">Historico</button></div>` : ""}
    ${showCommandBar ? `<div class="dynamic-tool-command">
      ${showStatusFilters ? '<div class="dynamic-tool-status-tabs" data-status-navigation></div>' : ''}
      <div class="dynamic-tool-toolbar">
        ${showSearch ? `
        <label class="dynamic-tool-search">
          <span aria-hidden="true"></span>
          <input data-tool-search placeholder="Buscar em ${escapeHtml(activeDefinition.nome)}" value="${escapeHtml(searchTerm)}">
        </label>` : ""}
        ${showFilters && filterConfig.modo_data === "date" ? `<input type="date" data-tool-date value="${escapeHtml(dateTerm)}" title="Filtrar por data">` : ""}
        ${showFilters && filterConfig.modo_data === "period" ? `<input type="date" data-tool-date-from value="${escapeHtml(dateFromTerm)}" title="Data inicial"><input type="date" data-tool-date-to value="${escapeHtml(dateToTerm)}" title="Data final">` : ""}
        ${showFilters && filterConfig.modo_data === "deadline" ? `<div class="dynamic-tool-deadline-tabs" aria-label="Filtrar por prazo">${visibleDeadlineEntries().map(([value, label]) => { const filterValue = value === "all" ? "" : value; return `<button type="button" class="${deadlineTerm === filterValue ? "active" : ""}" data-tool-deadline-option="${escapeHtml(filterValue)}">${escapeHtml(label)}</button>`; }).join("")}</div>` : ""}
        ${showFilters && filterConfig.mostrar_negociador ? `<select data-tool-operator title="Filtrar por negociador"><option value="">Todos os negociadores</option>${uniqueFilterValues("NEGOCIADOR").map((value) => `<option value="${escapeHtml(value)}" ${operatorTerm === value ? "selected" : ""}>${escapeHtml(value)}</option>`).join("")}</select>` : ""}
        ${showFilters && filterConfig.mostrar_carteira ? `<select data-tool-wallet title="Filtrar por carteira"><option value="">Todas as carteiras</option>${uniqueFilterValues("CARTEIRA").map((value) => `<option value="${escapeHtml(value)}" ${walletTerm === value ? "selected" : ""}>${escapeHtml(value)}</option>`).join("")}</select>` : ""}
        ${showFilters ? customFilterFields.map((field) => `<select data-tool-field-filter="${escapeHtml(field.chave)}" title="Filtrar por ${escapeHtml(field.nome)}"><option value="">${escapeHtml(field.nome)}: todos</option>${uniqueFilterValues(field.chave).map((value) => `<option value="${escapeHtml(value)}" ${fieldFilterTerms[field.chave] === value ? "selected" : ""}>${escapeHtml(value)}</option>`).join("")}</select>`).join("") : ""}
        ${showFilters && filterConfig.mostrar_ordenacao ? `<select data-tool-sort title="Ordenar registros"><option value="newest" ${sortTerm === "newest" ? "selected" : ""}>Mais recentes</option><option value="oldest" ${sortTerm === "oldest" ? "selected" : ""}>Mais antigos</option></select>` : ""}
        <button type="button" class="secondary-btn dynamic-tool-clear-filters" data-clear-tool-filters ${hasActiveCommandFilters() ? "" : "hidden"}>Limpar</button>
      </div>
    </div>` : ""}
    ${isDashboard ? '<div class="dynamic-tool-dashboard" data-tool-dashboard></div>' : isSpreadsheet ? '<div class="dynamic-tool-grid" data-tool-grid></div>' : '<div class="dynamic-tool-record-list" data-tool-list></div>'}
  `;
  host.querySelector("[data-new-record]")?.addEventListener("click", () => openRecordForm());
  host.querySelector("[data-refresh-tool]")?.addEventListener("click", (event) => refreshDynamicToolRecords(event.currentTarget));
  host.querySelector("[data-export-tool]")?.addEventListener("click", () => {
    const link = document.createElement("a");
    link.href = `/api/ferramentas/${encodeURIComponent(activeDefinition.slug)}/relatorio.csv`;
    link.download = `relatorio_${activeDefinition.slug}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  });
  host.querySelector("[data-clear-tool-filters]")?.addEventListener("click", () => {
    clearCommandFilters();
    renderTool();
  });
  host.querySelector("[data-focus-tool]")?.addEventListener("click", () => setFocusMode(!host.classList.contains("dynamic-tool-focus")));
  host.querySelector("[data-tool-search]")?.addEventListener("input", (event) => {
    searchTerm = event.target.value;
    renderRecords();
  });
  host.querySelector("[data-tool-date]")?.addEventListener("change", (event) => {
    dateTerm = event.target.value;
    renderRecords();
  });
  [["[data-tool-date-from]", (value) => { dateFromTerm = value; }], ["[data-tool-date-to]", (value) => { dateToTerm = value; }], ["[data-tool-deadline]", (value) => { deadlineTerm = value; }]].forEach(([selector, setter]) => {
    host.querySelector(selector)?.addEventListener("change", (event) => {
      setter(event.target.value);
      renderRecords();
    });
  });
  host.querySelectorAll("[data-tool-deadline-option]").forEach((button) => button.addEventListener("click", () => {
    deadlineTerm = button.dataset.toolDeadlineOption || "";
    renderTool();
  }));
  [["[data-tool-operator]", (value) => { operatorTerm = value; }], ["[data-tool-wallet]", (value) => { walletTerm = value; }], ["[data-tool-sort]", (value) => { sortTerm = value; }]].forEach(([selector, setter]) => {
    host.querySelector(selector)?.addEventListener("change", (event) => {
      setter(event.target.value);
      renderRecords();
    });
  });
  host.querySelectorAll("[data-tool-field-filter]").forEach((select) => select.addEventListener("change", (event) => {
    fieldFilterTerms = { ...fieldFilterTerms, [event.currentTarget.dataset.toolFieldFilter]: event.currentTarget.value };
    renderRecords();
  }));
  host.querySelectorAll("[data-screen-mode]").forEach((button) => button.addEventListener("click", () => {
    screenHistoryMode = button.dataset.screenMode === "history";
    renderTool();
  }));
  host.querySelector("[data-tool-grid]")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-record-details]");
    if (!button) return;
    event.stopPropagation();
    openRecordDetails(button.dataset.recordDetails).catch((error) => window.alert(error.message));
  });
  renderScreenNavigation();
  renderStatusNavigation();
  renderMetrics();
  if (isDashboard) renderDashboard();
  else if (isSpreadsheet) renderRecords();
  else renderScreenRecords();
}

async function refreshDynamicToolRecords(button = null) {
  if (!activeDefinition?.slug) return;
  const originalLabel = button?.innerHTML || "";
  if (button) {
    button.disabled = true;
    button.innerHTML = "Atualizando...";
  }
  try {
    records = (await apiGet(`/api/ferramentas/${activeDefinition.slug}/registros?_=${Date.now()}`)).items || [];
    lastLoadedAt = new Date();
    renderTool();
  } catch (error) {
    if (button) {
      button.disabled = false;
      button.innerHTML = originalLabel;
      button.title = error.message || "Nao foi possivel atualizar os registros.";
    }
  }
}

export async function loadDynamicToolDefinitions() {
  const data = await apiGet("/api/ferramentas");
  definitions = data.items || [];
  return definitions;
}

export async function loadDynamicTool(slug) {
  if (activeDefinition?.slug !== slug) {
    activeStatus = "";
    searchTerm = "";
    dateTerm = "";
    dateFromTerm = "";
    dateToTerm = "";
    deadlineTerm = "";
    operatorTerm = "";
    walletTerm = "";
    sortTerm = "newest";
    fieldFilterTerms = {};
    activeScreenId = "";
    screenHistoryMode = false;
  }
  setFocusMode(false);
  activeDefinition = definitions.find((item) => item.slug === slug);
  if (!activeDefinition) {
    activeDefinition = (await apiGet(`/api/ferramentas/${slug}`)).item;
  }
  records = (await apiGet(`/api/ferramentas/${slug}/registros`)).items || [];
  lastLoadedAt = new Date();
  renderTool();
}
