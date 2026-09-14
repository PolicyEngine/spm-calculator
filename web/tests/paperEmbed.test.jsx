import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import PaperPage, { metadata } from "../app/paper/page";
import {
  PAPER_AUTHORS,
  PAPER_REPO_URL,
  PAPER_REVISION,
  PAPER_REVISION_DATE,
  PAPER_TITLE,
  PAPER_VERSION,
  calculatorUrl,
  paperHtmlUrl,
  paperPageUrl,
  paperPdfUrl,
} from "../src/paperVersion";

const RENDER_DIR = "public/paper/web";
// Assembled at runtime so the guard below can scan this file too, rather than
// tripping over its own assertion.
const EXTERNAL_DEPLOYMENT = ["spm-threshold-paper", "vercel", "app"].join(".");
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const renderedLinks = () =>
  within(screen.getByTestId("paper-actions")).getAllByRole("link");

const allLinks = () => Array.from(document.querySelectorAll("a"));

describe("paper version constant", () => {
  it("is a single seven-hex-digit revision and date, shared by every reference", () => {
    expect(PAPER_VERSION).toMatch(/^[0-9a-f]{7}-\d{8}$/);
    expect(PAPER_REVISION).toBe("6937830");
    expect(PAPER_REVISION_DATE).toBe("2026-09-14");
    expect(PAPER_VERSION).toBe(
      `${PAPER_REVISION}-${PAPER_REVISION_DATE.replaceAll("-", "")}`,
    );
  });

  it("builds base-path-absolute URLs rather than page-relative ones", () => {
    for (const url of [paperHtmlUrl, paperPdfUrl, calculatorUrl, paperPageUrl])
      expect(url.startsWith(`${basePath}/`)).toBe(true);
    expect(paperHtmlUrl).toBe(
      `${basePath}/paper/web/index.html?v=${PAPER_VERSION}`,
    );
    expect(paperPdfUrl).toBe(
      `${basePath}/paper/web/index.pdf?v=${PAPER_VERSION}`,
    );
    expect(calculatorUrl).toBe(`${basePath}/`);
    expect(paperPageUrl).toBe(`${basePath}/paper/`);
  });
});

describe("paper wrapper page", () => {
  it("leads with the kicker, the manuscript title and the revision pill", () => {
    render(<PaperPage />);
    expect(screen.getByText("Working paper")).toBeVisible();
    expect(
      screen.getByRole("heading", { level: 1, name: PAPER_TITLE }),
    ).toBeVisible();
    expect(screen.getByTestId("paper-revision-pill")).toHaveTextContent(
      `Revision ${PAPER_REVISION} · ${PAPER_REVISION_DATE} · ${PAPER_AUTHORS}`,
    );
  });

  it("states the paper's results and the embedded snapshot", () => {
    render(<PaperPage />);
    const lead = screen.getByRole("heading", { level: 1 }).nextElementSibling;
    for (const claim of [
      "2.29 percent",
      "0.51 percent",
      "1.17 percent",
      "2.58 percent",
      "2019 through 2025",
      PAPER_REVISION,
    ])
      expect(lead).toHaveTextContent(claim);
  });

  it("offers the four actions, each at its expected destination", () => {
    render(<PaperPage />);
    const links = renderedLinks();
    expect(links.map((link) => link.textContent)).toEqual([
      "Open standalone HTML",
      "Download PDF",
      "Live calculator",
      "Code and artifacts",
    ]);
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      paperHtmlUrl,
      paperPdfUrl,
      calculatorUrl,
      PAPER_REPO_URL,
    ]);
  });

  it("frames the manuscript in one sandboxed, lazy, white-backed iframe", () => {
    render(<PaperPage />);
    const frames = document.querySelectorAll("iframe");
    expect(frames).toHaveLength(1);
    const frame = screen.getByTestId("paper-embed");
    expect(frame.getAttribute("src")).toBe(paperHtmlUrl);
    expect(frame.getAttribute("title")).toBe(`${PAPER_TITLE} (manuscript)`);
    expect(frame.getAttribute("loading")).toBe("lazy");
    expect(frame.getAttribute("sandbox")).toBe(
      "allow-same-origin allow-popups allow-popups-to-escape-sandbox",
    );
    expect(frame.getAttribute("referrerpolicy")).toBe("same-origin");
    expect(frame.style.height).toBe("calc(100vh - 16rem)");
    expect(frame.style.minHeight).toBe("720px");
    expect(frame.style.background).toBe("rgb(255, 255, 255)");
  });

  it("closes with a back-to-top anchor and a second link to the manuscript", () => {
    render(<PaperPage />);
    expect(screen.getByRole("link", { name: "↑ Back to top" })).toHaveAttribute(
      "href",
      "#paper-top",
    );
    expect(document.getElementById("paper-top")).not.toBeNull();
    expect(
      screen.getByRole("link", { name: "Open manuscript in a new page" }),
    ).toHaveAttribute("href", paperHtmlUrl);
  });

  it("carries one identical version token on the iframe and every render link", () => {
    render(<PaperPage />);
    const renderRefs = [
      ...allLinks()
        .map((link) => link.getAttribute("href"))
        .filter((href) => href.includes("/paper/web/")),
      screen.getByTestId("paper-embed").getAttribute("src"),
    ];
    // Both standalone links, the PDF and the iframe.
    expect(renderRefs).toHaveLength(4);
    expect(new Set(renderRefs.map((ref) => ref.split("?v=")[1]))).toEqual(
      new Set([PAPER_VERSION]),
    );
    for (const ref of renderRefs)
      expect(ref).toMatch(/^.*\/paper\/web\/index\.(html|pdf)\?v=[^?&]+$/);
  });

  it("never links the manuscript's own external deployment", () => {
    render(<PaperPage />);
    for (const href of allLinks().map((link) => link.getAttribute("href")))
      expect(href).not.toContain(EXTERNAL_DEPLOYMENT);
  });

  it("declares article metadata with the canonical policyengine.org URL", () => {
    const canonical = "https://www.policyengine.org/us/spm-calculator/paper";
    expect(metadata.title).toBe(`${PAPER_TITLE} | PolicyEngine`);
    expect(metadata.alternates.canonical).toBe(canonical);
    expect(metadata.openGraph.type).toBe("article");
    expect(metadata.openGraph.url).toBe(canonical);
    expect(metadata.openGraph.siteName).toBe("PolicyEngine");
    for (const description of [
      metadata.description,
      metadata.openGraph.description,
    ]) {
      expect(description).toContain("2.29 percent");
      expect(description).toContain("0.51 percent");
    }
  });
});

