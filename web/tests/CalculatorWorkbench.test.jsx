/**
 * Smoke and regression tests for CalculatorWorkbench.
 *
 * These tests render the component against a synthetic data fixture
 * (see ./fixtures/calculatorData.js) and assert invariants the UI is
 * supposed to uphold — they don't re-test the math, they test that
 * the math is surfaced and that the version/methodology plumbing
 * doesn't regress.
 */

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import CalculatorWorkbench from "../src/components/CalculatorWorkbench";
import RootLayout from "../app/layout";
import { makeCalculatorData } from "./fixtures/calculatorData";

describe("CalculatorWorkbench", () => {
  it("renders one shared navigation header in the actual page layout", () => {
    const layout = RootLayout({
      children: <CalculatorWorkbench data={makeCalculatorData()} />,
    });
    // Render the real body without nesting html/head inside jsdom's body.
    render(
      layout.props.children.find((child) => child.type === "body").props
        .children,
    );
    expect(
      screen.getAllByRole("button", { name: "Toggle navigation" }),
    ).toHaveLength(1);
    expect(screen.getByTestId("version-footer")).toBeTruthy();
  });

  it("shows matching search results and selects an area with a click", () => {
    render(<CalculatorWorkbench data={makeCalculatorData()} />);
    fireEvent.change(screen.getByLabelText("Search Census areas"), {
      target: { value: "san jose" },
    });
    const matches = screen.getByRole("listbox", {
      name: "Matching Census areas",
    });
    expect(within(matches).getAllByRole("option")).toHaveLength(1);
    fireEvent.click(
      within(matches).getByRole("option", {
        name: "San Jose-Sunnyvale-Santa Clara, CA MSA",
      }),
    );
    expect(
      screen.getByRole("heading", {
        name: "San Jose-Sunnyvale-Santa Clara, CA MSA",
      }),
    ).toBeTruthy();
    expect(screen.getByLabelText("Search Census areas")).toHaveValue("");
    expect(screen.getByLabelText("Census metro/nonmetro area")).toHaveValue(
      "41940",
    );
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("selects a Census area code with Enter and reports empty searches", () => {
    render(<CalculatorWorkbench data={makeCalculatorData()} />);
    const search = screen.getByLabelText("Search Census areas");
    fireEvent.change(search, { target: { value: "1002" } });
    fireEvent.keyDown(search, { key: "Enter", code: "Enter" });
    expect(
      screen.getByRole("heading", { name: "Alabama Nonmetro" }),
    ).toBeTruthy();
    fireEvent.change(search, { target: { value: "no matching place" } });
    expect(screen.getByText("No Census areas match your search.")).toBeTruthy();
    const matches = screen.getByRole("listbox", {
      name: "Matching Census areas",
    });
    expect(within(matches).queryAllByRole("option")).toHaveLength(0);
    expect(
      screen.getByRole("heading", { name: "Alabama Nonmetro" }),
    ).toBeTruthy();
    fireEvent.change(search, { target: { value: "" } });
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(
      screen.getByLabelText("Census metro/nonmetro area").options,
    ).toHaveLength(3);
  });

  it("limits location choices to Census metro/nonmetro workbook areas", () => {
    render(<CalculatorWorkbench data={makeCalculatorData()} />);

    expect(screen.getByLabelText("Census metro/nonmetro area")).toBeTruthy();
    expect(screen.queryByLabelText("Geography type")).toBeNull();
    for (const name of [
      "National average",
      "State",
      "County",
      "Congressional district",
    ]) {
      expect(screen.queryByRole("option", { name })).toBeNull();
    }
    expect(
      screen.getByRole("option", { name: "Alabama Nonmetro" }),
    ).toBeTruthy();
    expect(screen.queryByRole("option", { name: "2023" })).toBeNull();
  });

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
    expect(card.textContent).toMatch(/metro\/nonmetro/);
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
    expect(footer.querySelector('a[href*="pypi.org"]')).toBeNull();
    // Data-vintage link still present.
    expect(footer.querySelector('a[href*="census.gov"]')).not.toBeNull();
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

describe("published and nowcast years", () => {
  it("keeps the nowcast label and disclaimer machinery for future years", () => {
    const data = makeCalculatorData();
    data.baseThresholds["2026"] = {
      renter: 42660,
      owner_with_mortgage: 42273,
      owner_without_mortgage: 35116,
    };
    data.nowcast["2026"] = {
      label: "PolicyEngine nowcast of 2026 thresholds — NOT a BLS publication",
      method: "Illustrative consumption-growth method.",
    };
    render(<CalculatorWorkbench data={data} />);

    const option = screen.getByRole("option", { name: "2026 (nowcast)" });
    fireEvent.change(option.closest("select"), {
      target: { value: "2026" },
    });

    expect(screen.getAllByText(/Nowcast/).length).toBeGreaterThan(0);
    const disclaimer = screen.getByTestId("nowcast-disclaimer");
    expect(disclaimer.textContent).toContain("NOT a BLS publication");
    expect(
      screen.getAllByRole("link", { name: /working paper/i }).length,
    ).toBeGreaterThan(0);
  });

  it("marks 2025 published and surfaces its archived evaluation", () => {
    render(<CalculatorWorkbench data={makeCalculatorData()} />);

    expect(screen.getByRole("option", { name: "2025" })).not.toBeNull();
    expect(
      screen.queryByRole("option", { name: /2025 \(nowcast\)/ }),
    ).toBeNull();
    expect(screen.queryByTestId("nowcast-disclaimer")).toBeNull();
    expect(screen.queryByText("Nowcast — not BLS")).toBeNull();
    expect(screen.getAllByText("Published by BLS").length).toBeGreaterThan(0);
    const evaluation = screen.getByTestId("nowcast-evaluation");
    expect(evaluation.textContent).toMatch(/\$40,756/);
    expect(evaluation.textContent).toMatch(/-2\.27% versus BLS/);
    expect(evaluation.textContent).toMatch(/1\.17%/);
  });
});
