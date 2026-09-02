import { expect, test } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import path from "node:path";

const GERENCIAL = process.env.GERENCIAL_E2E_URL || "http://127.0.0.1:8765";
const NEGOCIAL = process.env.NEGOCIAL_E2E_URL || "http://127.0.0.1:8890";

function capturePageErrors(page) {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.stack || error.message));
  return errors;
}

test("login pages render without JavaScript errors", async ({ page }) => {
  const errors = capturePageErrors(page);
  await page.goto(`${GERENCIAL}/login.html`);
  await expect(page.locator("#loginForm")).toBeVisible();
  await expect(page.getByRole("button", { name: "Entrar" })).toBeVisible();

  await page.goto(`${NEGOCIAL}/login`);
  await expect(page.locator("#loginForm")).toBeVisible();
  await expect(page.getByRole("button", { name: "Entrar" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("sync coordinator keeps the negotiator profile stable", async ({ page }) => {
  await page.goto(`${GERENCIAL}/login.html`);
  const calls = await page.evaluate(async () => {
    const { startSyncCoordinator } = await import(`/core/syncCoordinator.js?test=${Date.now()}`);
    const counters = { negotiator: 0, notifications: 0 };
    const stop = startSyncCoordinator({
      getMode: () => "negociador",
      refreshNegotiator: async () => { counters.negotiator += 1; },
      refreshNotifications: async () => { counters.notifications += 1; },
      tickMs: 10,
    });
    await new Promise((resolve) => window.setTimeout(resolve, 45));
    stop();
    return counters;
  });
  expect(calls.negotiator).toBe(0);
  expect(calls.notifications).toBeGreaterThan(0);
});

test("negocial conditional required fields do not block form submission while hidden", async ({ page }) => {
  await page.goto(`${NEGOCIAL}/login`);
  const result = await page.evaluate(async () => {
    const { syncConditionalControlState } = await import(`/static/js/ferramentas.js?test=${Date.now()}`);
    const form = document.createElement("form");
    form.innerHTML = '<label data-field-wrap="ENTRADA"><input required></label>';
    document.body.append(form);
    const wrapper = form.querySelector("[data-field-wrap]");
    const input = form.querySelector("input");
    syncConditionalControlState(wrapper, false);
    const hidden = { valid: form.checkValidity(), disabled: input.disabled, required: input.required };
    syncConditionalControlState(wrapper, true);
    const visible = { valid: form.checkValidity(), disabled: input.disabled, required: input.required };
    form.remove();
    return { hidden, visible };
  });
  expect(result.hidden).toEqual({ valid: true, disabled: true, required: false });
  expect(result.visible).toEqual({ valid: false, disabled: false, required: true });
});

test("gerencial authenticates and loads its module shell", async ({ page }) => {
  const username = process.env.GERENCIAL_E2E_USERNAME;
  const password = process.env.GERENCIAL_E2E_PASSWORD;
  test.skip(!username || !password, "Defina credenciais E2E do Gerencial.");
  const errors = capturePageErrors(page);

  await page.goto(`${GERENCIAL}/login.html`);
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL(`${GERENCIAL}/`, { waitUntil: "domcontentloaded" });
  await expect(page.locator("#currentUser")).toHaveText(username);
  await expect(page.locator("#pageTitle")).toBeVisible();
  await expect(page.locator("#notificationBtn")).toBeVisible();

  await page.locator("#mainHubBtn").click();
  await expect(page.locator("#mainHubContent .main-hub-command-bar")).toBeVisible();
  await expect(page.locator("#mainHubContent .main-hub-metrics")).toBeVisible();
  await expect(page.locator("#mainHubContent .main-hub-head")).toHaveCount(0);
  const hubRows = page.locator("#mainHubList .hub-card");
  if (await hubRows.count()) {
    const firstHubRowHeight = await hubRows.first().evaluate((element) => element.getBoundingClientRect().height);
    expect(firstHubRowHeight).toBeLessThanOrEqual(64);
    await expect(page.locator("#mainHubList .hub-period-group").first()).toBeVisible();
    await hubRows.first().click();
    await expect(page.locator("#mainHubDialog")).toBeVisible();
    await expect(page.locator("#mainHubDialog .hub-info-grid")).toBeVisible();
    await expect(page.locator("#mainHubDialog .hub-notes-disclosure")).toBeVisible();
    await expect(page.locator("#mainHubDialogFooter")).toBeVisible();
    await page.locator("#mainHubDialog [data-close-hub]").click();
    await expect(page.locator("#mainHubDialog")).not.toBeVisible();
  }

  await page.locator("#sidebarToggleBtn").click();
  await page.locator("#toolMenuBtn").click();
  await expect(page.locator(".sidebar")).toHaveClass(/group-menu-open/);
  await expect(page.locator("#groupDropdown")).toBeVisible();
  const menuLayers = await page.evaluate(() => ({
    sidebar: Number.parseInt(getComputedStyle(document.querySelector(".sidebar")).zIndex, 10),
    header: Number.parseInt(getComputedStyle(document.querySelector(".topbar")).zIndex, 10),
  }));
  expect(menuLayers.sidebar).toBeGreaterThan(menuLayers.header);
  await page.locator("#toolMenuBtn").click();
  await expect(page.locator(".sidebar")).not.toHaveClass(/group-menu-open/);

  await page.locator('[data-tool="monitoramento"]').click();
  await expect(page.locator("#pageTitleIcon")).toHaveAttribute("src", /monitoring-9\.svg$/);
  await page.locator("#negociadoresBtn").click();
  await expect(page.locator("#negociadoresBtn")).toHaveClass(/active/);
  await expect(page.locator("#pageTitle")).toHaveText("Negociadores");
  await expect(page.locator("#negociadoresContent")).toBeVisible();
  await page.locator("#overviewBtn").click();
  await expect(page.locator("#overviewContent .overview-command-bar")).toBeVisible();
  await expect(page.locator("#overviewViewSummary")).toBeVisible();
  await page.locator(".overview-filter-panel > summary").click();
  await expect(page.locator(".overview-filter-panel .overview-filters")).toBeVisible();
  await page.locator(".overview-filter-panel > summary").click();
  const overviewRows = page.locator("#overviewList .overview-item");
  if (await overviewRows.count()) {
    const firstOverviewRow = overviewRows.first();
    const rowBox = await firstOverviewRow.boundingBox();
    expect(rowBox.height).toBeLessThanOrEqual(72);
    await expect(firstOverviewRow).toHaveAttribute("tabindex", "0");
  }
  for (const status of ["read", "all"]) {
    await page.locator(`[data-overview-status="${status}"]`).click();
    const statusRows = page.locator("#overviewList .overview-item");
    await expect(statusRows.first()).toBeVisible({ timeout: 20_000 });
    const firstGroup = page.locator("#overviewList .overview-group").first();
    await expect(firstGroup).toBeVisible({ timeout: 20_000 });
    const firstGroupHeight = await firstGroup.evaluate((element) => element.getBoundingClientRect().height);
    expect(firstGroupHeight).toBeGreaterThanOrEqual(58);
    if (status === "all") {
      await statusRows.first().click();
      await expect(page.locator("#overviewDrawer")).toHaveClass(/open/);
      await expect(page.locator("#overviewDrawerTitle")).not.toHaveText("");
      await expect(page.locator("#overviewDrawer .overview-audit-meta")).toBeVisible();
      await expect(page.locator("#overviewDrawer .overview-audit-comparison")).toBeVisible();
      await expect(page.locator("#overviewDrawerFooter")).toBeVisible();
      await page.locator("#overviewDrawer [data-close-overview]").click();
      await expect(page.locator("#overviewDrawer")).not.toHaveClass(/open/);
    }
  }
  await page.locator('[data-overview-status="unread"]').click();
  const headerGeometry = await page.locator(".topbar, .topbar-main, .module-tabs-row").evaluateAll(([header, main, tabs]) => ({
    header: Math.round(header.getBoundingClientRect().height),
    main: Math.round(main.getBoundingClientRect().height),
    tabs: Math.round(tabs.getBoundingClientRect().height),
    headerWidth: Math.round(header.getBoundingClientRect().width),
    mainWidth: Math.round(main.getBoundingClientRect().width),
    tabsWidth: Math.round(tabs.getBoundingClientRect().width),
  }));
  expect(headerGeometry.header).toBeLessThanOrEqual(93);
  expect(headerGeometry.main).toBe(52);
  expect(headerGeometry.tabs).toBe(40);
  expect(headerGeometry.mainWidth).toBe(headerGeometry.headerWidth);
  expect(headerGeometry.tabsWidth).toBe(headerGeometry.headerWidth);
  const headerAlignment = await page.evaluate(() => {
    const header = document.querySelector(".topbar").getBoundingClientRect();
    const actions = document.querySelector(".topbar .actions").getBoundingClientRect();
    const moduleAction = document.querySelector(".module-action-slot").getBoundingClientRect();
    return {
      actionsRightGap: Math.round(header.right - actions.right),
      moduleActionRightGap: Math.round(header.right - moduleAction.right),
    };
  });
  expect(headerAlignment.actionsRightGap).toBeLessThanOrEqual(25);
  expect(headerAlignment.moduleActionRightGap).toBeLessThanOrEqual(21);

  for (const tool of ["monitoramento", "parecer", "protocolo", "colchao"]) {
    const button = page.locator(`[data-tool="${tool}"]`);
    if (await button.count()) {
      await button.click();
      await expect(page.locator("#pageTitle")).not.toHaveText("");
    }
  }
  await expect(page.locator(".topbar")).toHaveClass(/tabs-hidden/);
  await expect(page.locator(".module-tabs-row")).toBeHidden();
  const profileHomeSpacing = await page.evaluate(() => {
    const header = document.querySelector(".topbar").getBoundingClientRect();
    const content = document.querySelector(".colchao-profile-home").getBoundingClientRect();
    return {
      headerHeight: Math.round(header.height),
      contentGap: Math.round(content.top - header.bottom),
      leftGap: Math.round(content.left - header.left),
      rightGap: Math.round(header.right - content.right),
    };
  });
  expect(profileHomeSpacing.headerHeight).toBeLessThanOrEqual(53);
  expect(profileHomeSpacing.contentGap).toBeLessThanOrEqual(12);
  expect(profileHomeSpacing.leftGap).toBeLessThanOrEqual(20);
  expect(profileHomeSpacing.rightGap).toBeLessThanOrEqual(20);
  expect(errors).toEqual([]);
});

test("production intelligence renders all analytical topics", async ({ page }) => {
  test.setTimeout(60_000);
  const username = process.env.GERENCIAL_E2E_USERNAME;
  const password = process.env.GERENCIAL_E2E_PASSWORD;
  test.skip(!username || !password, "Defina credenciais E2E do Gerencial.");
  const errors = capturePageErrors(page);

  await page.goto(`${GERENCIAL}/login.html`);
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL(`${GERENCIAL}/`, { waitUntil: "domcontentloaded" });

  await page.locator("#toolMenuBtn").click();
  await page.locator('[data-group-tool="analise"]').click();
  const analysisNav = page.locator("#analiseToolDropdown");
  await expect(analysisNav).toBeVisible();
  await expect(analysisNav).toHaveClass(/app-module-nav/);
  const expandedSidebarLayout = await page.evaluate(() => {
    const sidebar = document.querySelector(".sidebar").getBoundingClientRect();
    const brand = document.querySelector("#toolMenuBtn").getBoundingClientRect();
    const nav = document.querySelector("#analiseToolDropdown").getBoundingClientRect();
    return { sidebar, brand, nav };
  });
  expect(expandedSidebarLayout.nav.left).toBeGreaterThanOrEqual(expandedSidebarLayout.sidebar.left);
  expect(expandedSidebarLayout.nav.right).toBeLessThanOrEqual(expandedSidebarLayout.sidebar.right);
  expect(expandedSidebarLayout.nav.top).toBeGreaterThanOrEqual(expandedSidebarLayout.brand.bottom);

  await page.locator("#sidebarToggleBtn").click();
  await expect(page.locator("body")).toHaveClass(/sidebar-collapsed/);
  await page.waitForTimeout(250);
  const collapsedSidebarLayout = await page.evaluate(() => {
    const sidebar = document.querySelector(".sidebar").getBoundingClientRect();
    const brand = document.querySelector("#toolMenuBtn").getBoundingClientRect();
    const nav = document.querySelector("#analiseToolDropdown").getBoundingClientRect();
    return { sidebar, brand, nav };
  });
  expect(collapsedSidebarLayout.nav.left).toBeGreaterThanOrEqual(collapsedSidebarLayout.sidebar.left);
  expect(collapsedSidebarLayout.nav.right).toBeLessThanOrEqual(collapsedSidebarLayout.sidebar.right);
  expect(collapsedSidebarLayout.nav.top).toBeGreaterThan(collapsedSidebarLayout.brand.bottom);
  await expect(page.locator("#pageTitle")).toHaveText("Inteligência de Produção");
  await expect(page.locator("#analyticsWorkspace")).toBeVisible({ timeout: 30_000 });
  await page.locator("#analyticsFiltersToggleBtn").click();
  await expect(page.locator("#analyticsAdvancedFilters")).toBeVisible();
  await page.locator("#analyticsWalletFilter").selectOption("GAMMA");
  await expect(page.locator("#analyticsActiveFilterCount")).toHaveText("1");
  await expect(page.locator('#analyticsActiveFilters [data-clear-analytics-filter="analyticsWalletFilter"]')).toBeVisible();
  await page.locator('#analyticsActiveFilters [data-clear-analytics-filter="analyticsWalletFilter"]').click();
  await expect(page.locator("#analyticsActiveFilterCount")).toBeHidden();
  await page.locator("#analyticsPeriodScopeFilter").selectOption("journey");
  await expect(page.locator("#analyticsMonthNavigation")).toBeHidden();
  await page.locator("#analyticsPeriodScopeFilter").selectOption("month");
  await expect(page.locator("#analyticsMonthNavigation")).toBeVisible();
  await expect(page.locator("#analyticsWorkspace")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("#analyticsKpis .analytics-kpi")).toHaveCount(6);
  await expect(page.locator("#analyticsTrendChart svg")).toBeVisible();
  await page.locator("#analyticsExecutiveTrendMetric").selectOption("breaks_value");
  const executiveTrendPoint = page.locator("#analyticsTrendChart [data-executive-trend-date]").nth(2);
  await expect(executiveTrendPoint).toBeVisible();
  await executiveTrendPoint.click();
  await expect(page.locator("#analyticsDrawer")).toBeVisible();
  await expect(page.locator("[data-negotiator-agreements]")).toBeVisible();
  await page.locator("#analyticsDrawerClose").click();

  await page.locator('[data-analysis-page="wallets"]').click();
  await expect(page.locator('[data-analysis-panel="wallets"]')).toBeVisible();
  expect(await page.locator("#analyticsWalletTabs [data-wallet-tab]").count()).toBeGreaterThanOrEqual(3);
  await expect(page.locator('#analyticsWalletTabs [data-wallet-tab="GAMMA"]')).toHaveClass(/active/);
  expect(await page.locator("#analyticsWalletKpis .analytics-wallet-kpi").count()).toBeGreaterThanOrEqual(5);
  await expect(page.locator("#analyticsWalletTrend")).not.toBeEmpty();
  await expect(page.locator("#analyticsWalletNegotiators")).not.toBeEmpty();
  await page.locator('#analyticsWalletTabs [data-wallet-tab="ALPHA"]').click();
  await expect(page.locator("#analyticsWalletPortfolioPanel")).toBeVisible();
  await expect(page.locator("#analyticsWalletPortfolioRows tr").first()).toBeVisible();
  await page.locator('#analyticsWalletTabs [data-wallet-tab="BETA"]').click();
  await expect(page.locator("#analyticsWalletPortfolioPanel")).toBeVisible();
  await page.locator('#analyticsWalletTabs [data-wallet-tab="GAMMA"]').click();
  await expect(page.locator("#analyticsWalletGammaHonorariosPanel")).toBeVisible();
  await expect(page.locator("#analyticsWalletGammaFunnel [data-analytics-kind='status']")).toHaveCount(4);
  await expect(page.locator("#analyticsWalletGammaGecorPanel")).toBeVisible();
  await page.locator("#analyticsWalletTrendMetric").selectOption("paid_value");
  await expect(page.locator("#analyticsWalletTrend .analytics-wallet-trend-svg")).toBeVisible();
  const firstTrendPoint = page.locator("#analyticsWalletTrend [data-wallet-trend-date]").nth(2);
  await expect(firstTrendPoint).toBeVisible();
  await firstTrendPoint.click();
  await expect(page.locator("#analyticsDrawer")).toBeVisible();
  await expect(page.locator("[data-negotiator-agreements]")).toBeVisible();
  await page.locator("#analyticsDrawerClose").click();
  const firstState = page.locator("#analyticsWalletGammaStates [data-analytics-kind='wallet-dimension']").first();
  await expect(firstState).toBeVisible();
  await firstState.click();
  await expect(page.locator("#analyticsDrawer")).toBeVisible();
  await expect(page.locator("[data-negotiator-agreements]")).toBeVisible();
  await page.locator("#analyticsDrawerClose").click();
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    document.querySelectorAll("main, .main-content, .workspace").forEach((element) => {
      element.scrollTop = 0;
    });
  });
  await page.screenshot({ path: "test-results/production-intelligence-wallets.png", fullPage: true });

  for (const topic of ["negotiators", "pipeline", "executive"]) {
    await page.locator(`[data-analysis-page="${topic}"]`).click();
    await expect(page.locator(`[data-analysis-panel="${topic}"]`)).toBeVisible();
  }

  await page.screenshot({ path: "test-results/production-intelligence.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("pending queues expose copyable client identifiers", async ({ page }) => {
  test.setTimeout(60_000);
  const username = process.env.GERENCIAL_E2E_USERNAME;
  const password = process.env.GERENCIAL_E2E_PASSWORD;
  test.skip(!username || !password, "Defina credenciais E2E do Gerencial.");
  const errors = capturePageErrors(page);

  await page.goto(`${GERENCIAL}/login.html`);
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL(`${GERENCIAL}/`);

  await page.locator('[data-tool="protocolo"]').click();
  await page.locator('[data-protocolo-page="monitoramento"]').click();
  const protocolRow = page.locator("#protocoloOpenGrid .protocolo-queue-row").first();
  await expect(protocolRow).toBeVisible({ timeout: 20_000 });
  const protocolValues = protocolRow.locator("[data-pending-select-value]");
  await expect(protocolValues).toHaveCount(2);
  for (const value of await protocolValues.all()) {
    await expect(value).toHaveCSS("user-select", "all");
    await value.click();
    await expect(protocolRow.locator(".protocolo-queue-details")).toBeHidden();
  }

  await page.locator('[data-tool="parecer"]').click();
  await page.locator('[data-parecer-page="pendentes"]').click();
  const opinionRow = page.locator("#parecerPendentesGrid .parecer-queue-row").first();
  const opinionCount = await opinionRow.count();
  if (opinionCount) {
    await expect(opinionRow).toBeVisible({ timeout: 20_000 });
    const opinionValues = opinionRow.locator("[data-pending-select-value]");
    await expect(opinionValues).toHaveCount(2);
    for (const value of await opinionValues.all()) {
      await expect(value).toHaveCSS("user-select", "all");
      await value.click();
      await expect(opinionRow.locator(".parecer-queue-details")).toBeHidden();
    }
  } else {
    await expect(page.locator("#parecerPendentesGrid .parecer-empty-state")).toBeVisible({ timeout: 20_000 });
  }
  expect(errors).toEqual([]);
});

test("colchao pending queue groups and expands records", async ({ page }) => {
  test.setTimeout(90_000);
  const username = process.env.GERENCIAL_E2E_USERNAME;
  const password = process.env.GERENCIAL_E2E_PASSWORD;
  test.skip(!username || !password, "Defina credenciais E2E do Gerencial.");
  const errors = capturePageErrors(page);
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"], { origin: GERENCIAL });
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (value) => { window.__colchaoCopiedValue = value; },
        readText: async () => window.__colchaoCopiedValue || "",
      },
    });
  });

  await page.goto(`${GERENCIAL}/login.html`);
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL(`${GERENCIAL}/`);
  await page.locator('[data-tool="colchao"]').click();
  await page.locator('[data-colchao-profile="alpha"]').click();
  const pendingSearch = await page.evaluate(async () => {
    const response = await fetch("/api/colchao/pendencias?profile=alpha");
    if (!response.ok) throw new Error(`Falha ao carregar pendencias do colchao: ${response.status}`);
    const rows = await response.json();
    const first = rows[0] || {};
    return String(first.CLIENTE || first.NOME || first["DEBIT ID"] || first.SUITID || "").trim();
  });
  expect(pendingSearch).not.toBe("");
  await page.locator("#colchaoPendingSearch").evaluate((input, value) => { input.value = value; }, pendingSearch);
  await expect(page.locator(".topbar")).not.toHaveClass(/tabs-hidden/);
  await expect(page.locator(".module-tabs-row")).toBeVisible();
  await page.locator('[data-colchao-page="pendencias"]').click();

  const pageRoot = page.locator("#colchaoPendencias");
  await expect(pageRoot).toBeVisible();
  await expect(pageRoot.locator(".colchao-queue-toolbar")).toBeVisible();
  const rows = pageRoot.locator(".colchao-queue-row");
  await expect(rows.first()).toBeVisible({ timeout: 30_000 });
  await expect(pageRoot.locator(".colchao-queue-summary")).toContainText("pendências");

  const firstGroup = pageRoot.locator("[data-colchao-pending-group]").first();
  await expect(firstGroup).toHaveAttribute("aria-expanded", "true");
  await firstGroup.click();
  await expect(firstGroup).toHaveAttribute("aria-expanded", "false");
  await firstGroup.click();
  const firstIdentifier = rows.first().locator("[data-colchao-select-id]");
  const firstClientName = rows.first().locator(".colchao-queue-identity strong[data-colchao-select-value]");
  const firstDocumentNumber = rows.first().locator(".colchao-queue-identity small [data-colchao-select-value]").last();
  for (const selectableValue of [firstIdentifier, firstClientName, firstDocumentNumber]) {
    await expect(selectableValue).toBeVisible();
    await expect(selectableValue).toHaveCSS("user-select", "all");
    await selectableValue.click();
    await expect(rows.first().locator(".colchao-queue-details")).toBeHidden();
  }
  const expandedState = await rows.first().locator("[data-colchao-pending-expand]").evaluate((button) => {
    button.click();
    return button.getAttribute("aria-expanded");
  });
  expect(expandedState).toBe("true");
  await page.screenshot({ path: "test-results/colchao-pending-queue.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("colchao spreadsheet prioritizes the grid and consolidates observations", async ({ page }) => {
  test.setTimeout(60_000);
  const username = process.env.GERENCIAL_E2E_USERNAME;
  const password = process.env.GERENCIAL_E2E_PASSWORD;
  test.skip(!username || !password, "Defina credenciais E2E do Gerencial.");
  const errors = capturePageErrors(page);

  await page.goto(`${GERENCIAL}/login.html`);
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL(`${GERENCIAL}/`);
  await page.locator('[data-tool="colchao"]').click();
  await page.locator('[data-colchao-profile="alpha"]').click();
  await page.locator('[data-colchao-page="completo"]').click();

  const sheet = page.locator("#colchaoCompleto");
  const grid = page.locator("#colchaoCompletoGrid");
  await expect(sheet.locator(".colchao-sheet-commandbar")).toBeVisible();
  await expect(grid.locator(".excel-grid-shell")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("#colchaoSaveChangesBtn")).toBeHidden();

  const observationHeaders = (await grid.locator(".excel-field-title").allTextContents())
    .filter((title) => /^(obs|observa)/i.test(title.trim()));
  expect(observationHeaders).toEqual(["Observações"]);

  const initialTotal = await page.locator("#colchaoPageInfo").textContent();
  await page.locator("#colchaoFullSearch").fill("CELIO ROBERTO VACARE");
  await expect(page.locator("#colchaoClearQuickFiltersBtn")).toBeVisible({ timeout: 30_000 });
  await expect.poll(() => page.locator("#colchaoPageInfo").textContent()).not.toBe(initialTotal);
  await page.locator("#colchaoClearQuickFiltersBtn").click();
  await expect(page.locator("#colchaoPageInfo")).toHaveText(initialTotal, { timeout: 30_000 });

  const status = grid.locator("[data-colchao-batch-select]").first();
  await expect(status).toBeVisible();
  const original = await status.inputValue();
  const replacement = original === "PAGO" ? "VENCIDO" : "PAGO";
  await status.selectOption(replacement);
  await expect(page.locator("#colchaoSaveChangesBtn")).toBeVisible();
  await expect(page.locator("#colchaoSheetState")).toContainText("pendente");
  await status.selectOption(original);
  await expect(page.locator("#colchaoSaveChangesBtn")).toBeHidden();
  await expect(page.locator("#colchaoSheetState")).toHaveText("Sem alterações pendentes");

  const bounds = await grid.boundingBox();
  const viewport = page.viewportSize();
  expect(bounds.height).toBeGreaterThan(560);
  expect(viewport.height - bounds.y - bounds.height).toBeLessThan(12);

  await page.locator("#colchaoExpandSpreadsheetBtn").click();
  const focus = page.locator("#colchaoExpandedDialog");
  await expect(focus).toBeVisible();
  const focusBounds = await focus.boundingBox();
  expect(focusBounds.width).toBeGreaterThanOrEqual(viewport.width - 1);
  expect(focusBounds.height).toBeGreaterThanOrEqual(viewport.height - 1);
  await page.locator("[data-close-colchao-expanded]").click();
  await page.screenshot({ path: "test-results/colchao-sheet-workspace.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("colchao agreement form is compact and calculates its summary", async ({ page }) => {
  test.setTimeout(45_000);
  const username = process.env.GERENCIAL_E2E_USERNAME;
  const password = process.env.GERENCIAL_E2E_PASSWORD;
  test.skip(!username || !password, "Defina credenciais E2E do Gerencial.");
  const errors = capturePageErrors(page);

  await page.goto(`${GERENCIAL}/login.html`);
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL(`${GERENCIAL}/`);
  await page.locator('[data-tool="colchao"]').click();
  await page.locator('[data-colchao-profile="alpha"]').click();
  await expect(page.locator('[data-colchao-page="historico"]')).toHaveCount(0);
  await page.locator('[data-colchao-page="cadastro"]').click();

  const form = page.locator("#colchaoAgreementForm");
  await expect(form).toBeVisible();
  await expect(form.locator(".colchao-form-section")).toHaveCount(3);
  await expect(form.locator(".colchao-agreement-summary")).toBeVisible();
  await expect(page.locator("#colchaoAgreementSubmitBtn")).toBeDisabled();

  await form.locator('[name="debit_id"]').fill("87654321");
  await form.locator('[name="cpf_cnpj"]').fill("12345678901");
  await form.locator('[name="cliente"]').fill("CLIENTE DE TESTE VISUAL");
  await form.locator('[name="valor_acordo"]').fill("1000,00");
  await form.locator('[name="entrada"]').fill("100,00");
  await form.locator('[name="parcelas"]').fill("3");
  await form.locator('[name="data_vencimento"]').fill("2026-08-15");
  await form.locator('[name="tipo_acordo"]').selectOption("PARCELADO");
  await form.locator('[name="operador"]').fill("OPERADOR TESTE");

  await expect(page.locator("#colchaoAgreementProgress")).toHaveText("9 de 9 campos obrigatórios preenchidos");
  await expect(page.locator("#colchaoSummaryTotal")).toHaveText("R$ 1.000,00");
  await expect(page.locator("#colchaoSummaryBalance")).toHaveText("R$ 900,00");
  await expect(page.locator("#colchaoSummaryInstallmentValue")).toHaveText("R$ 450,00");
  await expect(page.locator("#colchaoSummaryLastDue")).toHaveText("15/10/2026");
  await expect(page.locator("#colchaoAgreementSubmitBtn")).toBeEnabled();
  await page.screenshot({ path: "test-results/colchao-agreement-form.png", fullPage: true });

  await form.getByRole("button", { name: "Limpar" }).click();
  await expect(page.locator("#colchaoAgreementSubmitBtn")).toBeDisabled();
  await expect(page.locator("#colchaoSummaryTotal")).toHaveText("R$ 0,00");

  await page.locator("#colchaoBackProfilesTopBtn").click();
  await page.locator('[data-colchao-profile="beta"]').click();
  await page.locator('[data-colchao-page="cadastro"]').click();
  await expect(page.locator("#colchaoProcessoField")).toBeVisible();
  await expect(page.locator("#colchaoSuitField")).toBeVisible();
  await expect(page.locator("#colchaoDebitField")).toBeHidden();
  await expect(page.locator("#colchaoCpfField")).toBeHidden();
  await expect(page.locator("#colchaoTipoAcordoField")).toBeHidden();
  await expect(page.locator("#colchaoCadastroSheetField")).toBeVisible();
  await expect(page.locator("#colchaoSummaryProfile")).toHaveText("Beta");
  expect(errors).toEqual([]);
});

test("gerencial wallet schema editor uses the executive full-screen layout", async ({ page }) => {
  const username = process.env.GERENCIAL_E2E_USERNAME;
  const password = process.env.GERENCIAL_E2E_PASSWORD;
  test.skip(!username || !password, "Defina credenciais E2E do Gerencial.");
  const errors = capturePageErrors(page);

  await page.goto(`${GERENCIAL}/login.html`);
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL(`${GERENCIAL}/`);
  await page.locator('[data-tool="monitoramento"]').click();
  await page.locator("#carteirasBtn").click();
  await page.locator("#addCarteiraBtn").click();

  const dialog = page.locator("#carteiraDialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.locator(".carteira-basics-panel")).toBeVisible();
  await expect(dialog.locator(".carteira-ho-panel")).toBeVisible();
  await expect(dialog.locator(".carteira-schema-scroll")).toBeVisible();
  const bounds = await dialog.boundingBox();
  const viewport = page.viewportSize();
  expect(bounds.x).toBeLessThanOrEqual(1);
  expect(bounds.y).toBeLessThanOrEqual(1);
  expect(bounds.width).toBeGreaterThanOrEqual(viewport.width - 1);
  expect(bounds.height).toBeGreaterThanOrEqual(viewport.height - 1);

  const initialColumns = await dialog.locator("[data-carteira-column]").count();
  expect(initialColumns).toBeGreaterThan(0);
  await dialog.locator("#addCarteiraColumnBtn").click();
  await expect(dialog.locator("[data-carteira-column]")).toHaveCount(initialColumns + 1);
  const newColumnType = dialog.locator("[data-carteira-column]").last().locator('[name="column_tipo"]');
  await expect(newColumnType.locator('option[value="multiselect"]')).toHaveText("Selecao multipla");
  await newColumnType.selectOption("multiselect");
  await expect(newColumnType).toHaveValue("multiselect");
  await dialog.locator("[data-close-carteira]").first().click();
  await expect(dialog).not.toBeVisible();
  expect(errors).toEqual([]);
});

test("gerencial opens a wallet as an integrated operational workspace", async ({ page }) => {
  const username = process.env.GERENCIAL_E2E_USERNAME;
  const password = process.env.GERENCIAL_E2E_PASSWORD;
  test.skip(!username || !password, "Defina credenciais E2E do Gerencial.");
  const errors = capturePageErrors(page);

  await page.goto(`${GERENCIAL}/login.html`);
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL(`${GERENCIAL}/`);
  await page.locator('[data-tool="monitoramento"]').click();
  await page.locator("#carteirasBtn").click();

  const wallet = page.locator("[data-open-carteira-workspace]").first();
  await expect(wallet).toBeVisible();
  await wallet.click();
  await expect(page.locator("#carteiraDetailView")).toBeVisible();
  await expect(page.locator("#carteiraWorkspaceTabs")).toBeVisible();
  await expect(page.locator('[data-carteira-workspace-tab="overview"]')).toHaveClass(/active/);
  await expect(page.locator("#carteiraWorkspaceOverview .carteira-workspace-summary")).toBeVisible();

  await page.locator('[data-carteira-workspace-tab="production"]').click();
  await expect(page.locator("#carteiraWorkspaceProduction .carteira-sheet-head")).toBeVisible();
  await expect(page.locator("#carteiraWorkspaceProduction .excel-grid-shell")).toBeVisible();
  const editableProductionCell = page.locator("#carteiraWorkspaceProduction .excel-cell.editable").first();
  await expect(editableProductionCell).toBeVisible();
  await editableProductionCell.dblclick();
  await expect(editableProductionCell.locator(".excel-cell-editor")).toBeVisible();
  await page.keyboard.press("Escape");
  const productionOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(productionOverflow).toBeLessThanOrEqual(2);
  const productionBounds = await page.locator("#carteiraWorkspaceProduction .carteira-workspace-grid").boundingBox();
  const productionPanelBounds = await page.locator("#carteiraWorkspaceProduction").boundingBox();
  expect(productionBounds.width).toBeLessThanOrEqual(productionPanelBounds.width + 1);
  await page.locator("#carteiraWorkspaceProduction [data-carteira-sheet-focus]").click();
  await expect(page.locator("body")).toHaveClass(/carteira-workspace-focus-mode/);
  await expect(page.locator("#carteiraWorkspaceProduction")).toHaveClass(/workspace-focus-target/);
  await page.locator("#carteiraWorkspaceProduction [data-carteira-sheet-focus]").click();
  await expect(page.locator("body")).not.toHaveClass(/carteira-workspace-focus-mode/);

  await page.locator('[data-carteira-workspace-tab="monitor"]').click();
  await expect(page.locator(".carteira-monitor-controls")).toBeVisible();
  await expect(page.locator("#carteiraMonitor")).toBeVisible();

  const dynamicTool = page.locator("[data-carteira-tool]").first();
  if (await dynamicTool.count()) {
    await dynamicTool.click();
    await expect(page.locator("#carteiraWorkspaceDynamic .carteira-sheet-head")).toBeVisible();
    await expect(page.locator("#carteiraWorkspaceDynamic .excel-grid-shell")).toBeVisible();
    const editableToolCell = page.locator("#carteiraWorkspaceDynamic .excel-cell.editable").first();
    await expect(editableToolCell).toBeVisible();
    await editableToolCell.dblclick();
    await expect(editableToolCell.locator(".excel-cell-editor")).toBeVisible();
    await page.keyboard.press("Escape");
    const dynamicOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(dynamicOverflow).toBeLessThanOrEqual(2);
  }

  await page.locator('[data-carteira-workspace-tab="settings"]').click();
  await expect(page.locator("#carteiraWorkspaceSettings .carteira-settings-grid")).toBeVisible();
  const productionToggle = page.locator('[data-wallet-tool-toggle="producao"]');
  await expect(productionToggle).toBeChecked();
  await expect(productionToggle).toBeDisabled();
  const parecerToggle = page.locator('[data-wallet-tool-toggle="pareceres"]');
  await expect(parecerToggle).toHaveCount(1);
  const parecerWasEnabled = await parecerToggle.isChecked();
  await parecerToggle.evaluate((element) => element.click());
  await expect(page.locator('[data-wallet-tool-toggle="pareceres"]')).toBeChecked({ checked: !parecerWasEnabled });
  await expect(page.locator('[data-carteira-workspace-tab="pareceres"]')).toHaveCount(parecerWasEnabled ? 0 : 1);
  await page.locator('[data-wallet-tool-toggle="pareceres"]').evaluate((element) => element.click());
  await expect(page.locator('[data-wallet-tool-toggle="pareceres"]')).toBeChecked({ checked: parecerWasEnabled });
  const protectedProductionStatus = await page.evaluate(async () => {
    const wallet = document.querySelector("#carteiraMonitorTitle")?.textContent?.trim() || "";
    const response = await fetch(`/api/config/carteiras/${encodeURIComponent(wallet)}/ferramentas`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool_key: "producao", enabled: false }),
    });
    return response.status;
  });
  expect(protectedProductionStatus).toBe(400);
  expect(errors).toEqual([]);
});

test("gerencial exposes the versioned Alpha goals and H.O. conference workspace", async ({ page }) => {
  const username = process.env.GERENCIAL_E2E_USERNAME;
  const password = process.env.GERENCIAL_E2E_PASSWORD;
  test.skip(!username || !password, "Defina credenciais E2E do Gerencial.");
  const errors = capturePageErrors(page);

  await page.goto(`${GERENCIAL}/login.html`);
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL(`${GERENCIAL}/`);
  await page.locator('[data-tool="monitoramento"]').click();
  await page.locator("#carteirasBtn").click();
  await page.locator('[data-edit-carteira="ALPHA"]').evaluate((button) => button.click());
  await expect(page.locator("#carteiraDialog")).toBeVisible();
  await expect(page.locator('#carteiraDialog [name="ho_motor_calculo"]')).toHaveValue("ALPHA_EXCEPCIONAL");
  await expect(page.locator('#carteiraDialog [name="ho_coluna_destino"]')).toHaveValue("HONORARIOS_CALCULADOS");
  const conditionalHoFields = page.locator('#carteiraDialog [data-ho-conditional]');
  await expect(conditionalHoFields).toHaveCount(2);
  await expect(conditionalHoFields.nth(0)).toBeHidden();
  await expect(conditionalHoFields.nth(1)).toBeHidden();
  await page.locator("#carteiraDialog [data-close-carteira]").first().click();
  await page.locator("[data-open-carteira-workspace]").filter({ hasText: /ALPHA/i }).click();

  const tab = page.locator('[data-carteira-workspace-tab="honorarios"]');
  await expect(tab).toBeVisible();
  await tab.click();
  await expect(page.locator("#carteiraWorkspaceHonorarios .alpha-ho-commandbar")).toBeVisible();
  await expect(page.locator("#carteiraWorkspaceHonorarios")).toContainText("3T2026");
  await expect(page.locator("#carteiraWorkspaceHonorarios")).toContainText("Conferencia");
  await expect(page.locator("#carteiraWorkspaceHonorarios .alpha-ho-matrix-row")).toHaveCount(5);
  await expect(page.locator("#carteiraWorkspaceHonorarios .alpha-ho-goals-table")).toBeVisible();
  await expect(page.locator("#carteiraWorkspaceHonorarios [data-edit-alpha-goal]")).toHaveCount(162);
  await page.locator("#carteiraWorkspaceHonorarios [data-edit-alpha-goal]").first().click();
  await expect(page.locator("[data-alpha-goal-dialog]")).toBeVisible();
  await expect(page.locator("[data-alpha-goal-form] textarea[name='reason']")).toBeVisible();
  await page.locator("[data-alpha-goal-dialog] [data-close-goal-dialog]").first().click();
  await expect(page.locator("[data-alpha-goal-dialog]")).not.toBeVisible();
  await expect(page.locator("#carteiraWorkspaceHonorarios .alpha-ho-calculation-table")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth))
    .toBeLessThanOrEqual(2);
  expect(errors).toEqual([]);
});

test("gerencial spreadsheet views use the shared Excel workspace", async ({ page }) => {
  test.setTimeout(120_000);
  const username = process.env.GERENCIAL_E2E_USERNAME;
  const password = process.env.GERENCIAL_E2E_PASSWORD;
  test.skip(!username || !password, "Defina credenciais E2E do Gerencial.");
  const errors = capturePageErrors(page);

  await page.goto(`${GERENCIAL}/login.html`);
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL(`${GERENCIAL}/`);

  await page.locator('[data-tool="monitoramento"]').click();
  await page.locator("#monitorPlanilhaBtn").click();
  await page.locator("#monitorPlanilhaCarteira").selectOption("GAMMA");
  await page.locator("#monitorPlanilhaMes").selectOption("6");
  await page.locator("#monitorPlanilhaAno").selectOption("2026");
  await page.locator("#monitorPlanilhaCarteira").dispatchEvent("change");
  await expect(page.locator("#monitorPlanilhaTable.monitor-native-excel.excel-grid")).toBeVisible();
  await expect(page.locator("#monitorPlanilhaTable .excel-formula-bar")).toBeVisible();
  await expect(page.locator("#monitorPlanilhaTable .excel-letter-row")).toBeVisible();
  await expect(page.locator("#monitorPlanilhaTable .excel-status-bar")).toBeVisible();
  await expect(page.locator("#monitorPlanilhaTable .excel-toolbar")).toBeVisible();
  await expect(page.locator("#monitorPlanilhaTable .excel-filter-btn").first()).toBeVisible();

  const firstCell = page.locator("#monitorPlanilhaTable .excel-cell").first();
  await firstCell.click();
  await expect(firstCell).toHaveClass(/active/);
  await expect(page.locator("#monitorPlanilhaTable .excel-name-box")).not.toHaveText("");
  await page.locator("#monitorPlanilhaTable .excel-filter-btn").first().click();
  await expect(page.locator(".excel-filter-menu")).toBeVisible();
  await page.locator(".excel-filter-menu [data-cancel]").click();
  await page.locator("#monitorPlanilhaExpandBtn").click();
  const expandedMonitor = page.locator("#monitorPlanilhaExpandedDialog");
  await expect(expandedMonitor).toBeVisible();
  await expect(expandedMonitor).toHaveClass(/focus-spreadsheet-dialog/);
  await expect(expandedMonitor.locator(".monitor-planilha-expanded-head")).toHaveCount(0);
  await expect(page.locator("#monitorPlanilhaExpandedTable.monitor-native-excel .excel-toolbar")).toBeVisible();
  const monitorFocusBounds = await expandedMonitor.boundingBox();
  const monitorViewport = page.viewportSize();
  expect(monitorFocusBounds.x).toBeLessThanOrEqual(1);
  expect(monitorFocusBounds.y).toBeLessThanOrEqual(1);
  expect(monitorFocusBounds.width).toBeGreaterThanOrEqual(monitorViewport.width - 1);
  expect(monitorFocusBounds.height).toBeGreaterThanOrEqual(monitorViewport.height - 1);
  await page.locator("[data-close-monitor-planilha-expanded]").click();
  await expect(expandedMonitor).not.toBeVisible();

  await page.locator('[data-tool="protocolo"]').click();
  await page.locator('[data-protocolo-page="concluidos"]').click();
  await expect(page.locator("#protocoloClosedGrid.monitor-native-excel.excel-grid")).toBeVisible();
  await expect(page.locator("#protocoloClosedGrid .excel-letter-row")).toBeVisible();

  await page.locator('[data-tool="parecer"]').click();
  await page.locator('[data-parecer-page="completa"]').click();
  await expect(page.locator("#parecerCompletaGrid.monitor-native-excel.excel-grid")).toBeVisible();
  await expect(page.locator("#parecerCompletaGrid .excel-filter-btn").first()).toBeVisible();
  await expect(page.locator("#parecerReportFullBtn")).toBeVisible();
  await expect(page.locator("#parecerOpenSpreadsheetBtn, #parecerPrevPage, #parecerNextPage")).toHaveCount(0);

  await page.locator('[data-tool="colchao"]').click();
  await page.locator('[data-colchao-profile="alpha"]').click();
  await page.locator('[data-colchao-page="completo"]').click();
  await expect(page.locator("#colchaoCompletoGrid.monitor-native-excel.excel-grid")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator("#colchaoCompletoGrid .excel-status-bar")).toBeVisible();
  await expect(page.locator("#colchaoCompleto .colchao-sheet-actions")).toBeVisible();
  await expect(page.locator("#colchaoSaveChangesBtn")).toBeHidden();
  const actionBarBox = await page.locator("#colchaoCompleto .colchao-sheet-commandbar").boundingBox();
  const gridBox = await page.locator("#colchaoCompletoGrid").boundingBox();
  expect(actionBarBox.y).toBeLessThan(gridBox.y);
  const colchaoToolbar = page.locator("#colchaoCompletoGrid .excel-toolbar");
  await expect(colchaoToolbar).toHaveCSS("overflow", "visible");
  await page.locator("#colchaoCompletoGrid .excel-more-menu summary").click();
  await expect(page.locator("#colchaoCompletoGrid .excel-more-popover")).toBeVisible();
  const toolbarDimensions = await colchaoToolbar.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }));
  expect(toolbarDimensions.scrollWidth).toBe(toolbarDimensions.clientWidth);
  await page.locator("#colchaoCompletoGrid .excel-more-menu summary").click();
  await page.locator("#colchaoExpandSpreadsheetBtn").click();
  const expandedColchao = page.locator("#colchaoExpandedDialog");
  await expect(expandedColchao).toBeVisible();
  await expect(expandedColchao).toHaveClass(/focus-spreadsheet-dialog/);
  await expect(expandedColchao.locator(".monitor-planilha-expanded-head")).toHaveCount(0);
  await expect(page.locator("#colchaoExpandedTable .excel-grid-shell")).toBeVisible();
  const focusBounds = await expandedColchao.boundingBox();
  const viewport = page.viewportSize();
  expect(focusBounds.x).toBeLessThanOrEqual(1);
  expect(focusBounds.y).toBeLessThanOrEqual(1);
  expect(focusBounds.width).toBeGreaterThanOrEqual(viewport.width - 1);
  expect(focusBounds.height).toBeGreaterThanOrEqual(viewport.height - 1);
  await page.locator("[data-close-colchao-expanded]").click();
  await expect(expandedColchao).not.toBeVisible();
  expect(errors).toEqual([]);
});

