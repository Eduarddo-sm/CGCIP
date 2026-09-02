import { api } from "../core/api.js";
import { removeCache } from "../core/cache.js";
import { $ } from "../core/dom.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { saveNavigationState } from "../core/navigationPersistence.js";
import { state } from "../core/state.js";
import { toast } from "../core/toast.js";
import { closeDialog } from "../layout/dialogs.js";
import { syncCarteiraSelects } from "./carteiraOptions.js";
import { formatDateTime, formatFileSize, pageLabel, pageName, roleLabel, toolLabels } from "./configuracaoSupport.js";
import { loadDynamicToolsAdmin } from "./ferramentaBuilder.js?v=20260812-multi-field-condition-1";

const configUsersView = {
  tab: "all",
  search: "",
  role: "",
  wallet: "",
  status: "",
};

let configUserMenu = null;
const backupView = {
  search: "",
  source: "",
  period: "",
  data: null,
  verified: new Map(),
};

const configPermissionsView = {
  section: "roles",
  search: "",
  module: "",
  state: "",
  view: "matrix",
  profile: "gerencial",
  collapsedGroups: new Set(),
  savedRoles: null,
  draftRoles: null,
  dirty: false,
};

const permissionGroupDefinitions = [
  { key: "monitoramento", label: "Monitoramento", matches: ["monitoramento_", "delete_agreements"] },
  { key: "pareceres", label: "Pareceres", matches: ["parecer_", "approve_parecer"] },
  { key: "protocolos", label: "Protocolos", matches: ["protocolo_"] },
  { key: "colchao", label: "Colchao", matches: ["colchao_"] },
  { key: "auditoria", label: "Auditoria", matches: ["view_audit"] },
  { key: "schemas", label: "Carteiras e schemas", matches: ["view_schema_versions", "edit_schema"] },
  { key: "usuarios", label: "Usuarios e acessos", matches: ["manage_users"] },
  { key: "backups", label: "Backups e recuperacao", matches: ["manage_backups", "restore_backup"] },
];

function setText(selector, value) {
  const element = $(selector);
  if (element) element.textContent = value;
}

export async function loadConfigUsers() {
  const target = $("#configUsersList");
  if (!target) return;
  target.innerHTML = `<div class="empty-overview">Carregando usuarios...</div>`;
  try {
    const payload = await api("/api/config/users");
    state.configUsers = {
      gerencial: payload.gerencial || [],
      negociadores: payload.negociadores || [],
    };
    syncCarteiraSelects();
    renderConfigUsers();
  } catch (error) {
    target.innerHTML = `<div class="empty-overview">${escapeHtml(error.message || "Nao foi possivel carregar usuarios.")}</div>`;
  }
}

export async function showConfigPage(page = state.configPage || "usuarios") {
  state.configPage = allowedConfigPage(page);
  renderConfigPageShell();
  saveNavigationState();
  if (state.configPage === "usuarios") return loadConfigUsers();
  if (state.configPage === "auditoria") return loadConfigAudit();
  if (state.configPage === "permissoes") return loadConfigPermissions();
  if (state.configPage === "schemas") return loadConfigSchemaVersions();
  if (state.configPage === "ferramentas") return loadDynamicToolsAdmin();
  if (state.configPage === "backups") return loadConfigBackups();
  if (state.configPage === "diagnostico") return loadConfigDiagnostic();
}

export function renderConfigPageShell() {
  const page = allowedConfigPage(state.configPage || "usuarios");
  state.configPage = page;
  const meta = {
    usuarios: ["Usuários", "Gerencie acessos gerenciais e negociais sem alterar os dados operacionais."],
    auditoria: ["Auditoria", "Consulte eventos recentes, responsáveis e alterações registradas."],
    permissoes: ["Permissões", "Configure o que cada perfil pode consultar ou executar."],
    schemas: ["Versões de schema", "Acompanhe a evolução estrutural das carteiras negociais."],
    backups: ["Backups e restore", "Crie, consulte e restaure snapshots do banco de dados."],
    diagnostico: ["Diagnóstico", "Verifique serviços, banco, versões e estado técnico do sistema."],
  };
  meta.ferramentas = ["Ferramentas negociais", "Crie e publique fluxos dinamicos para o sistema negocial."];
  const [title, subtitle] = meta[page] || meta.usuarios;
  $("#configPageTitle").textContent = title;
  $("#configPageSubtitle").textContent = subtitle;
  document.querySelectorAll("[data-config-page]").forEach((button) => {
    button.classList.toggle("hidden", !canOpenConfigPage(button.dataset.configPage || ""));
    button.classList.toggle("active", button.dataset.configPage === page);
  });
  ["Users", "Audit", "Permission", "Schema", "Tool", "Backup", "Diagnostic"].forEach((name) => {
    $(`#config${name}Actions`)?.classList.toggle("hidden", name.toLowerCase() !== pageLabel(page));
  });
  document.querySelectorAll(".config-page").forEach((section) => {
    section.classList.toggle("hidden", section.id !== `config${pageName(page)}Page`);
  });
}

export async function loadConfigAudit() {
  const target = $("#configAuditList");
  if (!target) return;
  target.innerHTML = `<div class="empty-overview">Carregando auditoria...</div>`;
  try {
    const payload = await api(`/api/auditoria/geral?${auditQueryString()}`);
    renderConfigAudit(payload.items || []);
  } catch (error) {
    target.innerHTML = `<div class="empty-overview">${escapeHtml(error.message || "Nao foi possivel carregar auditoria.")}</div>`;
  }
}

export function exportConfigAudit(format) {
  const ext = format === "xlsx" ? "xlsx" : "csv";
  window.location.href = `/api/auditoria/geral.${ext}?${auditQueryString(2000)}`;
}

function auditQueryString(limit = 500) {
  const params = new URLSearchParams({ limit: String(limit) });
  const mapping = {
    configAuditSearch: "q",
    configAuditActor: "actor",
    configAuditAction: "action",
    configAuditEntity: "entity_type",
    configAuditOutcome: "outcome",
    configAuditFrom: "date_from",
    configAuditTo: "date_to",
  };
  Object.entries(mapping).forEach(([id, key]) => {
    const value = String($(`#${id}`)?.value || "").trim();
    if (value) params.set(key, value);
  });
  return params.toString();
}

export async function loadConfigPermissions() {
  const target = $("#configPermissionsMatrix");
  if (!target) return;
  if (configPermissionsView.dirty && !window.confirm("Descartar as alteracoes de permissoes ainda nao salvas?")) return;
  target.innerHTML = `<div class="empty-overview">Carregando permissões...</div>`;
  try {
    const [payload, usersPayload] = await Promise.all([
      api("/api/config/permissoes"),
      api("/api/config/permissoes/usuarios"),
    ]);
    state.configPermissions = {
      permissions: payload.permissions || {},
      roles: payload.roles || {},
    };
    configPermissionsView.savedRoles = clonePermissionRoles(state.configPermissions.roles);
    configPermissionsView.draftRoles = clonePermissionRoles(state.configPermissions.roles);
    configPermissionsView.dirty = false;
    state.configUserPermissions = {
      permissions: usersPayload.permissions || {},
      users: usersPayload.users || [],
    };
    renderConfigPermissions();
    renderConfigUserPermissionSelect();
  } catch (error) {
    target.innerHTML = `<div class="empty-overview">${escapeHtml(error.message || "Nao foi possivel carregar permissoes.")}</div>`;
  }
}

export async function saveConfigPermissions() {
  const roles = clonePermissionRoles(configPermissionsView.draftRoles || state.configPermissions?.roles || {});
  try {
    const payload = await api("/api/config/permissoes", {
      method: "POST",
      body: JSON.stringify({ roles }),
    });
    state.configPermissions = {
      permissions: payload.permissions || {},
      roles: payload.roles || {},
    };
    configPermissionsView.savedRoles = clonePermissionRoles(state.configPermissions.roles);
    configPermissionsView.draftRoles = clonePermissionRoles(state.configPermissions.roles);
    configPermissionsView.dirty = false;
    renderConfigPermissions();
    renderConfigUserPermissions();
    toast("Permissões atualizadas.");
  } catch (error) {
    toast(error.message || "Nao foi possivel salvar permissoes.");
  }
}

export async function saveConfigUserPermissions() {
  const select = $("#configUserPermissionSelect");
  const userId = select?.value || "";
  if (!userId) {
    toast("Selecione um usuário.");
    return;
  }
  const overrides = {};
  document.querySelectorAll("[data-user-permission-key]").forEach((input) => {
    const value = input.value;
    if (value === "inherit") return;
    overrides[input.dataset.userPermissionKey] = value === "allow";
  });
  try {
    const payload = await api("/api/config/permissoes/usuarios", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, overrides }),
    });
    const index = state.configUserPermissions.users.findIndex((item) => String(item.id) === String(userId));
    if (index >= 0) state.configUserPermissions.users[index] = payload.user;
    renderConfigUserPermissions();
    toast("Exceções do usuário atualizadas.");
  } catch (error) {
    toast(error.message || "Nao foi possivel salvar exceções.");
  }
}

