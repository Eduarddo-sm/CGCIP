export async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    const detail = typeof body === "object" ? body?.detail : null;
    const message = Array.isArray(detail)
      ? detail.map((item) => item?.msg || String(item)).filter(Boolean).join(" ")
      : typeof detail === "string" && detail.trim()
        ? detail
        : typeof body === "string" && body.trim() && body.trim() !== "Internal Server Error"
          ? body.trim()
          : "Nao foi possivel completar a acao.";
    throw new Error(message);
  }

  return body;
}

export function apiGet(path) {
  return apiRequest(path);
}

export function apiPost(path, payload = {}) {
  return apiRequest(path, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function apiPut(path, payload = {}) {
  return apiRequest(path, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function apiPatch(path, payload = {}) {
  return apiRequest(path, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function apiDelete(path) {
  return apiRequest(path, {
    method: "DELETE",
    headers: {},
  });
}
