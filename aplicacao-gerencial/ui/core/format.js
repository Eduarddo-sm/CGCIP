export function normalizeText(value) {
  return String(value ?? "")
    .trim()
    .toUpperCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^A-Z0-9]/g, "");
}

export function formatValue(value) {
  if (value === null || value === undefined || value === "") return "Vazio";
  if (typeof value === "object") return JSON.stringify(value);
  return value;
}

export function capitalize(value) {
  return String(value || "").slice(0, 1).toUpperCase() + String(value || "").slice(1);
}