export async function loadConfigDiagnostic() {
  const target = $("#configDiagnosticPanel");
  if (!target) return;
  target.innerHTML = `<div class="empty-overview">Carregando diagnóstico...</div>`;
  try {
    const [diagnostic, monitoring, status, performance, alerts] = await Promise.all([
      api("/api/diagnostico"),
      api("/api/database/monitoring"),
      api("/api/database/monitoring/status"),
      api("/api/database/performance"),
      api("/api/database/alerts?status=active"),
    ]);
    state.configDiagnostic = { ...diagnostic, monitoring, status, performance, alerts };
    renderConfigDiagnostic();
  } catch (error) {
    target.innerHTML = `<div class="empty-overview">${escapeHtml(error.message || "Nao foi possivel carregar diagnostico.")}</div>`;
  }
}

export async function collectDatabaseMonitoring() {
  const button = $("#collectDatabaseMonitoringBtn");
  if (button) button.disabled = true;
  try {
    await api("/api/database/monitoring/collect", { method: "POST", body: "{}" });
    toast("Métricas do banco atualizadas.");
    await loadConfigDiagnostic();
  } catch (error) {
    toast(error.message || "Nao foi possivel coletar as métricas.");
  } finally {
    if (button) button.disabled = false;
  }
}

export function discardConfigPermissionChanges() {
  if (!configPermissionsView.dirty) return;
  configPermissionsView.draftRoles = clonePermissionRoles(configPermissionsView.savedRoles || state.configPermissions?.roles || {});
  configPermissionsView.dirty = false;
  renderConfigPermissions();
  toast("Alteracoes descartadas.");
}

export function updateConfigPermissionFilters() {
  configPermissionsView.search = String($("#configPermissionSearch")?.value || "").trim().toLocaleLowerCase("pt-BR");
  configPermissionsView.module = String($("#configPermissionModuleFilter")?.value || "");
  configPermissionsView.state = String($("#configPermissionStateFilter")?.value || "");
  configPermissionsView.profile = String($("#configPermissionProfile")?.value || "gerencial");
  renderConfigPermissions();
}

export function setConfigPermissionView(view) {
  configPermissionsView.view = view === "profile" ? "profile" : "matrix";
  renderConfigPermissions();
}

export function setConfigPermissionSection(section) {
  configPermissionsView.section = section === "users" ? "users" : "roles";
  renderConfigPermissionSection();
}

export async function testDatabaseAlert() {
  try {
    await api("/api/database/alerts/test", { method: "POST", body: "{}" });
    toast("Alerta de teste criado.");
    await loadConfigDiagnostic();
  } catch (error) {
    toast(error.message || "Nao foi possivel criar o alerta de teste.");
  }
}

async function acknowledgeDatabaseAlert(id) {
  try {
    await api("/api/database/alerts/acknowledge", {
      method: "POST",
      body: JSON.stringify({ id }),
    });
    toast("Alerta reconhecido.");
    await loadConfigDiagnostic();
  } catch (error) {
    toast(error.message || "Nao foi possivel reconhecer o alerta.");
  }
}

export async function loadConfigSchemaVersions() {
  const select = $("#configSchemaCarteira");
  const target = $("#configSchemaVersionsList");
  const summary = $("#configSchemaSummary");
  if (!target || !summary) return;
  const carteira = select?.value || "";
  if (!carteira) {
    summary.textContent = "Selecione uma carteira para consultar as versões.";
    target.innerHTML = "";
    return;
  }
  target.innerHTML = `<div class="empty-overview">Carregando versões...</div>`;
  try {
    const payload = await api(`/api/carteiras/schema/versions?carteira=${encodeURIComponent(carteira)}`);
    renderConfigSchemaVersions(payload);
  } catch (error) {
    summary.textContent = "Não foi possível carregar as versões.";
    target.innerHTML = `<div class="empty-overview">${escapeHtml(error.message || "Erro ao carregar schema.")}</div>`;
  }
}

export async function loadConfigBackups() {
  const target = $("#databaseBackupList");
  if (!target) return;
  target.innerHTML = `<div class="empty-overview">Carregando backups...</div>`;
  try {
    const [retention, backups, storage, attachmentStorage, defasagemSource] = await Promise.all([
      api("/api/backups/retention"),
      api("/api/backups/database"),
      isAdmin() ? api("/api/backups/storage") : Promise.resolve(null),
      isAdmin() ? api("/api/config/attachments/storage") : Promise.resolve(null),
      isAdmin() ? api("/api/config/defasagem/source") : Promise.resolve(null),
    ]);
    renderConfigBackups(retention, backups, storage, attachmentStorage, defasagemSource);
  } catch (error) {
    target.innerHTML = `<div class="empty-overview">${escapeHtml(error.message || "Nao foi possivel carregar backups.")}</div>`;
  }
}

export async function createDatabaseBackup() {
  const button = $("#createDatabaseBackupBtn");
  const original = button?.textContent || "Criar backup";
  if (button) {
    button.disabled = true;
    button.textContent = "Criando...";
  }
  try {
    await api("/api/backups/database", { method: "POST", body: JSON.stringify({}) });
    toast("Backup criado.");
    await loadConfigBackups();
  } catch (error) {
    toast(error.message || "Nao foi possivel criar backup.");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = original;
    }
  }
}

async function restoreDatabaseBackup(name) {
  if (!name) return;
  const motivo = window.prompt(`Motivo para restaurar o backup ${name}:`);
  if (!motivo) return;
  const confirmacao = window.prompt("Digite CONFIRMAR para restaurar o backup:");
  if (String(confirmacao || "").toUpperCase() !== "CONFIRMAR") return;
  try {
    await api("/api/backups/database/restore", {
      method: "POST",
      body: JSON.stringify({ name, motivo, confirmacao }),
    });
    toast("Backup restaurado. Recarregue a aplica??o para ver o estado restaurado.");
    await loadConfigBackups();
  } catch (error) {
    toast(error.message || "Nao foi possivel restaurar backup.");
  }
}


export function renderConfigUsers() {
  const target = $("#configUsersList");
  if (!target) return;
  const gerencial = state.configUsers?.gerencial || [];
  const negociadores = state.configUsers?.negociadores || [];
  if (!gerencial.length && !negociadores.length) {
    target.innerHTML = `<div class="empty-overview">Nenhum usuario encontrado.</div>`;
    return;
  }
  const users = [
    ...gerencial.map((user) => ({ ...user, source: "gerencial" })),
    ...negociadores.map((user) => ({ ...user, source: "negociador" })),
  ];
  const filtered = filterConfigUsers(users);
  const wallets = [...new Set(negociadores.map((user) => String(user.carteira || "").trim().toUpperCase()).filter(Boolean))].sort();
  const roles = [...new Set(gerencial.map((user) => String(user.role || "").trim().toLowerCase()).filter(Boolean))].sort();
  const inactive = users.filter((user) => !Boolean(user.active)).length;
  const online = users.filter((user) => Boolean(user.active) && Boolean(user.online)).length;

  target.innerHTML = `
    <section class="config-user-kpis" aria-label="Resumo dos usuarios">
      ${userKpi("Total", users.length, "Contas cadastradas", "all")}
      ${userKpi("Gerenciais", gerencial.length, "Gestao e supervisao", "gerencial")}
      ${userKpi("Negociadores", negociadores.length, "Operacao negocial", "negociador")}
      ${userKpi("Online agora", online, "Sessoes ativas", "online", "online")}
      ${userKpi("Desativados", inactive, "Acesso bloqueado", "inactive", inactive ? "inactive" : "")}
    </section>
    <section class="config-user-commandbar">
      <label class="config-user-search">
        <span aria-hidden="true">&#128269;</span>
        <input data-config-user-search value="${escapeAttr(configUsersView.search)}" placeholder="Buscar nome, carteira ou ferramenta" aria-label="Buscar usuarios" />
      </label>
      <select data-config-user-role aria-label="Filtrar por perfil">
        <option value="">Todos os perfis</option>
        ${roles.map((role) => `<option value="${escapeAttr(role)}" ${configUsersView.role === role ? "selected" : ""}>${escapeHtml(roleLabel(role))}</option>`).join("")}
      </select>
      <select data-config-user-wallet aria-label="Filtrar por carteira">
        <option value="">Todas as carteiras</option>
        ${wallets.map((wallet) => `<option value="${escapeAttr(wallet)}" ${configUsersView.wallet === wallet ? "selected" : ""}>${escapeHtml(wallet)}</option>`).join("")}
      </select>
      <select data-config-user-status aria-label="Filtrar por situacao">
        <option value="">Todas as situacoes</option>
        <option value="online" ${configUsersView.status === "online" ? "selected" : ""}>Online</option>
        <option value="offline" ${configUsersView.status === "offline" ? "selected" : ""}>Offline</option>
        <option value="inactive" ${configUsersView.status === "inactive" ? "selected" : ""}>Desativado</option>
      </select>
    </section>
    <div class="config-user-tabs" role="tablist" aria-label="Tipo de usuario">
      ${userTab("all", "Todos", users.length)}
      ${userTab("gerencial", "Gerenciais", gerencial.length)}
      ${userTab("negociador", "Negociadores", negociadores.length)}
      ${userTab("inactive", "Desativados", inactive)}
      <span class="config-user-result-count">${filtered.length} resultado(s)</span>
    </div>
    <div class="config-user-table-wrap">
      <div class="config-user-table" role="table" aria-label="Usuarios do sistema">
        <div class="config-user-table-head" role="row">
          <span role="columnheader">Usuario</span>
          <span role="columnheader">Tipo</span>
          <span role="columnheader">Perfil</span>
          <span role="columnheader">Carteira</span>
          <span role="columnheader">Ultimo acesso</span>
          <span role="columnheader">Status</span>
          <span role="columnheader" aria-label="Acoes"></span>
        </div>
        <div class="config-user-table-body">
          ${filtered.length ? filtered.map(renderUserRow).join("") : `
            <div class="config-user-empty">
              <strong>Nenhum usuario encontrado</strong>
              <span>Ajuste a busca ou remova algum filtro.</span>
            </div>
          `}
        </div>
      </div>
    </div>
  `;
  bindConfigUserControls(target);
}

