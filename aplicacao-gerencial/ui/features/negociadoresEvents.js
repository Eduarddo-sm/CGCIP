import { api } from "../core/api.js";
import { $ } from "../core/dom.js";
import { formatValue } from "../core/format.js";
import { escapeHtml } from "../core/html.js";
import { state } from "../core/state.js";
import { toast } from "../core/toast.js";
import { expandChangeRows, renderMiniRowDiffs } from "./changeDiff.js";
import { renderNotesPanel } from "./notes.js";

export async function openEvent(eventId) {
  try {
    const event = await api(`/api/negociadores/${state.activeId}/events/${eventId}`);
    const meta = event.metadata;
    const changes = event.delta.changes || [];
    $("#eventDetails").innerHTML = `
      <div class="meta-grid">
        <div><strong>Negociador</strong><br>${escapeHtml(meta.negociador)}</div>
        <div><strong>Carteira</strong><br>${escapeHtml(meta.carteira || "Carteira nao informada")}</div>
        <div><strong>Arquivo</strong><br>${escapeHtml(meta.arquivo)}</div>
        <div><strong>Sheet</strong><br>${escapeHtml(meta.sheet)}</div>
        <div><strong>Data/Hora</strong><br>${escapeHtml(meta.data)} ${escapeHtml(meta.hora)}</div>
        </div>
        <div class="change-card">
        <h2>Alteracoes realizadas</h2>
        ${renderChanges(changes)}
        </div>
        <div id="eventNotes"></div>
        `;
    await renderNotesPanel("event", event.id, "#eventNotes");
    $("#eventDialog").showModal();
  } catch (error) {
    toast(error.message);
  }
}

function renderChanges(changes) {
  const rows = changes.flatMap(expandChangeRows);
  return `
    ${renderMiniRowDiffs(changes)}
    <table class="changes-table">
      <thead><tr><th>Campo</th><th>Linha</th><th>Antes</th><th>Depois</th></tr></thead>
      <tbody>
      ${rows.map((change) => `
          <tr>
          <td>${escapeHtml(change.column)}</td>
          <td>${escapeHtml(change.excel_row || change.row_id)}</td>
          <td class="before">${escapeHtml(formatValue(change.before))}</td>
          <td class="after">${escapeHtml(formatValue(change.after))}</td>
          </tr>
          `).join("")}
      </tbody>
    </table>
  `;
}
