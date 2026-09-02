import { currentCompetencia, itemCompetencia } from "./formatters.js?v=20260714-module-contract-1";

export function availableCompetenciasForItems(items) {
  const competencias = new Set([currentCompetencia()]);
  items.forEach((item) => {
    const competencia = itemCompetencia(item);
    if (competencia) competencias.add(competencia);
  });
  return [...competencias].sort((a, b) => b.localeCompare(a));
}

export function monthItemsForCompetencia(items, selectedCompetencia) {
  return items.filter((item) => itemCompetencia(item) === selectedCompetencia);
}

export function competenciaItemCount(items, competencia) {
  return items.filter((item) => itemCompetencia(item) === competencia).length;
}

export function pluralAcordos(count) {
  return `${count} acordo${count === 1 ? "" : "s"}`;
}

export function canMoveToNextMonth(date = new Date()) {
  const lastDay = new Date(date.getFullYear(), date.getMonth() + 1, 0);
  const daysUntilClose = lastDay.getDate() - date.getDate();
  return daysUntilClose >= 0 && daysUntilClose <= 5;
}

export function nextCompetenciaValue(date = new Date()) {
  const next = new Date(date.getFullYear(), date.getMonth() + 1, 1);
  return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}`;
}
