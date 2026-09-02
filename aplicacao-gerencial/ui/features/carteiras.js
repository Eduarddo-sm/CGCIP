import { api } from "../core/api.js";
import { $ } from "../core/dom.js";
import { formatValue } from "../core/format.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { state } from "../core/state.js";
import { toast } from "../core/toast.js";
import { closeDialog } from "../layout/dialogs.js";
import { renderVisibility } from "../layout/visibility.js";
import { carteiraNames, loadCarteiras, syncCarteiraSelects } from "./carteiraOptions.js";
import { labelChange, renderMiniRowDiff } from "./changeDiff.js";
import { groupTimelineChangesByLine } from "./timelineData.js?v=20260717-css-cleanup-2";
import { clearCarteiraWorkspaceCache, exitCarteiraWorkspaceFocus, renderCarteiraWorkspace } from "./carteiraWorkspace.js?v=20260825-beta-repurchase-1";
import { openToolBuilder, openToolRecordDirect } from "./ferramentaBuilder.js?v=20260812-multi-field-condition-1";

const expanded = new Set();
const collapsedMonths = new Set();
let eventsLoaded = false;
let eventsLoading = false;
let carteiraMenuBound = false;

const DEFAULT_COLUMNS = [
  { nome: "DATA", tipo: "data", obrigatoria: true, identificador: false, automatico: true, auto_tipo: "today", visivel: true, mostrar_cadastro: true, cadastro_etapa: 1 },
  { nome: "IDENTIFICADOR", tipo: "texto", obrigatoria: true, identificador: true, visivel: true, mostrar_cadastro: true, cadastro_etapa: 1 },
  { nome: "CLIENTE", tipo: "texto", obrigatoria: true, identificador: false, visivel: true, mostrar_cadastro: true, cadastro_etapa: 1 },
  { nome: "VALOR DO ACORDO", tipo: "moeda", obrigatoria: true, identificador: false, visivel: true, mostrar_cadastro: true, cadastro_etapa: 2 },
  { nome: "VALOR DA ENTRADA", tipo: "moeda", obrigatoria: false, identificador: false, visivel: true },
  { nome: "TIPO DE ACORDO", tipo: "select", obrigatoria: true, identificador: false, visivel: true, mostrar_cadastro: true, cadastro_etapa: 1, opcoes: "A VISTA, PARCELADO" },
  { nome: "DATA DE VENCIMENTO", tipo: "data", obrigatoria: true, identificador: false, visivel: true },
  { nome: "STATUS", tipo: "select", obrigatoria: true, identificador: false, visivel: true, opcoes: "PROPOSTA, AGUARDANDO_PAGAMENTO, PAGAMENTO_REALIZADO, PROPOSTA_NEGADA, OPERACAO_RECOMPRADA, QUEBRA" },
  { nome: "JUSTIFICATIVA", tipo: "texto", obrigatoria: false, identificador: false, visivel: false, mostrar_cadastro: false, cadastro_etapa: 2 },
  { nome: "NEGOCIADOR", tipo: "texto", obrigatoria: true, identificador: false, automatico: true, auto_tipo: "usuario", visivel: true, mostrar_cadastro: false, cadastro_etapa: 2 },
];

export async function showCarteiras() {
  exitCarteiraWorkspaceFocus();
  state.mode = "carteiras";
  state.carteira.selected = null;
  $("#pageTitle").textContent = "Carteiras";
  renderVisibility();
  renderCarteiras();
  try {
    await loadCarteiraAdminItems();
  } catch (error) {
    toast(error.message || "Não foi possível atualizar as carteiras.");
  }
}

export function renderCarteiras() {
  const wallets = carteiraGroups();
  const search = ($("#carteirasSearch")?.value || "").trim().toLowerCase();
  const status = $("#carteirasStatus")?.value || "";
  const order = $("#carteirasOrder")?.value || "name";
  const visibleWallets = wallets
    .filter((group) => !search || [group.carteira, group.description].some((value) => String(value || "").toLowerCase().includes(search)))
    .filter((group) => !status || (status === "active" ? group.active : !group.active))
    .sort((left, right) => {
      if (order === "updated") return adminDate(right.updatedAt) - adminDate(left.updatedAt);
      if (order === "negotiators") return right.items.length - left.items.length || left.carteira.localeCompare(right.carteira, "pt-BR");
      return left.carteira.localeCompare(right.carteira, "pt-BR");
    });
  $("#carteirasBadge").textContent = wallets.filter((item) => item.active).length;
  $("#carteirasListView").classList.toggle("hidden", Boolean(state.carteira.selected));
  $("#carteiraDetailView").classList.toggle("hidden", !state.carteira.selected);
  if (state.carteira.selected) {
    ensureEvents();
    const selectedGroup = wallets.find((group) => normalizeWallet(group.carteira) === normalizeWallet(state.carteira.selected));
    if (selectedGroup) {
      $("#carteiraMonitorTitle").textContent = selectedGroup.carteira;
      $("#carteiraMonitorMeta").textContent = `${selectedGroup.items.length} negociadores · ${selectedGroup.negocial?.colunas?.length ?? 0} colunas`;
      $("#carteiraMonitorStatus").textContent = selectedGroup.active === false ? "Inativa" : "Ativa";
      $("#carteiraMonitorStatus").classList.toggle("inactive", selectedGroup.active === false);
      renderCarteiraWorkspace(selectedGroup, {
        active: state.carteira.workspaceTab || "overview",
        eventCount: (carteira) => carteiraEntries(carteira, "").length,
        onTabChange: (tab) => {
          state.carteira.workspaceTab = tab;
          renderCarteiras();
        },
        onEditSchema: () => openCarteiraDialog(selectedGroup.carteira),
        onOpenToolRecord: (toolId, recordId) => openToolRecordDirect(toolId, recordId, {
          onChanged: async () => {
            clearCarteiraWorkspaceCache(selectedGroup.carteira);
            renderCarteiras();
          },
        }),
        onConfigureTool: (toolId) => openToolBuilder(toolId),
        onRefresh: () => {
          clearCarteiraWorkspaceCache(selectedGroup.carteira);
          renderCarteiras();
        },
        onError: (error) => toast(error.message || "Nao foi possivel atualizar a ferramenta."),
      });
    }
    if (state.carteira.workspaceTab === "monitor") renderCarteiraMonitor();
    return;
  }
  exitCarteiraWorkspaceFocus();
  renderCarteiraSummary(wallets);
  $("#carteirasList").innerHTML = visibleWallets.length ? visibleWallets.map(renderCarteiraAdminRow).join("") : `<div class="empty-overview">Nenhuma carteira encontrada.</div>`;
  ["#carteirasSearch", "#carteirasStatus", "#carteirasOrder"].forEach((selector) => {
    const control = $(selector);
    if (control) control.oninput = renderCarteiras;
  });
  document.querySelectorAll("[data-carteira-details]").forEach((button) => {
    button.addEventListener("click", () => openCarteiraDetails(button.dataset.carteiraDetails));
  });
  document.querySelectorAll("[data-open-carteira-workspace]").forEach((button) => {
    button.addEventListener("click", () => openCarteira(button.dataset.openCarteiraWorkspace));
  });
  document.querySelectorAll("[data-edit-carteira]").forEach((button) => {
    button.addEventListener("click", () => openCarteiraDialog(button.dataset.editCarteira));
  });
  document.querySelectorAll("[data-delete-carteira]").forEach((button) => {
    button.addEventListener("click", () => deleteCarteira(button.dataset.deleteCarteira));
  });
  document.querySelectorAll("[data-monitor-carteira]").forEach((button) => {
    button.addEventListener("click", () => openCarteira(button.dataset.monitorCarteira));
  });
  document.querySelectorAll("[data-duplicate-carteira]").forEach((button) => {
    button.addEventListener("click", () => duplicateCarteira(button.dataset.duplicateCarteira));
  });
  document.querySelectorAll("[data-reactivate-carteira]").forEach((button) => {
    button.addEventListener("click", () => reactivateCarteira(button.dataset.reactivateCarteira));
  });
  document.querySelectorAll("[data-carteira-menu]").forEach((button) => {
    button.addEventListener("click", (event) => toggleCarteiraMenu(event, button));
  });
  bindCarteiraMenuDismiss();
}

