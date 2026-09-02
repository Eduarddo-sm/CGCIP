import { api } from "../core/api.js";
import { readCache, writeCache } from "../core/cache.js";
import { $ } from "../core/dom.js";
import { escapeAttr, escapeHtml } from "../core/html.js";
import { state } from "../core/state.js";
import { toast } from "../core/toast.js";

const callbacks = {
  openOverview: () => {},
  openParecerPendentes: () => {},
  openProtocoloPendentes: () => {},
  openDynamicTool: () => {},
};

const ALERTS_KEY = "negociadores_notification_alerts";
const CACHE_KEY = "notifications.latest";
const BASE_TITLE = document.title || "Monitor de Negociadores";
let baselineReady = false;
let knownNotificationIds = new Set();
let audioContext = null;

export function configureNotifications(options = {}) {
  if (typeof options.openOverview === "function") callbacks.openOverview = options.openOverview;
  if (typeof options.openParecerPendentes === "function") callbacks.openParecerPendentes = options.openParecerPendentes;
  if (typeof options.openProtocoloPendentes === "function") callbacks.openProtocoloPendentes = options.openProtocoloPendentes;
  if (typeof options.openDynamicTool === "function") callbacks.openDynamicTool = options.openDynamicTool;
}

export function initNotificationAlerts() {
  const storedPreference = localStorage.getItem(ALERTS_KEY);
  state.notificationAlertsEnabled = storedPreference === "true" || (storedPreference === null && hasTauriNotifications());
  if (storedPreference !== "false" && hasNativeNotificationApi() && Notification.permission === "granted") {
    state.notificationAlertsEnabled = true;
  }
  if (state.notificationAlertsEnabled) {
    localStorage.setItem(ALERTS_KEY, "true");
  }
  updateAlertButton();
}

export async function toggleNotificationAlerts() {
  if (state.notificationAlertsEnabled) {
    state.notificationAlertsEnabled = false;
    localStorage.setItem(ALERTS_KEY, "false");
    updateAlertButton();
    toast("Alertas desativados");
    return;
  }

  const tauriAvailable = hasTauriNotifications();
  const nativeAvailable = tauriAvailable || canUseNativeNotifications();
  const hasNativeApi = hasNativeNotificationApi();
  if (!tauriAvailable && hasNativeApi && nativeAvailable && Notification.permission === "default") {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      toast("Permissao de notificacao nao concedida.");
      updateAlertButton();
      return;
    }
  }
  if (!tauriAvailable && hasNativeApi && Notification.permission === "denied") {
    toast("Notificacoes bloqueadas no navegador. Libere a permissao nas configuracoes do site.");
    updateAlertButton();
    return;
  }

  state.notificationAlertsEnabled = true;
  localStorage.setItem(ALERTS_KEY, "true");
  baselineReady = true;
  knownNotificationIds = new Set(state.notifications.map((item) => item.id));
  updateAlertButton();
  toast(tauriAvailable ? "Alertas do Windows ativados" : nativeAvailable ? "Alertas do Chrome ativados" : "Alertas locais ativados. Para aparecer fora da guia, acesse por localhost ou HTTPS.");
  playNotificationSound();
  await showNativeNotification({
    id: "alerts-enabled",
    title: "Alertas ativados",
    message: "Voce sera avisado quando surgirem novas pendencias.",
    meta: "Monitor de Negociadores",
    source: "mainhub",
  }, { surfaceErrors: true });
  if (tauriAvailable) await previewTaskbarBadge();
}

export function toggleNotifications() {
  const dropdown = $("#notificationDropdown");
  const willOpen = dropdown.classList.contains("hidden");
  dropdown.classList.toggle("hidden", !willOpen);
  $("#notificationBtn").setAttribute("aria-expanded", String(willOpen));
  if (willOpen) loadNotifications(false);
}

export function closeNotifications() {
  $("#notificationDropdown").classList.add("hidden");
  $("#notificationBtn").setAttribute("aria-expanded", "false");
}

