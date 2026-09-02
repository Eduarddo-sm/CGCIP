import { api } from "../core/api.js";
import { $ } from "../core/dom.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { state } from "../core/state.js";
import { toast } from "../core/toast.js";
import { renderVisibility } from "../layout/visibility.js?v=20260810-highlighted-screens-1";
import { renderConsolidatedDynamicTool } from "./carteiraWorkspace.js?v=20260825-beta-repurchase-1";
import {
  cardFieldRoles,
  dashboardAggregations,
  dashboardBlockTypes,
  dashboardConditionOperators,
  deadlineFilterOptions,
  deadlineModes,
  defaultDashboardConfig,
  defaultCardActionsConfig,
  defaultDefinition,
  defaultFilterConfig,
  defaultGroupingConfig,
  defaultScreens,
  fieldTypes,
  flowTemplates,
  normalizedFilterConfig,
  normalizedCardActionsConfig,
  normalizedGroupingConfig,
  screenComponents,
  screenTypes,
} from "./ferramentaBuilderDefinitions.js?v=20260811-card-updated-toggle-1";

let tools = [];
let wallets = [];
let negotiators = [];
let editing = null;
let recordsContext = null;
let recordsLoadSequence = 0;
let builderTab = "geral";
let permissionTab = "wallets";
let previewAudience = "negocial";
let previewScreenId = "";
let previewRenderFrame = 0;
let builderScreenIndex = 0;
let builderDirty = false;
let highlightedTools = [];

function ensureScreens() {
  if (!Array.isArray(editing.configuracao?.telas) || !editing.configuracao.telas.length) {
    editing.configuracao = { ...(editing.configuracao || {}), telas: defaultScreens(editing.tipo === "SOLICITACAO" ? "approval" : "simple") };
  }
  return editing.configuracao.telas;
}

function ensureDashboardConfig(screen) {
  if (!screen.dashboard || !Array.isArray(screen.dashboard.blocks) || !screen.dashboard.blocks.length) {
    screen.dashboard = structuredClone(defaultDashboardConfig());
  }
  screen.dashboard.columns = 12;
  return screen.dashboard;
}

function createDashboardBlock(type = "metric", index = 0) {
  const labels = Object.fromEntries(dashboardBlockTypes);
  return {
    id: `${type}-${Date.now()}-${index}`,
    tipo: type,
    titulo: labels[type] || "Novo bloco",
    agregacao: "count",
    campo: "",
    campo_secundario: "",
    agrupador: "",
    condicao_campo: "",
    condicao_operador: "eq",
    condicao_valor: "",
    status_codes: [],
    cor: editing?.cor || "#2563eb",
    largura: type === "metric" ? 3 : type === "status" ? 9 : 6,
    limite: type === "recent" ? 6 : 8,
    periodo: "day",
  };
}

function applyFlowTemplate(templateName) {
  const template = flowTemplates[templateName];
  if (!template) return;
  editing.statuses = template.statuses.map((item) => ({ ...item }));
  editing.transicoes = template.transicoes.map((item) => ({ ...item }));
  editing.configuracao = { ...(editing.configuracao || {}), telas: defaultScreens(templateName) };
  builderScreenIndex = 0;
  previewScreenId = "";
  markBuilderDirty();
  renderStatusRows();
  renderTransitionRows();
  renderFlowPreview();
  renderMetricOptions();
  renderScreenRows();
}

function versionBadges(item) {
  return (item.versoes || []).slice(0, 3).map((version) => `
    <span class="dynamic-tool-version ${version.status === "PUBLICADA" ? "published" : version.status === "RASCUNHO" ? "draft" : ""}">
      v${version.numero} ${version.status.toLowerCase()}
    </span>
  `).join("");
}

function formatTrashDeadline(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function renderList() {
  const target = $("#dynamicToolsList");
  if (!target) return;
  if (!tools.length) {
    target.innerHTML = `<div class="dynamic-builder-empty">Nenhuma ferramenta criada.</div>`;
    return;
  }
  const orderedTools = [...tools].sort((left, right) => (
    Number(left.exclusao_pendente) - Number(right.exclusao_pendente)
    || String(left.nome || "").localeCompare(String(right.nome || ""), "pt-BR")
  ));
  target.innerHTML = orderedTools.map((item) => {
    const hasDraft = item.versoes?.some((version) => version.status === "RASCUNHO");
    const hasPublished = item.versoes?.some((version) => version.status === "PUBLICADA");
    const lifecycleReason = item.carteiras_vinculadas
      ? `Vinculada a ${item.carteiras_vinculadas} carteira(s). Desvincule antes de alterar a situacao.`
      : "";
    if (item.exclusao_pendente) {
      return `
        <article class="dynamic-tool-admin-item in-trash">
          <span class="dynamic-tool-admin-icon">${escapeHtml(item.icone || "F")}</span>
          <div class="dynamic-tool-admin-copy">
            <strong>${escapeHtml(item.nome)}</strong>
            <small>Na lixeira · exclusao definitiva em ${escapeHtml(formatTrashDeadline(item.purge_after))}</small>
            <span class="dynamic-tool-admin-flags"><em>Restauravel por 3 dias</em></span>
          </div>
          <div class="dynamic-tool-admin-stat"><strong>${item.registros}</strong><span>registros preservados</span></div>
          <div class="dynamic-tool-admin-stat"><strong>${item.carteiras_vinculadas}</strong><span>carteiras preservadas</span></div>
          <div class="dynamic-tool-admin-stat"><strong>Lixeira</strong><span>situacao</span></div>
          <div class="dynamic-tool-admin-actions">
            <button class="primary-btn" type="button" data-tool-lifecycle="${item.id}" data-operation="restaurar">Restaurar</button>
          </div>
        </article>
      `;
    }
    return `
      <article class="dynamic-tool-admin-item">
        <span class="dynamic-tool-admin-icon">${escapeHtml(item.icone || "F")}</span>
        <div class="dynamic-tool-admin-copy">
          <strong>${escapeHtml(item.nome)}</strong>
          <small>${escapeHtml(item.tipo === "SOLICITACAO" ? "Fluxo de solicitacao" : "Cadastro operacional")} · ${versionBadges(item)}</small>
          <span class="dynamic-tool-admin-flags">
            ${item.destaque_gerencial ? `<em>Destacada na sidebar</em>` : ""}
            ${item.carteiras_vinculadas ? `<em>${item.carteiras_vinculadas} carteira(s)</em>` : ""}
          </span>
        </div>
        <div class="dynamic-tool-admin-stat"><strong>${item.registros}</strong><span>registros</span></div>
        <div class="dynamic-tool-admin-stat"><strong>${item.permissoes}</strong><span>escopos</span></div>
        <div class="dynamic-tool-admin-stat"><strong>${item.active ? "Ativa" : "Inativa"}</strong><span>situacao</span></div>
        <div class="dynamic-tool-admin-actions">
          ${hasPublished ? `<button class="secondary-btn" type="button" data-tool-records="${item.id}">Registros</button>` : ""}
          ${hasPublished && !hasDraft ? `<button class="secondary-btn" type="button" data-tool-version="${item.id}">Nova versao</button>` : ""}
          ${hasDraft ? `<button class="primary-btn" type="button" data-tool-publish="${item.id}">Publicar</button>` : ""}
          <button class="secondary-btn" type="button" data-tool-edit="${item.id}">${hasDraft ? "Editar rascunho" : "Visualizar"}</button>
          <button class="secondary-btn" type="button" data-tool-lifecycle="${item.id}" data-operation="${item.active ? "inativar" : "ativar"}"
            ${item.active && !item.pode_inativar ? "disabled" : ""} title="${escapeHtml(item.active && !item.pode_inativar ? lifecycleReason : "")}">
            ${item.active ? "Inativar" : "Ativar"}
          </button>
          <button class="secondary-btn danger" type="button" data-tool-lifecycle="${item.id}" data-operation="excluir"
            title="Mover para a lixeira por 3 dias">Excluir</button>
        </div>
      </article>
    `;
  }).join("");
  target.querySelectorAll("[data-tool-edit]").forEach((button) => {
    button.addEventListener("click", () => openToolBuilder(Number(button.dataset.toolEdit)));
  });
  target.querySelectorAll("[data-tool-publish]").forEach((button) => {
    button.addEventListener("click", () => publishTool(Number(button.dataset.toolPublish)));
  });
  target.querySelectorAll("[data-tool-version]").forEach((button) => {
    button.addEventListener("click", () => createVersion(Number(button.dataset.toolVersion)));
  });
  target.querySelectorAll("[data-tool-records]").forEach((button) => {
    button.addEventListener("click", () => openToolRecords(Number(button.dataset.toolRecords)));
  });
  target.querySelectorAll("[data-tool-lifecycle]").forEach((button) => {
    button.addEventListener("click", () => changeToolLifecycle(
      Number(button.dataset.toolLifecycle),
      button.dataset.operation,
    ));
  });
}

async function changeToolLifecycle(toolId, operation) {
  const messages = {
    ativar: "Reativar esta ferramenta?",
    inativar: "Inativar esta ferramenta? Ela deixara de aparecer nos sistemas.",
    excluir: "Mover esta ferramenta para a lixeira? Ela sera desativada agora e excluida definitivamente depois de 3 dias. Durante esse prazo, a acao podera ser desfeita.",
    restaurar: "Restaurar esta ferramenta e seus vinculos como estavam antes da exclusao?",
  };
  if (!window.confirm(messages[operation])) return;
  try {
    await api(`/api/config/ferramentas-negociais/${toolId}/${operation}`, { method: "POST", body: "{}" });
    const feedback = {
      excluir: "Ferramenta movida para a lixeira por 3 dias.",
      restaurar: "Ferramenta restaurada com sucesso.",
      ativar: "Ferramenta ativada.",
      inativar: "Ferramenta inativada.",
    };
    toast(feedback[operation] || "Ferramenta atualizada.");
    await Promise.all([loadDynamicToolsAdmin(), loadHighlightedToolNavigation()]);
  } catch (error) {
    toast(error.message);
  }
}

export async function loadHighlightedToolNavigation() {
  const target = $("#toolDropdown");
  if (!target) return;
  target.querySelectorAll("[data-highlighted-tool-id]").forEach((button) => button.remove());
  try {
    const payload = await api("/api/ferramentas-destacadas");
    highlightedTools = payload.items || [];
    const officialParecer = highlightedTools.some((item) => String(item.slug || "").toLowerCase() === "pareceres");
    const legacyParecerButton = target.querySelector('[data-tool="parecer"]');
    if (legacyParecerButton) {
      legacyParecerButton.hidden = officialParecer;
      legacyParecerButton.setAttribute("aria-hidden", String(officialParecer));
    }
    highlightedTools.forEach((item) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.highlightedToolId = String(item.id);
      button.title = item.nome;
      button.setAttribute("aria-label", item.nome);
      button.style.setProperty("--dynamic-tool-color", item.cor || "#2563eb");
      button.innerHTML = `
        <span class="tool-icon dynamic-tool-nav-icon" aria-hidden="true">${escapeHtml(item.icone || "F")}</span>
        <strong>${escapeHtml(item.nome).toUpperCase()}</strong>
      `;
      button.addEventListener("click", async () => {
        target.querySelectorAll("button").forEach((entry) => entry.classList.remove("active"));
        button.classList.add("active");
        await showHighlightedTool(Number(item.id));
      });
      target.appendChild(button);
    });
  } catch (error) {
    // Perfis sem acesso administrativo mantem apenas os modulos fixos.
  }
}

export async function showHighlightedTool(toolId) {
  let tool = highlightedTools.find((item) => Number(item.id) === Number(toolId));
  if (!tool) {
    const payload = await api("/api/ferramentas-destacadas");
    highlightedTools = payload.items || [];
    tool = highlightedTools.find((item) => Number(item.id) === Number(toolId));
  }
  if (!tool) throw new Error("Ferramenta destacada nao encontrada ou indisponivel.");

  state.mode = "dynamicTool";
  state.activeGroup = "backoffice";
  state.dynamicToolId = Number(tool.id);
  $("#pageTitle").textContent = tool.nome;
  renderVisibility();
  document.querySelectorAll("[data-highlighted-tool-id]").forEach((button) => {
    button.classList.toggle("active", Number(button.dataset.highlightedToolId) === Number(tool.id));
  });
  const target = $("#dynamicToolContent");
  if (!target) return;
  target.innerHTML = '<div class="carteira-workspace-loading"><span></span><strong>Carregando ferramenta...</strong></div>';
  await renderConsolidatedDynamicTool(target, tool, {
    onOpenToolRecord: (currentToolId, recordId) => openToolRecordDirect(currentToolId, recordId, {
      onChanged: async () => {
        if (state.mode !== "dynamicTool" || Number(state.dynamicToolId) !== Number(tool.id)) return;
        await showHighlightedTool(tool.id);
      },
    }),
    onError: (error) => toast(error.message || "Nao foi possivel abrir o registro."),
  });
}

export async function loadDynamicToolsAdmin() {
  const target = $("#dynamicToolsList");
  if (target) target.innerHTML = `<div class="dynamic-builder-empty">Carregando ferramentas...</div>`;
  try {
    const [toolsPayload, usersPayload, walletsPayload] = await Promise.all([
      api("/api/config/ferramentas-negociais"),
      api("/api/config/users"),
      api("/api/carteiras"),
    ]);
    tools = toolsPayload.items || [];
    negotiators = usersPayload.negociadores || [];
    wallets = (walletsPayload.carteiras || walletsPayload.items || walletsPayload || []).map((item) => item.nome || item.name || item).filter(Boolean);
    renderList();
  } catch (error) {
    if (target) target.innerHTML = `<div class="dynamic-builder-empty">${escapeHtml(error.message)}</div>`;
  }
}

function optionList(options, selected) {
  return options.map(([value, label]) => `<option value="${value}" ${value === selected ? "selected" : ""}>${label}</option>`).join("");
}

function conditionValueList(value) {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
  return String(value ?? "").split(/[\n,;]+/).map((item) => item.trim()).filter(Boolean);
}

function rowCheck(label, attr, checked) {
  return `<label class="dynamic-builder-check"><input type="checkbox" data-${attr} ${checked ? "checked" : ""}><span>${label}</span></label>`;
}

function statusCodeFromName(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 64);
}

function finalizeStatusCodes() {
  const used = new Set();
  const replacements = new Map();
  document.querySelectorAll("[data-status-index]").forEach((row, index) => {
    const nameInput = row.querySelector("[data-status-name]");
    const codeInput = row.querySelector("[data-status-code]");
    let code = statusCodeFromName(codeInput.value || nameInput.value || `ETAPA_${index + 1}`);
    const base = code || `ETAPA_${index + 1}`;
    let suffix = 2;
    while (used.has(code)) code = `${base}_${suffix++}`;
    used.add(code);
    const previous = codeInput.value;
    codeInput.value = code;
    if (previous && previous !== code) replacements.set(previous, code);
  });
  if (!replacements.size) return;
  document.querySelectorAll("[data-transition-origin] option,[data-transition-target] option,[data-screen-status],[data-screen-history-status]").forEach((control) => {
    if (replacements.has(control.value)) control.value = replacements.get(control.value);
  });
}

function renderFieldRows() {
  const target = $("#dynamicBuilderFields");
  target.innerHTML = editing.campos.map((field, index) => {
    const isFile = field.tipo === "arquivo";
    const isDate = field.tipo === "data";
    const fileValidation = field.validacao || {};
    const automaticDate = isDate && fileValidation.preenchimento_automatico === "today";
    const optionValues = isFile ? (fileValidation.extensoes || ["pdf", "docx", "xlsx", "png", "jpg"]) : (field.opcoes || []);
    return `
    <div class="dynamic-builder-field-row" data-field-index="${index}" draggable="true">
      <div class="dynamic-builder-order">
        <button type="button" data-move-field="-1" title="Subir">↑</button>
        <button type="button" data-move-field="1" title="Descer">↓</button>
      </div>
      <input data-field-name value="${escapeHtml(field.nome || "")}" placeholder="Nome">
      <input data-field-key value="${escapeHtml(field.chave || "")}" placeholder="CHAVE">
      <select data-field-type>${optionList(fieldTypes, field.tipo)}</select>
      <input data-field-step type="number" min="1" max="10" value="${field.etapa || 1}" title="Etapa">
      ${rowCheck("Obrig.", "field-required", field.obrigatorio)}
      ${rowCheck("Leitura", "field-readonly", field.somente_leitura)}
      <label class="dynamic-builder-check ${isDate ? "" : "is-disabled"}" title="${isDate ? "Preencher com a data do cadastro" : "Disponivel apenas para campos de data"}">
        <input type="checkbox" data-field-auto-date ${automaticDate ? "checked" : ""} ${isDate ? "" : "disabled"}>
        <span>Data atual</span>
      </label>
      ${rowCheck("Negocial", "field-negocial", field.visivel_negocial !== false)}
      ${rowCheck("Gerencial", "field-gerencial", field.visivel_gerencial !== false)}
      <div class="dynamic-builder-field-config">
        <input data-field-options value="${escapeHtml(optionValues.join(", "))}" placeholder="${isFile ? "Extensoes permitidas" : "Opcoes separadas por virgula"}">
      ${isFile ? `<div class="dynamic-builder-file-options">
        <label><span>Limite MB</span><input data-field-file-max type="number" min="1" max="100" value="${Number(fileValidation.max_mb || 15)}"></label>
        <label class="dynamic-builder-check"><input data-field-file-multiple type="checkbox" ${fileValidation.multiplo ? "checked" : ""}><span>Varios arquivos</span></label>
      </div>` : ""}
      </div>
      <button class="secondary-btn dynamic-builder-rules-btn" type="button" data-field-rules title="Condicoes, validacoes e calculos">Regras</button>
      <button class="icon-btn" type="button" data-remove-field aria-label="Remover">x</button>
    </div>
  `; }).join("");
  const count = $("#dynamicBuilderFieldCount");
  if (count) count.textContent = editing.campos.length;
  bindRowEvents(target, "field");
  target.querySelectorAll("[data-field-type]").forEach((select) => {
    select.addEventListener("change", () => {
      collectBuilder();
      renderFieldRows();
      markBuilderDirty();
    });
  });
  target.querySelectorAll("[data-field-rules]").forEach((button) => {
    button.addEventListener("click", () => {
      collectBuilder();
      openFieldRules(Number(button.closest("[data-field-index]").dataset.fieldIndex));
    });
  });
  target.oninput = validateFieldKeys;
  validateFieldKeys();
  queueMicrotask(renderMainHubOptions);
}