describe("embedded manuscript render", () => {
  it("ships the HTML, the PDF and the support files the HTML asks for", () => {
    const html = join(RENDER_DIR, "index.html");
    expect(existsSync(html)).toBe(true);
    expect(existsSync(join(RENDER_DIR, "index.pdf"))).toBe(true);
    expect(statSync(join(RENDER_DIR, "index.pdf")).size).toBeGreaterThan(10000);
    expect(readdirSync(join(RENDER_DIR, "index_files")).length).toBeGreaterThan(
      0,
    );
    const source = readFileSync(html, "utf8");
    const referenced = new Set(
      [...source.matchAll(/(?:src|href)="(index_files\/[^"]+)"/g)].map(
        (match) => match[1],
      ),
    );
    expect(referenced.size).toBeGreaterThan(0);
    for (const reference of referenced)
      expect(existsSync(join(RENDER_DIR, reference)), reference).toBe(true);
  });

  it("is the titled manuscript and resolves every asset relatively", () => {
    const source = readFileSync(join(RENDER_DIR, "index.html"), "utf8");
    expect(source).toContain(`<title>${PAPER_TITLE}</title>`);
    // A root-relative asset would break once the render is served under the
    // calculator's base path rather than at a domain root.
    expect([...source.matchAll(/(?:src|href)="(\/[^"]*)"/g)]).toHaveLength(0);
  });
});

describe("the app's own references to the paper", () => {
  const appSources = () => {
    const files = [];
    const walk = (dir) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const path = join(dir, entry.name);
        if (entry.isDirectory()) walk(path);
        else if (/\.(jsx?|mjs|json|xml)$/.test(entry.name)) files.push(path);
      }
    };
    for (const dir of ["app", "lib", "src", "tests"]) walk(dir);
    files.push("public/sitemap.xml", "public/data/release_config.json");
    return files;
  };

  it("points the calculator's methodology notes at the embedded paper", () => {
    const workbench = readFileSync(
      "src/components/CalculatorWorkbench.jsx",
      "utf8",
    );
    expect(workbench).toContain('from "@/src/paperVersion"');
    expect(workbench).toContain("Read the methods paper");
    expect(workbench).toContain("href={paperPageUrl}");
  });

  it("lists the paper in the sitemap", () => {
    expect(readFileSync("public/sitemap.xml", "utf8")).toContain(
      "<loc>https://policyengine.org/us/spm-calculator/paper</loc>",
    );
  });

  it("keeps the manuscript's external deployment out of the app entirely", () => {
    for (const file of appSources())
      expect(readFileSync(file, "utf8"), file).not.toContain(
        EXTERNAL_DEPLOYMENT,
      );
  });
});
