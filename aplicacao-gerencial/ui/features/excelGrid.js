const instances = new Map();
let activeInstance = null;
let dragState = null;
let resizeState = null;
let fillState = null;
let clipboardCut = null;
let edgeScrollFrame = 0;
const EMPTY_FILTER_KEY = "__EMPTY__";
const DATE_FILTER_PREFIX = "__DATE__:";
const MONTH_FILTER_PREFIX = "__MONTH__:";
const YEAR_FILTER_PREFIX = "__YEAR__:";
const MONTH_NAMES = [
  "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
  "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function cellKey(row, col) {
  return `${row}:${col}`;
}

function columnName(index) {
  let value = index + 1;
  let label = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    label = String.fromCharCode(65 + remainder) + label;
    value = Math.floor((value - 1) / 26);
  }
  return label;
}

function normalizeText(value) {
  if (Array.isArray(value)) return value.map((item) => String(item ?? "").trim()).filter(Boolean).join("; ");
  return String(value ?? "");
}

function refreshRows(instance) {
  const rows = applyGridFiltersAndSort(instance, [...(instance.sourceRows || [])]);

  instance.rows = rows;
  if (instance.active) {
    instance.active.row = clamp(instance.active.row, 0, Math.max(instance.rows.length - 1, 0));
    instance.active.col = clamp(instance.active.col, 0, Math.max(instance.columns.length - 1, 0));
  }
}

function normalizeFilterText(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function filterKey(value) {
  const date = parseFilterDate(value);
  if (date) return dateKey(date);
  const text = normalizeText(value).trim();
  return text || EMPTY_FILTER_KEY;
}

function filterLabel(value) {
  const text = normalizeText(value).trim();
  return text || "Vazio";
}

function filterDisplayValue(column, row) {
  if (column.display) return column.display(row);
  if (column.type === "select" && column.options) {
    const value = valueFor(column, row);
    return column.options.find((entry) => entry.value === value)?.label ?? value;
  }
  return valueFor(column, row);
}

function rowPassesFilters(instance, row, ignoredColumnId = "") {
  return (instance.allColumns?.length ? instance.allColumns : instance.columns).every((column) => {
    if (column.id === ignoredColumnId || column.type === "action") return true;
    const selected = instance.filters?.[column.id];
    if (!selected || !(selected instanceof Set)) return true;
    return selectedIncludesFilterValue(selected, filterDisplayValue(column, row));
  });
}

function selectedIncludesFilterValue(selected, value) {
  const date = parseFilterDate(value);
  if (date) {
    return selected.has(dateKey(date))
      || selected.has(monthToken(date.getFullYear(), date.getMonth()))
      || selected.has(yearToken(date.getFullYear()));
  }
  return selected.has(filterKey(value));
}

function applyGridFiltersAndSort(instance, rows) {
  const filtered = rows.filter((row) => rowPassesFilters(instance, row));
  const sort = instance.sort;
  if (!sort?.columnId) return filtered;
  const column = (instance.allColumns?.length ? instance.allColumns : instance.columns).find((item) => item.id === sort.columnId);
  if (!column) return filtered;
  return filtered.sort((a, b) => {
    const aValue = filterDisplayValue(column, a);
    const bValue = filterDisplayValue(column, b);
    const aDate = parseFilterDate(aValue);
    const bDate = parseFilterDate(bValue);
    if (aDate && bDate) return (aDate.getTime() - bDate.getTime()) * sort.dir;
    const aNumber = Number(String(aValue).replace(/[^\d,.-]/g, "").replace(/\./g, "").replace(",", "."));
    const bNumber = Number(String(bValue).replace(/[^\d,.-]/g, "").replace(/\./g, "").replace(",", "."));
    if (Number.isFinite(aNumber) && Number.isFinite(bNumber) && String(aValue).match(/\d/) && String(bValue).match(/\d/)) {
      return (aNumber - bNumber) * sort.dir;
    }
    return String(aValue ?? "").localeCompare(String(bValue ?? ""), "pt-BR", { numeric: true, sensitivity: "base" }) * sort.dir;
  });
}

function isInputLike(target) {
  return target instanceof HTMLInputElement
    || target instanceof HTMLTextAreaElement
    || target instanceof HTMLSelectElement;
}

function defaultColumnWidth(column) {
  return column.width || 132;
}

function isColumnEditable(column) {
  return Boolean(
    column
      && column.type !== "action"
      && column.editable !== false
      && typeof column.save === "function",
  );
}

function storageAvailable() {
  try {
    return typeof localStorage !== "undefined";
  } catch (_error) {
    return false;
  }
}

function gridStorageKey(instance, suffix) {
  return instance.persistKey ? `excelGrid:${instance.persistKey}:${suffix}` : "";
}

function loadStoredColumnWidths(instance) {
  const key = gridStorageKey(instance, "colWidths");
  if (!key || !storageAvailable()) return {};
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed)
        .map(([columnId, width]) => [columnId, Number(width)])
        .filter(([, width]) => Number.isFinite(width) && width >= 40),
    );
  } catch (_error) {
    return {};
  }
}

function saveStoredColumnWidths(instance) {
  const key = gridStorageKey(instance, "colWidths");
  if (!key || !storageAvailable()) return;
  const validWidths = Object.fromEntries(
    Object.entries(instance.colWidths || {})
      .map(([columnId, width]) => [columnId, Number(width)])
      .filter(([, width]) => Number.isFinite(width) && width >= 40),
  );
  try {
    localStorage.setItem(key, JSON.stringify(validWidths));
  } catch (_error) {
    // Prefer keeping the grid responsive over surfacing storage quota errors.
  }
}

function loadStoredLayout(instance) {
  const key = gridStorageKey(instance, "layout");
  if (!key || !storageAvailable()) return {};
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || "{}");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch (_error) {
    return {};
  }
}

function saveStoredLayout(instance) {
  const key = gridStorageKey(instance, "layout");
  if (!key || !storageAvailable()) return;
  try {
    localStorage.setItem(key, JSON.stringify({
      order: instance.columnOrder || [],
      hidden: [...(instance.hiddenColumns || [])],
      frozenCount: instance.frozenCount || 0,
      zoom: instance.zoom || 100,
      rowHeights: instance.rowHeights || {},
    }));
  } catch (_error) {
    // Local preferences are optional; the grid must remain usable without them.
  }
}

