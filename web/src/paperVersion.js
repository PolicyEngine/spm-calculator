// Single source of truth for the embedded manuscript snapshot.
//
// `web/public/paper/web/` holds a Quarto render of
// PolicyEngine/spm-threshold-paper at the revision below. Every link to that
// render — and the iframe on /paper — carries the same `?v=` token, so a
// browser or CDN cannot serve a stale manuscript behind a fresh wrapper.
// Re-render, re-copy and bump both constants together.

export const PAPER_REVISION = "6937830";
export const PAPER_REVISION_DATE = "2026-09-14";

export const PAPER_VERSION = `${PAPER_REVISION}-${PAPER_REVISION_DATE.replaceAll("-", "")}`;

export const PAPER_TITLE =
  "Calculating and projecting Supplemental Poverty Measure thresholds";
export const PAPER_AUTHORS = "Max Ghenis, PolicyEngine";
export const PAPER_REPO_URL =
  "https://github.com/PolicyEngine/spm-threshold-paper";

// Build every in-app URL from the deployed base path rather than relative to
// the current page: /paper is exported with and without a trailing slash, so a
// page-relative href would resolve differently depending on which one the
// visitor landed on. Both the standalone origin and the policyengine.org zone
// mount the app at this same base path.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export const paperHtmlUrl = `${basePath}/paper/web/index.html?v=${PAPER_VERSION}`;
export const paperPdfUrl = `${basePath}/paper/web/index.pdf?v=${PAPER_VERSION}`;
export const calculatorUrl = `${basePath}/`;
export const paperPageUrl = `${basePath}/paper/`;
