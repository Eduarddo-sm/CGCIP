import { apiGet, apiPost } from "./api.js?v=20260714-module-contract-1";
import { initPareceres, loadPareceres } from "./parecer.js?v=20260727-grid-empty-state-1";
import { canAutoRefreshProducao, initProducao, loadProducao } from "./producao.js?v=20260828-new-agreement-1";
import { exitDynamicToolFocus, loadDynamicTool, loadDynamicToolDefinitions } from "./ferramentas.js?v=20260812-dynamic-form-steps-1";
import { initMonthRollover } from "./monthRollover.js?v=20260901-month-rollover-5";

const pageTitle = document.querySelector("#pageTitle");
const pageTitleIcon = document.querySelector("#pageTitleIcon");
const pageTitleDescription = document.querySelector("#pageTitleDescription");
const producaoPage = document.querySelector("#producaoPage");
const pareceresPage = document.querySelector("#pareceresPage");
const dynamicToolPage = document.querySelector("#dynamicToolPage");
const sideNav = document.querySelector("#sideNav");
const profileUsername = document.querySelector("#profileUsername");
const profileRole = document.querySelector("#profileRole");
const profileAvatar = document.querySelector("#profileAvatar");
const profileMenuBtn = document.querySelector("#profileMenuBtn");
const profileMenu = document.querySelector("#profileMenu");
const profileMenuUsername = document.querySelector("#profileMenuUsername");
const profileMenuRole = document.querySelector("#profileMenuRole");
const themeToggleBtn = document.querySelector("#themeToggleBtn");
const themeToggleIcon = document.querySelector("#themeToggleIcon");
const themeToggleLabel = document.querySelector("#themeToggleLabel");
const logoutBtn = document.querySelector("#logoutBtn");
const correctionAlertBtn = document.querySelector("#correctionAlertBtn");
const correctionAlertCount = document.querySelector("#correctionAlertCount");
const correcoesDialog = document.querySelector("#correcoesDialog");
const closeCorrecoesDialogBtn = document.querySelector("#closeCorrecoesDialogBtn");
const correcoesList = document.querySelector("#correcoesList");
const appShell = document.querySelector(".app-shell");
const appSidebar = document.querySelector("#appSidebar");
const sidebarToggleBtn = document.querySelector("#sidebarToggleBtn");
const navItems = () => [...document.querySelectorAll(".nav-item")];

const pages = {
  producao: {
    description: "Acordos, metas e acompanhamento da competencia",
    title: "Produção Diária",
    icon: "▦",
    element: producaoPage,
  },
  pareceres: {
    description: "Solicitacoes e acompanhamento de pareceres",
    title: "Pareceres",
    icon: "▤",
    element: pareceresPage,
  },
};

let currentPage = "producao";
let enabledPageKeys = new Set(Object.keys(pages));
let correctionItems = [];
let producaoRefreshInFlight = false;
let userProfileRefreshInFlight = false;
let monthRolloverRefreshInFlight = false;
let producaoVersion = null;
const replacedLegacyPages = new Set();

function applySidebarState(collapsed) {
  appShell?.classList.toggle("sidebar-collapsed", collapsed);
  appSidebar?.classList.toggle("collapsed", collapsed);
  sidebarToggleBtn?.setAttribute("aria-expanded", String(!collapsed));
  sidebarToggleBtn?.setAttribute("aria-label", collapsed ? "Expandir navegacao" : "Minimizar navegacao");
  if (sidebarToggleBtn) sidebarToggleBtn.textContent = collapsed ? "›" : "‹";
  localStorage.setItem("negocial.sidebarCollapsed", collapsed ? "1" : "0");
}

function roleLabel(role) {
  const labels = {
    ADMIN: "Administrador",
    USER: "Negociador",
  };
  return labels[String(role || "").toUpperCase()] || role;
}

function syncProfile(user) {
  const username = user.username || "Usuário";
  const label = roleLabel(user.role);
  const role = user.carteira ? `${label} - ${user.carteira}` : label;
  profileUsername.textContent = username;
  profileRole.textContent = role;
  profileMenuUsername.textContent = username;
  profileMenuRole.textContent = role;
  profileAvatar.textContent = username.trim().charAt(0).toUpperCase() || "U";
}

function setProfileMenu(open) {
  profileMenu?.classList.toggle("hidden", !open);
  profileMenuBtn?.setAttribute("aria-expanded", String(open));
}

function applyTheme(theme, persist = true) {
  const nextTheme = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = nextTheme;
  if (persist) localStorage.setItem("negocial.theme", nextTheme);
  const dark = nextTheme === "dark";
  if (themeToggleIcon) themeToggleIcon.textContent = dark ? "☀" : "☾";
  if (themeToggleLabel) themeToggleLabel.textContent = dark ? "Tema claro" : "Tema escuro";
  themeToggleBtn?.setAttribute("aria-label", dark ? "Ativar tema claro" : "Ativar tema escuro");
}

