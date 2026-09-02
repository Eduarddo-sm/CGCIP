import { formatValue, normalizeText } from "../core/format.js";

const cache = new WeakMap();

export function filterRowsBySearch(rows, headers, search, formatter = formatValue) {
  const query = normalizeText(search);
  if (!query) return rows;
  const index = rowSearchIndex(rows, headers, formatter);
  return rows.filter((row, rowIndex) => index[rowIndex]?.includes(query));
}

function rowSearchIndex(rows, headers, formatter) {
  let byHeaders = cache.get(rows);
  const headerKey = headers.join("\u001f");
  if (!byHeaders) {
    byHeaders = new Map();
    cache.set(rows, byHeaders);
  }
  if (!byHeaders.has(headerKey)) {
    byHeaders.set(headerKey, rows.map((row) => normalizeText(headers.map((header) => formatter(row[header], header)).join(" "))));
  }
  return byHeaders.get(headerKey);
}
