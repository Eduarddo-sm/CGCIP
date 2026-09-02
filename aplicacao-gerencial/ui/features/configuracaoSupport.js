export function toolLabels(tools) {
  const labels = { producao: "Producao", pareceres: "Parecer" };
  const selected = Array.isArray(tools) && tools.length ? tools : ["producao", "pareceres"];
  return selected.map((tool) => labels[tool] || tool);
}

export function roleLabel(role) {
  const labels = {
    superadmin: "Superadministrador",
    admin: "Administrador",
    gerencial: "Gerencial",
    supervisor: "Supervisor",
    user: "Usuario",
  };
  return labels[String(role || "").toLowerCase()] || "Usuario";
}

export function money(value) {
  return Number(value || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function pageLabel(page) {
  return {
    usuarios: "users", auditoria: "audit", permissoes: "permission",
    schemas: "schema", ferramentas: "tool", backups: "backup", diagnostico: "diagnostic",
  }[page] || "users";
}

export function pageName(page) {
  return {
    usuarios: "Users", auditoria: "Audit", permissoes: "Permissions",
    schemas: "Schemas", ferramentas: "Tools", backups: "Backups", diagnostico: "Diagnostic",
  }[page] || "Users";
}

export function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("pt-BR");
}

export function formatFileSize(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