function openFieldRules(index) {
  const field = editing.campos[index];
  if (!field) return;
  document.querySelector("#dynamicFieldRulesDialog")?.remove();
  const validation = field.validacao || {};
  const condition = field.condicao || {};
  const calculation = validation.calculo || {};
  const conditionSourceFields = editing.campos.filter((item) => item.chave && item.chave !== field.chave);
  const fieldOptions = conditionSourceFields
    .map((item) => [item.chave, item.nome]);
  const dialog = document.createElement("dialog");
  dialog.id = "dynamicFieldRulesDialog";
  dialog.className = "modal";
  dialog.innerHTML = `
    <form class="modal-card dynamic-rules-dialog">
      <div class="modal-header"><div><p class="eyebrow">Campo</p><h2>${escapeHtml(field.nome || field.chave)}</h2></div><button class="icon-btn" type="button" data-close>&times;</button></div>
      <div class="dynamic-rules-body">
        <section><h3>Exibicao condicional</h3><div class="dynamic-rules-grid three">
          <label><span>Depende do campo</span><select data-rule-condition-field><option value="">Sempre exibir</option>${optionList(fieldOptions, condition.campo)}</select></label>
          <label><span>Operador</span><select data-rule-condition-operator>${optionList([
            ["igual", "Igual a"], ["diferente", "Diferente de"], ["em", "É um destes valores"], ["nao_em", "Não é nenhum destes valores"], ["preenchido", "Preenchido"], ["vazio", "Vazio"],
            ["contem", "Contem"], ["maior", "Maior que"], ["maior_igual", "Maior ou igual"], ["menor", "Menor que"], ["menor_igual", "Menor ou igual"],
          ], condition.operador || "igual")}</select></label>
          <div class="dynamic-condition-value" data-rule-condition-value-host></div>
        </div><small>Use “É um destes valores” para exibir o campo quando qualquer uma das opções selecionadas for encontrada.</small></section>
        <section><h3>Validacao</h3><div class="dynamic-rules-grid four">
          <label><span>Min. caracteres</span><input type="number" min="0" data-rule-min-length value="${escapeAttr(validation.min_length ?? "")}"></label>
          <label><span>Max. caracteres</span><input type="number" min="1" data-rule-max-length value="${escapeAttr(validation.max_length ?? "")}"></label>
          <label><span>Valor minimo</span><input inputmode="decimal" data-rule-min value="${escapeAttr(validation.min ?? "")}"></label>
          <label><span>Valor maximo</span><input inputmode="decimal" data-rule-max value="${escapeAttr(validation.max ?? "")}"></label>
          <label class="wide"><span>Expressao regular</span><input data-rule-regex value="${escapeAttr(validation.regex ?? "")}" placeholder="Ex.: ^[0-9]{14}$"></label>
          <label class="wide"><span>Mensagem personalizada</span><input data-rule-message value="${escapeAttr(validation.mensagem ?? "")}" placeholder="Mensagem exibida quando o valor for invalido"></label>
          <label class="wide"><span>Valor padrao</span><input data-rule-default value="${escapeAttr(field.valor_padrao ?? "")}" placeholder="Opcional"></label>
        </div></section>
        <section><div class="dynamic-rules-section-head"><h3>Campo calculado</h3><label class="dynamic-builder-inline-check"><input type="checkbox" data-rule-calculated ${Object.keys(calculation).length ? "checked" : ""}> Ativar calculo</label></div>
          <div class="dynamic-rules-grid four" data-calculation-fields>
            <label><span>Operacao</span><select data-rule-calc-operation>${optionList([["percentual", "Percentual"], ["soma", "Soma"], ["subtracao", "Subtracao"], ["multiplicacao", "Multiplicacao"], ["divisao", "Divisao"]], calculation.operacao || "percentual")}</select></label>
            <label><span>Campo base</span><select data-rule-calc-base><option value="">Selecione</option>${optionList(fieldOptions, calculation.campo_base)}</select></label>
            <label><span>Segundo campo</span><select data-rule-calc-secondary><option value="">Usar valor fixo</option>${optionList(fieldOptions, calculation.campo_secundario)}</select></label>
            <label><span>Valor fixo / percentual</span><input inputmode="decimal" data-rule-calc-value value="${escapeAttr(calculation.valor ?? "")}" placeholder="Ex.: 10"></label>
          </div><small>O resultado e calculado no servidor e o campo passa a ser somente leitura.</small>
        </section>
      </div>
      <div class="modal-actions"><button class="secondary-btn" type="button" data-close>Cancelar</button><button class="primary-btn" type="submit">Aplicar regras</button></div>
    </form>`;
  document.body.append(dialog);
  let conditionValues = conditionValueList(condition.valor);
  const readConditionValues = () => {
    const checked = [...dialog.querySelectorAll("[data-rule-condition-choice]:checked")].map((input) => input.value);
    if (checked.length || dialog.querySelector("[data-rule-condition-choice]")) return checked;
    const control = dialog.querySelector("[data-rule-condition-value]");
    return conditionValueList(control?.value);
  };
  const renderConditionValue = (preserveCurrent = false) => {
    if (preserveCurrent) conditionValues = readConditionValues();
    const host = dialog.querySelector("[data-rule-condition-value-host]");
    const sourceKey = dialog.querySelector("[data-rule-condition-field]").value;
    const operator = dialog.querySelector("[data-rule-condition-operator]").value;
    const source = conditionSourceFields.find((item) => item.chave === sourceKey);
    if (["preenchido", "vazio"].includes(operator) || !sourceKey) {
      host.innerHTML = `<span>Valor esperado</span><div class="dynamic-condition-empty">Não é necessário informar um valor.</div>`;
      return;
    }
    if (["em", "nao_em"].includes(operator) && source?.opcoes?.length) {
      host.innerHTML = `<span>Valores aceitos</span><div class="dynamic-condition-choices">${source.opcoes.map((option) => {
        const selected = conditionValues.some((value) => value.toLocaleLowerCase("pt-BR") === String(option).toLocaleLowerCase("pt-BR"));
        return `<label><input type="checkbox" data-rule-condition-choice value="${escapeAttr(option)}" ${selected ? "checked" : ""}><span>${escapeHtml(option)}</span></label>`;
      }).join("")}</div>`;
      return;
    }
    if (["em", "nao_em"].includes(operator)) {
      host.innerHTML = `<span>Valores aceitos</span><textarea data-rule-condition-value rows="3" placeholder="Um valor por linha">${escapeHtml(conditionValues.join("\n"))}</textarea>`;
      return;
    }
    host.innerHTML = `<span>Valor esperado</span><input data-rule-condition-value value="${escapeAttr(conditionValues[0] || "")}" placeholder="Valor da condição">`;
  };
  const syncCalculation = () => {
    dialog.querySelector("[data-calculation-fields]").classList.toggle("is-disabled", !dialog.querySelector("[data-rule-calculated]").checked);
  };
  dialog.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => dialog.close()));
  dialog.querySelector("[data-rule-calculated]").addEventListener("change", syncCalculation);
  dialog.querySelector("[data-rule-condition-field]").addEventListener("change", () => renderConditionValue(true));
  dialog.querySelector("[data-rule-condition-operator]").addEventListener("change", () => renderConditionValue(true));
  dialog.querySelector("form").addEventListener("submit", (event) => {
    event.preventDefault();
    const value = (selector) => dialog.querySelector(selector)?.value?.trim() || "";
    const nextValidation = { ...validation };
    [["min_length", "[data-rule-min-length]"], ["max_length", "[data-rule-max-length]"], ["min", "[data-rule-min]"], ["max", "[data-rule-max]"]].forEach(([key, selector]) => {
      const current = value(selector);
      if (current === "") delete nextValidation[key]; else nextValidation[key] = Number(current);
    });
    [["regex", "[data-rule-regex]"], ["mensagem", "[data-rule-message]"]].forEach(([key, selector]) => {
      const current = value(selector);
      if (current) nextValidation[key] = current; else delete nextValidation[key];
    });
    if (dialog.querySelector("[data-rule-calculated]").checked) {
      nextValidation.calculo = {
        operacao: value("[data-rule-calc-operation]"), campo_base: value("[data-rule-calc-base]"),
        campo_secundario: value("[data-rule-calc-secondary]"), valor: value("[data-rule-calc-value]") || null,
      };
      field.somente_leitura = true;
    } else delete nextValidation.calculo;
    const conditionField = value("[data-rule-condition-field]");
    const conditionOperator = value("[data-rule-condition-operator]");
    const selectedConditionValues = readConditionValues();
    const isMultipleCondition = ["em", "nao_em"].includes(conditionOperator);
    if (conditionField && isMultipleCondition && !selectedConditionValues.length) {
      toast("Selecione pelo menos um valor para a condição.");
      return;
    }
    const conditionValue = isMultipleCondition
      ? selectedConditionValues
      : value("[data-rule-condition-value]");
    field.condicao = conditionField ? { campo: conditionField, operador: conditionOperator, valor: conditionValue } : {};
    field.valor_padrao = value("[data-rule-default]") || null;
    field.validacao = nextValidation;
    markBuilderDirty();
    dialog.close();
    renderFieldRows();
    renderBuilderPreview();
  });
  renderConditionValue();
  syncCalculation();
  dialog.showModal();
}

function validateFieldKeys() {
  const rows = [...document.querySelectorAll("[data-field-index]")];
  const counts = new Map();
  rows.forEach((row) => {
    const key = row.querySelector("[data-field-key]").value.trim().toUpperCase();
    if (key) counts.set(key, (counts.get(key) || 0) + 1);
  });
  rows.forEach((row) => {
    const input = row.querySelector("[data-field-key]");
    const duplicate = Boolean(input.value.trim()) && counts.get(input.value.trim().toUpperCase()) > 1;
    row.classList.toggle("invalid", duplicate);
    input.setCustomValidity(duplicate ? "Esta chave esta duplicada." : "");
    input.title = duplicate ? "Chave duplicada" : "";
  });
}

function renderStatusRows() {
  const target = $("#dynamicBuilderStatuses");
  target.innerHTML = editing.statuses.length ? editing.statuses.map((item, index) => `
    <article class="dynamic-builder-status-row ${item.inicial ? "is-initial" : ""} ${item.final ? "is-final" : ""}" data-status-index="${index}" style="--stage-color:${escapeHtml(item.cor || "#2563eb")}">
      <header class="dynamic-stage-card-head">
        <span class="dynamic-stage-order">${index + 1}</span>
        <i aria-hidden="true"></i>
        <div>
          <strong>${escapeHtml(item.nome || `Etapa ${index + 1}`)}</strong>
          <small>${item.inicial ? "Entrada do fluxo" : item.final ? "Etapa de encerramento" : "Etapa de andamento"}</small>
        </div>
        <span class="dynamic-stage-move">
          <button type="button" data-move-status="-1" aria-label="Mover etapa para cima" title="Mover para cima" ${index === 0 ? "disabled" : ""}>&uarr;</button>
          <button type="button" data-move-status="1" aria-label="Mover etapa para baixo" title="Mover para baixo" ${index === editing.statuses.length - 1 ? "disabled" : ""}>&darr;</button>
        </span>
        <button class="icon-btn" type="button" data-remove-status aria-label="Remover etapa" title="Remover etapa">&times;</button>
      </header>
      <div class="dynamic-stage-card-fields">
        <label><span>Nome exibido na aba</span><input data-status-name value="${escapeHtml(item.nome)}" placeholder="Ex.: Aguardando aprovacao"></label>
        <label><span>Codigo interno</span><input data-status-code data-code-auto="${item.codigo ? "false" : "true"}" value="${escapeHtml(item.codigo)}" placeholder="Gerado automaticamente"></label>
        <label class="dynamic-stage-color"><span>Cor dos cards/eventos</span><input data-status-color type="color" value="${escapeHtml(item.cor || "#2563eb")}" title="Aplicada aos cards, marcadores e indicadores deste status"></label>
      </div>
      <footer class="dynamic-stage-card-options">
        <label class="dynamic-stage-role"><input type="checkbox" data-status-initial ${item.inicial ? "checked" : ""}><span><strong>Etapa inicial</strong><small>Todo novo registro entra aqui.</small></span></label>
        <label class="dynamic-stage-role"><input type="checkbox" data-status-final ${item.final ? "checked" : ""}><span><strong>Encerra o fluxo</strong><small>Indica que o trabalho foi finalizado.</small></span></label>
      </footer>
    </article>
  `).join("") : '<div class="dynamic-builder-empty">Nenhuma etapa configurada. Adicione uma etapa ou use um modelo pronto.</div>';
  bindRowEvents(target, "status");
  target.oninput = (event) => {
    const row = event.target.closest("[data-status-index]");
    const index = Number(row?.dataset.statusIndex);
    const previousCode = editing.statuses[index]?.codigo || "";
    const codeInput = row?.querySelector("[data-status-code]");
    if (event.target.matches("[data-status-name]") && codeInput?.dataset.codeAuto === "true") {
      codeInput.value = statusCodeFromName(event.target.value);
    }
    if (event.target.matches("[data-status-code]")) {
      event.target.dataset.codeAuto = "false";
    }
    collectBuilder();
    const nextCode = editing.statuses[index]?.codigo || "";
    if (event.target.matches("[data-status-code]") && previousCode && previousCode !== nextCode) {
      editing.transicoes.forEach((transition) => {
        if (transition.origem_codigo === previousCode) transition.origem_codigo = nextCode;
        if (transition.destino_codigo === previousCode) transition.destino_codigo = nextCode;
      });
    }
    renderFlowPreview();
  };
  target.onchange = (event) => {
    if (event.target.matches("[data-status-initial]") && event.target.checked) {
      target.querySelectorAll("[data-status-initial]").forEach((input) => {
        if (input !== event.target) input.checked = false;
      });
    }
    collectBuilder();
    renderStatusRows();
    renderTransitionRows();
    renderFlowPreview();
    renderMetricOptions();
    renderMainHubOptions();
  };
  queueMicrotask(renderMainHubOptions);
}

function renderTransitionRows() {
  const target = $("#dynamicBuilderTransitions");
  const statuses = editing.statuses.map((item) => [item.codigo, item.nome]);
  target.innerHTML = editing.transicoes.length ? editing.transicoes.map((item, index) => `
    <article class="dynamic-builder-transition-row" data-transition-index="${index}">
      <header class="dynamic-transition-card-head">
        <span>Acao ${index + 1}</span>
        <button class="icon-btn" type="button" data-remove-transition aria-label="Remover acao" title="Remover acao">&times;</button>
      </header>
      <div class="dynamic-transition-sentence">
        <label><span>Quando estiver em</span><select data-transition-origin>${optionList(statuses, item.origem_codigo)}</select></label>
        <span class="dynamic-transition-arrow" aria-hidden="true">&rarr;</span>
        <label class="action-name"><span>O botao exibido sera</span><input data-transition-name value="${escapeHtml(item.nome)}" placeholder="Ex.: Aprovar"></label>
        <span class="dynamic-transition-arrow" aria-hidden="true">&rarr;</span>
        <label><span>E movera para</span><select data-transition-target>${optionList(statuses, item.destino_codigo)}</select></label>
      </div>
      <footer class="dynamic-transition-options">
        <span>Antes de executar:</span>
        ${rowCheck("Exigir justificativa", "transition-reason", item.exige_justificativa)}
        <span class="dynamic-transition-access-label">Quem pode executar:</span>
        ${rowCheck("Negociador", "transition-negotiator", item.permite_negociador)}
        ${rowCheck("Gerencial", "transition-manager", item.permite_gerencial !== false)}
        <button class="secondary-btn dynamic-transition-automation-btn" type="button" data-transition-automations>Automacoes ${(item.configuracao?.automacoes || []).length ? `(${item.configuracao.automacoes.length})` : ""}</button>
      </footer>
    </article>
  `).join("") : '<div class="dynamic-builder-empty">Nenhuma acao configurada. Os registros permanecerao na etapa inicial ate uma acao ser criada.</div>';
  bindRowEvents(target, "transition");
  target.oninput = () => {
    collectBuilder();
    renderFlowPreview();
  };
  target.onchange = () => {
    collectBuilder();
    renderFlowPreview();
  };
  target.querySelectorAll("[data-transition-automations]").forEach((button) => {
    button.addEventListener("click", () => {
      collectBuilder();
      openTransitionAutomations(Number(button.closest("[data-transition-index]").dataset.transitionIndex));
    });
  });
}

function openTransitionAutomations(index) {
  const transition = editing.transicoes[index];
  if (!transition) return;
  document.querySelector("#dynamicTransitionAutomationDialog")?.remove();
  const current = (transition.configuracao?.automacoes || []).map((item) => ({ ...item }));
  const fieldOptions = editing.campos.filter((field) => field.chave).map((field) => [field.chave, field.nome]);
  const dialog = document.createElement("dialog");
  dialog.id = "dynamicTransitionAutomationDialog";
  dialog.className = "modal";
  dialog.innerHTML = `<form class="modal-card dynamic-rules-dialog">
    <div class="modal-header"><div><p class="eyebrow">Depois da transicao</p><h2>${escapeHtml(transition.nome || "Automacoes")}</h2></div><button class="icon-btn" type="button" data-close>&times;</button></div>
    <div class="dynamic-rules-body"><section><div class="dynamic-rules-section-head"><div><h3>Acoes automaticas</h3><small>Executadas na ordem abaixo, junto com a mudanca de status.</small></div><button class="secondary-btn" type="button" data-add-automation>Adicionar acao</button></div><div class="dynamic-automation-list"></div></section></div>
    <div class="modal-actions"><button class="secondary-btn" type="button" data-close>Cancelar</button><button class="primary-btn" type="submit">Aplicar automacoes</button></div>
  </form>`;
  document.body.append(dialog);
  const render = () => {
    dialog.querySelector(".dynamic-automation-list").innerHTML = current.length ? current.map((item, itemIndex) => `
      <div class="dynamic-automation-row" data-automation-index="${itemIndex}">
        <select data-automation-type>${optionList([["data_atual", "Preencher data atual"], ["definir_valor", "Definir valor"], ["limpar_campo", "Limpar campo"], ["notificar", "Registrar aviso no historico"]], item.tipo)}</select>
        <select data-automation-field><option value="">${item.tipo === "notificar" ? "Sem campo" : "Selecione o campo"}</option>${optionList(fieldOptions, item.campo)}</select>
        <input data-automation-value value="${escapeAttr(item.valor ?? "")}" placeholder="Valor ou mensagem">
        <button class="icon-btn" type="button" data-remove-automation>&times;</button>
      </div>`).join("") : '<div class="dynamic-builder-empty">Nenhuma acao automatica configurada.</div>';
    dialog.querySelectorAll("[data-remove-automation]").forEach((button) => button.addEventListener("click", () => {
      current.splice(Number(button.closest("[data-automation-index]").dataset.automationIndex), 1);
      render();
    }));
  };
  const collect = () => [...dialog.querySelectorAll("[data-automation-index]")].map((row) => ({
    tipo: row.querySelector("[data-automation-type]").value,
    campo: row.querySelector("[data-automation-field]").value,
    valor: row.querySelector("[data-automation-value]").value.trim() || null,
  }));
  dialog.querySelector("[data-add-automation]").addEventListener("click", () => {
    current.splice(0, current.length, ...collect());
    current.push({ tipo: "data_atual", campo: fieldOptions[0]?.[0] || "", valor: null });
    render();
  });
  dialog.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => dialog.close()));
  dialog.querySelector("form").addEventListener("submit", (event) => {
    event.preventDefault();
    transition.configuracao = { ...(transition.configuracao || {}), automacoes: collect() };
    markBuilderDirty();
    dialog.close();
    renderTransitionRows();
  });
  render();
  dialog.showModal();
}

function renderPermissionRows() {
  const target = $("#dynamicBuilderPermissions");
  const walletConfigured = new Map(
    (editing.permissoes || []).filter((item) => item.carteira && !item.user_id)
      .map((item) => [item.carteira.toUpperCase(), item]),
  );
  const userConfigured = new Map(
    (editing.permissoes || []).filter((item) => item.user_id)
      .map((item) => [Number(item.user_id), item]),
  );
  const walletRows = wallets.map((wallet) => permissionRow(
    "wallet",
    wallet,
    wallet,
    walletConfigured.get(String(wallet).toUpperCase()),
  )).join("");
  const userRows = negotiators.map((user) => permissionRow(
    "user",
    user.id,
    `${user.username}${user.carteira ? ` · ${user.carteira}` : ""}`,
    userConfigured.get(Number(user.id)),
  )).join("");
  target.innerHTML = `
    <div class="dynamic-builder-permission-group" data-permission-panel="wallets">
      ${walletRows || '<div class="dynamic-builder-empty">Nenhuma carteira cadastrada.</div>'}
    </div>
    <div class="dynamic-builder-permission-group hidden" data-permission-panel="users">
      <div class="dynamic-builder-user-permissions">
        ${userRows || '<div class="dynamic-builder-empty">Nenhum negociador cadastrado.</div>'}
      </div>
    </div>
  `;
  activatePermissionTab(permissionTab);
}

