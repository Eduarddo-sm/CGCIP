import { copySelectedCells, editCell } from "./spreadsheetGridEditing.js";
import { cellInfo, cellKey, gridState as state, instanceFromCell } from "./spreadsheetGridCore.js";

export { configureSpreadsheetGrid } from "./spreadsheetGridCore.js";

export function bindSpreadsheetGrid(containerSelector, options = {}) {
  const container = document.querySelector(containerSelector);
  if (!container) return;
  const instance = {
    id: options.id || containerSelector,
    containerSelector,
    selectedCells: new Set(),
    lastCell: null,
    selectedAnchor: null,
    editable: Boolean(options.editable),
    onSave: options.onSave,
    onSelectionChange: options.onSelectionChange,
    zoom: state.zooms.get(options.id || containerSelector) || 1,
  };
  state.instances.set(instance.id, instance);
  container.classList.add("spreadsheet-grid", "excel-grid", "gerencial-excel-grid");
  decorateSpreadsheetGrid(container, instance);
  applyZoom(instance);
  if (!container.dataset.zoomBound) {
    container.dataset.zoomBound = "true";
    container.addEventListener("wheel", handleZoom, { passive: false });
  }
  container.querySelectorAll(".spreadsheet-cell").forEach((cell) => {
    cell.dataset.gridId = instance.id;
    cell.addEventListener("mousedown", (event) => startDrag(event, cell));
    cell.addEventListener("mouseenter", (event) => dragCell(event, cell));
    cell.addEventListener("dblclick", (event) => editCell(event, cell, {
      onTab: (shiftKey) => moveTabFromCell(cell, shiftKey),
    }));
    cell.addEventListener("keydown", (event) => {
      if (event.key === "Tab") {
        moveTabSelection(event, cell);
        return;
      }
      if (["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key)) {
        moveSelection(event, cell);
        return;
      }
      if (event.key === " " || event.key === "Enter") {
        event.preventDefault();
        selectCell(event, cell);
      }
    });
  });
}

function moveTabSelection(event, cell) {
  if (state.editingCell) return;
  event.preventDefault();
  moveTabFromCell(cell, event.shiftKey);
}

function moveTabFromCell(cell, shiftKey = false) {
  const instance = instanceFromCell(cell);
  if (!instance) return;
  const origin = instance.lastCell || cellInfo(cell);
  const targetRow = origin.row;
  const targetCol = Math.max(0, origin.col + (shiftKey ? -1 : 1));
  const target = document.querySelector(`${instance.containerSelector} .spreadsheet-cell[data-sheet-row="${targetRow}"][data-sheet-col="${targetCol}"]`);
  if (!target) return;
  applyKeyboardSelection(instance, target, targetRow, targetCol, false, origin);
}

document.addEventListener("copy", copySelectedCells);
document.addEventListener("mouseup", () => {
  state.drag = null;
});

function handleZoom(event) {
  if (!event.ctrlKey) return;
  const cell = event.target.closest(".spreadsheet-cell");
  if (!cell) return;
  const instance = instanceFromCell(cell);
  if (!instance) return;
  event.preventDefault();
  const direction = event.deltaY < 0 ? 1 : -1;
  const nextZoom = Math.min(1.8, Math.max(0.65, Number((instance.zoom + direction * 0.08).toFixed(2))));
  if (nextZoom === instance.zoom) return;
  instance.zoom = nextZoom;
  state.zooms.set(instance.id, nextZoom);
  applyZoom(instance);
}

function applyZoom(instance) {
  const container = document.querySelector(instance.containerSelector);
  if (!container) return;
  container.style.setProperty("--sheet-zoom", instance.zoom);
}

function startDrag(event, cell) {
  if (event.button !== 0 || state.editingCell) return;
  const instance = instanceFromCell(cell);
  if (!instance) return;
  const interactiveTarget = event.target.closest("button, input, select, textarea, a");
  if (!interactiveTarget) event.preventDefault();
  const info = cellInfo(cell);
  if (event.shiftKey && instance.lastCell) {
    const base = event.ctrlKey || event.metaKey ? new Set(instance.selectedCells) : new Set();
    applyRange(instance, instance.lastCell.row, instance.lastCell.col, info.row, info.col, base);
    state.drag = { instanceId: instance.id, start: { ...instance.lastCell }, base };
    return;
  }
  const base = event.ctrlKey || event.metaKey ? new Set(instance.selectedCells) : new Set();
  state.drag = { instanceId: instance.id, start: { row: info.row, col: info.col }, base };
  instance.lastCell = { row: info.row, col: info.col };
  instance.selectedAnchor = { row: info.row, col: info.col };
  applyRange(instance, info.row, info.col, info.row, info.col, base);
  if (!interactiveTarget) cell.focus({ preventScroll: true });
}

function dragCell(event, cell) {
  if (!state.drag || state.editingCell) return;
  const instance = instanceFromCell(cell);
  if (!instance || instance.id !== state.drag.instanceId) return;
  event.preventDefault();
  const info = cellInfo(cell);
  const { start, base } = state.drag;
  applyRange(instance, start.row, start.col, info.row, info.col, base);
}

function selectCell(event, cell) {
  const instance = instanceFromCell(cell);
  if (!instance) return;
  const info = cellInfo(cell);
  const key = cellKey(info.row, info.col);
  if (event.shiftKey && instance.lastCell) {
    const base = event.ctrlKey || event.metaKey ? new Set(instance.selectedCells) : new Set();
    applyRange(instance, instance.lastCell.row, instance.lastCell.col, info.row, info.col, base);
    instance.selectedAnchor = instance.selectedAnchor || { ...instance.lastCell };
  } else if (event.ctrlKey || event.metaKey) {
    if (instance.selectedCells.has(key)) instance.selectedCells.delete(key);
    else instance.selectedCells.add(key);
    instance.lastCell = { row: info.row, col: info.col };
    instance.selectedAnchor = { row: info.row, col: info.col };
    renderSelection(instance);
  } else {
    instance.selectedCells.clear();
    instance.selectedCells.add(key);
    instance.lastCell = { row: info.row, col: info.col };
    instance.selectedAnchor = { row: info.row, col: info.col };
    renderSelection(instance);
  }
}

function moveSelection(event, cell) {
  if (state.editingCell) return;
  const instance = instanceFromCell(cell);
  if (!instance) return;
  event.preventDefault();
  const origin = instance.lastCell || cellInfo(cell);
  const [rowDelta, colDelta] = {
    ArrowUp: [-1, 0],
    ArrowDown: [1, 0],
    ArrowLeft: [0, -1],
    ArrowRight: [0, 1],
  }[event.key];
  const edgeJump = event.ctrlKey || event.metaKey;
  const edge = edgeJump ? findVirtualEdgeCell(instance, cell, origin, rowDelta, colDelta) || findEdgeCell(instance, origin, rowDelta, colDelta) : null;
  const targetRow = edge ? edge.row : Math.max(0, origin.row + rowDelta);
  const targetCol = edge ? edge.col : Math.max(0, origin.col + colDelta);
  let target = document.querySelector(`${instance.containerSelector} .spreadsheet-cell[data-sheet-row="${targetRow}"][data-sheet-col="${targetCol}"]`);
  if (!target && materializeVirtualTarget(instance, cell, targetRow, targetCol, event.shiftKey, origin)) return;
  if (!target) return;
  applyKeyboardSelection(instance, target, targetRow, targetCol, event.shiftKey, origin, {
    edgeJump,
    rowDelta,
    colDelta,
  });
}

function applyKeyboardSelection(instance, target, targetRow, targetCol, extendSelection, origin, scrollOptions = {}) {
  if (extendSelection) {
    const anchor = instance.selectedAnchor || origin;
    applyRange(instance, anchor.row, anchor.col, targetRow, targetCol);
    instance.selectedAnchor = anchor;
  } else {
    instance.selectedCells.clear();
    instance.selectedCells.add(cellKey(targetRow, targetCol));
    instance.selectedAnchor = { row: targetRow, col: targetCol };
    renderSelection(instance);
  }
  instance.lastCell = { row: targetRow, col: targetCol };
  target.focus({ preventScroll: true });
  ensureCellFullyVisible(instance, target, scrollOptions);
}

function ensureCellFullyVisible(instance, cell, options = {}) {
  const scroller = findGridScroller(instance, cell);
  if (!scroller) {
    cell.scrollIntoView({ block: "nearest", inline: "nearest" });
    return;
  }

  const maxLeft = Math.max(0, scroller.scrollWidth - scroller.clientWidth);
  const maxTop = Math.max(0, scroller.scrollHeight - scroller.clientHeight);
  if (options.edgeJump && options.colDelta > 0) scroller.scrollLeft = maxLeft;
  if (options.edgeJump && options.colDelta < 0) scroller.scrollLeft = 0;
  if (options.edgeJump && options.rowDelta > 0) scroller.scrollTop = maxTop;
  if (options.edgeJump && options.rowDelta < 0) scroller.scrollTop = 0;

  const scrollerRect = scroller.getBoundingClientRect();
  let cellRect = cell.getBoundingClientRect();
  const headerHeight = cell.closest("table")?.querySelector("thead")?.getBoundingClientRect().height || 0;
  const stickyActionWidth = stickyRightWidth(scroller, cell);
  const padding = 4;
  const visibleLeft = scrollerRect.left + padding;
  const visibleRight = scrollerRect.right - stickyActionWidth - padding;
  const visibleTop = scrollerRect.top + headerHeight + padding;
  const visibleBottom = scrollerRect.bottom - padding;

  cellRect = cell.getBoundingClientRect();

  if (cellRect.right > visibleRight) {
    scroller.scrollLeft = Math.min(maxLeft, scroller.scrollLeft + (cellRect.right - visibleRight));
  } else if (cellRect.left < visibleLeft) {
    scroller.scrollLeft = Math.max(0, scroller.scrollLeft - (visibleLeft - cellRect.left));
  }

  if (cellRect.bottom > visibleBottom) {
    scroller.scrollTop = Math.min(maxTop, scroller.scrollTop + (cellRect.bottom - visibleBottom));
  } else if (cellRect.top < visibleTop) {
    scroller.scrollTop = Math.max(0, scroller.scrollTop - (visibleTop - cellRect.top));
  }
}

function findGridScroller(instance, cell) {
  const container = document.querySelector(instance.containerSelector);
  return cell.closest(".monitor-planilha-scroll, .excel-sheet-viewport")
    || container?.querySelector(".monitor-planilha-scroll, .excel-sheet-viewport")
    || nearestScrollableParent(cell, container)
    || null;
}

function findVirtualEdgeCell(instance, cell, origin, rowDelta, colDelta) {
  const scroller = findGridScroller(instance, cell);
  if (!scroller?.dataset.virtualRowHeight) return null;
  const totalRows = Number(scroller.dataset.virtualTotalRows || 0);
  const totalCols = Number(scroller.dataset.virtualTotalCols || 0);
  if (rowDelta < 0) return { row: 0, col: origin.col };
  if (rowDelta > 0 && totalRows > 0) return { row: totalRows - 1, col: origin.col };
  if (colDelta < 0) return { row: origin.row, col: 0 };
  if (colDelta > 0 && totalCols > 0) return { row: origin.row, col: totalCols - 1 };
  return null;
}

function materializeVirtualTarget(instance, cell, targetRow, targetCol, extendSelection, origin) {
  const scroller = findGridScroller(instance, cell);
  const rowHeight = Number(scroller?.dataset.virtualRowHeight || 0);
  if (!scroller || !rowHeight) return false;
  scroller.scrollTop = Math.max(0, targetRow * rowHeight - rowHeight * 2);
  window.setTimeout(() => {
    const target = document.querySelector(`${instance.containerSelector} .spreadsheet-cell[data-sheet-row="${targetRow}"][data-sheet-col="${targetCol}"]`);
    if (!target) return;
    applyKeyboardSelection(instance, target, targetRow, targetCol, extendSelection, origin, { edgeJump: true });
  }, 20);
  return true;
}

function nearestScrollableParent(cell, stopAt) {
  let node = cell.parentElement;
  while (node && node !== stopAt?.parentElement) {
    const style = window.getComputedStyle(node);
    const scrollableX = /(auto|scroll)/.test(style.overflowX) && node.scrollWidth > node.clientWidth;
    const scrollableY = /(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight;
    if (scrollableX || scrollableY) return node;
    node = node.parentElement;
  }
  return null;
}

function stickyRightWidth(scroller, cell) {
  return 0;
}

function findEdgeCell(instance, origin, rowDelta, colDelta) {
  const cells = [...document.querySelectorAll(`${instance.containerSelector} .spreadsheet-cell`)].map(cellInfo);
  if (!cells.length) return null;
  if (rowDelta < 0) {
    const rows = cells.filter((info) => info.col === origin.col && info.row <= origin.row).map((info) => info.row);
    return { row: Math.min(...rows), col: origin.col };
  }
  if (rowDelta > 0) {
    const rows = cells.filter((info) => info.col === origin.col && info.row >= origin.row).map((info) => info.row);
    return { row: Math.max(...rows), col: origin.col };
  }
  if (colDelta < 0) {
    const cols = cells.filter((info) => info.row === origin.row && info.col <= origin.col).map((info) => info.col);
    return { row: origin.row, col: Math.min(...cols) };
  }
  if (colDelta > 0) {
    const cols = cells.filter((info) => info.row === origin.row && info.col >= origin.col).map((info) => info.col);
    return { row: origin.row, col: Math.max(...cols) };
  }
  return null;
}

function applyRange(instance, startRow, startCol, endRow, endCol, base = new Set()) {
  instance.selectedCells = new Set(base);
  const minRow = Math.min(startRow, endRow);
  const maxRow = Math.max(startRow, endRow);
  const minCol = Math.min(startCol, endCol);
  const maxCol = Math.max(startCol, endCol);
  document.querySelectorAll(`${instance.containerSelector} .spreadsheet-cell`).forEach((node) => {
    const info = cellInfo(node);
    if (info.row >= minRow && info.row <= maxRow && info.col >= minCol && info.col <= maxCol) {
      instance.selectedCells.add(cellKey(info.row, info.col));
    }
  });
  renderSelection(instance);
}

function renderSelection(instance) {
  const cells = [...document.querySelectorAll(`${instance.containerSelector} .spreadsheet-cell`)];
  const selected = cells.filter((cell) => instance.selectedCells.has(cellKey(cellInfo(cell).row, cellInfo(cell).col)));
  const selectedInfo = selected.map(cellInfo);
  const rows = selectedInfo.map((info) => info.row);
  const cols = selectedInfo.map((info) => info.col);
  const minRow = rows.length ? Math.min(...rows) : -1;
  const maxRow = rows.length ? Math.max(...rows) : -1;
  const minCol = cols.length ? Math.min(...cols) : -1;
  const maxCol = cols.length ? Math.max(...cols) : -1;

  cells.forEach((cell) => {
    const info = cellInfo(cell);
    const isSelected = instance.selectedCells.has(cellKey(info.row, info.col));
    const isActive = Boolean(instance.lastCell && info.row === instance.lastCell.row && info.col === instance.lastCell.col);
    cell.classList.toggle("selected", isSelected);
    cell.classList.toggle("active", isActive);
    cell.classList.toggle("selection-edge-top", isSelected && info.row === minRow);
    cell.classList.toggle("selection-edge-right", isSelected && info.col === maxCol);
    cell.classList.toggle("selection-edge-bottom", isSelected && info.row === maxRow);
    cell.classList.toggle("selection-edge-left", isSelected && info.col === minCol);
  });
  updateSpreadsheetChrome(instance, selectedInfo);
  if (typeof instance.onSelectionChange === "function") {
    instance.onSelectionChange(selectedInfo, instance);
  }
}

function decorateSpreadsheetGrid(container, instance) {
  const table = container.querySelector("table");
  if (!table) return;
  const viewport = table.closest(".monitor-planilha-scroll, .table-scroll, .data-table-wrap") || table.parentElement;
  table.classList.add("excel-table");
  viewport?.classList.add("excel-sheet-viewport");

  const thead = table.tHead;
  const fieldRow = thead?.querySelector(".excel-field-row")
    || [...(thead?.rows || [])].find((row) => !row.classList.contains("excel-letter-row"));
  if (!thead || !fieldRow) return;
  const fieldHeaders = [...fieldRow.cells].filter((header) => !header.classList.contains("excel-field-corner"));
  fieldRow.classList.add("excel-field-row");
  fieldHeaders.forEach((header, col) => {
    header.classList.add("excel-field-header");
    header.dataset.excelCol = String(col);
  });

  if (!thead.querySelector(".excel-letter-row")) {
    const letters = document.createElement("tr");
    letters.className = "excel-letter-row";
    letters.innerHTML = `<th class="excel-corner"></th>${fieldHeaders.map((header, col) => `
      <th class="excel-letter-header" data-excel-col="${col}">${columnName(col)}</th>
    `).join("")}`;
    thead.insertBefore(letters, fieldRow);

    const corner = document.createElement("th");
    corner.className = "excel-row-header excel-field-corner";
    corner.textContent = "#";
    fieldRow.insertBefore(corner, fieldRow.firstChild);
  }

  [...(table.tBodies?.[0]?.rows || [])].forEach((row, rowIndex) => {
    if (row.querySelector(".excel-row-header")) return;
    const rowHeader = document.createElement("th");
    rowHeader.className = "excel-row-header";
    rowHeader.scope = "row";
    rowHeader.textContent = String(rowIndex + 1);
    rowHeader.dataset.excelRow = String(rowIndex);
    row.insertBefore(rowHeader, row.firstChild);
  });

  if (!container.querySelector(":scope > .excel-formula-bar")) {
    const formula = document.createElement("div");
    formula.className = "excel-formula-bar";
    formula.innerHTML = `
      <span class="excel-name-box">A1</span>
      <span class="excel-fx">fx</span>
      <input class="excel-formula-input" type="text" readonly aria-label="Conteudo da celula selecionada">
    `;
    container.insertBefore(formula, viewport || table);
  }

  if (!container.querySelector(":scope > .excel-status-bar")) {
    const status = document.createElement("div");
    status.className = "excel-status-bar";
    status.innerHTML = `<span>Pronto</span><div class="excel-selection-summary"></div>`;
    (viewport || table).insertAdjacentElement("afterend", status);
  }
  instance.formulaBar = container.querySelector(":scope > .excel-formula-bar");
  instance.statusBar = container.querySelector(":scope > .excel-status-bar");
}

function updateSpreadsheetChrome(instance, selected = []) {
  const container = document.querySelector(instance.containerSelector);
  if (!container) return;
  const active = instance.lastCell || selected.at(-1) || null;
  const activeCell = active
    ? container.querySelector(`.spreadsheet-cell[data-sheet-row="${active.row}"][data-sheet-col="${active.col}"]`)
    : null;
  const nameBox = container.querySelector(":scope > .excel-formula-bar .excel-name-box");
  const formulaInput = container.querySelector(":scope > .excel-formula-bar .excel-formula-input");
  if (nameBox) nameBox.textContent = active ? `${columnName(active.col)}${active.row + 1}` : "A1";
  if (formulaInput) formulaInput.value = activeCell?.dataset.sheetValue ?? "";

  container.querySelectorAll(".excel-letter-header").forEach((header) => {
    header.classList.toggle("active", Boolean(active && Number(header.dataset.excelCol) === active.col));
  });
  container.querySelectorAll(".excel-row-header[data-excel-row]").forEach((header) => {
    header.classList.toggle("active", Boolean(active && Number(header.dataset.excelRow) === active.row));
  });

  const summary = container.querySelector(":scope > .excel-status-bar .excel-selection-summary");
  if (!summary) return;
  const numeric = selected.map((item) => parseSpreadsheetNumber(item.value)).filter(Number.isFinite);
  const sum = numeric.reduce((total, value) => total + value, 0);
  const average = numeric.length ? sum / numeric.length : 0;
  summary.innerHTML = `
    <span>Contagem: ${selected.length}</span>
    ${numeric.length ? `<span>Soma: ${formatSpreadsheetNumber(sum)}</span><span>Media: ${formatSpreadsheetNumber(average)}</span>` : ""}
  `;
}

function parseSpreadsheetNumber(value) {
  const text = String(value ?? "").trim().replace(/R\$\s*/gi, "").replace(/\s/g, "");
  if (!text || !/[0-9]/.test(text)) return Number.NaN;
  const normalized = text.includes(",") ? text.replace(/\./g, "").replace(",", ".") : text;
  const number = Number(normalized.replace(/[^0-9.-]/g, ""));
  return Number.isFinite(number) ? number : Number.NaN;
}

function formatSpreadsheetNumber(value) {
  return Number(value || 0).toLocaleString("pt-BR", { maximumFractionDigits: 2 });
}

function columnName(index) {
  let value = Number(index) + 1;
  let result = "";
  while (value > 0) {
    value -= 1;
    result = String.fromCharCode(65 + (value % 26)) + result;
    value = Math.floor(value / 26);
  }
  return result || "A";
}