export async function saveBackupStorage() {
  if (!isAdmin()) return;
  const button = $("#saveBackupStorageBtn");
  const original = button?.textContent || "Salvar local";
  if (button) {
    button.disabled = true;
    button.textContent = "Validando...";
  }
  try {
    const payload = await api("/api/backups/storage", {
      method: "POST",
      body: JSON.stringify({
        path: $("#backupStoragePath")?.value || "",
        migrate_existing: Boolean($("#migrateExistingBackups")?.checked),
      }),
    });
    toast(payload.moved_backups ? `${payload.moved_backups} backup(s) movido(s).` : "Local dos backups atualizado.");
    toggleBackupStorageEditor(false);
    await loadConfigBackups();
  } catch (error) {
    toast(error.message || "Nao foi possivel atualizar o local dos backups.");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = original;
    }
  }
}

export function toggleBackupStorageEditor(editing) {
  $("#backupStorageEditor")?.classList.toggle("hidden", !editing);
  $("#editBackupStorageBtn")?.classList.toggle("hidden", editing);
  if (editing) {
    const input = $("#backupStoragePath");
    input?.focus();
    input?.select();
  }
}

export async function saveAttachmentStorage() {
  if (!isAdmin()) return;
  const button = $("#saveAttachmentStorageBtn");
  const original = button?.textContent || "Salvar local";
  if (button) {
    button.disabled = true;
    button.textContent = "Validando...";
  }
  try {
    const payload = await api("/api/config/attachments/storage", {
      method: "POST",
      body: JSON.stringify({
        path: $("#attachmentStoragePath")?.value || "",
        migrate_existing: Boolean($("#migrateExistingAttachments")?.checked),
      }),
    });
    const moved = Number(payload.moved_attachments || 0);
    toast(moved ? `${moved} anexo(s) movido(s).` : "Local dos anexos atualizado.");
    toggleAttachmentStorageEditor(false);
    await loadConfigBackups();
  } catch (error) {
    toast(error.message || "Nao foi possivel atualizar o local dos anexos.");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = original;
    }
  }
}

export function toggleAttachmentStorageEditor(editing) {
  $("#attachmentStorageEditor")?.classList.toggle("hidden", !editing);
  $("#editAttachmentStorageBtn")?.classList.toggle("hidden", editing);
  if (editing) {
    const input = $("#attachmentStoragePath");
    input?.focus();
    input?.select();
  }
}

export async function saveDefasagemSource() {
  if (!isAdmin()) return;
  const button = $("#saveDefasagemSourceBtn");
  const original = button?.textContent || "Salvar origem";
  if (button) {
    button.disabled = true;
    button.textContent = "Validando...";
  }
  try {
    await api("/api/config/defasagem/source", {
      method: "POST",
      body: JSON.stringify({ path: $("#defasagemSourcePath")?.value || "" }),
    });
    toast("Origem das planilhas da Defasagem atualizada.");
    toggleDefasagemSourceEditor(false);
    await loadConfigBackups();
  } catch (error) {
    toast(error.message || "Nao foi possivel atualizar a origem da Defasagem.");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = original;
    }
  }
}

export function toggleDefasagemSourceEditor(editing) {
  $("#defasagemSourceEditor")?.classList.toggle("hidden", !editing);
  $("#editDefasagemSourceBtn")?.classList.toggle("hidden", editing);
  if (editing) {
    const input = $("#defasagemSourcePath");
    input?.focus();
    input?.select();
  }
}

export function applyBackupFilters() {
  backupView.search = String($("#backupSearchInput")?.value || "").trim().toLocaleLowerCase("pt-BR");
  backupView.source = String($("#backupSourceFilter")?.value || "");
  backupView.period = String($("#backupPeriodFilter")?.value || "");
  renderBackupList();
}

function userKpi(label, value, description, filter, tone = "") {
  return `
    <button class="config-user-kpi ${tone ? `is-${tone}` : ""}" type="button" data-config-user-kpi="${escapeAttr(filter)}">
      <span>${escapeHtml(label)}</span>
      <strong>${Number(value || 0).toLocaleString("pt-BR")}</strong>
      <small>${escapeHtml(description)}</small>
    </button>
  `;
}

function userTab(value, label, count) {
  return `
    <button class="${configUsersView.tab === value ? "active" : ""}" type="button" role="tab" aria-selected="${configUsersView.tab === value}" data-config-user-tab="${escapeAttr(value)}">
      ${escapeHtml(label)} <span>${Number(count || 0).toLocaleString("pt-BR")}</span>
    </button>
  `;
}

function filterConfigUsers(users) {
  const query = configUsersView.search.trim().toLocaleLowerCase("pt-BR");
  return users.filter((user) => {
    const active = Boolean(user.active);
    const online = active && Boolean(user.online);
    if (configUsersView.tab === "gerencial" && user.source !== "gerencial") return false;
    if (configUsersView.tab === "negociador" && user.source !== "negociador") return false;
    if (configUsersView.tab === "inactive" && active) return false;
    if (configUsersView.role && String(user.role || "").toLowerCase() !== configUsersView.role) return false;
    if (configUsersView.wallet && String(user.carteira || "").toUpperCase() !== configUsersView.wallet) return false;
    if (configUsersView.status === "online" && !online) return false;
    if (configUsersView.status === "offline" && (!active || online)) return false;
    if (configUsersView.status === "inactive" && active) return false;
    if (!query) return true;
    const searchable = [
      user.username,
      user.role,
      user.carteira,
      user.source,
      ...toolLabels(user.enabled_tools),
    ].join(" ").toLocaleLowerCase("pt-BR");
    return searchable.includes(query);
  }).sort((a, b) => String(a.username || "").localeCompare(String(b.username || ""), "pt-BR"));
}

function renderUserRow(user) {
  const isCurrent = user.source === "gerencial" && String(user.id) === String(state.user?.id);
  const active = Boolean(user.active);
  const online = active && Boolean(user.online);
  const status = !active ? "Desativado" : online ? "Online" : "Offline";
  const statusClass = !active ? "inactive" : online ? "online" : "offline";
  const profile = user.source === "negociador" ? "Negociador" : roleLabel(user.role);
  const type = user.source === "negociador" ? "Negocial" : "Gerencial";
  return `
    <article class="config-user-row ${active ? "" : "is-inactive"}" role="row" data-config-user-source="${escapeAttr(user.source)}">
      <div class="config-user-identity" role="cell">
        <span class="config-user-avatar">${escapeHtml(userInitials(user.username))}</span>
        <span><strong>${escapeHtml(user.username || "-")}</strong>${isCurrent ? "<small>Voce</small>" : ""}</span>
      </div>
      <span class="config-user-type" role="cell">${escapeHtml(type)}</span>
      <span role="cell">${escapeHtml(profile)}</span>
      <span role="cell">${escapeHtml(user.source === "negociador" ? (user.carteira || "Sem carteira") : "-")}</span>
      <span class="config-user-last-access" role="cell">${escapeHtml(lastAccessLabel(user))}</span>
      <span role="cell"><i class="config-user-status is-${statusClass}"><b></b>${escapeHtml(status)}</i></span>
      <button class="config-user-more" type="button" data-config-user-menu data-user-source="${escapeAttr(user.source)}" data-user-id="${escapeAttr(user.id)}" aria-label="Acoes de ${escapeAttr(user.username)}" title="Acoes">&#8943;</button>
    </article>
  `;
}

function userInitials(username) {
  const parts = String(username || "U").split(/[.\s_-]+/).filter(Boolean);
  return parts.slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "U";
}

function lastAccessLabel(user) {
  if (user.online) return "Agora";
  const value = user.last_access_at || user.last_login_at;
  return value ? formatDateTime(value) : "Nunca acessou";
}

