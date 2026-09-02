import { api } from "../core/api.js";
import { $ } from "../core/dom.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { toast } from "../core/toast.js";
import { state } from "../core/state.js";
import { displayCellValue, money } from "./monitorPlanilhaFormat.js?v=20260717-css-cleanup-2";
import { bindSpreadsheetGrid } from "./spreadsheetGrid.js";

const monthNames = [
  "Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

export function initMonitorFechamento() {
  populateClosingPeriodSelectors();
}

export async function loadMonitorFechamento() {
  populateClosingPeriodSelectors();
  const carteira = $("#monitorFechamentoCarteira")?.value || "";
  const mes = $("#monitorFechamentoMes")?.value || "";
  const ano = $("#monitorFechamentoAno")?.value || "";
  if (!carteira) {
    renderClosingEmpty("Selecione uma carteira para validar o fechamento.");
    return;
  }
  $("#monitorFechamentoStatus").innerHTML = `<div class="empty-overview">Carregando fechamento...</div>`;
  $("#monitorFechamentoOpenList").innerHTML = "";
  try {
    const payload = await api(`/api/monitoramento/fechamento?carteira=${encodeURIComponent(carteira)}&mes=${encodeURIComponent(mes)}&ano=${encodeURIComponent(ano)}`);
    state.monitorFechamento = payload;
    renderClosing(payload);
  } catch (error) {
    renderClosingEmpty(error.message || "Nao foi possivel carregar o fechamento.");
  }
}

export async function closeMonitorMonth() {
  const payload = currentClosingFilters();
  if (!payload.carteira) {
    toast("Selecione uma carteira");
    return;
  }
  const current = state.monitorFechamento;
  if (current?.closed) {
    toast("Este periodo ja esta fechado");
    return;
  }
  const confirmation = window.prompt(
    `Fechar ${payload.carteira} ${monthNames[Number(payload.mes) - 1]}/${payload.ano}?\n\nIsso aplicara QUEBRA nas propostas abertas e travara edicoes do periodo.\nDigite FECHAR para confirmar.`
  );
  if (confirmation !== "FECHAR") return;
  try {
    const result = await api("/api/monitoramento/fechamento", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.monitorFechamento = result;
    renderClosing(result);
    toast(`Fechamento concluido. Quebras aplicadas: ${result.quebras_aplicadas || 0}`);
  } catch (error) {
    toast(error.message || "Nao foi possivel fechar o mes");
  }
}

export function downloadMonitorClosingReport() {
  const payload = currentClosingFilters();
  if (!payload.carteira) {
    toast("Selecione uma carteira");
    return;
  }
  const url = `/api/monitoramento/fechamento/relatorio.xlsx?carteira=${encodeURIComponent(payload.carteira)}&mes=${encodeURIComponent(payload.mes)}&ano=${encodeURIComponent(payload.ano)}`;
  window.open(url, "_blank");
}

function currentClosingFilters() {
  return {
    carteira: $("#monitorFechamentoCarteira")?.value || "",
    mes: Number($("#monitorFechamentoMes")?.value || 0),
    ano: Number($("#monitorFechamentoAno")?.value || 0),
  };
}

function populateClosingPeriodSelectors() {
  const monthSelect = $("#monitorFechamentoMes");
  const yearSelect = $("#monitorFechamentoAno");
  if (monthSelect && !monthSelect.options.length) {
    const currentMonth = new Date().getMonth() + 1;
    monthSelect.innerHTML = monthNames.map((name, index) => `<option value="${index + 1}">${name}</option>`).join("");
    monthSelect.value = String(currentMonth);
  }
  if (yearSelect && !yearSelect.options.length) {
    const currentYear = new Date().getFullYear();
    yearSelect.innerHTML = Array.from({ length: 7 }, (_, index) => currentYear - 3 + index)
      .map((year) => `<option value="${year}">${year}</option>`)
      .join("");
    yearSelect.value = String(currentYear);
  }
}

function renderClosing(payload) {
  const report = payload.report || {};
  const closed = Boolean(payload.closed);
  $("#monitorFechamentoSummary").innerHTML = `
    <article class="monitor-summary-card">
      <span>Periodo</span>
      <strong>${escapeHtml(payload.mes_nome || "-")}/${escapeHtml(String(payload.ano || ""))}</strong>
    </article>
    <article class="monitor-summary-card">
      <span>Casos</span>
      <strong>${escapeHtml(String(report.total_casos_atualizados || 0))}</strong>
    </article>
    <article class="monitor-summary-card">
      <span>Producao</span>
      <strong>${money(report.total_producao)}</strong>
    </article>
    <article class="monitor-summary-card ${closed ? "success" : "warning"}">
      <span>Status</span>
      <strong>${closed ? "Fechado" : "Aberto"}</strong>
    </article>
  `;
  $("#monitorFechamentoStatus").innerHTML = `
    <div class="fechamento-status-line">
      <div>
        <strong>${closed ? "Periodo travado" : "Periodo aberto para fechamento"}</strong>
        <span>${closed ? `Fechado por ${escapeHtml(payload.closed_by || "-")} em ${escapeHtml(payload.closed_at || "-")}` : "Confira as propostas abertas antes de fechar."}</span>
      </div>
      <span class="status-pill ${closed ? "concluido" : "pendente"}">${closed ? "FECHADO" : "ABERTO"}</span>
    </div>
  `;
  $("#monitorFechamentoCloseBtn").disabled = closed;
  renderOpenRows(payload.open_rows || []);
}

function renderOpenRows(rows) {
  if (!rows.length) {
    $("#monitorFechamentoOpenList").innerHTML = `<div class="empty-overview">Nenhuma proposta aberta para o periodo selecionado.</div>`;
    return;
  }
  const headers = ["DATA", "CLIENTE", "NEGOCIADOR", "STATUS", "VALOR DO ACORDO", "HONORÁRIOS RECEBIDOS"];
  $("#monitorFechamentoOpenList").innerHTML = `
    <div class="panel-head">
      <h2>Propostas abertas</h2>
      <span>${rows.length} registro(s)</span>
    </div>
    <div class="monitor-planilha-scroll">
      <table class="data-table compact-table">
        <thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
        <tbody>
          ${rows.map((row, rowIndex) => `<tr>${headers.map((header, columnIndex) => {
            const value = displayCellValue(header, row[header] ?? fallbackValue(row, header));
            return `<td
              class="spreadsheet-cell copy-cell"
              tabindex="0"
              data-sheet-row="${rowIndex}"
              data-sheet-row-key="${escapeAttr(row._row_id ?? row.id ?? rowIndex)}"
              data-sheet-col="${columnIndex}"
              data-sheet-header="${escapeAttr(header)}"
              data-sheet-value="${escapeAttr(value)}"
            >${escapeHtml(value)}</td>`;
          }).join("")}</tr>`).join("")}
        </tbody>
      </table>
    </div>
  `;
  bindSpreadsheetGrid("#monitorFechamentoOpenList", {
    id: "monitor-fechamento-open-rows",
    editable: false,
  });
}

function fallbackValue(row, header) {
  if (header === "NEGOCIADOR") return row.NEGOCIADOR || row.USUARIO || row.OPERADOR || "";
  if (header === "VALOR DO ACORDO") return row["VALOR TOTAL"] || row["VALOR TOTAL DE ACORDO"] || "";
  if (header === "HONORÁRIOS RECEBIDOS") return row["HONORARIOS"] || row["HONORÁRIOS"] || "";
  return "";
}

function renderClosingEmpty(message) {
  $("#monitorFechamentoSummary").innerHTML = "";
  $("#monitorFechamentoStatus").innerHTML = `<div class="empty-overview">${escapeHtml(message)}</div>`;
  $("#monitorFechamentoOpenList").innerHTML = "";
}