async function loadCarteiraAdminItems() {
  const payload = await api("/api/carteiras?include_inactive=1");
  state.carteira.adminItems = payload.items || [];
  renderCarteiras();
}

function renderCarteiraSummary(wallets) {
  const target = $("#carteirasSummary");
  if (!target) return;
  const active = wallets.filter((item) => item.active);
  const negotiators = active.reduce((total, item) => total + item.items.length, 0);
  const columns = active.reduce((total, item) => total + Number(item.negocial?.colunas?.length || 0), 0);
  target.innerHTML = `
    <span><strong>${wallets.length}</strong> carteiras</span>
    <span><strong>${active.length}</strong> ativas</span>
    <span><strong>${negotiators}</strong> negociadores</span>
    <span><strong>${columns}</strong> colunas configuradas</span>
  `;
}

function renderCarteiraAdminRow(group) {
  const columns = group.negocial?.colunas?.length || 0;
  const version = Number(group.negocial?.schema_version || 0);
  return `
    <article class="carteira-admin-row ${group.active ? "is-active" : "is-inactive"}">
      <button class="carteira-admin-main" type="button" data-open-carteira-workspace="${escapeAttr(group.carteira)}">
        <span class="carteira-admin-avatar" aria-hidden="true">${escapeHtml(group.carteira.slice(0, 1).toUpperCase())}</span>
        <span class="carteira-admin-identity">
          <strong>${escapeHtml(group.carteira)}</strong>
          <span>${group.items.length} negociadores · ${columns} colunas · ${version ? `Schema v${version}` : "Sem versão de schema"}</span>
          <small>Atualizada em ${escapeHtml(formatAdminDate(group.updatedAt))}</small>
        </span>
      </button>
      <span class="carteira-admin-status">${group.active ? "Ativa" : "Inativa"}</span>
      <div class="carteira-admin-menu-wrap">
        <button class="carteira-admin-menu-trigger" type="button" data-carteira-menu="${escapeAttr(group.carteira)}" aria-label="Ações de ${escapeAttr(group.carteira)}" aria-expanded="false">•••</button>
        <div class="carteira-admin-menu" data-carteira-menu-panel="${escapeAttr(group.carteira)}">
          <button type="button" data-carteira-details="${escapeAttr(group.carteira)}">Visualizar estrutura</button>
          <button type="button" data-monitor-carteira="${escapeAttr(group.carteira)}">Abrir monitoramento</button>
          <button type="button" data-edit-carteira="${escapeAttr(group.carteira)}">Editar schema</button>
          <button type="button" data-duplicate-carteira="${escapeAttr(group.carteira)}">Duplicar carteira</button>
          ${group.active
            ? `<button class="danger" type="button" data-delete-carteira="${escapeAttr(group.carteira)}">Desativar</button>`
            : `<button type="button" data-reactivate-carteira="${escapeAttr(group.carteira)}">Reativar</button>`}
        </div>
      </div>
    </article>
  `;
}

export function createCarteiraPrompt() {
  openCarteiraDialog();
}

function toggleCarteiraMenu(event, button) {
  event.stopPropagation();
  const name = button.dataset.carteiraMenu;
  const panel = document.querySelector(`[data-carteira-menu-panel="${CSS.escape(name)}"]`);
  const willOpen = !panel?.classList.contains("open");
  document.querySelectorAll("[data-carteira-menu-panel]").forEach((item) => item.classList.remove("open"));
  document.querySelectorAll("[data-carteira-menu]").forEach((item) => item.setAttribute("aria-expanded", "false"));
  if (willOpen && panel) {
    panel.classList.add("open");
    button.setAttribute("aria-expanded", "true");
  }
}

function bindCarteiraMenuDismiss() {
  if (carteiraMenuBound) return;
  carteiraMenuBound = true;
  document.addEventListener("click", (event) => {
    if (event.target.closest(".carteira-admin-menu-wrap")) return;
    document.querySelectorAll("[data-carteira-menu-panel]").forEach((item) => item.classList.remove("open"));
    document.querySelectorAll("[data-carteira-menu]").forEach((item) => item.setAttribute("aria-expanded", "false"));
  });
}

function openCarteiraDetails(nome) {
  const group = carteiraGroups().find((item) => normalizeWallet(item.carteira) === normalizeWallet(nome));
  if (!group) return;
  const dialog = ensureCarteiraDetailsDialog();
  const columns = group.negocial?.colunas || [];
  const negotiators = group.items.map((item) => item.nome).sort((left, right) => left.localeCompare(right, "pt-BR"));
  const version = Number(group.negocial?.schema_version || 0);
  dialog.dataset.carteira = group.carteira;
  dialog.querySelector("[data-carteira-detail-avatar]").textContent = group.carteira.slice(0, 1).toUpperCase();
  dialog.querySelector("[data-carteira-detail-name]").textContent = group.carteira;
  dialog.querySelector("[data-carteira-detail-status]").textContent = group.active ? "Ativa" : "Inativa";
  dialog.querySelector("[data-carteira-detail-status]").className = `carteira-detail-status ${group.active ? "active" : "inactive"}`;
  dialog.querySelector("[data-carteira-detail-meta]").innerHTML = `
    <div><strong>${group.items.length}</strong><span>Negociadores</span></div>
    <div><strong>${columns.length}</strong><span>Colunas</span></div>
    <div><strong>${version ? `v${version}` : "—"}</strong><span>Schema</span></div>
    <div><strong>${escapeHtml(formatAdminDate(group.updatedAt))}</strong><span>Última atualização</span></div>
  `;
  dialog.querySelector("[data-carteira-detail-description]").textContent = group.description || "Nenhuma descrição cadastrada.";
  dialog.querySelector("[data-carteira-detail-columns]").innerHTML = columns.length
    ? columns.map((column) => `<span>${escapeHtml(column.nome || "Coluna")}</span>`).join("")
    : `<em>Schema negocial não configurado.</em>`;
  dialog.querySelector("[data-carteira-detail-users]").innerHTML = negotiators.length
    ? negotiators.map((name) => `<span>${escapeHtml(name)}</span>`).join("")
    : `<em>Nenhum negociador vinculado.</em>`;
  if (!dialog.open) dialog.showModal();
}