function permissionRow(scope, value, label, permission) {
  return `
    <div class="dynamic-builder-permission-row" data-permission-scope="${scope}" data-permission-value="${escapeHtml(value)}">
      <strong>${escapeHtml(label)}</strong>
      ${rowCheck("Exibir", "permission-view", permission?.pode_visualizar)}
      ${rowCheck("Criar", "permission-create", permission?.pode_criar)}
      ${rowCheck("Editar", "permission-edit", permission?.pode_editar)}
      ${rowCheck("Status", "permission-transition", permission?.pode_transicionar)}
      ${rowCheck("Exportar", "permission-export", permission?.pode_exportar)}
    </div>
  `;
}

function collectBuilder() {
  const previousFields = [...(editing.campos || [])];
  const previousStatuses = [...(editing.statuses || [])];
  editing.nome = $("#dynamicToolName").value.trim();
  editing.descricao = $("#dynamicToolDescription").value.trim();
  editing.tipo = $("#dynamicToolType").value;
  editing.icone = $("#dynamicToolIcon").value.trim();
  editing.cor = $("#dynamicToolColor").value;
  editing.destaque_gerencial = $("#dynamicToolHighlight").checked;
  editing.configuracao = {
    ...(editing.configuracao || {}),
    campo_titulo: $("#dynamicToolTitleField").value.trim().toUpperCase(),
    mostrar_cards: $("#dynamicToolCards").checked,
    metricas_cards: [...document.querySelectorAll("[data-metric-key]:checked")].map((input) => input.dataset.metricKey),
    usar_status: editing.tipo === "SOLICITACAO" || $("#dynamicToolUseStatus").checked,
    negociador_define_status: (
      editing.tipo === "CADASTRO"
      && $("#dynamicToolUseStatus").checked
      && $("#dynamicToolNegotiatorStatus").checked
    ),
    negociador_altera_status: (
      $("#dynamicToolUseStatus").checked
      && $("#dynamicToolChangeStatus").checked
    ),
    main_hub: {
      enabled: Boolean($("#dynamicToolMainHub")?.checked),
      status_codes: [...document.querySelectorAll("[data-main-hub-status]:checked")].map((input) => input.value),
      field_keys: [...document.querySelectorAll("[data-main-hub-field]:checked")].map((input) => input.value),
    },
  };
  const screenRows = [...document.querySelectorAll("[data-screen-index]")];
  if (screenRows.length) {
    const screens = ensureScreens();
    screenRows.forEach((row) => {
      const screenIndex = Number(row.dataset.screenIndex);
      screens[screenIndex] = {
      ...(screens[screenIndex] || {}),
      id: row.querySelector("[data-screen-id]").value.trim(),
      nome: row.querySelector("[data-screen-name]").value.trim(),
      icone: row.querySelector("[data-screen-icon]").value.trim(),
      tipo: row.querySelector("[data-screen-type]").value,
      ordem: screenIndex,
      visivel_negocial: row.querySelector("[data-screen-negocial]").checked,
      visivel_gerencial: row.querySelector("[data-screen-gerencial]").checked,
      status_codes: [...row.querySelectorAll("[data-screen-status]:checked")].map((input) => input.value),
      historico_status_codes: [...row.querySelectorAll("[data-screen-history-status]:checked")].map((input) => input.value),
      campos: [...row.querySelectorAll("[data-screen-field]:checked")].map((input) => input.value),
      componentes: [...row.querySelectorAll("[data-screen-component]:checked")].map((input) => input.value),
      layout: {
        colunas_desktop: Number(row.querySelector("[data-screen-columns-desktop]")?.value || 1),
        colunas_tablet: Number(row.querySelector("[data-screen-columns-tablet]")?.value || 1),
        colunas_mobile: Number(row.querySelector("[data-screen-columns-mobile]")?.value || 1),
        densidade: row.querySelector("[data-screen-density]")?.value || "compacta",
        altura_uniforme: Boolean(row.querySelector("[data-screen-uniform-height]")?.checked),
      },
      dashboard: {
        columns: 12,
        blocks: [...row.querySelectorAll("[data-dashboard-block]")].map((block, blockIndex) => ({
          id: block.dataset.dashboardBlockId || `bloco-${blockIndex + 1}`,
          tipo: block.querySelector("[data-dashboard-block-type]")?.value || "metric",
          titulo: block.querySelector("[data-dashboard-block-title]")?.value.trim() || "Bloco",
          agregacao: block.querySelector("[data-dashboard-block-aggregation]")?.value || "count",
          campo: block.querySelector("[data-dashboard-block-field]")?.value || "",
          campo_secundario: block.querySelector("[data-dashboard-block-secondary-field]")?.value || "",
          agrupador: block.querySelector("[data-dashboard-block-group]")?.value || "",
          condicao_campo: block.querySelector("[data-dashboard-block-condition-field]")?.value || "",
          condicao_operador: block.querySelector("[data-dashboard-block-condition-operator]")?.value || "eq",
          condicao_valor: block.querySelector("[data-dashboard-block-condition-value]")?.value.trim() || "",
          status_codes: [...block.querySelectorAll("[data-dashboard-block-status]:checked")].map((input) => input.value),
          cor: block.querySelector("[data-dashboard-block-color]")?.value || editing.cor || "#2563eb",
          largura: Number(block.querySelector("[data-dashboard-block-width]")?.value || 6),
          limite: Number(block.querySelector("[data-dashboard-block-limit]")?.value || 8),
          periodo: block.querySelector("[data-dashboard-block-period]")?.value || "day",
        })),
      },
      filtros: {
        ...(screens[screenIndex]?.filtros || {}),
        mostrar_status: Boolean(row.querySelector("[data-screen-filter-status]")?.checked),
        mostrar_negociador: Boolean(row.querySelector("[data-screen-filter-negotiator]")?.checked),
        mostrar_carteira: Boolean(row.querySelector("[data-screen-filter-wallet]")?.checked),
        mostrar_ordenacao: Boolean(row.querySelector("[data-screen-filter-sort]")?.checked),
        campos: [...row.querySelectorAll("[data-screen-filter-field]:checked")].map((input) => input.value),
        campo_data: row.querySelector("[data-screen-date-field]")?.value || "",
        modo_data: row.querySelector("[data-screen-date-mode]")?.value || "none",
        prazos_visiveis: [...row.querySelectorAll("[data-screen-deadline-option]:checked")].map((input) => input.value),
        agrupar_prazo: Boolean(row.querySelector("[data-screen-group-deadline]")?.checked),
        iniciar_recolhido: Boolean(row.querySelector("[data-screen-groups-collapsed]")?.checked),
      },
      agrupamento: {
        modo: row.querySelector("[data-screen-group-mode]")?.value || "none",
        campo: row.querySelector("[data-screen-group-field]")?.value || "",
        iniciar_recolhido: Boolean(row.querySelector("[data-screen-groups-collapsed]")?.checked),
      },
      acoes_card: {
        copiar: Boolean(row.querySelector("[data-screen-action-copy]")?.checked),
        copiar_campos: [...row.querySelectorAll("[data-screen-action-copy-field]:checked")].map((input) => input.value),
        observacoes: Boolean(row.querySelector("[data-screen-action-notes]")?.checked),
        mostrar_atualizacao: Boolean(row.querySelector("[data-screen-action-updated]")?.checked),
        status_modo: row.querySelector("[data-screen-action-mode]")?.value || "open",
        status_origem: row.querySelector("[data-screen-action-source]")?.value || "flow",
        status_campo: row.querySelector("[data-screen-action-field]")?.value || "",
        botao_rotulo: row.querySelector("[data-screen-action-label]")?.value.trim() || "Abrir",
        botao_status: row.querySelector("[data-screen-action-target]")?.value || "",
      },
      campo_layout: Object.fromEntries([...row.querySelectorAll("[data-screen-field-layout]")].map((fieldRow) => [
        fieldRow.dataset.screenFieldLayout,
        {
          papel: fieldRow.querySelector("[data-screen-field-role]")?.value || "info",
          largura: fieldRow.querySelector("[data-screen-field-width]")?.value || "auto",
          copiavel: Boolean(fieldRow.querySelector("[data-screen-field-copyable]")?.checked),
        },
      ])),
      };
    });
    editing.configuracao.telas = screens.map((screen, index) => ({ ...screen, ordem: index }));
  }
  editing.campos = [...document.querySelectorAll("[data-field-index]")].map((row, index) => {
    const previous = editing.campos[Number(row.dataset.fieldIndex)] || {};
    const type = row.querySelector("[data-field-type]").value;
    const rawOptions = row.querySelector("[data-field-options]").value.split(",").map((item) => item.trim()).filter(Boolean);
    const options = type === "arquivo" ? rawOptions.map((item) => item.replace(/^\./, "").toLowerCase()) : rawOptions;
    return {
      ...previous,
      nome: row.querySelector("[data-field-name]").value.trim(),
      chave: row.querySelector("[data-field-key]").value.trim(),
      tipo: type,
      ordem: index,
      etapa: Number(row.querySelector("[data-field-step]").value || 1),
      obrigatorio: row.querySelector("[data-field-required]").checked,
      somente_leitura: row.querySelector("[data-field-readonly]").checked,
      visivel_negocial: row.querySelector("[data-field-negocial]").checked,
      visivel_gerencial: row.querySelector("[data-field-gerencial]").checked,
      opcoes: type === "arquivo" ? [] : options,
      validacao: type === "arquivo" ? {
        ...(previous.validacao || {}),
        preenchimento_automatico: null,
        extensoes: options,
        max_mb: Number(row.querySelector("[data-field-file-max]")?.value || 15),
        multiplo: Boolean(row.querySelector("[data-field-file-multiple]")?.checked),
        max_arquivos: row.querySelector("[data-field-file-multiple]")?.checked ? 10 : 1,
      } : {
        ...(previous.validacao || {}),
        preenchimento_automatico: (
          type === "data" && row.querySelector("[data-field-auto-date]")?.checked
        ) ? "today" : null,
      },
    };
  });
  const fieldKeyReplacements = new Map(editing.campos.map((field, index) => [previousFields[index]?.chave, field.chave]));
  (editing.configuracao.telas || []).forEach((screen) => {
    screen.campos = (screen.campos || []).map((key) => fieldKeyReplacements.get(key) || key);
    screen.filtros = { ...(screen.filtros || {}), campos: (screen.filtros?.campos || []).map((key) => fieldKeyReplacements.get(key) || key) };
    screen.agrupamento = { ...(screen.agrupamento || {}), campo: fieldKeyReplacements.get(screen.agrupamento?.campo) || screen.agrupamento?.campo || "" };
    screen.acoes_card = {
      ...(screen.acoes_card || {}),
      status_campo: fieldKeyReplacements.get(screen.acoes_card?.status_campo) || screen.acoes_card?.status_campo || "",
      copiar_campos: (screen.acoes_card?.copiar_campos || []).map((key) => fieldKeyReplacements.get(key) || key),
    };
  });
  editing.configuracao.main_hub.field_keys = (editing.configuracao.main_hub.field_keys || [])
    .map((key) => fieldKeyReplacements.get(key) || key);
  editing.statuses = [...document.querySelectorAll("[data-status-index]")].map((row, index) => ({
    nome: row.querySelector("[data-status-name]").value.trim(),
    codigo: row.querySelector("[data-status-code]").value.trim(),
    cor: row.querySelector("[data-status-color]").value,
    ordem: index,
    inicial: row.querySelector("[data-status-initial]").checked,
    final: row.querySelector("[data-status-final]").checked,
  }));
  const statusCodeReplacements = new Map(editing.statuses.map((status, index) => [previousStatuses[index]?.codigo, status.codigo]));
  editing.configuracao.main_hub.status_codes = (editing.configuracao.main_hub.status_codes || [])
    .map((code) => statusCodeReplacements.get(code) || code);
  editing.transicoes = [...document.querySelectorAll("[data-transition-index]")].map((row) => {
    const originSelect = row.querySelector("[data-transition-origin]");
    const targetSelect = row.querySelector("[data-transition-target]");
    return ({
    origem_codigo: originSelect.value || editing.statuses[originSelect.selectedIndex]?.codigo || "",
    destino_codigo: targetSelect.value || editing.statuses[targetSelect.selectedIndex]?.codigo || "",
    nome: row.querySelector("[data-transition-name]").value.trim(),
    exige_justificativa: row.querySelector("[data-transition-reason]").checked,
    permite_negociador: row.querySelector("[data-transition-negotiator]").checked,
    permite_gerencial: row.querySelector("[data-transition-manager]").checked,
    configuracao: editing.transicoes[Number(row.dataset.transitionIndex)]?.configuracao || {},
  });
  });
  editing.permissoes = [...document.querySelectorAll("[data-permission-scope]")].flatMap((row) => {
    const enabled = row.querySelector("[data-permission-view]").checked;
    if (!enabled) return [];
    const permission = {
      pode_visualizar: true,
      pode_criar: row.querySelector("[data-permission-create]").checked,
      pode_editar: row.querySelector("[data-permission-edit]").checked,
      pode_transicionar: row.querySelector("[data-permission-transition]").checked,
      pode_exportar: row.querySelector("[data-permission-export]").checked,
    };
    if (row.dataset.permissionScope === "user") {
      permission.user_id = Number(row.dataset.permissionValue);
    } else {
      permission.carteira = row.dataset.permissionValue;
    }
    return [permission];
  });
}

function validateBuilderDraft() {
  if (!editing.nome) throw new Error("Informe o nome da ferramenta.");
  const validFields = editing.campos.filter((field) => field.chave || field.nome);
  if (!validFields.length) throw new Error("Adicione ao menos um campo a ferramenta.");
  const fieldKeys = validFields.map((field) => statusCodeFromName(field.chave || field.nome));
  if (new Set(fieldKeys).size !== fieldKeys.length) throw new Error("Existem campos com a mesma chave.");
  const screens = ensureScreens();
  if (!screens.length) throw new Error("Adicione ao menos uma tela a ferramenta.");
  if (screens.some((screen) => !screen.nome?.trim() || !screen.id?.trim())) {
    throw new Error("Todas as telas precisam de nome e identificador.");
  }
  if (new Set(screens.map((screen) => screen.id.trim().toLowerCase())).size !== screens.length) {
    throw new Error("Existem telas com o mesmo identificador.");
  }
  if (!statusEnabled()) return;
  if (!editing.statuses.length) throw new Error("Adicione ao menos uma etapa ao fluxo.");
  if (editing.statuses.filter((status) => status.inicial).length !== 1) {
    throw new Error("Escolha exatamente uma etapa inicial.");
  }
  const statusCodes = new Set(editing.statuses.map((status) => status.codigo));
  const transitionPairs = new Set();
  editing.transicoes.forEach((transition, index) => {
    if (!statusCodes.has(transition.origem_codigo) || !statusCodes.has(transition.destino_codigo)) {
      throw new Error(`A acao ${index + 1} aponta para uma etapa invalida.`);
    }
    if (transition.origem_codigo === transition.destino_codigo) {
      throw new Error(`A acao ${index + 1} precisa mover o registro para outra etapa.`);
    }
    const pair = `${transition.origem_codigo}::${transition.destino_codigo}`;
    if (transitionPairs.has(pair)) {
      throw new Error("Existem duas acoes com a mesma etapa de origem e destino.");
    }
    transitionPairs.add(pair);
  });
}

