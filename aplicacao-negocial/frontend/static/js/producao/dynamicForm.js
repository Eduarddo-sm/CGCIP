import { statusLabels } from "./constants.js?v=20260714-module-contract-1";
import {
  dynamicAgreementTypeKeys,
  dynamicColumnMatches,
  dynamicDigitsOnlyKeys,
  dynamicEntryValueKeys,
  isAgreementAtSight,
  normalizedDynamicKey,
} from "./dynamicSchema.js?v=20260714-schema-only-2";
import { escapeHtml } from "./formatters.js?v=20260714-module-contract-1";
import { normalizeStatusValue } from "./options.js?v=20260714-module-contract-1";


export function createDynamicFormController({ state, elements, isDynamicCarteira }) {
  let outsideClickBound = false;
  function normalizeMultiselectValue(value) {
    if (Array.isArray(value)) return [...new Set(value.map((item) => String(item || "").trim()).filter(Boolean))];
    const text = String(value || "").trim();
    if (!text) return [];
    if (text.startsWith("[")) {
      try {
        const parsed = JSON.parse(text);
        if (Array.isArray(parsed)) return normalizeMultiselectValue(parsed);
      } catch (_error) {
        // Valores legados continuam sendo aceitos como texto separado.
      }
    }
    return [...new Set(text.split(/[;,]/).map((item) => item.trim()).filter(Boolean))];
  }

  function dynamicColumns() {
    return (state.schema?.columns || []).filter((column) => column.visivel !== false);
  }

  function normalizeDynamicInput(input) {
    if (!input || input.dataset?.dynamicMultiselect !== undefined) return;
    const key = normalizedDynamicKey(input?.dataset?.dynamicField);
    if (dynamicDigitsOnlyKeys.has(key)) {
      const digits = String(input.value || "").replace(/\D/g, "");
      input.value = input.maxLength > 0 ? digits.slice(0, input.maxLength) : digits;
    }
  }

  function dynamicFieldInput(column) {
    return column ? document.querySelector(`[data-dynamic-field="${column.chave}"]`) : null;
  }

  function dynamicAgreementTypeInput() {
    return dynamicFieldInput(dynamicColumns().find((column) => dynamicColumnMatches(column, dynamicAgreementTypeKeys)));
  }

  function dynamicAgreementIsAtSight() {
    return isDynamicCarteira() && isAgreementAtSight(dynamicAgreementTypeInput()?.value);
  }

  function applyDynamicAgreementTypeRules() {
    if (!isDynamicCarteira()) return false;
    const isAtSight = dynamicAgreementIsAtSight();
    dynamicColumns()
      .filter((column) => dynamicColumnMatches(column, dynamicEntryValueKeys))
      .forEach((column) => {
        const input = dynamicFieldInput(column);
        if (!input) return;
        input.closest("label")?.classList.toggle("hidden", isAtSight);
        input.required = Boolean(column.obrigatoria) && !isAtSight;
        if (isAtSight) {
          if (input.dataset.entryBeforeAtSight === undefined) {
            input.dataset.entryBeforeAtSight = input.value === "0" ? "" : input.value;
          }
          input.value = "0";
        } else if (input.dataset.entryBeforeAtSight !== undefined) {
          input.value = input.dataset.entryBeforeAtSight;
          delete input.dataset.entryBeforeAtSight;
        }
      });
    return isAtSight;
  }

  function isDynamicOperatorColumn(column) {
    return ["NEGOCIADOR", "OPERADOR"].includes(String(column?.chave || "").toUpperCase());
  }

  function dynamicGridColumns() {
    return dynamicColumns().filter((column) => !isDynamicOperatorColumn(column));
  }

  function dynamicIdentifierColumn() {
    return dynamicColumns().find((column) => column.identificador) || dynamicColumns()[0] || null;
  }

  function dynamicInputId(column) {
    return `dynamicField_${column.chave}`;
  }

  function isDynamicJustificativaColumn(column) {
    return String(column?.chave || "").toUpperCase() === "JUSTIFICATIVA";
  }

  function isDynamicHonorariosColumn(column) {
    const key = String(column?.chave || "").toUpperCase();
    const name = String(column?.nome || "").toUpperCase();
    return !key.includes("RECEBID") && !name.includes("RECEBID")
      && (["HONORARIOS", "HONOR_RIOS", "H_O", "HO", "VALOR_HO", "H_O_VALOR"].includes(key) || name.includes("HONOR"));
  }

  function hasAutomaticHonorarios() {
    const rules = state.schema?.regras_ho || {};
    return Boolean(rules.usa_percentual_ho && rules.calculo_automatico_ho);
  }

  function dynamicAutomaticValue(column) {
    if (!column?.automatico) return null;
    const autoTipo = String(column.auto_tipo || "").toLowerCase();
    if (autoTipo === "today") return new Date().toISOString().slice(0, 10);
    if (autoTipo === "usuario") return state.user?.username || "";
    if (autoTipo === "carteira") return state.carteira || "";
    return null;
  }

  function dynamicFieldValue(column, item = null) {
    if (!item) {
      const automaticValue = dynamicAutomaticValue(column);
      return automaticValue !== null ? automaticValue : "";
    }
    const fields = item.campos || {};
    const value = fields[column.chave] ?? item[column.chave?.toLowerCase?.()] ?? "";
    if ((value == null || value === "") && column.automatico) {
      const automaticValue = dynamicAutomaticValue(column);
      if (automaticValue !== null) return automaticValue;
    }
    if (column.tipo === "multiselect") return normalizeMultiselectValue(value);
    if (value == null) return "";
    const text = String(value);
    return column.tipo === "data" ? text.slice(0, 10) : text;
  }

  function dynamicOptionText(option) {
    if (option && typeof option === "object") {
      return String(option.value ?? option.label ?? option.nome ?? option.name ?? option.text ?? "").trim();
    }
    return String(option ?? "").trim();
  }

  function dynamicSelectOption(column, option) {
    const rawValue = dynamicOptionText(option);
    const isStatus = String(column.chave || "").toUpperCase() === "STATUS";
    const isAgreementType = dynamicColumnMatches(column, dynamicAgreementTypeKeys);
    const value = isStatus
      ? normalizeStatusValue(rawValue, rawValue)
      : isAgreementType
        ? (isAgreementAtSight(rawValue) ? "A_VISTA" : normalizedDynamicKey(rawValue) === "PARCELADO" ? "PARCELADO" : rawValue)
        : rawValue;
    const label = isStatus
      ? (statusLabels[value] || rawValue || value)
      : isAgreementType
        ? ({ A_VISTA: "A vista", PARCELADO: "Parcelado" }[value] || rawValue)
        : rawValue;
    return { value, label };
  }

  function multiselectValues(field) {
    if (!field) return [];
    return [...field.querySelectorAll("[data-multiselect-option]:checked")].map((input) => input.value);
  }

  function updateMultiselectSummary(field) {
    const summary = field?.querySelector("[data-multiselect-summary]");
    if (!summary) return;
    const selected = multiselectValues(field);
    summary.textContent = selected.length === 0
      ? "Selecione"
      : selected.length === 1
        ? selected[0]
        : `${selected.length} selecionados`;
    field.classList.toggle("has-value", selected.length > 0);
  }

  function closeMultiselects(except = null) {
    elements.form?.querySelectorAll("[data-dynamic-multiselect].open").forEach((field) => {
      if (field === except) return;
      field.classList.remove("open");
      field.querySelector("[data-multiselect-trigger]")?.setAttribute("aria-expanded", "false");
    });
  }

  function dynamicFieldFormValue(field) {
    return field?.dataset?.dynamicMultiselect !== undefined ? multiselectValues(field) : field?.value ?? "";
  }

  function dynamicFieldIsEmpty(field) {
    const value = dynamicFieldFormValue(field);
    return Array.isArray(value) ? value.length === 0 : !String(value || "").trim();
  }

  function focusDynamicField(field) {
    (field?.querySelector?.("[data-multiselect-trigger]") || field)?.focus?.();
  }

  function bindDynamicFormEvents() {
    const form = elements.form;
    if (!form || form.dataset.dynamicMultiselectBound === "true") return;
    form.dataset.dynamicMultiselectBound = "true";
    form.addEventListener("click", (event) => {
      const trigger = event.target.closest?.("[data-multiselect-trigger]");
      if (trigger) {
        const field = trigger.closest("[data-dynamic-multiselect]");
        const willOpen = !field.classList.contains("open");
        closeMultiselects(willOpen ? field : null);
        field.classList.toggle("open", willOpen);
        trigger.setAttribute("aria-expanded", String(willOpen));
        return;
      }
      const clear = event.target.closest?.("[data-multiselect-clear]");
      if (clear) {
        const field = clear.closest("[data-dynamic-multiselect]");
        field.querySelectorAll("[data-multiselect-option]").forEach((input) => { input.checked = false; });
        updateMultiselectSummary(field);
        return;
      }
      const done = event.target.closest?.("[data-multiselect-done]");
      if (done) closeMultiselects();
    });
    form.addEventListener("change", (event) => {
      const field = event.target.closest?.("[data-dynamic-multiselect]");
      if (field) updateMultiselectSummary(field);
    });
    if (!outsideClickBound) {
      outsideClickBound = true;
      document.addEventListener("click", (event) => {
        if (!event.target.closest?.("[data-dynamic-multiselect]")) closeMultiselects();
      });
    }
  }

  function renderDynamicField(column, item = null) {
    if (isDynamicOperatorColumn(column)) return "";
    const value = dynamicFieldValue(column, item);
    const automaticHo = hasAutomaticHonorarios() && isDynamicHonorariosColumn(column);
    const required = column.obrigatoria && !isDynamicJustificativaColumn(column) && !automaticHo ? "required" : "";
    const readonly = column.automatico || automaticHo ? "readonly" : "";
    const disabledSelect = column.automatico ? "disabled" : "";
    const autoHint = column.automatico || automaticHo ? `<small class="field-hint">Preenchido automaticamente</small>` : "";
    const maxLength = column.max_length ? `maxlength="${Number(column.max_length)}"` : "";
    const inputMode = dynamicDigitsOnlyKeys.has(normalizedDynamicKey(column.chave))
      ? 'inputmode="numeric"'
      : ["moeda", "numero"].includes(column.tipo)
        ? 'inputmode="decimal"'
        : "";
    if (column.tipo === "select") {
      const currentValue = dynamicSelectOption(column, value).value;
      const options = (column.opcoes || []).map((option) => dynamicSelectOption(column, option)).filter((option) => option.value);
      return `
        <label><span>${escapeHtml(column.nome)}</span>
          <select id="${dynamicInputId(column)}" data-dynamic-field="${column.chave}" ${required} ${disabledSelect}>
            <option value="">Selecione</option>
            ${options.map((option) => `<option value="${escapeHtml(option.value)}" ${currentValue === option.value ? "selected" : ""}>${escapeHtml(option.label)}</option>`).join("")}
          </select>${autoHint}
        </label>`;
    }
    if (column.tipo === "multiselect") {
      const selected = normalizeMultiselectValue(value);
      const selectedKeys = new Set(selected.map((item) => normalizedDynamicKey(item)));
      const options = (column.opcoes || []).map((option) => dynamicOptionText(option)).filter(Boolean);
      const summary = selected.length === 0 ? "Selecione" : selected.length === 1 ? selected[0] : `${selected.length} selecionados`;
      return `
        <label class="dynamic-multiselect-label"><span>${escapeHtml(column.nome)}</span>
          <div
            id="${dynamicInputId(column)}"
            class="dynamic-multiselect ${selected.length ? "has-value" : ""}"
            data-dynamic-field="${column.chave}"
            data-dynamic-multiselect
            ${column.obrigatoria && !isDynamicJustificativaColumn(column) ? 'data-required="true"' : ""}
          >
            <button class="dynamic-multiselect-trigger" type="button" data-multiselect-trigger aria-expanded="false">
              <span data-multiselect-summary>${escapeHtml(summary)}</span><span aria-hidden="true">&#9662;</span>
            </button>
            <div class="dynamic-multiselect-menu">
              <div class="dynamic-multiselect-options">
                ${options.length ? options.map((option) => `
                  <label class="dynamic-multiselect-option">
                    <input type="checkbox" data-multiselect-option value="${escapeHtml(option)}" ${selectedKeys.has(normalizedDynamicKey(option)) ? "checked" : ""}>
                    <span>${escapeHtml(option)}</span>
                  </label>`).join("") : '<div class="dynamic-multiselect-empty">Nenhuma opcao configurada.</div>'}
              </div>
              <div class="dynamic-multiselect-actions">
                <button type="button" data-multiselect-clear>Limpar</button>
                <button type="button" data-multiselect-done>Concluir</button>
              </div>
            </div>
          </div>${autoHint}
        </label>`;
    }
    const inputType = column.tipo === "data" ? "date" : "text";
    return `
      <label><span>${escapeHtml(column.nome)}</span>
        <input id="${dynamicInputId(column)}" data-dynamic-field="${column.chave}" type="${inputType}" value="${escapeHtml(value)}" ${required} ${readonly} ${maxLength} ${inputMode}>
        ${autoHint}
      </label>`;
  }

  function renderDynamicFields(item = null) {
    if (!elements.dynamicStepOne || !elements.dynamicStepTwo) return;
    const visible = isDynamicCarteira();
    elements.dynamicStepOne.classList.toggle("hidden", !visible);
    elements.dynamicStepTwo.classList.toggle("hidden", !visible);
    if (!visible) {
      elements.dynamicStepOne.innerHTML = "";
      elements.dynamicStepTwo.innerHTML = "";
      return;
    }
    const identifier = dynamicIdentifierColumn();
    const editableColumns = dynamicColumns().filter((column) => column.mostrar_cadastro !== false);
    const stepOne = editableColumns.filter((column) => column.id === identifier?.id || Number(column.cadastro_etapa || 2) === 1);
    const stepTwo = editableColumns.filter((column) => !stepOne.includes(column));
    elements.dynamicStepOne.innerHTML = stepOne.map((column) => renderDynamicField(column, item)).join("");
    elements.dynamicStepTwo.innerHTML = stepTwo.map((column) => renderDynamicField(column, item)).join("");
  }

  return {
    applyDynamicAgreementTypeRules,
    bindDynamicFormEvents,
    dynamicAgreementIsAtSight,
    dynamicAutomaticValue,
    dynamicColumns,
    dynamicGridColumns,
    dynamicIdentifierColumn,
    dynamicFieldFormValue,
    dynamicFieldIsEmpty,
    focusDynamicField,
    isAgreementAtSight,
    isDynamicJustificativaColumn,
    isDynamicOperatorColumn,
    normalizeDynamicInput,
    renderDynamicFields,
    dynamicColumnMatches,
    dynamicEntryValueKeys,
  };
}