function ensureCarteiraDetailsDialog() {
  let dialog = $("#carteiraDetailsDialog");
  if (dialog) return dialog;
  dialog = document.createElement("dialog");
  dialog.id = "carteiraDetailsDialog";
  dialog.className = "carteira-details-dialog";
  dialog.innerHTML = `
    <form method="dialog">
      <header>
        <div class="carteira-detail-title">
          <span class="carteira-detail-avatar" data-carteira-detail-avatar></span>
          <div><h2 data-carteira-detail-name></h2><span data-carteira-detail-status></span></div>
        </div>
        <button class="icon-btn" type="button" data-close-carteira-detail aria-label="Fechar">×</button>
      </header>
      <section class="carteira-detail-body">
        <div class="carteira-detail-meta" data-carteira-detail-meta></div>
        <section><h3>Descrição</h3><p data-carteira-detail-description></p></section>
        <section><h3>Colunas configuradas</h3><div class="carteira-detail-tags" data-carteira-detail-columns></div></section>
        <section><h3>Negociadores vinculados</h3><div class="carteira-detail-tags" data-carteira-detail-users></div></section>
      </section>
      <footer>
        <button class="secondary-btn" type="button" data-detail-monitor>Monitoramento</button>
        <button class="primary-btn fit" type="button" data-detail-edit>Editar schema</button>
      </footer>
    </form>
  `;
  document.body.appendChild(dialog);
  dialog.querySelector("[data-close-carteira-detail]").addEventListener("click", () => dialog.close());
  dialog.querySelector("[data-detail-monitor]").addEventListener("click", () => {
    const carteira = dialog.dataset.carteira;
    dialog.close();
    openCarteira(carteira);
  });
  dialog.querySelector("[data-detail-edit]").addEventListener("click", () => {
    const carteira = dialog.dataset.carteira;
    dialog.close();
    openCarteiraDialog(carteira);
  });
  return dialog;
}

function duplicateCarteira(nome) {
  const existing = findCarteira(nome);
  if (!existing) return;
  openCarteiraDialog(nome);
  const form = $("#carteiraForm");
  form.nome.value = `${nome} CÓPIA`;
  form.descricao.value = existing.descricao || "";
  form.nome.focus();
  form.nome.select();
}

async function reactivateCarteira(nome) {
  const existing = findCarteira(nome);
  if (!existing) return;
  try {
    await api("/api/carteiras", {
      method: "POST",
      body: JSON.stringify({
        nome: existing.nome,
        descricao: existing.descricao || "",
        sync_negocial: Boolean(existing.negocial),
        regras_ho: existing.negocial?.regras_ho || {},
        colunas: existing.negocial?.colunas || DEFAULT_COLUMNS,
      }),
    });
    await Promise.all([loadCarteiras(), loadCarteiraAdminItems()]);
    toast("Carteira reativada.");
  } catch (error) {
    toast(error.message || "Não foi possível reativar a carteira.");
  }
}

export function openCarteiraDialog(nome = "") {
  const dialog = $("#carteiraDialog");
  const form = $("#carteiraForm");
  if (!dialog || !form) {
    toast("Formulario de carteira ainda nao foi carregado. Atualize a pagina e tente novamente.");
    return;
  }
  if (dialog.open) return;
  const existing = findCarteira(nome);
  form.reset();
  form.nome.value = existing?.nome || nome || "";
  form.descricao.value = existing?.descricao || "";
  form.sync_negocial.checked = true;
  renderCarteiraColumns(existing?.negocial?.colunas || DEFAULT_COLUMNS);
  setHoRules(form, existing?.negocial?.regras_ho || existing?.regras_ho);
  dialog.showModal();
}

export async function saveCarteira(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const colunas = readCarteiraColumns();
  if (!String(form.nome.value || "").trim()) {
    toast("Informe o nome da carteira.");
    form.nome.focus();
    return;
  }
  if (!colunas.length) {
    toast("Informe ao menos uma coluna para a carteira.");
    return;
  }
  if (!colunas.some((column) => column.identificador)) {
    toast("Marque uma coluna como chave da carteira.");
    return;
  }
  const hoRules = readHoRules(form);
  if (
    hoRules.usa_percentual_ho
    && hoRules.calculo_automatico_ho
    && !hoRules.coluna_destino
  ) {
    toast("Selecione a coluna de destino do cálculo de H.O.");
    return;
  }
  if (
    hoRules.usa_percentual_ho
    && hoRules.calculo_automatico_ho
    && hoRules.motor_calculo === "PERCENTUAL_FIXO"
    && !hoRules.coluna_base
  ) {
    toast("Selecione a base do cálculo fixo de H.O.");
    return;
  }
  if (
    hoRules.usa_percentual_ho
    && hoRules.calculo_automatico_ho
    && hoRules.motor_calculo === "PERCENTUAL_CONDICIONAL"
    && (!hoRules.coluna_base_vista || !hoRules.coluna_base_parcelado)
  ) {
    toast("Selecione as bases para acordos à vista e parcelados.");
    return;
  }
  if (hoRules.coluna_percentual_efetivo && !hoRules.coluna_valor_recebido) {
    toast("Selecione o valor recebido para calcular o percentual efetivo.");
    return;
  }
  const payload = {
    nome: form.nome.value,
    descricao: form.descricao.value,
    sync_negocial: form.sync_negocial.checked,
    regras_ho: hoRules,
    colunas,
  };
  const submitButton = form.querySelector("[type='submit']");
  try {
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "Salvando...";
    }
    await api("/api/carteiras", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await Promise.all([loadCarteiras(), loadCarteiraAdminItems()]);
    syncCarteiraSelects();
    closeDialog("#carteiraDialog");
    toast("Carteira cadastrada.");
  } catch (error) {
    toast(error.message || "Nao foi possivel cadastrar a carteira.");
  } finally {
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.textContent = "Salvar carteira";
    }
  }
}

