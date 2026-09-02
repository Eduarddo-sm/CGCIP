export const MONTHS = [
  "Janeiro",
  "Fevereiro",
  "Marco",
  "Abril",
  "Maio",
  "Junho",
  "Julho",
  "Agosto",
  "Setembro",
  "Outubro",
  "Novembro",
  "Dezembro",
];

export const TABLE_HEADERS = [
  "DATA",
  "USUARIO",
  "CARTEIRA",
  "CLIENTE",
  "NPJ",
  "GECOR",
  "HONORARIOS",
  "VALOR TOTAL",
  "STATUS",
  "ULTIMA ATUALIZACAO",
];

export const NON_EDITABLE_HEADERS = new Set([
  "ULTIMA ATUALIZACAO",
  "CRIADO EM",
  "DIAS DE ATRASO",
  "%",
  "% H.O",
]);

export const REASON_HEADERS = new Set([
  "VALOR DO ACORDO",
  "VALOR TOTAL",
  "VALOR TOTAL DE ACORDO",
  "VALOR DA ENTRADA",
  "ENTRADA",
  "ACORDO",
  "HONORARIOS",
  "HONORARIOS RECEBIDOS",
  "HONORÁRIOS",
  "HONORÁRIOS RECEBIDOS",
]);

export const EMPTY_FILTER_KEY = "__EMPTY__";

export const DATE_FILTER_HEADERS = new Set([
  "DATA",
  "DT AJUIZAMENTO",
  "DATA ACORDO",
  "DATA DE VENCIMENTO",
  "DATA DO VENCIMENTO",
  "DATA DO PAGAMENTO",
  "VENCIMENTO",
  "PAGAMENTO",
  "DATA DO 1º ATRASO",
  "ULTIMA ATUALIZACAO",
]);

export const MONEY_FILTER_HEADERS = new Set([
  "HONORARIOS",
  "HONORÁRIOS",
  "HONORARIOS RECEBIDOS",
  "HONORÁRIOS RECEBIDOS",
  "VALOR TOTAL",
  "VALOR TOTAL DE ACORDO",
  "VALOR DO ACORDO",
  "ACORDO",
  "ENTRADA",
  "VALOR DA ENTRADA",
]);

export const NUMBER_FILTER_HEADERS = new Set(["%", "% H.O", "DIAS DE ATRASO"]);