export async function loadNotifications(silent = true) {
  try {
    if (!state.notifications.length) {
      const cached = readCache(CACHE_KEY, 120000);
      if (cached) {
        state.notifications = cached.items || [];
        state.notificationsVersion = cached.version || "";
        renderNotifications(cached);
      }
    }
    const query = state.notificationsVersion ? `?version=${encodeURIComponent(state.notificationsVersion)}` : "";
    const payload = await api(`/api/notificacoes${query}`);
    if (payload.changed === false) {
      renderNotifications({ ...payload, items: state.notifications });
      return;
    }
    writeCache(CACHE_KEY, payload);
    state.notifications = payload.items || [];
    state.notificationsVersion = payload.version || "";
    renderNotifications(payload);
    handleNotificationAlerts(state.notifications, silent);
  } catch (error) {
    if (!silent && !String(error.message || "").includes("Login")) toast(error.message);
  }
}

function renderNotifications(payload = null) {
  const count = payload?.count ?? state.notifications.length;
  const badge = $("#notificationBadge");
  badge.textContent = count > 99 ? "99+" : count;
  badge.classList.toggle("hidden", count === 0);
  $("#notificationBtn").classList.toggle("has-notifications", count > 0);
  const overviewCount = payload?.overview ?? state.notifications.filter((item) => item.source === "overview").length;
  const parecerCount = payload?.pareceres ?? state.notifications.filter((item) => item.source === "parecer").length;
  const protocoloCount = payload?.protocolos ?? state.notifications.filter((item) => item.source === "protocolo").length;
  const toolCount = payload?.ferramentas ?? state.notifications.filter((item) => item.source === "ferramenta").length;
  $("#notificationSummary").textContent = count
    ? `${overviewCount} alteracoes - ${parecerCount} pareceres - ${protocoloCount} protocolos - ${toolCount} ferramentas`
    : "Sem novidades";
  updateDocumentTitle(count);
  syncTaskbarBadge(count);
  updateAlertButton();
  if (!state.notifications.length) {
    $("#notificationList").innerHTML = `<div class="notification-empty">Nenhuma notificacao nova.</div>`;
    return;
  }
  $("#notificationList").innerHTML = state.notifications.map((item) => `
    <button class="notification-item ${escapeAttr(item.priority || "normal")}" type="button" data-notification="${escapeAttr(item.id)}">
      <span class="notification-dot"></span>
      <span>
        <strong>${escapeHtml(item.title)}</strong>
        <small>${escapeHtml(notificationTime(item))}</small>
        <em>${escapeHtml(item.message)}</em>
        <small>${escapeHtml(item.meta || "")}</small>
      </span>
    </button>
  `).join("");
  document.querySelectorAll("[data-notification]").forEach((button) => {
    button.addEventListener("click", () => openNotification(button.dataset.notification));
  });
}

async function openNotification(notificationId) {
  const item = state.notifications.find((notification) => notification.id === notificationId);
  if (!item) return;
  openNotificationTarget(item);
}

function openNotificationTarget(item) {
  closeNotifications();
  if (item.source === "parecer") {
    callbacks.openParecerPendentes();
    toast("Abrindo pareceres pendentes");
    return;
  }
  if (item.source === "protocolo") {
    callbacks.openProtocoloPendentes();
    toast("Abrindo protocolos pendentes");
    return;
  }
  if (item.source === "mainhub") {
    window.focus();
    return;
  }
  if (item.source === "ferramenta") {
    callbacks.openDynamicTool(item);
    toast(`Abrindo ${item.title || "ferramenta"}`);
    return;
  }
  callbacks.openOverview();
  toast("Abrindo Overview");
}

export function removeNotification(notificationId) {
  state.notifications = state.notifications.filter((item) => item.id !== notificationId);
  knownNotificationIds.delete(notificationId);
  renderNotifications();
}

export function removeParecerNotifications(pks) {
  const requested = new Set(pks.map((pk) => `PARECER_${String(pk)}`));
  state.notifications = state.notifications.filter((item) => !requested.has(item.id));
  requested.forEach((id) => knownNotificationIds.delete(id));
  renderNotifications();
}

function handleNotificationAlerts(items, silent) {
  const currentIds = new Set(items.map((item) => item.id));
  if (!baselineReady) {
    knownNotificationIds = currentIds;
    baselineReady = true;
    return;
  }
  const fresh = items.filter((item) => !knownNotificationIds.has(item.id));
  knownNotificationIds = currentIds;
  if (!fresh.length) return;

  showLocalNotifications(fresh);
  if (!state.notificationAlertsEnabled) return;

  playNotificationSound();
  if (!silent) toast(`${fresh.length} nova(s) notificacao(oes)`);
  if (fresh.length === 1) {
    void showNativeNotification(fresh[0]);
    return;
  }
  void showNativeNotification({
    id: `bulk-${Date.now()}`,
    title: `${fresh.length} novas pendencias`,
    message: fresh.slice(0, 3).map((item) => item.message || item.title).join(" - "),
    meta: "Clique para abrir o Main Hub",
    source: "mainhub",
  });
}