export function addCarteiraColumn() {
  const columns = readCarteiraColumns();
  columns.push({ nome: "", tipo: "texto", obrigatoria: false, identificador: false, visivel: true, mostrar_cadastro: true, cadastro_etapa: 2, opcoes: "" });
  renderCarteiraColumns(columns);
}

function setHoRules(form, rules = null) {
  const enabled = Boolean(rules?.usa_percentual_ho);
  form.usa_percentual_ho.checked = enabled;
  form.percentual_ho_padrao.value = rules?.percentual_ho_padrao ?? (enabled ? 10 : "");
  form.percentual_ho_minimo.value = rules?.percentual_ho_minimo ?? (enabled ? 10 : "");
  form.percentual_ho_maximo.value = rules?.percentual_ho_maximo ?? (enabled ? 10 : "");
  form.calculo_automatico_ho.checked = Boolean(rules?.calculo_automatico_ho ?? enabled);
  form.ho_motor_calculo.value = rules?.motor_calculo || "PERCENTUAL_FIXO";
  form.ho_casas_decimais.value = rules?.casas_decimais ?? 2;
  refreshHoColumnOptions(form, rules);
  updateHoFields(form);
}

function readHoRules(form) {
  const enabled = form.usa_percentual_ho.checked;
  return {
    usa_percentual_ho: enabled,
    percentual_ho_padrao: enabled ? form.percentual_ho_padrao.value : null,
    percentual_ho_minimo: enabled ? form.percentual_ho_minimo.value : null,
    percentual_ho_maximo: enabled ? form.percentual_ho_maximo.value : null,
    calculo_automatico_ho: enabled && form.calculo_automatico_ho.checked,
    motor_calculo: enabled ? form.ho_motor_calculo.value : "PERCENTUAL_FIXO",
    coluna_base: enabled ? form.ho_coluna_base.value || null : null,
    coluna_base_vista: enabled ? form.ho_coluna_base_vista.value || null : null,
    coluna_base_parcelado: enabled ? form.ho_coluna_base_parcelado.value || null : null,
    coluna_destino: enabled ? form.ho_coluna_destino.value || null : null,
    coluna_valor_recebido: enabled ? form.ho_coluna_valor_recebido.value || null : null,
    coluna_percentual_efetivo: enabled ? form.ho_coluna_percentual_efetivo.value || null : null,
    casas_decimais: enabled ? Number(form.ho_casas_decimais.value || 2) : 2,
  };
}

function updateHoFields(form = $("#carteiraForm")) {
  if (!form) return;
  const enabled = form.usa_percentual_ho.checked;
  const engine = form.ho_motor_calculo.value || "PERCENTUAL_FIXO";
  form.querySelectorAll("[data-ho-fields] input, [data-ho-fields] select").forEach((control) => {
    control.disabled = !enabled;
  });
  form.ho_motor_calculo.disabled = !enabled;
  form.querySelectorAll("[data-ho-fixed]").forEach((element) => {
    element.classList.toggle("hidden", engine !== "PERCENTUAL_FIXO");
  });
  form.querySelectorAll("[data-ho-conditional]").forEach((element) => {
    element.classList.toggle("hidden", engine !== "PERCENTUAL_CONDICIONAL");
  });
  form.querySelectorAll("[data-ho-percent]").forEach((element) => {
    element.classList.toggle("hidden", engine === "ALPHA_EXCEPCIONAL");
  });
  const alphaOption = form.ho_motor_calculo.querySelector('option[value="ALPHA_EXCEPCIONAL"]');
  if (alphaOption) {
    alphaOption.hidden = schemaKey(form.nome.value) !== "ALPHA";
  }
  updateHoPreview(form);
}

