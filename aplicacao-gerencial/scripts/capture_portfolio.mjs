import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";


const outputDir = resolve(process.cwd(), "..", "docs", "portfolio");
const username = process.env.PORTFOLIO_DEMO_USERNAME || "admin.demo";
const password = process.env.PORTFOLIO_DEMO_PASSWORD;
const negocialUrl = process.env.PORTFOLIO_NEGOCIAL_URL || "http://127.0.0.1:8891";
const gerencialUrl = process.env.PORTFOLIO_GERENCIAL_URL || "http://127.0.0.1:8766";

if (!password) {
  throw new Error("Defina PORTFOLIO_DEMO_PASSWORD antes de gerar as capturas.");
}

await mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({
  viewport: { width: 1600, height: 1000 },
  deviceScaleFactor: 1,
  colorScheme: "light",
});
await context.addInitScript(() => {
  localStorage.setItem("theme", "light");
  localStorage.setItem("negocial.theme", "light");
});

async function screenshot(page, filename) {
  await page.waitForTimeout(700);
  await page.screenshot({ path: resolve(outputDir, filename), fullPage: false });
}

try {
  const negocial = await context.newPage();
  await negocial.goto(`${negocialUrl}/login`, { waitUntil: "networkidle" });
  await negocial.locator("#username").fill(username);
  await negocial.locator("#password").fill(password);
  await Promise.all([
    negocial.waitForURL((url) => !url.pathname.endsWith("/login")),
    negocial.locator("#loginButton").click(),
  ]);
  await negocial.waitForLoadState("networkidle");
  await screenshot(negocial, "01-negocial-producao.png");

  await negocial.locator("#openProducaoDialogBtn").click();
  await negocial.locator("#producaoDialog").waitFor({ state: "visible" });
  await screenshot(negocial, "02-negocial-novo-acordo.png");

  const gerencial = await context.newPage();
  await gerencial.goto(`${gerencialUrl}/login`, { waitUntil: "networkidle" });
  await gerencial.locator('[name="username"]').fill(username);
  await gerencial.locator('[name="password"]').fill(password);
  await Promise.all([
    gerencial.waitForURL((url) => !url.pathname.endsWith("/login")),
    gerencial.locator('#loginForm button[type="submit"]').click(),
  ]);
  await gerencial.waitForLoadState("networkidle");
  await gerencial.evaluate(() => {
    document.querySelector('[data-group-tool="configuracao"]')?.click();
  });
  await gerencial.evaluate(() => {
    document.querySelector('[data-config-page="ferramentas"]')?.click();
  });
  await gerencial.locator("#openDynamicToolBuilderBtn").waitFor({ state: "attached" });
  await gerencial.evaluate(() => {
    document.querySelector("#openDynamicToolBuilderBtn")?.click();
  });
  await gerencial.locator(".dynamic-tool-builder-dialog").waitFor({ state: "visible" });
  await screenshot(gerencial, "03-gerencial-construtor.png");

  await gerencial.locator('[data-builder-tab="telas"]').click();
  await screenshot(gerencial, "04-gerencial-configuracao-telas.png");
} finally {
  await browser.close();
}

console.log(`Capturas salvas em ${outputDir}`);
