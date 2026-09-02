export const gridState = {
  instances: new Map(),
  active: null,
  drag: null,
  editingCell: null,
  zooms: new Map(),
  toast: () => {},
};

export function configureSpreadsheetGrid(options = {}) {
  if (typeof options.toast === "function") gridState.toast = options.toast;
}

export function cellKey(row, col) {
  return `${row}:${col}`;
}

export function cellInfo(cell) {
  return {
    gridId: cell.dataset.gridId,
    row: Number(cell.dataset.sheetRow),
    rowKey: cell.dataset.sheetRowKey,
    col: Number(cell.dataset.sheetCol),
    header: cell.dataset.sheetHeader,
    value: cell.dataset.sheetValue || "",
  };
}

export function instanceFromCell(cell) {
  const instance = gridState.instances.get(cell.dataset.gridId);
  if (instance) gridState.active = instance.id;
  return instance;
}