function showBuilderSaveError(message = "") {
  const target = $("#dynamicBuilderSaveError");
  if (!target) return;
  target.textContent = message;
  target.classList.toggle("hidden", !message);
  if (message) target.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function bindRowEvents(target, type) {
  target.querySelectorAll(`[data-remove-${type}]`).forEach((button) => {
    button.addEventListener("click", () => {
      collectBuilder();
      const row = button.closest(`[data-${type}-index]`);
      const key = type === "field" ? "campos" : type === "status" ? "statuses" : "transicoes";
      if (type === "status") {
        const removedCode = editing.statuses[Number(row.dataset.statusIndex)]?.codigo;
        editing.transicoes = editing.transicoes.filter((transition) => (
          transition.origem_codigo !== removedCode && transition.destino_codigo !== removedCode
        ));
      }
      editing[key].splice(Number(row.dataset[`${type}Index`]), 1);
      if (type === "status" && editing.statuses.length && !editing.statuses.some((status) => status.inicial)) {
        editing.statuses[0].inicial = true;
      }
      markBuilderDirty();
      renderAllRows();
    });
  });
  if (type === "status") {
    target.querySelectorAll("[data-move-status]").forEach((button) => {
      button.addEventListener("click", () => {
        collectBuilder();
        const index = Number(button.closest("[data-status-index]").dataset.statusIndex);
        const next = index + Number(button.dataset.moveStatus);
        if (next < 0 || next >= editing.statuses.length) return;
        [editing.statuses[index], editing.statuses[next]] = [editing.statuses[next], editing.statuses[index]];
        markBuilderDirty();
        renderStatusRows();
        renderTransitionRows();
        renderFlowPreview();
      });
    });
  }
  if (type === "field") {
    target.querySelectorAll("[data-move-field]").forEach((button) => {
      button.addEventListener("click", () => {
        collectBuilder();
        const index = Number(button.closest("[data-field-index]").dataset.fieldIndex);
        const next = index + Number(button.dataset.moveField);
        if (next < 0 || next >= editing.campos.length) return;
        [editing.campos[index], editing.campos[next]] = [editing.campos[next], editing.campos[index]];
        markBuilderDirty();
        renderFieldRows();
      });
    });
    let draggedIndex = null;
    target.querySelectorAll("[data-field-index]").forEach((row) => {
      row.addEventListener("dragstart", (event) => {
        if (event.target.closest("input,select,button")) {
          event.preventDefault();
          return;
        }
        draggedIndex = Number(row.dataset.fieldIndex);
        row.classList.add("dragging");
        event.dataTransfer.effectAllowed = "move";
      });
      row.addEventListener("dragend", () => {
        row.classList.remove("dragging");
        draggedIndex = null;
      });
      row.addEventListener("dragover", (event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
      });
      row.addEventListener("drop", (event) => {
        event.preventDefault();
        const targetIndex = Number(row.dataset.fieldIndex);
        if (draggedIndex === null || draggedIndex === targetIndex) return;
        collectBuilder();
        const [moved] = editing.campos.splice(draggedIndex, 1);
        editing.campos.splice(targetIndex, 0, moved);
        markBuilderDirty();
        renderFieldRows();
      });
    });
  }
}

function renderAllRows() {
  renderFieldRows();
  renderStatusRows();
  renderTransitionRows();
  renderPermissionRows();
  renderFlowPreview();
  renderMetricOptions();
  renderMainHubOptions();
  renderScreenRows();
}

function renderDashboardStudio(screen) {
  const dashboard = ensureDashboardConfig(screen);
  const fields = editing.campos || [];
  const valueFields = fields.filter((field) => ["numero", "moeda"].includes(field.tipo));
  const dateFields = fields.filter((field) => field.tipo === "data");
  const fieldOptions = (items, selected, emptyLabel) => `<option value="">${emptyLabel}</option>${items.map((field) => `<option value="${escapeHtml(field.chave)}" ${selected === field.chave ? "selected" : ""}>${escapeHtml(field.nome)}</option>`).join("")}`;
  return `<section class="dynamic-builder-screen-section dynamic-dashboard-studio">
    <div class="dynamic-builder-field-layout-head"><div><h4>Composicao do dashboard</h4><small>Monte a visao executiva em uma grade de 12 colunas.</small></div><button class="primary-btn compact" type="button" data-add-dashboard-block>+ Adicionar bloco</button></div>
    <div class="dynamic-dashboard-block-list">
      ${dashboard.blocks.map((block, index) => {
        const type = block.tipo || "metric";
        const usesAggregation = ["metric", "distribution", "ranking", "timeline", "comparison"].includes(type);
        const usesGroup = ["distribution", "ranking", "validation"].includes(type);
        const usesDate = ["timeline", "comparison", "deadline"].includes(type);
        const usesLimit = ["distribution", "ranking", "timeline", "recent", "queue"].includes(type);
        const usesSecondary = ["ratio", "difference", "duration_average"].includes(block.agregacao);
        return `<article class="dynamic-dashboard-block-editor" data-dashboard-block data-dashboard-block-id="${escapeAttr(block.id || `bloco-${index + 1}`)}" style="--block-color:${escapeHtml(block.cor || editing.cor || "#2563eb")}">
          <header><span class="dynamic-dashboard-block-grip" aria-hidden="true">&#8942;&#8942;</span><strong>${index + 1}. ${escapeHtml(block.titulo || "Bloco")}</strong><div><button type="button" data-move-dashboard-block="up" ${index === 0 ? "disabled" : ""} title="Mover para cima">&uarr;</button><button type="button" data-move-dashboard-block="down" ${index === dashboard.blocks.length - 1 ? "disabled" : ""} title="Mover para baixo">&darr;</button><button type="button" data-remove-dashboard-block title="Remover">&times;</button></div></header>
          <div class="dynamic-dashboard-block-fields">
            <label><span>Tipo de bloco</span><select data-dashboard-block-type>${dashboardBlockTypes.map(([value, label]) => `<option value="${value}" ${type === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>
            <label class="wide"><span>Titulo</span><input data-dashboard-block-title value="${escapeHtml(block.titulo || "")}" placeholder="Titulo exibido"></label>
            <label><span>Cor</span><input data-dashboard-block-color type="color" value="${escapeHtml(block.cor || editing.cor || "#2563eb")}"></label>
            <label><span>Largura</span><select data-dashboard-block-width>${[3,4,6,8,9,12].map((value) => `<option value="${value}" ${Number(block.largura || 6) === value ? "selected" : ""}>${value}/12</option>`).join("")}</select></label>
            <label class="${usesAggregation ? "" : "hidden"}"><span>Calculo</span><select data-dashboard-block-aggregation>${dashboardAggregations.map(([value, label]) => `<option value="${value}" ${(block.agregacao || "count") === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>
            <label class="${usesAggregation ? "" : "hidden"}"><span>Campo de valor</span><select data-dashboard-block-field>${fieldOptions(valueFields, block.campo, "Nao se aplica para quantidade")}</select></label>
            <label class="${usesSecondary ? "" : "hidden"}"><span>Segundo campo</span><select data-dashboard-block-secondary-field>${fieldOptions(block.agregacao === "duration_average" ? dateFields : valueFields, block.campo_secundario, "Selecione o segundo campo")}</select></label>
            ${usesGroup || usesDate ? `<label><span>${usesDate ? "Campo de data" : "Agrupar por"}</span><select data-dashboard-block-group>${fieldOptions(usesDate ? dateFields : fields, block.agrupador, usesDate ? "Selecione a data" : "Selecione o campo")}</select></label>` : '<input type="hidden" data-dashboard-block-group value="">'}
            <label class="${usesDate ? "" : "hidden"}"><span>Periodo</span><select data-dashboard-block-period><option value="day" ${block.periodo === "day" ? "selected" : ""}>Dia</option><option value="month" ${block.periodo === "month" ? "selected" : ""}>Mes</option><option value="year" ${block.periodo === "year" ? "selected" : ""}>Ano</option></select></label>
            <label class="${usesLimit ? "" : "hidden"}"><span>Itens exibidos</span><input data-dashboard-block-limit type="number" min="3" max="30" value="${Number(block.limite || 8)}"></label>
            <label><span>Condicao por campo</span><select data-dashboard-block-condition-field>${fieldOptions(fields, block.condicao_campo, "Sem condicao adicional")}</select></label>
            <label><span>Operador</span><select data-dashboard-block-condition-operator>${dashboardConditionOperators.map(([value, label]) => `<option value="${value}" ${(block.condicao_operador || "eq") === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>
            <label class="wide"><span>Valor esperado</span><input data-dashboard-block-condition-value value="${escapeHtml(block.condicao_valor || "")}" placeholder="Valor usado pela condicao"></label>
          </div>
          <fieldset class="dynamic-dashboard-status-filter"><legend>Status considerados <small>(nenhum = todos)</small></legend>${(editing.statuses || []).map((status) => `<label style="--choice-color:${escapeHtml(status.cor || "#2563eb")}"><input type="checkbox" data-dashboard-block-status value="${escapeHtml(status.codigo)}" ${(block.status_codes || []).includes(status.codigo) ? "checked" : ""}><i></i>${escapeHtml(status.nome)}</label>`).join("") || "<small>Esta ferramenta nao utiliza status.</small>"}</fieldset>
        </article>`;
      }).join("")}
    </div>
  </section>`;
}

function renderScreenRows() {
  const target = $("#dynamicBuilderScreens");
  if (!target) return;
  const screens = ensureScreens();
  builderScreenIndex = Math.max(0, Math.min(builderScreenIndex, screens.length - 1));
  const screen = screens[builderScreenIndex];
  if (!screen) {
    target.innerHTML = '<div class="dynamic-builder-empty">Nenhuma tela configurada.</div>';
    return;
  }
  const selectedFieldKeys = new Set(screen.campos || []);
  const layoutFields = (editing.campos || []).filter((field) => !selectedFieldKeys.size || selectedFieldKeys.has(field.chave));
  const dateFields = (editing.campos || []).filter((field) => field.tipo === "data");
  const screenLayout = screen.layout || {};
  const screenFilters = normalizedFilterConfig(screen.filtros || {});
  const screenGrouping = normalizedGroupingConfig(screen.agrupamento || {}, screenFilters);
  const screenActions = normalizedCardActionsConfig(screen.acoes_card || defaultCardActionsConfig());
  const availableScreenComponents = screen.tipo === "dashboard"
    ? screenComponents.filter(([value]) => ["busca", "filtros", "relatorio"].includes(value))
    : screenComponents;
  const availableDateModes = screen.tipo === "dashboard"
    ? deadlineModes.filter(([value]) => ["none", "date", "period"].includes(value))
    : deadlineModes;
  const dashboardFiltersEnabled = screen.tipo !== "dashboard"
    || (screen.componentes || []).includes("filtros");
  const fieldLayout = screen.campo_layout || {};
  const list = screens.map((item, index) => {
    const visible = [item.visivel_negocial !== false ? "N" : "", item.visivel_gerencial !== false ? "G" : ""].filter(Boolean);
    const typeLabel = screenTypes.find(([value]) => value === item.tipo)?.[1] || "Tela";
    return `
      <button class="dynamic-builder-screen-list-item ${index === builderScreenIndex ? "active" : ""}" type="button" data-select-screen="${index}" draggable="true" data-screen-list-index="${index}">
        <b>${escapeHtml(item.icone || item.nome?.slice(0, 1) || "T")}</b>
        <span><strong>${escapeHtml(item.nome || `Tela ${index + 1}`)}</strong><small>${escapeHtml(typeLabel)}</small></span>
        <em>${visible.map((label) => `<i>${label}</i>`).join("") || "-"}</em>
      </button>`;
  }).join("");
  target.innerHTML = `
    <aside class="dynamic-builder-screen-list" aria-label="Telas configuradas">
      <div class="dynamic-builder-screen-list-head"><span>Telas</span><strong>${screens.length}</strong></div>
      <div class="dynamic-builder-screen-list-items">${list}</div>
      <button class="dynamic-builder-screen-add" id="addDynamicScreenInlineBtn" type="button">+ Adicionar tela</button>
    </aside>
    <article class="dynamic-builder-screen-card" data-screen-index="${builderScreenIndex}">
      <header class="dynamic-builder-screen-card-head">
        <div><span>Editando tela</span><strong>${escapeHtml(screen.nome || `Tela ${builderScreenIndex + 1}`)}</strong></div>
        <div>
          <button class="secondary-btn" type="button" data-duplicate-screen="${builderScreenIndex}">Duplicar</button>
          <button class="icon-btn" type="button" data-remove-screen="${builderScreenIndex}" aria-label="Remover tela">&times;</button>
        </div>
      </header>
      <section class="dynamic-builder-screen-section">
        <h4>Identificacao</h4>
        <div class="dynamic-builder-screen-fields">
          <label><span>Nome da aba</span><input data-screen-name value="${escapeHtml(screen.nome || "")}" placeholder="Pendentes"></label>
          <label><span>Identificador</span><input data-screen-id value="${escapeHtml(screen.id || "")}" placeholder="pendentes"></label>
          <label><span>Icone</span><input data-screen-icon value="${escapeHtml(screen.icone || "T")}" maxlength="8"></label>
          <label><span>Tipo de tela</span><select data-screen-type>${screenTypes.map(([value, label]) => `<option value="${value}" ${screen.tipo === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>
        </div>
      </section>
      ${screen.tipo === "dashboard" ? renderDashboardStudio(screen) : ""}
      <section class="dynamic-builder-screen-section">
        <h4>Disponibilidade e componentes</h4>
        <div class="dynamic-builder-screen-options primary-options">
          <fieldset><legend>Onde aparece</legend>
            <label><input type="checkbox" data-screen-negocial ${screen.visivel_negocial !== false ? "checked" : ""}> Negocial</label>
            <label><input type="checkbox" data-screen-gerencial ${screen.visivel_gerencial !== false ? "checked" : ""}> Gerencial</label>
          </fieldset>
          <fieldset><legend>${screen.tipo === "dashboard" ? "Recursos adicionais" : "Componentes"}</legend>${availableScreenComponents.map(([value, label]) => `<label><input type="checkbox" data-screen-component value="${value}" ${(screen.componentes || []).includes(value) ? "checked" : ""}> ${label}</label>`).join("")}</fieldset>
        </div>
      </section>
      <section class="dynamic-builder-screen-section ${screen.tipo === "dashboard" ? "hidden" : ""}">
        <h4>Conteudo e fluxo</h4>
        <div class="dynamic-builder-screen-options content-options">
          <fieldset><legend>Status desta tela</legend>${(editing.statuses || []).map((status) => `<label><input type="checkbox" data-screen-status value="${escapeHtml(status.codigo)}" ${(screen.status_codes || []).includes(status.codigo) ? "checked" : ""}> ${escapeHtml(status.nome)}</label>`).join("") || "<small>Fluxo sem status.</small>"}</fieldset>
          <fieldset class="${screen.tipo === "aprovacao" || screen.tipo === "historico" ? "" : "is-optional"}"><legend>Status do historico</legend>${(editing.statuses || []).map((status) => `<label><input type="checkbox" data-screen-history-status value="${escapeHtml(status.codigo)}" ${(screen.historico_status_codes || []).includes(status.codigo) ? "checked" : ""}> ${escapeHtml(status.nome)}</label>`).join("") || "<small>Fluxo sem status.</small>"}</fieldset>
          <fieldset><legend>Campos exibidos <small>(nenhum = todos)</small></legend>${(editing.campos || []).map((field) => `<label><input type="checkbox" data-screen-field value="${escapeHtml(field.chave)}" ${(screen.campos || []).includes(field.chave) ? "checked" : ""}> ${escapeHtml(field.nome)}</label>`).join("")}</fieldset>
        </div>
      </section>
      <section class="dynamic-builder-screen-section ${screen.tipo === "dashboard" ? "hidden" : ""}">
        <h4>Grade e densidade</h4>
        <div class="dynamic-builder-layout-grid">
          <label><span>Desktop</span><select data-screen-columns-desktop>${[1,2,3,4,5,6].map((value) => `<option value="${value}" ${Number(screenLayout.colunas_desktop || 1) === value ? "selected" : ""}>${value} coluna${value > 1 ? "s" : ""}</option>`).join("")}</select></label>
          <label><span>Tablet</span><select data-screen-columns-tablet>${[1,2,3].map((value) => `<option value="${value}" ${Number(screenLayout.colunas_tablet || 1) === value ? "selected" : ""}>${value} coluna${value > 1 ? "s" : ""}</option>`).join("")}</select></label>
          <label><span>Celular</span><select data-screen-columns-mobile>${[1,2].map((value) => `<option value="${value}" ${Number(screenLayout.colunas_mobile || 1) === value ? "selected" : ""}>${value} coluna${value > 1 ? "s" : ""}</option>`).join("")}</select></label>
          <label><span>Densidade</span><select data-screen-density><option value="compacta" ${(screenLayout.densidade || "compacta") === "compacta" ? "selected" : ""}>Compacta</option><option value="padrao" ${screenLayout.densidade === "padrao" ? "selected" : ""}>Padrao</option><option value="confortavel" ${screenLayout.densidade === "confortavel" ? "selected" : ""}>Confortavel</option></select></label>
          <label class="dynamic-builder-inline-check"><input type="checkbox" data-screen-uniform-height ${screenLayout.altura_uniforme ? "checked" : ""}><span>Altura uniforme</span></label>
        </div>
      </section>
      <section class="dynamic-builder-screen-section ${dashboardFiltersEnabled ? "" : "hidden"}" data-screen-filter-settings>
        <h4>${screen.tipo === "dashboard" ? "Filtros do dashboard" : "Filtros personalizados"}</h4>
        <div class="dynamic-builder-screen-options content-options">
          <fieldset><legend>Controles exibidos</legend>
            <label><input type="checkbox" data-screen-filter-status ${screenFilters.mostrar_status ? "checked" : ""}> Status</label>
            <label><input type="checkbox" data-screen-filter-negotiator ${screenFilters.mostrar_negociador ? "checked" : ""}> Negociador</label>
            <label><input type="checkbox" data-screen-filter-wallet ${screenFilters.mostrar_carteira ? "checked" : ""}> Carteira</label>
            <label><input type="checkbox" data-screen-filter-sort ${screenFilters.mostrar_ordenacao ? "checked" : ""}> Ordenacao</label>
          </fieldset>
          <fieldset><legend>Campos da ferramenta</legend>${(editing.campos || []).map((field) => `<label><input type="checkbox" data-screen-filter-field value="${escapeHtml(field.chave)}" ${(screenFilters.campos || []).includes(field.chave) ? "checked" : ""}> ${escapeHtml(field.nome)}</label>`).join("") || "<small>Nenhum campo disponivel.</small>"}</fieldset>
        </div>
        <h4>${screen.tipo === "dashboard" ? "Periodo analisado" : "Data e prazo"}</h4>
        <div class="dynamic-builder-layout-grid filters">
          <label><span>Campo de data</span><select data-screen-date-field><option value="">Selecionar campo</option>${dateFields.map((field) => `<option value="${escapeHtml(field.chave)}" ${screenFilters.campo_data === field.chave ? "selected" : ""}>${escapeHtml(field.nome)}</option>`).join("")}</select></label>
          <label><span>Comportamento</span><select data-screen-date-mode>${availableDateModes.map(([value,label]) => `<option value="${value}" ${(screenFilters.modo_data || "none") === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>
          ${screen.tipo === "dashboard" ? '<input type="hidden" data-screen-group-deadline><input type="hidden" data-screen-groups-collapsed><input type="hidden" data-screen-group-mode value="none"><input type="hidden" data-screen-group-field>' : ""}
        </div>
        ${screen.tipo === "dashboard" ? "" : `<fieldset class="dynamic-builder-deadline-options"><legend>Botoes de prazo exibidos</legend>${deadlineFilterOptions.map(([value, label]) => `<label><input type="checkbox" data-screen-deadline-option value="${value}" ${(screenFilters.prazos_visiveis || []).includes(value) ? "checked" : ""}> ${label}</label>`).join("")}</fieldset>`}
      </section>
      <section class="dynamic-builder-screen-section ${screen.tipo === "dashboard" ? "hidden" : ""}">
        <h4>Agrupamento dos cards</h4>
        <div class="dynamic-builder-layout-grid card-behavior">
          <label><span>Agrupar por</span><select data-screen-group-mode>
            <option value="none" ${screenGrouping.modo === "none" ? "selected" : ""}>Sem agrupamento</option>
            <option value="deadline" ${screenGrouping.modo === "deadline" ? "selected" : ""}>Prazo inteligente</option>
            <option value="status" ${screenGrouping.modo === "status" ? "selected" : ""}>Status</option>
            <option value="field" ${screenGrouping.modo === "field" ? "selected" : ""}>Campo da ferramenta</option>
          </select></label>
          <label><span>Campo usado no agrupamento</span><select data-screen-group-field><option value="">Selecione</option>${(editing.campos || []).map((field) => `<option value="${escapeAttr(field.chave)}" ${screenGrouping.campo === field.chave ? "selected" : ""}>${escapeHtml(field.nome)}</option>`).join("")}</select></label>
          <label class="dynamic-builder-inline-check"><input type="checkbox" data-screen-groups-collapsed ${screenGrouping.iniciar_recolhido ? "checked" : ""}><span>Iniciar grupos recolhidos</span></label>
          <input type="hidden" data-screen-group-deadline ${screenGrouping.modo === "deadline" ? "checked" : ""}>
        </div>
      </section>
      <section class="dynamic-builder-screen-section ${screen.tipo === "dashboard" ? "hidden" : ""}">
        <h4>Acoes na lateral do card</h4>
        <div class="dynamic-builder-screen-options card-action-options">
          <fieldset><legend>Botoes auxiliares</legend>
            <label><input type="checkbox" data-screen-action-copy ${screenActions.copiar ? "checked" : ""}> Copiar dados</label>
            <label><input type="checkbox" data-screen-action-notes ${screenActions.observacoes ? "checked" : ""}> Observacoes</label>
            <label><input type="checkbox" data-screen-action-updated ${screenActions.mostrar_atualizacao ? "checked" : ""}> Exibir ultima atualizacao</label>
          </fieldset>
          <fieldset><legend>Campos copiados</legend>${(editing.campos || []).map((field) => `<label><input type="checkbox" data-screen-action-copy-field value="${escapeAttr(field.chave)}" ${(screenActions.copiar_campos || []).includes(field.chave) ? "checked" : ""}> ${escapeHtml(field.nome)}</label>`).join("")}</fieldset>
        </div>
        <div class="dynamic-builder-layout-grid card-behavior">
          <label><span>Acao principal</span><select data-screen-action-mode><option value="none" ${screenActions.status_modo === "none" ? "selected" : ""}>Nenhuma</option><option value="open" ${screenActions.status_modo === "open" ? "selected" : ""}>Abrir registro</option><option value="select" ${screenActions.status_modo === "select" ? "selected" : ""}>Select de status/opcao</option><option value="button" ${screenActions.status_modo === "button" ? "selected" : ""}>Botao unico</option></select></label>
          <label><span>Origem das opcoes</span><select data-screen-action-source><option value="flow" ${screenActions.status_origem === "flow" ? "selected" : ""}>Status da ferramenta</option><option value="field" ${screenActions.status_origem === "field" ? "selected" : ""}>Campo select</option></select></label>
          <label><span>Campo select</span><select data-screen-action-field><option value="">Selecione</option>${(editing.campos || []).filter((field) => ["select", "multiselect"].includes(field.tipo)).map((field) => `<option value="${escapeAttr(field.chave)}" ${screenActions.status_campo === field.chave ? "selected" : ""}>${escapeHtml(field.nome)}</option>`).join("")}</select></label>
          <label><span>Destino do botao unico</span><select data-screen-action-target><option value="">Abrir registro</option>${(editing.statuses || []).map((status) => `<option value="${escapeAttr(status.codigo)}" ${screenActions.botao_status === status.codigo ? "selected" : ""}>${escapeHtml(status.nome)}</option>`).join("")}</select></label>
          <label><span>Texto do botao</span><input data-screen-action-label value="${escapeAttr(screenActions.botao_rotulo)}" placeholder="Ex.: Concluir"></label>
        </div>
      </section>
      <section class="dynamic-builder-screen-section ${screen.tipo === "dashboard" ? "hidden" : ""}">
        <div class="dynamic-builder-field-layout-head"><h4>Composicao dos cards</h4><small>Defina a funcao, largura e possibilidade de copiar cada campo.</small></div>
        <div class="dynamic-builder-card-fields">
          ${layoutFields.map((field) => {
            const config = fieldLayout[field.chave] || {};
            return `<div data-screen-field-layout="${escapeAttr(field.chave)}"><strong>${escapeHtml(field.nome)}</strong><select data-screen-field-role>${cardFieldRoles.map(([value,label]) => `<option value="${value}" ${(config.papel || "info") === value ? "selected" : ""}>${label}</option>`).join("")}</select><select data-screen-field-width><option value="auto" ${(config.largura || "auto") === "auto" ? "selected" : ""}>Automatica</option><option value="full" ${config.largura === "full" ? "selected" : ""}>Linha inteira</option><option value="half" ${config.largura === "half" ? "selected" : ""}>Meia linha</option><option value="third" ${config.largura === "third" ? "selected" : ""}>1/3 da linha</option></select><label title="Permitir copiar"><input type="checkbox" data-screen-field-copyable ${config.copiavel ? "checked" : ""}> Copiar</label></div>`;
          }).join("") || '<small>Nenhum campo disponivel.</small>'}
        </div>
      </section>
    </article>`;
  target.querySelectorAll("[data-select-screen]").forEach((button) => button.addEventListener("click", () => {
    collectBuilder();
    builderScreenIndex = Number(button.dataset.selectScreen);
    previewScreenId = ensureScreens()[builderScreenIndex]?.id || "";
    renderScreenRows();
    renderBuilderPreview();
  }));
  target.querySelectorAll("[data-remove-screen]").forEach((button) => button.addEventListener("click", () => {
    collectBuilder();
    editing.configuracao.telas.splice(Number(button.dataset.removeScreen), 1);
    builderScreenIndex = Math.min(builderScreenIndex, editing.configuracao.telas.length - 1);
    previewScreenId = "";
    markBuilderDirty();
    renderScreenRows();
    renderBuilderPreview();
  }));
  target.querySelectorAll("[data-duplicate-screen]").forEach((button) => button.addEventListener("click", () => {
    collectBuilder();
    const index = Number(button.dataset.duplicateScreen);
    const source = editing.configuracao.telas[index];
    const copy = { ...source, id: `${source.id || "tela"}-copia`, nome: `${source.nome || "Tela"} copia`, campos: [...(source.campos || [])], componentes: [...(source.componentes || [])], status_codes: [...(source.status_codes || [])], historico_status_codes: [...(source.historico_status_codes || [])], layout: { ...(source.layout || {}) }, filtros: { ...(source.filtros || {}) }, agrupamento: structuredClone(source.agrupamento || defaultGroupingConfig()), acoes_card: structuredClone(source.acoes_card || defaultCardActionsConfig()), campo_layout: structuredClone(source.campo_layout || {}), dashboard: structuredClone(source.dashboard || {}) };
    editing.configuracao.telas.splice(index + 1, 0, copy);
    builderScreenIndex = index + 1;
    markBuilderDirty();
    renderScreenRows();
    renderBuilderPreview();
  }));
  target.querySelector("#addDynamicScreenInlineBtn")?.addEventListener("click", addBuilderScreen);
  target.querySelector("[data-screen-type]")?.addEventListener("change", () => {
    collectBuilder();
    const active = ensureScreens()[builderScreenIndex];
    if (active.tipo === "dashboard") ensureDashboardConfig(active);
    markBuilderDirty();
    renderScreenRows();
    renderBuilderPreview();
  });
  target.querySelector("[data-add-dashboard-block]")?.addEventListener("click", () => {
    collectBuilder();
    const active = ensureScreens()[builderScreenIndex];
    const dashboard = ensureDashboardConfig(active);
    dashboard.blocks.push(createDashboardBlock("metric", dashboard.blocks.length));
    markBuilderDirty();
    renderScreenRows();
    renderBuilderPreview();
  });
  target.querySelectorAll("[data-dashboard-block]").forEach((block, blockIndex) => {
    block.querySelector("[data-remove-dashboard-block]")?.addEventListener("click", () => {
      collectBuilder();
      const dashboard = ensureDashboardConfig(ensureScreens()[builderScreenIndex]);
      dashboard.blocks.splice(blockIndex, 1);
      if (!dashboard.blocks.length) dashboard.blocks.push(createDashboardBlock("metric", 0));
      markBuilderDirty();
      renderScreenRows();
      renderBuilderPreview();
    });
    block.querySelectorAll("[data-move-dashboard-block]").forEach((button) => button.addEventListener("click", () => {
      collectBuilder();
      const dashboard = ensureDashboardConfig(ensureScreens()[builderScreenIndex]);
      const targetIndex = button.dataset.moveDashboardBlock === "up" ? blockIndex - 1 : blockIndex + 1;
      if (targetIndex < 0 || targetIndex >= dashboard.blocks.length) return;
      const [moved] = dashboard.blocks.splice(blockIndex, 1);
      dashboard.blocks.splice(targetIndex, 0, moved);
      markBuilderDirty();
      renderScreenRows();
      renderBuilderPreview();
    }));
    block.querySelector("[data-dashboard-block-type]")?.addEventListener("change", () => {
      collectBuilder();
      markBuilderDirty();
      renderScreenRows();
      renderBuilderPreview();
    });
    block.querySelector("[data-dashboard-block-aggregation]")?.addEventListener("change", () => {
      collectBuilder();
      markBuilderDirty();
      renderScreenRows();
      renderBuilderPreview();
    });
    block.querySelectorAll("input,select").forEach((control) => {
      if (control.matches("[data-dashboard-block-type]")) return;
      control.addEventListener("change", () => {
        collectBuilder();
        markBuilderDirty();
        scheduleBuilderPreview();
      });
      if (control.matches("[data-dashboard-block-title]")) control.addEventListener("input", () => {
        collectBuilder();
        markBuilderDirty();
        scheduleBuilderPreview();
      });
    });
  });
  target.querySelectorAll("[data-screen-field]").forEach((input) => input.addEventListener("change", () => {
    collectBuilder();
    renderScreenRows();
    renderBuilderPreview();
  }));
  target.querySelectorAll("[data-screen-component]").forEach((input) => input.addEventListener("change", () => {
    collectBuilder();
    markBuilderDirty();
    if (ensureScreens()[builderScreenIndex]?.tipo === "dashboard" && input.value === "filtros") {
      renderScreenRows();
      renderBuilderPreview();
      return;
    }
    scheduleBuilderPreview();
  }));
  target.querySelectorAll(`
    [data-screen-filter-status],
    [data-screen-filter-negotiator],
    [data-screen-filter-wallet],
    [data-screen-filter-sort],
    [data-screen-filter-field],
    [data-screen-date-field],
    [data-screen-date-mode],
    [data-screen-group-deadline],
    [data-screen-groups-collapsed],
    [data-screen-group-mode],
    [data-screen-group-field],
    [data-screen-action-copy],
    [data-screen-action-copy-field],
    [data-screen-action-notes],
    [data-screen-action-updated],
    [data-screen-action-mode],
    [data-screen-action-source],
    [data-screen-action-field],
    [data-screen-action-target],
    [data-screen-action-label]
  `).forEach((control) => control.addEventListener("change", () => {
    // Commit immediately so switching through the live preview cannot discard the last choice.
    collectBuilder();
    markBuilderDirty();
    scheduleBuilderPreview();
  }));
  let draggedIndex = null;
  target.querySelectorAll("[data-screen-list-index]").forEach((item) => {
    item.addEventListener("dragstart", (event) => {
      draggedIndex = Number(item.dataset.screenListIndex);
      item.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
    });
    item.addEventListener("dragend", () => { item.classList.remove("dragging"); draggedIndex = null; });
    item.addEventListener("dragover", (event) => { event.preventDefault(); event.dataTransfer.dropEffect = "move"; });
    item.addEventListener("drop", (event) => {
      event.preventDefault();
      const targetIndex = Number(item.dataset.screenListIndex);
      if (draggedIndex === null || draggedIndex === targetIndex) return;
      collectBuilder();
      const [moved] = editing.configuracao.telas.splice(draggedIndex, 1);
      editing.configuracao.telas.splice(targetIndex, 0, moved);
      builderScreenIndex = targetIndex;
      markBuilderDirty();
      renderScreenRows();
      renderBuilderPreview();
    });
  });
}

function addBuilderScreen() {
  collectBuilder();
  const index = editing.configuracao.telas.length + 1;
  editing.configuracao.telas.push({ id: `tela-${index}`, nome: `Tela ${index}`, icone: "T", tipo: "lista", visivel_negocial: true, visivel_gerencial: true, status_codes: [], historico_status_codes: [], campos: [], componentes: ["busca", "lista", "acoes"], filtros: defaultFilterConfig(false), agrupamento: defaultGroupingConfig(), acoes_card: defaultCardActionsConfig() });
  builderScreenIndex = editing.configuracao.telas.length - 1;
  previewScreenId = editing.configuracao.telas[builderScreenIndex].id;
  markBuilderDirty();
  renderScreenRows();
  renderBuilderPreview();
}

function selectedMetricKeys() {
  const configured = editing?.configuracao?.metricas_cards;
  if (Array.isArray(configured)) return configured;
  if (editing?.configuracao?.mostrar_cards === false) return [];
  const usesStatus = editing?.tipo === "SOLICITACAO" || editing?.configuracao?.usar_status !== false;
  if (usesStatus && editing?.statuses?.length) {
    return editing.statuses.map((status) => `STATUS:${status.codigo}`);
  }
  return ["TOTAL", "MES_ATUAL"];
}

function renderMetricOptions() {
  const target = $("#dynamicToolMetricOptions");
  if (!target) return;
  const selected = new Set(selectedMetricKeys());
  const cardsEnabled = $("#dynamicToolCards")?.checked ?? editing?.configuracao?.mostrar_cards !== false;
  const statusMetrics = statusEnabled()
    ? (editing.statuses || []).filter((status) => status.codigo).map((status) => ({
        key: `STATUS:${status.codigo}`,
        name: status.nome || status.codigo,
        description: `Quantidade de registros em ${status.nome || status.codigo}.`,
        color: status.cor || "#2563eb",
      }))
    : [];
  const options = [
    { key: "TOTAL", name: "Total de registros", description: "Quantidade completa da ferramenta.", color: editing.cor || "#2563eb" },
    { key: "MES_ATUAL", name: "Criados neste mes", description: "Registros criados na competencia atual.", color: "#059669" },
    ...statusMetrics,
  ];
  target.classList.toggle("disabled", !cardsEnabled);
  target.innerHTML = options.map((option) => `
    <label class="dynamic-builder-metric-option" style="--metric-color:${escapeHtml(option.color)}">
      <input type="checkbox" data-metric-key="${escapeHtml(option.key)}" ${selected.has(option.key) ? "checked" : ""} ${cardsEnabled ? "" : "disabled"}>
      <i></i>
      <span><strong>${escapeHtml(option.name)}</strong><small>${escapeHtml(option.description)}</small></span>
    </label>
  `).join("");
}

function renderMainHubOptions() {
  const target = $("#dynamicToolMainHubOptions");
  const enabledInput = $("#dynamicToolMainHub");
  if (!target || !enabledInput) return;
  const configured = editing?.configuracao?.main_hub || {};
  const supportsStatus = statusEnabled();
  if (!supportsStatus) enabledInput.checked = false;
  enabledInput.disabled = !supportsStatus;
  const enabled = supportsStatus && enabledInput.checked;
  const selectedStatuses = new Set(configured.status_codes || []);
  const selectedFields = new Set(configured.field_keys || []);
  const statusOptions = statusEnabled() ? (editing.statuses || []) : [];
  const fieldOptions = (editing.campos || []).filter((field) => field.visivel_gerencial !== false);
  target.classList.toggle("disabled", !enabled);
  target.innerHTML = `
    <div class="dynamic-builder-hub-column">
      <strong>Status que geram pendencia</strong>
      <small>O registro permanece no Hub enquanto estiver em um destes status.</small>
      <div class="dynamic-builder-choice-list">
        ${statusOptions.map((status) => `<label><input type="checkbox" data-main-hub-status value="${escapeHtml(status.codigo)}" ${selectedStatuses.has(status.codigo) ? "checked" : ""} ${enabled ? "" : "disabled"}><i style="--choice-color:${escapeHtml(status.cor || "#2563eb")}"></i><span>${escapeHtml(status.nome || status.codigo)}</span></label>`).join("") || "<em>Ative o uso de status para gerar pendencias.</em>"}
      </div>
    </div>
    <div class="dynamic-builder-hub-column">
      <strong>Campos exibidos no Main Hub</strong>
      <small>Escolha ate oito informacoes para o resumo e os detalhes.</small>
      <div class="dynamic-builder-choice-list">
        ${fieldOptions.map((field) => `<label><input type="checkbox" data-main-hub-field value="${escapeHtml(field.chave)}" ${selectedFields.has(field.chave) ? "checked" : ""} ${enabled ? "" : "disabled"}><span>${escapeHtml(field.nome || field.chave)}</span></label>`).join("") || "<em>Adicione campos visiveis no Gerencial.</em>"}
      </div>
    </div>
  `;
  target.querySelectorAll("[data-main-hub-field]").forEach((input) => {
    input.addEventListener("change", (event) => {
      const selected = target.querySelectorAll("[data-main-hub-field]:checked");
      if (selected.length <= 8) return;
      event.target.checked = false;
      toast("Selecione no maximo 8 campos para o Main Hub.");
    });
  });
}

function activatePermissionTab(tab) {
  permissionTab = tab;
  document.querySelectorAll("[data-permission-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.permissionTab === tab);
  });
  document.querySelectorAll("[data-permission-panel]").forEach((panel) => {
    panel.classList.toggle("hidden", panel.dataset.permissionPanel !== tab);
  });
}

function markBuilderDirty() {
  builderDirty = true;
  $("#dynamicBuilderDirty")?.classList.remove("hidden");
}

function syncBuilderIdentityPreview() {
  const name = $("#dynamicToolName")?.value.trim() || "Nova ferramenta";
  const icon = $("#dynamicToolIcon")?.value.trim() || "F";
  const color = $("#dynamicToolColor")?.value || "#2563eb";
  const type = $("#dynamicToolType")?.value || "CADASTRO";
  const headerName = $("#dynamicBuilderHeaderName");
  const headerMeta = $("#dynamicBuilderHeaderMeta");
  const namePreview = $("#dynamicToolNamePreview");
  const iconPreview = $("#dynamicToolIconPreview");
  const colorValue = $("#dynamicToolColorValue");
  if (headerName) headerName.textContent = name;
  if (headerMeta) headerMeta.textContent = type === "SOLICITACAO" ? "Solicitacao" : "Cadastro";
  if (namePreview) namePreview.textContent = name;
  if (iconPreview) iconPreview.textContent = icon;
  if (colorValue) colorValue.textContent = color.toUpperCase();
  document.querySelector(".dynamic-builder-editor-icon")?.style.setProperty("--tool-color", color);
  document.querySelector(".dynamic-builder-sidebar-sample > div")?.style.setProperty("--tool-color", color);
}

function applyPermissionPreset(preset) {
  const panel = document.querySelector(`[data-permission-panel="${permissionTab}"]`);
  if (!panel) return;
  panel.querySelectorAll("[data-permission-scope]").forEach((row) => {
    const view = row.querySelector("[data-permission-view]");
    const controls = [
      row.querySelector("[data-permission-create]"),
      row.querySelector("[data-permission-edit]"),
      row.querySelector("[data-permission-transition]"),
      row.querySelector("[data-permission-export]"),
    ];
    view.checked = preset !== "none";
    controls.forEach((control) => {
      control.checked = preset === "all";
    });
  });
  markBuilderDirty();
}

function statusEnabled() {
  const type = $("#dynamicToolType")?.value || editing?.tipo || "CADASTRO";
  return type === "SOLICITACAO" || Boolean($("#dynamicToolUseStatus")?.checked);
}

function renderFlowPreview() {
  const target = $("#dynamicBuilderFlowPreview");
  if (!target) return;
  if (!statusEnabled()) {
    target.innerHTML = '<div class="dynamic-builder-empty">Este cadastro sera concluido diretamente, sem fluxo de status.</div>';
    return;
  }
  if (!editing.statuses?.length) {
    target.innerHTML = '<div class="dynamic-builder-empty">Adicione ao menos um status para montar o fluxo.</div>';
    return;
  }
  const transitionsByOrigin = new Map();
  (editing.transicoes || []).forEach((transition) => {
    if (!transitionsByOrigin.has(transition.origem_codigo)) transitionsByOrigin.set(transition.origem_codigo, []);
    transitionsByOrigin.get(transition.origem_codigo).push(transition);
  });
  target.innerHTML = `
    <div class="dynamic-flow-track">
      ${editing.statuses.map((status, index) => `
        <article class="dynamic-flow-stage ${status.inicial ? "is-initial" : ""} ${status.final ? "is-final" : ""}">
          <button class="dynamic-flow-node" type="button" data-flow-status="${index}">
            <i style="--status-color:${escapeHtml(status.cor || "#2563eb")}"></i>
            <span><small>Etapa ${index + 1}</small><strong>${escapeHtml(status.nome || status.codigo || "Sem nome")}</strong></span>
            <em>${status.inicial ? "Entrada" : status.final ? "Final" : "Andamento"}</em>
          </button>
          <div class="dynamic-flow-stage-actions">
            ${(transitionsByOrigin.get(status.codigo) || []).map((transition) => `
              <span>${escapeHtml(transition.nome || "Mover")} <b>&rarr; ${escapeHtml(editing.statuses.find((item) => item.codigo === transition.destino_codigo)?.nome || transition.destino_codigo)}</b></span>
            `).join("") || "<span>Sem proxima acao</span>"}
          </div>
        </article>
      `).join("")}
    </div>
  `;
  target.querySelectorAll("[data-flow-status]").forEach((button) => {
    button.addEventListener("click", () => {
      const row = document.querySelector(`[data-status-index="${button.dataset.flowStatus}"]`);
      row?.scrollIntoView({ behavior: "smooth", block: "center" });
      row?.classList.add("highlight");
      window.setTimeout(() => row?.classList.remove("highlight"), 900);
    });
  });
}

function previewFieldValue(field) {
  if (field.tipo === "moeda") return "R$ 12.500,00";
  if (field.tipo === "data") return "04/08/2026";
  if (field.tipo === "numero") return "1024";
  if (field.tipo === "boolean") return "Sim";
  if (field.tipo === "usuario") return "NEGOCIADOR";
  if (field.tipo === "carteira") return "CARTEIRA";
  if (field.tipo === "arquivo") return "documento.pdf";
  if (field.tipo === "select" || field.tipo === "multiselect") return field.opcoes?.[0] || "Opcao";
  return field.nome || field.chave || "Valor";
}

function previewScreenFields(screen) {
  const visibilityKey = previewAudience === "gerencial" ? "visivel_gerencial" : "visivel_negocial";
  const visible = (editing.campos || []).filter((field) => field[visibilityKey] !== false);
  const selected = new Set(screen.campos || []);
  return selected.size ? visible.filter((field) => selected.has(field.chave)) : visible;
}

function renderPreviewMetrics() {
  if (editing.configuracao?.mostrar_cards === false) return "";
  const selected = selectedMetricKeys().slice(0, 4);
  if (!selected.length) return "";
  return `<div class="dynamic-preview-metrics">${selected.map((key, index) => {
    const statusCode = key.startsWith("STATUS:") ? key.slice(7) : "";
    const status = (editing.statuses || []).find((item) => item.codigo === statusCode);
    const label = key === "TOTAL" ? "Total de registros" : key === "MES_ATUAL" ? "Criados neste mes" : status?.nome || statusCode;
    return `<article style="--preview-accent:${escapeHtml(status?.cor || editing.cor || "#2563eb")}"><small>${escapeHtml(label)}</small><strong>${index ? index * 4 + 2 : 18}</strong></article>`;
  }).join("")}</div>`;
}

function renderPreviewFilters(screen) {
  const components = new Set(screen.componentes || []);
  if (!components.has("busca") && !components.has("filtros")) return "";
  const filters = normalizedFilterConfig(screen.filtros || {});
  const selectedFields = (filters.campos || []).map((key) => (editing.campos || []).find((field) => field.chave === key)?.nome || key);
  const controls = [
    filters.mostrar_status ? "Status" : "",
    filters.mostrar_negociador ? "Negociador" : "",
    filters.mostrar_carteira ? "Carteira" : "",
    filters.mostrar_ordenacao ? "Ordenacao" : "",
    filters.modo_data !== "none" ? "Data" : "",
    ...selectedFields,
  ].filter(Boolean);
  return `<div class="dynamic-preview-filters">
    ${components.has("busca") ? '<span>Buscar registros...</span>' : ""}
    ${components.has("filtros") ? controls.map((label) => `<button type="button">${escapeHtml(label)}</button>`).join("") : ""}
  </div>${components.has("filtros") && filters.modo_data === "deadline" ? `<div class="dynamic-preview-deadlines">${deadlineFilterOptions.filter(([value]) => (filters.prazos_visiveis || []).includes(value)).map(([value, label], index) => `<span class="${index === 0 ? "active" : ""}">${escapeHtml(label)}</span>`).join("")}</div>` : ""}`;
}

function renderPreviewStatusTabs(screen) {
  if (!(screen.componentes || []).includes("filtros") || !normalizedFilterConfig(screen.filtros || {}).mostrar_status || !statusEnabled()) return "";
  const selected = new Set(screen.status_codes || []);
  const statuses = selected.size ? (editing.statuses || []).filter((status) => selected.has(status.codigo)) : (editing.statuses || []);
  if (!statuses.length) return "";
  return `<div class="dynamic-preview-status-tabs"><span class="active">Todos</span>${statuses.slice(0, 5).map((status) => `<span><i style="--status-color:${escapeHtml(status.cor || "#2563eb")}"></i>${escapeHtml(status.nome || status.codigo)}</span>`).join("")}</div>`;
}

function renderPreviewTable(fields) {
  const columns = fields.slice(0, 6);
  return `<div class="dynamic-preview-table"><table><thead><tr><th>#</th>${columns.map((field) => `<th>${escapeHtml(field.nome || field.chave)}</th>`).join("")}</tr></thead><tbody>${[1, 2, 3].map((row) => `<tr><th>${row}</th>${columns.map((field) => `<td>${escapeHtml(previewFieldValue(field))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

function renderPreviewList(screen, fields) {
  const components = new Set(screen.componentes || []);
  const fieldLayout = screen.campo_layout || {};
  const visibleFields = fields.filter((field) => fieldLayout[field.chave]?.papel !== "oculto");
  const titleField = visibleFields.find((field) => fieldLayout[field.chave]?.papel === "titulo") || visibleFields.find((field) => field.chave === editing.configuracao?.campo_titulo) || visibleFields[0];
  const subtitleField = visibleFields.find((field) => fieldLayout[field.chave]?.papel === "subtitulo");
  const detailFields = visibleFields.filter((field) => ![titleField?.chave, subtitleField?.chave].includes(field.chave)).slice(0, 5);
  const status = (editing.statuses || []).find((item) => (screen.status_codes || []).includes(item.codigo)) || editing.statuses?.[0];
  const layout = screen.layout || {};
  const grouping = normalizedGroupingConfig(screen.agrupamento || {}, screen.filtros || {});
  const actions = normalizedCardActionsConfig(screen.acoes_card || {});
  const actionPreview = () => {
    const copy = actions.copiar ? '<button type="button" title="Copiar">&#10697;</button>' : "";
    const notes = actions.observacoes ? '<button type="button">Obs.</button>' : "";
    const primary = actions.status_modo === "select" ? `<select><option>${escapeHtml(status?.nome || "Status")}</option></select>` : actions.status_modo === "button" ? `<button type="button">${escapeHtml(actions.botao_rotulo || "Executar")}</button>` : actions.status_modo === "open" ? `<button type="button">${escapeHtml(actions.botao_rotulo || "Abrir")} &rsaquo;</button>` : "";
    return `${copy}${notes}${primary}`;
  };
  const cards = `<div class="dynamic-preview-list density-${escapeAttr(layout.densidade || "compacta")} ${layout.altura_uniforme ? "uniform" : ""}" style="--card-cols:${Number(layout.colunas_desktop || 1)}">${[1, 2, 3, 4].slice(0, Math.max(2, Number(layout.colunas_desktop || 1))).map(() => `
    <article class="parecer-style" style="--preview-accent:${escapeHtml(status?.cor || editing.cor || "#2563eb")}">
      <i class="dynamic-preview-card-marker" aria-hidden="true"></i>
      <div><header><strong>${escapeHtml(previewFieldValue(titleField || { nome: "Cliente" }))}</strong>${actions.mostrar_atualizacao ? "<time>Atualizado agora</time>" : ""}</header>${subtitleField ? `<em>${escapeHtml(previewFieldValue(subtitleField))}</em>` : ""}<p>${detailFields.map((field) => `<span class="role-${escapeAttr(fieldLayout[field.chave]?.papel || "info")}">${escapeHtml(field.nome)}: <b>${escapeHtml(previewFieldValue(field))}</b></span>`).join("")}</p></div>
      <aside><small>${escapeHtml(status?.nome || "Registro")}</small>${components.has("acoes") ? actionPreview() : ""}</aside>
    </article>`).join("")}</div>`;
  if (grouping.modo === "none") return cards;
  const groupLabel = grouping.modo === "deadline" ? "Vencidos" : grouping.modo === "status" ? (status?.nome || "Status") : ((editing.campos || []).find((field) => field.chave === grouping.campo)?.nome || "Grupo");
  return `<div class="dynamic-preview-group"><header><strong>${escapeHtml(groupLabel)}</strong><span>4 registros</span></header>${cards}</div>`;
}

function renderPreviewDashboard(screen, fields) {
  const dashboard = screen.dashboard?.blocks?.length ? screen.dashboard : defaultDashboardConfig();
  const statuses = editing.statuses || [];
  const blockContent = (block) => {
    if (block.tipo === "metric") return `<strong class="value">${block.agregacao === "count" ? "128" : block.agregacao === "ratio" ? "84,2%" : block.agregacao === "duration_average" ? "4,6 dias" : "R$ 84.250,00"}</strong><small>Atualizado agora</small>`;
    if (["status", "funnel"].includes(block.tipo)) return `<div class="status-grid ${block.tipo === "funnel" ? "funnel" : ""}">${statuses.slice(0, 4).map((status, index) => `<span style="--item-color:${escapeHtml(status.cor || block.cor)}"><b>${index * 7 + 12}</b><small>${escapeHtml(status.nome)}</small></span>`).join("") || "<small>Sem status configurados</small>"}</div>`;
    if (["distribution", "ranking"].includes(block.tipo)) return `<div class="bar-list">${[82, 64, 43, 26].map((width, index) => `<span style="--bar:${width}%"><small>${escapeHtml(fields[index]?.nome || `Grupo ${index + 1}`)}</small><b>${92 - index * 17}</b><i></i></span>`).join("")}</div>`;
    if (block.tipo === "timeline") return `<div class="timeline"><i style="--point:35%"></i><i style="--point:62%"></i><i style="--point:48%"></i><i style="--point:85%"></i><i style="--point:70%"></i></div>`;
    if (block.tipo === "comparison") return '<div class="dynamic-dashboard-comparison"><strong>R$ 84.250,00</strong><span class="positive">+12,4%</span><small>Periodo anterior: R$ 74.955,00</small></div>';
    if (block.tipo === "deadline") return `<div class="bar-list">${[35, 18, 52, 74].map((width, index) => `<span style="--bar:${width}%"><small>${["Vencidos", "Hoje", "Proximos 7 dias", "Posteriores"][index]}</small><b>${[12, 4, 18, 31][index]}</b><i></i></span>`).join("")}</div>`;
    if (block.tipo === "validation") return '<div class="dynamic-dashboard-alert"><strong>7</strong><span>registros exigem atencao</span></div>';
    if (block.tipo === "queue") return `<div class="recent-list">${[1,2,3].map((value) => `<span><b>Prioridade ${value}</b><small>Aguardando acao</small></span>`).join("")}</div>`;
    return `<div class="recent-list">${[1,2,3].map((value) => `<span><b>${escapeHtml(fields[value - 1]?.nome || `Registro ${value}`)}</b><small>Atualizado agora</small></span>`).join("")}</div>`;
  };
  return `<div class="dynamic-preview-dashboard configurable">${dashboard.blocks.map((block) => `<section class="block-${escapeAttr(block.tipo || "metric")}" style="--preview-accent:${escapeHtml(block.cor || editing.cor || "#2563eb")};--dashboard-span:${Number(block.largura || 6)}"><header><strong>${escapeHtml(block.titulo || "Bloco")}</strong><small>${dashboardBlockTypes.find(([value]) => value === block.tipo)?.[1] || "Indicador"}</small></header>${blockContent(block)}</section>`).join("")}</div>`;
}

function renderBuilderPreview() {
  const target = $("#dynamicBuilderPreview");
  if (!target) return;
  collectBuilder();
  const visibilityKey = previewAudience === "gerencial" ? "visivel_gerencial" : "visivel_negocial";
  const previewScreens = ensureScreens().filter((screen) => screen[visibilityKey] !== false);
  if (!previewScreens.some((screen) => screen.id === previewScreenId)) {
    const activeScreen = ensureScreens()[builderScreenIndex];
    previewScreenId = activeScreen?.[visibilityKey] !== false && previewScreens.includes(activeScreen)
      ? activeScreen.id
      : previewScreens[0]?.id || "";
  }
  const previewScreen = previewScreens.find((screen) => screen.id === previewScreenId);
  document.querySelectorAll("[data-preview-audience]").forEach((button) => {
    button.classList.toggle("active", button.dataset.previewAudience === previewAudience);
  });
  if (!previewScreen) {
    target.innerHTML = `<div class="dynamic-builder-empty">Nenhuma tela foi habilitada para o ${previewAudience === "gerencial" ? "Gerencial" : "Negocial"}.</div>`;
    return;
  }
  const fields = previewScreenFields(previewScreen);
  const components = new Set(previewScreen.componentes || []);
  const isDashboard = previewScreen.tipo === "dashboard";
  const isSpreadsheet = previewScreen.tipo === "planilha" || components.has("planilha");
  const content = isDashboard
    ? renderPreviewDashboard(previewScreen, fields)
    : isSpreadsheet
      ? renderPreviewTable(fields)
      : renderPreviewList(previewScreen, fields);
  target.innerHTML = `
    <div class="dynamic-preview-shell ${previewAudience}">
      <aside class="dynamic-preview-sidebar">
        <span class="dynamic-preview-brand">${previewAudience === "gerencial" ? "B" : "N"}</span>
        <small>${previewAudience === "gerencial" ? "BACKOFFICE" : "NEGOCIAL"}</small>
        <div class="dynamic-preview-tool" style="--tool-color:${escapeHtml(editing.cor || "#2563eb")}">
          <b>${escapeHtml(editing.icone || "F")}</b><span>${escapeHtml(editing.nome || "Nova ferramenta")}</span>
        </div>
      </aside>
      <main class="dynamic-preview-main">
        <header>
          <div><small>${previewAudience === "gerencial" ? "Sistema gerencial" : "Sistema negocial"}</small><h3>${escapeHtml(editing.nome || "Nova ferramenta")}</h3></div>
          <button type="button">${previewAudience === "gerencial" ? "Atualizar" : "Novo registro"}</button>
        </header>
        <nav class="dynamic-preview-screen-tabs">
          ${previewScreens.map((screen) => `<button type="button" class="${screen.id === previewScreen.id ? "active" : ""}" data-preview-screen="${escapeAttr(screen.id)}"><b>${escapeHtml(screen.icone || screen.nome.slice(0, 1))}</b>${escapeHtml(screen.nome)}</button>`).join("")}
        </nav>
        <div class="dynamic-preview-screen-label"><strong>${escapeHtml(previewScreen.nome)}</strong><small>${screenTypes.find(([value]) => value === previewScreen.tipo)?.[1] || "Tela"}</small></div>
        ${components.has("metricas") && !isDashboard ? renderPreviewMetrics() : ""}
        ${renderPreviewStatusTabs(previewScreen)}
        ${renderPreviewFilters(previewScreen)}
        <div class="dynamic-preview-content">${content}</div>
      </main>
    </div>
  `;
  target.querySelectorAll("[data-preview-screen]").forEach((button) => {
    button.addEventListener("click", () => {
      collectBuilder();
      previewScreenId = button.dataset.previewScreen;
      const index = ensureScreens().findIndex((screen) => screen.id === previewScreenId);
      if (index >= 0 && index !== builderScreenIndex) {
        builderScreenIndex = index;
        renderScreenRows();
      }
      renderBuilderPreview();
    });
  });
}

function scheduleBuilderPreview() {
  window.cancelAnimationFrame(previewRenderFrame);
  previewRenderFrame = window.requestAnimationFrame(() => renderBuilderPreview());
}

function activateBuilderTab(tab) {
  builderTab = tab;
  document.querySelectorAll("[data-builder-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.builderTab === tab);
  });
  document.querySelectorAll("[data-builder-panel]").forEach((panel) => {
    panel.classList.toggle("hidden", panel.dataset.builderPanel !== tab);
  });
  if (tab === "telas") renderBuilderPreview();
  if (tab === "fluxo") renderFlowPreview();
}

function renderBuilderDialog(readonly = false) {
  document.querySelector("#dynamicToolBuilderDialog")?.remove();
  const dialog = document.createElement("dialog");
  dialog.id = "dynamicToolBuilderDialog";
  dialog.className = "dynamic-tool-builder-dialog";
  dialog.innerHTML = `
    <form class="modal-card" id="dynamicToolBuilderForm">
      <div class="dynamic-builder-editor-header">
        <div class="dynamic-builder-editor-title">
          <span class="dynamic-builder-editor-icon" style="--tool-color:${escapeHtml(editing.cor || "#2563eb")}">${escapeHtml(editing.icone || "F")}</span>
          <div><p class="eyebrow">Sistema negocial</p><h2 id="dynamicBuilderHeaderName">${escapeHtml(editing.nome || (editing.id ? "Editar ferramenta" : "Nova ferramenta"))}</h2></div>
          <small class="dynamic-builder-editor-meta" id="dynamicBuilderHeaderMeta">${editing.tipo === "SOLICITACAO" ? "Solicitacao" : "Cadastro"}</small>
          <span class="dynamic-tool-version ${editing.versao_status === "PUBLICADA" ? "published" : "draft"}">${escapeHtml(editing.versao_status === "PUBLICADA" ? "Publicada" : "Rascunho")}</span>
          <span class="dynamic-builder-dirty hidden" id="dynamicBuilderDirty">Alteracoes nao salvas</span>
        </div>
        <button class="icon-btn" type="button" data-close aria-label="Fechar">&times;</button>
      </div>
      <nav class="dynamic-builder-tabs" aria-label="Etapas da configuracao">
        <button type="button" data-builder-tab="geral">Geral</button>
        <button type="button" data-builder-tab="campos">Campos <span id="dynamicBuilderFieldCount">${editing.campos.length}</span></button>
        <button type="button" data-builder-tab="fluxo">Status e fluxo</button>
        <button type="button" data-builder-tab="telas">Telas</button>
        <button type="button" data-builder-tab="acessos">Acessos</button>
      </nav>
      <div class="dynamic-builder-body">
        <section class="dynamic-builder-panel" data-builder-panel="geral">
          <div class="dynamic-builder-page-head"><div><h3>Configuracao geral</h3><p>Identidade e comportamento principal da ferramenta.</p></div></div>
          <div class="dynamic-builder-general-layout">
            <section class="dynamic-builder-config-card dynamic-builder-identity-card">
              <div class="dynamic-builder-config-title"><h4>Identidade</h4></div>
              <div class="dynamic-builder-identity-grid">
                <label class="wide"><span>Nome da ferramenta</span><input id="dynamicToolName" value="${escapeHtml(editing.nome)}" placeholder="Ex.: APM" required></label>
                <label><span>Tipo</span><select id="dynamicToolType"><option value="CADASTRO" ${editing.tipo === "CADASTRO" ? "selected" : ""}>Cadastro</option><option value="SOLICITACAO" ${editing.tipo === "SOLICITACAO" ? "selected" : ""}>Solicitacao</option></select></label>
                <label><span>Campo usado como titulo</span><input id="dynamicToolTitleField" value="${escapeHtml(editing.configuracao?.campo_titulo || "CLIENTE")}" placeholder="CLIENTE"></label>
                <label class="wide"><span>Descricao</span><textarea id="dynamicToolDescription" rows="3" placeholder="Descricao curta para identificar a finalidade">${escapeHtml(editing.descricao || "")}</textarea></label>
              </div>
            </section>
            <section class="dynamic-builder-config-card dynamic-builder-appearance-card">
              <div class="dynamic-builder-config-title"><h4>Aparencia</h4></div>
              <div class="dynamic-builder-appearance-fields">
                <label><span>Icone ou sigla</span><input id="dynamicToolIcon" value="${escapeHtml(editing.icone || "F")}" maxlength="8" placeholder="A"></label>
                <label><span>Cor principal</span><span class="dynamic-builder-color-field"><input id="dynamicToolColor" type="color" value="${escapeHtml(editing.cor || "#2563eb")}"><code id="dynamicToolColorValue">${escapeHtml(editing.cor || "#2563eb")}</code></span></label>
              </div>
              <div class="dynamic-builder-sidebar-sample">
                <small>Previa na navegacao</small>
                <div style="--tool-color:${escapeHtml(editing.cor || "#2563eb")}">
                  <b id="dynamicToolIconPreview">${escapeHtml(editing.icone || "F")}</b>
                  <span id="dynamicToolNamePreview">${escapeHtml(editing.nome || "Nova ferramenta")}</span>
                </div>
              </div>
              <label class="dynamic-builder-toggle-card dynamic-builder-highlight-toggle"><input id="dynamicToolHighlight" type="checkbox" ${editing.destaque_gerencial ? "checked" : ""}><i></i><span><strong>Destacar ferramenta</strong><small>Exibe esta ferramenta na sidebar do Gerencial quando estiver ativa e publicada.</small></span></label>
            </section>
            <section class="dynamic-builder-config-card dynamic-builder-behavior-card">
              <div class="dynamic-builder-config-title"><h4>Comportamento</h4></div>
              <div class="dynamic-builder-switches">
                <label class="dynamic-builder-toggle-card"><input id="dynamicToolCards" type="checkbox" ${editing.configuracao?.mostrar_cards !== false ? "checked" : ""}><i></i><span><strong>Cards de metricas</strong><small>Exibe somente os indicadores selecionados abaixo.</small></span></label>
                <div class="dynamic-builder-status-config" id="dynamicToolStatusConfig">
                  <label class="dynamic-builder-toggle-card"><input id="dynamicToolUseStatus" type="checkbox" ${editing.tipo !== "CADASTRO" || editing.configuracao?.usar_status !== false ? "checked" : ""}><i></i><span><strong>Usar status</strong><small>Habilita fluxo operacional neste cadastro.</small></span></label>
                  <label class="dynamic-builder-toggle-card"><input id="dynamicToolNegotiatorStatus" type="checkbox" ${editing.configuracao?.negociador_define_status ? "checked" : ""}><i></i><span><strong>Status no cadastro</strong><small>O negociador escolhe o status inicial.</small></span></label>
                  <label class="dynamic-builder-toggle-card"><input id="dynamicToolChangeStatus" type="checkbox" ${editing.configuracao?.negociador_altera_status ? "checked" : ""}><i></i><span><strong>Alterar status depois</strong><small>Libera na planilha e edicao para acessos com permissao de Status.</small></span></label>
                </div>
              </div>
              <div class="dynamic-builder-metrics-config">
                <div><strong>Metricas exibidas</strong><small>Escolha exatamente quais cards aparecerao no sistema negocial.</small></div>
                <div class="dynamic-builder-metric-options" id="dynamicToolMetricOptions"></div>
              </div>
              <div class="dynamic-builder-main-hub-config">
                <label class="dynamic-builder-toggle-card"><input id="dynamicToolMainHub" type="checkbox" ${editing.configuracao?.main_hub?.enabled ? "checked" : ""}><i></i><span><strong>Notificar pendencias no Main Hub</strong><small>Exibe registros pendentes desta ferramenta no Hub e no sino de notificacoes.</small></span></label>
                <div class="dynamic-builder-main-hub-options" id="dynamicToolMainHubOptions"></div>
              </div>
            </section>
          </div>
        </section>
        <section class="dynamic-builder-panel hidden" data-builder-panel="campos">
          <div class="dynamic-builder-page-head"><div><h3>Campos da ferramenta</h3><p>Defina ordem, tipo, preenchimento e visibilidade.</p></div><button class="primary-btn" id="addDynamicFieldBtn" type="button">Adicionar campo</button></div>
          <div class="dynamic-builder-field-head" aria-hidden="true">
            <span></span><span>Nome</span><span>Chave</span><span>Tipo</span><span>Etapa</span>
            <span>Obrig.</span><span>Leitura</span><span>Automatico</span><span>Negocial</span><span>Gerencial</span><span>Opcoes</span><span>Regras</span><span></span>
          </div>
          <div class="dynamic-builder-rows" id="dynamicBuilderFields"></div>
        </section>
        <section class="dynamic-builder-panel hidden" data-builder-panel="fluxo">
          <div class="dynamic-builder-page-head">
            <div><h3>Fluxo operacional</h3><p>Organize por onde o registro entra, quais caminhos pode seguir e onde o trabalho termina.</p></div>
            <div class="dynamic-flow-templates">
              <span>Modelo inicial</span>
              <button class="secondary-btn" type="button" data-flow-template="approval">Solicitacao com aprovacao</button>
              <button class="secondary-btn" type="button" data-flow-template="simple">Cadastro simples</button>
            </div>
          </div>
          <ol class="dynamic-flow-steps" aria-label="Como configurar o fluxo">
            <li><b>1</b><span><strong>Crie as etapas</strong><small>Elas serao as abas da ferramenta.</small></span></li>
            <li><b>2</b><span><strong>Defina as acoes</strong><small>Escolha origem, botao e destino.</small></span></li>
            <li><b>3</b><span><strong>Libere os acessos</strong><small>Decida quem pode executar cada acao.</small></span></li>
          </ol>
          <div class="dynamic-builder-flow-preview" id="dynamicBuilderFlowPreview"></div>
          <section class="dynamic-builder-section" id="dynamicToolStatusesSection">
            <div class="dynamic-builder-section-head"><div><span class="dynamic-builder-section-number">1</span><h3>Etapas do processo</h3><small>Cada etapa aparece como uma aba para acompanhar os registros.</small></div><button class="secondary-btn" id="addDynamicStatusBtn" type="button">+ Nova etapa</button></div>
            <div class="dynamic-builder-rows" id="dynamicBuilderStatuses"></div>
          </section>
          <section class="dynamic-builder-section" id="dynamicToolTransitionsSection">
            <div class="dynamic-builder-section-head"><div><span class="dynamic-builder-section-number">2</span><h3>Acoes entre etapas</h3><small>Monte cada acao como uma frase: onde esta, qual botao aparece e para onde vai.</small></div><button class="secondary-btn" id="addDynamicTransitionBtn" type="button">+ Nova acao</button></div>
            <div class="dynamic-builder-rows" id="dynamicBuilderTransitions"></div>
          </section>
        </section>
        <section class="dynamic-builder-panel hidden" data-builder-panel="telas">
          <div class="dynamic-builder-page-head"><div><h3>Telas da ferramenta</h3><p>Monte a navegacao e escolha o que cada pagina apresenta.</p></div><div class="dynamic-flow-templates"><button class="secondary-btn" type="button" data-screen-preset="approval">Modelo com aprovacao</button><button class="secondary-btn" type="button" data-screen-preset="simple">Modelo simples</button><button class="primary-btn" id="addDynamicScreenBtn" type="button">Adicionar tela</button></div></div>
          <div class="dynamic-builder-screen-studio">
            <div class="dynamic-builder-screens" id="dynamicBuilderScreens"></div>
            <section class="dynamic-builder-live-preview">
              <div class="dynamic-builder-live-preview-head">
                <div><h3>Previa em tempo real</h3><p>A previa acompanha a tela selecionada.</p></div>
                <div class="dynamic-builder-preview-modes" aria-label="Sistema exibido na previa">
                  <button type="button" data-preview-audience="negocial">Negocial</button>
                  <button type="button" data-preview-audience="gerencial">Gerencial</button>
                </div>
              </div>
              <div id="dynamicBuilderPreview"></div>
            </section>
          </div>
        </section>
        <section class="dynamic-builder-panel hidden" data-builder-panel="acessos">
          <div class="dynamic-builder-page-head"><div><h3>Acessos</h3><p>Controle quem visualiza, cria, edita e movimenta registros.</p></div></div>
          <div class="dynamic-builder-subtabs">
            <button type="button" data-permission-tab="wallets">Carteiras</button>
            <button type="button" data-permission-tab="users">Excecoes por negociador</button>
            <span></span>
            <button type="button" data-permission-preset="all">Liberar tudo</button>
            <button type="button" data-permission-preset="read">Somente leitura</button>
            <button type="button" data-permission-preset="none">Remover acesso</button>
          </div>
          <div class="dynamic-builder-rows" id="dynamicBuilderPermissions"></div>
        </section>
      </div>
      <div class="modal-actions">
        <p class="dynamic-builder-save-error hidden" id="dynamicBuilderSaveError" role="alert"></p>
        <button class="secondary-btn" type="button" data-close>Cancelar</button>
        ${!readonly ? '<button class="primary-btn" type="submit">Salvar rascunho</button>' : ""}
      </div>
    </form>
  `;
  document.body.append(dialog);
  renderAllRows();
  syncStatusConfiguration();
  activateBuilderTab(builderTab);
  dialog.querySelectorAll("[data-builder-tab]").forEach((button) => {
    button.addEventListener("click", () => activateBuilderTab(button.dataset.builderTab));
  });
  dialog.querySelectorAll("[data-permission-tab]").forEach((button) => {
    button.addEventListener("click", () => activatePermissionTab(button.dataset.permissionTab));
  });
  dialog.querySelectorAll("[data-permission-preset]").forEach((button) => {
    button.addEventListener("click", () => applyPermissionPreset(button.dataset.permissionPreset));
  });
  dialog.querySelectorAll("[data-preview-audience]").forEach((button) => {
    button.addEventListener("click", () => {
      previewAudience = button.dataset.previewAudience;
      previewScreenId = "";
      renderBuilderPreview();
    });
  });
  dialog.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => dialog.close()));
  dialog.querySelector("form").addEventListener("input", (event) => {
    if (!event.target.matches("button")) {
      markBuilderDirty();
      if (builderTab === "telas") scheduleBuilderPreview();
    }
  });
  ["#dynamicToolName", "#dynamicToolIcon", "#dynamicToolColor", "#dynamicToolType"].forEach((selector) => {
    $(selector)?.addEventListener("input", syncBuilderIdentityPreview);
    $(selector)?.addEventListener("change", syncBuilderIdentityPreview);
  });
  $("#addDynamicFieldBtn").addEventListener("click", () => {
    collectBuilder();
    editing.campos.push({ chave: "", nome: "", tipo: "texto", etapa: 1, visivel_negocial: true, visivel_gerencial: true });
    markBuilderDirty();
    renderFieldRows();
  });
  $("#addDynamicStatusBtn").addEventListener("click", () => {
    collectBuilder();
    editing.statuses.push({ codigo: "", nome: "", cor: "#2563eb", inicial: editing.statuses.length === 0, final: false });
    markBuilderDirty();
    renderStatusRows();
    renderTransitionRows();
    renderFlowPreview();
  });
  $("#addDynamicTransitionBtn").addEventListener("click", () => {
    finalizeStatusCodes();
    collectBuilder();
    const first = editing.statuses[0]?.codigo || "";
    const second = editing.statuses[1]?.codigo || first;
    editing.transicoes.push({ origem_codigo: first, destino_codigo: second, nome: "", permite_gerencial: true });
    markBuilderDirty();
    renderTransitionRows();
  });
  $("#addDynamicScreenBtn").addEventListener("click", addBuilderScreen);
  dialog.querySelectorAll("[data-screen-preset]").forEach((button) => button.addEventListener("click", () => {
    collectBuilder();
    editing.configuracao.telas = defaultScreens(button.dataset.screenPreset);
    builderScreenIndex = 0;
    previewScreenId = "";
    markBuilderDirty();
    renderScreenRows();
    renderBuilderPreview();
  }));
  dialog.querySelectorAll("[data-flow-template]").forEach((button) => {
    button.addEventListener("click", () => applyFlowTemplate(button.dataset.flowTemplate));
  });
  $("#dynamicToolType").addEventListener("change", syncStatusConfiguration);
  $("#dynamicToolUseStatus").addEventListener("change", syncStatusConfiguration);
  $("#dynamicToolCards").addEventListener("change", () => {
    collectBuilder();
    renderMetricOptions();
  });
  $("#dynamicToolMainHub").addEventListener("change", (event) => {
    if (event.target.checked && !(editing.configuracao?.main_hub?.status_codes || []).length) {
      editing.configuracao.main_hub = {
        ...(editing.configuracao?.main_hub || {}),
        enabled: true,
        status_codes: (editing.statuses || []).filter((status) => !status.final).map((status) => status.codigo),
        field_keys: (editing.configuracao?.main_hub?.field_keys || []).length
          ? editing.configuracao.main_hub.field_keys
          : (editing.campos || []).filter((field) => field.visivel_gerencial !== false).slice(0, 4).map((field) => field.chave),
      };
    }
    renderMainHubOptions();
    markBuilderDirty();
  });
  $("#dynamicToolColor").addEventListener("input", (event) => {
    dialog.querySelector(".dynamic-builder-editor-icon")?.style.setProperty("--tool-color", event.target.value);
  });
  dialog.querySelector("form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitButton = event.submitter || dialog.querySelector('button[type="submit"]');
    showBuilderSaveError();
    try {
      finalizeStatusCodes();
      collectBuilder();
      validateBuilderDraft();
      if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = "Salvando...";
      }
      await api("/api/config/ferramentas-negociais", { method: "POST", body: JSON.stringify(editing) });
      builderDirty = false;
      dialog.close();
      toast("Rascunho salvo. Publique a versao para aplicar na ferramenta.");
      await Promise.all([loadDynamicToolsAdmin(), loadHighlightedToolNavigation()]);
    } catch (error) {
      showBuilderSaveError(error.message || "Nao foi possivel salvar o rascunho.");
      toast(error.message);
    } finally {
      if (submitButton && dialog.open) {
        submitButton.disabled = false;
        submitButton.textContent = "Salvar rascunho";
      }
    }
  });
  if (readonly) {
    dialog.querySelectorAll("input,select,textarea,[data-remove-field],[data-remove-status],[data-remove-transition],[data-remove-screen],[data-move-field],[data-move-status],[data-move-screen],[data-flow-template],[data-screen-preset],#addDynamicFieldBtn,#addDynamicStatusBtn,#addDynamicTransitionBtn,#addDynamicScreenBtn").forEach((control) => control.disabled = true);
  }
  dialog.showModal();
}

function syncStatusConfiguration() {
  const type = $("#dynamicToolType")?.value || editing?.tipo || "CADASTRO";
  const statusConfig = $("#dynamicToolStatusConfig");
  const useStatus = $("#dynamicToolUseStatus");
  const negotiatorStatus = $("#dynamicToolNegotiatorStatus");
  const changeStatus = $("#dynamicToolChangeStatus");
  const statusesSection = $("#dynamicToolStatusesSection");
  const transitionsSection = $("#dynamicToolTransitionsSection");
  if (!statusConfig || !useStatus || !negotiatorStatus || !changeStatus) return;

  const isRequest = type === "SOLICITACAO";
  statusConfig.classList.remove("hidden");
  useStatus.disabled = isRequest;
  if (isRequest) useStatus.checked = true;
  negotiatorStatus.disabled = !useStatus.checked || isRequest;
  if (!useStatus.checked || isRequest) negotiatorStatus.checked = false;
  changeStatus.disabled = !useStatus.checked;
  if (!useStatus.checked) changeStatus.checked = false;
  statusesSection?.classList.toggle("hidden", !useStatus.checked);
  transitionsSection?.classList.toggle("hidden", !useStatus.checked);
  renderFlowPreview();
  renderMetricOptions();
}

export async function openToolBuilder(toolId = null) {
  try {
    builderTab = "geral";
    permissionTab = "wallets";
    previewAudience = "negocial";
    previewScreenId = "";
    builderScreenIndex = 0;
    builderDirty = false;
    if (toolId) {
      editing = (await api(`/api/config/ferramentas-negociais/${toolId}`)).item;
    } else {
      editing = defaultDefinition();
    }
    renderBuilderDialog(editing.versao_status && editing.versao_status !== "RASCUNHO");
  } catch (error) {
    toast(error.message);
  }
}

async function publishTool(toolId) {
  if (!window.confirm("Publicar esta versao para os negociadores autorizados?")) return;
  try {
    await api(`/api/config/ferramentas-negociais/${toolId}/publicar`, { method: "POST", body: "{}" });
    toast("Ferramenta publicada.");
    await Promise.all([loadDynamicToolsAdmin(), loadHighlightedToolNavigation()]);
  } catch (error) {
    toast(error.message);
  }
}

async function createVersion(toolId) {
  try {
    await api(`/api/config/ferramentas-negociais/${toolId}/nova-versao`, { method: "POST", body: "{}" });
    await loadDynamicToolsAdmin();
    await openToolBuilder(toolId);
  } catch (error) {
    toast(error.message);
  }
}

function displayValue(value) {
  if (value === null || value === undefined || value === "") return "Vazio";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? "Sim" : "Nao";
  return String(value);
}

function localDateTime(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("pt-BR");
}

function dynamicRecordFieldValue(field, value) {
  if (value === null || value === undefined || value === "") return "Nao informado";
  const type = String(field?.tipo || "").toLowerCase();
  if (type === "data" || type === "date") {
    const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (match) return `${match[3]}/${match[2]}/${match[1]}`;
  }
  if (["moeda", "currency", "valor"].includes(type)) {
    let numeric = value;
    if (typeof value === "string") {
      const cleaned = value.replace(/[^\d,.-]/g, "");
      numeric = cleaned.includes(",")
        ? Number(cleaned.replace(/\./g, "").replace(",", "."))
        : Number(cleaned);
    }
    if (Number.isFinite(Number(numeric))) {
      return Number(numeric).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
    }
  }
  return displayValue(value);
}

function dynamicRecordFieldClass(field, value) {
  const type = String(field?.tipo || "").toLowerCase();
  const text = String(value ?? "");
  const isEmpty = value === null || value === undefined || value === "";
  const isWide = ["textarea", "texto_longo", "arquivo"].includes(type) || text.length > 90;
  return `${isEmpty ? "is-empty" : ""} ${isWide ? "is-wide" : ""}`.trim();
}

function fileSize(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
}

function recordStatusDefinition(code) {
  return (recordsContext?.definition?.statuses || []).find((item) => String(item.codigo) === String(code)) || null;
}

function recordStatusBadge(code) {
  return recordStatusBadgeFor(recordsContext?.definition, code);
}

function recordStatusBadgeFor(toolDefinition, code) {
  const definition = (toolDefinition?.statuses || []).find((item) => String(item.codigo) === String(code));
  const color = /^#[0-9a-f]{6}$/i.test(String(definition?.cor || "")) ? definition.cor : "#64748b";
  return `<span class="dynamic-record-status" style="--record-status-color:${escapeAttr(color)}">${escapeHtml(definition?.nome || code || "Sem status")}</span>`;
}

function visibleRecordFields() {
  const definition = recordsContext?.definition || {};
  const titleKey = String(definition.configuracao?.campo_titulo || "").toUpperCase();
  const metadataKeys = new Set(["NEGOCIADOR", "OPERADOR", "USUARIO", "CARTEIRA", titleKey]);
  return (definition.campos || [])
    .filter((field) => field.visivel_gerencial
      && !["usuario", "carteira"].includes(String(field.tipo || "").toLowerCase())
      && !metadataKeys.has(String(field.chave || "").toUpperCase()))
    .slice(0, 7);
}

function recordTitleLabel() {
  const definition = recordsContext?.definition || {};
  const titleKey = String(definition.configuracao?.campo_titulo || "").toUpperCase();
  return definition.campos?.find((field) => String(field.chave || "").toUpperCase() === titleKey)?.nome || "Registro";
}

function recordFilters() {
  const dialog = $("#dynamicToolRecordsDialog");
  return {
    status: dialog?.querySelector("[data-record-filter-status]")?.value || "",
    carteira: dialog?.querySelector("[data-record-filter-wallet]")?.value || "",
    usuario: dialog?.querySelector("[data-record-filter-user]")?.value || "",
    q: dialog?.querySelector("[data-record-filter-query]")?.value.trim() || "",
  };
}

function recordQueryString(filters = recordFilters()) {
  const query = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) query.set(key, value);
  });
  return query.toString();
}

function renderRecordTable() {
  const target = $("#dynamicToolRecordsTable");
  if (!target || !recordsContext) return;
  const fields = visibleRecordFields();
  const useStatus = recordsContext.definition.tipo !== "CADASTRO"
    || recordsContext.definition.configuracao?.usar_status !== false;
  if (!recordsContext.items.length) {
    target.innerHTML = `
      <div class="dynamic-records-empty">
        <span aria-hidden="true">&#128269;</span>
        <strong>Nenhum registro encontrado</strong>
        <small>Ajuste os filtros ou limpe a pesquisa para consultar outros registros.</small>
      </div>`;
    return;
  }
  target.innerHTML = `
    <table>
      <thead><tr>
        ${useStatus ? "<th>Status</th>" : ""}<th>${escapeHtml(recordTitleLabel())}</th>
        ${fields.map((field) => `<th>${escapeHtml(field.nome)}</th>`).join("")}
        <th>Negociador</th><th>Carteira</th><th>Atualizado</th><th aria-label="Acoes"></th>
      </tr></thead>
      <tbody>${recordsContext.items.map((item) => `
        <tr class="${String(recordsContext.selectedId) === String(item.id) ? "is-selected" : ""}" data-tool-record-id="${item.id}" tabindex="0">
          ${useStatus ? `<td>${recordStatusBadge(item.status)}</td>` : ""}
          <td class="dynamic-record-title-cell"><strong>${escapeHtml(item.titulo || `Registro ${item.id}`)}</strong><small>#${item.id}</small></td>
          ${fields.map((field) => `<td>${escapeHtml(displayValue(item.payload?.[field.chave]))}</td>`).join("")}
          <td>${escapeHtml(item.negociador || "-")}</td>
          <td>${escapeHtml(item.carteira || "-")}</td>
          <td>${escapeHtml(localDateTime(item.updated_at))}</td>
          <td><button class="dynamic-record-open" type="button" aria-label="Abrir detalhes" title="Abrir detalhes">&#8250;</button></td>
        </tr>
      `).join("")}</tbody>
    </table>
  `;
  target.querySelectorAll("[data-tool-record-id]").forEach((row) => {
    const open = () => openToolRecordDetails(recordsContext.toolId, Number(row.dataset.toolRecordId));
    row.addEventListener("click", open);
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") open();
    });
  });
}

