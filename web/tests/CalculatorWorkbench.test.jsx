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
  it("starts with explicit setup instead of defaulting inputs", () => {
    render(<CalculatorWorkbench data={makeCalculatorData()} />);
    const [yearSelect, locationSelect] = screen.getAllByRole("combobox");

    expect(yearSelect).toHaveValue("");
    expect(locationSelect).toHaveValue("");
    expect(screen.getByTestId("setup-wizard")).toHaveTextContent(
      "Choose a year",
    );
    expect(screen.getByTestId("setup-wizard")).toHaveTextContent(
      "Enter adults and children",
    );
    expect(screen.queryByText("Tenure comparison")).toBeNull();
    expect(screen.queryByText("Reproduce with Python")).toBeNull();
  });

  it("renders the methodology card with the formula", () => {
    render(<CalculatorWorkbench data={makeCalculatorData()} />);
    const card = screen.getByTestId("methodology-card");
    // The Betson-scale formula must be visible to the user so they
    // can cross-check threshold values against Census documentation.
    expect(card.textContent).toMatch(/base\[tenure\]/);
    expect(card.textContent).toMatch(/equivalence_scale/);
    expect(card.textContent).toMatch(/geoadj\[tenure\]/);
    expect(card.textContent).toMatch(/metro and nonmetro/);
  });

  it("limits geography choices to official Census workbook areas", () => {
    render(<CalculatorWorkbench data={makeCalculatorData()} />);

    expect(screen.getByText("Census metro/nonmetro area")).toBeInTheDocument();
    expect(screen.queryByText("Adjustment basis")).toBeNull();
    expect(screen.queryByText("Search")).toBeNull();
    expect(
      screen.queryByRole("option", { name: "National average" }),
    ).toBeNull();
    expect(screen.queryByRole("option", { name: "State" })).toBeNull();
    expect(screen.queryByRole("option", { name: "County" })).toBeNull();
    expect(
      screen.queryByRole("option", { name: "Congressional district" }),
    ).toBeNull();
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

  it("surfaces person-level SPM unit reconstruction workflows", () => {
    render(<CalculatorWorkbench data={makeCalculatorData()} />);
    const card = screen.getByTestId("microdata-card");

    expect(card.textContent).toMatch(/Person microdata/);
    expect(card.textContent).toMatch(/SPM_ID/);
    expect(card.textContent).toMatch(/spm_unit_id/);
    expect(card.textContent).toMatch(/spm_unit_id_match/);
    expect(card.textContent).toMatch(/PECOHAB/);
    expect(screen.getByText("Unit ID docs")).toBeInTheDocument();
  });

  it("warns instead of calculating child-only SPM units", () => {
    render(<CalculatorWorkbench data={makeCalculatorData()} />);
    const [adultInput, childInput] = screen.getAllByRole("spinbutton");

    fireEvent.change(adultInput, { target: { value: "0" } });
    fireEvent.change(childInput, { target: { value: "2" } });

    expect(screen.getByTestId("composition-error").textContent).toMatch(
      /at least one adult/,
    );
  });
});
