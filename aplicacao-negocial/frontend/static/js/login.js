import { apiGet, apiPost } from "./api.js?v=20260714-module-contract-1";

const form = document.querySelector("#loginForm");
const button = document.querySelector("#loginButton");
const errorBox = document.querySelector("#loginError");

async function redirectIfAuthenticated() {
  try {
    await apiGet("/api/me");
    window.location.href = "/";
  } catch (_error) {
    // Usuario ainda nao autenticado.
  }
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = false;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.hidden = true;
  button.disabled = true;
  button.textContent = "Entrando...";

  const payload = {
    username: form.username.value.trim(),
    password: form.password.value,
  };

  try {
    await apiPost("/api/login", payload);
    window.location.href = "/";
  } catch (error) {
    showError(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Entrar";
  }
});

redirectIfAuthenticated();