function applyToolPermissions(user) {
  const tools = Array.isArray(user.enabled_tools)
    ? user.enabled_tools
    : ["producao"];
  enabledPageKeys = new Set([
    ...tools.filter((tool) => pages[tool]),
    ...Object.keys(pages).filter((key) => key.startsWith("tool:")),
  ]);
  replacedLegacyPages.forEach((key) => enabledPageKeys.delete(key));
  if (!enabledPageKeys.size) enabledPageKeys.add("producao");
  navItems().forEach((item) => {
    if (String(item.dataset.page || "").startsWith("tool:")) return;
    const enabled = enabledPageKeys.has(item.dataset.page) && !replacedLegacyPages.has(item.dataset.page);
    item.hidden = !enabled;
    item.classList.toggle("tool-disabled", !enabled);
    item.setAttribute("aria-hidden", String(!enabled));
    item.tabIndex = enabled ? 0 : -1;
  });
  Object.entries(pages).forEach(([key, item]) => {
    if (key.startsWith("tool:")) return;
    const enabled = enabledPageKeys.has(key) && !replacedLegacyPages.has(key);
    item.element.hidden = !enabled;
    item.element.classList.toggle("tool-disabled", !enabled);
    item.element.setAttribute("aria-hidden", String(!enabled));
  });
  const hasDynamicTools = Object.keys(pages).some((key) => key.startsWith("tool:"));
  dynamicToolPage?.classList.toggle("tool-disabled", !hasDynamicTools);
}

function firstEnabledPage() {
  return enabledPageKeys.has("producao") ? "producao" : [...enabledPageKeys][0] || "producao";
}

function setPage(pageKey) {
  const nextPageKey = enabledPageKeys.has(pageKey) ? pageKey : firstEnabledPage();
  const page = pages[nextPageKey] || pages.producao;
  currentPage = nextPageKey;
  pageTitle.textContent = page.title;
  if (pageTitleDescription) {
    pageTitleDescription.textContent = page.description || "";
    pageTitleDescription.hidden = !page.description;
  }
  if (pageTitleIcon) {
    pageTitleIcon.textContent = page.icon;
    pageTitleIcon.classList.toggle("dynamic-page-icon", Boolean(page.dynamic));
    pageTitleIcon.style.setProperty("--tool-color", page.color || "#2563eb");
  }
  setProfileMenu(false);

  Object.entries(pages).forEach(([key, item]) => {
    if (key.startsWith("tool:")) return;
    item.element.classList.toggle("hidden", key !== nextPageKey || !enabledPageKeys.has(key));
  });
  const dynamicActive = nextPageKey.startsWith("tool:");
  if (!dynamicActive) exitDynamicToolFocus();
  dynamicToolPage?.classList.toggle("hidden", !dynamicActive);
  dynamicToolPage?.setAttribute("aria-hidden", String(!dynamicActive));

  navItems().forEach((item) => {
    const active = item.dataset.page === nextPageKey;
    item.classList.toggle("active", active);
    if (active) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  });

  if (nextPageKey === "producao") {
    loadProducao().catch(() => {});
  }
  if (nextPageKey === "pareceres") {
    loadPareceres().catch(() => {});
  }
  if (nextPageKey.startsWith("tool:")) {
    loadDynamicTool(nextPageKey.slice(5)).catch((error) => {
      if (dynamicToolPage) {
        dynamicToolPage.innerHTML = `<div class="dynamic-tool-empty">${escapeHtml(error.message)}</div>`;
      }
    });
  }
}

function registerDynamicTools(definitions) {
  definitions.forEach((definition) => {
    if (definition.slug === "pareceres") replacedLegacyPages.add("pareceres");
    const key = `tool:${definition.slug}`;
    pages[key] = {
      title: definition.nome,
      icon: definition.icone || "&#9636;",
      description: definition.descricao || "Ferramenta operacional",
      color: definition.cor || "#2563eb",
      dynamic: true,
      element: dynamicToolPage,
    };
    const button = document.createElement("button");
    button.className = "nav-item dynamic-nav-item";
    button.type = "button";
    button.dataset.page = key;
    button.dataset.tooltip = definition.nome;
    button.title = definition.nome;
    button.style.setProperty("--tool-color", definition.cor || "#2563eb");
    button.innerHTML = `
      <span class="nav-glyph" aria-hidden="true">${escapeHtml(definition.icone || "F")}</span>
      <span class="nav-copy">
        <span class="nav-label">${escapeHtml(definition.nome)}</span>
        <small>${escapeHtml(definition.descricao || "Ferramenta operacional")}</small>
      </span>
    `;
    sideNav?.append(button);
  });
}

