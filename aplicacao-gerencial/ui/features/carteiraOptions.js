import { api } from "../core/api.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { state } from "../core/state.js";

const DEFAULT_CARTEIRAS = ["GAMMA", "ALPHA", "BETA"];

export async function loadCarteiras() {
  const payload = await api("/api/carteiras");
  state.carteiras = payload.items || [];
  syncCarteiraSelects();
  return state.carteiras;
}

export function carteiraNames() {
  const names = new Set(DEFAULT_CARTEIRAS);
  (state.carteiras || []).forEach((item) => {
    const nome = normalizeCarteira(item.nome);
    if (nome) names.add(nome);
  });
  (state.negociadores || []).forEach((item) => {
    const nome = normalizeCarteira(item.carteira);
    if (nome) names.add(nome);
  });
  (state.configUsers?.negociadores || []).forEach((item) => {
    const nome = normalizeCarteira(item.carteira);
    if (nome) names.add(nome);
  });
  return [...names].sort((a, b) => a.localeCompare(b, "pt-BR"));
}

export function syncCarteiraSelects(root = document) {
  root.querySelectorAll("[data-carteira-options]").forEach((select) => {
    const current = String(select.value || "").trim().toUpperCase();
    const placeholder = select.dataset.placeholder || "Selecione";
    const options = carteiraNames();
    select.innerHTML = `<option value="">${escapeHtml(placeholder)}</option>${options.map((nome) => (
      `<option value="${escapeAttr(nome)}">${escapeHtml(nome)}</option>`
    )).join("")}`;
    if (current && options.includes(current)) {
      select.value = current;
    }
  });
}

function normalizeCarteira(value) {
  return String(value || "").trim().toUpperCase().replace(/\s+/g, " ");
}