function applyColumnPreferences(instance) {
  const allColumns = instance.allColumns || [];
  const byId = new Map(allColumns.map((column) => [column.id, column]));
  const actionIds = allColumns.filter((column) => column.type === "action").map((column) => column.id);
  const requestedOrder = (instance.columnOrder || [])
    .filter((id) => byId.has(id) && !actionIds.includes(id));
  const missing = allColumns
    .map((column) => column.id)
    .filter((id) => !actionIds.includes(id) && !requestedOrder.includes(id));
  instance.columnOrder = [...requestedOrder, ...missing, ...actionIds];

  const ordered = instance.columnOrder.map((id) => byId.get(id)).filter(Boolean);
  const visible = ordered.filter((column) => column.type === "action" || !instance.hiddenColumns.has(column.id));
  instance.columns = visible.length ? visible : ordered.slice(0, 1);
  instance.frozenCount = clamp(instance.frozenCount || 0, 0, instance.columns.length);
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function normalizeRange(aRow, aCol, bRow, bCol) {
  return {
    rowStart: Math.min(aRow, bRow),
    rowEnd: Math.max(aRow, bRow),
    colStart: Math.min(aCol, bCol),
    colEnd: Math.max(aCol, bCol),
  };
}

function valueFor(column, row) {
  if (column.value) return column.value(row);
  return row?.[column.id];
}

function displayFor(column, row) {
  if (column.render) return column.render(row);
  if (column.display) return escapeHtml(column.display(row));
  if (column.type === "select" && column.options) {
    const value = valueFor(column, row);
    const option = column.options.find((entry) => entry.value === value);
    return escapeHtml(option?.label ?? value);
  }
  if (column.type === "multiselect") return escapeHtml(normalizeText(valueFor(column, row)));
  return escapeHtml(valueFor(column, row));
}

function selectedCells(instance) {
  return [...instance.selected].map((key) => {
    const [row, col] = key.split(":").map(Number);
    return { row, col };
  });
}

function selectedBounds(instance) {
  const cells = selectedCells(instance);
  if (!cells.length) return null;
  return {
    rowStart: Math.min(...cells.map((cell) => cell.row)),
    rowEnd: Math.max(...cells.map((cell) => cell.row)),
    colStart: Math.min(...cells.map((cell) => cell.col)),
    colEnd: Math.max(...cells.map((cell) => cell.col)),
  };
}

function selectedCellDetails(instance) {
  return selectedCells(instance)
    .filter(({ row, col }) => row >= 0 && col >= 0 && row < instance.rows.length && col < instance.columns.length)
    .map(({ row, col }) => {
      const column = instance.columns[col];
      const item = instance.rows[row];
      return {
        row,
        col,
        column,
        item,
        value: valueFor(column, item),
        display: column.display ? column.display(item) : valueFor(column, item),
      };
    });
}

function numericCellValue(detail) {
  if (!detail || detail.column?.type === "date" || detail.column?.type === "action") return null;
  const cellClass = typeof detail.column?.cellClass === "function"
    ? detail.column.cellClass(detail.item)
    : String(detail.column?.cellClass || "");
  const numericColumn = ["number", "money", "currency"].includes(detail.column?.type)
    || /excel-cell-(?:money|number)/.test(cellClass);
  if (!numericColumn) return null;
  const raw = normalizeText(detail.value).trim();
  if (!raw || parseFilterDate(raw)) return null;
  const normalized = raw
    .replace(/R\$\s*/gi, "")
    .replace(/\s/g, "")
    .replace(/\.(?=\d{3}(?:\D|$))/g, "")
    .replace(",", ".")
    .replace(/[^\d+-.]/g, "");
  const value = Number(normalized);
  return Number.isFinite(value) ? value : null;
}

function isMoneyCell(detail) {
  const cellClass = typeof detail.column?.cellClass === "function"
    ? detail.column.cellClass(detail.item)
    : String(detail.column?.cellClass || "");
  return ["money", "currency"].includes(detail.column?.type) || cellClass.includes("excel-cell-money");
}

function formatStatusNumber(value, currency = false) {
  return new Intl.NumberFormat("pt-BR", currency
    ? { style: "currency", currency: "BRL", maximumFractionDigits: 2 }
    : { maximumFractionDigits: 2 }).format(value);
}

function updateStatusBar(instance, details = selectedCellDetails(instance)) {
  const summary = instance.container.querySelector("[data-grid-selection-summary]");
  if (!summary) return;
  const nonEmpty = details.filter((detail) => normalizeText(detail.value).trim() !== "");
  const numericDetails = details
    .map((detail) => ({ detail, value: numericCellValue(detail) }))
    .filter(({ value }) => value !== null);
  const numbers = numericDetails.map(({ value }) => value);
  const parts = [`Contagem: ${nonEmpty.length}`];
  if (numbers.length) {
    const sum = numbers.reduce((total, value) => total + value, 0);
    const currency = numericDetails.every(({ detail }) => isMoneyCell(detail));
    parts.unshift(`Média: ${formatStatusNumber(sum / numbers.length, currency)}`);
    parts.push(`Soma: ${formatStatusNumber(sum, currency)}`);
  }
  summary.textContent = parts.join("   ");
}

function gridStateText(instance) {
  if (instance.pendingSaves > 0) return "Salvando...";
  if (instance.saveState === "saved") return "Salvo agora";
  if (instance.saveState === "error") return "Erro ao salvar";
  return "Pronto";
}

function updateGridStateLabel(instance) {
  const label = instance.container.querySelector("[data-grid-state]");
  const stateName = instance.pendingSaves > 0 ? "saving" : (instance.saveState || "idle");
  if (label) {
    label.textContent = gridStateText(instance);
    label.dataset.state = stateName;
  }
  instance.onSaveStateChange?.({ state: stateName, pending: instance.pendingSaves });
}

function scheduleGridReady(instance) {
  window.clearTimeout(instance.saveStateTimer);
  instance.saveStateTimer = window.setTimeout(() => {
    if (instance.pendingSaves > 0) return;
    instance.saveState = "idle";
    updateGridStateLabel(instance);
  }, 2400);
}

function emitSelectionChange(instance) {
  const detail = {
    cells: selectedCellDetails(instance),
    active: instance.active ? { ...instance.active } : null,
  };
  updateStatusBar(instance, detail.cells);
  instance.onSelectionChange?.(detail);
}

function applyRange(instance, rowStart, colStart, rowEnd, colEnd, append = false) {
  if (!append) instance.selected.clear();
  const range = normalizeRange(rowStart, colStart, rowEnd, colEnd);
  for (let row = range.rowStart; row <= range.rowEnd; row += 1) {
    for (let col = range.colStart; col <= range.colEnd; col += 1) {
      instance.selected.add(cellKey(row, col));
    }
  }
  renderSelection(instance);
}

function setActiveCell(instance, row, col, options = {}) {
  if (!instance.rows.length || !instance.columns.length) return;
  const nextRow = clamp(row, 0, instance.rows.length - 1);
  const nextCol = clamp(col, 0, instance.columns.length - 1);
  instance.active = { row: nextRow, col: nextCol };
  instance.anchor = options.keepAnchor ? instance.anchor : { row: nextRow, col: nextCol };

  if (options.shift && instance.anchor) {
    applyRange(instance, instance.anchor.row, instance.anchor.col, nextRow, nextCol);
  } else if (!options.keepSelection) {
    instance.selected.clear();
    instance.selected.add(cellKey(nextRow, nextCol));
    renderSelection(instance);
  } else {
    renderSelection(instance);
  }

  updateFormulaBar(instance);
  if (options.focus !== false) {
    focusCell(instance, nextRow, nextCol, options.scroll || {});
  }
}

function focusCell(instance, row, col, scrollOptions = {}) {
  let cell = instance.container.querySelector(`.excel-cell[data-row="${row}"][data-col="${col}"]`);
  if (!cell && instance.rows.length > instance.virtualThreshold) {
    const viewport = instance.container.querySelector(".excel-sheet-viewport");
    if (viewport) {
      viewport.scrollTop = Math.max(0, row * 30 * ((instance.zoom || 100) / 100) - viewport.clientHeight / 2);
      renderGrid(instance, { preserveScroll: true });
      cell = instance.container.querySelector(`.excel-cell[data-row="${row}"][data-col="${col}"]`);
    }
  }
  if (!cell) return;
  cell.focus({ preventScroll: true });
  ensureCellVisible(instance, cell, scrollOptions);
}

function ensureCellVisible(instance, cell, options = {}) {
  const viewport = instance.container.querySelector(".excel-sheet-viewport");
  if (!viewport) return;

  const maxLeft = Math.max(0, viewport.scrollWidth - viewport.clientWidth);
  const maxTop = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
  if (options.edgeJump && options.colDelta > 0) viewport.scrollLeft = maxLeft;
  if (options.edgeJump && options.colDelta < 0) viewport.scrollLeft = 0;
  if (options.edgeJump && options.rowDelta > 0) viewport.scrollTop = maxTop;
  if (options.edgeJump && options.rowDelta < 0) viewport.scrollTop = 0;

  const leftPadding = 6;
  const rightPadding = 6;
  const verticalPadding = 6;
  const rowHeaderWidth = 42;
  const stickyHeaderHeight = 59;
  const viewportRect = viewport.getBoundingClientRect();
  const cellRect = cell.getBoundingClientRect();
  const visibleLeft = viewportRect.left + rowHeaderWidth + leftPadding;
  const visibleRight = viewportRect.right - rightPadding;
  const visibleTop = viewportRect.top + stickyHeaderHeight + verticalPadding;
  const visibleBottom = viewportRect.bottom - verticalPadding;

  if (cellRect.right > visibleRight) {
    viewport.scrollLeft = Math.min(maxLeft, viewport.scrollLeft + (cellRect.right - visibleRight));
  } else if (cellRect.left < visibleLeft) {
    viewport.scrollLeft = Math.max(0, viewport.scrollLeft - (visibleLeft - cellRect.left));
  }

  if (cellRect.bottom > visibleBottom) {
    viewport.scrollTop = Math.min(maxTop, viewport.scrollTop + (cellRect.bottom - visibleBottom));
  } else if (cellRect.top < visibleTop) {
    viewport.scrollTop = Math.max(0, viewport.scrollTop - (visibleTop - cellRect.top));
  }
}

function captureGridPosition(instance) {
  const viewport = instance.container.querySelector(".excel-sheet-viewport");
  return {
    scrollLeft: viewport?.scrollLeft ?? 0,
    scrollTop: viewport?.scrollTop ?? 0,
    active: instance.active ? { ...instance.active } : null,
    anchor: instance.anchor ? { ...instance.anchor } : null,
    selected: [...instance.selected],
  };
}

function clampCellPosition(instance, cell) {
  if (!cell || !instance.rows.length || !instance.columns.length) return null;
  return {
    row: clamp(cell.row, 0, instance.rows.length - 1),
    col: clamp(cell.col, 0, instance.columns.length - 1),
  };
}

function applyGridPosition(instance, position) {
  if (!position) return;

  if (!instance.rows.length || !instance.columns.length) {
    instance.active = null;
    instance.anchor = null;
    instance.selected.clear();
    return;
  }

  const active = clampCellPosition(instance, position.active);
  const anchor = clampCellPosition(instance, position.anchor);
  instance.active = active || instance.active || { row: 0, col: 0 };
  instance.anchor = anchor || instance.active;

  instance.selected.clear();
  (position.selected || []).forEach((key) => {
    const [row, col] = String(key).split(":").map(Number);
    if (
      Number.isFinite(row)
      && Number.isFinite(col)
      && row >= 0
      && col >= 0
      && row < instance.rows.length
      && col < instance.columns.length
    ) {
      instance.selected.add(cellKey(row, col));
    }
  });

  if (!instance.selected.size && instance.active) {
    instance.selected.add(cellKey(instance.active.row, instance.active.col));
  }
}

function restoreGridScroll(instance, position) {
  if (!position) return;
  const viewport = instance.container.querySelector(".excel-sheet-viewport");
  if (!viewport) return;
  viewport.scrollLeft = position.scrollLeft || 0;
  viewport.scrollTop = position.scrollTop || 0;
}

function selectionRanges(instance) {
  const rows = new Map();
  instance.selected.forEach((key) => {
    const [row, col] = key.split(":").map(Number);
    if (!Number.isFinite(row) || !Number.isFinite(col)) return;
    if (!rows.has(row)) rows.set(row, []);
    rows.get(row).push(col);
  });

  const ranges = [];
  const openRanges = new Map();
  [...rows.keys()].sort((a, b) => a - b).forEach((row) => {
    const columns = [...new Set(rows.get(row))].sort((a, b) => a - b);
    const runs = [];
    columns.forEach((col) => {
      const current = runs[runs.length - 1];
      if (current && col === current.colEnd + 1) current.colEnd = col;
      else runs.push({ colStart: col, colEnd: col });
    });

    const nextOpen = new Map();
    runs.forEach((run) => {
      const runKey = run.colStart + ":" + run.colEnd;
      const existing = openRanges.get(runKey);
      if (existing && existing.rowEnd === row - 1) {
        existing.rowEnd = row;
        nextOpen.set(runKey, existing);
      } else {
        const range = { rowStart: row, rowEnd: row, ...run };
        ranges.push(range);
        nextOpen.set(runKey, range);
      }
    });
    openRanges.clear();
    nextOpen.forEach((range, runKey) => openRanges.set(runKey, range));
  });
  return ranges;
}

function renderedRowNumbers(instance) {
  return [...new Set(
    [...instance.container.querySelectorAll(".excel-cell[data-row]")]
      .map((cell) => Number(cell.dataset.row))
      .filter(Number.isFinite),
  )].sort((a, b) => a - b);
}

function renderSelectionOutlines(instance) {
  const shell = instance.container.querySelector(".excel-grid-shell");
  const viewport = instance.container.querySelector(".excel-sheet-viewport");
  shell?.querySelectorAll(".excel-selection-outline").forEach((node) => node.remove());
  if (!shell || !viewport || !instance.selected.size) return;

  const ranges = selectionRanges(instance);
  const renderedRows = renderedRowNumbers(instance);
  if (!ranges.length || !renderedRows.length) return;
  const shellRect = shell.getBoundingClientRect();
  const viewportRect = viewport.getBoundingClientRect();
  const clip = {
    left: viewportRect.left + 42,
    top: viewportRect.top + 59,
    right: viewportRect.left + viewport.clientWidth,
    bottom: viewportRect.top + viewport.clientHeight,
  };

  ranges.forEach((range) => {
    const rowsInView = renderedRows.filter((row) => row >= range.rowStart && row <= range.rowEnd);
    if (!rowsInView.length) return;
    const preferredRow = instance.active?.row >= range.rowStart && instance.active?.row <= range.rowEnd
      ? instance.active.row
      : rowsInView[0];
    const horizontalRow = rowsInView.includes(preferredRow) ? preferredRow : rowsInView[0];
    const leftCell = instance.container.querySelector(
      '.excel-cell[data-row="' + horizontalRow + '"][data-col="' + range.colStart + '"]',
    );
    const rightCell = instance.container.querySelector(
      '.excel-cell[data-row="' + horizontalRow + '"][data-col="' + range.colEnd + '"]',
    );
    if (!leftCell || !rightCell) return;

    const leftRect = leftCell.getBoundingClientRect();
    const rightRect = rightCell.getBoundingClientRect();
    const topCell = renderedRows.includes(range.rowStart)
      ? instance.container.querySelector('.excel-cell[data-row="' + range.rowStart + '"][data-col="' + range.colStart + '"]')
      : null;
    const bottomCell = renderedRows.includes(range.rowEnd)
      ? instance.container.querySelector('.excel-cell[data-row="' + range.rowEnd + '"][data-col="' + range.colEnd + '"]')
      : null;
    const full = {
      left: leftRect.left,
      right: rightRect.right,
      top: topCell?.getBoundingClientRect().top ?? clip.top - 1,
      bottom: bottomCell?.getBoundingClientRect().bottom ?? clip.bottom + 1,
    };
    if (full.right <= clip.left || full.left >= clip.right || full.bottom <= clip.top || full.top >= clip.bottom) return;

    const visible = {
      left: Math.max(full.left, clip.left),
      right: Math.min(full.right, clip.right),
      top: Math.max(full.top, clip.top),
      bottom: Math.min(full.bottom, clip.bottom),
    };
    if (visible.right <= visible.left || visible.bottom <= visible.top) return;

    const outline = document.createElement("div");
    outline.className = "excel-selection-outline";
    outline.classList.toggle("clipped-left", full.left < clip.left);
    outline.classList.toggle("clipped-right", full.right > clip.right);
    outline.classList.toggle("clipped-top", full.top < clip.top);
    outline.classList.toggle("clipped-bottom", full.bottom > clip.bottom);
    outline.style.left = (visible.left - shellRect.left) + "px";
    outline.style.top = (visible.top - shellRect.top) + "px";
    outline.style.width = (visible.right - visible.left) + "px";
    outline.style.height = (visible.bottom - visible.top) + "px";

    const canFill = ranges.length === 1
      && !fillState
      && !outline.classList.contains("clipped-right")
      && !outline.classList.contains("clipped-bottom")
      && instance.columns[range.colEnd]?.type !== "action";
    if (canFill) {
      const handle = document.createElement("span");
      handle.className = "excel-fill-handle";
      handle.title = "Preencher por arraste";
      outline.appendChild(handle);
    }
    shell.appendChild(outline);
  });
}

function renderSelection(instance) {
  const rowsWithSelection = new Set();
  const colsWithSelection = new Set();
  instance.container.classList.toggle("excel-range-selection", instance.selected.size > 1);
  instance.container.querySelectorAll(".excel-fill-handle").forEach((node) => node.remove());

  instance.container.querySelectorAll(".excel-cell").forEach((cell) => {
    const row = Number(cell.dataset.row);
    const col = Number(cell.dataset.col);
    const key = cellKey(row, col);
    const selected = instance.selected.has(key);
    const active = instance.active?.row === row && instance.active?.col === col;
    cell.classList.toggle("selected", selected);
    cell.classList.toggle("active", active);
    cell.classList.toggle("cut-source", instance.cutCells?.has(key) || false);
    cell.classList.toggle("fill-preview", Boolean(
      instance.fillPreview
        && row >= instance.fillPreview.rowStart
        && row <= instance.fillPreview.rowEnd
        && col >= instance.fillPreview.colStart
        && col <= instance.fillPreview.colEnd,
    ));
    cell.classList.toggle("selection-edge-top", selected && !instance.selected.has(cellKey(row - 1, col)));
    cell.classList.toggle("selection-edge-right", selected && !instance.selected.has(cellKey(row, col + 1)));
    cell.classList.toggle("selection-edge-bottom", selected && !instance.selected.has(cellKey(row + 1, col)));
    cell.classList.toggle("selection-edge-left", selected && !instance.selected.has(cellKey(row, col - 1)));
    if (selected) {
      rowsWithSelection.add(row);
      colsWithSelection.add(col);
    }
  });

  instance.container.querySelectorAll("[data-row-select]").forEach((node) => {
    const row = Number(node.dataset.rowSelect);
    node.classList.toggle("selected", rowsWithSelection.has(row));
    node.classList.toggle("active", instance.active?.row === row);
  });

  instance.container.querySelectorAll("[data-col-select]").forEach((node) => {
    const col = Number(node.dataset.colSelect);
    node.classList.toggle("selected", colsWithSelection.has(col));
    node.classList.toggle("active", instance.active?.col === col);
  });

  renderSelectionOutlines(instance);
  emitSelectionChange(instance);
}

function updateFormulaBar(instance) {
  const nameBox = instance.container.querySelector(".excel-name-box");
  const formulaInput = instance.container.querySelector(".excel-formula-input");
  if (!nameBox || !formulaInput || !instance.active) return;
  const column = instance.columns[instance.active.col];
  const row = instance.rows[instance.active.row];
  nameBox.textContent = `${columnName(instance.active.col)}${instance.active.row + 1}`;
  formulaInput.value = normalizeText(valueFor(column, row));
  formulaInput.disabled = !isColumnEditable(column);
}

function editorHtml(column, value) {
  if (column.type === "select" && column.options) {
    return `
      <select class="excel-cell-editor">
        ${column.options.map((option) => `
          <option value="${escapeHtml(option.value)}" ${option.value === value ? "selected" : ""}>${escapeHtml(option.label)}</option>
        `).join("")}
      </select>
    `;
  }
  if (column.type === "multiselect" && column.options) {
    const selected = new Set((Array.isArray(value) ? value : normalizeText(value).split(/[;,]/)).map((item) => String(item).trim()));
    const size = Math.min(Math.max(column.options.length, 2), 6);
    return `
      <select class="excel-cell-editor excel-multiselect-editor" multiple size="${size}">
        ${column.options.map((option) => `
          <option value="${escapeHtml(option.value)}" ${selected.has(String(option.value)) ? "selected" : ""}>${escapeHtml(option.label)}</option>
        `).join("")}
      </select>
    `;
  }
  const type = column.type === "date" ? "date" : "text";
  const editorValue = column.type === "date" ? normalizeDateEditorValue(value) : value;
  return `<input class="excel-cell-editor" type="${type}" value="${escapeHtml(editorValue)}">`;
}

function normalizeDateEditorValue(value) {
  const raw = normalizeText(value).trim();
  if (/^\d{4}-\d{2}-\d{2}/.test(raw)) return raw.slice(0, 10);
  const brDate = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (!brDate) return "";
  const [, day, month, year] = brDate;
  return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
}

function startEdit(instance, row, col, initialValue = null) {
  const column = instance.columns[col];
  const item = instance.rows[row];
  if (!isColumnEditable(column)) return;

  const cell = instance.container.querySelector(`.excel-cell[data-row="${row}"][data-col="${col}"]`);
  if (!cell) return;

  const rawValue = initialValue ?? valueFor(column, item);
  const currentValue = column.type === "multiselect" ? rawValue : normalizeText(rawValue);
  instance.editing = { row, col, oldValue: column.type === "multiselect" ? valueFor(column, item) : normalizeText(valueFor(column, item)) };
  cell.classList.add("editing");
  cell.innerHTML = editorHtml(column, currentValue);
  const editor = cell.querySelector(".excel-cell-editor");
  editor?.focus();
  if (editor instanceof HTMLInputElement) editor.select();
}

async function commitEdit(instance, commitValue = null) {
  if (!instance.editing) return false;
  const { row, col, oldValue } = instance.editing;
  const column = instance.columns[col];
  const cell = instance.container.querySelector(`.excel-cell[data-row="${row}"][data-col="${col}"]`);
  const editor = cell?.querySelector(".excel-cell-editor");
  const nextValue = commitValue ?? (
    editor instanceof HTMLSelectElement && editor.multiple
      ? [...editor.selectedOptions].map((option) => option.value)
      : editor?.value ?? ""
  );
  instance.editing = null;

  if (JSON.stringify(nextValue) === JSON.stringify(oldValue)) {
    if (cell) {
      cell.classList.remove("editing");
      cell.innerHTML = displayFor(column, instance.rows[row]);
    }
    return true;
  }

  return saveCell(instance, row, col, nextValue, { oldValue, pushHistory: true });
}

function cancelEdit(instance) {
  if (!instance.editing) return;
  const { row, col } = instance.editing;
  const column = instance.columns[col];
  const cell = instance.container.querySelector(`.excel-cell[data-row="${row}"][data-col="${col}"]`);
  instance.editing = null;
  if (cell) {
    cell.classList.remove("editing");
    cell.innerHTML = displayFor(column, instance.rows[row]);
  }
}

function sameRow(left, right) {
  if (left === right) return true;
  const leftId = left?.id ?? left?._row_id ?? left?.pk;
  const rightId = right?.id ?? right?._row_id ?? right?.pk;
  return leftId !== undefined && leftId !== null && String(leftId) === String(rightId);
}

function replaceRowData(instance, currentItem, updatedItem, fallbackRow) {
  const sourceIndex = instance.sourceRows.findIndex((entry) => sameRow(entry, currentItem));
  if (sourceIndex >= 0) instance.sourceRows[sourceIndex] = updatedItem;

  const viewIndex = instance.rows.findIndex((entry) => sameRow(entry, currentItem));
  const targetRow = viewIndex >= 0 ? viewIndex : fallbackRow;
  if (targetRow >= 0 && targetRow < instance.rows.length) instance.rows[targetRow] = updatedItem;
  return targetRow;
}

function refreshRenderedRow(instance, row) {
  if (row < 0 || row >= instance.rows.length) return;
  const item = instance.rows[row];
  instance.columns.forEach((column, col) => {
    const cell = instance.container.querySelector(`.excel-cell[data-row="${row}"][data-col="${col}"]`);
    if (!cell) return;
    cell.classList.remove("editing", "saving");
    cell.innerHTML = displayFor(column, item);
  });
  renderSelection(instance);
  updateFormulaBar(instance);
  updateStatusBar(instance);
}

async function saveCell(instance, row, col, nextValue, options = {}) {
  const column = instance.columns[col];
  const item = instance.rows[row];
  if (!isColumnEditable(column)) return false;

  const oldValue = options.oldValue ?? normalizeText(valueFor(column, item));
  const cell = instance.container.querySelector(`.excel-cell[data-row="${row}"][data-col="${col}"]`);
  cell?.classList.add("saving");
  window.clearTimeout(instance.saveStateTimer);
  instance.saveState = "saving";
  instance.pendingSaves += 1;
  updateGridStateLabel(instance);
  try {
    const result = await column.save(item, nextValue, { row, col, oldValue });
    if (result === false) {
      instance.saveState = "idle";
      if (options.render !== false) refreshRenderedRow(instance, row);
      setActiveCell(instance, row, col, { keepSelection: true, focus: false });
      return false;
    }
    let renderedRow = row;
    if (result && typeof result === "object") {
      renderedRow = replaceRowData(instance, item, result, row);
    }
    if (options.pushHistory !== false) {
      instance.undoStack.push({ row, col, oldValue, newValue: nextValue });
      instance.redoStack.length = 0;
    }
    if (options.render !== false) {
      refreshRenderedRow(instance, renderedRow);
      setActiveCell(instance, renderedRow, col, { keepSelection: true, focus: false });
    }
    instance.saveState = "saved";
    return true;
  } catch (error) {
    instance.saveState = "error";
    instance.onError?.(error);
    if (options.render !== false) {
      refreshRenderedRow(instance, row);
      setActiveCell(instance, row, col, { keepSelection: true, focus: false });
    }
    return false;
  } finally {
    instance.pendingSaves = Math.max(0, instance.pendingSaves - 1);
    updateGridStateLabel(instance);
    scheduleGridReady(instance);
    cell?.classList.remove("saving");
  }
}

function selectionText(instance) {
  const bounds = selectedBounds(instance);
  if (!bounds) return "";
  const lines = [];
  for (let row = bounds.rowStart; row <= bounds.rowEnd; row += 1) {
    const values = [];
    for (let col = bounds.colStart; col <= bounds.colEnd; col += 1) {
      if (!instance.selected.has(cellKey(row, col))) {
        values.push("");
        continue;
      }
      const column = instance.columns[col];
      values.push(normalizeText(valueFor(column, instance.rows[row])).replace(/\t/g, " ").replace(/\r?\n/g, " "));
    }
    lines.push(values.join("\t"));
  }
  return lines.join("\n");
}

function copySelection(instance, clipboardData) {
  const text = selectionText(instance);
  if (text) clipboardData.setData("text/plain", text);
}

async function pasteSelection(instance, text) {
  if (!instance.active || !text) return;
  const rows = text.replace(/\r/g, "").split("\n").filter((line, index, list) => line || index < list.length - 1);
  if (!rows.length) return;

  const changes = [];
  for (let rowOffset = 0; rowOffset < rows.length; rowOffset += 1) {
    const values = rows[rowOffset].split("\t");
    for (let colOffset = 0; colOffset < values.length; colOffset += 1) {
      const row = instance.active.row + rowOffset;
      const col = instance.active.col + colOffset;
      if (row >= instance.rows.length || col >= instance.columns.length) continue;
      const column = instance.columns[col];
      if (!isColumnEditable(column)) continue;
      changes.push({ row, col, value: values[colOffset] });
    }
  }

  let changed = false;
  for (const change of changes) {
    changed = await saveCell(instance, change.row, change.col, change.value, {
      pushHistory: true,
      render: false,
    }) || changed;
  }

  if (changed) {
    refreshRows(instance);
    renderGrid(instance, { preserveScroll: true });
    setActiveCell(instance, instance.active.row, instance.active.col, { keepSelection: true, focus: false });
  }

  if (clipboardCut && clipboardCut.instance === instance && clipboardCut.cells.length) {
    const destination = new Set(changes.map((change) => cellKey(change.row, change.col)));
    for (const source of clipboardCut.cells) {
      if (destination.has(cellKey(source.row, source.col)) || !isColumnEditable(source.column)) continue;
      await saveCell(instance, source.row, source.col, "", { pushHistory: true, render: false });
    }
    clipboardCut = null;
    instance.cutCells = new Set();
    refreshRows(instance);
    renderGrid(instance, { preserveScroll: true });
  }
}

async function undo(instance) {
  const change = instance.undoStack.pop();
  if (!change) return;
  await saveCell(instance, change.row, change.col, change.oldValue, { pushHistory: false });
  instance.redoStack.push(change);
}

async function redo(instance) {
  const change = instance.redoStack.pop();
  if (!change) return;
  await saveCell(instance, change.row, change.col, change.newValue, { pushHistory: false });
  instance.undoStack.push(change);
}

async function clearSelectedCells(instance) {
  const cells = selectedCellDetails(instance).filter((detail) => isColumnEditable(detail.column));
  let changed = false;
  for (const detail of cells) {
    changed = await saveCell(instance, detail.row, detail.col, "", { pushHistory: true, render: false }) || changed;
  }
  if (changed) {
    refreshRows(instance);
    renderGrid(instance, { preserveScroll: true });
  }
}

function moveActive(instance, rowDelta, colDelta, options = {}) {
  const current = instance.active || { row: 0, col: 0 };
  setActiveCell(instance, current.row + rowDelta, current.col + colDelta, {
    shift: options.shift,
    keepAnchor: options.shift,
  });
}

function jumpActive(instance, key, options = {}) {
  const current = instance.active || { row: 0, col: 0 };
  const targets = {
    ArrowUp: { row: 0, col: current.col },
    ArrowDown: { row: instance.rows.length - 1, col: current.col },
    ArrowLeft: { row: current.row, col: 0 },
    ArrowRight: { row: current.row, col: instance.columns.length - 1 },
  };
  const target = targets[key];
  if (!target) return;
  setActiveCell(instance, target.row, target.col, {
    shift: options.shift,
    keepAnchor: options.shift,
    scroll: {
      edgeJump: true,
      rowDelta: target.row - current.row,
      colDelta: target.col - current.col,
    },
  });
}

function handleKeydown(event, instance) {
  activeInstance = instance;
  if (event.target.classList?.contains("excel-formula-input")) return;
  if (isInputLike(event.target)) return;

  if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "l") {
    event.preventDefault();
    clearGridFilters(instance);
    return;
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a") {
    event.preventDefault();
    if (instance.rows.length && instance.columns.length) {
      applyRange(instance, 0, 0, instance.rows.length - 1, instance.columns.length - 1);
      instance.active = { row: 0, col: 0 };
      instance.anchor = { row: 0, col: 0 };
      updateFormulaBar(instance);
    }
    return;
  }
  if (event.ctrlKey && event.code === "Space" && instance.active) {
    event.preventDefault();
    instance.selected.clear();
    for (let row = 0; row < instance.rows.length; row += 1) instance.selected.add(cellKey(row, instance.active.col));
    renderSelection(instance);
    return;
  }
  if (event.shiftKey && event.code === "Space" && instance.active) {
    event.preventDefault();
    instance.selected.clear();
    for (let col = 0; col < instance.columns.length; col += 1) instance.selected.add(cellKey(instance.active.row, col));
    renderSelection(instance);
    return;
  }
  if (event.ctrlKey && event.key.toLowerCase() === "z") {
    event.preventDefault();
    undo(instance);
    return;
  }
  if (event.ctrlKey && event.key.toLowerCase() === "y") {
    event.preventDefault();
    redo(instance);
    return;
  }
  if (event.key === "F2") {
    event.preventDefault();
    if (instance.active) startEdit(instance, instance.active.row, instance.active.col);
    return;
  }
  if (event.key === "Delete" || event.key === "Backspace") {
    event.preventDefault();
    clearSelectedCells(instance).catch((error) => instance.onError?.(error));
    return;
  }
  if (event.key === "Escape") {
    clipboardCut = null;
    instance.cutCells = new Set();
    instance.fillPreview = null;
    renderSelection(instance);
    return;
  }
  if (event.key === "Enter") {
    event.preventDefault();
    if (event.shiftKey) moveActive(instance, -1, 0);
    else moveActive(instance, 1, 0);
    return;
  }
  if (event.key === "Tab") {
    event.preventDefault();
    moveActive(instance, 0, event.shiftKey ? -1 : 1);
    return;
  }
  if (event.key === "Home") {
    event.preventDefault();
    setActiveCell(instance, event.ctrlKey ? 0 : instance.active?.row || 0, 0, { shift: event.shiftKey, keepAnchor: event.shiftKey });
    return;
  }
  if (event.key === "End") {
    event.preventDefault();
    setActiveCell(instance, event.ctrlKey ? instance.rows.length - 1 : instance.active?.row || 0, instance.columns.length - 1, { shift: event.shiftKey, keepAnchor: event.shiftKey });
    return;
  }
  if (event.key === "PageDown") {
    event.preventDefault();
    moveActive(instance, 18, 0, { shift: event.shiftKey });
    return;
  }
  if (event.key === "PageUp") {
    event.preventDefault();
    moveActive(instance, -18, 0, { shift: event.shiftKey });
    return;
  }
  const arrows = {
    ArrowUp: [-1, 0],
    ArrowDown: [1, 0],
    ArrowLeft: [0, -1],
    ArrowRight: [0, 1],
  };
  if (arrows[event.key]) {
    event.preventDefault();
    if (event.ctrlKey || event.metaKey) {
      jumpActive(instance, event.key, { shift: event.shiftKey });
      return;
    }
    const [rowDelta, colDelta] = arrows[event.key];
    moveActive(instance, rowDelta, colDelta, { shift: event.shiftKey });
    return;
  }
  if (!event.ctrlKey && !event.metaKey && !event.altKey && event.key.length === 1 && instance.active) {
    const column = instance.columns[instance.active.col];
    if (isColumnEditable(column)) {
      event.preventDefault();
      startEdit(instance, instance.active.row, instance.active.col, event.key);
    }
  }
}