test("negocial authenticates with a temporary user and loads production", async ({ page }) => {
  const root = path.resolve(process.cwd(), "../aplicacao-negocial");
  const python = path.join(root, ".venv", "Scripts", "python.exe");
  const helper = path.join(root, "tests", "e2e_user.py");
  const username = `__e2e_negocial_${randomUUID().replaceAll("-", "").slice(0, 12)}`;
  const password = `E2E-${randomUUID()}`;
  const errors = capturePageErrors(page);

  execFileSync(python, [helper, "create", username, password], { cwd: root });
  try {
    await page.goto(`${NEGOCIAL}/login`);
    await page.locator("#username").fill(username);
    await page.locator("#password").fill(password);
    await page.locator("#loginButton").click();
    await page.waitForURL(`${NEGOCIAL}/`);
    await expect(page.locator("#pageTitle")).toHaveText("Produção Diária");
    await expect(page.locator("#producaoGrid")).toBeVisible();
    await expect(page.locator('[data-page="pareceres"]')).toBeVisible();

    const npj = `${String(Date.now()).slice(-13)}1`;
    await page.locator("#openProducaoDialogBtn").click();
    await page.locator('[data-dynamic-field="NPJ"]').fill(npj);
    await page.locator('[data-dynamic-field="CLIENTE"]').fill("CLIENTE TESTE E2E VIRGULA");
    await page.locator('[data-dynamic-field="GECOR"]').fill("1234");
    await page.locator('[data-dynamic-field="PARCELADO_OU_VISTA"]').selectOption("A_VISTA");
    await page.locator("#nextProducaoStepBtn").click();

    const totalInput = page.locator('[data-dynamic-field="VALOR_DO_ACORDO"]');
    await totalInput.fill("19105,64");
    await expect(totalInput).toHaveValue("19105,64");
    await page.locator('[data-dynamic-field="DATA_DE_VENCIMENTO"]').fill("2026-07-30");
    await page.locator('[data-dynamic-field="STATUS"]').selectOption("PROPOSTA");
    await page.locator('[data-dynamic-field="HONOR_RIOS_RECEBIDOS"]').fill("1910,56");
    const requiredSelects = page.locator('#producaoDialog select[data-dynamic-field][required]');
    for (const select of await requiredSelects.all()) {
      if (!await select.isVisible() || await select.inputValue()) continue;
      const firstValue = await select.locator('option:not([value=""])').first().getAttribute("value");
      if (firstValue) await select.selectOption(firstValue);
    }
    const requiredMultiselects = page.locator('#producaoDialog [data-dynamic-multiselect][data-required="true"]');
    for (const multiselect of await requiredMultiselects.all()) {
      if (!await multiselect.isVisible() || await multiselect.locator('[data-multiselect-option]:checked').count()) continue;
      await multiselect.locator("[data-multiselect-trigger]").click();
      await multiselect.locator("[data-multiselect-option]").first().check();
      await multiselect.locator("[data-multiselect-done]").click();
    }
    await page.locator("#saveProducaoBtn").click();

    await expect(page.locator("#producaoDialog")).not.toBeVisible();
    await expect(page.locator("#producaoGrid")).toContainText("CLIENTE TESTE E2E VIRGULA");
    expect(errors).toEqual([]);
  } finally {
    execFileSync(python, [helper, "delete", username], { cwd: root });
  }
});