function schemaKey(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function refreshHoColumnOptions(form = $("#carteiraForm"), rules = null) {
  if (!form) return;
  const columns = readCarteiraColumns()
    .filter((column) => ["numero", "moeda"].includes(column.tipo))
    .map((column) => ({
      key: column.chave || schemaKey(column.nome),
      name: column.nome,
    }))
    .filter((column) => column.key);
  const definitions = [
    ["ho_coluna_base", "Selecione a base", rules?.coluna_base],
    ["ho_coluna_base_vista", "Selecione a base à vista", rules?.coluna_base_vista],
    ["ho_coluna_base_parcelado", "Selecione a base parcelada", rules?.coluna_base_parcelado],
    ["ho_coluna_destino", "Selecione o destino", rules?.coluna_destino],
    ["ho_coluna_valor_recebido", "Nao utilizado", rules?.coluna_valor_recebido],
    ["ho_coluna_percentual_efetivo", "Nao utilizado", rules?.coluna_percentual_efetivo],
  ];
  definitions.forEach(([name, placeholder, configured]) => {
    const select = form.elements[name];
    if (!select) return;
    const previous = configured ?? select.value;
    select.innerHTML = [
      `<option value="">${escapeHtml(placeholder)}</option>`,
      ...columns.map((column) => `<option value="${escapeAttr(column.key)}">${escapeHtml(column.name)}</option>`),
    ].join("");
    select.value = columns.some((column) => column.key === previous) ? previous : "";
  });
  updateHoPreview(form);
}

function updateHoPreview(form = $("#carteiraForm")) {
  const preview = form?.querySelector("[data-ho-preview]");
  if (!preview) return;
  if (!form.usa_percentual_ho.checked) {
    preview.textContent = "Regra de H.O desativada para esta carteira.";
    return;
  }
  const base = form.ho_coluna_base.selectedOptions[0]?.textContent || "Base";
  const sightBase = form.ho_coluna_base_vista.selectedOptions[0]?.textContent || "Base à vista";
  const installmentBase = form.ho_coluna_base_parcelado.selectedOptions[0]?.textContent || "Base parcelada";
  const destination = form.ho_coluna_destino.selectedOptions[0]?.textContent || "Destino";
  const engine = form.ho_motor_calculo.value || "PERCENTUAL_FIXO";
  if (engine === "ALPHA_EXCEPCIONAL") {
    preview.textContent = `Motor trimestral Alpha → ${destination}`;
    return;
  }
  const percentage = String(form.percentual_ho_padrao.value || "0").replace(".", ",");
  preview.textContent = engine === "PERCENTUAL_CONDICIONAL"
    ? `À vista: ${sightBase} · Parcelado: ${installmentBase} · ${percentage}% → ${destination}`
    : `${base} × ${percentage}% → ${destination}`;
}

document.addEventListener("change", (event) => {
  if (event.target?.name === "usa_percentual_ho" || event.target?.name === "ho_motor_calculo") {
    updateHoFields(event.target.form);
    return;
  }
  if (event.target?.closest?.("#carteiraForm [data-ho-fields]")) {
    updateHoPreview(event.target.form);
  }
  if (event.target?.closest?.("#carteiraColumns")) {
    refreshHoColumnOptions($("#carteiraForm"));
  }
});

document.addEventListener("input", (event) => {
  if (event.target?.closest?.("#carteiraForm [data-ho-fields]")) {
    updateHoPreview(event.target.form);
  }
});

async function deleteCarteira(nome) {
  if (!nome) return;
  const motivo = window.prompt(`Motivo para excluir a carteira ${nome}:`);
  if (!motivo) return;
  const confirmacao = window.prompt("Digite CONFIRMAR para excluir a carteira:");
  if (String(confirmacao || "").toUpperCase() !== "CONFIRMAR") return;
  try {
    await api(`/api/carteiras/${encodeURIComponent(nome)}`, {
      method: "DELETE",
      body: JSON.stringify({ motivo, confirmacao }),
    });
    await Promise.all([loadCarteiras(), loadCarteiraAdminItems()]);
    toast("Carteira desativada.");
  } catch (error) {
    toast(error.message || "Nao foi possivel excluir a carteira.");
  }
}

function renderCarteiraColumns(columns) {
  const target = $("#carteiraColumns");
  target.innerHTML = columns.map((column, index) => {
    const options = Array.isArray(column.opcoes)
      ? column.opcoes.join(", ")
      : String(column.opcoes || "");
    return `
    <div class="carteira-column-row" data-carteira-column data-column-key="${escapeAttr(column.chave || "")}">
      <div class="carteira-column-order">
        <button class="icon-btn compact" type="button" data-move-column="${index}" data-direction="-1" title="Mover para cima">↑</button>
        <button class="icon-btn compact" type="button" data-move-column="${index}" data-direction="1" title="Mover para baixo">↓</button>
      </div>
      <input name="column_nome" placeholder="Nome da coluna" value="${escapeAttr(column.nome || "")}" />
      <select name="column_tipo">
        ${[
          ["texto", "Texto"],
          ["numero", "Numero"],
          ["moeda", "Moeda"],
          ["data", "Data"],
          ["select", "Selecao unica"],
          ["multiselect", "Selecao multipla"],
          ["boolean", "Sim/Nao"],
        ].map(([tipo, label]) => `<option value="${tipo}" ${tipo === (column.tipo || "texto") ? "selected" : ""}>${label}</option>`).join("")}
      </select>
      <label class="mini-check" title="Obrigatoria"><input name="column_obrigatoria" type="checkbox" aria-label="Obrigatoria" ${column.obrigatoria ? "checked" : ""} /></label>
      <label class="mini-check" title="Chave"><input name="column_identificador" type="checkbox" aria-label="Chave" ${column.identificador ? "checked" : ""} /></label>
      <label class="mini-check" title="Automatica"><input name="column_automatico" type="checkbox" aria-label="Automatica" ${column.automatico ? "checked" : ""} /></label>
      <select name="column_auto_tipo" title="Valor automático">
        ${[
          ["", "Manual"],
          ["today", "Data atual"],
          ["usuario", "Usuário"],
          ["carteira", "Carteira"],
        ].map(([value, label]) => `<option value="${value}" ${value === (column.auto_tipo || "") ? "selected" : ""}>${label}</option>`).join("")}
      </select>
      <label class="mini-check" title="Mostrar no cadastro"><input name="column_mostrar_cadastro" type="checkbox" aria-label="Mostrar no cadastro" ${column.mostrar_cadastro !== false ? "checked" : ""} /></label>
      <label class="mini-check" title="Exibir no sistema negocial"><input name="column_visivel" type="checkbox" aria-label="Exibir no sistema negocial" ${column.visivel !== false ? "checked" : ""} /></label>
      <select name="column_cadastro_etapa" title="Etapa do cadastro">
        <option value="1" ${Number(column.cadastro_etapa || 2) === 1 ? "selected" : ""}>Etapa 1</option>
        <option value="2" ${Number(column.cadastro_etapa || 2) === 2 ? "selected" : ""}>Etapa 2</option>
      </select>
      <input class="column-max-length" name="column_max_length" type="number" min="1" step="1" placeholder="Max. caract." value="${column.max_length || ""}" />
      <input name="column_opcoes" placeholder="Opcoes do select, separadas por virgula" value="${escapeAttr(options)}" />
      <button class="icon-btn" type="button" data-remove-column="${index}">&times;</button>
    </div>
  `;
  }).join("");
  target.querySelectorAll("[data-move-column]").forEach((button) => {
    button.addEventListener("click", () => {
      const next = readCarteiraColumns();
      const from = Number(button.dataset.moveColumn);
      const to = from + Number(button.dataset.direction);
      if (to < 0 || to >= next.length) return;
      [next[from], next[to]] = [next[to], next[from]];
      renderCarteiraColumns(next);
    });
  });
  target.querySelectorAll("[data-remove-column]").forEach((button) => {
    button.addEventListener("click", () => {
      const next = readCarteiraColumns();
      next.splice(Number(button.dataset.removeColumn), 1);
      renderCarteiraColumns(next.length ? next : DEFAULT_COLUMNS);
    });
  });
  refreshHoColumnOptions($("#carteiraForm"));
}

function readCarteiraColumns() {
  return [...document.querySelectorAll("#carteiraColumns [data-carteira-column]")].map((row) => ({
    chave: String(row.dataset.columnKey || "").trim(),
    nome: row.querySelector("[name='column_nome']").value.trim(),
    tipo: row.querySelector("[name='column_tipo']").value,
    obrigatoria: row.querySelector("[name='column_obrigatoria']").checked,
    identificador: row.querySelector("[name='column_identificador']").checked,
    automatico: row.querySelector("[name='column_automatico']").checked,
    auto_tipo: row.querySelector("[name='column_auto_tipo']").value,
    mostrar_cadastro: row.querySelector("[name='column_mostrar_cadastro']").checked,
    visivel: row.querySelector("[name='column_visivel']").checked,
    cadastro_etapa: Number(row.querySelector("[name='column_cadastro_etapa']").value || 2),
    max_length: row.querySelector("[name='column_max_length']").value,
    opcoes: row.querySelector("[name='column_opcoes']").value.split(",").map((item) => item.trim()).filter(Boolean),
  })).filter((column) => column.nome);
}

function findCarteira(nome) {
  const normalized = normalizeWallet(nome);
  return [...(state.carteira.adminItems || []), ...(state.carteiras || [])]
    .find((item) => normalizeWallet(item.nome) === normalized);
}

export function resetCarteiraSelection() {
  state.carteira.selected = null;
  state.carteira.query = "";
  state.carteira.monitorTab = "timeline";
  state.carteira.workspaceTab = "overview";
  $("#carteiraClientSearch").value = "";
  $("#pageTitle").textContent = "Carteiras";
  expanded.clear();
  collapsedMonths.clear();
  renderCarteiras();
}

export function renderCarteiraMonitor() {
  const carteira = state.carteira.selected;
  if (!carteira) return;
  ensureEvents();
  const query = ($("#carteiraClientSearch")?.value || "").trim().toLowerCase();
  state.carteira.query = query;
  const registered = carteiraGroups().find((group) => normalizeWallet(group.carteira) === normalizeWallet(carteira));
  const allEntries = carteiraEntries(carteira, "");
  const filters = carteiraFilters();
  const entries = carteiraEntries(carteira, query).filter((entry) => matchesFilters(entry, filters));

  $("#carteiraMonitorTitle").textContent = carteira;
  $("#carteiraMonitorMeta").textContent = `${registered?.items?.length ?? 0} negociadores · ${registered?.negocial?.colunas?.length ?? 0} colunas`;
  $("#carteiraMonitorStatus").textContent = registered?.active === false ? "Inativa" : "Ativa";
  $("#carteiraMonitorStatus").classList.toggle("inactive", registered?.active === false);

  bindCarteiraMonitorControls();
  if (!query) {
    renderCarteiraRecentActivity(allEntries.filter((entry) => matchesFilters(entry, filters)));
    return;
  }
  renderCarteiraClientWorkspace(entries, query);
}

function bindCarteiraMonitorControls() {
  const clearButton = $("#clearCarteiraFiltersBtn");
  if (clearButton) {
    clearButton.onclick = () => {
      ["carteiraClientSearch", "carteiraPeriodFilter", "carteiraUserFilter", "carteiraTypeFilter"].forEach((id) => {
        const control = $(`#${id}`);
        if (control) control.value = "";
      });
      state.carteira.monitorTab = "timeline";
      renderCarteiraMonitor();
    };
  }
  document.querySelectorAll("[data-carteira-monitor-tab]").forEach((button) => {
    const tab = button.dataset.carteiraMonitorTab;
    button.classList.toggle("active", tab === state.carteira.monitorTab);
    button.onclick = () => {
      state.carteira.monitorTab = tab;
      renderCarteiraMonitor();
    };
  });
}

function renderCarteiraRecentActivity(entries) {
  $("#carteiraClientSummary").classList.add("hidden");
  $("#carteiraMonitorTabs").classList.add("hidden");
  $("#carteiraTimelineActions").classList.add("hidden");
  $("#carteiraMonitorSectionTitle").textContent = "Alterações recentes";
  $("#carteiraMonitorSectionMeta").textContent = eventsLoading
    ? "Carregando os movimentos da carteira..."
    : `${entries.length} eventos registrados · selecione um cliente para investigar`;
  const recent = entries.slice(0, 12);
  $("#carteiraTimeline").innerHTML = recent.length
    ? `<div class="carteira-recent-list">${recent.map(renderRecentEntry).join("")}</div>`
    : `<div class="carteira-monitor-empty"><strong>Nenhuma atividade encontrada</strong><span>Ajuste os filtros ou aguarde uma nova atualização da carteira.</span></div>`;
  document.querySelectorAll("[data-carteira-client]").forEach((button) => {
    button.onclick = () => {
      $("#carteiraClientSearch").value = button.dataset.carteiraClient || "";
      state.carteira.monitorTab = "timeline";
      renderCarteiraMonitor();
    };
  });
}

function renderRecentEntry(entry) {
  const client = entry.group.client || "Cliente não identificado";
  const canOpen = Boolean(entry.group.client);
  return `
    <button class="carteira-recent-item" type="button" ${canOpen ? `data-carteira-client="${escapeAttr(client)}"` : "disabled"}>
      <span class="carteira-recent-icon ${escapeAttr(entry.priority)}" aria-hidden="true"></span>
      <span class="carteira-recent-main">
        <strong>${escapeHtml(client)}</strong>
        <small>${escapeHtml(entry.description)}</small>
      </span>
      <span class="carteira-recent-user">${escapeHtml(entry.user)}</span>
      <time datetime="${escapeAttr(entry.date.toISOString())}">${escapeHtml(formatCompactDate(entry.date))}</time>
      <b>${escapeHtml(entry.type)}</b>
    </button>`;
}

function renderCarteiraClientWorkspace(entries, query) {
  const clients = [...new Set(entries.map((entry) => entry.group.client).filter(Boolean))];
  const displayClient = clients.length === 1 ? clients[0] : (clients[0] || query);
  const users = [...new Set(entries.map((entry) => entry.user).filter(Boolean))];
  const lastEntry = entries[0];
  const firstEntry = entries.at(-1);
  const summary = $("#carteiraClientSummary");
  summary.classList.remove("hidden");
  summary.innerHTML = `
    <div class="carteira-client-primary">
      <span class="carteira-client-avatar" aria-hidden="true">${escapeHtml(clientInitials(displayClient))}</span>
      <div>
        <span>${clients.length > 1 ? `${clients.length} clientes encontrados` : "Cliente selecionado"}</span>
        <strong>${escapeHtml(displayClient)}</strong>
      </div>
    </div>
    <dl>
      <div><dt>Eventos</dt><dd>${entries.length}</dd></div>
      <div><dt>Responsáveis</dt><dd>${users.length}</dd></div>
      <div><dt>Período</dt><dd>${firstEntry ? escapeHtml(firstEntry.date.toLocaleDateString("pt-BR")) : "-"} até ${lastEntry ? escapeHtml(lastEntry.date.toLocaleDateString("pt-BR")) : "-"}</dd></div>
      <div><dt>Última atualização</dt><dd>${lastEntry ? escapeHtml(formatCompactDate(lastEntry.date)) : "-"}</dd></div>
    </dl>`;

  $("#carteiraMonitorTabs").classList.remove("hidden");
  document.querySelectorAll("[data-carteira-monitor-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.carteiraMonitorTab === state.carteira.monitorTab);
  });
  const tab = state.carteira.monitorTab || "timeline";
  const titles = {
    timeline: ["Timeline consolidada", "Alterações organizadas cronologicamente"],
    current: ["Dados atuais", "Último valor conhecido de cada campo"],
    corrections: ["Correções do backoffice", "Ajustes manuais realizados pela gestão"],
    audit: ["Auditoria técnica", "Rastreabilidade completa dos eventos"],
  };
  $("#carteiraMonitorSectionTitle").textContent = titles[tab][0];
  $("#carteiraMonitorSectionMeta").textContent = entries.length
    ? `${titles[tab][1]} · ${entries.length} eventos encontrados`
    : "Nenhum histórico encontrado para os filtros informados";
  $("#carteiraTimelineActions").classList.toggle("hidden", tab !== "timeline" || !entries.length);

  if (!entries.length) {
    $("#carteiraTimeline").innerHTML = `<div class="carteira-monitor-empty"><strong>Nenhum histórico encontrado</strong><span>Revise o cliente ou os filtros aplicados.</span></div>`;
    return;
  }
  if (tab === "current") $("#carteiraTimeline").innerHTML = renderCurrentData(entries);
  else if (tab === "corrections") $("#carteiraTimeline").innerHTML = renderCorrections(entries);
  else if (tab === "audit") $("#carteiraTimeline").innerHTML = renderAudit(entries);
  else {
    $("#carteiraTimeline").innerHTML = renderGroupedEntries(entries);
    bindToggles();
  }
}

