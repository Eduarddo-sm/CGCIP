import { statusLabels } from "./constants.js?v=20260714-schema-only-1";
import { datePayloadValue, escapeHtml, formatDate, formatMoney } from "./formatters.js?v=20260714-schema-only-1";
import { normalizeStatusValue, statusOptions } from "./options.js?v=20260714-schema-only-1";

function normalizedColumnKey(column) {
  return String(column?.chave || column?.nome || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toUpperCase();
}

function isStatusColumn(column) {
  return normalizedColumnKey(column) === "STATUS";
}

function schemaOption(option) {
  if (option && typeof option === "object") {
    const value = String(option.value ?? option.label ?? option.nome ?? option.name ?? "").trim();
    const label = String(option.label ?? option.nome ?? option.name ?? value).trim();
    return { value, label };
  }
  const value = String(option ?? "").trim();
  return { value, label: value };
}

function statusValue(item, column) {
  const schemaValue = item.campos?.[column.chave];
  const rawValue = item.status ?? schemaValue ?? "PROPOSTA";
  return normalizeStatusValue(rawValue, String(rawValue || "PROPOSTA"));
}

function multiselectValue(value) {
  if (Array.isArray(value)) return value.map((item) => String(item || "").trim()).filter(Boolean);
  const text = String(value || "").trim();
  if (!text) return [];
  return text.split(/[;,]/).map((item) => item.trim()).filter(Boolean);
}

function statusSelect(item, column) {
  const currentStatus = statusValue(item, column);
  const statusClass = String(currentStatus).toLowerCase().replace(/[^a-z0-9_-]/g, "");
  const clientName = item.cliente || item.campos?.CLIENTE || "cliente";
  return `
    <select
      class="status-fill status-fill-select status-${statusClass}"
      data-action="status"
      data-id="${item.id}"
      aria-label="Status de ${escapeHtml(clientName)}"
      onchange="window.negocialProducaoStatusChange && window.negocialProducaoStatusChange(this)"
    >
      ${statusOptions(currentStatus, true)}
    </select>
  `;
}

export function buildProducaoColumns({ dynamicColumns = [], saveCell }) {
  const columns = dynamicColumns.map((column) => {
    const statusColumn = isStatusColumn(column);
    const valueForColumn = (item) => statusColumn
      ? statusValue(item, column)
      : item.campos?.[column.chave] ?? item[column.chave?.toLowerCase?.()] ?? "";
    return {
      id: `campos.${column.chave}`,
      title: column.nome,
      width: statusColumn ? 190 : column.tipo === "data" ? 130 : column.identificador ? 160 : 150,
      type: column.tipo === "select" ? "select" : column.tipo === "multiselect" ? "multiselect" : column.tipo === "data" ? "date" : undefined,
      options: statusColumn
        ? Object.entries(statusLabels).map(([value, label]) => ({ value, label }))
        : (column.opcoes || []).map(schemaOption).filter((option) => option.value),
      cellClass: column.tipo === "moeda" ? "excel-accounting-cell" : "",
      value: valueForColumn,
      display: (item) => {
        const value = valueForColumn(item);
        if (statusColumn) return statusLabels[value] || value;
        if (column.tipo === "data") return formatDate(value);
        if (column.tipo === "moeda") return formatMoney(value);
        if (column.tipo === "multiselect") return multiselectValue(value).join("; ");
        return value ?? "";
      },
      render: statusColumn ? (item) => statusSelect(item, column) : undefined,
      save: (item, value) => saveCell(
        item,
        statusColumn ? "status" : `campos.${column.chave}`,
        statusColumn
          ? normalizeStatusValue(value, item.status)
          : column.tipo === "data" ? datePayloadValue(value) : column.tipo === "multiselect" ? multiselectValue(value) : value,
      ),
    };
  });
  columns.push({
    id: "acoes",
    title: "Acoes",
    width: 92,
    type: "action",
    render: (item) => `
      <div class="row-actions">
        <button class="table-btn production-edit-btn" type="button" data-action="edit" data-id="${item.id}" title="Editar acordo" aria-label="Editar acordo">&#9998;</button>
      </div>
    `,
  });
  return columns;
}
