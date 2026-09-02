import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { SourceTextModule } from "node:vm";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const moduleCache = new Map();

async function loadModule(filePath) {
  const normalizedPath = resolve(filePath);
  if (moduleCache.has(normalizedPath)) return moduleCache.get(normalizedPath);

  const source = await readFile(normalizedPath, "utf8");
  const module = new SourceTextModule(source, {
    identifier: pathToFileURL(normalizedPath).href,
  });
  moduleCache.set(normalizedPath, module);
  await module.link(async (specifier, referencingModule) => {
    const targetUrl = new URL(specifier, referencingModule.identifier);
    targetUrl.search = "";
    targetUrl.hash = "";
    return loadModule(fileURLToPath(targetUrl));
  });
  return module;
}

for (const entry of ["frontend/static/js/app.js", "frontend/static/js/login.js"]) {
  await loadModule(resolve(projectRoot, entry));
}

console.log(`Linked ${moduleCache.size} frontend modules successfully.`);