function renderCurrentData(entries) {
  const values = new Map();
  [...entries].reverse().forEach((entry) => {
    entry.group.changes.forEach((change) => {
      const column = String(change.column || labelChange(change) || "Campo").trim();
      if (column) values.set(column, change.after);
    });
  });
  if (!values.size) return `<div class="carteira-monitor-empty"><strong>Sem dados atuais</strong><span>Os eventos não possuem campos estruturados.</span></div>`;
  return `<div class="carteira-current-grid">${[...values.entries()].map(([column, value]) => `
    <div><span>${escapeHtml(column)}</span><strong>${escapeHtml(formatValue(value))}</strong></div>`).join("")}</div>`;
}

function renderCorrections(entries) {
  const corrections = entries.filter(({ event }) => {
    const metadata = event.metadata || {};
    const source = `${event.event_type || ""} ${metadata.source || ""} ${metadata.origin || ""}`.toLowerCase();
    return source.includes("manual") || source.includes("gerencial") || source.includes("backoffice");
  });
  if (!corrections.length) return `<div class="carteira-monitor-empty"><strong>Nenhuma correção gerencial</strong><span>Não há ajustes manuais registrados para este cliente.</span></div>`;
  return `<div class="carteira-correction-list">${corrections.map((entry) => `
    <article><span class="carteira-recent-icon changed"></span><div><strong>${escapeHtml(entry.description)}</strong><small>${escapeHtml(entry.user)} · ${escapeHtml(formatCompactDate(entry.date))}</small></div></article>`).join("")}</div>`;
}