function showLocalNotifications(items) {
  const stack = $("#localNotificationStack");
  if (!stack || !items.length) return;
  items.slice(0, 4).forEach((item) => {
    const alert = document.createElement("article");
    alert.className = `local-notification ${item.priority || "normal"}`;
    alert.dataset.localNotification = item.id;
    const { title, message } = localNotificationContent(item);
    alert.innerHTML = `
      <button class="local-notification-close" type="button" aria-label="Fechar">×</button>
      <button class="local-notification-body" type="button">
        <strong>${escapeHtml(title)}</strong>
        <span>${escapeHtml(message)}</span>
      </button>
    `;
    alert.querySelector(".local-notification-body").addEventListener("click", () => {
      dismissLocalNotification(alert);
      openNotificationTarget(item);
    });
    alert.querySelector(".local-notification-close").addEventListener("click", (event) => {
      event.stopPropagation();
      dismissLocalNotification(alert);
    });
    stack.prepend(alert);
    requestAnimationFrame(() => alert.classList.add("show"));
    setTimeout(() => dismissLocalNotification(alert), 9000);
  });
}

function localNotificationContent(item) {
  if (item.source === "overview") {
    const { negociador, cliente } = monitorNotificationParts(item);
    return {
      title: "Monitoramento",
      message: `Negociador ${negociador} tem Cliente ${cliente}`,
    };
  }
  if (item.source === "parecer") {
    return {
      title: "Parecer",
      message: `${item.message || "Cliente nao identificado"} - ${item.meta || "Parecer pendente"}`,
    };
  }
  if (item.source === "protocolo") {
    return {
      title: "Protocolo",
      message: `${item.message || "Cliente nao identificado"} - ${item.meta || "Protocolo pendente"}`,
    };
  }
  return {
    title: item.title || "Nova notificacao",
    message: item.message || item.meta || "Novo evento recebido",
  };
}

function dismissLocalNotification(alert) {
  if (!alert || alert.classList.contains("leaving")) return;
  alert.classList.add("leaving");
  setTimeout(() => alert.remove(), 180);
}

function monitorNotificationParts(item) {
  const metaMain = String(item.meta || "").split(" - ")[0].trim();
  const messageParts = String(item.message || "").split(" - ");
  return {
    negociador: metaMain || "nao identificado",
    cliente: (messageParts[messageParts.length - 1] || item.message || "Cliente nao identificado").trim(),
  };
}

async function showNativeNotification(item, options = {}) {
  if (!state.notificationAlertsEnabled) return { ok: false, provider: "disabled" };
  const tauriResult = await showTauriNotification(item, options);
  if (tauriResult.available) return tauriResult;
  if (!canUseNativeNotifications() || Notification.permission !== "granted") return { ok: false, provider: "browser", error: "Notificacoes do navegador indisponiveis." };
  try {
    const nativePayload = nativeNotificationPayload(item);
    const notification = new Notification(item.title || "Nova notificacao", {
      body: [nativePayload.message, nativePayload.meta].filter(Boolean).join("\n"),
      tag: item.id,
      renotify: false,
    });
    notification.onclick = () => {
      window.focus();
      notification.close();
      openNotificationTarget(item);
    };
    return { ok: true, provider: "browser" };
  } catch {
    // O navegador pode bloquear notificacoes em enderecos de intranet sem HTTPS.
    return { ok: false, provider: "browser", error: "O navegador bloqueou a notificacao." };
  }
}

async function showTauriNotification(item, options = {}) {
  const invoke = tauriInvoke();
  if (!invoke) return { available: false, ok: false, provider: "tauri" };
  const nativePayload = nativeNotificationPayload(item);
  try {
    await invoke("notify_user", {
      title: nativePayload.title || item.title || "Nova notificacao",
      body: [nativePayload.message, nativePayload.meta].filter(Boolean).join("\n"),
    });
    return { available: true, ok: true, provider: "tauri" };
  } catch (error) {
    const message = String(error?.message || error || "Falha desconhecida na notificacao do Windows.");
    if (options.surfaceErrors) toast(message);
    return { available: true, ok: false, provider: "tauri", error: message };
  }
}

