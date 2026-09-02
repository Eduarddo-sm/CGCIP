export function createStatusDialogs(deps) {
  const {
    state,
    els,
    statusLabels,
    todayInputValue,
    submitProducaoPayload,
    saveStatusChange,
    closeDialog,
    clearError,
    updateFinancialRules,
    setFormStatusValue,
    canMoveToNextMonth,
    nextCompetenciaDisplay,
  } = deps;
  const formalizationSources = new Set(["QUEBRA", "PROPOSTA_NEGADA"]);
  const formalizationTargets = new Set(["AGUARDANDO_PAGAMENTO", "PAGAMENTO_REALIZADO"]);

  function isFormalizationTransition(previousStatus, nextStatus) {
    return formalizationSources.has(previousStatus) && formalizationTargets.has(nextStatus);
  }

  function showStatusError(message) {
    els.statusJustificativaError.textContent = message;
    els.statusJustificativaError.hidden = false;
  }

  function clearStatusError() {
    els.statusJustificativaError.hidden = true;
    els.statusJustificativaError.textContent = "";
  }

  function showStatusModal() {
    els.statusJustificativaDialog.classList.remove("hidden");
    window.setTimeout(() => els.statusJustificativaTexto.focus(), 0);
  }

  function configureNextMonthOption(nextStatus) {
    if (!els.statusNextMonthField) return;
    const visible = nextStatus === "QUEBRA" && canMoveToNextMonth();
    els.statusNextMonthField.classList.toggle("hidden", !visible);
    els.statusNextMonth.checked = false;
    if (visible) {
      els.statusNextMonthHint.textContent = `Cria uma copia em ${nextCompetenciaDisplay()} como Proposta.`;
    }
  }

  function shouldMoveToNextMonth(pending) {
    return Boolean(
      pending?.nextStatus === "QUEBRA"
        && canMoveToNextMonth()
        && els.statusNextMonth?.checked,
    );
  }

  function hideStatusModal() {
    els.statusJustificativaDialog.classList.add("hidden");
  }

  function showPaymentError(message) {
    els.pagamentoError.textContent = message;
    els.pagamentoError.hidden = false;
  }

  function clearPaymentError() {
    els.pagamentoError.hidden = true;
    els.pagamentoError.textContent = "";
  }

  function showPaymentModal() {
    els.pagamentoDialog.classList.remove("hidden");
    window.setTimeout(() => {
      if (!els.pagamentoDataField?.classList.contains("hidden")) els.pagamentoData.focus();
      else els.formalizacaoNovoAcordo?.focus();
    }, 0);
  }

  function hidePaymentModal() {
    els.pagamentoDialog.classList.add("hidden");
  }

  function configurePaymentTransition(previousStatus, nextStatus) {
    const requiresPaymentDate = nextStatus === "PAGAMENTO_REALIZADO";
    const showsFormalization = isFormalizationTransition(previousStatus, nextStatus);
    els.pagamentoDataField?.classList.toggle("hidden", !requiresPaymentDate);
    els.pagamentoData.required = requiresPaymentDate;
    els.formalizacaoNovoAcordoField?.classList.toggle("hidden", !showsFormalization);
    els.formalizacaoNovoAcordo.checked = false;
    els.pagamentoTitle.textContent = requiresPaymentDate
      ? "Informar data de pagamento"
      : "Confirmar atualizacao de status";
    els.pagamentoSaveBtn.textContent = requiresPaymentDate ? "Salvar pagamento" : "Salvar status";
  }

  function openStatusPaymentDialog(item, nextStatus, selectElement) {
    state.pendingPaymentChange = {
      mode: "inline",
      id: item.id,
      previousStatus: item.status,
      nextStatus,
      selectElement,
      previousDataPagamento: item.data_pagamento || "",
    };
    clearPaymentError();
    configurePaymentTransition(item.status, nextStatus);
    els.pagamentoData.value = item.data_pagamento || todayInputValue();
    showPaymentModal();
  }

  function openFormSavePaymentDialog(nextStatus) {
    state.pendingPaymentChange = {
      mode: "form-save",
      previousStatus: state.previousFormStatus,
      nextStatus,
      previousDataPagamento: els.dataPagamento.value || "",
    };
    clearPaymentError();
    configurePaymentTransition(state.previousFormStatus, nextStatus);
    els.pagamentoData.value = els.dataPagamento.value || todayInputValue();
    if (els.dialog.open) closeDialog();
    showPaymentModal();
  }

  function openFormPaymentDialog(nextStatus) {
    state.pendingPaymentChange = {
      mode: "form",
      previousStatus: state.previousFormStatus,
      nextStatus,
      previousDataPagamento: els.dataPagamento.value || "",
      formWasOpen: els.dialog.open,
    };
    clearPaymentError();
    configurePaymentTransition(state.previousFormStatus, nextStatus);
    els.pagamentoData.value = els.dataPagamento.value || todayInputValue();
    if (els.dialog.open) closeDialog();
    showPaymentModal();
  }

  function openStatusJustificativaDialog(item, nextStatus, selectElement) {
    state.pendingStatusChange = {
      mode: "inline",
      id: item.id,
      previousStatus: item.status,
      nextStatus,
      selectElement,
    };
    clearStatusError();
    els.statusJustificativaTitle.textContent = `Justificar ${statusLabels[nextStatus] || nextStatus}`;
    els.statusJustificativaTexto.value = item.justificativa_status || "";
    configureNextMonthOption(nextStatus);
    showStatusModal();
  }

  function openFormJustificativaDialog(nextStatus) {
    state.pendingStatusChange = {
      mode: "form",
      previousStatus: state.previousFormStatus,
      nextStatus,
      formWasOpen: els.dialog.open,
    };
    clearStatusError();
    els.statusJustificativaTitle.textContent = `Justificar ${statusLabels[nextStatus] || nextStatus}`;
    els.statusJustificativaTexto.value = els.justificativa.value || "";
    configureNextMonthOption(nextStatus);
    if (els.dialog.open) closeDialog();
    showStatusModal();
  }

  function openFormSaveJustificativaDialog(nextStatus) {
    state.pendingStatusChange = {
      mode: "form-save",
      previousStatus: state.previousFormStatus,
      nextStatus,
    };
    clearStatusError();
    els.statusJustificativaTitle.textContent = `Justificar ${statusLabels[nextStatus] || nextStatus}`;
    els.statusJustificativaTexto.value = els.justificativa.value || "";
    configureNextMonthOption(nextStatus);
    if (els.dialog.open) closeDialog();
    showStatusModal();
  }

  function cancelStatusJustificativa() {
    if (state.pendingStatusChange?.mode === "form" || state.pendingStatusChange?.mode === "form-save") {
      const shouldReopenForm = state.pendingStatusChange.formWasOpen || state.pendingStatusChange.mode === "form-save";
      setFormStatusValue(state.pendingStatusChange.previousStatus);
      els.justificativa.value = "";
      state.moveStatusToNextMonth = false;
      updateFinancialRules();
      if (shouldReopenForm && !els.dialog.open) {
        els.dialog.showModal();
      }
    } else if (state.pendingStatusChange?.selectElement) {
      state.pendingStatusChange.selectElement.value = state.pendingStatusChange.previousStatus;
    }
    state.pendingStatusChange = null;
    clearStatusError();
    hideStatusModal();
  }

  function cancelPaymentDate() {
    if (state.pendingPaymentChange?.mode === "form" || state.pendingPaymentChange?.mode === "form-save") {
      const shouldReopenForm = state.pendingPaymentChange.formWasOpen || state.pendingPaymentChange.mode === "form-save";
      setFormStatusValue(state.pendingPaymentChange.previousStatus);
      els.dataPagamento.value = state.pendingPaymentChange.previousDataPagamento || "";
      state.formalizadoNovoAcordo = false;
      updateFinancialRules();
      if (shouldReopenForm && !els.dialog.open) {
        els.dialog.showModal();
      }
    } else if (state.pendingPaymentChange?.selectElement) {
      state.pendingPaymentChange.selectElement.value = state.pendingPaymentChange.previousStatus;
    }
    state.pendingPaymentChange = null;
    if (els.formalizacaoNovoAcordo) els.formalizacaoNovoAcordo.checked = false;
    clearPaymentError();
    hidePaymentModal();
  }

  async function submitPaymentDate(event) {
    event.preventDefault();
    const pending = state.pendingPaymentChange;
    if (!pending) return;

    const requiresPaymentDate = pending.nextStatus === "PAGAMENTO_REALIZADO";
    const dataPagamento = requiresPaymentDate ? els.pagamentoData.value : null;
    const formalizadoNovoAcordo = Boolean(
      isFormalizationTransition(pending.previousStatus, pending.nextStatus)
        && els.formalizacaoNovoAcordo?.checked,
    );
    if (requiresPaymentDate && !dataPagamento) {
      showPaymentError("Informe a data de pagamento para salvar este status.");
      return;
    }

    els.pagamentoSaveBtn.disabled = true;
    els.pagamentoSaveBtn.textContent = "Salvando...";
    try {
      if (pending.mode === "form-save") {
        els.dataPagamento.value = dataPagamento;
        state.formalizadoNovoAcordo = formalizadoNovoAcordo;
        await submitProducaoPayload();
        state.pendingPaymentChange = null;
        hidePaymentModal();
        return;
      }

      if (pending.mode === "form") {
        els.dataPagamento.value = dataPagamento || "";
        state.formalizadoNovoAcordo = formalizadoNovoAcordo;
        state.previousFormStatus = pending.nextStatus;
        state.pendingPaymentChange = null;
        clearError();
        updateFinancialRules();
        hidePaymentModal();
        if (pending.formWasOpen && !els.dialog.open) {
          els.dialog.showModal();
          window.setTimeout(() => els.saveBtn.focus(), 0);
        }
        return;
      }

      await saveStatusChange(pending.id, pending.nextStatus, null, dataPagamento, {
        formalizadoNovoAcordo,
      });
      state.pendingPaymentChange = null;
      hidePaymentModal();
    } catch (error) {
      showPaymentError(error.message);
      if (pending.selectElement) {
        pending.selectElement.value = pending.previousStatus;
      }
    } finally {
      els.pagamentoSaveBtn.disabled = false;
      els.pagamentoSaveBtn.textContent = pending.nextStatus === "PAGAMENTO_REALIZADO"
        ? "Salvar pagamento"
        : "Salvar status";
    }
  }

  async function submitStatusJustificativa(event) {
    event.preventDefault();
    const pending = state.pendingStatusChange;
    if (!pending) return;

    const justificativa = els.statusJustificativaTexto.value.trim();
    if (!justificativa) {
      showStatusError("Preencha a justificativa para salvar este status.");
      return;
    }

    els.statusJustificativaSaveBtn.disabled = true;
    els.statusJustificativaSaveBtn.textContent = "Salvando...";
    try {
      if (pending.mode === "form-save") {
        els.justificativa.value = justificativa;
        state.moveStatusToNextMonth = shouldMoveToNextMonth(pending);
        await submitProducaoPayload();
        state.moveStatusToNextMonth = false;
        state.pendingStatusChange = null;
        hideStatusModal();
        return;
      }

      if (pending.mode === "form") {
        els.justificativa.value = justificativa;
        state.moveStatusToNextMonth = shouldMoveToNextMonth(pending);
        state.previousFormStatus = pending.nextStatus;
        state.pendingStatusChange = null;
        clearError();
        updateFinancialRules();
        hideStatusModal();
        if (pending.formWasOpen && !els.dialog.open) {
          els.dialog.showModal();
          window.setTimeout(() => els.saveBtn.focus(), 0);
        }
        return;
      }

      await saveStatusChange(pending.id, pending.nextStatus, justificativa, null, {
        jogarProximoMes: shouldMoveToNextMonth(pending),
      });
      state.pendingStatusChange = null;
      hideStatusModal();
    } catch (error) {
      showStatusError(error.message);
      if (pending.selectElement) {
        pending.selectElement.value = pending.previousStatus;
      }
    } finally {
      els.statusJustificativaSaveBtn.disabled = false;
      els.statusJustificativaSaveBtn.textContent = "Salvar status";
    }
  }

  return {
    cancelPaymentDate,
    cancelStatusJustificativa,
    openFormJustificativaDialog,
    openFormPaymentDialog,
    openFormSaveJustificativaDialog,
    openFormSavePaymentDialog,
    openStatusJustificativaDialog,
    openStatusPaymentDialog,
    submitPaymentDate,
    submitStatusJustificativa,
  };
}
