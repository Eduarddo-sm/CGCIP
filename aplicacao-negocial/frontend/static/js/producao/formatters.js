export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function formatMoney(value) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(Number(value || 0));
}

export function formatDate(value) {
  if (!value) return "-";
  const [year, month, day] = String(value).split("-");
  if (!year || !month || !day) return String(value);
  return `${day}/${month}/${year}`;
}

export function todayInputValue() {
  const now = new Date();
  return [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");
}

export function currentCompetencia() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function itemCompetencia(item) {
  return item.competencia || String(item.data_acordo || "").slice(0, 7);
}

export function competenciaLabel(competencia) {
  if (!competencia) return "Mes atual";
  const [year, month] = competencia.split("-").map(Number);
  const date = new Date(year, month - 1, 1);
  const label = new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric" }).format(date);
  return label.charAt(0).toUpperCase() + label.slice(1);
}

export function shortCompetenciaLabel(competencia) {
  const [year, month] = competencia.split("-").map(Number);
  const date = new Date(year, month - 1, 1);
  return new Intl.DateTimeFormat("pt-BR", { month: "short", year: "2-digit" })
    .format(date)
    .replace(".", "")
    .toUpperCase();
}

export function formatPercent(value) {
  return `${Number(value || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

export function clampPercent(value) {
  return Math.max(0, Math.min(100, Number(value || 0)));
}

export function digitsOnly(value, maxLength) {
  return String(value ?? "").replace(/\D/g, "").slice(0, maxLength);
}

export function normalizeMoneyText(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return "";

  let cleaned = raw.replace(/[^0-9,.\-]/g, "");
  if (!cleaned) return "";

  const sign = cleaned.includes("-") ? "-" : "";
  cleaned = cleaned.replace(/-/g, "");

  if (cleaned.includes(",")) {
    cleaned = cleaned.replace(/\./g, "").replace(",", ".");
  } else if ((cleaned.match(/\./g) || []).length > 1) {
    const parts = cleaned.split(".");
    if (parts.at(-1).length <= 2) {
      cleaned = `${parts.slice(0, -1).join("")}.${parts.at(-1)}`;
    } else {
      cleaned = parts.join("");
    }
  } else if (cleaned.includes(".")) {
    const [whole, decimal] = cleaned.split(".");
    if (decimal.length === 3 && /^\d+$/.test(whole)) {
      cleaned = `${whole}${decimal}`;
    }
  }

  let [whole, decimal = ""] = cleaned.split(".");
  whole = whole.replace(/\D/g, "");
  decimal = decimal.replace(/\D/g, "").slice(0, 2);

  if (!whole && !decimal) return "";
  whole = whole || "0";

  return decimal ? `${sign}${whole},${decimal.padEnd(2, "0")}` : `${sign}${whole}`;
}

export function moneyToInput(value) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) return "";
  return numeric.toFixed(2).replace(".", ",");
}

export function datePayloadValue(value) {
  const raw = String(value ?? "").trim();
  if (!raw || raw === "-") return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;

  const brDate = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (brDate) {
    const [, day, month, year] = brDate;
    return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  }

  return raw;
}

export function decimalPayloadValue(value) {
  if (typeof value === "number") return String(value);
  const normalized = normalizeMoneyText(value);
  return normalized ? normalized.replace(",", ".") : "0";
}
