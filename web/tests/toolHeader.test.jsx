import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ToolHeader, { CODE_URL, PACKAGE_URL, TOOL_LINKS, isActiveLink } from "../src/components/ToolHeader";
import { calculatorUrl, paperPageUrl } from "../src/paperVersion";

describe("tool header", () => {
  it("puts the paper beside the calculator, package and code on every page", () => {
    render(<ToolHeader />);
    const nav = screen.getByRole("navigation", { name: "SPM Threshold Calculator" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((a) => a.textContent.trim())).toEqual([
      "SPM Threshold Calculator by PolicyEngine",
      "Calculator",
      "Paper",
      "Python package",
      "Code",
    ]);
    expect(within(nav).getByRole("link", { name: "Paper" })).toHaveAttribute("href", paperPageUrl);
    expect(within(nav).getByRole("link", { name: "Calculator" })).toHaveAttribute("href", calculatorUrl);
    expect(within(nav).getByRole("link", { name: "Python package" })).toHaveAttribute("href", PACKAGE_URL);
    expect(within(nav).getByRole("link", { name: "Code" })).toHaveAttribute("href", CODE_URL);
  });

  it("renders the paper as the filled action and opens external links in a new tab", () => {
    render(<ToolHeader />);
    const paper = screen.getByRole("link", { name: "Paper" });
    expect(paper.className).toContain("bg-primary");
    expect(paper).not.toHaveAttribute("target");
    for (const label of ["Python package", "Code"]) {
      const link = screen.getByRole("link", { name: label });
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
  });

  it("marks the current section from the browser path, with or without a trailing slash", () => {
    const paper = TOOL_LINKS.find((link) => link.id === "paper");
    const calculator = TOOL_LINKS.find((link) => link.id === "calculator");
    expect(isActiveLink(paperPageUrl, paper)).toBe(true);
    expect(isActiveLink(paperPageUrl.replace(/\/$/, ""), paper)).toBe(true);
    expect(isActiveLink(paperPageUrl, calculator)).toBe(false);
    expect(isActiveLink(calculatorUrl, calculator)).toBe(true);
    expect(isActiveLink("", paper)).toBe(false);
  });

  it("sets aria-current on the paper link when the page is the paper", async () => {
    window.history.pushState({}, "", paperPageUrl);
    render(<ToolHeader />);
    const paper = await screen.findByRole("link", { name: "Paper", current: "page" });
    expect(paper).toHaveAttribute("aria-current", "page");
    window.history.pushState({}, "", "/");
  });
});
