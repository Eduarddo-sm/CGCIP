import { $ } from "../core/dom.js";

export function toggleProfileMenu() {
  const dropdown = $("#profileDropdown");
  const willOpen = dropdown.classList.contains("hidden");
  dropdown.classList.toggle("hidden", !willOpen);
  $("#profileBtn").setAttribute("aria-expanded", String(willOpen));
}

export function closeProfileMenu() {
  $("#profileDropdown").classList.add("hidden");
  $("#profileBtn").setAttribute("aria-expanded", "false");
}