function clearGridFilters(instance) {
  instance.filters = {};
  instance.sort = null;
  closeFilterMenu(instance);
  refreshRows(instance);
  renderGrid(instance, { preserveScroll: true });
}

function handleMouseDown(event, instance) {
  activeInstance = instance;
  instance.container.focus({ preventScroll: true });

  const fillHandle = event.target.closest(".excel-fill-handle");
  if (fillHandle) {
    const source = selectedBounds(instance);
    if (source) {
      fillState = { instance, source, target: source };
      instance.fillPreview = source;
      startEdgeAutoScroll(fillState, event);
    }
    event.preventDefault();
    event.stopPropagation();
    return;
  }

  const filterButton = event.target.closest(".excel-filter-btn");
  if (filterButton) {
    event.preventDefault();
    event.stopPropagation();
    openFilterMenu(instance, Number(filterButton.dataset.filterCol), filterButton);
    return;
  }

  if (instance.editing && !event.target.closest(".excel-cell-editor")) {
    commitEdit(instance).catch((error) => instance.onError?.(error));
  }

  const colResize = event.target.closest(".excel-col-resizer");
  if (colResize) {
    const col = Number(colResize.closest("[data-col-select]")?.dataset.colSelect);
    resizeState = {
      type: "col",
      instance,
      col,
      startX: event.clientX,
      startWidth: instance.colWidths[instance.columns[col].id] || defaultColumnWidth(instance.columns[col]),
    };
    event.preventDefault();
    return;
  }

  const rowResize = event.target.closest(".excel-row-resizer");
  if (rowResize) {
    const row = Number(rowResize.closest("[data-row-select]")?.dataset.rowSelect);
    resizeState = {
      type: "row",
      instance,
      row,
      startY: event.clientY,
      startHeight: instance.rowHeights[row] || 30,
    };
    event.preventDefault();
    return;
  }

  if (event.target.closest(".excel-corner, .excel-field-corner")) {
    if (instance.rows.length && instance.columns.length) {
      applyRange(instance, 0, 0, instance.rows.length - 1, instance.columns.length - 1);
      instance.active = { row: 0, col: 0 };
      instance.anchor = { row: 0, col: 0 };
      updateFormulaBar(instance);
    }
    event.preventDefault();
    return;
  }

  const colHeader = event.target.closest("[data-col-select]");
  if (colHeader && !event.target.closest(".excel-col-resizer")) {
    const col = Number(colHeader.dataset.colSelect);
    const startCol = event.shiftKey && instance.active ? Math.min(instance.active.col, col) : col;
    const endCol = event.shiftKey && instance.active ? Math.max(instance.active.col, col) : col;
    if (!event.ctrlKey && !event.metaKey) instance.selected.clear();
    for (let selectedCol = startCol; selectedCol <= endCol; selectedCol += 1) {
      for (let row = 0; row < instance.rows.length; row += 1) instance.selected.add(cellKey(row, selectedCol));
    }
    setActiveCell(instance, 0, col, { keepSelection: true });
    event.preventDefault();
    return;
  }

  const rowHeader = event.target.closest("[data-row-select]");
  if (rowHeader && !event.target.closest(".excel-row-resizer")) {
    const row = Number(rowHeader.dataset.rowSelect);
    const startRow = event.shiftKey && instance.active ? Math.min(instance.active.row, row) : row;
    const endRow = event.shiftKey && instance.active ? Math.max(instance.active.row, row) : row;
    if (!event.ctrlKey && !event.metaKey) instance.selected.clear();
    for (let selectedRow = startRow; selectedRow <= endRow; selectedRow += 1) {
      for (let col = 0; col < instance.columns.length; col += 1) instance.selected.add(cellKey(selectedRow, col));
    }
    setActiveCell(instance, row, 0, { keepSelection: true });
    event.preventDefault();
    return;
  }

  const cell = event.target.closest(".excel-cell");
  if (!cell) return;
  const row = Number(cell.dataset.row);
  const col = Number(cell.dataset.col);

  if (event.target.closest("button, select, input, textarea, a")) {
    setActiveCell(instance, row, col);
    return;
  }

  if (event.shiftKey && instance.active) {
    setActiveCell(instance, row, col, { shift: true, keepAnchor: true });
  } else if (event.ctrlKey || event.metaKey) {
    const key = cellKey(row, col);
    if (instance.selected.has(key)) instance.selected.delete(key);
    else instance.selected.add(key);
    setActiveCell(instance, row, col, { keepSelection: true });
  } else {
    setActiveCell(instance, row, col);
    dragState = { instance, startRow: row, startCol: col };
    startEdgeAutoScroll(dragState, event);
  }
  event.preventDefault();
}