function bindConfigUserControls(target) {
  target.querySelector("[data-config-user-search]")?.addEventListener("input", (event) => {
    configUsersView.search = event.target.value;
    renderConfigUsers();
    const input = $("[data-config-user-search]");
    input?.focus();
    input?.setSelectionRange(input.value.length, input.value.length);
  });
  target.querySelector("[data-config-user-role]")?.addEventListener("change", (event) => {
    configUsersView.role = event.target.value;
    renderConfigUsers();
  });
  target.querySelector("[data-config-user-wallet]")?.addEventListener("change", (event) => {
    configUsersView.wallet = event.target.value;
    renderConfigUsers();
  });
  target.querySelector("[data-config-user-status]")?.addEventListener("change", (event) => {
    configUsersView.status = event.target.value;
    renderConfigUsers();
  });
  target.querySelectorAll("[data-config-user-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      configUsersView.tab = button.dataset.configUserTab;
      renderConfigUsers();
    });
  });
  target.querySelectorAll("[data-config-user-kpi]").forEach((button) => {
    button.addEventListener("click", () => {
      const filter = button.dataset.configUserKpi;
      if (filter === "all") {
        Object.assign(configUsersView, { tab: "all", search: "", role: "", wallet: "", status: "" });
      } else if (["gerencial", "negociador", "inactive"].includes(filter)) {
        configUsersView.tab = filter;
        configUsersView.status = filter === "inactive" ? "inactive" : "";
      } else if (filter === "online") {
        configUsersView.tab = "all";
        configUsersView.status = configUsersView.status === "online" ? "" : "online";
      }
      renderConfigUsers();
    });
  });
  target.querySelectorAll("[data-config-user-menu]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openConfigUserMenu(button);
    });
  });
}

function openConfigUserMenu(anchor) {
  closeConfigUserMenu();
  const source = anchor.dataset.userSource;
  const userId = anchor.dataset.userId;
  const user = findUser(source, userId);
  if (!user) return;
  const isCurrent = source === "gerencial" && String(user.id) === String(state.user?.id);
  const targetRole = String(user.role || "").toLowerCase();
  const protectedAdmin = source === "gerencial" && ["admin", "superadmin"].includes(targetRole) && !isSuperAdmin();
  const menu = document.createElement("div");
  menu.className = "config-user-popover";
  menu.innerHTML = `
    ${(source === "negociador" || (source === "gerencial" && isSuperAdmin())) ? `<button type="button" data-menu-edit>Editar usuario</button>` : ""}
    <button type="button" data-menu-toggle ${(isCurrent || protectedAdmin) ? "disabled" : ""}>${user.active ? "Desativar acesso" : "Reativar acesso"}</button>
    <span></span>
    <button class="danger" type="button" data-menu-delete ${(isCurrent || protectedAdmin) ? "disabled" : ""}>Excluir login</button>
  `;
  document.body.appendChild(menu);
  const rect = anchor.getBoundingClientRect();
  const menuWidth = 190;
  menu.style.left = `${Math.max(8, Math.min(window.innerWidth - menuWidth - 8, rect.right - menuWidth))}px`;
  menu.style.top = `${Math.min(window.innerHeight - menu.offsetHeight - 8, rect.bottom + 5)}px`;
  menu.querySelector("[data-menu-edit]")?.addEventListener("click", () => {
    closeConfigUserMenu();
    openEditConfigUserDialog(source, userId);
  });
  menu.querySelector("[data-menu-toggle]")?.addEventListener("click", () => {
    closeConfigUserMenu();
    toggleConfigUser(source, userId);
  });
  menu.querySelector("[data-menu-delete]")?.addEventListener("click", () => {
    closeConfigUserMenu();
    deleteConfigUser(source, userId);
  });
  configUserMenu = menu;
  document.addEventListener("keydown", closeConfigUserMenuOnEscape);
  setTimeout(() => document.addEventListener("click", closeConfigUserMenu, { once: true }), 0);
}

function closeConfigUserMenu() {
  configUserMenu?.remove();
  configUserMenu = null;
  document.removeEventListener("keydown", closeConfigUserMenuOnEscape);
}

function closeConfigUserMenuOnEscape(event) {
  if (event.key === "Escape") closeConfigUserMenu();
}

function renderConfigAudit(events) {
  const target = $("#configAuditList");
  if (!target) return;
  const users = new Set(events.map((event) => event.actor || "").filter(Boolean));
  $("#configAuditTotal").textContent = String(events.length);
  $("#configAuditLast").textContent = events[0]?.created_at ? formatDateTime(events[0].created_at) : "-";
  $("#configAuditUsers").textContent = String(users.size);
  if (!events.length) {
    target.innerHTML = `<div class="empty-overview">Nenhum evento encontrado.</div>`;
    return;
  }
  target.innerHTML = `
    <table class="config-table">
      <thead>
        <tr>
          <th>Data/Hora</th>
          <th>Usuário</th>
          <th>Ação</th>
          <th>Entidade</th>
          <th>Resultado</th>
          <th>Detalhes</th>
        </tr>
      </thead>
      <tbody>
        ${events.map((event) => {
          return `
            <tr>
              <td>${escapeHtml(formatDateTime(event.created_at))}</td>
              <td>${escapeHtml(event.actor || "Sistema")}</td>
              <td><span class="status-chip">${escapeHtml(eventTypeLabel(event.action))}</span></td>
              <td>${escapeHtml([event.entity_type, event.entity_label || event.entity_id].filter(Boolean).join(" - ") || "-")}</td>
              <td>${escapeHtml(event.outcome || "success")}</td>
              <td>${escapeHtml(shortDetails(event.details))}</td>
            </tr>
          `;
        }).join("")}
      </tbody>
    </table>
  `;
}

function renderConfigPermissions() {
  const target = $("#configPermissionsMatrix");
  if (!target) return;
  const permissions = state.configPermissions?.permissions || {};
  const permissionKeys = Object.keys(permissions);
  if (!permissionKeys.length) {
    target.innerHTML = `<div class="empty-overview">Nenhuma permiss&atilde;o configurada.</div>`;
    return;
  }
  if (!configPermissionsView.draftRoles) {
    configPermissionsView.savedRoles = clonePermissionRoles(state.configPermissions?.roles || {});
    configPermissionsView.draftRoles = clonePermissionRoles(state.configPermissions?.roles || {});
  }
  const roles = configPermissionsView.draftRoles;
  const roleKeys = ["superadmin", "admin", "gerencial", "supervisor"];
  const roleLabels = { superadmin: "Superadmin", admin: "Admin", gerencial: "Gerencial", supervisor: "Supervisor" };

  syncPermissionToolbar(permissionKeys);
  renderConfigPermissionSection();
  renderPermissionSummary(permissionKeys);
  const groups = groupPermissions(permissionKeys).filter((group) => {
    if (configPermissionsView.module && group.key !== configPermissionsView.module) return false;
    return group.permissions.some((permission) => permissionMatchesFilters(permission, permissions, roles));
  }).map((group) => ({
    ...group,
    permissions: group.permissions.filter((permission) => permissionMatchesFilters(permission, permissions, roles)),
  }));
  const visibleRoles = configPermissionsView.view === "profile" ? [configPermissionsView.profile] : roleKeys;

  target.innerHTML = groups.length ? groups.map((group) => {
    const collapsed = !configPermissionsView.search && configPermissionsView.collapsedGroups.has(group.key);
    return `
      <section class="config-permission-group ${collapsed ? "is-collapsed" : ""}" data-permission-group="${escapeAttr(group.key)}">
        <header>
          <button class="config-permission-group-toggle" type="button" data-toggle-permission-group="${escapeAttr(group.key)}" aria-expanded="${collapsed ? "false" : "true"}">
            <span class="config-permission-chevron" aria-hidden="true">&#9662;</span>
            <strong>${escapeHtml(group.label)}</strong>
            <small>${group.permissions.length} permiss&atilde;o(&otilde;es)</small>
          </button>
          <div class="config-permission-bulk-actions">
            <button type="button" data-permission-bulk="allow" data-permission-group-key="${escapeAttr(group.key)}" data-permission-bulk-role="gerencial" title="Permitir o m&oacute;dulo para Gerencial">Gerencial: permitir</button>
            <button type="button" data-permission-bulk="allow" data-permission-group-key="${escapeAttr(group.key)}" data-permission-bulk-role="supervisor" title="Permitir o m&oacute;dulo para Supervisor">Supervisor: permitir</button>
            <button type="button" data-permission-bulk="reset" data-permission-group-key="${escapeAttr(group.key)}" title="Desfazer altera&ccedil;&otilde;es deste m&oacute;dulo">Restaurar</button>
          </div>
        </header>
        <div class="config-permission-group-body">
          <table class="config-table permission-matrix">
            <thead><tr><th>Permiss&atilde;o</th>${visibleRoles.map((role) => `<th>${escapeHtml(roleLabels[role])}</th>`).join("")}</tr></thead>
            <tbody>${group.permissions.map((permission) => permissionRow(permission, permissions[permission], visibleRoles, roles)).join("")}</tbody>
          </table>
        </div>
      </section>`;
  }).join("") : `<div class="config-permissions-empty">Nenhuma permiss&atilde;o corresponde aos filtros aplicados.</div>`;

  target.querySelectorAll("[data-permission-role]").forEach((input) => {
    input.addEventListener("change", () => {
      const role = input.dataset.permissionRole;
      const permission = input.dataset.permissionKey;
      configPermissionsView.draftRoles[role] ||= {};
      configPermissionsView.draftRoles[role][permission] = input.checked;
      const stateLabel = input.closest(".permission-toggle")?.querySelector("em");
      if (stateLabel) stateLabel.textContent = input.checked ? "Permitido" : "Bloqueado";
      updatePermissionDirtyState();
      renderPermissionSummary(permissionKeys);
      if (configPermissionsView.state) renderConfigPermissions();
    });
  });
  target.querySelectorAll("[data-toggle-permission-group]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.togglePermissionGroup;
      if (configPermissionsView.collapsedGroups.has(key)) configPermissionsView.collapsedGroups.delete(key);
      else configPermissionsView.collapsedGroups.add(key);
      renderConfigPermissions();
    });
  });
  target.querySelectorAll("[data-permission-bulk]").forEach((button) => {
    button.addEventListener("click", () => applyPermissionBulkAction(button));
  });
  updatePermissionDirtyState();
}

