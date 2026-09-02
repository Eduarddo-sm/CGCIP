import { $ } from "../core/dom.js";

const CLOSE_ANIMATION_MS = 180;
let dialogScrollLockPatched = false;

export function closeDialog(dialogOrSelector) {
  const dialog = typeof dialogOrSelector === "string" ? $(dialogOrSelector) : dialogOrSelector;
  if (!dialog?.open || dialog.classList.contains("closing")) return;

  dialog.classList.add("closing");
  window.setTimeout(() => {
    dialog.classList.remove("closing");
    if (dialog.open) dialog.close();
  }, CLOSE_ANIMATION_MS);
}

export function bindDialogDismiss(dialogOrSelector) {
  const dialog = typeof dialogOrSelector === "string" ? $(dialogOrSelector) : dialogOrSelector;
  if (!dialog || dialog.dataset.dismissBound) return;

  dialog.dataset.dismissBound = "true";
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) closeDialog(dialog);
  });
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeDialog(dialog);
  });
  dialog.addEventListener("close", () => {
    dialog.classList.remove("closing");
    updateDialogScrollLock();
  });
}

export function bindAllDialogDismiss() {
  patchDialogScrollLock();
  document.querySelectorAll("dialog").forEach(bindDialogDismiss);
  updateDialogScrollLock();
}

function patchDialogScrollLock() {
  if (dialogScrollLockPatched || !window.HTMLDialogElement) return;
  dialogScrollLockPatched = true;
  const originalShowModal = window.HTMLDialogElement.prototype.showModal;
  window.HTMLDialogElement.prototype.showModal = function patchedShowModal(...args) {
    const result = originalShowModal.apply(this, args);
    updateDialogScrollLock();
    return result;
  };
}

function updateDialogScrollLock() {
  const hasOpenDialog = Boolean(document.querySelector("dialog[open]"));
  document.body.classList.toggle("dialog-open", hasOpenDialog);
}
