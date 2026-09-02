import { api } from "../core/api.js";

let timer = null;

export function startBackgroundOptimization() {
  window.setTimeout(requestBackgroundRefresh, 6000);
  clearInterval(timer);
  timer = setInterval(requestBackgroundRefresh, 10 * 60 * 1000);
}

export async function requestBackgroundRefresh() {
  try {
    await api("/api/background/refresh", { method: "POST", body: "{}" });
  } catch {
    // Background warming is opportunistic; visible pages keep their own error handling.
  }
}
