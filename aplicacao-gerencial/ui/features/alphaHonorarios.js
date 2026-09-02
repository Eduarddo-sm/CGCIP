import { api } from "../core/api.js";
import { escapeAttr, escapeHtml } from "../core/html.js";

const money = (value) => Number(value || 0).toLocaleString("pt-BR", {
  style: "currency",
  currency: "BRL",
});

function dateTime(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function monthLabel(value) {
  if (!value) return "-";
  const [year, month] = String(value).split("-").map(Number);
  return new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric" })
    .format(new Date(year, month - 1, 1))
    .replace(/^\w/, (character) => character.toUpperCase());
}

async function fileAsBase64(file) {
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Nao foi possivel ler o PDF selecionado."));
    reader.onload = () => resolve(reader.result);
    reader.readAsDataURL(file);
  });
  return String(dataUrl).split(",", 2)[1] || "";
}

function totalsMarkup(item) {
  return (item?.raw_data_json?.totals || []).map((total) => `
    <article>
      <span>${escapeHtml(monthLabel(total.competence))}</span>
      <strong>${money(total.meta_pnt)}</strong>
      <small>Caixa ${money(total.meta_caixa)} + retomadas ${money(total.retomadas_value)}</small>
    </article>`).join("");
}

function importHistoryMarkup(items) {
  if (!items.length) return '<div class="alpha-ho-empty">Nenhum PDF trimestral importado.</div>';
  return items.map((item) => `
    <button type="button" class="alpha-ho-import-row" data-alpha-import="${item.id}">
      <span><strong>${escapeHtml(item.quarter)}</strong><small>${escapeHtml(item.file_name)}</small></span>
      <span><em class="alpha-ho-status status-${escapeAttr(String(item.status).toLowerCase())}">${escapeHtml(item.status)}</em><small>${dateTime(item.created_at)}</small></span>
    </button>`).join("");
}

function matrixMarkup(rule) {
  const matrix = rule?.matrix_json || {};
  const delayBands = matrix.delay_bands || [];
  return `
    <div class="alpha-ho-matrix" data-alpha-matrix>
      <div class="alpha-ho-matrix-head">
        <span>Faixa de atraso</span><span>&lt; 85%</span><span>85% a 110%</span><span>&gt; 110%</span>
      </div>
      ${delayBands.map((band, index) => `
        <div class="alpha-ho-matrix-row" data-delay-band="${index}" data-min="${Number(band.min || 0)}" data-max="${band.max ?? ""}">
          <strong>${Number(band.min || 0)} a ${band.max ?? "+"} dias</strong>
          <label><input type="number" min="0" max="100" step="0.01" data-rate="BELOW_85" value="${Number(band.rates?.BELOW_85 || 0)}"><span>%</span></label>
          <label><input type="number" min="0" max="100" step="0.01" data-rate="BETWEEN_85_110" value="${Number(band.rates?.BETWEEN_85_110 || 0)}"><span>%</span></label>
          <label><input type="number" min="0" max="100" step="0.01" data-rate="ABOVE_110" value="${Number(band.rates?.ABOVE_110 || 0)}"><span>%</span></label>
        </div>`).join("")}
    </div>`;
}