function closeFilterMenu(instance) {
  instance.filterMenu?.remove();
  instance.filterMenu = null;
  instance.container.querySelector(".excel-filter-menu")?.remove();
  if (instance.closeFilterMenuOnOutside) {
    document.removeEventListener("mousedown", instance.closeFilterMenuOnOutside, { capture: true });
  }
}

function filterOptions(instance, column) {
  const rows = instance.sourceRows.filter((row) => rowPassesFilters(instance, row, column.id));
  const map = new Map();
  rows.forEach((row) => {
    const value = filterDisplayValue(column, row);
    const key = filterKey(value);
    if (!map.has(key)) {
      const date = parseFilterDate(value);
      map.set(key, {
        key,
        label: date ? date.toLocaleDateString("pt-BR") : filterLabel(value),
        search: normalizeFilterText(value),
        date,
      });
    }
  });
  return [...map.values()].sort((a, b) => {
    if (a.key === EMPTY_FILTER_KEY) return 1;
    if (b.key === EMPTY_FILTER_KEY) return -1;
    if (a.date && b.date) return a.date.getTime() - b.date.getTime();
    return a.label.localeCompare(b.label, "pt-BR", { numeric: true, sensitivity: "base" });
  });
}

function openFilterMenu(instance, col, button) {
  closeFilterMenu(instance);
  const column = instance.columns[col];
  if (!column || column.type === "action") return;
  const options = filterOptions(instance, column);
  const dateTree = dateTreeOptions(options);
  const optionKeys = filterKeySet(options, dateTree);
  const current = instance.filters[column.id] instanceof Set
    ? new Set([...instance.filters[column.id]].filter((key) => optionKeys.has(key)))
    : new Set(options.map((option) => option.key));
  let draft = new Set(current);
  const collapsedDateNodes = initialCollapsedDateNodes(dateTree);
  const menu = document.createElement("div");
  menu.className = "excel-filter-menu";
  menu.innerHTML = `
    <div class="excel-filter-actions">
      <button type="button" data-sort="asc">Classificar A a Z</button>
      <button type="button" data-sort="desc">Classificar Z a A</button>
      <button type="button" data-clear ${instance.filters[column.id] ? "" : "disabled"}>Limpar filtro</button>
    </div>
    <input class="excel-filter-search" type="search" placeholder="Pesquisar">
    <label class="excel-filter-select-all">
      <input type="checkbox" data-select-all>
      <span>Selecionar tudo</span>
    </label>
    <div class="excel-filter-values"></div>
    <div class="excel-filter-footer">
      <button type="button" class="ghost-btn" data-cancel>Cancelar</button>
      <button type="button" class="primary-btn" data-apply>OK</button>
    </div>
  `;
  const host = button.closest("dialog[open]") || document.body;
  host.appendChild(menu);
  instance.filterMenu = menu;

  const values = menu.querySelector(".excel-filter-values");
  const search = menu.querySelector(".excel-filter-search");
  const selectAll = menu.querySelector("[data-select-all]");

  function syncSelectAll() {
    const selected = selectedOptionCount(options, draft);
    selectAll.checked = options.length > 0 && selected === options.length;
    selectAll.indeterminate = selected > 0 && selected < options.length;
  }

  function renderOptions() {
    const query = normalizeFilterText(search.value);
    if (dateTree && !query) {
      values.innerHTML = renderDateTree(dateTree, draft, collapsedDateNodes);
      applyIndeterminateStates(values);
      return;
    }
    values.innerHTML = options
      .filter((option) => !query || option.search.includes(query) || normalizeFilterText(option.label).includes(query))
      .map((option) => `
        <label class="excel-filter-option">
          <input type="checkbox" value="${escapeHtml(option.key)}" ${isOptionSelected(option, draft) ? "checked" : ""}>
          <span>${escapeHtml(option.label)}</span>
        </label>
      `).join("") || `<div class="excel-filter-empty">Nenhum valor encontrado.</div>`;
  }

  function searchedOptionKeys() {
    const query = normalizeFilterText(search.value);
    if (!query) return null;
    return options
      .filter((option) => option.search.includes(query) || normalizeFilterText(option.label).includes(query))
      .map((option) => option.key);
  }

  function rerender() {
    refreshRows(instance);
    renderGrid(instance, { preserveScroll: true });
  }

  renderOptions();
  syncSelectAll();
  positionFilterMenu(menu, button, instance, host);

  menu.querySelector("[data-sort='asc']").addEventListener("click", () => {
    instance.sort = { columnId: column.id, dir: 1 };
    closeFilterMenu(instance);
    rerender();
  });
  menu.querySelector("[data-sort='desc']").addEventListener("click", () => {
    instance.sort = { columnId: column.id, dir: -1 };
    closeFilterMenu(instance);
    rerender();
  });
  menu.querySelector("[data-clear]").addEventListener("click", () => {
    delete instance.filters[column.id];
    closeFilterMenu(instance);
    rerender();
  });
  menu.querySelector("[data-cancel]").addEventListener("click", () => closeFilterMenu(instance));
  menu.querySelector("[data-apply]").addEventListener("click", () => {
    if (selectedOptionCount(options, draft) === options.length) delete instance.filters[column.id];
    else instance.filters[column.id] = new Set(draft);
    closeFilterMenu(instance);
    rerender();
  });
  search.addEventListener("input", () => {
    const keys = searchedOptionKeys();
    if (keys) draft = new Set(keys);
    renderOptions();
    syncSelectAll();
  });
  selectAll.addEventListener("change", () => {
    draft = selectAll.checked ? new Set(options.map((option) => option.key)) : new Set();
    renderOptions();
    syncSelectAll();
  });
  values.addEventListener("change", (event) => {
    const input = event.target.closest("input[type='checkbox']");
    if (!input) return;
    if (input.dataset.dateToken) {
      const keys = input.dataset.dateKeys.split("|").filter(Boolean);
      const childTokens = input.dataset.dateChildTokens.split("|").filter(Boolean);
      if (input.checked) {
        draft.add(input.dataset.dateToken);
        if (!isSameSingleDateKey(input.dataset.dateToken, keys)) keys.forEach((key) => draft.delete(key));
        childTokens.forEach((token) => draft.delete(token));
      } else {
        materializeSelectedDateParents(draft, input.dataset.dateToken, dateTree);
        draft.delete(input.dataset.dateToken);
        removeParentDateTokens(draft, input.dataset.dateToken);
        keys.forEach((key) => draft.delete(key));
        childTokens.forEach((token) => draft.delete(token));
      }
      renderOptions();
    } else if (input.checked) draft.add(input.value);
    else draft.delete(input.value);
    syncSelectAll();
  });
  values.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-date-toggle]");
    if (!toggle) return;
    event.preventDefault();
    event.stopPropagation();
    const key = toggle.dataset.dateToggle;
    if (collapsedDateNodes.has(key)) collapsedDateNodes.delete(key);
    else collapsedDateNodes.add(key);
    renderOptions();
  });

  instance.closeFilterMenuOnOutside = (event) => {
    if (event.target.closest(".excel-filter-menu") || event.target.closest(".excel-filter-btn")) return;
    closeFilterMenu(instance);
  };
  window.setTimeout(() => document.addEventListener("mousedown", instance.closeFilterMenuOnOutside, { capture: true }), 0);
}

