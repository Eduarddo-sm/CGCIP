const callbacks = {
  showMainHub: async () => {},
  showOverview: async () => {},
  showParecer: async () => {},
  showProtocolo: async () => {},
  showColchao: async () => {},
  showAnalise: async () => {},
  showDefasagem: async () => {},
  showConfiguracao: async () => {},
};

export function configureToolSwitcher(options = {}) {
  Object.assign(callbacks, options);
}

export function toggleToolMenu() {
  const button = document.getElementById("toolMenuBtn");
  const dropdown = document.getElementById("groupDropdown");
  if (!button || !dropdown) return;
  const expanded = button.getAttribute("aria-expanded") === "true";
  button.setAttribute("aria-expanded", String(!expanded));
  dropdown.classList.toggle("hidden", expanded);
  document.querySelector(".sidebar")?.classList.toggle("group-menu-open", !expanded);
}

export function closeToolMenu() {
  document.getElementById("toolMenuBtn")?.setAttribute("aria-expanded", "false");
  document.getElementById("groupDropdown")?.classList.add("hidden");
  document.querySelector(".sidebar")?.classList.remove("group-menu-open");
}

export function selectTool(tool) {
  closeToolMenu();
  setActiveTool(tool);
  if (tool === "parecer") {
    callbacks.showParecer();
    return;
  }
  if (tool === "protocolo") {
    callbacks.showProtocolo();
    return;
  }
  if (tool === "colchao") {
    callbacks.showColchao();
    return;
  }
  if (tool === "analise") {
    callbacks.showAnalise();
    return;
  }
  if (tool === "defasagem") {
    callbacks.showDefasagem();
    return;
  }
  if (tool === "configuracao") {
    callbacks.showConfiguracao();
    return;
  }
  callbacks.showOverview();
}

export function setActiveTool(tool) {
  document.querySelectorAll("[data-highlighted-tool-id]").forEach((button) => {
    button.classList.remove("active");
  });
  document.querySelectorAll("[data-tool]").forEach((button) => {
    button.classList.toggle("active", button.dataset.tool === tool);
  });
}

export function setActiveGroup(group) {
  document.querySelectorAll("[data-group]").forEach((button) => {
    button.classList.toggle("active", button.dataset.group === group);
  });
}
