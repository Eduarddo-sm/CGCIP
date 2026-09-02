import { $ } from "../core/dom.js";

const NAV_IDS = ["monitorNav", "parecerNav", "protocoloNav", "colchaoNav", "analiseNav", "defasagemNav"];

export function setupModuleTabs() {
  const tabs = $("#moduleTabs");
  if (!tabs || tabs.dataset.ready === "true") return;

  const moduleNav = $("#toolDropdown");
  if (moduleNav) {
    moduleNav.classList.remove("hidden");
    moduleNav.classList.add("app-module-nav");
    moduleNav.setAttribute("aria-label", "Modulos Backoffice");
    moduleNav.querySelector("[data-sidebar-group='backoffice']")?.remove();
  }

  const analysisModuleNav = $("#analiseToolDropdown");
  if (analysisModuleNav) {
    analysisModuleNav.classList.add("app-module-nav");
    analysisModuleNav.setAttribute("aria-label", "Modulos de Analise de Dados");
  }

  $("#activeToolName").textContent = "BACKOFFICE";
  $("#toolMenuBtn .brand-mark").textContent = "B";

  for (const id of NAV_IDS) {
    const nav = document.getElementById(id);
    if (!nav) continue;
    nav.classList.add("module-tab-nav");
    nav.querySelector(".nav-action-btn")?.remove();
    tabs.appendChild(nav);
  }

  tabs.dataset.ready = "true";
}

export function updateModuleTabs() {
  const tabs = $("#moduleTabs");
  if (!tabs) return;
  const hasVisibleTabs = NAV_IDS.some((id) => {
    const nav = document.getElementById(id);
    return nav && !nav.classList.contains("hidden");
  });
  tabs.classList.toggle("hidden", !hasVisibleTabs);
}
