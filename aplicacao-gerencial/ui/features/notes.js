import { api } from "../core/api.js";
import { $ } from "../core/dom.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { closeDialog } from "../layout/dialogs.js";

const labels = {
  event: "Evento da timeline",
  parecer: "Parecer",
  protocolo: "Protocolo",
  monitoramento: "Monitoramento",
};

let activeTarget = null;

export function notesButton(targetType, targetId, label = "Observações") {
  return `<button class="secondary-btn note-btn" type="button" data-note-target="${escapeAttr(targetType)}:${escapeAttr(targetId)}">${escapeHtml(label)}</button>`;
}

export function bindNotesButtons(root = document) {
  if (!root || root.dataset?.notesDelegated === "true") return;
  if (root.dataset) root.dataset.notesDelegated = "true";
  root.addEventListener("click", (event) => {
    const button = event.target.closest("[data-note-target]");
    if (!button || !root.contains(button)) return;
    event.stopPropagation();
    const [targetType, ...idParts] = button.dataset.noteTarget.split(":");
    openNotesDialog(targetType, idParts.join(":"));
  });
}

export async function renderNotesPanel(targetType, targetId, selector) {
  const target = $(selector);
  if (!target) return;
  target.innerHTML = `<section class="notes-panel"><h3>Observações</h3><div class="empty-overview">Carregando observações...</div></section>`;
  const notes = await loadNotes(targetType, targetId);
  target.innerHTML = renderNotes(targetType, targetId, notes, false);
  const countTarget = target.closest(".hub-notes-disclosure")?.querySelector("[data-notes-count]");
  if (countTarget) countTarget.textContent = `${notes.length} ${notes.length === 1 ? "registro" : "registros"}`;
  bindNotesPanel(target, targetType, targetId);
}

export async function openNotesDialog(targetType, targetId) {
  activeTarget = { targetType, targetId };
  $("#notesDialogBody").innerHTML = `<div class="empty-overview">Carregando observações...</div>`;
  $("#notesDialog").showModal();
  await refreshNotesDialog();
}

export function bindNotesDialogActions() {
  document.querySelector("[data-close-notes]")?.addEventListener("click", () => closeDialog("#notesDialog"));
}

async function refreshNotesDialog() {
  if (!activeTarget) return;
  const notes = await loadNotes(activeTarget.targetType, activeTarget.targetId);
  $("#notesDialogBody").innerHTML = renderNotes(activeTarget.targetType, activeTarget.targetId, notes, true);
  bindNotesPanel($("#notesDialogBody"), activeTarget.targetType, activeTarget.targetId, true);
}

async function loadNotes(targetType, targetId) {
  return api(`/api/notes?target_type=${encodeURIComponent(targetType)}&target_id=${encodeURIComponent(targetId)}`);
}

function renderNotes(targetType, targetId, notes, compact) {
  return `
    <section class="notes-panel ${compact ? "notes-panel-dialog" : ""}" data-notes-panel="${escapeAttr(targetType)}:${escapeAttr(targetId)}">
      <div class="notes-head">
        <h3>Observações</h3>
        <span>${notes.length} registro(s)</span>
      </div>
      <form class="notes-form" data-note-form>
        <textarea name="text" rows="3" placeholder="Adicionar uma observação"></textarea>
        <button class="primary-btn fit" type="submit">Salvar observação</button>
      </form>
      <div class="notes-list">
        ${notes.length ? notes.map(renderNote).join("") : `<div class="empty-overview">Nenhuma observação registrada ainda.</div>`}
      </div>
    </section>
  `;
}

function renderNote(note) {
  return `
    <article class="note-item" data-note-id="${escapeAttr(note.id)}">
      <div class="note-meta">
        <strong>${escapeHtml(note.usuario || "Usuario")}</strong>
        <span>${escapeHtml(formatNoteDate(note.updated_at || note.created_at))}</span>
      </div>
      <p>${escapeHtml(note.text)}</p>
      <button class="text-btn" type="button" data-note-edit="${escapeAttr(note.id)}">Editar</button>
    </article>
  `;
}

function bindNotesPanel(root, targetType, targetId, dialogMode = false) {
  root.querySelector("[data-note-form]")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = event.currentTarget.text.value.trim();
    if (!text) return;
    await api("/api/notes", {
      method: "POST",
      body: JSON.stringify({ target_type: targetType, target_id: targetId, text }),
    });
    if (dialogMode) await refreshNotesDialog();
    else await renderNotesPanel(targetType, targetId, `#${root.id}`);
  });
  root.querySelectorAll("[data-note-edit]").forEach((button) => {
    button.addEventListener("click", async () => {
      const item = button.closest(".note-item");
      const current = item.querySelector("p").textContent;
      item.innerHTML = `
        <form class="notes-form note-edit-form">
          <textarea name="text" rows="3">${escapeHtml(current)}</textarea>
          <div class="note-edit-actions">
            <button class="secondary-btn" type="button" data-note-cancel>Cancelar</button>
            <button class="primary-btn fit" type="submit">Salvar</button>
          </div>
        </form>
      `;
      item.querySelector("[data-note-cancel]").addEventListener("click", () => {
        if (dialogMode) refreshNotesDialog();
        else renderNotesPanel(targetType, targetId, `#${root.id}`);
      });
      item.querySelector("form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const text = event.currentTarget.text.value.trim();
        if (!text) return;
        await api(`/api/notes/${button.dataset.noteEdit}`, {
          method: "PUT",
          body: JSON.stringify({ text }),
        });
        if (dialogMode) await refreshNotesDialog();
        else await renderNotesPanel(targetType, targetId, `#${root.id}`);
      });
      item.querySelector("textarea").focus();
    });
  });
}

function formatNoteDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || "";
  return date.toLocaleString("pt-BR");
}
