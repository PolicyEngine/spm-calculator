import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";

import { loadCalculatorData } from "../lib/loadCalculatorData";
import CalculatorWorkbench from "../src/components/CalculatorWorkbench";

afterEach(() => vi.unstubAllGlobals());

describe("pinned release integration", () => {
  it("uses published 2025 data and places release provenance in the app footnote", async () => {
    const data = await loadCalculatorData();
    expect(data.baseThresholds["2025"].renter).toBe(41700.555713);
    expect(data.baseThresholds["2026"]).toBeUndefined();
    render(<CalculatorWorkbench data={data} />);
    const footnote = screen.getByTestId("version-footer");
    expect(footnote.textContent).toContain(data.releaseMetadata.sha256);
    expect(footnote.textContent).toContain("2024 (carried");
    const layout = readFileSync("app/layout.jsx", "utf8");
    expect(layout).not.toMatch(/releaseMetadata|release-provenance|packageVersion|informationDate/);
  });

  it("offers every official Census area offline without custom ACS options", async () => {
    const fetch = vi.fn(() => { throw new Error("Network unavailable"); });
    vi.stubGlobal("fetch", fetch);
    const data = await loadCalculatorData();
    expect(data.acsLookup).toBeUndefined();
    render(<CalculatorWorkbench data={data} />);
    const areas = screen.getByLabelText("Census metro/nonmetro area");
    expect(areas.options.length).toBe(341);
    expect(Object.fromEntries(
      Array.from(areas.options, (option) => [option.value, option.textContent]),
    )).toEqual(Object.fromEntries(
      Object.entries(data.metroAreas).map(([id, area]) => [id, area.name]),
    ));
    fireEvent.change(areas, { target: { value: "1002" } });
    expect(screen.getByRole("heading", { name: "Alabama Nonmetro" })).toBeTruthy();
    expect(screen.getByText(/geography_id="1002"/)).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("keeps Census residual state metro groups available and labels carried indices", async () => {
    const data = await loadCalculatorData();
    render(<CalculatorWorkbench data={data} />);
    const [id, area] = Object.entries(data.metroAreas).find(([, value]) => value.name === "Alaska Metro");
    fireEvent.change(screen.getByLabelText("Census metro/nonmetro area"), {
      target: { value: id },
    });
    expect(screen.getByRole("heading", { name: area.name })).toBeTruthy();
    expect(screen.getByText("2024 Census rent index (carried)")).toBeTruthy();
    expect(screen.queryByText("Published metro adjustment factor")).toBeNull();
  });

  it("does not calculate a zero-dollar threshold for unsupported adult counts", async () => {
    render(<CalculatorWorkbench data={await loadCalculatorData()} />);
    const adults = screen.getByLabelText("Adults");
    expect(adults.min).toBe("1");
    fireEvent.change(adults, {target: {value: "0"}});
    // The input widget may clamp invalid entries; if it passes one through,
    // the calculator must surface classification rather than a $0 threshold.
    if (adults.value === "0") {
      expect(screen.getByRole("alert").textContent).toContain("classified SPM adult");
    } else {
      expect(Number(adults.value)).toBeGreaterThanOrEqual(1);
    }
  });
});
