export async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (response.status === 401) {
    location.href = "/login.html";
    throw new Error("Login necessario");
  }

  const contentType = response.headers.get("content-type") || "";
  let payload = {};

  if (response.status !== 204) {
    const body = await response.text();
    if (body) {
      if (contentType.includes("application/json")) {
        try {
          payload = JSON.parse(body);
        } catch {
          throw new Error("O servidor retornou uma resposta JSON invalida");
        }
      } else if (!response.ok) {
        throw new Error(`Falha ao acessar ${path} (${response.status})`);
      } else {
        throw new Error("O servidor retornou uma resposta inesperada");
      }
    }
  }
  if (!response.ok) throw new Error(payload.error || "Erro inesperado");
  return payload;
}
