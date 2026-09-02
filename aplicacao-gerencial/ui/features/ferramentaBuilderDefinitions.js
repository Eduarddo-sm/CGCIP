export const flowTemplates = {
  simple: {
    statuses: [
      { codigo: "PENDENTE", nome: "Pendentes", cor: "#d97706", ordem: 0, inicial: true, final: false },
      { codigo: "SOLICITADO", nome: "Solicitados", cor: "#2563eb", ordem: 1, inicial: false, final: false },
      { codigo: "CONCLUIDO", nome: "Concluidos", cor: "#059669", ordem: 2, inicial: false, final: true },
      { codigo: "CANCELADO", nome: "Cancelados", cor: "#dc2626", ordem: 3, inicial: false, final: true },
    ],
    transicoes: [
      { origem_codigo: "PENDENTE", destino_codigo: "SOLICITADO", nome: "Marcar como solicitado", exige_justificativa: false, permite_negociador: false, permite_gerencial: true },
      { origem_codigo: "SOLICITADO", destino_codigo: "CONCLUIDO", nome: "Concluir", exige_justificativa: false, permite_negociador: false, permite_gerencial: true },
      { origem_codigo: "PENDENTE", destino_codigo: "CANCELADO", nome: "Cancelar", exige_justificativa: true, permite_negociador: true, permite_gerencial: true },
    ],
  },
  approval: {
    statuses: [
      { codigo: "RECEBIDO", nome: "Recebidos", cor: "#64748b", ordem: 0, inicial: true, final: false },
      { codigo: "EM_APROVACAO", nome: "Em aprovacao", cor: "#d97706", ordem: 1, inicial: false, final: false },
      { codigo: "APROVADO", nome: "Aprovados", cor: "#7c3aed", ordem: 2, inicial: false, final: false },
      { codigo: "SOLICITADO", nome: "Solicitados", cor: "#2563eb", ordem: 3, inicial: false, final: false },
      { codigo: "CONCLUIDO", nome: "Concluidos", cor: "#059669", ordem: 4, inicial: false, final: true },
      { codigo: "REPROVADO", nome: "Reprovados", cor: "#dc2626", ordem: 5, inicial: false, final: true },
    ],
    transicoes: [
      { origem_codigo: "RECEBIDO", destino_codigo: "EM_APROVACAO", nome: "Enviar para aprovacao", exige_justificativa: false, permite_negociador: true, permite_gerencial: true },
      { origem_codigo: "EM_APROVACAO", destino_codigo: "APROVADO", nome: "Aprovar", exige_justificativa: true, permite_negociador: false, permite_gerencial: true },
      { origem_codigo: "EM_APROVACAO", destino_codigo: "REPROVADO", nome: "Reprovar", exige_justificativa: true, permite_negociador: false, permite_gerencial: true },
      { origem_codigo: "APROVADO", destino_codigo: "SOLICITADO", nome: "Marcar como solicitado", exige_justificativa: false, permite_negociador: false, permite_gerencial: true },
      { origem_codigo: "SOLICITADO", destino_codigo: "CONCLUIDO", nome: "Concluir", exige_justificativa: false, permite_negociador: false, permite_gerencial: true },
      { origem_codigo: "REPROVADO", destino_codigo: "RECEBIDO", nome: "Corrigir e reenviar", exige_justificativa: false, permite_negociador: true, permite_gerencial: true },
    ],
  },
};

export const screenTypes = [
  ["dashboard", "Dashboard"], ["lista", "Lista operacional"],
  ["aprovacao", "Aprovacao e historico"], ["historico", "Historico"],
  ["planilha", "Planilha Excel-like"],
];

export const screenComponents = [
  ["metricas", "Metricas"], ["busca", "Busca"], ["filtros", "Filtros"],
  ["lista", "Lista"], ["acoes", "Acoes"], ["planilha", "Planilha"], ["relatorio", "Relatorio"],
];

export const dashboardBlockTypes = [
  ["metric", "Indicador"],
  ["status", "Indicadores por status"],
  ["funnel", "Funil de fluxo"],
  ["distribution", "Distribuicao por campo"],
  ["ranking", "Ranking"],
  ["timeline", "Evolucao temporal"],
  ["comparison", "Comparativo de periodo"],
  ["deadline", "Faixas de prazo / SLA"],
  ["queue", "Fila operacional"],
  ["validation", "Validacao e alertas"],
  ["recent", "Registros recentes"],
];

export const dashboardAggregations = [
  ["count", "Quantidade de registros"],
  ["sum", "Soma"],
  ["average", "Media"],
  ["min", "Menor valor"],
  ["max", "Maior valor"],
  ["ratio", "Percentual entre campos"],
  ["difference", "Diferenca entre campos"],
  ["duration_average", "Tempo medio entre datas"],
];