function renderRecordsSummary() {
  if (!recordsContext) return;
  const target = $("#dynamicToolRecordsSummary");
  if (!target) return;
  const useStatus = recordsContext.definition.tipo !== "CADASTRO"
    || recordsContext.definition.configuracao?.usar_status !== false;
  const finalStatuses = new Set((recordsContext.definition.statuses || []).filter((status) => status.final).map((status) => status.codigo));
  const counts = recordsContext.status_counts || {};
  const totalCount = Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0) || recordsContext.total || 0;
  const finalCount = [...finalStatuses].reduce((sum, code) => sum + Number(counts[code] || 0), 0);
  const activeCount = totalCount - finalCount;
  const today = new Date().toDateString();
  const updatedToday = recordsContext.items.filter((item) => {
    const value = new Date(item.updated_at);
    return !Number.isNaN(value.getTime()) && value.toDateString() === today;
  }).length;
  const metrics = [
    ["Registros", totalCount, "Resultado atual"],
    ...(useStatus ? [["Em andamento", activeCount, "Status nao final"], ["Finalizados", finalCount, "Status final"]] : []),
    ["Atualizados hoje", updatedToday, "Movimentacoes recentes"],
  ];
  target.innerHTML = metrics.map(([label, value, note]) => `<article><span>${escapeHtml(label)}</span><strong>${Number(value || 0).toLocaleString("pt-BR")}</strong><small>${escapeHtml(note)}</small></article>`).join("");
}

