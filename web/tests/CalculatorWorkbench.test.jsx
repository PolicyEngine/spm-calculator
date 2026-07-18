/**
 * Smoke and regression tests for CalculatorWorkbench.
 *
 * These tests render the component against a synthetic data fixture
 * (see ./fixtures/calculatorData.js) and assert invariants the UI is
 * supposed to uphold — they don't re-test the math, they test that
 * the math is surfaced and that the version/methodology plumbing
 * doesn't regress.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import CalculatorWorkbench from "../src/components/CalculatorWorkbench";
import { makeCalculatorData } from "./fixtures/calculatorData";

describe("CalculatorWorkbench", () => {
  it("renders the methodology card with the formula", () => {
    render(<CalculatorWorkbench data={makeCalculatorData()} />);
    const card = screen.getByTestId("methodology-card");
    // The Betson-scale formula must be visible to the user so they
    // can cross-check threshold values against Census documentation.
    expect(card.textContent).toMatch(/base\[tenure\]/);
    expect(card.textContent).toMatch(/equivalence_scale/);
    expect(card.textContent).toMatch(/geoadj\[tenure\]/);
    // Tenure-specific shares should appear so users can tell which
    // geoadj they're seeing.
    expect(card.textContent).toMatch(/0\.443/);
    expect(card.textContent).toMatch(/0\.434/);
    expect(card.textContent).toMatch(/0\.323/);
  });

  it("surfaces the package version and data vintage in the footer", () => {
    render(
      <CalculatorWorkbench
        data={makeCalculatorData({ packageVersion: "0.3.0" })}
      />,
    );
    const footer = screen.getByTestId("version-footer");
    // Version badge links to PyPI and carries the installed version.
    const pypiLink = footer.querySelector('a[href*="pypi.org"]');
    expect(pypiLink).not.toBeNull();
    expect(pypiLink.textContent).toContain("0.3.0");
    // Data vintage link points at the Census 2024 workbook.
    const sourceLink = footer.querySelector('a[href*="census.gov"]');
    expect(sourceLink).not.toBeNull();
    expect(sourceLink.textContent).toMatch(
      /Census Bureau SPM Thresholds by Metro Area 2024/,
    );
  });

  it("does not render the version link when packageVersion is missing", () => {
    // Older bundles predating PR with `packageVersion` should still
    // render cleanly — the link just disappears rather than crashing.
    render(
      <CalculatorWorkbench
        data={makeCalculatorData({ packageVersion: undefined })}
      />,
    );
    const footer = screen.getByTestId("version-footer");
    expect(
      footer.querySelector('a[href*="pypi.org"]'),
    ).toBeNull();
    // Data-vintage link still present.
    expect(
      footer.querySelector('a[href*="census.gov"]'),
    ).not.toBeNull();
  });

  it("links out to both BLS methodology and the Census SPM report", () => {
    render(<CalculatorWorkbench data={makeCalculatorData()} />);
    const card = screen.getByTestId("methodology-card");
    expect(
      card.querySelector('a[href*="bls.gov/pir/spm/garner_spm_choices"]'),
    ).not.toBeNull();
    expect(
      card.querySelector(
        'a[href*="census.gov/library/publications/2025/demo/p60-287"]',
      ),
    ).not.toBeNull();
  });
});

describe("nowcast year", () => {
  it("labels nowcast years in the year selector and shows the badge", () => {
    render(<CalculatorWorkbench data={makeCalculatorData()} />);

    const option = screen.getByRole("option", { name: "2025 (nowcast)" });
    fireEvent.change(option.closest("select"), {
      target: { value: "2025" },
    });

    expect(screen.getAllByText(/Nowcast/).length).toBeGreaterThan(0);
    const disclaimer = screen.getByTestId("nowcast-disclaimer");
    expect(disclaimer.textContent).toContain("NOT a BLS publication");
    expect(
      screen.getAllByRole("link", { name: /working paper/i }).length,
    ).toBeGreaterThan(0);
  });

  it("does not show the nowcast disclaimer for published years", () => {
    render(<CalculatorWorkbench data={makeCalculatorData()} />);
    expect(screen.queryByTestId("nowcast-disclaimer")).toBeNull();
  });
});
