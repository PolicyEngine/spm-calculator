import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";

import { loadCalculatorData } from "../lib/loadCalculatorData";
import { loadStateRentOptions, loadCountyRentOptions, loadDistrictRentOptions, getAcsYearForThresholdYear } from "../lib/acsLookup";
import CalculatorWorkbench from "../src/components/CalculatorWorkbench";

afterEach(() => vi.unstubAllGlobals());

describe("pinned release integration", () => {
  it("resolves state, county and district rents without requests or credentials", async () => {
    const fetch = vi.fn(() => { throw new Error("Network unavailable"); });
    vi.stubGlobal("fetch", fetch);
    expect(getAcsYearForThresholdYear(2025)).toBe(2023);
    const state = await loadStateRentOptions(2023);
    const county = await loadCountyRentOptions(2023, "06");
    const district = await loadDistrictRentOptions(2023, "06");
    expect(state.options.find(x => x.id === "06").medianRent).toBeGreaterThan(0);
    expect(county.options.find(x => x.id === "06001").medianRent).toBeGreaterThan(0);
    expect(district.options.find(x => x.id === "0601").medianRent).toBeGreaterThan(0);
    expect(fetch).not.toHaveBeenCalled();
    await expect(loadCountyRentOptions(2022, "06")).rejects.toThrow("unavailable");
    await expect(loadCountyRentOptions(2023, "99")).rejects.toThrow("No published rent");
  });

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

  it("keeps county selection useful while offline", async () => {
    const fetch = vi.fn(() => { throw new Error("Network unavailable"); });
    vi.stubGlobal("fetch", fetch);
    render(<CalculatorWorkbench data={await loadCalculatorData()} />);
    const option = screen.getByRole("option", { name: "County" });
    fireEvent.change(option.closest("select"), {target: {value: "county"}});
    expect(await screen.findByRole("option", { name: /Alameda County/ })).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
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