function renderRecordStageTabs() {
  const target = $("#dynamicToolRecordStages");
  if (!target || !recordsContext) return;
  const definition = recordsContext.definition;
  const useStatus = definition.tipo !== "CADASTRO" || definition.configuracao?.usar_status !== false;
  if (!useStatus) {
    target.classList.add("hidden");
    target.innerHTML = "";
    return;
  }
  target.classList.remove("hidden");
  const current = recordFilters().status;
  const counts = recordsContext.status_counts || {};
  const total = Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0);
  target.innerHTML = `
    <button type="button" class="${!current ? "active" : ""}" data-record-stage="">
      <span>Todos</span><strong>${total.toLocaleString("pt-BR")}</strong>
    </button>
    ${(definition.statuses || []).map((status) => `
      <button type="button" class="${current === status.codigo ? "active" : ""}" data-record-stage="${escapeAttr(status.codigo)}" style="--stage-color:${escapeAttr(status.cor || "#64748b")}">
        <i></i><span>${escapeHtml(status.nome)}</span><strong>${Number(counts[status.codigo] || 0).toLocaleString("pt-BR")}</strong>
      </button>
    `).join("")}
  `;
  target.querySelectorAll("[data-record-stage]").forEach((button) => {
    button.addEventListener("click", () => {
      const select = $("#dynamicToolRecordsDialog")?.querySelector("[data-record-filter-status]");
      if (select) select.value = button.dataset.recordStage || "";
      loadToolRecords(recordsContext.toolId, recordFilters());
    });
  });
}