export const dashboardConditionOperators = [
  ["eq", "Igual a"], ["neq", "Diferente de"], ["contains", "Contem"],
  ["gt", "Maior que"], ["gte", "Maior ou igual"],
  ["lt", "Menor que"], ["lte", "Menor ou igual"],
  ["filled", "Preenchido"], ["empty", "Vazio"],
];

export function defaultDashboardConfig() {
  return {
    columns: 12,
    blocks: [
      { id: "total", tipo: "metric", titulo: "Total de registros", agregacao: "count", campo: "", agrupador: "", status_codes: [], cor: "#2563eb", largura: 3, limite: 8, periodo: "day" },
      { id: "status", tipo: "status", titulo: "Situacao dos registros", agregacao: "count", campo: "", agrupador: "", status_codes: [], cor: "#2563eb", largura: 9, limite: 8, periodo: "day" },
      { id: "recentes", tipo: "recent", titulo: "Atualizacoes recentes", agregacao: "count", campo: "", agrupador: "", status_codes: [], cor: "#64748b", largura: 12, limite: 6, periodo: "day" },
    ],
  };
}

export const cardFieldRoles = [
  ["info", "Informacao"], ["titulo", "Titulo"], ["subtitulo", "Subtitulo"],
  ["destaque", "Destaque"], ["badge", "Badge"], ["rodape", "Rodape"], ["oculto", "Oculto"],
];

export const deadlineModes = [
  ["none", "Sem filtro de prazo"], ["date", "Data especifica"],
  ["period", "Intervalo de datas"], ["deadline", "Vencimento inteligente"],
];

export const deadlineFilterOptions = [
  ["all", "Todos"], ["overdue", "Vencidos"], ["today", "Vence hoje"],
  ["next3", "Proximos 3 dias"], ["next7", "Proximos 7 dias"],
  ["next30", "Proximos 30 dias"], ["later", "Posteriores"],
  ["no_date", "Sem data"], ["completed", "Encerrados"],
];

export const fieldTypes = [
  ["texto", "Texto"], ["texto_longo", "Texto longo"], ["numero", "Numero"],
  ["moeda", "Moeda"], ["data", "Data"], ["select", "Selecao"],
  ["multiselect", "Multipla selecao"], ["boolean", "Sim/Nao"],
  ["usuario", "Usuario automatico"], ["carteira", "Carteira automatica"],
  ["arquivo", "Arquivo / anexo"],
];

export function defaultFilterConfig(legacy = false) {
  return {
    mostrar_status: legacy,
    mostrar_negociador: legacy,
    mostrar_carteira: false,
    mostrar_ordenacao: legacy,
    campos: [],
    campo_data: "",
    modo_data: "none",
    prazos_visiveis: deadlineFilterOptions.map(([value]) => value),
    agrupar_prazo: false,
    iniciar_recolhido: false,
  };
}

export function defaultGroupingConfig() {
  return {
    modo: "none",
    campo: "",
    iniciar_recolhido: false,
  };
}

export function normalizedGroupingConfig(raw = {}, filters = {}) {
  const allowed = new Set(["none", "deadline", "status", "field"]);
  const legacyDeadline = Boolean(filters?.agrupar_prazo);
  const mode = allowed.has(raw?.modo) ? raw.modo : (legacyDeadline ? "deadline" : "none");
  return {
    ...defaultGroupingConfig(),
    ...raw,
    modo: mode,
    campo: typeof raw?.campo === "string" ? raw.campo : "",
    iniciar_recolhido: Object.prototype.hasOwnProperty.call(raw || {}, "iniciar_recolhido")
      ? Boolean(raw.iniciar_recolhido)
      : Boolean(filters?.iniciar_recolhido),
  };
}

export function defaultCardActionsConfig() {
  return {
    copiar: false,
    copiar_campos: [],
    observacoes: false,
    mostrar_atualizacao: true,
    status_modo: "open",
    status_origem: "flow",
    status_campo: "",
    botao_rotulo: "Abrir",
    botao_status: "",
  };
}

export function normalizedCardActionsConfig(raw = {}) {
  const modes = new Set(["none", "open", "select", "button"]);
  const sources = new Set(["flow", "field"]);
  return {
    ...defaultCardActionsConfig(),
    ...raw,
    copiar: Boolean(raw?.copiar),
    copiar_campos: Array.isArray(raw?.copiar_campos) ? raw.copiar_campos : [],
    observacoes: Boolean(raw?.observacoes),
    mostrar_atualizacao: Object.prototype.hasOwnProperty.call(raw || {}, "mostrar_atualizacao")
      ? Boolean(raw.mostrar_atualizacao)
      : true,
    status_modo: modes.has(raw?.status_modo) ? raw.status_modo : "open",
    status_origem: sources.has(raw?.status_origem) ? raw.status_origem : "flow",
    status_campo: typeof raw?.status_campo === "string" ? raw.status_campo : "",
    botao_rotulo: String(raw?.botao_rotulo || "Abrir").trim() || "Abrir",
    botao_status: typeof raw?.botao_status === "string" ? raw.botao_status : "",
  };
}