test("configuration renders the compact user center", async ({ page }) => {
  const username = process.env.GERENCIAL_E2E_USERNAME;
  const password = process.env.GERENCIAL_E2E_PASSWORD;
  test.skip(!username || !password, "Defina credenciais E2E do Gerencial.");
  const errors = capturePageErrors(page);

  await page.goto(`${GERENCIAL}/login.html`);
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL(`${GERENCIAL}/`, { waitUntil: "domcontentloaded" });
  await page.locator("#toolMenuBtn").click();
  await page.locator('[data-group="configuracao"]').click({ force: true });

  await expect(page.locator("#configUsersPage")).toBeVisible();
  await expect(page.locator(".config-user-kpi")).toHaveCount(5);
  await expect(page.locator(".config-user-commandbar")).toBeVisible();
  await expect(page.locator(".config-user-table-head")).toBeVisible();
  await expect(page.locator(".config-user-row").first()).toBeVisible();

  await page.locator('[data-config-user-tab="negociador"]').click();
  await expect(page.locator('.config-user-row[data-config-user-source="negociador"]').first()).toBeVisible();
  await page.locator(".config-user-row .config-user-more").first().click();
  await expect(page.locator(".config-user-popover")).toBeVisible();
  await expect(page.locator(".config-user-popover [data-menu-edit]")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator(".config-user-popover")).toHaveCount(0);
  await page.screenshot({ path: "test-results/config-users-center.png", fullPage: true });
  expect(errors).toEqual([]);
});