async function loadToolRecords(toolId, filters = {}) {
  const sequence = ++recordsLoadSequence;
  const target = $("#dynamicToolRecordsTable");
  if (target) target.innerHTML = '<div class="dynamic-builder-empty">Carregando registros...</div>';
  const query = recordQueryString(filters);
  const selectedId = Number(recordsContext?.toolId) === Number(toolId) ? recordsContext?.selectedId : null;
  const payload = await api(`/api/config/ferramentas-negociais/${toolId}/registros${query ? `?${query}` : ""}`);
  if (sequence !== recordsLoadSequence || !document.querySelector("#dynamicToolRecordsDialog")) return;
  recordsContext = {
    ...payload,
    toolId,
    selectedId,
  };
  if (recordsContext.selectedId && !recordsContext.items.some((item) => Number(item.id) === Number(recordsContext.selectedId))) {
    recordsContext.selectedId = null;
    $("#dynamicToolRecordDetails")?.classList.add("hidden");
  }
  const total = $("#dynamicToolRecordsTotal");
  if (total) total.textContent = `${Number(recordsContext.filtered_total ?? recordsContext.items.length).toLocaleString("pt-BR")} registro(s)`;
  renderRecordsSummary();
  renderRecordStageTabs();
  renderRecordTable();
}

export async function openToolRecords(toolId) {
  document.querySelector("#dynamicToolRecordsDialog")?.remove();
  const tool = tools.find((item) => Number(item.id) === Number(toolId));
  const toolColor = /^#[0-9a-f]{6}$/i.test(String(tool?.cor || "")) ? tool.cor : "#2563eb";
  const dialog = document.createElement("dialog");
  dialog.id = "dynamicToolRecordsDialog";
  dialog.className = "dynamic-tool-records-dialog is-refined";
  dialog.innerHTML = `
    <div class="modal-card">
      <div class="modal-header dynamic-records-header">
        <div class="dynamic-records-identity">
          <span class="dynamic-records-icon" style="--tool-color:${escapeAttr(toolColor)}">${escapeHtml(tool?.icone || "F")}</span>
          <div><p class="eyebrow">Gerenciar registros</p><h2>${escapeHtml(tool?.nome || "Registros")}</h2><small>${escapeHtml(tool?.descricao || "Consulte, filtre e acompanhe os registros desta ferramenta.")}</small></div>
        </div>
        <div class="dynamic-records-header-actions">
          <button class="secondary-btn" type="button" data-record-report>Gerar relat&oacute;rio</button>
          <button class="icon-btn" type="button" data-close aria-label="Fechar" title="Fechar">&times;</button>
        </div>
      </div>
      <div id="dynamicToolRecordsSummary" class="dynamic-records-summary"></div>
      <nav id="dynamicToolRecordStages" class="dynamic-records-stages hidden" aria-label="Etapas do fluxo"></nav>
      <div class="dynamic-records-toolbar">
        <label class="dynamic-records-search"><span aria-hidden="true">&#128269;</span><input data-record-filter-query placeholder="Buscar em todos os campos"></label>
        <select class="hidden" data-record-filter-status aria-label="Etapa"><option value="">Todas as etapas</option></select>
        <select data-record-filter-wallet aria-label="Carteira"><option value="">Todas as carteiras</option>${wallets.map((item) => `<option>${escapeHtml(item)}</option>`).join("")}</select>
        <select data-record-filter-user aria-label="Negociador"><option value="">Todos os negociadores</option>${negotiators.map((item) => `<option value="${escapeHtml(item.username)}">${escapeHtml(item.username)}</option>`).join("")}</select>
        <button class="secondary-btn" type="button" data-record-filter title="Atualizar resultados">Atualizar</button>
        <button class="secondary-btn" type="button" data-record-clear>Limpar</button>
        <strong id="dynamicToolRecordsTotal">0 registro(s)</strong>
      </div>
      <div class="dynamic-records-content">
        <div id="dynamicToolRecordsTable" class="dynamic-records-table"></div>
        <aside id="dynamicToolRecordDetails" class="dynamic-record-details hidden"></aside>
      </div>
    </div>
  `;
  document.body.append(dialog);
  dialog.querySelector("[data-close]").addEventListener("click", () => dialog.close());
  dialog.querySelector("[data-record-filter]").addEventListener("click", () => loadToolRecords(toolId, recordFilters()));
  let searchTimer = null;
  dialog.querySelector("[data-record-filter-query]").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadToolRecords(toolId, recordFilters()), 350);
  });
  dialog.querySelectorAll("[data-record-filter-status], [data-record-filter-wallet], [data-record-filter-user]").forEach((select) => {
    select.addEventListener("change", () => loadToolRecords(toolId, recordFilters()));
  });
  dialog.querySelector("[data-record-clear]").addEventListener("click", () => {
    dialog.querySelectorAll("[data-record-filter-query], [data-record-filter-status], [data-record-filter-wallet], [data-record-filter-user]").forEach((input) => { input.value = ""; });
    loadToolRecords(toolId, {});
  });
  dialog.querySelector("[data-record-report]").addEventListener("click", () => downloadToolRecordsReport(toolId));
  dialog.addEventListener("close", () => {
    clearTimeout(searchTimer);
    recordsLoadSequence += 1;
    recordsContext = null;
    dialog.remove();
  }, { once: true });
  dialog.showModal();
  await loadToolRecords(toolId);
  const statusSelect = dialog.querySelector("[data-record-filter-status]");
  const useStatus = recordsContext.definition.tipo !== "CADASTRO"
    || recordsContext.definition.configuracao?.usar_status !== false;
  statusSelect.classList.toggle("hidden", !useStatus);
  if (useStatus) {
    statusSelect.innerHTML += recordsContext.definition.statuses
      .map((item) => `<option value="${escapeHtml(item.codigo)}">${escapeHtml(item.nome)}</option>`).join("");
  }
}