function clonePermissionRoles(roles) {
  return Object.fromEntries(Object.entries(roles || {}).map(([role, values]) => [role, { ...(values || {}) }]));
}

function permissionGroupFor(permission) {
  return permissionGroupDefinitions.find((group) => group.matches.some((match) => permission === match || permission.startsWith(match)))
    || { key: "outros", label: "Outras permissoes", matches: [] };
}

function groupPermissions(permissionKeys) {
  const grouped = new Map();
  permissionKeys.forEach((permission) => {
    const definition = permissionGroupFor(permission);
    if (!grouped.has(definition.key)) grouped.set(definition.key, { key: definition.key, label: definition.label, permissions: [] });
    grouped.get(definition.key).permissions.push(permission);
  });
  const order = [...permissionGroupDefinitions.map((group) => group.key), "outros"];
  return [...grouped.values()].sort((left, right) => order.indexOf(left.key) - order.indexOf(right.key));
}

function permissionMatchesFilters(permission, labels, roles) {
  const searchable = `${labels[permission] || ""} ${permission}`.toLocaleLowerCase("pt-BR");
  if (configPermissionsView.search && !searchable.includes(configPermissionsView.search)) return false;
  const editableValues = ["gerencial", "supervisor"].map((role) => Boolean(roles?.[role]?.[permission]));
  if (configPermissionsView.state === "allowed" && !editableValues.some(Boolean)) return false;
  if (configPermissionsView.state === "blocked" && editableValues.some(Boolean)) return false;
  return true;
}

function permissionRow(permission, label, visibleRoles, roles) {
  const critical = /^(manage_|restore_|delete_|edit_schema|approve_)/.test(permission);
  return `
    <tr class="${critical ? "is-critical" : ""}">
      <td>
        <div class="config-permission-name"><strong>${escapeHtml(label)}</strong>${critical ? `<span>Cr&iacute;tica</span>` : ""}</div>
        <small>${escapeHtml(permission)}</small>
      </td>
      ${visibleRoles.map((role) => {
        const locked = ["admin", "superadmin"].includes(role);
        const checked = roles?.[role]?.[permission] ? "checked" : "";
        return `<td>
          <label class="permission-toggle ${locked ? "is-locked" : ""}" title="${locked ? "Permissao obrigatoria deste perfil" : "Alterar permissao"}">
            <input type="checkbox" data-permission-role="${escapeAttr(role)}" data-permission-key="${escapeAttr(permission)}" ${checked} ${locked ? "disabled" : ""} />
            <span aria-hidden="true">${locked ? "&#128274;" : ""}</span>
            <em>${locked ? "Fixo" : (checked ? "Permitido" : "Bloqueado")}</em>
          </label>
        </td>`;
      }).join("")}
    </tr>`;
}

function syncPermissionToolbar(permissionKeys) {
  const moduleSelect = $("#configPermissionModuleFilter");
  if (moduleSelect) {
    const groups = groupPermissions(permissionKeys);
    moduleSelect.innerHTML = `<option value="">Todos os m&oacute;dulos</option>${groups.map((group) => `<option value="${escapeAttr(group.key)}">${escapeHtml(group.label)}</option>`).join("")}`;
    moduleSelect.value = configPermissionsView.module;
  }
  const search = $("#configPermissionSearch");
  if (search && search.value !== configPermissionsView.search) search.value = configPermissionsView.search;
  const stateFilter = $("#configPermissionStateFilter");
  if (stateFilter) stateFilter.value = configPermissionsView.state;
  const profile = $("#configPermissionProfile");
  if (profile) {
    profile.value = configPermissionsView.profile;
    profile.classList.toggle("hidden", configPermissionsView.view !== "profile");
  }
  document.querySelectorAll("[data-permission-view]").forEach((button) => button.classList.toggle("active", button.dataset.permissionView === configPermissionsView.view));
}

function renderPermissionSummary(permissionKeys) {
  const target = $("#configPermissionsSummary");
  if (!target) return;
  const roles = configPermissionsView.draftRoles || {};
  const summary = ["gerencial", "supervisor"].map((role) => {
    const allowed = permissionKeys.filter((permission) => roles?.[role]?.[permission]).length;
    return `<span><strong>${role === "gerencial" ? "Gerencial" : "Supervisor"}</strong> ${allowed}/${permissionKeys.length} permitidas</span>`;
  }).join("");
  target.innerHTML = `<span>${permissionKeys.length} permiss&atilde;o(&otilde;es) em ${groupPermissions(permissionKeys).length} m&oacute;dulos</span>${summary}`;
}

function renderConfigPermissionSection() {
  $("#configPermissionRolesSection")?.classList.toggle("hidden", configPermissionsView.section !== "roles");
  $("#configPermissionUsersSection")?.classList.toggle("hidden", configPermissionsView.section !== "users");
  document.querySelectorAll("[data-permission-section]").forEach((button) => button.classList.toggle("active", button.dataset.permissionSection === configPermissionsView.section));
}

function updatePermissionDirtyState() {
  configPermissionsView.dirty = JSON.stringify(configPermissionsView.draftRoles || {}) !== JSON.stringify(configPermissionsView.savedRoles || {});
  $("#configPermissionsDirty")?.classList.toggle("hidden", !configPermissionsView.dirty);
  $("#discardConfigPermissionsBtn")?.classList.toggle("hidden", !configPermissionsView.dirty);
  const saveButton = $("#saveConfigPermissionsBtn");
  if (saveButton) saveButton.disabled = !configPermissionsView.dirty;
}

function applyPermissionBulkAction(button) {
  const group = groupPermissions(Object.keys(state.configPermissions?.permissions || {})).find((item) => item.key === button.dataset.permissionGroupKey);
  if (!group) return;
  const action = button.dataset.permissionBulk;
  const role = button.dataset.permissionBulkRole;
  if (action === "reset") {
    ["gerencial", "supervisor"].forEach((editableRole) => {
      configPermissionsView.draftRoles[editableRole] ||= {};
      group.permissions.forEach((permission) => {
        configPermissionsView.draftRoles[editableRole][permission] = Boolean(configPermissionsView.savedRoles?.[editableRole]?.[permission]);
      });
    });
  } else if (role) {
    configPermissionsView.draftRoles[role] ||= {};
    group.permissions.forEach((permission) => { configPermissionsView.draftRoles[role][permission] = action === "allow"; });
  }
  updatePermissionDirtyState();
  renderConfigPermissions();
}

function renderConfigUserPermissionSelect() {
  const select = $("#configUserPermissionSelect");
  if (!select) return;
  const current = select.value;
  const users = state.configUserPermissions?.users || [];
  select.innerHTML = `<option value="">Selecione um usuário</option>${users.map((user) => (
    `<option value="${escapeAttr(user.id)}">${escapeHtml(user.username)} (${escapeHtml(user.role || "-")})</option>`
  )).join("")}`;
  if (current && users.some((user) => String(user.id) === String(current))) select.value = current;
  renderConfigUserPermissions();
}

export function renderConfigUserPermissions() {
  const target = $("#configUserPermissionsMatrix");
  const select = $("#configUserPermissionSelect");
  if (!target || !select) return;
  const user = (state.configUserPermissions?.users || []).find((item) => String(item.id) === String(select.value));
  const permissions = state.configUserPermissions?.permissions || state.configPermissions?.permissions || {};
  if (!user) {
    target.innerHTML = `<div class="empty-overview">Selecione um usuário para ajustar exceções.</div>`;
    return;
  }
  target.innerHTML = `
    <table class="config-table permission-matrix">
      <thead><tr><th>Permissão</th><th>Regra do perfil</th><th>Exceção</th><th>Efetivo</th></tr></thead>
      <tbody>
        ${Object.keys(permissions).map((permission) => {
          const inherited = Boolean(state.configPermissions?.roles?.[user.role]?.[permission]);
          const override = Object.prototype.hasOwnProperty.call(user.overrides || {}, permission) ? Boolean(user.overrides[permission]) : null;
          const effective = override === null ? inherited : override;
          return `
            <tr>
              <td><strong>${escapeHtml(permissions[permission])}</strong><span>${escapeHtml(permission)}</span></td>
              <td>${inherited ? "Permitir" : "Bloquear"}</td>
              <td>
                <select data-user-permission-key="${escapeAttr(permission)}">
                  <option value="inherit" ${override === null ? "selected" : ""}>Herdar perfil</option>
                  <option value="allow" ${override === true ? "selected" : ""}>Permitir</option>
                  <option value="deny" ${override === false ? "selected" : ""}>Bloquear</option>
                </select>
              </td>
              <td><span class="status-chip ${effective ? "success" : "danger"}">${effective ? "Permitido" : "Bloqueado"}</span></td>
            </tr>
          `;
        }).join("")}
      </tbody>
    </table>
  `;
}

