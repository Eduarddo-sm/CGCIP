import { currentCompetencia } from "./formatters.js?v=20260714-module-contract-1";

export function createProductionState() {
  return {
    initialized: false,
    items: [],
    grid: null,
    expandedGrid: null,
    editingId: null,
    pendingStatusChange: null,
    pendingPaymentChange: null,
    moveStatusToNextMonth: false,
    formalizadoNovoAcordo: false,
    previousFormStatus: "PROPOSTA",
    step: 1,
    selectedCompetencia: currentCompetencia(),
    competenciaMenuOpen: false,
    summaryCollapsed: localStorage.getItem("negocial.producaoSummaryCollapsed") !== "0",
    focusMode: false,
    attentionFilter: null,
    user: null,
    metaPagamento: 70000,
    monthlyGoals: {},
    carteira: "GAMMA",
    schema: null,
    corrections: [],
  };
}
