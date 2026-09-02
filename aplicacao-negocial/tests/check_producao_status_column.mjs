import assert from "node:assert/strict";

import { buildProducaoColumns } from "../frontend/static/js/producao/columns.js";

const saves = [];
const columns = buildProducaoColumns({
  isAlpha: false,
  isBeta: false,
  isDynamic: true,
  dynamicColumns: [
    {
      chave: "STATUS",
      nome: "STATUS",
      tipo: "select",
      opcoes: ["PROPOSTA", "PROPOSTA_NEGADA", "QUEBRA"],
    },
  ],
  npjLabel: "NPJ",
  saveCell: (...args) => {
    saves.push(args);
    return args[0];
  },
});

const statusColumn = columns[0];
const item = {
  id: 42,
  cliente: "Cliente teste",
  status: "PROPOSTA_NEGADA",
  campos: { STATUS: "PROPOSTA_NEGADA" },
};

assert.equal(statusColumn.display(item), "Proposta negada");
assert.match(statusColumn.render(item), /status-proposta_negada/);
assert.match(statusColumn.render(item), />Proposta negada<\/option>/);

await statusColumn.save(item, "QUEBRA");
assert.equal(saves.length, 1);
assert.equal(saves[0][1], "status");
assert.equal(saves[0][2], "QUEBRA");

console.log("Dynamic production status column contract is valid.");