function renderConfigSchemaVersions(payload) {
  const target = $("#configSchemaVersionsList");
  const summary = $("#configSchemaSummary");
  if (!target || !summary) return;
  const versions = payload.items || payload.versions || [];
  const carteira = payload.carteira || {};
  summary.textContent = `${carteira.nome || carteira.slug || "Carteira"} - ${versions.length} versão(ões) registrada(s).`;
  if (!versions.length) {
    target.innerHTML = `<div class="empty-overview">Nenhuma versão registrada para esta carteira.</div>`;
    return;
  }
  target.innerHTML = versions.map((version) => {
    const schema = version.schema || version.schema_json || {};
    const columns = Array.isArray(schema.colunas) ? schema.colunas : Array.isArray(schema.columns) ? schema.columns : [];
    return `
      <article class="config-version-card">
        <div>
          <strong>Versão ${escapeHtml(String(version.version_number || version.versao || "-"))}</strong>
          <span>${escapeHtml(formatDateTime(version.created_at))} - ${escapeHtml(actionLabel(version.action))}</span>
        </div>
        <div class="config-version-columns">
          ${columns.slice(0, 10).map((column) => `<span>${escapeHtml(column.nome || column.chave || column.name || "-")}</span>`).join("")}
          ${columns.length > 10 ? `<span>+${columns.length - 10}</span>` : ""}
        </div>
      </article>
    `;
  }).join("");
}

function renderConfigBackups(retention, backups, storage = null, attachmentStorage = null, defasagemSource = null) {
  const items = backups.items || [];
  const policy = retention.policy || {};
  backupView.data = { retention, backups, storage };
  const latest = items[0] || null;
  const totalBytes = items.reduce((sum, item) => sum + Number(item.size_bytes || 0), 0);
  setText("#backupDailyRetention", String(policy.retention_days || "-"));
  setText("#backupWeeklyRetention", String(policy.keep_latest_per_source || "-"));
  setText("#backupTotal", String(items.length));
  setText("#backupUsedSpace", formatFileSize(totalBytes));
  setText("#backupLastSize", latest ? formatFileSize(latest.size_bytes) : "-");
  setText("#backupLastDate", latest ? formatDateTime(latest.created_at) : "Sem backup");
  setText("#backupLastStatus", latest ? "Disponivel" : "Sem backup");
  const storageSettings = $("#backupStorageSettings");
  storageSettings?.classList.toggle("hidden", !isAdmin());
  if (storage && isAdmin()) {
    const pathInput = $("#backupStoragePath");
    if (pathInput) pathInput.value = storage.path || "";
    setText("#backupStorageDisplay", storage.path || "-");
    setText("#backupStorageStatus", storage.available && storage.writable
      ? `Destino disponivel: ${storage.path}`
      : `Destino indisponivel: ${storage.path}`);
    const health = $("#backupStorageHealth");
    if (health) {
      health.textContent = storage.available && storage.writable ? "Disponivel" : "Indisponivel";
      health.classList.toggle("is-ok", Boolean(storage.available && storage.writable));
      health.classList.toggle("is-error", !storage.available || !storage.writable);
    }
  }
  toggleBackupStorageEditor(false);
  renderAttachmentStorage(attachmentStorage);
  renderDefasagemSource(defasagemSource);
  renderBackupList();
}

function renderDefasagemSource(source) {
  const settings = $("#defasagemSourceSettings");
  settings?.classList.toggle("hidden", !isAdmin());
  if (source && isAdmin()) {
    const input = $("#defasagemSourcePath");
    if (input) input.value = source.path || "";
    setText("#defasagemSourceDisplay", source.path || "-");
    const files = source.files || {};
    const found = [files.contracts, files.guarantees, files.triggers].filter((item) => item?.exists).length;
    const ready = Boolean(source.available && source.readable && files.contracts?.exists);
    setText("#defasagemSourceStatus", ready
      ? `${found} de 3 planilhas encontradas. A base de contratos esta disponivel.`
      : `Origem indisponivel ou sem ${files.contracts?.name || "contratos_ativos.xlsx"}.`);
    const health = $("#defasagemSourceHealth");
    if (health) {
      health.textContent = ready ? "Disponivel" : "Indisponivel";
      health.classList.toggle("is-ok", ready);
      health.classList.toggle("is-error", !ready);
    }
  }
  toggleDefasagemSourceEditor(false);
}

function renderAttachmentStorage(storage) {
  const settings = $("#attachmentStorageSettings");
  settings?.classList.toggle("hidden", !isAdmin());
  if (storage && isAdmin()) {
    const input = $("#attachmentStoragePath");
    if (input) input.value = storage.path || "";
    setText("#attachmentStorageDisplay", storage.path || "-");
    const files = Number(storage.files || 0).toLocaleString("pt-BR");
    const size = formatFileSize(storage.size_bytes || 0);
    const legacy = Array.isArray(storage.legacy_paths) ? storage.legacy_paths.length : 0;
    setText("#attachmentStorageStatus", storage.available && storage.writable
      ? `${files} arquivo(s), ${size}${legacy ? `, ${legacy} destino(s) anterior(es) preservado(s)` : ""}`
      : `Destino indisponivel: ${storage.path || "-"}`);
    const health = $("#attachmentStorageHealth");
    if (health) {
      health.textContent = storage.available && storage.writable ? "Disponivel" : "Indisponivel";
      health.classList.toggle("is-ok", Boolean(storage.available && storage.writable));
      health.classList.toggle("is-error", !storage.available || !storage.writable);
    }
  }
  toggleAttachmentStorageEditor(false);
}

function renderBackupList() {
  const target = $("#databaseBackupList");
  if (!target) return;
  const allItems = backupView.data?.backups?.items || [];
  const now = new Date();
  const items = allItems.filter((item) => {
    if (backupView.search && !String(item.name || "").toLocaleLowerCase("pt-BR").includes(backupView.search)) return false;
    if (backupView.source && backupSource(item) !== backupView.source) return false;
    if (!backupView.period) return true;
    const created = new Date(item.created_at);
    if (Number.isNaN(created.getTime())) return false;
    if (backupView.period === "today") return created.toDateString() === now.toDateString();
    return created >= new Date(now.getTime() - Number(backupView.period) * 86400000);
  });
  setText("#backupHistoryCount", `${items.length} de ${allItems.length} arquivo(s)`);
  if (!items.length) {
    target.innerHTML = `<div class="empty-overview">Nenhum backup encontrado para os filtros aplicados.</div>`;
    return;
  }
  target.innerHTML = items.map((item) => {
    const verification = backupView.verified.get(item.name);
    return `
      <article class="config-backup-row">
        <div class="config-backup-name"><span aria-hidden="true">&#128451;</span><strong title="${escapeAttr(item.name)}">${escapeHtml(item.name)}</strong></div>
        <span class="config-backup-source is-${escapeAttr(backupSource(item))}">${escapeHtml(backupSourceLabel(backupSource(item)))}</span>
        <span>${escapeHtml(formatDateTime(item.created_at))}</span>
        <span>${escapeHtml(formatFileSize(item.size_bytes))}</span>
        <span class="config-backup-integrity ${verification ? "is-verified" : ""}">${verification ? "Verificado" : "Nao verificado"}</span>
        <details class="config-backup-actions">
          <summary aria-label="Acoes do backup" title="Acoes">&#8943;</summary>
          <div>
            <button type="button" data-backup-details="${escapeAttr(item.name)}">Ver detalhes</button>
            <button type="button" data-backup-verify="${escapeAttr(item.name)}">Validar integridade</button>
            <button class="danger" type="button" data-restore-backup="${escapeAttr(item.name)}">Restaurar</button>
          </div>
        </details>
      </article>
    `;
  }).join("");
  target.querySelectorAll("[data-backup-details]").forEach((button) => button.addEventListener("click", () => showBackupDetails(button.dataset.backupDetails)));
  target.querySelectorAll("[data-backup-verify]").forEach((button) => button.addEventListener("click", () => verifyDatabaseBackup(button.dataset.backupVerify, button)));
  target.querySelectorAll("[data-restore-backup]").forEach((button) => button.addEventListener("click", () => restoreDatabaseBackup(button.dataset.restoreBackup)));
}

function backupSource(item) {
  if (item.source) return item.source;
  const name = String(item.name || "").toLowerCase();
  if (name.startsWith("automatico_")) return "automatic";
  if (name.startsWith("pre_restore_")) return "pre_restore";
  return "manual";
}

function backupSourceLabel(source) {
  return { automatic: "Automatico", pre_restore: "Pre-restore", manual: "Manual" }[source] || "Manual";
}

