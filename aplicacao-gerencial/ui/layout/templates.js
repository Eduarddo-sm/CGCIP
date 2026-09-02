const templateCache = new Map();
const TEMPLATE_PREFIX = "gerencial.template.";

export async function loadTemplates(definitions = []) {
  const prepared = await Promise.all(definitions.map(prepareTemplate));
  for (const item of prepared) {
    if (!item) continue;
    const container = document.querySelector(item.definition.target || "body");
    if (!container) throw new Error(`Container de template nao encontrado: ${item.definition.target || "body"}`);
    insertFragment(container, item.fragment, item.definition.position || "beforeend");
  }
}

async function prepareTemplate(definition) {
  const { path, once = true } = definition;
  if (!path) throw new Error("Template sem caminho definido.");
  if (once && document.querySelector(`[data-template-source="${cssEscape(path)}"]`)) return null;

  const html = await fetchTemplate(path);
  const wrapper = document.createElement("template");
  wrapper.innerHTML = html.trim();
  const fragment = wrapper.content.cloneNode(true);
  markTemplateNodes(fragment, path);
  return { definition, fragment };
}

async function fetchTemplate(path) {
  if (templateCache.has(path)) return templateCache.get(path);
  const cached = readStoredTemplate(path);
  if (cached) {
    templateCache.set(path, cached);
    refreshStoredTemplate(path);
    return cached;
  }
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Nao foi possivel carregar template: ${path}`);
  const html = await response.text();
  templateCache.set(path, html);
  writeStoredTemplate(path, html);
  return html;
}

function readStoredTemplate(path) {
  try {
    const raw = localStorage.getItem(TEMPLATE_PREFIX + path);
    if (!raw) return "";
    const payload = JSON.parse(raw);
    if (payload.version !== appVersion()) return "";
    return String(payload.html || "");
  } catch {
    return "";
  }
}

function writeStoredTemplate(path, html) {
  try {
    localStorage.setItem(TEMPLATE_PREFIX + path, JSON.stringify({
      version: appVersion(),
      html,
    }));
  } catch {
    // Template cache only improves reload speed.
  }
}

function refreshStoredTemplate(path) {
  window.setTimeout(async () => {
    try {
      const response = await fetch(path);
      if (!response.ok) return;
      const html = await response.text();
      templateCache.set(path, html);
      writeStoredTemplate(path, html);
    } catch {
      // Keep the cached shell when the background refresh fails.
    }
  }, 1200);
}

function appVersion() {
  return window.__GERENCIAL_ASSET_VERSION__ || "dev";
}

function markTemplateNodes(fragment, path) {
  const elementNodes = [...fragment.children];
  for (const node of elementNodes) {
    node.dataset.templateSource = path;
  }
}

function insertFragment(container, fragment, position) {
  if (position === "afterbegin") {
    container.insertBefore(fragment, container.firstChild);
    return;
  }
  if (position === "beforebegin") {
    container.parentNode?.insertBefore(fragment, container);
    return;
  }
  if (position === "afterend") {
    container.parentNode?.insertBefore(fragment, container.nextSibling);
    return;
  }
  container.appendChild(fragment);
}

function cssEscape(value) {
  if (window.CSS?.escape) return CSS.escape(value);
  return String(value).replace(/["\\]/g, "\\$&");
}
