import { api } from "../core/api.js";
import { state } from "../core/state.js";
import { toast } from "../core/toast.js";
import { parecerHeader, parecerPk } from "./parecerData.js";
import { renderParecerAprovacao, renderParecerCompleta, renderParecerPendentes } from "./parecerView.js?v=20260717-css-cleanup-2";

const callbacks = {
  removeParecerNotifications: () => {},
  reloadPage: async () => {},
  reloadDashboard: async () => {},
  onHubRefresh: async () => {},
};

export function configureParecerActions(options = {}) {
  Object.assign(callbacks, options);
}

export async function markParecer(pk, button = null) {
  if (!pk) {
    toast("PK nao localizada nesta linha");
    return false;
  }
  const oldText = button?.textContent || "";
  if (button) {
    button.disabled = true;
    button.textContent = "Solicitando...";
  }
  try {
    if (state.parecer.page === "pendentes") state.parecer.pendingScrollTop = window.scrollY;
    const result = await api("/api/pareceres/marcar-solicitado", { method: "POST", body: JSON.stringify({ pk }) });
    applyLocalParecerRequested([pk]);
    callbacks.removeParecerNotifications([pk]);
    await callbacks.onHubRefresh();
    const time = Number.isFinite(Number(result.elapsed_ms)) ? ` em ${(Number(result.elapsed_ms) / 1000).toFixed(1)}s` : "";
    toast(result.duplicated ? `PK ${pk} ja estava solicitada` : `PK ${pk} marcada como solicitada${time}`);
    queueParecerSync();
    return true;
  } catch (error) {
    toast(error.message);
    return false;
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = oldText;
    }
  }
}

export async function approveParecer(pk, justificativa = "", descricao = "", button = null) {
  if (!pk) return toast("PK nao localizada nesta solicitacao");
  const reason = String(justificativa || "").trim();
  if (!reason) return toast("Informe a justificativa da aprovação.");
  const description = String(descricao || "").trim();
  if (!description) return toast("Informe a descrição do parecer.");
  const oldText = button?.textContent || "";
  if (button) {
    button.disabled = true;
    button.textContent = "Aprovando...";
  }
  try {
    await api("/api/pareceres/aprovar", { method: "POST", body: JSON.stringify({ pk, justificativa: reason, descricao: description }) });
    state.parecer.aprovacao = state.parecer.aprovacao.filter((row) => String(parecerPk(row)) !== String(pk));
    await callbacks.onHubRefresh();
    toast("Parecer aprovado. Ele agora aparece em Pendentes.");
    queueParecerSync();
    if (state.parecer.page === "aprovacao") renderParecerAprovacao();
    return true;
  } catch (error) {
    toast(error.message);
    return false;
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = oldText;
    }
  }
}

export async function rejectParecer(pk, justificativa, descricao = "", button = null) {
  if (!pk) return toast("PK nao localizada nesta solicitacao");
  const reason = String(justificativa || "").trim();
  if (!reason) return toast("Informe a justificativa da reprovação.");
  const description = String(descricao || "").trim();
  if (!description) return toast("Informe a descrição do parecer.");
  const oldText = button?.textContent || "";
  if (button) {
    button.disabled = true;
    button.textContent = "Reprovando...";
  }
  try {
    await api("/api/pareceres/reprovar", { method: "POST", body: JSON.stringify({ pk, justificativa: reason, descricao: description }) });
    state.parecer.aprovacao = state.parecer.aprovacao.filter((row) => String(parecerPk(row)) !== String(pk));
    await callbacks.onHubRefresh();
    toast("Parecer reprovado e cancelado no sistema negocial.");
    queueParecerSync();
    if (state.parecer.page === "aprovacao") renderParecerAprovacao();
    return true;
  } catch (error) {
    toast(error.message);
    return false;
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = oldText;
    }
  }
}
export async function markSelectedParecer() {
  const pks = [...document.querySelectorAll(".parecer-row-check:checked")].map((check) => check.value).filter(Boolean);
  if (!pks.length) return toast("Selecione pelo menos um parecer");
  if (state.parecer.page === "pendentes") state.parecer.pendingScrollTop = window.scrollY;
  const result = await api("/api/pareceres/marcar-varios", { method: "POST", body: JSON.stringify({ pks }) });
  applyLocalParecerRequested(pks);
  callbacks.removeParecerNotifications(pks);
  await callbacks.onHubRefresh();
  const time = Number.isFinite(Number(result.elapsed_ms)) ? ` em ${(Number(result.elapsed_ms) / 1000).toFixed(1)}s` : "";
  toast(`${pks.length} pareceres marcados${time}`);
  queueParecerSync();
}

function applyLocalParecerRequested(pks) {
  const requested = new Set(pks.map((pk) => String(pk)));
  state.parecer.pendentes = state.parecer.pendentes.filter((row) => !requested.has(String(parecerPk(row))));
  state.parecer.records = state.parecer.records.map((row) => {
    if (!requested.has(String(parecerPk(row)))) return row;
    const header = parecerHeader(row, state.parecer.config?.solicitado_column || "SOLICITADO?");
    return { ...row, [header]: "SIM" };
  });
  if (state.parecer.page === "pendentes") renderParecerPendentes();
  if (state.parecer.page === "completa") renderParecerCompleta();
}

function queueParecerSync() {
  clearTimeout(state.parecer.syncTimer);
  state.parecer.syncTimer = setTimeout(async () => {
    try {
      if (state.parecer.page === "pendentes") state.parecer.pendingScrollTop = window.scrollY;
      await callbacks.reloadPage();
      if (state.parecer.page !== "dashboard") await callbacks.reloadDashboard();
      await callbacks.onHubRefresh();
    } catch (error) {
      toast(error.message);
    }
  }, 900);
}

