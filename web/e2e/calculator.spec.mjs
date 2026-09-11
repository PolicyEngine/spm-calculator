import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { test, expect } from "@playwright/test";

// These are the real released inputs, not a synthetic fixture or a second calculator.
const sourceBytes = readFileSync(new URL("../public/data/release_config.json", import.meta.url));
const source = JSON.parse(sourceBytes);
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const expectedContent = process.env.SPM_E2E_EXPECT_CONTENT_SHA256 ?? source.forecast.contentSha256;
const expectedVersion = process.env.SPM_E2E_EXPECT_PACKAGE_VERSION ?? source.packageVersion;
const expectedStatus = process.env.SPM_E2E_EXPECT_PACKAGE_STATUS ?? source.packageDistribution.status;
const observations = new WeakMap();
const menu = (year) => source.areaMenus[source.areaMenuByYear[year]];
const yearEntry = (year, scenario = source.forecast.defaultScenario) => source.forecast.scenarios[scenario].years[year];
const geography = (year) => source.geographies[yearEntry(year).geographyRef].geography_by_area;
const currency = (value) => new Intl.NumberFormat("en-US", {
  style: "currency", currency: "USD", maximumFractionDigits: 0, minimumFractionDigits: 0,
}).format(value);
const threshold = (page) => page.getByTestId("primary-result")
  .getByText("SPM threshold", { exact: true }).locator("..").locator("span").nth(1);

test.beforeEach(async ({ page, baseURL }, testInfo) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const surface = new URL(baseURL);
  const responsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.origin === surface.origin && url.pathname.endsWith("/data/release_config.json");
  });
  await page.goto("./", { waitUntil: "domcontentloaded" });
  const response = await responsePromise;
  expect(response.ok()).toBe(true);
  const dataURL = response.url();
  const allowedDataURLs = [new URL("data/release_config.json", baseURL).href];
  // Vercel's standalone root can serve the same subpath-built export as the
  // PolicyEngine zone. Check the actual app request, including that mount.
  if (process.env.SPM_E2E_BASE_URL && surface.pathname === "/") {
    allowedDataURLs.push(new URL("us/spm-calculator/data/release_config.json", baseURL).href);
  }
  expect(allowedDataURLs).toContain(dataURL);
  const bytes = await response.body();
  const data = JSON.parse(bytes);
  expect(data.forecast.contentSha256).toBe(expectedContent);
  // An external publication may change distribution metadata, but must serve
  // the same reviewed scientific inputs as this checkout.
  expect(data.forecast).toEqual(source.forecast);
  expect(data.areaMenus).toEqual(source.areaMenus);
  expect(data.areaMenuByYear).toEqual(source.areaMenuByYear);
  expect(data.geographies).toEqual(source.geographies);
  expect(data.methodology).toEqual(source.methodology);
  expect(data.availableYears).toEqual(source.availableYears);
  expect(data.packageVersion).toBe(expectedVersion);
  expect(data.packageDistribution.status).toBe(expectedStatus);
  expect(data.packageDistribution.version).toBe(expectedVersion);
  if (expectedStatus === "published") {
    expect(data.packageDistribution.publishedVersion).toBe(expectedVersion);
  } else {
    expect(data.packageDistribution.publishedVersion).toBeNull();
  }
  if (!process.env.SPM_E2E_BASE_URL) expect(sha256(bytes)).toBe(sha256(sourceBytes));
  await expect(page.getByTestId("primary-result")).toBeVisible();
  await expect(threshold(page)).toHaveText(/^\$[\d,]+$/);
  await testInfo.attach("surface-identity.json", {
    contentType: "application/json",
    body: JSON.stringify({
      requestedURL: baseURL, finalURL: page.url(), dataURL,
      releaseConfigSha256: sha256(bytes), contentSha256: data.forecast.contentSha256,
      auditArtifact: data.forecast.auditArtifact, packageDistribution: data.packageDistribution,
    }, null, 2),
  });
  observations.set(testInfo, { errors, dataURL });
});

test.afterEach(async ({}, testInfo) => {
  expect(observations.get(testInfo)?.errors ?? [], "Uncaught browser errors").toEqual([]);
});

