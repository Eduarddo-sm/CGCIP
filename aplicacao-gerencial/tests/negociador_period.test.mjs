import assert from "node:assert/strict";
import test from "node:test";

import { periodRows } from "../ui/features/negociadorPeriod.js";

test("uses canonical competencia before the displayed agreement date", () => {
  const data = {
    headers: ["DATA ACORDO", "CLIENTE"],
    rows: [
      {
        competencia: "2026-08-01",
        "DATA ACORDO": "14/07/2026",
        CLIENTE: "POSTO IPUTINGA",
      },
    ],
  };

  assert.deepEqual(periodRows(data, { month: 7, year: 2026 }), []);
  assert.equal(periodRows(data, { month: 8, year: 2026 }).length, 1);
});