function renderAudit(entries) {
  return `<div class="carteira-audit-table-wrap"><table class="carteira-audit-table"><thead><tr><th>Data e hora</th><th>Responsável</th><th>Evento</th><th>Origem</th><th>Registro</th><th>Log</th></tr></thead><tbody>${entries.map((entry) => `
    <tr><td>${escapeHtml(entry.date.toLocaleString("pt-BR"))}</td><td>${escapeHtml(entry.user)}</td><td>${escapeHtml(entry.type)}</td><td>${escapeHtml(originLabel(entry.event.event_type))}</td><td>${escapeHtml(formatValue(entry.group.line || "-"))}</td><td>#${escapeHtml(String(entry.event.id || "-"))}</td></tr>`).join("")}</tbody></table></div>`;
}

function formatCompactDate(date) {
  const today = new Date();
  const sameDay = date.toDateString() === today.toDateString();
  return sameDay
    ? `Hoje, ${date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`
    : date.toLocaleString("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function clientInitials(value) {
  return String(value || "C").trim().split(/\s+/).slice(0, 2).map((part) => part[0] || "").join("").toUpperCase();
}

export function expandCarteiraHistory() {
  carteiraEntries(state.carteira.selected, state.carteira.query).forEach((entry) => expanded.add(entry.id));
  renderCarteiraMonitor();
}

export function collapseCarteiraHistory() {
  expanded.clear();
  renderCarteiraMonitor();
}

function openCarteira(carteira) {
  state.carteira.selected = carteira;
  state.carteira.query = "";
  state.carteira.monitorTab = "timeline";
  state.carteira.workspaceTab = "overview";
  $("#pageTitle").textContent = `Carteira - ${carteira}`;
  $("#carteiraClientSearch").value = "";
  expanded.clear();
  collapsedMonths.clear();
  renderCarteiras();
}

function carteiraGroups() {
  const groups = new Map();
  const source = state.carteira.adminItems?.length ? state.carteira.adminItems : state.carteiras;
  const byName = new Map((source || []).map((item) => [normalizeWallet(item.nome), item]));
  carteiraNames().forEach((carteira) => {
    const registered = byName.get(normalizeWallet(carteira));
    groups.set(carteira, {
      items: [],
      negocial: registered?.negocial,
      active: registered ? Boolean(registered.active) : true,
      description: registered?.descricao || registered?.negocial?.descricao || "",
      updatedAt: registered?.negocial?.updated_at || registered?.updated_at || "",
    });
  });
  (source || []).forEach((registered) => {
    const carteira = registered.nome;
    if (!groups.has(carteira)) {
      groups.set(carteira, {
        items: [],
        negocial: registered.negocial,
        active: Boolean(registered.active),
        description: registered.descricao || registered.negocial?.descricao || "",
        updatedAt: registered.negocial?.updated_at || registered.updated_at || "",
      });
    }
  });
  [...(state.negociadores || [])]
    .sort((a, b) => String(a.nome || "").localeCompare(String(b.nome || "")))
    .forEach((item) => {
      const carteira = item.carteira || "Carteira nao informada";
      if (!groups.has(carteira)) groups.set(carteira, { items: [], active: true, description: "", updatedAt: "" });
      groups.get(carteira).items.push(item);
    });
  return [...groups.entries()]
    .filter(([carteira]) => carteira)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([carteira, payload]) => ({
      carteira,
      items: payload.items,
      negocial: payload.negocial,
      active: payload.active !== false,
      description: payload.description || "",
      updatedAt: payload.updatedAt || "",
    }));
}

function adminDate(value) {
  const parsed = new Date(String(value || "").replace(" ", "T"));
  return Number.isNaN(parsed.getTime()) ? 0 : parsed.getTime();
}

function formatAdminDate(value) {
  const timestamp = adminDate(value);
  if (!timestamp) return "não informada";
  const date = new Date(timestamp);
  return `${date.toLocaleDateString("pt-BR")} às ${date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`;
}

async function ensureEvents() {
  if (eventsLoaded || eventsLoading) return;
  eventsLoading = true;
  try {
    state.allEvents = await api("/api/events?limit=5000");
    eventsLoaded = true;
  } catch {
    state.allEvents = [];
  } finally {
    eventsLoading = false;
    if (state.mode === "carteiras" && state.carteira.selected) renderCarteiras();
  }
}

