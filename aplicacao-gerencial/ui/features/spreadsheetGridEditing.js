import { cellInfo, cellKey, gridState as state, instanceFromCell } from "./spreadsheetGridCore.js";

export function copySelectedCells(event) {
  const instance = state.instances.get(state.active);
  if (!instance || !instance.selectedCells.size) return;
  if (!shouldCopyGridSelection(instance)) return;
  const cells = [...document.querySelectorAll(`${instance.containerSelector} .spreadsheet-cell.selected`)].map((cell) => cellInfo(cell));
  if (!cells.length) return;
  const rows = [...new Set(cells.map((cell) => cell.row))].sort((a, b) => a - b);
  const cols = [...new Set(cells.map((cell) => cell.col))].sort((a, b) => a - b);
  const lookup = new Map(cells.map((cell) => [cellKey(cell.row, cell.col), cell.value]));
  const text = rows.map((row) => cols.map((col) => lookup.get(cellKey(row, col)) || "").join("\t")).join("\n");
  event.preventDefault();
  event.clipboardData.setData("text/plain", text);
  state.toast(`${cells.length} celula(s) copiadas`);
}

function shouldCopyGridSelection(instance) {
  const container = document.querySelector(instance.containerSelector);
  if (!container || container.getClientRects().length === 0 || container.closest(".hidden")) return false;

  const selection = window.getSelection();
  if (selection && !selection.isCollapsed && String(selection).trim()) {
    return nodeInside(container, selection.anchorNode) && nodeInside(container, selection.focusNode);
  }

  const active = document.activeElement;
  return Boolean(active && container.contains(active));
}

function nodeInside(container, node) {
  if (!node) return false;
  const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
  return Boolean(element && container.contains(element));
}

export function editCell(event, cell, options = {}) {
  const instance = instanceFromCell(cell);
  if (!instance?.editable || state.editingCell) return;
  if (cell.dataset.sheetEditable === "false") return;
  event.preventDefault();
  event.stopPropagation();
  state.drag = null;
  const info = cellInfo(cell);
  const original = info.value;
  cell.classList.add("editing");
  cell.innerHTML = `<input class="cell-editor" type="text" />`;
  const editor = cell.querySelector(".cell-editor");
  editor.value = original;
  editor.focus();
  editor.select();
  state.editingCell = cell;
  let finished = false;
  const finish = async (save) => {
    if (finished) return;
    finished = true;
    const nextValue = editor.value;
    state.editingCell = null;
    cell.classList.remove("editing");
    if (!save || nextValue === original) {
      cell.textContent = original;
      return save;
    }
    cell.textContent = nextValue;
    cell.dataset.sheetValue = nextValue;
    try {
      await instance.onSave?.({ ...info, value: nextValue });
      state.toast("Celula salva na planilha");
      return true;
    } catch (error) {
      cell.textContent = original;
      cell.dataset.sheetValue = original;
      state.toast(error.message);
      return false;
    }
  };
  editor.addEventListener("mousedown", (innerEvent) => innerEvent.stopPropagation());
  editor.addEventListener("keydown", async (innerEvent) => {
    if (innerEvent.key === "Tab") {
      innerEvent.preventDefault();
      innerEvent.stopPropagation();
      const saved = await finish(true);
      if (saved) options.onTab?.(innerEvent.shiftKey);
      return;
    }
    if (innerEvent.key === "Enter") {
      innerEvent.preventDefault();
      await finish(true);
      return;
    }
    if (innerEvent.key === "Escape") {
      innerEvent.preventDefault();
      finish(false);
    }
  });
  editor.addEventListener("blur", () => finish(true));
}
