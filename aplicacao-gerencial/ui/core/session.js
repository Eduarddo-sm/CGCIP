import { api } from "./api.js";
import { readCache, removeCache, writeCache } from "./cache.js";
import { $ } from "./dom.js";
import { state } from "./state.js";

export async function loadSession() {
  const cachedUser = readCache("session.user", 24 * 60 * 60 * 1000);
  if (cachedUser) paintUser(cachedUser);
  const payload = await api("/api/me");
  state.user = payload.user;
  paintUser(state.user);
  writeCache("session.user", state.user);
}

export async function logout() {
  await api("/api/logout", { method: "POST", body: "{}" });
  removeCache("session.user");
  location.href = "/login.html";
}

function paintUser(user) {
  if (!user) return;
  state.user = user;
  $("#currentUser").textContent = user.username || "-";
  const roleLabels = {
    superadmin: "Superadministrador",
    admin: "Administrador",
    gerencial: "Gerencial",
    supervisor: "Supervisor",
    user: "Usuario",
  };
  $("#currentRole").textContent = roleLabels[String(user.role || "").toLowerCase()] || "Usuario";
  $("#profileInitial").textContent = String(user.username || "-").slice(0, 1).toUpperCase();
}
