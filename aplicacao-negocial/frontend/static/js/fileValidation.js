const DEFAULT_EXTENSIONS = ["pdf", "doc", "docx", "xls", "xlsx", "csv", "txt", "png", "jpg", "jpeg"];
const BLOCKED_EXTENSIONS = new Set(["exe", "dll", "bat", "cmd", "com", "js", "jse", "msi", "ps1", "scr", "vbs"]);

function normalizedExtensions(value) {
  const entries = Array.isArray(value) ? value : String(value || "").split(",");
  return entries
    .map((item) => String(item || "").trim().toLocaleLowerCase("pt-BR").replace(/^\./, ""))
    .filter(Boolean);
}

export function validateSelectedFiles(fileFields) {
  for (const { field, files } of fileFields) {
    const validation = field.validacao || {};
    const configured = normalizedExtensions(validation.extensoes || field.opcoes);
    const allowedExtensions = new Set(configured.length ? configured : DEFAULT_EXTENSIONS);
    const multiple = Boolean(validation.multiplo);
    const configuredMaxFiles = Number(validation.max_arquivos || (multiple ? 10 : 1));
    const configuredMaxMb = Number(validation.max_mb || 15);
    const maxFiles = Math.max(1, Math.min(Number.isFinite(configuredMaxFiles) ? configuredMaxFiles : 1, 20));
    const maxMb = Math.max(1, Math.min(Number.isFinite(configuredMaxMb) ? configuredMaxMb : 15, 100));
    const maxBytes = maxMb * 1024 * 1024;
    if ((!multiple && files.length > 1) || files.length > maxFiles) {
      throw new Error(`${field.nome} aceita no maximo ${maxFiles} arquivo(s).`);
    }
    for (const file of files) {
      const extension = String(file.name || "").split(".").pop()?.toLocaleLowerCase("pt-BR") || "";
      if (!extension || BLOCKED_EXTENSIONS.has(extension) || !allowedExtensions.has(extension)) {
        const expected = [...allowedExtensions].map((item) => `.${item}`).join(", ");
        throw new Error(`Formato nao permitido em ${field.nome}: ${file.name}. Use ${expected}.`);
      }
      if (!file.size) throw new Error(`${file.name} esta vazio.`);
      if (file.size > maxBytes) throw new Error(`${file.name} excede o limite de ${maxMb} MB.`);
    }
  }
}
