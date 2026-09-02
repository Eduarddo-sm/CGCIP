import { api } from "../core/api.js";
import { $ } from "../core/dom.js";
import { escapeHtml } from "../core/html.js";
import { state } from "../core/state.js";
import { toast } from "../core/toast.js";
import { closeDialog } from "../layout/dialogs.js";
import { syncCarteiraSelects } from "./carteiraOptions.js";

const callbacks = {
  reload: async () => {},
};

export function configureNegociadoresCrud(options = {}) {
  Object.assign(callbacks, options);
}

export function openForm(negociador = null) {
  state.editing = negociador;
  $("#dialogTitle").textContent = negociador ? "Editar negociador" : "Adicionar negociador";
  const form = $("#negociadorForm");
  syncCarteiraSelects($("#negociadorDialog"));
  const sourceType = negociador?.source_type || "planilha";
  form.elements.source_type.value = sourceType;
  form.nome.value = negociador?.nome || "";
  form.carteira.value = negociador?.carteira || "";
  form.carteira_sistema.value = negociador?.carteira || "";
  form.arquivo_path.value = negociador?.arquivo_path || "";
  form.sheet.value = negociador?.sheet || "";
  form.senha.value = negociador?.senha || "";
  form.negocial_username.value = negociador?.negocial_username || "";
  form.negocial_password.value = "";
  form.meta_pagamento.value = formatMetaValue(negociador?.meta_pagamento ?? "");
  $("#sheetChoices").innerHTML = "";
  updateFormSource();
  $("#negociadorDialog").showModal();
}

export function updateFormSource() {
  const form = $("#negociadorForm");
  const sourceType = form.elements.source_type.value || "planilha";
  const isSystem = sourceType === "sistema";
  const isEditingSystem = Boolean(state.editing && state.editing.source_type === "sistema");

  $("#planilhaFields").classList.toggle("hidden", isSystem);
  $("#sistemaFields").classList.toggle("hidden", !isSystem);
  $("#negociadorNomeField").classList.toggle("hidden", isSystem);
  $("#carteiraInputField").classList.toggle("hidden", isSystem);
  $("#carteiraSelectField").classList.toggle("hidden", !isSystem);

  form.nome.required = !isSystem;
  form.carteira.required = !isSystem;
  form.carteira_sistema.required = isSystem;
  form.arquivo_path.required = !isSystem;
  form.sheet.required = !isSystem;
  form.negocial_username.required = isSystem;
  form.negocial_password.required = isSystem && !isEditingSystem;
  form.meta_pagamento.required = isSystem;
  form.senha.required = false;

  if (isSystem) {
    $("#sheetChoices").innerHTML = "";
    form.nome.value = form.negocial_username.value || form.nome.value;
    form.arquivo_path.value = "";
    form.sheet.value = "";
    form.senha.value = "";
  } else {
    form.negocial_username.value = "";
    form.negocial_password.value = "";
    form.meta_pagamento.value = "";
    form.carteira_sistema.value = "";
  }
}

export async function loadSheets() {
  const form = $("#negociadorForm");
  if (form.elements.source_type.value === "sistema") {
    toast("Negociador via sistema nao usa sheets.");
    return;
  }
  try {
    const payload = await api("/api/sheets", {
      method: "POST",
      body: JSON.stringify({
        path: form.arquivo_path.value,
        password: form.senha.value,
      }),
    });
    $("#sheetChoices").innerHTML = payload.sheets.map((sheet) => `<button class="sheet-chip" type="button">${escapeHtml(sheet)}</button>`).join("");
    document.querySelectorAll(".sheet-chip").forEach((chip) => chip.addEventListener("click", () => {
      form.sheet.value = chip.textContent;
    }));
  } catch (error) {
    toast(error.message);
  }
}

export async function saveForm(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const sourceType = form.elements.source_type.value || "planilha";
  const payload = {
    source_type: sourceType,
    nome: form.nome.value.trim(),
    carteira: sourceType === "sistema"
      ? form.carteira_sistema.value.trim() || null
      : form.carteira.value.trim() || null,
  };
  if (sourceType === "sistema") {
    payload.negocial_username = form.negocial_username.value.trim();
    payload.negocial_password = form.negocial_password.value || null;
    payload.meta_pagamento = normalizeMetaValue(form.meta_pagamento.value);
    payload.nome = payload.negocial_username;
    if (!payload.carteira || !payload.negocial_username) {
      toast("Informe carteira e usuario do sistema negocial.");
      return;
    }
    if (payload.meta_pagamento === null) {
      toast("Informe uma meta valida para o negociador.");
      return;
    }
    if (!state.editing && !payload.negocial_password) {
      toast("Informe a senha do usuario negocial.");
      return;
    }
  } else {
    payload.arquivo_path = form.arquivo_path.value.trim();
    payload.sheet = form.sheet.value.trim();
    payload.senha = form.senha.value || null;
    if (!payload.nome || !payload.arquivo_path || !payload.sheet) {
      toast("Informe nome, arquivo da planilha e sheet.");
      return;
    }
  }
  try {
    if (state.editing) {
      await api(`/api/negociadores/${state.editing.id}`, { method: "PUT", body: JSON.stringify(payload) });
      toast("Negociador atualizado");
    } else {
      const bundle = await api("/api/negociadores", { method: "POST", body: JSON.stringify(payload) });
      state.activeId = bundle.negociador.id;
      state.mode = "negociador";
      toast("Negociador cadastrado");
    }
    closeDialog("#negociadorDialog");
    await callbacks.reload();
  } catch (error) {
    toast(error.message);
  }
}

export async function removeActive() {
  const active = state.negociadores.find((item) => item.id === state.activeId);
  await api(`/api/negociadores/${active.id}`, { method: "DELETE" });
  state.activeId = null;
  await callbacks.reload();
  toast("Negociador removido");
}

function normalizeMetaValue(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return null;
  const normalized = raw
    .replace(/[R$\s]/g, "")
    .replace(/\./g, "")
    .replace(",", ".");
  const number = Number(normalized);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function formatMetaValue(value) {
  if (value === null || value === undefined || value === "") return "";
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return number.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