async function verifyDatabaseBackup(name, button) {
  if (!name) return;
  const original = button?.textContent || "Validar integridade";
  if (button) {
    button.disabled = true;
    button.textContent = "Validando...";
  }
  try {
    const result = await api("/api/backups/database/verify", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    backupView.verified.set(name, result);
    renderBackupList();
    toast("Backup validado com sucesso.");
  } catch (error) {
    toast(error.message || "O backup nao passou na validacao.");
  } finally {
    if (button?.isConnected) {
      button.disabled = false;
      button.textContent = original;
    }
  }
}

function showBackupDetails(name) {
  const item = (backupView.data?.backups?.items || []).find((entry) => entry.name === name);
  if (!item) return;
  const verification = backupView.verified.get(name);
  const dialog = document.createElement("dialog");
  dialog.className = "dialog ds-modal config-backup-detail-dialog";
  dialog.innerHTML = `
    <section>
      <header><div><span>Backup do banco</span><h2>${escapeHtml(item.name)}</h2></div><button class="icon-btn" type="button" data-close>&times;</button></header>
      <dl>
        <div><dt>Origem</dt><dd>${escapeHtml(backupSourceLabel(backupSource(item)))}</dd></div>
        <div><dt>Data e hora</dt><dd>${escapeHtml(formatDateTime(item.created_at))}</dd></div>
        <div><dt>Tamanho</dt><dd>${escapeHtml(formatFileSize(item.size_bytes))}</dd></div>
        <div><dt>Integridade</dt><dd>${verification ? "Verificado" : "Nao verificado"}</dd></div>
        <div class="wide"><dt>Arquivo</dt><dd>${escapeHtml(item.path || item.name)}</dd></div>
        ${verification ? `<div class="wide"><dt>SHA-256</dt><dd>${escapeHtml(verification.sha256 || "-")}</dd></div>` : ""}
      </dl>
      <footer><button class="secondary-btn" type="button" data-close>Fechar</button></footer>
    </section>`;
  document.body.appendChild(dialog);
  dialog.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => dialog.close()));
  dialog.addEventListener("close", () => dialog.remove(), { once: true });
  dialog.showModal();
}

function renderConfigDiagnostic() {
  const target = $("#configDiagnosticPanel");
  const payload = state.configDiagnostic || {};
  if (!target) return;
  const snapshot = payload.monitoring?.snapshot || {};
  const database = snapshot.database || {};
  const status = payload.status || {};
  const performance = payload.performance || {};
  const alerts = payload.alerts?.items || [];
  const migrations = Object.fromEntries((performance.migrations || []).map((item) => [item.table_schema, item.version_num]));
  const cards = [
    ["Gerencial", payload.services?.gerencial?.status || "-", `Porta ${payload.services?.gerencial?.port || "-"}`],
    ["Negocial", payload.services?.negocial?.status || "-", `Porta ${payload.services?.negocial?.port || "-"}`],
    ["Heartbeat", status.heartbeat || "-", status.age_seconds == null ? "Sem coleta" : `${status.age_seconds}s desde a coleta`],
    ["Conexões", `${database.total_connections ?? "-"}/${database.max_connections ?? "-"}`, `${database.active_connections ?? "-"} ativas`],
    ["Cache hit", database.cache_hit_percent == null ? "-" : `${database.cache_hit_percent}%`, "Cache do PostgreSQL"],
    ["Tamanho", database.database_size_bytes == null ? "-" : formatFileSize(database.database_size_bytes), "Banco completo"],
  ];
  target.innerHTML = `
    <section class="database-health-head">
      <div>
        <span class="database-health-indicator ${escapeAttr(status.status || "unknown")}"></span>
        <strong>PostgreSQL ${escapeHtml(status.status === "healthy" ? "saudável" : "requer atenção")}</strong>
        <small>Última coleta ${escapeHtml(formatDateTime(snapshot.captured_at))}</small>
      </div>
      <div class="database-version-pills">
        <span>Gerencial ${escapeHtml(migrations.gerencial || "-")}</span>
        <span>Negocial ${escapeHtml(migrations.negocial || "-")}</span>
        <span>pg_stat_statements ${performance.pg_stat_statements?.loaded ? "ativo" : "pendente"}</span>
      </div>
    </section>
    <div class="config-kpi-row diagnostic-grid database-kpis">
      ${cards.map(([title, value, subtitle]) => `
        <article>
          <span>${escapeHtml(title)}</span>
          <strong>${escapeHtml(value)}</strong>
          <small>${escapeHtml(subtitle)}</small>
        </article>
      `).join("")}
    </div>
    <section class="database-diagnostic-section">
      <header><h4>Alertas ativos</h4><span>${alerts.length}</span></header>
      <div class="database-alert-list">
        ${alerts.length ? alerts.map((item) => `
          <article class="database-alert ${escapeAttr(item.severity)}">
            <div><strong>${escapeHtml(item.message)}</strong><small>${escapeHtml(item.alert_type)} · ${escapeHtml(formatDateTime(item.last_seen_at))} · ${item.occurrence_count} ocorrência(s)</small></div>
            ${item.status === "open" ? `<button class="secondary-btn compact" type="button" data-ack-database-alert="${item.id}">Reconhecer</button>` : `<span class="online-pill">Reconhecido</span>`}
          </article>
        `).join("") : `<div class="database-empty-state">Nenhum alerta operacional ativo.</div>`}
      </div>
    </section>
    <section class="database-diagnostic-section">
      <header><h4>Recomendações</h4><span>${(performance.recommendations || []).length}</span></header>
      <div class="database-recommendations">
        ${(performance.recommendations || []).map((item) => `<p data-severity="${escapeAttr(item.severity)}">${escapeHtml(item.message)}</p>`).join("")}
      </div>
    </section>
    <section class="database-diagnostic-section">
      <header><h4>Acesso às tabelas</h4><span>Scans e linhas estimadas</span></header>
      <div class="config-table-wrap">
        <table class="config-table database-performance-table">
          <thead><tr><th>Tabela</th><th>Linhas</th><th>Seq. scans</th><th>Linhas lidas</th><th>Index scans</th><th>Linhas mortas</th></tr></thead>
          <tbody>${(performance.table_access || []).map((item) => `
            <tr><td>${escapeHtml(`${item.schema_name}.${item.table_name}`)}</td><td>${Number(item.row_estimate || 0).toLocaleString("pt-BR")}</td><td>${Number(item.seq_scan || 0).toLocaleString("pt-BR")}</td><td>${Number(item.seq_tup_read || 0).toLocaleString("pt-BR")}</td><td>${Number(item.idx_scan || 0).toLocaleString("pt-BR")}</td><td>${Number(item.dead_rows || 0).toLocaleString("pt-BR")}</td></tr>
          `).join("")}</tbody>
        </table>
      </div>
    </section>
    <section class="database-diagnostic-section">
      <header><h4>Operação</h4><span>Retenção e manutenção</span></header>
      <div class="config-table-wrap">
      <table class="config-table">
        <thead><tr><th>Área</th><th>Status</th><th>Detalhes</th></tr></thead>
        <tbody>
          <tr><td>Retenção de backups</td><td>${escapeHtml(payload.backups?.retention?.ok === false ? "erro" : "ok")}</td><td>${escapeHtml(JSON.stringify(payload.backups?.retention || {}))}</td></tr>
          <tr><td>Manutenção do banco</td><td>${escapeHtml(payload.database?.maintenance?.ok === false ? "erro" : "ok")}</td><td>${escapeHtml(JSON.stringify(payload.database?.maintenance || {}))}</td></tr>
        </tbody>
      </table>
      </div>
    </section>
  `;
  target.querySelectorAll("[data-ack-database-alert]").forEach((button) => {
    button.addEventListener("click", () => acknowledgeDatabaseAlert(button.dataset.ackDatabaseAlert));
  });
}

export function openConfigUserDialog() {
  const dialog = $("#configUserDialog");
  const form = $("#configUserForm");
  if (!dialog || !form) return;
  form.reset();
  syncCarteiraSelects(dialog);
  form.dataset.editSource = "";
  form.dataset.editUserId = "";
  form.type.value = "gerencial";
  form.type.disabled = false;
  form.username.readOnly = false;
  form.password.required = true;
  form.meta_competencia.value = currentCompetence();
  form.meta_competencia.onchange = syncConfigGoalValue;
  form.dataset.monthlyGoals = "{}";
  form.dataset.goalFallback = "70000";
  const superadminOption = form.querySelector("[data-superadmin-role]");
  if (superadminOption) {
    superadminOption.hidden = !isSuperAdmin();
    superadminOption.disabled = !isSuperAdmin();
  }
  $("#configUserDialogTitle").textContent = "Cadastrar usuario";
  $("#configUserSubmitBtn").textContent = "Cadastrar";
  setToolCheckboxes(["producao", "pareceres"]);
  updateConfigUserType();
  dialog.showModal();
}

