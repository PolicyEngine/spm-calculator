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
    if (data.forecast.method === "rolling_ce_acs_v1") {
      const entry =
        data.forecast.scenarios[data.forecast.defaultScenario].years["2025"];
      expect(entry.thresholds).toEqual(data.baseThresholds["2025"]);
      expect(screen.getByText("Published by BLS")).toBeTruthy();
      expect(
        screen.getByText("Modeled geography and housing shares"),
      ).toBeTruthy();
      expect(footnote.textContent).toContain(data.forecast.contentSha256);
      expect(footnote.textContent).not.toContain("carried");
      expect(
        screen.getByRole("link", {
          name: "Preview Python API: calculator PR36",
        }),
      ).toHaveAttribute(
        "href",
        "https://github.com/PolicyEngine/spm-calculator/pull/36",
      );
    } else {
      expect(footnote.textContent).toContain("2024 (carried");
    }
    const layout = readFileSync("app/layout.jsx", "utf8");
    expect(layout).not.toMatch(
      /releaseMetadata|release-provenance|packageVersion|informationDate|contentSha256|forecast-provenance|assumptionSha256|load_forecast/,
    );
  });

  it("offers every official Census area offline without custom ACS options", async () => {
    const fetch = vi.fn(() => {
      throw new Error("Network unavailable");
    });
    vi.stubGlobal("fetch", fetch);
    const data = await loadCalculatorData();
    expect(data.acsLookup).toBeUndefined();
    if (data.forecast.method === "rolling_ce_acs_v1") {
      const areaIds = Object.keys(data.metroAreas).sort();
      for (const scenario of Object.values(data.forecast.scenarios)) {
        for (let year = 2024; year <= 2030; year++) {
          expect(Object.keys(scenario.years[year].rent_indices).sort()).toEqual(
            areaIds,
          );
        }
      }
    }
    render(<CalculatorWorkbench data={data} />);
    const areas = screen.getByLabelText("Census metro/nonmetro area");
    expect(areas.options.length).toBe(341);
    expect(
      Object.fromEntries(
        Array.from(areas.options, (option) => [
          option.value,
          option.textContent,
        ]),
      ),
    ).toEqual(
      Object.fromEntries(
        Object.entries(data.metroAreas).map(([id, area]) => [id, area.name]),
      ),
    );
    fireEvent.change(areas, { target: { value: "1002" } });
    expect(
      screen.getByRole("heading", { name: "Alabama Nonmetro" }),
    ).toBeTruthy();
    expect(screen.getByText(/geography_id=['"]1002['"]/)).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("keeps Census residual state metro groups available and labels geography status", async () => {
    const data = await loadCalculatorData();
    render(<CalculatorWorkbench data={data} />);
    const [id, area] = Object.entries(data.metroAreas).find(
      ([, value]) => value.name === "Alaska Metro",
    );
    fireEvent.change(screen.getByLabelText("Census metro/nonmetro area"), {
      target: { value: id },
    });
    expect(screen.getByRole("heading", { name: area.name })).toBeTruthy();
    if (data.forecast.method === "rolling_ce_acs_v1") {
      expect(
        screen.getByText("Modeled geography and housing shares"),
      ).toBeTruthy();
      expect(screen.queryByText(/Census rent index \(carried\)/)).toBeNull();
      fireEvent.change(
        screen.getByRole("option", { name: "2024" }).closest("select"),
        {
          target: { value: "2024" },
        },
      );
      expect(screen.getByText("2024 published geography anchor")).toBeTruthy();
      expect(
        screen.queryByText("Modeled geography and housing shares"),
      ).toBeNull();
    } else {
      expect(screen.getByText("2024 Census rent index (carried)")).toBeTruthy();
    }
    expect(screen.queryByText("Published metro adjustment factor")).toBeNull();
  });

  it("does not calculate a zero-dollar threshold for unsupported adult counts", async () => {
    render(<CalculatorWorkbench data={await loadCalculatorData()} />);
    const adults = screen.getByLabelText("Adults");
    expect(adults.min).toBe("1");
    fireEvent.change(adults, { target: { value: "0" } });
    // The input widget may clamp invalid entries; if it passes one through,
    // the calculator must surface classification rather than a $0 threshold.
    if (adults.value === "0") {
      expect(
        screen
          .getAllByRole("alert")
          .some((alert) => alert.textContent.includes("classified SPM adult")),
      ).toBe(true);
    } else {
      expect(Number(adults.value)).toBeGreaterThanOrEqual(1);
    }
  });

  it("offers 2026–2030 forecasts with explicit assumptions and replayable Python", async () => {
    const data = await loadCalculatorData();
    const isRolling = data.forecast.method === "rolling_ce_acs_v1";
    render(<CalculatorWorkbench data={data} />);
    for (let year = 2026; year <= 2030; year++) {
      const option = screen.getByRole("option", { name: `${year} (forecast)` });
      fireEvent.change(option.closest("select"), {
        target: { value: String(year) },
      });
      expect(screen.getByTestId("forecast-disclaimer").textContent).toContain(
        "not BLS or CBO forecasts",
      );
      expect(screen.getByTestId("forecast-provenance").textContent).toContain(
        data.forecast.assumptionSha256,
      );
      if (isRolling) {
        expect(screen.getByTestId("version-footer").textContent).not.toContain(
          "carried",
        );
        expect(
          screen.getByText("Modeled geography and housing shares"),
        ).toBeTruthy();
      } else {
        expect(screen.getByTestId("version-footer").textContent).toContain(
          "2024 (carried",
        );
      }
      expect(screen.queryByText("Published by BLS")).toBeNull();
      const snippet = screen.getByText(
        /from spm_calculator import/,
      ).textContent;
      if (isRolling) {
        expect(snippet).toContain(
          "from spm_calculator import load_forecast, SPMUnit",
        );
        expect(snippet).toContain(
          `load_forecast(expected_sha256="${data.forecast.contentSha256}")`,
        );
        expect(snippet).toContain("projection.calculate_unit(SPMUnit(");
        expect(snippet).toContain(`year=${year}`);
        expect(snippet).toContain(
          `scenario="${data.forecast.defaultScenario}"`,
        );
        expect(snippet).toContain('print(result["threshold"])');
        expect(snippet).not.toContain("inflation_factor");
      } else {
        expect(snippet).toContain("year=2025");
        expect(snippet).toContain(
          `inflation_factor = ${data.forecast.factorsByYear[year]}`,
        );
        expect(snippet).toContain(
          'print(result["threshold"] * inflation_factor)',
        );
      }
    }
    fireEvent.change(
      screen.getByRole("option", { name: "2026 (forecast)" }).closest("select"),
      {
        target: { value: "2026" },
      },
    );
    if (isRolling) {
      const entry =
        data.forecast.scenarios[data.forecast.defaultScenario].years["2026"];
      const areaId = screen.getByLabelText("Census metro/nonmetro area").value;
      const locationFactor =
        1 + entry.housing_shares.renter * (entry.rent_indices[areaId] - 1);
      // The default 2A2C composition is the reference family (scale = 1).
      const threshold = entry.thresholds.renter * locationFactor;
      const formattedThreshold = new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
      }).format(threshold);
      expect(screen.getAllByText(formattedThreshold).length).toBeGreaterThan(0);
    } else {
      expect(screen.getAllByText("$49,482").length).toBeGreaterThan(0);
    }
    fireEvent.change(
      screen.getByRole("option", { name: "2025" }).closest("select"),
      {
        target: { value: "2025" },
      },
    );
    expect(screen.getByText("Published by BLS")).toBeTruthy();
    if (isRolling) {
      expect(
        screen.getByText("Modeled geography and housing shares"),
      ).toBeTruthy();
    } else {
      expect(screen.queryByTestId("forecast-disclaimer")).toBeNull();
    }
    expect(
      screen.getByText(/from spm_calculator import/).textContent,
    ).not.toContain("inflation_factor");
  });
});
