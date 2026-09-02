export const statusLabels = {
  PROPOSTA: "Proposta",
  AGUARDANDO_PAGAMENTO: "Aguardando pagamento",
  PAGAMENTO_REALIZADO: "Pagamento realizado",
  AGUARDANDO_LEVANTAMENTO: "Aguardando levantamento",
  PROPOSTA_NEGADA: "Proposta negada",
  QUEBRA: "Quebra",
};

export const criticalStatuses = new Set(["QUEBRA", "PROPOSTA_NEGADA"]);
export const paymentStatus = "PAGAMENTO_REALIZADO";
export const normalStatusValues = ["PROPOSTA", "AGUARDANDO_PAGAMENTO", "PAGAMENTO_REALIZADO"];

export const tipoLabels = {
  A_VISTA: "A vista",
  PARCELADO: "Parcelado",
};