async function openEditConfigUserDialog(source, userId) {
  const user = findUser(source, userId);
  const dialog = $("#configUserDialog");
  const form = $("#configUserForm");
  if (!user || !dialog || !form) return;
  if (source === "gerencial" && !isSuperAdmin()) return;
  form.reset();
  syncCarteiraSelects(dialog);
  form.dataset.editSource = source;
  form.dataset.editUserId = String(userId);
  const isNegotiator = source === "negociador";
  form.type.value = isNegotiator ? "negociador" : "gerencial";
  form.type.disabled = true;
  form.username.value = user.username || "";
  form.username.readOnly = isNegotiator;
  form.password.value = "";
  form.password.required = false;
  form.role.value = isNegotiator ? "user" : String(user.role || "gerencial").toLowerCase();
  const superadminOption = form.querySelector("[data-superadmin-role]");
  if (superadminOption) {
    superadminOption.hidden = !isSuperAdmin();
    superadminOption.disabled = !isSuperAdmin();
  }
  if (isNegotiator) {
    form.carteira.value = String(user.carteira || "").toUpperCase();
    form.meta_pagamento.value = String(user.meta_pagamento || "").replace(".", ",");
    form.meta_competencia.value = currentCompetence();
    form.meta_competencia.onchange = syncConfigGoalValue;
    form.dataset.monthlyGoals = "{}";
    form.dataset.goalFallback = String(user.meta_pagamento || 0);
    setToolCheckboxes(user.enabled_tools);
  }
  $("#configUserDialogTitle").textContent = isNegotiator ? "Editar negociador" : "Editar usuario gerencial";
  $("#configUserSubmitBtn").textContent = "Salvar alterações";
  updateConfigUserType();
  dialog.showModal();
  if (isNegotiator) {
    try {
      const payload = await api(`/api/config/users/negociador/${encodeURIComponent(userId)}/goals`);
      const goals = Object.fromEntries((payload.items || []).map((item) => [item.competencia, item.meta_pagamento]));
      form.dataset.monthlyGoals = JSON.stringify(goals);
      form.dataset.goalFallback = String(payload.fallback ?? user.meta_pagamento ?? 0);
      syncConfigGoalValue();
    } catch (error) {
      toast(error.message || "Nao foi possivel carregar o historico de metas.");
    }
  }
}

function currentCompetence() {
  const today = new Date();
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
}

function syncConfigGoalValue() {
  const form = $("#configUserForm");
  if (!form || form.type.value !== "negociador") return;
  let goals = {};
  try {
    goals = JSON.parse(form.dataset.monthlyGoals || "{}");
  } catch (_error) {
    goals = {};
  }
  const competence = form.meta_competencia.value || currentCompetence();
  const hasExplicitGoal = Object.prototype.hasOwnProperty.call(goals, competence);
  const value = hasExplicitGoal ? goals[competence] : form.dataset.goalFallback || "";
  form.meta_pagamento.value = String(value ?? "").replace(".", ",");
  const hint = $("#configGoalHint");
  if (hint) {
    hint.textContent = hasExplicitGoal
      ? "Meta registrada para esta competencia. Alteracoes nao afetam os outros meses."
      : "Ainda nao ha meta propria neste mes. Ao salvar, uma nova competencia sera criada.";
  }
}

export function updateConfigUserType() {
  const form = $("#configUserForm");
  if (!form) return;
  const isNegotiator = form.type.value === "negociador";
  $("#configRoleField")?.classList.toggle("hidden", isNegotiator);
  $("#configNegotiatorFields")?.classList.toggle("hidden", !isNegotiator);
  form.role.required = !isNegotiator;
  form.carteira.required = isNegotiator;
  form.meta_competencia.required = isNegotiator;
  form.meta_pagamento.required = isNegotiator;
  form.querySelectorAll("input[name='enabled_tools']").forEach((input) => {
    input.required = false;
  });
}

export async function saveConfigUser(event) {
  event?.preventDefault();
  const form = $("#configUserForm");
  if (!form?.reportValidity()) return;
  const isEditing = Boolean(form.dataset.editUserId);
  const isNegotiator = isEditing ? form.dataset.editSource === "negociador" : form.type.value === "negociador";
  const enabledTools = [...form.querySelectorAll("input[name='enabled_tools']:checked")].map((input) => input.value);
  if (isNegotiator && !enabledTools.length) {
    toast("Selecione ao menos uma ferramenta para o negociador.");
    return;
  }
  try {
    const endpoint = isEditing
      ? `/api/config/users/${encodeURIComponent(form.dataset.editSource)}/${encodeURIComponent(form.dataset.editUserId)}/settings`
      : "/api/config/users";
    await api(endpoint, {
      method: isEditing ? "PUT" : "POST",
      body: JSON.stringify({
        type: isNegotiator ? "negociador" : form.type.value,
        username: form.username.value.trim(),
        password: form.password.value,
        role: isNegotiator ? "user" : form.role.value,
        carteira: isNegotiator ? form.carteira.value : "",
        meta_pagamento: isNegotiator ? form.meta_pagamento.value : "",
        meta_competencia: isNegotiator ? form.meta_competencia.value : "",
        enabled_tools: isNegotiator ? enabledTools : [],
      }),
    });
    removeCache("negociadores.list");
    closeDialog("#configUserDialog");
    toast(isEditing ? (isNegotiator ? "Negociador atualizado." : "Usuario gerencial atualizado.") : (isNegotiator ? "Negociador cadastrado." : "Login gerencial criado."));
    await loadConfigUsers();
  } catch (error) {
    toast(error.message || "Nao foi possivel criar o usuario.");
  }
}

async function toggleConfigUser(source, userId) {
  const user = findUser(source, userId);
  if (!user) return;
  const nextActive = !Boolean(user.active);
  const action = nextActive ? "ativar" : "desativar";
  if (!window.confirm(`Deseja ${action} o login ${user.username}?`)) return;
  try {
    await api(`/api/config/users/${encodeURIComponent(source)}/${encodeURIComponent(userId)}`, {
      method: "PUT",
      body: JSON.stringify({ active: nextActive }),
    });
    if (source === "negociador") removeCache("negociadores.list");
    toast(nextActive ? "Usuario ativado." : "Usuario desativado.");
    await loadConfigUsers();
  } catch (error) {
    toast(error.message || "Nao foi possivel alterar o usuario.");
  }
}

async function deleteConfigUser(source, userId) {
  const user = findUser(source, userId);
  if (!user) return;
  const scope = source === "negociador" ? "do negociador" : "gerencial";
  if (!window.confirm(`Excluir somente o login ${scope} ${user.username}? Os dados permanecerao armazenados.`)) return;
  try {
    await api(`/api/config/users/${encodeURIComponent(source)}/${encodeURIComponent(userId)}`, { method: "DELETE" });
    if (source === "negociador") removeCache("negociadores.list");
    toast("Login excluido.");
    await loadConfigUsers();
  } catch (error) {
    toast(error.message || "Nao foi possivel excluir o login.");
  }
}

function findUser(source, userId) {
  const key = source === "negociador" ? "negociadores" : "gerencial";
  return (state.configUsers?.[key] || []).find((item) => String(item.id) === String(userId));
}

function setToolCheckboxes(tools) {
  const selected = new Set(Array.isArray(tools) && tools.length ? tools : ["producao", "pareceres"]);
  $("#configUserForm")?.querySelectorAll("input[name='enabled_tools']").forEach((input) => {
    input.checked = selected.has(input.value);
  });
}

function eventTypeLabel(value) {
  const labels = {
    initial_snapshot: "Snapshot inicial",
    update: "Atualização",
    new_month: "Novo mês",
    sheet_changed: "Sheet alterado",
    login_success: "Login",
    login_failed: "Falha no login",
    logout: "Logout",
    user_create: "Usuário criado",
    user_update: "Usuário atualizado",
    user_activate: "Usuário ativado",
    user_deactivate: "Usuário desativado",
    user_delete_login: "Login excluído",
    carteira_create: "Carteira criada",
    carteira_deactivate: "Carteira desativada",
    backup_create: "Backup criado",
    backup_restore: "Restore",
    permissions_update: "Permissões atualizadas",
  };
  return labels[value] || String(value || "Evento");
}

function shortDetails(details) {
  if (!details || typeof details !== "object" || !Object.keys(details).length) return "-";
  return Object.entries(details).slice(0, 3).map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : value}`).join(" | ");
}

function actionLabel(value) {
  const labels = {
    create: "Criação",
    update: "Atualização",
    delete: "Exclusão",
    cleanup_duplicates: "Limpeza de duplicidades",
  };
  return labels[value] || String(value || "Registro");
}

function allowedConfigPage(page) {
  if (canOpenConfigPage(page)) return page || "usuarios";
  if (canOpenConfigPage("auditoria")) return "auditoria";
  if (canOpenConfigPage("schemas")) return "schemas";
  return page || "usuarios";
}

function isAdmin() {
  if (!state.user) return true;
  return ["admin", "superadmin"].includes(String(state.user?.role || "").toLowerCase());
}

function isSuperAdmin() {
  return String(state.user?.role || "").toLowerCase() === "superadmin";
}

function hasPermission(permission) {
  if (isAdmin()) return true;
  return Boolean(state.user?.permissions?.[permission]);
}

function canOpenConfigPage(page) {
  if (!state.user) return true;
  if (page === "usuarios") return hasPermission("manage_users");
  if (page === "permissoes") return isAdmin();
  if (page === "auditoria") return hasPermission("view_audit");
  if (page === "schemas") return hasPermission("view_schema_versions");
  if (page === "ferramentas") return isAdmin();
  if (page === "backups") return hasPermission("manage_backups") || hasPermission("restore_backup");
  if (page === "diagnostico") return isAdmin();
  return true;
}