export function normalizedFilterConfig(raw = {}) {
  const explicit = ["mostrar_status", "mostrar_negociador", "mostrar_carteira", "mostrar_ordenacao", "campos"]
    .some((key) => Object.prototype.hasOwnProperty.call(raw, key));
  const validDeadlines = new Set(deadlineFilterOptions.map(([value]) => value));
  const configuredDeadlines = Array.isArray(raw.prazos_visiveis)
    ? raw.prazos_visiveis.filter((value) => validDeadlines.has(value))
    : deadlineFilterOptions.map(([value]) => value);
  return {
    ...defaultFilterConfig(!explicit),
    ...raw,
    campos: Array.isArray(raw.campos) ? raw.campos : [],
    prazos_visiveis: configuredDeadlines,
  };
}

export function defaultScreens(template = "approval") {
  if (template === "simple") {
    return [
      { id: "registros", nome: "Registros", icone: "R", tipo: "lista", visivel_negocial: true, visivel_gerencial: true, status_codes: [], historico_status_codes: [], campos: [], componentes: ["busca", "filtros", "lista", "acoes"], filtros: defaultFilterConfig(true) },
      { id: "planilha", nome: "Planilha", icone: "P", tipo: "planilha", visivel_negocial: true, visivel_gerencial: true, status_codes: [], historico_status_codes: [], campos: [], componentes: ["busca", "filtros", "planilha", "relatorio"], filtros: defaultFilterConfig(true) },
    ];
  }
  return [
    { id: "dashboard", nome: "Dashboard", icone: "D", tipo: "dashboard", visivel_negocial: true, visivel_gerencial: true, status_codes: [], historico_status_codes: [], campos: [], componentes: ["metricas"], dashboard: defaultDashboardConfig() },
    { id: "pendentes", nome: "Pendentes", icone: "P", tipo: "lista", visivel_negocial: true, visivel_gerencial: true, status_codes: ["RECEBIDO", "EM_APROVACAO"], historico_status_codes: [], campos: [], componentes: ["busca", "filtros", "lista", "acoes"], filtros: defaultFilterConfig(true) },
    { id: "aprovacao", nome: "Aprovar", icone: "A", tipo: "aprovacao", visivel_negocial: false, visivel_gerencial: true, status_codes: ["EM_APROVACAO"], historico_status_codes: ["APROVADO", "REPROVADO", "CONCLUIDO"], campos: [], componentes: ["busca", "filtros", "lista", "acoes"], filtros: defaultFilterConfig(true) },
    { id: "planilha", nome: "Planilha", icone: "P", tipo: "planilha", visivel_negocial: true, visivel_gerencial: true, status_codes: [], historico_status_codes: [], campos: [], componentes: ["busca", "filtros", "planilha", "relatorio"], filtros: defaultFilterConfig(true) },
  ];
}

export function defaultDefinition() {
  return {
    nome: "", descricao: "", tipo: "SOLICITACAO", icone: "F", cor: "#2563eb", destaque_gerencial: false,
    configuracao: {
      campo_titulo: "CLIENTE", mostrar_cards: true, metricas_cards: ["TOTAL", "MES_ATUAL"],
      usar_status: true, negociador_define_status: false, negociador_altera_status: false,
      main_hub: { enabled: false, status_codes: [], field_keys: [] },
      telas: defaultScreens("approval"),
    },
    campos: [
      { chave: "CLIENTE", nome: "Cliente", tipo: "texto", ordem: 0, etapa: 1, obrigatorio: true, visivel_negocial: true, visivel_gerencial: true },
      { chave: "DESCRICAO", nome: "Descricao", tipo: "texto_longo", ordem: 1, etapa: 1, obrigatorio: true, visivel_negocial: true, visivel_gerencial: true },
      { chave: "NEGOCIADOR", nome: "Negociador", tipo: "usuario", ordem: 2, etapa: 1, obrigatorio: true, somente_leitura: true, visivel_negocial: false, visivel_gerencial: true },
      { chave: "CARTEIRA", nome: "Carteira", tipo: "carteira", ordem: 3, etapa: 1, obrigatorio: true, somente_leitura: true, visivel_negocial: false, visivel_gerencial: true },
    ],
    statuses: flowTemplates.approval.statuses.map((item) => ({ ...item })),
    transicoes: flowTemplates.approval.transicoes.map((item) => ({ ...item })),
    permissoes: [],
  };
}
