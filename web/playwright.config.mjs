import { defineConfig, devices } from "@playwright/test";

// Browser execution belongs on hosted Linux, away from the user's desktop.
// Listing tests is safe on any platform and does not start a browser/server.
if (process.platform !== "linux" && !process.argv.includes("--list")) {
  throw new Error("Run browser QA on hosted Linux; only --list is allowed locally.");
}

const externalURL = process.env.SPM_E2E_BASE_URL;
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
if (!["", "/us/spm-calculator"].includes(basePath)) {
  throw new Error("Build QA supports standalone or /us/spm-calculator only.");
}
if (externalURL) {
  const url = new URL(externalURL);
  if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash) {
    throw new Error("Existing deployment QA requires a public HTTPS URL without credentials, query, or fragment.");
  }
  if (!/^[a-f0-9]{64}$/.test(process.env.SPM_E2E_EXPECT_CONTENT_SHA256 ?? "")) {
    throw new Error("Existing deployment QA requires SPM_E2E_EXPECT_CONTENT_SHA256.");
  }
  if (!process.env.SPM_E2E_EXPECT_PACKAGE_VERSION ||
      !["published", "local_preview"].includes(process.env.SPM_E2E_EXPECT_PACKAGE_STATUS)) {
    throw new Error("Existing deployment QA requires an explicit package version and published/local_preview status.");
  }
}
const baseURL = externalURL
  ? `${externalURL.replace(/\/+$/, "")}/`
  : `http://127.0.0.1:4173${basePath}/`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [
    ["list"],
    ["html", { open: "never" }],
    ["json", { outputFile: "test-results/results.json" }],
  ],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: externalURL ? undefined : {
    command: "python3 -m http.server 4173 --bind 127.0.0.1 --directory e2e-site",
    url: baseURL,
    reuseExistingServer: false,
    timeout: 15_000,
  },
});