async function openToolRecordDetails(toolId, recordId, options = {}) {
  const payload = await api(`/api/config/ferramentas-negociais/${toolId}/registros/${recordId}`);
  const { definition, item } = payload;
  const target = options.target || $("#dynamicToolRecordDetails");
  if (!target) return;
  if (!options.standalone && recordsContext) {
    recordsContext.selectedId = recordId;
    renderRecordTable();
  }
  const titleKey = String(definition.configuracao?.campo_titulo || "").toUpperCase();
  const fields = definition.campos.filter((field) => field.visivel_gerencial
    && String(field.tipo || "").toLowerCase() !== "arquivo"
    && !["usuario", "carteira"].includes(String(field.tipo || "").toLowerCase())
    && !["NEGOCIADOR", "OPERADOR", "USUARIO", "CARTEIRA", titleKey].includes(String(field.chave || "").toUpperCase()));
  const useStatus = definition.tipo !== "CADASTRO" || definition.configuracao?.usar_status !== false;
  const transitions = definition.transicoes.filter(
    (transition) => transition.origem_codigo === item.status && transition.permite_gerencial,
  );
  const populatedFields = fields.filter((field) => item.payload?.[field.chave] !== null
    && item.payload?.[field.chave] !== undefined
    && item.payload?.[field.chave] !== "");
  const emptyFields = fields.filter((field) => !populatedFields.includes(field));
  const valueFields = populatedFields.filter((field) => ["moeda", "currency", "valor"].includes(String(field.tipo || "").toLowerCase()));
  const detailFields = populatedFields.filter((field) => !valueFields.includes(field));
  const renderFields = (items) => items.map((field) => `<div class="${dynamicRecordFieldClass(field, item.payload?.[field.chave])}"><span>${escapeHtml(field.nome)}</span><strong>${escapeHtml(dynamicRecordFieldValue(field, item.payload?.[field.chave]))}</strong></div>`).join("");
  target.classList.remove("hidden");
  target.innerHTML = `
    <div class="dynamic-record-details-head">
      <div>${useStatus ? recordStatusBadgeFor(definition, item.status) : ""}<h3>${escapeHtml(item.titulo || `Registro ${item.id}`)}</h3><small>Registro #${item.id}</small></div>
      <button class="icon-btn" type="button" data-record-close aria-label="Fechar" title="Fechar">&times;</button>
    </div>
    <div class="dynamic-record-body">
    <dl class="dynamic-record-meta">
      <div><dt>Negociador</dt><dd>${escapeHtml(item.negociador || "-")}</dd></div>
      <div><dt>Carteira</dt><dd>${escapeHtml(item.carteira || "-")}</dd></div>
      <div><dt>Criado</dt><dd>${escapeHtml(localDateTime(item.created_at))}</dd></div>
      <div><dt>Atualizado</dt><dd>${escapeHtml(localDateTime(item.updated_at))}</dd></div>
    </dl>
    ${detailFields.length ? `<section class="dynamic-record-section dynamic-record-data-section"><h4>Resumo</h4><div class="dynamic-record-fields">${renderFields(detailFields)}</div></section>` : ""}
    ${valueFields.length ? `<section class="dynamic-record-section dynamic-record-values-section"><h4>Valores</h4><div class="dynamic-record-fields">${renderFields(valueFields)}</div></section>` : ""}
    ${emptyFields.length ? `<details class="dynamic-record-empty-fields"><summary>Outros dados <span>${emptyFields.length} nao informado(s)</span></summary><div class="dynamic-record-fields">${renderFields(emptyFields)}</div></details>` : ""}
    ${transitions.length ? `
      <section class="dynamic-record-section dynamic-record-decision">
        <h4>Pr&oacute;xima a&ccedil;&atilde;o</h4>
        <textarea data-transition-reason placeholder="Informe a justificativa quando ela for obrigat&oacute;ria"></textarea>
      </section>
    ` : ""}
    <section class="dynamic-record-section dynamic-record-activity">
      <div class="dynamic-record-activity-tabs" role="tablist" aria-label="Atividade do registro">
        <button class="active" type="button" role="tab" aria-selected="true" data-record-tab="comments">Coment&aacute;rios <span>${(item.comentarios || []).length}</span></button>
        <button type="button" role="tab" aria-selected="false" data-record-tab="attachments">Anexos <span>${(item.anexos || []).length}</span></button>
        <button type="button" role="tab" aria-selected="false" data-record-tab="history">Hist&oacute;rico <span>${(item.eventos || []).length}</span></button>
      </div>
      <div data-record-panel="comments">
      <div class="dynamic-record-comments">
        ${(item.comentarios || []).map((comment) => `<p><strong>${escapeHtml(comment.usuario || "Sistema")}</strong><span>${escapeHtml(localDateTime(comment.created_at))}</span>${escapeHtml(comment.texto)}</p>`).join("") || "<p>Nenhum coment&aacute;rio.</p>"}
      </div>
      <div class="dynamic-record-comment-form">
        <textarea data-record-comment placeholder="Adicionar coment&aacute;rio"></textarea>
        <button class="secondary-btn" type="button" data-record-comment-save>Salvar coment&aacute;rio</button>
      </div>
      </div>
      <div class="hidden" data-record-panel="attachments">
        <div class="dynamic-record-attachments">
          ${(item.anexos || []).map((attachment) => `
            <article>
              <span class="dynamic-record-attachment-icon" aria-hidden="true">${escapeHtml(String(attachment.nome || "A").split(".").pop().slice(0, 4).toUpperCase())}</span>
              <div><strong>${escapeHtml(attachment.nome)}</strong><small>${escapeHtml(attachment.usuario || "Usuario")} &middot; ${escapeHtml(localDateTime(attachment.created_at))} &middot; ${fileSize(attachment.tamanho)}</small></div>
              <button
                class="secondary-btn"
                type="button"
                data-record-attachment-download
                data-attachment-url="/api/config/ferramentas-negociais/${toolId}/registros/${recordId}/anexos/${attachment.id}"
                data-attachment-name="${escapeAttr(attachment.nome || "anexo")}"
              >Baixar</button>
            </article>
          `).join("") || "<p>Nenhum anexo enviado.</p>"}
        </div>
      </div>
      <div class="hidden" data-record-panel="history">
      <div class="dynamic-record-history">
        ${(item.eventos || []).slice().reverse().map((event) => `
          <p><strong>${escapeHtml(event.tipo)}</strong><span>${escapeHtml(event.usuario || "Sistema")} &middot; ${escapeHtml(localDateTime(event.created_at))}</span>${escapeHtml(event.justificativa || `${event.status_anterior || "-"} -> ${event.status_novo || "-"}`)}</p>
        `).join("") || "<p>Nenhum evento.</p>"}
      </div>
      </div>
    </section>
    </div>
    <footer class="dynamic-record-footer">
      <button class="secondary-btn" type="button" data-record-close>Fechar</button>
      <div class="dynamic-record-actions">
        ${transitions.map((transition) => `
          <button class="dynamic-transition-action" type="button" data-record-transition="${escapeHtml(transition.destino_codigo)}" data-reason-required="${transition.exige_justificativa ? "1" : "0"}" style="--transition-color:${escapeAttr(definition.statuses.find((status) => status.codigo === transition.destino_codigo)?.cor || "#2563eb")}">
            ${escapeHtml(transition.nome)}
          </button>
        `).join("")}
      </div>
    </footer>
  `;
  target.querySelectorAll("[data-record-close]").forEach((button) => {
    button.addEventListener("click", () => {
      if (options.dialog) options.dialog.close();
      else target.classList.add("hidden");
      if (!options.standalone && recordsContext) {
        recordsContext.selectedId = null;
        renderRecordTable();
      }
    });
  });
  target.querySelectorAll("[data-record-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      const selectedTab = button.dataset.recordTab;
      target.querySelectorAll("[data-record-tab]").forEach((tab) => {
        const active = tab === button;
        tab.classList.toggle("active", active);
        tab.setAttribute("aria-selected", String(active));
      });
      target.querySelectorAll("[data-record-panel]").forEach((panel) => {
        panel.classList.toggle("hidden", panel.dataset.recordPanel !== selectedTab);
      });
    });
  });
  target.querySelectorAll("[data-record-transition]").forEach((button) => {
    button.addEventListener("click", async () => {
      const reason = target.querySelector("[data-transition-reason]")?.value.trim() || "";
      if (button.dataset.reasonRequired === "1" && !reason) {
        toast("Informe a justificativa.");
        return;
      }
      try {
        await api(`/api/config/ferramentas-negociais/${toolId}/registros/${recordId}/transicao`, {
          method: "POST",
          body: JSON.stringify({ status: button.dataset.recordTransition, justificativa: reason }),
        });
        toast("Status atualizado.");
        if (options.standalone) await options.onChanged?.();
        else await loadToolRecords(toolId, recordFilters());
        await openToolRecordDetails(toolId, recordId, options);
      } catch (error) {
        toast(error.message);
      }
    });
  });
  target.querySelectorAll("[data-record-attachment-download]").forEach((button) => {
    button.addEventListener("click", () => downloadToolAttachment(button));
  });
  target.querySelector("[data-record-comment-save]").addEventListener("click", async () => {
    const text = target.querySelector("[data-record-comment]").value.trim();
    if (!text) return toast("Informe o comentario.");
    try {
      await api(`/api/config/ferramentas-negociais/${toolId}/registros/${recordId}/comentarios`, {
        method: "POST",
        body: JSON.stringify({ texto: text }),
      });
      toast("Comentario salvo.");
      await openToolRecordDetails(toolId, recordId, options);
    } catch (error) {
      toast(error.message);
    }
  });
}

async function downloadToolAttachment(button) {
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Baixando...";
  try {
    const response = await fetch(button.dataset.attachmentUrl, {
      cache: "no-store",
      credentials: "same-origin",
    });
    if (response.status === 401) {
      location.href = "/login.html";
      return;
    }
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || `Nao foi possivel baixar o anexo (erro ${response.status}).`);
    }
    const blob = await response.blob();
    if (!blob.size) throw new Error("O arquivo recebido esta vazio.");
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = button.dataset.attachmentName || "anexo";
    link.hidden = true;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    toast("Download iniciado.");
  } catch (error) {
    toast(error.message || "Nao foi possivel baixar o anexo.");
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

export async function openToolRecordDirect(toolId, recordId, options = {}) {
  document.querySelector("#dynamicToolRecordDirectDialog")?.remove();
  const dialog = document.createElement("dialog");
  dialog.id = "dynamicToolRecordDirectDialog";
  dialog.className = "dynamic-tool-record-direct-dialog";
  dialog.innerHTML = '<div class="modal-card"><section class="dynamic-record-direct-content" data-direct-record-details><div class="dynamic-builder-empty">Carregando registro...</div></section></div>';
  document.body.append(dialog);
  dialog.addEventListener("close", () => dialog.remove(), { once: true });
  dialog.showModal();
  try {
    await openToolRecordDetails(toolId, recordId, {
      standalone: true,
      dialog,
      target: dialog.querySelector("[data-direct-record-details]"),
      onChanged: options.onChanged,
    });
  } catch (error) {
    dialog.close();
    toast(error.message || "Nao foi possivel abrir o registro.");
  }
}

async function downloadToolRecordsReport(toolId) {
  try {
    const query = recordQueryString();
    const response = await fetch(`/api/config/ferramentas-negociais/${toolId}/relatorio.xlsx${query ? `?${query}` : ""}`, {
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || `Erro ${response.status} ao gerar relatorio.`);
    }
    const blob = await response.blob();
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = "";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(href), 30000);
    toast("Relatorio gerado.");
  } catch (error) {
    toast(error.message);
  }
}