function carteiraEntries(carteira, query) {
  const wallet = normalizeWallet(carteira);
  return [...(state.allEvents || [])]
    .filter((event) => normalizeWallet(event.carteira || event.metadata?.carteira || "") === wallet)
    .flatMap((event) => {
      const date = new Date(event.changed_at);
      if (Number.isNaN(date.getTime())) return [];
      return groupTimelineChangesByLine(event)
        .filter((group) => !query || groupMatchesQuery(group, query))
        .map((group, index) => {
          const type = historyType(group.changes);
          return {
            id: `${event.id || event.changed_at}-${group.line || index}`,
            event,
            group,
            date,
            monthKey: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`,
            monthLabel: date.toLocaleDateString("pt-BR", { month: "long", year: "numeric" }).replace(/^\w/, (char) => char.toUpperCase()),
            user: event.negociador_nome || "Responsavel",
            type,
            priority: priorityClass(group.changes),
            description: historyDescription(group, type),
          };
        });
    })
    .sort((a, b) => b.date - a.date);
}

function renderGroupedEntries(entries) {
  const groups = new Map();
  entries.forEach((entry) => {
    if (!groups.has(entry.monthKey)) groups.set(entry.monthKey, { label: entry.monthLabel, entries: [] });
    groups.get(entry.monthKey).entries.push(entry);
  });
  return [...groups.entries()].map(([monthKey, group]) => {
    const isCollapsed = collapsedMonths.has(monthKey);
    return `
      <section class="history-month ${isCollapsed ? "collapsed" : ""}">
        <button class="history-month-toggle" type="button" data-carteira-month="${escapeAttr(monthKey)}" aria-expanded="${String(!isCollapsed)}">
          <span>${escapeHtml(group.label)}</span>
          <strong>${group.entries.length} eventos</strong>
          <b>${isCollapsed ? "Expandir" : "Recolher"}</b>
        </button>
        ${isCollapsed ? "" : `<div class="history-events">${group.entries.map(renderEntry).join("")}</div>`}
      </section>
    `;
  }).join("");
}

function renderEntry(entry) {
  const isExpanded = expanded.has(entry.id);
  return `
    <article class="history-event ${escapeAttr(entry.priority)}">
      <button class="history-summary" type="button" data-carteira-event="${escapeAttr(entry.id)}" aria-expanded="${String(isExpanded)}">
        <span class="history-dot"></span>
        <span>
          <strong>${escapeHtml(entry.date.toLocaleString("pt-BR"))} - ${escapeHtml(entry.user)}</strong>
          <em>${escapeHtml(entry.type)} · ${escapeHtml(entry.event.sheet || "")}</em>
          <small>${escapeHtml(entry.description)}</small>
        </span>
        <b>${isExpanded ? "Recolher" : "Expandir"}</b>
      </button>
      ${isExpanded ? renderDetails(entry) : ""}
    </article>
  `;
}

function renderDetails(entry) {
  return `
    <div class="history-details">
      <div class="meta-grid">
        <div><strong>Negociador</strong><br>${escapeHtml(entry.user)}</div>
        <div><strong>Carteira</strong><br>${escapeHtml(entry.event.carteira || entry.event.metadata?.carteira || "")}</div>
        <div><strong>Origem</strong><br>${escapeHtml(originLabel(entry.event.event_type))}</div>
        <div><strong>ID do log</strong><br>${escapeHtml(String(entry.event.id || entry.id))}</div>
        <div><strong>Sheet</strong><br>${escapeHtml(entry.event.sheet || "")}</div>
        <div><strong>Linha/registro</strong><br>${escapeHtml(formatValue(entry.group.line || "Nao localizado"))}</div>
      </div>
      ${renderMiniRowDiff(entry.group.changes, entry.group.line)}
    </div>
  `;
}

function bindToggles() {
  document.querySelectorAll("[data-carteira-event]").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.dataset.carteiraEvent;
      if (expanded.has(id)) expanded.delete(id);
      else expanded.add(id);
      renderCarteiraMonitor();
    });
  });
  document.querySelectorAll("[data-carteira-month]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.carteiraMonth;
      if (collapsedMonths.has(key)) collapsedMonths.delete(key);
      else collapsedMonths.add(key);
      renderCarteiraMonitor();
    });
  });
}

function carteiraFilters() {
  return {
    period: $("#carteiraPeriodFilter")?.value.trim().toLowerCase() || "",
    user: $("#carteiraUserFilter")?.value.trim().toLowerCase() || "",
    type: $("#carteiraTypeFilter")?.value.trim().toLowerCase() || "",
  };
}

function matchesFilters(entry, filters) {
  const dateText = entry.date.toLocaleDateString("pt-BR").toLowerCase();
  const isoText = entry.date.toISOString().slice(0, 10).toLowerCase();
  return (!filters.period || dateText.includes(filters.period) || isoText.includes(filters.period) || entry.monthKey.includes(filters.period))
    && (!filters.user || entry.user.toLowerCase().includes(filters.user))
    && (!filters.type || entry.type.toLowerCase().includes(filters.type));
}

function groupMatchesQuery(group, query) {
  if (!query) return false;
  const haystack = [
    group.client,
    group.line,
    ...group.changes.flatMap((change) => [change.column, change.before, change.after, change.type]),
  ].map((value) => String(value ?? "").toLowerCase()).join(" ");
  return haystack.includes(query);
}

function historyType(changes) {
  if (changes.some((change) => change.type === "row_added")) return "Cadastro";
  if (changes.some((change) => change.type === "row_removed")) return "Exclusao";
  const columns = changes.map((change) => String(change.column || "").toLowerCase()).join(" ");
  if (columns.includes("telefone") || columns.includes("fone") || columns.includes("celular")) return "Telefone";
  if (columns.includes("email") || columns.includes("e-mail")) return "E-mail";
  if (columns.includes("endereco") || columns.includes("endereço") || columns.includes("cidade") || columns.includes("uf")) return "Endereco";
  if (columns.includes("contrato") || columns.includes("npj") || columns.includes("processo")) return "Contrato";
  if (columns.includes("status") || columns.includes("situacao") || columns.includes("situação")) return "Status";
  if (columns.includes("observacao") || columns.includes("observação") || columns.includes("obs")) return "Observacao";
  if (changes.some((change) => change.type === "cell_filled")) return "Cadastro";
  return "Alteracao";
}

function historyDescription(group, type) {
  const first = group.changes[0] || {};
  const field = first.column || labelChange(first);
  const client = group.client || `Linha ${group.line || "nao localizada"}`;
  if (group.changes.length > 1) return `${type}: ${group.changes.length} campos alterados em ${client}`;
  return `${type}: ${field} de "${formatValue(first.before)}" para "${formatValue(first.after)}"`;
}

function priorityClass(changes) {
  if (changes.some((change) => change.type === "row_removed" || change.type === "cell_cleared")) return "removed";
  if (changes.some((change) => change.type === "row_added" || change.type === "cell_filled")) return "added";
  return "changed";
}

function originLabel(eventType) {
  return {
    file_changed: "Importacao/arquivo monitorado",
    manual_update: "Atualizacao manual",
    initial_snapshot: "Sistema",
    sheet_changed: "Sistema",
    new_month: "Sistema",
  }[eventType] || "Sistema";
}

function normalizeWallet(value) {
  return String(value || "Carteira nao informada").trim().toLowerCase();
}