function calculationMarkup(payload) {
  const summary = payload?.summary || {};
  const rows = payload?.items || [];
  return `
    <div class="alpha-ho-summary">
      <article><span>Acordos calculados</span><strong>${Number(summary.records || 0).toLocaleString("pt-BR")}</strong></article>
      <article><span>Base dos acordos</span><strong>${money(summary.base_value)}</strong></article>
      <article><span>H.O. em conferencia</span><strong>${money(summary.calculated_honorarios)}</strong></article>
      <article class="${Number(summary.unmatched_portfolios || 0) ? "is-warning" : ""}"><span>Sem meta localizada</span><strong>${Number(summary.unmatched_portfolios || 0)}</strong></article>
    </div>
    <div class="alpha-ho-calculation-table">
      <table>
        <thead><tr><th>Cliente</th><th>Portfolio</th><th>Competencia</th><th>Meta</th><th>Producao</th><th>Atingimento</th><th>Atraso</th><th>Taxa</th><th>H.O.</th></tr></thead>
        <tbody>${rows.slice(0, 500).map((row) => `
          <tr class="${row.goal_id ? "" : "is-unmatched"}">
            <td>${escapeHtml(row.cliente)}</td><td>${escapeHtml(row.portfolio || "Nao localizado")}</td>
            <td>${escapeHtml(monthLabel(row.competence))}</td><td>${money(row.meta_pnt)}</td>
            <td>${money(row.accumulated_production)}</td><td>${Number(row.attainment_percent || 0).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%</td>
            <td>${Number(row.delay_days || 0)} dias</td><td>${Number(row.applied_rate || 0).toLocaleString("pt-BR")}%</td>
            <td><strong>${money(row.calculated_honorarios)}</strong></td>
          </tr>`).join("")}</tbody>
      </table>
    </div>`;
}

function goalsMarkup(items) {
  if (!items.length) return '<div class="alpha-ho-empty">Nenhuma meta ativa localizada.</div>';
  return `
    <div class="alpha-ho-goals-table">
      <table>
        <thead><tr><th>Portfólio</th><th>Competência</th><th>Meta caixa</th><th>Retomadas</th><th>Valor retomadas</th><th>Meta PNT</th><th>Origem</th><th></th></tr></thead>
        <tbody>${items.map((goal) => `
          <tr>
            <td><strong>${escapeHtml(goal.portfolio)}</strong><small>${escapeHtml(goal.group_name || "")}</small></td>
            <td>${escapeHtml(monthLabel(goal.competence))}</td>
            <td>${money(goal.meta_caixa)}</td>
            <td>${Number(goal.retomadas_count || 0).toLocaleString("pt-BR")}</td>
            <td>${money(goal.retomadas_value)}</td>
            <td><strong>${money(goal.meta_pnt)}</strong></td>
            <td>
              <em class="alpha-ho-source source-${escapeAttr(String(goal.source_type || "PDF").toLowerCase())}">${escapeHtml(goal.source_type || "PDF")}</em>
              ${goal.created_by ? `<small>${escapeHtml(goal.created_by)}</small>` : ""}
            </td>
            <td><button type="button" class="secondary-btn ds-button compact" data-edit-alpha-goal="${goal.id}">Editar</button></td>
          </tr>`).join("")}</tbody>
      </table>
    </div>`;
}

function goalDialogMarkup() {
  return `
    <dialog class="alpha-ho-goal-dialog" data-alpha-goal-dialog>
      <form method="dialog" data-alpha-goal-form>
        <header>
          <div><span>Correção auditável</span><h3 data-goal-dialog-title>Editar meta</h3></div>
          <button type="button" class="icon-btn" data-close-goal-dialog aria-label="Fechar">×</button>
        </header>
        <div class="alpha-ho-goal-fields">
          <label>Meta caixa<input name="meta_caixa" inputmode="decimal" required></label>
          <label>Quantidade de retomadas<input name="retomadas_count" type="number" min="0" step="1" required></label>
          <label>Valor de retomadas<input name="retomadas_value" inputmode="decimal" required></label>
          <label class="span-all">Justificativa<textarea name="reason" minlength="5" required placeholder="Descreva por que a meta precisa ser corrigida"></textarea></label>
        </div>
        <aside>A meta importada do PDF será preservada no histórico. O total PNT será recalculado pela soma da meta caixa e do valor de retomadas.</aside>
        <footer>
          <button type="button" class="secondary-btn ds-button" data-close-goal-dialog>Cancelar</button>
          <button type="submit" class="primary-btn ds-button">Salvar correção</button>
        </footer>
      </form>
    </dialog>`;
}

export async function renderAlphaHonorarios(target, callbacks = {}) {
  target.innerHTML = '<div class="carteira-workspace-loading"><span></span><strong>Carregando metas e honorarios...</strong></div>';
  try {
    const [importsPayload, rulesPayload, calculations, goalsPayload] = await Promise.all([
      api("/api/config/alpha/ho/imports"),
      api("/api/config/alpha/ho/rules"),
      api("/api/config/alpha/ho/calculations"),
      api("/api/config/alpha/ho/goals"),
    ]);
    const imports = importsPayload.items || [];
    const goals = goalsPayload.items || [];
    const activeRule = (rulesPayload.items || []).find((rule) => rule.status === "ATIVA") || rulesPayload.items?.[0];
    target.innerHTML = `
      <div class="alpha-ho-page">
        <section class="alpha-ho-commandbar">
          <div><span>Regra excepcional</span><h3>Metas trimestrais e honorarios</h3><small>Modo conferencia: nenhum valor negocial e sobrescrito.</small></div>
          <div class="alpha-ho-actions">
            <label class="secondary-btn ds-button compact">Selecionar PDF<input type="file" accept="application/pdf,.pdf" data-alpha-pdf hidden></label>
            <button class="primary-btn ds-button compact" type="button" data-preview-alpha disabled>Validar PDF</button>
            <button class="secondary-btn ds-button compact" type="button" data-recalculate-alpha>Recalcular</button>
          </div>
        </section>
        <div class="alpha-ho-feedback hidden" data-alpha-feedback></div>
        <section class="alpha-ho-layout">
          <article class="carteira-workspace-card alpha-ho-import-card">
            <header><div><span>Fonte oficial</span><h3>Importacoes trimestrais</h3></div><strong>${imports.length}</strong></header>
            <div class="alpha-ho-imports">${importHistoryMarkup(imports)}</div>
          </article>
          <article class="carteira-workspace-card alpha-ho-preview-card">
            <header><div><span>Conferencia</span><h3 data-preview-title>Selecione uma importacao</h3></div><strong data-preview-status>-</strong></header>
            <div data-alpha-preview class="alpha-ho-empty">Os totais oficiais e avisos de validacao aparecerao aqui.</div>
          </article>
        </section>
        <section class="carteira-workspace-card alpha-ho-rule-card">
          <header>
            <div><span>Versao ${escapeHtml(activeRule?.id || "-")}</span><h3>Matriz de faixas</h3></div>
            <div class="alpha-ho-rule-actions">
              <input type="date" data-rule-effective value="${escapeAttr(new Date().toISOString().slice(0, 10))}">
              <button class="secondary-btn ds-button compact" type="button" data-save-rule>Salvar nova versao</button>
            </div>
          </header>
          ${matrixMarkup(activeRule)}
        </section>
        <section class="carteira-workspace-card alpha-ho-goals-card">
          <header>
            <div><span>${goals.length} metas ativas</span><h3>Metas por portfólio</h3></div>
            <strong>PDF + correções manuais</strong>
          </header>
          ${goalsMarkup(goals)}
        </section>
        <section class="carteira-workspace-card alpha-ho-calculation-card">
          <header><div><span>Memoria de calculo</span><h3>Resultado por acordo</h3></div><strong>Conferencia</strong></header>
          <div data-alpha-calculations>${calculationMarkup(calculations)}</div>
        </section>
        ${goalDialogMarkup()}
      </div>`;

    let selectedFile = null;
    const feedback = target.querySelector("[data-alpha-feedback]");
    const showFeedback = (message, kind = "info") => {
      feedback.textContent = message;
      feedback.className = `alpha-ho-feedback is-${kind}`;
    };
    const showImport = async (id) => {
      const payload = await api(`/api/config/alpha/ho/imports/${id}`);
      const item = payload.item;
      const validation = item.validation_json || {};
      target.querySelector("[data-preview-title]").textContent = `${item.quarter} - ${item.file_name}`;
      target.querySelector("[data-preview-status]").textContent = item.status;
      target.querySelector("[data-alpha-preview]").innerHTML = `
        <div class="alpha-ho-totals">${totalsMarkup(item)}</div>
        <div class="alpha-ho-validation ${validation.valid ? "is-valid" : "is-invalid"}">
          <strong>${validation.valid ? "PDF validado" : "Importacao bloqueada"}</strong>
          <span>${Number(validation.portfolio_count || 0)} portfolios e ${Number(validation.goal_count || 0)} metas mensais</span>
          ${(validation.errors || []).map((message) => `<p>${escapeHtml(message)}</p>`).join("")}
          ${(validation.warnings || []).map((message) => `<p class="warning">${escapeHtml(message)}</p>`).join("")}
        </div>
        ${item.status === "VALIDADO" ? `<button class="primary-btn ds-button compact" type="button" data-apply-alpha="${item.id}">Aplicar metas validadas</button>` : ""}`;
      target.querySelector("[data-apply-alpha]")?.addEventListener("click", async (event) => {
        event.currentTarget.disabled = true;
        try {
          const result = await api(`/api/config/alpha/ho/imports/${item.id}/apply`, { method: "POST", body: "{}" });
          showFeedback(`${result.calculation.calculated} acordos recalculados em modo conferencia.`, "success");
          await renderAlphaHonorarios(target, callbacks);
        } catch (error) {
          event.currentTarget.disabled = false;
          showFeedback(error.message, "error");
        }
      });
    };
    const goalDialog = target.querySelector("[data-alpha-goal-dialog]");
    const goalForm = target.querySelector("[data-alpha-goal-form]");
    let editingGoal = null;
    target.querySelectorAll("[data-edit-alpha-goal]").forEach((button) => {
      button.addEventListener("click", () => {
        editingGoal = goals.find((goal) => String(goal.id) === button.dataset.editAlphaGoal);
        if (!editingGoal) return;
        target.querySelector("[data-goal-dialog-title]").textContent =
          `${editingGoal.portfolio} · ${monthLabel(editingGoal.competence)}`;
        goalForm.elements.meta_caixa.value = Number(editingGoal.meta_caixa || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 });
        goalForm.elements.retomadas_count.value = Number(editingGoal.retomadas_count || 0);
        goalForm.elements.retomadas_value.value = Number(editingGoal.retomadas_value || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 });
        goalForm.elements.reason.value = "";
        goalDialog.showModal();
      });
    });
    target.querySelectorAll("[data-close-goal-dialog]").forEach((button) => {
      button.addEventListener("click", () => goalDialog.close());
    });
    goalForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!editingGoal || !goalForm.reportValidity()) return;
      const submit = goalForm.querySelector('[type="submit"]');
      submit.disabled = true;
      try {
        const result = await api(`/api/config/alpha/ho/goals/${editingGoal.id}/override`, {
          method: "POST",
          body: JSON.stringify({
            meta_caixa: goalForm.elements.meta_caixa.value,
            retomadas_count: Number(goalForm.elements.retomadas_count.value),
            retomadas_value: goalForm.elements.retomadas_value.value,
            reason: goalForm.elements.reason.value,
          }),
        });
        goalDialog.close();
        showFeedback(`Meta corrigida. ${result.calculation.calculated} acordos recalculados.`, "success");
        await renderAlphaHonorarios(target, callbacks);
      } catch (error) {
        submit.disabled = false;
        showFeedback(error.message, "error");
      }
    });

    target.querySelectorAll("[data-alpha-import]").forEach((button) => {
      button.addEventListener("click", () => showImport(button.dataset.alphaImport).catch(callbacks.onError));
    });
    target.querySelector("[data-alpha-pdf]")?.addEventListener("change", (event) => {
      selectedFile = event.target.files?.[0] || null;
      target.querySelector("[data-preview-alpha]").disabled = !selectedFile;
      if (selectedFile) showFeedback(`${selectedFile.name} pronto para validacao.`);
    });
    target.querySelector("[data-preview-alpha]")?.addEventListener("click", async (event) => {
      if (!selectedFile) return;
      event.currentTarget.disabled = true;
      try {
        const payload = await api("/api/config/alpha/ho/imports/preview", {
          method: "POST",
          body: JSON.stringify({
            file_name: selectedFile.name,
            content_base64: await fileAsBase64(selectedFile),
          }),
        });
        showFeedback(payload.duplicate ? "Este PDF ja havia sido importado." : "PDF validado e armazenado.", "success");
        await renderAlphaHonorarios(target, callbacks);
        await showImport(payload.item.id);
      } catch (error) {
        event.currentTarget.disabled = false;
        showFeedback(error.message, "error");
      }
    });
    target.querySelector("[data-recalculate-alpha]")?.addEventListener("click", async (event) => {
      event.currentTarget.disabled = true;
      try {
        const result = await api("/api/config/alpha/ho/recalculate", { method: "POST", body: "{}" });
        showFeedback(`${result.calculated} acordos recalculados.`, "success");
        await renderAlphaHonorarios(target, callbacks);
      } catch (error) {
        event.currentTarget.disabled = false;
        showFeedback(error.message, "error");
      }
    });
    target.querySelector("[data-save-rule]")?.addEventListener("click", async (event) => {
      const delayBands = [...target.querySelectorAll("[data-delay-band]")].map((row) => ({
        min: Number(row.dataset.min),
        max: row.dataset.max ? Number(row.dataset.max) : null,
        rates: Object.fromEntries([...row.querySelectorAll("[data-rate]")].map((input) => [input.dataset.rate, Number(input.value)])),
      }));
      event.currentTarget.disabled = true;
      try {
        await api("/api/config/alpha/ho/rules", {
          method: "POST",
          body: JSON.stringify({
            name: `Matriz Alpha ${new Date().toLocaleDateString("pt-BR")}`,
            effective_from: target.querySelector("[data-rule-effective]").value,
            activate: true,
            matrix: { ...(activeRule?.matrix_json || {}), delay_bands: delayBands },
          }),
        });
        showFeedback("Nova versao da matriz ativada.", "success");
        await renderAlphaHonorarios(target, callbacks);
      } catch (error) {
        event.currentTarget.disabled = false;
        showFeedback(error.message, "error");
      }
    });
    const applied = imports.find((item) => item.status === "APLICADO") || imports[0];
    if (applied) await showImport(applied.id);
  } catch (error) {
    target.innerHTML = `<div class="empty-overview">${escapeHtml(error.message || "Nao foi possivel carregar metas e honorarios.")}</div>`;
  }
}
