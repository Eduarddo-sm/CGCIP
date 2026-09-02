const MONTH_NAMES = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

export function currentProfilePeriod() {
  const now = new Date();
  return { month: now.getMonth() + 1, year: now.getFullYear() };
}

export function periodRows(data, period) {
  const rows = data?.rows || [];
  const headers = data?.headers || [];
  const periods = rows.map((row) => rowPeriod(row, headers));
  if (!periods.some(Boolean)) return rows;
  return rows.filter((_row, index) => periods[index]?.month === Number(period.month)
    && periods[index]?.year === Number(period.year));
}

export function availableProfileYears(data) {
  const headers = data?.headers || [];
  const years = new Set((data?.rows || []).map((row) => rowPeriod(row, headers)?.year).filter(Boolean));
  years.add(currentProfilePeriod().year);
  return [...years].sort((a, b) => b - a);
}

export function monthOptions() {
  return MONTH_NAMES.map((label, index) => ({ value: index + 1, label }));
}

function rowPeriod(row, headers) {
  // Competencia is the canonical monthly partition. Display columns such as
  // DATA ACORDO may retain the original agreement date when a case is carried
  // into the next month, so they must never override this value.
  const canonicalPeriod = parsePeriod(row?.competencia ?? row?.competencia_mes ?? row?._competencia_mes);
  if (canonicalPeriod) return canonicalPeriod;

  const normalizedHeaders = new Map(headers.map((header) => [normalize(header), header]));
  const yearHeader = findHeader(normalizedHeaders, ["ANO"]);
  const monthHeader = findHeader(normalizedHeaders, ["MES", "COMPETENCIA"]);
  const explicitYear = integer(row?.[yearHeader]);
  const explicitMonth = monthNumber(row?.[monthHeader]);
  if (explicitYear && explicitMonth) return { year: explicitYear, month: explicitMonth };
  const combinedPeriod = parsePeriod(row?.[monthHeader]);
  if (combinedPeriod) return combinedPeriod;

  const candidates = [
    "DATA ACORDO", "DATA DO ACORDO", "DATA", "COMPETENCIA",
    "DATA DE SOLICITACAO", "DATA PAGAMENTO", "DATA DO PAGAMENTO",
  ];
  for (const candidate of candidates) {
    const header = findHeader(normalizedHeaders, [candidate]);
    const parsed = parsePeriod(row?.[header]);
    if (parsed) return parsed;
  }

  for (const value of [row?.data_acordo, row?.created_at]) {
    const parsed = parsePeriod(value);
    if (parsed) return parsed;
  }
  return null;
}

function findHeader(headers, candidates) {
  for (const candidate of candidates) {
    if (headers.has(normalize(candidate))) return headers.get(normalize(candidate));
  }
  for (const [key, header] of headers.entries()) {
    if (candidates.some((candidate) => key.includes(normalize(candidate)))) return header;
  }
  return "";
}

function parsePeriod(value) {
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return { year: value.getFullYear(), month: value.getMonth() + 1 };
  }
  const text = String(value ?? "").trim();
  if (!text) return null;
  const iso = text.match(/^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?/);
  if (iso) return validPeriod(Number(iso[1]), Number(iso[2]));
  const br = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})/);
  if (br) return validPeriod(normalizeYear(br[3]), Number(br[2]));
  const monthYear = text.match(/^(\d{1,2})[\/.-](\d{4})$/);
  if (monthYear) return validPeriod(Number(monthYear[2]), Number(monthYear[1]));
  const normalizedText = normalize(text);
  const namedMonth = MONTH_NAMES.findIndex((name) => normalizedText.includes(normalize(name)));
  const namedYear = text.match(/\b(20\d{2})\b/);
  if (namedMonth >= 0 && namedYear) return validPeriod(Number(namedYear[1]), namedMonth + 1);
  return null;
}

function monthNumber(value) {
  const numeric = integer(value);
  if (numeric >= 1 && numeric <= 12) return numeric;
  const key = normalize(value);
  const index = MONTH_NAMES.findIndex((name) => normalize(name) === key || key.includes(normalize(name)));
  return index >= 0 ? index + 1 : 0;
}

function validPeriod(year, month) {
  return year >= 2000 && year <= 2100 && month >= 1 && month <= 12 ? { year, month } : null;
}

function normalizeYear(value) {
  const year = Number(value);
  return year < 100 ? 2000 + year : year;
}

function integer(value) {
  const parsed = Number.parseInt(String(value ?? "").trim(), 10);
  return Number.isFinite(parsed) ? parsed : 0;
}

function normalize(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, " ")
    .trim()
    .toUpperCase();
}