function parseFilterDate(value) {
  if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
  const text = String(value ?? "").trim();
  if (!text || text === "Vazio") return null;
  const br = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})(?:\s|$)/);
  if (br) {
    const year = Number(br[3].length === 2 ? `20${br[3]}` : br[3]);
    const date = new Date(year, Number(br[2]) - 1, Number(br[1]));
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const iso = text.match(/^(\d{4})-(\d{1,2})-(\d{1,2})(?:T|\s|$)/);
  if (iso) {
    const date = new Date(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3]));
    return Number.isNaN(date.getTime()) ? null : date;
  }
  return null;
}

function dateKey(date) {
  return `${DATE_FILTER_PREFIX}${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function monthToken(year, monthIndex) {
  return `${MONTH_FILTER_PREFIX}${year}-${String(Number(monthIndex) + 1).padStart(2, "0")}`;
}

function yearToken(year) {
  return `${YEAR_FILTER_PREFIX}${year}`;
}

function dateTreeOptions(options) {
  const dated = options.filter((option) => option.date);
  if (!dated.length || dated.length < Math.max(3, Math.ceil(options.length * 0.6))) return null;
  const years = new Map();
  const empty = options.find((option) => option.key === EMPTY_FILTER_KEY);
  dated.forEach((option) => {
    const year = String(option.date.getFullYear());
    const month = option.date.getMonth();
    const day = String(option.date.getDate()).padStart(2, "0");
    if (!years.has(year)) years.set(year, new Map());
    const months = years.get(year);
    if (!months.has(month)) months.set(month, new Map());
    const days = months.get(month);
    if (!days.has(day)) days.set(day, []);
    days.get(day).push(option);
  });
  return { years, empty };
}

function filterKeySet(options, dateTree) {
  const keys = new Set(options.map((option) => option.key));
  if (!dateTree) return keys;
  dateTree.years.forEach((months, year) => {
    keys.add(yearToken(year));
    months.forEach((_days, month) => keys.add(monthToken(year, month)));
  });
  return keys;
}

function initialCollapsedDateNodes(tree) {
  const collapsed = new Set();
  if (!tree) return collapsed;
  tree.years.forEach((months, year) => {
    const yearKey = `year:${year}`;
    collapsed.add(yearKey);
    months.forEach((_days, month) => collapsed.add(`${yearKey}:month:${month}`));
  });
  return collapsed;
}

function renderDateTree(tree, draft, collapsedNodes = new Set()) {
  const parts = [];
  [...tree.years.entries()]
    .sort(([a], [b]) => Number(a) - Number(b))
    .forEach(([year, months]) => {
      const yearKey = `year:${year}`;
      const yearCollapsed = collapsedNodes.has(yearKey);
      parts.push(renderDateTreeOption({
        label: year,
        keys: keysFromMonths(months),
        draft,
        level: "year",
        toggleKey: yearKey,
        collapsed: yearCollapsed,
        token: yearToken(year),
        childTokens: [...months.keys()].map((month) => monthToken(year, month)),
      }));
      if (yearCollapsed) return;
      [...months.entries()]
        .sort(([a], [b]) => a - b)
        .forEach(([month, days]) => {
          const monthKey = `${yearKey}:month:${month}`;
          const monthCollapsed = collapsedNodes.has(monthKey);
          parts.push(renderDateTreeOption({
            label: MONTH_NAMES[month] || String(month + 1).padStart(2, "0"),
            keys: keysFromDays(days),
            draft,
            level: "month",
            toggleKey: monthKey,
            collapsed: monthCollapsed,
            token: monthToken(year, month),
            childTokens: [],
          }));
          if (monthCollapsed) return;
          [...days.entries()]
            .sort(([a], [b]) => Number(a) - Number(b))
            .forEach(([day, options]) => {
              parts.push(renderDateTreeOption({
                label: day,
                keys: options.map((option) => option.key),
                draft,
                level: "day",
                token: options[0]?.key || "",
                childTokens: [],
              }));
            });
        });
    });
  if (tree.empty) {
    parts.push(renderDateTreeOption({
      label: "Vazio",
      keys: [tree.empty.key],
      draft,
      level: "empty",
      token: tree.empty.key,
      childTokens: [],
    }));
  }
  return parts.join("") || `<div class="excel-filter-empty">Nenhum valor encontrado.</div>`;
}

function renderDateTreeOption({ label, keys, draft, level, token = "", childTokens = [], toggleKey = "", collapsed = false }) {
  const selected = keys.filter((key) => isDateKeySelected(key, draft)).length;
  const checked = selected === keys.length;
  const indeterminate = selected > 0 && selected < keys.length;
  const toggle = toggleKey
    ? `<button class="excel-date-tree-toggle" type="button" data-date-toggle="${escapeHtml(toggleKey)}">${collapsed ? "+" : "-"}</button>`
    : `<span class="excel-date-tree-spacer"></span>`;
  return `
    <label class="excel-filter-option excel-date-tree ${escapeHtml(level)}">
      ${toggle}
      <input
        type="checkbox"
        data-date-token="${escapeHtml(token)}"
        data-date-keys="${escapeHtml(keys.join("|"))}"
        data-date-child-tokens="${escapeHtml(childTokens.join("|"))}"
        ${checked ? "checked" : ""}
        ${indeterminate ? "data-indeterminate=\"true\"" : ""}
      >
      <span>${escapeHtml(label)}</span>
    </label>
  `;
}

function keysFromMonths(months) {
  const keys = [];
  months.forEach((days) => keys.push(...keysFromDays(days)));
  return keys;
}

function keysFromDays(days) {
  const keys = [];
  days.forEach((options) => keys.push(...options.map((option) => option.key)));
  return keys;
}

function materializeSelectedDateParents(draft, token, tree) {
  if (!tree) return;
  if (String(token).startsWith(MONTH_FILTER_PREFIX)) {
    const [year, monthText] = String(token).slice(MONTH_FILTER_PREFIX.length).split("-");
    materializeYearToken(draft, tree, year);
    materializeMonthToken(draft, tree, year, Number(monthText) - 1);
    return;
  }
  const date = String(token).startsWith(DATE_FILTER_PREFIX)
    ? parseFilterDate(String(token).slice(DATE_FILTER_PREFIX.length))
    : null;
  if (!date) return;
  const year = String(date.getFullYear());
  const month = date.getMonth();
  materializeYearToken(draft, tree, year);
  materializeMonthToken(draft, tree, year, month);
}

function isSameSingleDateKey(token, keys) {
  return keys.length === 1 && keys[0] === token;
}

function materializeYearToken(draft, tree, year) {
  const token = yearToken(year);
  if (!draft.has(token)) return;
  const months = tree.years.get(String(year));
  if (!months) return;
  keysFromMonths(months).forEach((key) => draft.add(key));
  draft.delete(token);
  [...months.keys()].forEach((month) => draft.delete(monthToken(year, month)));
}

function materializeMonthToken(draft, tree, year, month) {
  const token = monthToken(year, month);
  if (!draft.has(token)) return;
  const days = tree.years.get(String(year))?.get(Number(month));
  if (!days) return;
  keysFromDays(days).forEach((key) => draft.add(key));
  draft.delete(token);
}

function selectedOptionCount(options, draft) {
  return options.filter((option) => isOptionSelected(option, draft)).length;
}

function isOptionSelected(option, draft) {
  if (!option.date) return draft.has(option.key);
  return isDateKeySelected(option.key, draft);
}

function isDateKeySelected(key, draft) {
  if (draft.has(key)) return true;
  if (!String(key).startsWith(DATE_FILTER_PREFIX)) return false;
  const date = parseFilterDate(String(key).slice(DATE_FILTER_PREFIX.length));
  if (!date) return false;
  return draft.has(monthToken(date.getFullYear(), date.getMonth()))
    || draft.has(yearToken(date.getFullYear()));
}

function removeParentDateTokens(draft, token) {
  if (String(token).startsWith(MONTH_FILTER_PREFIX)) {
    const year = String(token).slice(MONTH_FILTER_PREFIX.length).split("-")[0];
    draft.delete(yearToken(year));
  }
  if (String(token).startsWith(DATE_FILTER_PREFIX)) {
    const date = parseFilterDate(String(token).slice(DATE_FILTER_PREFIX.length));
    if (!date) return;
    draft.delete(monthToken(date.getFullYear(), date.getMonth()));
    draft.delete(yearToken(date.getFullYear()));
  }
}

function applyIndeterminateStates(root) {
  root.querySelectorAll("input[data-indeterminate='true']").forEach((input) => {
    input.indeterminate = true;
  });
}

function positionFilterMenu(menu, button, instance, host = document.body) {
  const buttonRect = button.getBoundingClientRect();
  const headerRect = (button.closest(".excel-field-header") || button).getBoundingClientRect();
  const width = Math.min(260, Math.max(210, window.innerWidth - 24));
  const left = Math.max(8, Math.min(buttonRect.left, window.innerWidth - width - 8));
  const spaceBelow = window.innerHeight - headerRect.bottom - 10;
  const spaceAbove = headerRect.top - 10;
  const openAbove = spaceBelow < 260 && spaceAbove > spaceBelow;
  const maxHeight = Math.max(230, Math.min(420, openAbove ? spaceAbove : spaceBelow));
  const top = openAbove ? Math.max(8, headerRect.top - maxHeight - 8) : Math.min(headerRect.bottom + 8, window.innerHeight - maxHeight - 8);
  menu.style.width = `${width}px`;
  menu.style.position = "fixed";
  if (host instanceof HTMLDialogElement) {
    const hostRect = host.getBoundingClientRect();
    menu.style.position = "absolute";
    menu.style.left = `${Math.max(8, left - hostRect.left + host.scrollLeft)}px`;
    menu.style.top = `${Math.max(8, top - hostRect.top + host.scrollTop)}px`;
    menu.style.maxHeight = `${maxHeight}px`;
    menu.style.height = `${Math.min(maxHeight, Math.max(220, menu.scrollHeight))}px`;
    menu.style.transform = "none";
    return;
  }
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
  menu.style.maxHeight = `${maxHeight}px`;
  menu.style.height = `${Math.min(maxHeight, Math.max(220, menu.scrollHeight))}px`;
  menu.style.transform = "none";
}

function fillPreviewRange(source, row, col) {
  const rowDistance = row < source.rowStart
    ? source.rowStart - row
    : Math.max(0, row - source.rowEnd);
  const colDistance = col < source.colStart
    ? source.colStart - col
    : Math.max(0, col - source.colEnd);
  if (rowDistance >= colDistance) {
    return {
      rowStart: Math.min(source.rowStart, row),
      rowEnd: Math.max(source.rowEnd, row),
      colStart: source.colStart,
      colEnd: source.colEnd,
    };
  }
  return {
    rowStart: source.rowStart,
    rowEnd: source.rowEnd,
    colStart: Math.min(source.colStart, col),
    colEnd: Math.max(source.colEnd, col),
  };
}

function sourceValueForFill(instance, source, row, col) {
  const sourceHeight = source.rowEnd - source.rowStart + 1;
  const sourceWidth = source.colEnd - source.colStart + 1;
  const sourceRow = source.rowStart + ((((row - source.rowStart) % sourceHeight) + sourceHeight) % sourceHeight);
  const sourceCol = source.colStart + ((((col - source.colStart) % sourceWidth) + sourceWidth) % sourceWidth);
  return valueFor(instance.columns[sourceCol], instance.rows[sourceRow]);
}

function numericSeriesValue(instance, source, row, col) {
  if (source.colStart === source.colEnd && source.rowEnd - source.rowStart === 1 && col === source.colStart) {
    const first = numericCellValue({ value: valueFor(instance.columns[col], instance.rows[source.rowStart]), column: instance.columns[col] });
    const second = numericCellValue({ value: valueFor(instance.columns[col], instance.rows[source.rowEnd]), column: instance.columns[col] });
    if (first !== null && second !== null) {
      const step = second - first;
      return row > source.rowEnd
        ? second + step * (row - source.rowEnd)
        : first - step * (source.rowStart - row);
    }
  }
  if (source.rowStart === source.rowEnd && source.colEnd - source.colStart === 1 && row === source.rowStart) {
    const first = numericCellValue({ value: valueFor(instance.columns[source.colStart], instance.rows[row]), column: instance.columns[source.colStart] });
    const second = numericCellValue({ value: valueFor(instance.columns[source.colEnd], instance.rows[row]), column: instance.columns[source.colEnd] });
    if (first !== null && second !== null) {
      const step = second - first;
      return col > source.colEnd
        ? second + step * (col - source.colEnd)
        : first - step * (source.colStart - col);
    }
  }
  return null;
}

async function commitFill(instance, source, target) {
  if (!source || !target) return;
  let changed = false;
  for (let row = target.rowStart; row <= target.rowEnd; row += 1) {
    for (let col = target.colStart; col <= target.colEnd; col += 1) {
      const insideSource = row >= source.rowStart && row <= source.rowEnd && col >= source.colStart && col <= source.colEnd;
      const column = instance.columns[col];
      if (insideSource || !isColumnEditable(column)) continue;
      const seriesValue = numericSeriesValue(instance, source, row, col);
      const nextValue = seriesValue ?? sourceValueForFill(instance, source, row, col);
      const saved = await saveCell(instance, row, col, nextValue, { pushHistory: true, render: false });
      changed = saved || changed;
      if (!saved) break;
    }
  }
  instance.fillPreview = null;
  if (changed) {
    refreshRows(instance);
    renderGrid(instance, { preserveScroll: true });
    applyRange(instance, target.rowStart, target.colStart, target.rowEnd, target.colEnd);
  } else {
    renderSelection(instance);
  }
}

function edgeScrollVelocity(position, start, end) {
  const zone = 46;
  const maxSpeed = 24;
  if (position < start + zone) {
    return -Math.ceil(maxSpeed * clamp((start + zone - position) / zone, 0.18, 1));
  }
  if (position > end - zone) {
    return Math.ceil(maxSpeed * clamp((position - (end - zone)) / zone, 0.18, 1));
  }
  return 0;
}

function updateDragTargetAtPointer(state) {
  const viewport = state.instance.container.querySelector(".excel-sheet-viewport");
  if (!viewport || !Number.isFinite(state.pointerX) || !Number.isFinite(state.pointerY)) return;
  const rect = viewport.getBoundingClientRect();
  const safeLeft = rect.left + 44;
  const safeRight = Math.max(safeLeft + 1, rect.right - 10);
  const safeTop = rect.top + 61;
  const safeBottom = Math.max(safeTop + 1, rect.bottom - 10);
  const pointX = clamp(state.pointerX, safeLeft, safeRight);
  const pointY = clamp(state.pointerY, safeTop, safeBottom);
  const cell = document.elementFromPoint(pointX, pointY)?.closest?.(".excel-cell");
  if (!cell || !state.instance.container.contains(cell)) return;
  const row = Number(cell.dataset.row);
  const col = Number(cell.dataset.col);
  if (!Number.isFinite(row) || !Number.isFinite(col)) return;
  if (state.lastRow === row && state.lastCol === col) return;
  state.lastRow = row;
  state.lastCol = col;

  if (state === fillState) {
    state.target = fillPreviewRange(state.source, row, col);
    state.instance.fillPreview = state.target;
    renderSelection(state.instance);
    return;
  }
  applyRange(state.instance, state.startRow, state.startCol, row, col);
}

function edgeAutoScrollTick() {
  const state = fillState || dragState;
  if (!state) {
    edgeScrollFrame = 0;
    return;
  }
  const viewport = state.instance.container.querySelector(".excel-sheet-viewport");
  if (!viewport) {
    edgeScrollFrame = requestAnimationFrame(edgeAutoScrollTick);
    return;
  }
  if (!state.dragging) {
    edgeScrollFrame = requestAnimationFrame(edgeAutoScrollTick);
    return;
  }
  const rect = viewport.getBoundingClientRect();
  const horizontal = edgeScrollVelocity(state.pointerX, rect.left + 42, rect.right - 14);
  const vertical = edgeScrollVelocity(state.pointerY, rect.top + 59, rect.bottom - 14);
  if (horizontal || vertical) {
    viewport.scrollLeft += horizontal;
    viewport.scrollTop += vertical;
  }
  updateDragTargetAtPointer(state);
  edgeScrollFrame = requestAnimationFrame(edgeAutoScrollTick);
}

function startEdgeAutoScroll(state, event) {
  state.originX = event.clientX;
  state.originY = event.clientY;
  state.pointerX = event.clientX;
  state.pointerY = event.clientY;
  state.dragging = false;
  if (!edgeScrollFrame) edgeScrollFrame = requestAnimationFrame(edgeAutoScrollTick);
}

function stopEdgeAutoScroll() {
  if (edgeScrollFrame) cancelAnimationFrame(edgeScrollFrame);
  edgeScrollFrame = 0;
}

function handleMouseOver(event) {
  const cell = event.target.closest(".excel-cell");
  if (fillState) {
    if (!fillState.dragging) return;
    if (!cell || !fillState.instance.container.contains(cell)) return;
    fillState.target = fillPreviewRange(
      fillState.source,
      Number(cell.dataset.row),
      Number(cell.dataset.col),
    );
    fillState.instance.fillPreview = fillState.target;
    renderSelection(fillState.instance);
    return;
  }
  if (dragState) {
    if (!dragState.dragging) return;
    if (!cell || !dragState.instance.container.contains(cell)) return;
    applyRange(
      dragState.instance,
      dragState.startRow,
      dragState.startCol,
      Number(cell.dataset.row),
      Number(cell.dataset.col),
    );
  }
}

function handleMouseMove(event) {
  const edgeState = fillState || dragState;
  if (edgeState) {
    event.preventDefault();
    edgeState.pointerX = event.clientX;
    edgeState.pointerY = event.clientY;
    if (Math.hypot(event.clientX - edgeState.originX, event.clientY - edgeState.originY) >= 4) {
      edgeState.dragging = true;
      updateDragTargetAtPointer(edgeState);
    }
  }
  if (!resizeState) return;
  const { instance } = resizeState;
  if (resizeState.type === "col") {
    const column = instance.columns[resizeState.col];
    instance.colWidths[column.id] = Math.max(64, resizeState.startWidth + event.clientX - resizeState.startX);
    applySizes(instance);
  } else {
    instance.rowHeights[resizeState.row] = Math.max(26, resizeState.startHeight + event.clientY - resizeState.startY);
    applySizes(instance);
  }
}

function autoFitColumn(instance, col) {
  const column = instance.columns[col];
  const sample = instance.rows.slice(0, 80).map((row) => normalizeText(column.display ? column.display(row) : valueFor(column, row)));
  const longest = [column.title, ...sample].reduce((max, value) => Math.max(max, normalizeText(value).length), 0);
  instance.colWidths[column.id] = Math.min(360, Math.max(84, longest * 8 + 32));
  saveStoredColumnWidths(instance);
  applySizes(instance);
}

function applySizes(instance) {
  instance.columns.forEach((column, col) => {
    const width = instance.colWidths[column.id] || defaultColumnWidth(column);
    instance.container.querySelectorAll(`[data-col="${col}"], [data-col-select="${col}"]`).forEach((node) => {
      node.style.width = `${width}px`;
      node.style.minWidth = `${width}px`;
      node.style.maxWidth = `${width}px`;
    });
  });
  Object.entries(instance.rowHeights).forEach(([row, height]) => {
    instance.container.querySelectorAll(`[data-row="${row}"], [data-row-select="${row}"]`).forEach((node) => {
      node.style.height = `${height}px`;
    });
  });
  applyFrozenColumns(instance);
  applyZoom(instance);
  renderSelectionOutlines(instance);
}

function applyZoom(instance) {
  const table = instance.container.querySelector(".excel-table");
  if (table) table.style.zoom = `${instance.zoom || 100}%`;
  const zoomLabel = instance.container.querySelector("[data-grid-zoom-label]");
  if (zoomLabel) zoomLabel.textContent = `${instance.zoom || 100}%`;
}

function applyFrozenColumns(instance) {
  let left = 42;
  instance.columns.forEach((column, col) => {
    const nodes = instance.container.querySelectorAll(`[data-col="${col}"], [data-col-select="${col}"]`);
    const frozen = col < instance.frozenCount;
    nodes.forEach((node) => {
      node.classList.toggle("excel-frozen-col", frozen);
      node.style.left = frozen ? `${left}px` : "";
    });
    if (frozen) left += instance.colWidths[column.id] || defaultColumnWidth(column);
  });
}

function changeZoom(instance, delta) {
  instance.zoom = clamp((instance.zoom || 100) + delta, 60, 160);
  saveStoredLayout(instance);
  applyZoom(instance);
  renderSelectionOutlines(instance);
}

function resetGridLayout(instance) {
  instance.columnOrder = (instance.allColumns || []).map((column) => column.id);
  instance.hiddenColumns = new Set();
  instance.frozenCount = 0;
  instance.zoom = 100;
  instance.colWidths = Object.fromEntries((instance.allColumns || []).map((column) => [column.id, defaultColumnWidth(column)]));
  instance.rowHeights = {};
  applyColumnPreferences(instance);
  saveStoredColumnWidths(instance);
  saveStoredLayout(instance);
  renderGrid(instance, { preserveScroll: true });
}

function closeColumnsMenu(instance) {
  instance.columnsMenu?.remove();
  instance.columnsMenu = null;
}

function moveColumn(instance, columnId, direction) {
  const index = instance.columnOrder.indexOf(columnId);
  const target = index + direction;
  if (index < 0 || target < 0 || target >= instance.columnOrder.length) return;
  const [moved] = instance.columnOrder.splice(index, 1);
  instance.columnOrder.splice(target, 0, moved);
  applyColumnPreferences(instance);
  saveStoredLayout(instance);
  renderGrid(instance, { preserveScroll: true });
}

function openColumnsMenu(instance, button) {
  closeColumnsMenu(instance);
  const menu = document.createElement("div");
  menu.className = "excel-columns-menu";
  menu.innerHTML = `
    <div class="excel-columns-menu-header">
      <strong>Colunas</strong>
      <button type="button" data-columns-close aria-label="Fechar">x</button>
    </div>
    <div class="excel-columns-list">
      ${(instance.columnOrder || []).map((columnId) => {
        const column = instance.allColumns.find((item) => item.id === columnId);
        if (!column) return "";
        const locked = column.type === "action";
        return `
          <div class="excel-column-option" data-column-id="${escapeHtml(column.id)}">
            <label>
              <input type="checkbox" data-column-visible ${!instance.hiddenColumns.has(column.id) ? "checked" : ""} ${locked ? "disabled" : ""}>
              <span>${escapeHtml(column.title)}</span>
            </label>
            <div class="excel-column-order-actions">
              <button type="button" data-column-move="-1" title="Mover para esquerda">&#8592;</button>
              <button type="button" data-column-move="1" title="Mover para direita">&#8594;</button>
            </div>
          </div>
        `;
      }).join("")}
    </div>
    <button class="excel-columns-reset" type="button" data-columns-reset>Restaurar layout</button>
  `;
  document.body.appendChild(menu);
  instance.columnsMenu = menu;
  const rect = button.getBoundingClientRect();
  menu.style.left = `${Math.max(8, Math.min(window.innerWidth - 318, rect.left))}px`;
  menu.style.top = `${Math.max(8, Math.min(window.innerHeight - menu.offsetHeight - 8, rect.bottom + 6))}px`;

  menu.addEventListener("click", (event) => {
    if (event.target.closest("[data-columns-close]")) closeColumnsMenu(instance);
    if (event.target.closest("[data-columns-reset]")) {
      closeColumnsMenu(instance);
      resetGridLayout(instance);
    }
    const moveButton = event.target.closest("[data-column-move]");
    if (moveButton) {
      const option = moveButton.closest("[data-column-id]");
      moveColumn(instance, option.dataset.columnId, Number(moveButton.dataset.columnMove));
      openColumnsMenu(instance, instance.container.querySelector("[data-grid-action='columns']"));
    }
  });
  menu.addEventListener("change", (event) => {
    const checkbox = event.target.closest("[data-column-visible]");
    if (!checkbox) return;
    const columnId = checkbox.closest("[data-column-id]").dataset.columnId;
    if (checkbox.checked) instance.hiddenColumns.delete(columnId);
    else instance.hiddenColumns.add(columnId);
    applyColumnPreferences(instance);
    saveStoredLayout(instance);
    renderGrid(instance, { preserveScroll: true });
    openColumnsMenu(instance, instance.container.querySelector("[data-grid-action='columns']"));
  });
}

function toggleFreeze(instance) {
  const activeCol = instance.active?.col ?? 0;
  instance.frozenCount = instance.frozenCount === activeCol + 1 ? 0 : activeCol + 1;
  saveStoredLayout(instance);
  applyFrozenColumns(instance);
  const label = instance.container.querySelector("[data-freeze-label]");
  if (label) label.textContent = instance.frozenCount ? `Fixadas: ${instance.frozenCount}` : "Congelar";
}

async function toolbarPaste(instance) {
  if (!navigator.clipboard?.readText) return;
  const text = await navigator.clipboard.readText();
  await pasteSelection(instance, text);
}

function handleToolbarAction(event, instance) {
  const button = event.target.closest("[data-grid-action]");
  if (!button) return;
  const action = button.dataset.gridAction;
  if (action === "undo") undo(instance);
  if (action === "redo") redo(instance);
  if (action === "copy") navigator.clipboard?.writeText(selectionText(instance));
  if (action === "cut") {
    navigator.clipboard?.writeText(selectionText(instance));
    clipboardCut = { instance, cells: selectedCellDetails(instance) };
    instance.cutCells = new Set([...instance.selected]);
    renderSelection(instance);
  }
  if (action === "paste") toolbarPaste(instance).catch((error) => instance.onError?.(error));
  if (action === "autofit") instance.columns.forEach((_column, col) => autoFitColumn(instance, col));
  if (action === "columns") openColumnsMenu(instance, button);
  if (action === "freeze") toggleFreeze(instance);
  if (action === "zoom-out") changeZoom(instance, -10);
  if (action === "zoom-in") changeZoom(instance, 10);
  if (action === "empty-create") instance.onEmptyAction?.();
  button.closest(".excel-more-menu")?.removeAttribute("open");
}

function closeContextMenu(instance) {
  instance.contextMenu?.remove();
  instance.contextMenu = null;
}

function openContextMenu(instance, event) {
  const cell = event.target.closest(".excel-cell");
  const header = event.target.closest("[data-col-select]");
  if (!cell && !header) return;
  const row = cell ? Number(cell.dataset.row) : (instance.active?.row ?? 0);
  const col = Number((cell || header).dataset.col ?? (cell || header).dataset.colSelect);
  if (cell && !instance.selected.has(cellKey(row, col))) setActiveCell(instance, row, col);
  else if (header) setActiveCell(instance, row, col, { keepSelection: true, focus: false });

  closeContextMenu(instance);
  const column = instance.columns[col];
  const menu = document.createElement("div");
  menu.className = "excel-context-menu";
  menu.innerHTML = `
    <button type="button" data-context-action="copy">Copiar <kbd>Ctrl+C</kbd></button>
    <button type="button" data-context-action="cut" ${isColumnEditable(column) ? "" : "disabled"}>Recortar <kbd>Ctrl+X</kbd></button>
    <button type="button" data-context-action="paste" ${isColumnEditable(column) ? "" : "disabled"}>Colar <kbd>Ctrl+V</kbd></button>
    <span class="excel-context-separator"></span>
    <button type="button" data-context-action="edit" ${isColumnEditable(column) ? "" : "disabled"}>Editar celula <kbd>F2</kbd></button>
    <button type="button" data-context-action="clear" ${isColumnEditable(column) ? "" : "disabled"}>Limpar conteudo <kbd>Del</kbd></button>
    <span class="excel-context-separator"></span>
    <button type="button" data-context-action="autofit">Autoajustar coluna</button>
    <button type="button" data-context-action="hide" ${column?.type === "action" ? "disabled" : ""}>Ocultar coluna</button>
    <button type="button" data-context-action="freeze">${instance.frozenCount ? "Alterar congelamento" : "Congelar ate aqui"}</button>
  `;
  document.body.appendChild(menu);
  instance.contextMenu = menu;
  menu.style.left = `${Math.min(event.clientX, window.innerWidth - menu.offsetWidth - 8)}px`;
  menu.style.top = `${Math.min(event.clientY, window.innerHeight - menu.offsetHeight - 8)}px`;
  menu.addEventListener("click", (clickEvent) => {
    const action = clickEvent.target.closest("[data-context-action]")?.dataset.contextAction;
    if (!action) return;
    if (action === "copy") navigator.clipboard?.writeText(selectionText(instance));
    if (action === "cut") {
      navigator.clipboard?.writeText(selectionText(instance));
      clipboardCut = { instance, cells: selectedCellDetails(instance) };
      instance.cutCells = new Set([...instance.selected]);
      renderSelection(instance);
    }
    if (action === "paste") toolbarPaste(instance).catch((error) => instance.onError?.(error));
    if (action === "edit") startEdit(instance, row, col);
    if (action === "clear") clearSelectedCells(instance).catch((error) => instance.onError?.(error));
    if (action === "autofit") autoFitColumn(instance, col);
    if (action === "hide" && column?.type !== "action") {
      instance.hiddenColumns.add(column.id);
      applyColumnPreferences(instance);
      saveStoredLayout(instance);
      renderGrid(instance, { preserveScroll: true });
    }
    if (action === "freeze") toggleFreeze(instance);
    closeContextMenu(instance);
  });
}

function bindInstance(instance) {
  instance.container.addEventListener("keydown", (event) => handleKeydown(event, instance));
  instance.container.addEventListener("mousedown", (event) => handleMouseDown(event, instance));
  instance.container.addEventListener("click", (event) => handleToolbarAction(event, instance));
  instance.container.addEventListener("contextmenu", (event) => {
    if (!event.target.closest(".excel-cell, [data-col-select]")) return;
    event.preventDefault();
    openContextMenu(instance, event);
  });
  instance.container.addEventListener("wheel", (event) => {
    if (!event.ctrlKey) return;
    event.preventDefault();
    changeZoom(instance, event.deltaY > 0 ? -10 : 10);
  }, { passive: false });
  instance.container.addEventListener("scroll", (event) => {
    if (!event.target.classList?.contains("excel-sheet-viewport")) return;
    if (instance.rows.length <= instance.virtualThreshold) {
      if (instance.selectionOutlineFrame) cancelAnimationFrame(instance.selectionOutlineFrame);
      instance.selectionOutlineFrame = requestAnimationFrame(() => {
        instance.selectionOutlineFrame = 0;
        renderSelectionOutlines(instance);
      });
      return;
    }
    if (instance.virtualRenderFrame) cancelAnimationFrame(instance.virtualRenderFrame);
    instance.virtualRenderFrame = requestAnimationFrame(() => {
      instance.virtualRenderFrame = 0;
      const next = renderWindowFor(instance, event.target);
      if (next.start !== instance.virtualWindow.start || next.end !== instance.virtualWindow.end) {
        renderGrid(instance, { preserveScroll: true });
      } else {
        renderSelectionOutlines(instance);
      }
    });
  }, true);
  instance.container.addEventListener("dblclick", (event) => {
    const resizer = event.target.closest(".excel-col-resizer");
    if (resizer) {
      autoFitColumn(instance, Number(resizer.closest("[data-col-select]")?.dataset.colSelect));
      return;
    }
    const cell = event.target.closest(".excel-cell");
    if (!cell) return;
    startEdit(instance, Number(cell.dataset.row), Number(cell.dataset.col));
  });
  instance.container.addEventListener("focusin", () => {
    activeInstance = instance;
    updateFormulaBar(instance);
  });
  instance.container.addEventListener("keydown", async (event) => {
    if (!event.target.classList.contains("excel-cell-editor")) return;
    if (event.key === "Tab") {
      event.preventDefault();
      event.stopPropagation();
      const editing = instance.editing ? { ...instance.editing } : null;
      const saved = await commitEdit(instance);
      if (saved && editing) moveActive(instance, 0, event.shiftKey ? -1 : 1);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const editing = instance.editing ? { ...instance.editing } : null;
      const saved = await commitEdit(instance);
      if (saved && editing) moveActive(instance, event.shiftKey ? -1 : 1, 0);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      cancelEdit(instance);
    }
  });
  instance.container.addEventListener("change", async (event) => {
    if (!event.target.classList.contains("excel-cell-editor")) return;
    if (event.target instanceof HTMLSelectElement && !event.target.multiple) {
      await commitEdit(instance);
    }
  });
  instance.container.addEventListener("focusout", (event) => {
    if (event.target.classList.contains("excel-cell-editor")) {
      window.setTimeout(() => {
        if (!instance.container.contains(document.activeElement)) commitEdit(instance);
      }, 0);
    }
  });
  instance.container.addEventListener("keydown", async (event) => {
    if (!event.target.classList.contains("excel-formula-input")) return;
    if (event.key === "Enter" && instance.active) {
      event.preventDefault();
      const { row, col } = instance.active;
      const saved = await saveCell(instance, row, col, event.target.value, { pushHistory: true });
      if (saved) moveActive(instance, event.shiftKey ? -1 : 1, 0);
    }
  });
}

document.addEventListener("mouseover", handleMouseOver);
document.addEventListener("mousemove", handleMouseMove);
document.addEventListener("mouseup", () => {
  stopEdgeAutoScroll();
  if (resizeState?.type === "col") {
    saveStoredColumnWidths(resizeState.instance);
  }
  if (resizeState?.type === "row") {
    saveStoredLayout(resizeState.instance);
  }
  if (fillState) {
    const { instance, source, target } = fillState;
    fillState = null;
    commitFill(instance, source, target).catch((error) => instance.onError?.(error));
  }
  dragState = null;
  resizeState = null;
});
document.addEventListener("mousedown", (event) => {
  instances.forEach((instance) => {
    if (!event.target.closest?.(".excel-columns-menu, [data-grid-action='columns']")) closeColumnsMenu(instance);
    if (!event.target.closest?.(".excel-context-menu")) closeContextMenu(instance);
  });
  if (!activeInstance || !(event.target instanceof Node)) return;
  if (!activeInstance.container.contains(event.target)) {
    activeInstance = null;
  }
});
window.addEventListener("resize", () => {
  instances.forEach((instance) => renderSelectionOutlines(instance));
});
window.addEventListener("blur", () => {
  stopEdgeAutoScroll();
  const fillInstance = fillState?.instance || null;
  fillState = null;
  dragState = null;
  resizeState = null;
  if (fillInstance) {
    fillInstance.fillPreview = null;
    renderSelection(fillInstance);
  }
});
function shouldUseGridClipboard(event) {
  if (!activeInstance || isInputLike(event.target)) return false;
  const activeElement = document.activeElement;
  const eventTarget = event.target instanceof Node ? event.target : null;
  return Boolean(
    (activeElement && activeInstance.container.contains(activeElement))
      || (eventTarget && activeInstance.container.contains(eventTarget)),
  );
}
document.addEventListener("copy", (event) => {
  if (!shouldUseGridClipboard(event)) return;
  copySelection(activeInstance, event.clipboardData);
  event.preventDefault();
});
document.addEventListener("cut", (event) => {
  if (!shouldUseGridClipboard(event)) return;
  copySelection(activeInstance, event.clipboardData);
  clipboardCut = { instance: activeInstance, cells: selectedCellDetails(activeInstance) };
  activeInstance.cutCells = new Set([...activeInstance.selected]);
  renderSelection(activeInstance);
  event.preventDefault();
});
document.addEventListener("paste", (event) => {
  if (!shouldUseGridClipboard(event)) return;
  pasteSelection(activeInstance, event.clipboardData.getData("text/plain"));
  event.preventDefault();
});

export function createExcelGrid(container, options = {}) {
  const element = typeof container === "string" ? document.querySelector(container) : container;
  if (!element) return null;

  const id = options.id || element.id || `grid-${instances.size + 1}`;
  const existingInstance = instances.get(id);
  const previousContainer = existingInstance?.container || null;
  const instance = existingInstance || {
    id,
    container: element,
    allColumns: [],
    columns: [],
    columnOrder: [],
    hiddenColumns: new Set(),
    frozenCount: 0,
    zoom: 100,
    sourceRows: [],
    rows: [],
    selected: new Set(),
    active: null,
    anchor: null,
    colWidths: {},
    rowHeights: {},
    undoStack: [],
    redoStack: [],
    cutCells: new Set(),
    fillPreview: null,
    pendingSaves: 0,
    saveState: "idle",
    saveStateTimer: 0,
    virtualThreshold: Number(options.virtualThreshold) || 400,
    virtualWindow: { start: 0, end: 0 },
    virtualRenderFrame: 0,
    editing: null,
    filters: {},
    sort: null,
    persistKey: options.persistKey || "",
    filtersEnabled: Boolean(options.filters),
    toolbarEnabled: options.toolbar !== false,
    onSelectionChange: options.onSelectionChange || null,
    onSaveStateChange: options.onSaveStateChange || null,
    onEmptyAction: options.onEmptyAction || null,
    emptyActionLabel: options.emptyActionLabel || "",
    emptyTitle: options.emptyTitle || "Nenhum registro nesta visualizacao",
    emptyDescription: options.emptyDescription || "Altere a competencia ou limpe os filtros para consultar outros acordos.",
    onError: options.onError || ((error) => window.alert(error.message || error)),
  };

  instance.container = element;
  instance.onError = options.onError || instance.onError;
  instance.onSelectionChange = options.onSelectionChange || instance.onSelectionChange;
  instance.onSaveStateChange = options.onSaveStateChange || instance.onSaveStateChange;
  instance.onEmptyAction = options.onEmptyAction || instance.onEmptyAction;
  instance.emptyActionLabel = options.emptyActionLabel ?? instance.emptyActionLabel;
  instance.emptyTitle = options.emptyTitle || instance.emptyTitle;
  instance.emptyDescription = options.emptyDescription || instance.emptyDescription;
  instance.filtersEnabled = Boolean(options.filters ?? instance.filtersEnabled);
  instance.toolbarEnabled = options.toolbar !== false;
  instance.virtualThreshold = Number(options.virtualThreshold) || instance.virtualThreshold || 400;
  if (options.persistKey && options.persistKey !== instance.persistKey) {
    instance.persistKey = options.persistKey;
    const layout = loadStoredLayout(instance);
    instance.columnOrder = Array.isArray(layout.order) ? layout.order : [];
    instance.hiddenColumns = new Set(Array.isArray(layout.hidden) ? layout.hidden : []);
    instance.frozenCount = Number(layout.frozenCount) || 0;
    instance.zoom = Number(layout.zoom) || 100;
    instance.rowHeights = layout.rowHeights && typeof layout.rowHeights === "object" ? layout.rowHeights : {};
    instance.colWidths = {
      ...instance.colWidths,
      ...loadStoredColumnWidths(instance),
    };
  } else if (instance.persistKey) {
    const layout = loadStoredLayout(instance);
    if (!instance.columnOrder.length && Array.isArray(layout.order)) instance.columnOrder = layout.order;
    if (!instance.hiddenColumns.size && Array.isArray(layout.hidden)) instance.hiddenColumns = new Set(layout.hidden);
    if (!instance.frozenCount) instance.frozenCount = Number(layout.frozenCount) || 0;
    if (instance.zoom === 100) instance.zoom = Number(layout.zoom) || 100;
    if (!Object.keys(instance.rowHeights).length && layout.rowHeights && typeof layout.rowHeights === "object") {
      instance.rowHeights = layout.rowHeights;
    }
    instance.colWidths = {
      ...loadStoredColumnWidths(instance),
      ...instance.colWidths,
    };
  }

  instance.render = () => {
    renderGrid(instance, { preserveScroll: true });
  };

  if (!existingInstance) {
    instances.set(id, instance);
  }
  if (!existingInstance || previousContainer !== element) {
    element.classList.add("excel-grid");
    element.tabIndex = 0;
    bindInstance(instance);
  }

  return {
    render(rows, columns, options = {}) {
      const position = options.preservePosition ? captureGridPosition(instance) : null;
      instance.sourceRows = rows || [];
      instance.allColumns = columns || instance.allColumns || [];
      applyColumnPreferences(instance);
      const storedWidths = loadStoredColumnWidths(instance);
      instance.allColumns.forEach((column) => {
        instance.colWidths[column.id] = storedWidths[column.id] || instance.colWidths[column.id] || defaultColumnWidth(column);
      });
      refreshRows(instance);
      if (position) {
        applyGridPosition(instance, position);
      } else {
        instance.selected.clear();
        if (!instance.rows.length || !instance.columns.length) {
          instance.active = null;
          instance.anchor = null;
        }
        if (!instance.active && instance.rows.length && instance.columns.length) {
          instance.active = { row: 0, col: 0 };
          instance.anchor = { row: 0, col: 0 };
          instance.selected.add(cellKey(0, 0));
        }
      }
      renderGrid(instance);
      restoreGridScroll(instance, position);
    },
    capturePosition() {
      return captureGridPosition(instance);
    },
    restorePosition(position) {
      applyGridPosition(instance, position);
      renderSelection(instance);
      updateFormulaBar(instance);
      restoreGridScroll(instance, position);
    },
    updateRow(updatedItem) {
      const currentItem = instance.sourceRows.find((entry) => sameRow(entry, updatedItem));
      if (!currentItem) return false;
      const row = replaceRowData(instance, currentItem, updatedItem, -1);
      refreshRenderedRow(instance, row);
      return true;
    },
    getSelectedCells() {
      return selectedCellDetails(instance);
    },
    getViewState() {
      return {
        filters: Object.fromEntries(Object.entries(instance.filters || {}).map(([key, values]) => [key, [...values]])),
        sort: instance.sort ? { ...instance.sort } : null,
        order: [...instance.columnOrder],
        hidden: [...instance.hiddenColumns],
        frozenCount: instance.frozenCount,
        zoom: instance.zoom,
      };
    },
    applyViewState(view = {}) {
      instance.filters = Object.fromEntries(
        Object.entries(view.filters || {}).map(([key, values]) => [key, new Set(Array.isArray(values) ? values : [])]),
      );
      instance.sort = view.sort?.columnId ? { ...view.sort } : null;
      if (Array.isArray(view.order) && view.order.length) instance.columnOrder = [...view.order];
      if (Array.isArray(view.hidden)) instance.hiddenColumns = new Set(view.hidden);
      if (Number.isFinite(Number(view.frozenCount))) instance.frozenCount = Number(view.frozenCount);
      if (Number.isFinite(Number(view.zoom))) instance.zoom = clamp(Number(view.zoom), 60, 180);
      applyColumnPreferences(instance);
      refreshRows(instance);
      saveStoredLayout(instance);
      renderGrid(instance, { preserveScroll: true });
    },
    clearFilters() {
      clearGridFilters(instance);
    },
    refreshLayout() {
      renderGrid(instance, { preserveScroll: true });
    },
    setColumnFilter(columnId, values = []) {
      const column = instance.allColumns.find((entry) => entry.id === columnId);
      if (!column) return;
      if (!values.length) delete instance.filters[columnId];
      else instance.filters[columnId] = new Set(values.map(filterKey));
      refreshRows(instance);
      renderGrid(instance, { preserveScroll: true });
    },
    instance,
  };
}

function renderWindowFor(instance, viewport) {
  const rows = instance.rows;
  const virtualized = rows.length > instance.virtualThreshold && !Object.keys(instance.rowHeights).length;
  if (!virtualized) return { start: 0, end: rows.length, top: 0, bottom: 0, virtualized: false };
  const zoom = (instance.zoom || 100) / 100;
  const rowHeight = 30 * zoom;
  const viewportHeight = viewport?.clientHeight || 480;
  const scrollTop = viewport?.scrollTop || 0;
  const overscan = 16;
  const start = clamp(Math.floor(scrollTop / rowHeight) - overscan, 0, rows.length);
  const visible = Math.ceil(viewportHeight / rowHeight) + overscan * 2;
  const end = clamp(start + visible, start, rows.length);
  return {
    start,
    end,
    top: start * 30,
    bottom: Math.max(0, (rows.length - end) * 30),
    virtualized: true,
  };
}

function virtualSpacerRow(height, columns) {
  if (!height) return "";
  return `
    <tr class="excel-virtual-spacer" aria-hidden="true">
      <td colspan="${Math.max(columns.length + 1, 1)}" style="height:${height}px"></td>
    </tr>
  `;
}

function renderGrid(instance, options = {}) {
  const columns = instance.columns;
  const rows = instance.rows;
  const previousViewport = instance.container.querySelector(".excel-sheet-viewport");
  const previousScroll = options.preserveScroll && previousViewport
    ? { left: previousViewport.scrollLeft, top: previousViewport.scrollTop }
    : null;
  const renderWindow = renderWindowFor(instance, previousViewport);
  instance.virtualWindow = { start: renderWindow.start, end: renderWindow.end };
  const visibleRows = rows.slice(renderWindow.start, renderWindow.end);

  instance.container.innerHTML = `
    <div class="excel-grid-shell">
      ${instance.toolbarEnabled ? `
        <div class="excel-toolbar" role="toolbar" aria-label="Ferramentas da planilha">
          <div class="excel-toolbar-group">
            <button type="button" data-grid-action="undo" title="Desfazer (Ctrl+Z)" aria-label="Desfazer" ${instance.undoStack.length ? "" : "disabled"}>&#8630;</button>
            <button type="button" data-grid-action="redo" title="Refazer (Ctrl+Y)" aria-label="Refazer" ${instance.redoStack.length ? "" : "disabled"}>&#8631;</button>
          </div>
          <div class="excel-toolbar-group">
            <button type="button" data-grid-action="copy" title="Copiar (Ctrl+C)" aria-label="Copiar"><span aria-hidden="true">&#10697;</span></button>
            <button type="button" data-grid-action="cut" title="Recortar (Ctrl+X)" aria-label="Recortar"><span aria-hidden="true">&#9986;</span></button>
            <button type="button" data-grid-action="paste" title="Colar (Ctrl+V)" aria-label="Colar"><span aria-hidden="true">&#9635;</span></button>
          </div>
          <details class="excel-more-menu">
            <summary title="Mais ferramentas" aria-label="Mais ferramentas">&#8943;</summary>
            <div class="excel-more-popover">
              <button type="button" data-grid-action="autofit"><span>Autoajustar colunas</span><kbd>duplo clique</kbd></button>
              <button type="button" data-grid-action="columns"><span>Organizar colunas</span></button>
              <button type="button" data-grid-action="freeze"><span data-freeze-label>${instance.frozenCount ? `Fixadas: ${instance.frozenCount}` : "Congelar colunas"}</span></button>
            </div>
          </details>
        </div>
      ` : ""}
      <div class="excel-formula-bar">
        <span class="excel-name-box">A1</span>
        <span class="excel-fx">fx</span>
        <input class="excel-formula-input" aria-label="Barra de formula">
      </div>
      <div class="excel-sheet-viewport">
        <table class="excel-table" role="grid" aria-rowcount="${rows.length}" aria-colcount="${columns.length}">
          <thead>
            <tr class="excel-letter-row">
              <th class="excel-corner"></th>
              ${columns.map((column, col) => `
                <th class="excel-letter-header" data-col-select="${col}" data-col="${col}">
                  ${columnName(col)}
                </th>
              `).join("")}
            </tr>
            <tr class="excel-field-row">
              <th class="excel-row-header excel-field-corner">#</th>
              ${columns.map((column, col) => `
                <th class="excel-field-header" data-col-select="${col}" data-col="${col}">
                  <span class="excel-field-title">${escapeHtml(column.title)}</span>
                  ${instance.filtersEnabled && column.type !== "action" ? `
                    <button
                      class="excel-filter-btn ${instance.filters[column.id] ? "active" : ""}"
                      type="button"
                      data-filter-col="${col}"
                      title="Filtrar ${escapeHtml(column.title)}"
                      aria-label="Filtrar ${escapeHtml(column.title)}"
                    >▾</button>
                  ` : ""}
                  <span class="excel-col-resizer"></span>
                </th>
              `).join("")}
            </tr>
          </thead>
          <tbody>
            ${rows.length ? `
              ${virtualSpacerRow(renderWindow.top, columns)}
              ${visibleRows.map((row, visibleIndex) => {
                const rowIndex = renderWindow.start + visibleIndex;
                return `
              <tr>
                <th class="excel-row-header" data-row-select="${rowIndex}">
                  ${rowIndex + 1}
                  <span class="excel-row-resizer"></span>
                </th>
                ${columns.map((column, col) => {
                  const width = instance.colWidths[column.id] || defaultColumnWidth(column);
                  const height = instance.rowHeights[rowIndex] || 30;
                  const customCellClass = typeof column.cellClass === "function" ? column.cellClass(row) : (column.cellClass || "");
                  return `
                    <td
                      class="excel-cell ${isColumnEditable(column) ? "editable" : "read-only"} ${column.type === "action" ? "action-cell" : ""} ${escapeHtml(customCellClass)}"
                      data-row="${rowIndex}"
                      data-col="${col}"
                      style="width:${width}px;min-width:${width}px;max-width:${width}px;height:${height}px"
                      tabindex="-1"
                    >${displayFor(column, row)}</td>
                  `;
                }).join("")}
              </tr>
                `;
              }).join("")}
              ${virtualSpacerRow(renderWindow.bottom, columns)}
            ` : `
              <tr>
                <th class="excel-row-header">1</th>
                <td class="excel-empty-cell" colspan="${Math.max(columns.length, 1)}">
                  <div class="excel-empty-state">
                    <strong>${escapeHtml(instance.emptyTitle)}</strong>
                    <span>${escapeHtml(instance.emptyDescription)}</span>
                    ${instance.emptyActionLabel ? `<button type="button" data-grid-action="empty-create">${escapeHtml(instance.emptyActionLabel)}</button>` : ""}
                  </div>
                </td>
              </tr>
            `}
          </tbody>
        </table>
      </div>
      <div class="excel-status-bar">
        <span data-grid-state data-state="${instance.pendingSaves > 0 ? "saving" : (instance.saveState || "idle")}">${gridStateText(instance)}</span>
        <strong data-grid-selection-summary>Contagem: 0</strong>
        <div class="excel-zoom-control">
          <button type="button" data-grid-action="zoom-out" aria-label="Diminuir zoom">-</button>
          <span data-grid-zoom-label>${instance.zoom || 100}%</span>
          <button type="button" data-grid-action="zoom-in" aria-label="Aumentar zoom">+</button>
        </div>
      </div>
    </div>
  `;
  applySizes(instance);
  if (previousScroll) {
    const viewport = instance.container.querySelector(".excel-sheet-viewport");
    if (viewport) {
      viewport.scrollLeft = previousScroll.left;
      viewport.scrollTop = previousScroll.top;
    }
  }
  renderSelection(instance);
  updateFormulaBar(instance);
}
