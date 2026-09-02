import { formatValue } from "../core/format.js";
import { escapeAttr } from "../core/html.js";
import { bindNotesButtons, notesButton } from "./notes.js";
import { parecerPk } from "./parecerData.js";
import {
  headersFromRows,
  isGridDateHeader,
  isGridMoneyHeader,
  mountOperationalExcelGrid,
  operationalColumnWidth,
} from "./operationalExcelGrid.js?v=20260717-unfreeze-last-1";

let parecerGrid = null;

const PREFERRED_HEADERS = [
  "PK", "DATA", "NPJ", "NOME CLIENTE", "CLIENTE", "MOTIVO", "DESCRICAO", "DESCRIÇÃO",
  "OPERADOR", "NEGOCIADOR", "CARTEIRA", "STATUS", "APROVACAO", "APROVAÇÃO",
  "DATA APROVADO/REPROVADO", "SOLICITADO?", "DATA SOLICITADO", "JUSTIFICATIVA APROVACAO/REPROVACAO",
];

function orderedHeaders(rows) {
  const rank = new Map(PREFERRED_HEADERS.map((header, index) => [header, index]));
  return headersFromRows(rows)
    .map((header, index) => ({ header, index, rank: rank.get(String(header).toUpperCase()) ?? Number.MAX_SAFE_INTEGER }))
    .sort((left, right) => left.rank - right.rank || left.index - right.index)
    .map(({ header }) => header);
}

export function renderParecerExcelGrid(rows = []) {
  const headers = orderedHeaders(rows);
  if (!headers.length) return null;
  const columns = headers.map((header) => ({
    id: header,
    title: header,
    width: operationalColumnWidth(header),
    type: isGridDateHeader(header) ? "date" : undefined,
    value: (row) => row[header] ?? "",
    display: (row) => formatValue(row[header]),
    cellClass: isGridMoneyHeader(header) ? "excel-cell-money" : "",
  }));
  columns.push({
    id: "__parecer_observacoes",
    title: "Observacoes",
    width: 116,
    type: "action",
    render: (row) => notesButton("parecer", parecerPk(row), "Obs."),
  });
  parecerGrid = mountOperationalExcelGrid("#parecerCompletaGrid", {
    id: "parecer-completa-excel",
    persistKey: "gerencial:pareceres:planilha:v2",
    rows,
    columns,
  });
  const container = document.querySelector("#parecerCompletaGrid");
  bindNotesButtons(container);
  container?.setAttribute("aria-label", `Planilha de pareceres com ${escapeAttr(rows.length)} registros`);
  return parecerGrid;
}