async function bootstrap() {
  try {
    const { user } = await apiGet("/api/me");
    syncProfile(user);
    registerDynamicTools(await loadDynamicToolDefinitions());
    applyToolPermissions(user);
    initProducao(user);
    if (!replacedLegacyPages.has("pareceres")) initPareceres();
    setPage(currentPage);
    await refreshMonthRollover();
    loadCorrecoes().catch(() => {});
    window.setInterval(() => loadCorrecoes().catch(() => {}), 30000);
    window.setInterval(() => refreshUserProfile().catch(() => {}), 30000);
    window.setInterval(() => refreshCurrentProduction().catch(() => {}), 15000);
    window.setInterval(() => refreshMonthRollover().catch(() => {}), 60000);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) {
        refreshUserProfile().catch(() => {});
        refreshCurrentProduction().catch(() => {});
        refreshMonthRollover().catch(() => {});
      }
    });
    window.addEventListener("focus", () => refreshMonthRollover().catch(() => {}));
  } catch (error) {
    console.error("Falha ao iniciar o sistema negocial.", error);
    window.location.href = "/login";
  }
}

async function refreshMonthRollover() {
  if (document.hidden || monthRolloverRefreshInFlight) return false;
  monthRolloverRefreshInFlight = true;
  try {
    return await initMonthRollover({ onConfirmed: () => loadProducao({ silent: true }) });
  } finally {
    monthRolloverRefreshInFlight = false;
  }
}

async function refreshUserProfile() {
  if (document.hidden || userProfileRefreshInFlight) return;
  userProfileRefreshInFlight = true;
  try {
    const { user } = await apiGet("/api/me");
    syncProfile(user);
    applyToolPermissions(user);
    if (!enabledPageKeys.has(currentPage)) {
      setPage(firstEnabledPage());
    }
  } finally {
    userProfileRefreshInFlight = false;
  }
}

async function refreshCurrentProduction() {
  if (currentPage !== "producao" || document.hidden || !canAutoRefreshProducao()) return;
  if (producaoRefreshInFlight) return;
  producaoRefreshInFlight = true;
  try {
    const data = await apiGet("/api/sync/version");
    const nextVersion = data.versions?.producao?.version ?? null;
    if (producaoVersion !== null && nextVersion === producaoVersion) return;
    producaoVersion = nextVersion;
    await loadProducao({ silent: true });
  } finally {
    producaoRefreshInFlight = false;
  }
}

async function loadCorrecoes() {
  const data = await apiGet("/api/correcoes");
  correctionItems = data.items || [];
  document.dispatchEvent(new CustomEvent("negocial:correcoes", { detail: { items: correctionItems } }));
  if (correctionAlertCount) correctionAlertCount.textContent = String(correctionItems.length);
  correctionAlertBtn?.classList.toggle("has-corrections", correctionItems.length > 0);
  renderCorrecoes();
}

function renderCorrecoes() {
  if (!correcoesList) return;
  if (!correctionItems.length) {
    correcoesList.innerHTML = `<div class="empty-corrections">Nenhuma correcao pendente.</div>`;
    return;
  }
  correcoesList.innerHTML = correctionItems.map((item) => `
    <article class="correction-item">
      <div>
        <strong>${escapeHtml(item.cliente || "Cliente nao identificado")}</strong>
        <span>${escapeHtml(item.campo || "")}</span>
      </div>
      <p><b>Antes:</b> ${escapeHtml(item.valor_anterior || "Vazio")}</p>
      <p><b>Depois:</b> ${escapeHtml(item.valor_novo || "Vazio")}</p>
      ${item.motivo ? `<p><b>Motivo:</b> ${escapeHtml(item.motivo)}</p>` : ""}
      <small>Corrigido por ${escapeHtml(item.corrigido_por || "Backoffice")}</small>
      <button class="secondary-btn" type="button" data-correction-read="${item.id}">Marcar como lido</button>
    </article>
  `).join("");
  correcoesList.querySelectorAll("[data-correction-read]").forEach((button) => {
    button.addEventListener("click", async () => {
      await apiPost(`/api/correcoes/${button.dataset.correctionRead}/visualizar`, {});
      await loadCorrecoes();
      if (currentPage === "producao") loadProducao().catch(() => {});
    });
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

sideNav?.addEventListener("click", (event) => {
  const item = event.target.closest(".nav-item");
  if (!item || !enabledPageKeys.has(item.dataset.page)) return;
  setPage(item.dataset.page);
});

applySidebarState(localStorage.getItem("negocial.sidebarCollapsed") !== "0");
applyTheme(document.documentElement.dataset.theme, false);

sidebarToggleBtn?.addEventListener("click", () => {
  applySidebarState(!appShell?.classList.contains("sidebar-collapsed"));
});

logoutBtn.addEventListener("click", async () => {
  await apiPost("/api/logout");
  window.location.href = "/login";
});

profileMenuBtn?.addEventListener("click", (event) => {
  event.stopPropagation();
  setProfileMenu(profileMenu?.classList.contains("hidden"));
});

profileMenu?.addEventListener("click", (event) => event.stopPropagation());

themeToggleBtn?.addEventListener("click", () => {
  const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  applyTheme(nextTheme);
});

document.addEventListener("click", () => setProfileMenu(false));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") setProfileMenu(false);
});

correctionAlertBtn?.addEventListener("click", () => {
  renderCorrecoes();
  correcoesDialog?.showModal();
});

closeCorrecoesDialogBtn?.addEventListener("click", () => correcoesDialog?.close());

bootstrap();