test("one shared header, working mobile navigation, and app-owned provenance", async ({ page }) => {
  const toggle = page.locator('button[aria-label="Toggle navigation"]');
  await expect(toggle).toHaveCount(1);
  const header = page.locator("main").first().locator("xpath=preceding-sibling::*[1]");
  await expect(header.locator('button[aria-label="Toggle navigation"]')).toHaveCount(1);
  const chrome = await page.locator("header, footer").evaluateAll((elements) => elements
    .filter((element) => !element.closest('[data-testid="results-footnote"]'))
    .map((element) => element.textContent).join("\n"));
  expect(`${await header.textContent()}\n${chrome}`).not.toMatch(/SHA-256|rolling_ce_acs_v1|equivalence_scale|load_forecast/);
  await expect(page.getByTestId("results-footnote")).toContainText(expectedContent);
  await page.setViewportSize({ width: 800, height: 900 });
  await toggle.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("dialog").getByRole("link").first()).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("area search selects by click and Enter and preserves selection on no match", async ({ page }) => {
  const search = page.getByRole("combobox", { name: "Search SPM areas" });
  const area = page.getByLabel("SPM estimation area", { exact: true });
  await search.fill("san jose");
  const matches = page.getByRole("listbox", { name: "Matching SPM areas" });
  await expect(matches.getByRole("option")).toHaveCount(1);
  await matches.getByRole("option", { name: menu(2025)["41940"].name, exact: true }).click();
  await expect(area).toHaveValue("41940");
  await expect(page.getByTestId("primary-result").getByRole("heading")).toHaveText(menu(2025)["41940"].name);
  await expect(search).toHaveValue("");
  await expect(matches).toHaveCount(0);
  await search.fill("1002");
  await expect(matches.getByRole("option")).toHaveCount(5);
  await expect(matches.getByRole("option").first()).toHaveText(menu(2025)["1002"].name);
  await search.press("Enter");
  await expect(area).toHaveValue("1002");
  await expect(page.getByTestId("primary-result").getByRole("heading")).toHaveText(menu(2025)["1002"].name);
  const selectedThreshold = await threshold(page).textContent();
  await search.fill("no matching place xyz");
  await expect(page.getByText("No SPM areas match your search.")).toBeVisible();
  await expect(matches.getByRole("option")).toHaveCount(0);
  await search.press("Enter");
  await expect(area).toHaveValue("1002");
  await expect(threshold(page)).toHaveText(selectedThreshold);
});

test("annual SPM-area menus and published versus modeled geography are explicit", async ({ page }) => {
  const area = page.getByLabel("SPM estimation area", { exact: true });
  const year = page.getByLabel("Threshold year", { exact: true });
  await expect(page.getByLabel("Geography type", { exact: true })).toHaveCount(0);
  for (const value of [2022, 2024, 2025, 2035]) {
    await year.selectOption(String(value));
    const actual = await area.locator("option").evaluateAll((options) => Object.fromEntries(
      options.filter((option) => option.value).map((option) => [option.value, option.textContent]),
    ));
    expect(actual).toEqual(Object.fromEntries(Object.entries(menu(value)).map(([id, entry]) => [id, entry.name])));
    expect(Object.values(menu(value)).every((entry) => [
      "msa", "state_nonmetro", "state_metro_residual", "modeled_residual_metro",
    ].includes(entry.area_type))).toBe(true);
  }
  await year.selectOption("2024");
  const official = Object.keys(geography(2024)).find((id) => menu(2024)[id]?.area_type === "msa" && geography(2024)[id].status === "published_anchor");
  const modeled = Object.keys(geography(2024)).find((id) => menu(2024)[id]?.area_type === "modeled_residual_metro");
  expect(official).toBeTruthy();
  expect(modeled).toBeTruthy();
  await area.selectOption(official);
  await expect(page.getByTestId("primary-result")).toContainText("2024 published geography anchor");
  await expect(page.getByTestId("area-provenance")).toContainText("This area has a published Census geography anchor.");
  await area.selectOption(modeled);
  await expect(page.getByTestId("primary-result")).toContainText("Modeled geography");
  await expect(page.getByTestId("area-provenance")).toContainText("This residual group has no published Census geography anchor.");
  await area.selectOption(official);
  await year.selectOption("2025");
  await expect(page.getByText("Published by BLS", { exact: true })).toBeVisible();
  await expect(page.getByTestId("primary-result")).toContainText("Modeled geography");
  await expect(page.getByTestId("primary-result")).not.toContainText("Research forecast");
  await expect(page.getByTestId("forecast-disclaimer")).toContainText("The 2025 geography is modeled");
});

test("future years, real spending, and household controls update real results", async ({ page }) => {
  const year = page.getByLabel("Threshold year", { exact: true });
  const factor = page.getByTestId("primary-result").getByText("Location factor", { exact: true })
    .locator("..").locator("span").nth(1);
  const factor2025 = await factor.textContent();
  for (let value = 2026; value <= 2035; value++) {
    await expect(year.getByRole("option", { name: `${value} (forecast)`, exact: true })).toHaveCount(1);
    await year.selectOption(String(value));
    await expect(page.getByTestId("primary-result")).toContainText("Research forecast");
    await expect(page.getByTestId("source-windows")).toContainText(`${value} source windows`);
    await expect(threshold(page)).toHaveText(/^\$[\d,]+$/);
  }
  await expect(factor).not.toHaveText(factor2025);
  const row = page.getByRole("region", { name: "Year-by-year thresholds" })
    .getByRole("row").filter({ has: page.getByRole("cell", { name: "2035", exact: true }) });
  const scenario = page.getByLabel("Real spending", { exact: true });
  await scenario.selectOption("ce_trend");
  await expect(row.getByRole("cell").nth(1)).toHaveText(currency(yearEntry(2035, "ce_trend").thresholds.renter));
  const trendThreshold = await threshold(page).textContent();
  await scenario.selectOption("zero_real");
  await expect(row.getByRole("cell").nth(1)).toHaveText(currency(yearEntry(2035, "zero_real").thresholds.renter));
  await expect(threshold(page)).not.toHaveText(trendThreshold);
  await expect(page.getByTestId("year-by-year-card")).toContainText(source.forecast.scenarios.zero_real.label);
  const zeroThreshold = await threshold(page).textContent();
  await page.getByLabel("Adults", { exact: true }).fill("3");
  await expect(threshold(page)).not.toHaveText(zeroThreshold);
  await expect(threshold(page)).toHaveText(/^\$[\d,]+$/);
  const familyThreshold = await threshold(page).textContent();
  const noMortgage = page.getByRole("tab", { name: "No mortgage", exact: true });
  await noMortgage.click();
  await expect(noMortgage).toHaveAttribute("aria-selected", "true");
  await expect(threshold(page)).not.toHaveText(familyThreshold);
  await expect(page.getByTestId("primary-result")).toContainText("Owner without mortgage");
  await expect(page.getByTestId("forecast-provenance")).toContainText(expectedContent);
});

test("canonical download and package provenance match the served calculation", async ({ page }, testInfo) => {
  const artifact = source.forecast.auditArtifact;
  const artifactURL = new URL(artifact.url.replace(/^\/data\//, ""), observations.get(testInfo).dataURL).href;
  const link = page.getByRole("link", { name: "Download full canonical audit data (JSON)" });
  expect(await link.evaluate((element) => element.href)).toBe(artifactURL);
  const downloadPromise = page.waitForEvent("download");
  await link.click();
  const download = await downloadPromise;
  expect(await download.failure()).toBeNull();
  expect(download.suggestedFilename()).toBe(artifact.name);
  const bytes = readFileSync(await download.path());
  expect(bytes.length).toBe(artifact.bytes);
  expect(sha256(bytes)).toBe(artifact.sha256);
  const canonical = JSON.parse(bytes);
  expect(canonical.content_sha256).toBe(expectedContent);
  expect(canonical.base_release_sha256).toBe(source.forecast.baseReleaseSha256);
  expect(canonical.assumption_sha256).toBe(source.forecast.assumptionSha256);
  await testInfo.attach("canonical-download.json", { contentType: "application/json", body: JSON.stringify({
    url: artifactURL, bytes: bytes.length, sha256: sha256(bytes), contentSha256: canonical.content_sha256,
  }, null, 2) });
  const footnote = page.getByTestId("results-footnote");
  if (expectedStatus === "published") {
    await expect(footnote).toContainText(`Published package: spm-calculator ${expectedVersion}.`);
    await expect(footnote.getByRole("link", { name: `spm-calculator ${expectedVersion}`, exact: true }))
      .toHaveAttribute("href", `https://pypi.org/project/spm-calculator/${expectedVersion}/`);
    await expect(footnote).not.toContainText("Publication on PyPI is not confirmed");
  } else {
    await expect(footnote).toContainText(`Local build / development preview: spm-calculator ${expectedVersion}.`);
    await expect(footnote).toContainText("Publication on PyPI is not confirmed for this build.");
  }
});

for (const failure of ["failed", "stalled"]) {
  test(`calculator recovers from a ${failure} data request using the real server`, async ({ page }, testInfo) => {
    if (failure === "stalled") test.setTimeout(90_000);
    const { dataURL } = observations.get(testInfo);
    let intercepted = 0;
    await page.route(dataURL, async (route) => {
      intercepted++;
      if (failure === "failed") await route.abort("failed");
      // A stalled request gets no response. The production loader must abort
      // it after its real 30-second timeout; the retry is not intercepted.
    }, { times: 1 });
    await page.reload({ waitUntil: "domcontentloaded" });
    if (failure === "stalled") {
      await expect(page.getByRole("status")).toHaveText("Loading thresholds and geographic inputs…");
    }
    await expect(page.getByRole("alert").filter({ hasText: "We couldn’t load the calculator data" })).toBeVisible({ timeout: 35_000 });
    expect(intercepted).toBe(1);
    await expect(page.getByTestId("primary-result")).toHaveCount(0);
    const recovered = page.waitForResponse((response) => response.url() === dataURL);
    await page.getByRole("button", { name: "Try again", exact: true }).click();
    const response = await recovered;
    expect(response.ok()).toBe(true);
    const data = await response.json();
    expect(data.forecast).toEqual(source.forecast);
    expect(data.geographies).toEqual(source.geographies);
    await expect(page.getByTestId("primary-result")).toBeVisible();
    await expect(threshold(page)).toHaveText(/^\$[\d,]+$/);
    await expect(page.getByRole("button", { name: "Try again", exact: true })).toHaveCount(0);
  });
}

test("an unavailable area stays explicit until the user selects a valid area", async ({ page }) => {
  const area = page.getByLabel("SPM estimation area", { exact: true });
  const year = page.getByLabel("Threshold year", { exact: true });
  await year.selectOption("2022");
  await area.selectOption("45001");
  await expect(threshold(page)).toHaveText(/^\$[\d,]+$/);
  await year.selectOption("2023");
  await expect(area).toHaveValue("");
  await expect(area.getByRole("option", { name: "Selected area unavailable in 2023", exact: true })).toBeDisabled();
  await expect(area.locator('option[value="45001"]')).toHaveCount(0);
  await expect(threshold(page)).toHaveText("Unavailable");
  await area.selectOption("modeled_residual_metro:45");
  await expect(threshold(page)).toHaveText(/^\$[\d,]+$/);
  await expect(page.getByTestId("primary-result").getByRole("heading")).toHaveText(menu(2023)["modeled_residual_metro:45"].name);
});

test("Massachusetts and Sumter series breaks remain visible in later years", async ({ page }) => {
  const area = page.getByLabel("SPM estimation area", { exact: true });
  const year = page.getByLabel("Threshold year", { exact: true });
  const warning = page.getByTestId("historical-series-break-warning");
  for (const id of ["25002", "modeled_residual_metro:45"]) {
    await year.selectOption("2023");
    await area.selectOption(id);
    const disclosure = geography(2023)[id].series_breaks[0];
    await expect(warning).toContainText(`${disclosure.from_year}→${disclosure.to_year}: ${disclosure.interpretation}`);
    await year.selectOption("2035");
    await expect(warning).toContainText(disclosure.interpretation);
  }
  await area.selectOption("41940");
  await expect(warning).toHaveCount(0);
});

test("rental support and topcoding diagnostics follow the actual area and year", async ({ page }) => {
  const area = page.getByLabel("SPM estimation area", { exact: true });
  const year = page.getByLabel("Threshold year", { exact: true });
  const diagnostics = source.geographies[yearEntry(2035).geographyRef].median_diagnostics;
  const thin = Object.keys(diagnostics).find((id) => diagnostics[id].thin_support);
  const topcoded = Object.keys(diagnostics).find((id) => !diagnostics[id].thin_support && diagnostics[id].rent_index_topcode_warning);
  expect(thin).toBeTruthy();
  expect(topcoded).toBeTruthy();
  expect(menu(2035)[thin]).toBeTruthy();
  expect(menu(2035)[topcoded]).toBeTruthy();
  await year.selectOption("2035");
  const warning = page.getByTestId("primary-result").getByTestId("median-diagnostics-warning");
  for (const id of [thin, topcoded]) {
    await area.selectOption(id);
    const entry = diagnostics[id];
    await expect(warning).toContainText(entry.thin_support ? "Thin rental support" : "Rental topcoding");
    await expect(warning).toContainText(`${entry.unique_records.toLocaleString("en-US")} unique records`);
    await expect(warning).toContainText(`Kish effective count ${entry.kish_effective_count.toFixed(1)}`);
    await expect(warning).toContainText(`${(entry.topcoded_weight_share * 100).toFixed(1)}% topcoded weight`);
    await expect(warning).toContainText("Repeated future cohorts do not add independent observations");
    await expect(warning).toContainText("not a survey-design effective sample size");
    if (entry.rent_index_topcode_warning) await expect(warning).toContainText("including its vintage bridge");
    await expect(threshold(page)).toHaveText(/^\$[\d,]+$/);
  }
  await year.selectOption("2024");
  await expect(warning).toHaveCount(0);
  await expect(threshold(page)).toHaveText(/^\$[\d,]+$/);
});
