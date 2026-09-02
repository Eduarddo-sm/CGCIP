import { $ } from "../core/dom.js";

export function applySidebarState() {
  const collapsed = localStorage.sidebarCollapsed === "true";
  document.body.classList.toggle("sidebar-collapsed", collapsed);
  const button = $("#sidebarToggleBtn");
  if (button) {
    button.setAttribute("aria-expanded", String(!collapsed));
    button.setAttribute("aria-label", collapsed ? "Expandir menu" : "Minimizar menu");
  }
}

export function toggleSidebar() {
  const collapsed = !document.body.classList.contains("sidebar-collapsed");
  localStorage.sidebarCollapsed = String(collapsed);
  applySidebarState();
}
