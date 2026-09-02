export function parseSelectedNumber(value) {
  const text = String(value ?? "").trim();
  if (!text || /^\d{4}-\d{2}-\d{2}/.test(text) || /^\d{2}\/\d{2}\/\d{4}$/.test(text)) return null;
  const numericText = text
    .replace(/[^\d,.-]/g, "")
    .replace(/\.(?=\d{3}(?:\D|$))/g, "")
    .replace(",", ".");
  if (!numericText || !/\d/.test(numericText)) return null;
  const numericValue = Number(numericText);
  return Number.isFinite(numericValue) ? numericValue : null;
}

export function formatSelectionMoney(value) {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    minimumFractionDigits: 2,
  }).format(value);
}

export function selectionSummary(selection = { cells: [] }) {
  const filledCells = (selection.cells || []).filter((cell) => String(cell.value ?? cell.display ?? "").trim());
  const numbers = filledCells
    .map((cell) => parseSelectedNumber(cell.display ?? cell.value))
    .filter((value) => value !== null);
  const parts = [`Contagem: ${filledCells.length}`];
  if (numbers.length) {
    parts.push(`Soma: ${formatSelectionMoney(numbers.reduce((total, value) => total + value, 0))}`);
  }
  return parts.join(" | ");
}