function playNotificationSound() {
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    audioContext = audioContext || new AudioContext();
    if (audioContext.state === "suspended") audioContext.resume();
    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(880, audioContext.currentTime);
    oscillator.frequency.exponentialRampToValueAtTime(660, audioContext.currentTime + 0.16);
    gain.gain.setValueAtTime(0.0001, audioContext.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.08, audioContext.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, audioContext.currentTime + 0.22);
    oscillator.connect(gain);
    gain.connect(audioContext.destination);
    oscillator.start();
    oscillator.stop(audioContext.currentTime + 0.24);
  } catch {
    // Audio pode ser bloqueado ate o primeiro clique do usuario.
  }
}

function updateDocumentTitle(count = state.notifications.length) {
  document.title = count ? `(${count}) ${BASE_TITLE}` : BASE_TITLE;
}

function syncTaskbarBadge(count = state.notifications.length) {
  const invoke = tauriInvoke();
  if (!invoke) return;
  invoke("set_taskbar_badge", { count: Number(count || 0) }).catch(() => {});
}

async function previewTaskbarBadge() {
  const invoke = tauriInvoke();
  if (!invoke) return;
  const previewCount = Math.max(1, Number(state.notifications.length || 0));
  try {
    await invoke("set_taskbar_badge", { count: previewCount });
    setTimeout(() => syncTaskbarBadge(), 3500);
  } catch (error) {
    toast(String(error?.message || error || "Falha ao aplicar contador na barra de tarefas."));
  }
}

function updateAlertButton() {
  const button = $("#notificationAlertsBtn");
  if (!button) return;
  const tauriAvailable = hasTauriNotifications();
  const nativeAvailable = tauriAvailable || canUseNativeNotifications();
  const hasNativeApi = hasNativeNotificationApi();
  const denied = !tauriAvailable && hasNativeApi && Notification.permission === "denied";
  button.classList.toggle("active", state.notificationAlertsEnabled);
  button.disabled = denied && !state.notificationAlertsEnabled;
  if (denied) {
    button.textContent = "Bloqueado";
    button.title = "Permissao de notificacao bloqueada no navegador.";
    return;
  }
  if (state.notificationAlertsEnabled) {
    button.textContent = tauriAvailable ? "Alertas Windows ativos" : nativeAvailable && Notification.permission === "granted" ? "Alertas Chrome ativos" : "Alertas locais";
    button.title = tauriAvailable || nativeAvailable ? "Clique para desativar os alertas." : "Som e contador da aba ativos. Para aparecer fora da guia, use localhost ou HTTPS.";
    return;
  }
  button.textContent = tauriAvailable ? "Ativar alertas Windows" : nativeAvailable ? "Permitir notificacoes" : "Ativar alertas locais";
  button.title = tauriAvailable ? "Ativar notificacoes nativas do aplicativo." : nativeAvailable ? "Pedir permissao do Chrome para notificar fora da guia." : "O Chrome exige localhost ou HTTPS para notificacoes fora da guia.";
}

function hasNativeNotificationApi() {
  return "Notification" in window;
}

function canUseNativeNotifications() {
  return hasNativeNotificationApi() && window.isSecureContext;
}

function hasTauriNotifications() {
  return Boolean(tauriInvoke());
}

function tauriInvoke() {
  return window.__TAURI__?.core?.invoke || window.__TAURI__?.tauri?.invoke || null;
}

function nativeNotificationPayload(item) {
  if (item.source !== "overview") return item;
  const { negociador, cliente } = monitorNotificationParts(item);
  return {
    ...item,
    title: "Monitoramento",
    message: `Negociador ${negociador} tem Cliente ${cliente}`,
    meta: item.meta || "",
  };
}

function notificationTime(item) {
  const raw = item.dataHora || "";
  const date = new Date(raw);
  if (!raw || Number.isNaN(date.getTime())) return item.source === "parecer" ? "Pendente" : "";
  return `${date.toLocaleDateString()} ${date.toLocaleTimeString()}`;
}
