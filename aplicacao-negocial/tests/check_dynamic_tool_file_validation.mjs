import assert from "node:assert/strict";
import { validateSelectedFiles } from "../frontend/static/js/fileValidation.js";

const field = {
  nome: "Parecer",
  opcoes: ["pdf"],
  validacao: { extensoes: ["pdf"], max_mb: 15, multiplo: false },
};

assert.throws(
  () => validateSelectedFiles([{ field, files: [{ name: "imagem.png", size: 1024 }] }]),
  /Formato nao permitido/
);
assert.doesNotThrow(
  () => validateSelectedFiles([{ field, files: [{ name: "parecer.pdf", size: 1024 }] }])
);
assert.throws(
  () => validateSelectedFiles([{ field, files: [{ name: "vazio.pdf", size: 0 }] }]),
  /esta vazio/
);

console.log("Dynamic tool attachment preflight is valid.");
