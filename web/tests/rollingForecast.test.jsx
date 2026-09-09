import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import CalculatorWorkbench from "../src/components/CalculatorWorkbench";
import {
  AVAILABLE_YEARS,
  FORECAST_CONTENT_SHA256,
  MODELED_AREA_ID,
  makeRollingCalculatorData,
} from "./fixtures/rollingCalculatorData";

function selectYear(year) {
  fireEvent.change(screen.getByLabelText("Threshold year"), {
    target: { value: String(year) },
  });
}
function selectScenario(scenario) {
  fireEvent.change(screen.getByLabelText("Real spending"), {
    target: { value: scenario },
  });
}
function selectArea(id) {
  fireEvent.change(screen.getByLabelText("SPM estimation area"), {
    target: { value: id },
  });
}
function yearRow(year) {
  const table = within(screen.getByTestId("year-by-year-card")).getByRole(
    "table",
  );
  return within(table)
    .getAllByRole("row")
    .find(
      (row) =>
        within(row).queryAllByRole("cell")[0]?.textContent === String(year),
    );
}

describe("canonical rolling CE and ACS forecasts", () => {
  it("uses the declared scenario and each year's own thresholds, shares and geography", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    expect(screen.getByLabelText("Real spending")).toHaveValue("ce_trend");
    expect(screen.getByLabelText("Threshold year")).toHaveValue("2025");
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$50,041");
    expect(screen.getByTestId("primary-result")).toHaveTextContent("1.200");
    selectYear(2026);
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$58,800");
    expect(screen.getByTestId("primary-result")).toHaveTextContent("1.400");
    expect(yearRow(2026)).toHaveTextContent("$42,000");
    selectScenario("zero_real");
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$52,800");
    expect(screen.getByTestId("primary-result")).toHaveTextContent("1.200");
    expect(yearRow(2026)).toHaveTextContent("$44,000");
  });

  it("honors an artifact default of zero real spending growth", () => {
    const data = makeRollingCalculatorData();
    data.forecast.defaultScenario = "zero_real";
    render(<CalculatorWorkbench data={data} />);
    expect(screen.getByLabelText("Real spending")).toHaveValue("zero_real");
    selectYear(2026);
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$52,800");
  });

  it("shows all 14 years and updates the full 2035 horizon when the scenario changes", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    const table = within(screen.getByTestId("year-by-year-card")).getByRole(
      "table",
    );
    expect(within(table).getAllByRole("row")).toHaveLength(15);
    for (const year of AVAILABLE_YEARS) expect(yearRow(year)).toBeTruthy();
    for (const [year, base, factor, local] of [
      [2024, "$39,430", "1.160", "$45,736"],
      [2025, "$41,701", "1.200", "$50,041"],
      [2026, "$42,000", "1.400", "$58,800"],
      [2030, "$46,000", "1.600", "$73,600"],
      [2035, "$51,000", "1.850", "$94,350"],
    ]) {
      expect(yearRow(year)).toHaveTextContent(base);
      expect(yearRow(year)).toHaveTextContent(factor);
      expect(yearRow(year)).toHaveTextContent(local);
    }
    selectYear(2035);
    expect(within(table).getAllByRole("row")).toHaveLength(15);
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$94,350");
    selectScenario("zero_real");
    expect(yearRow(2026)).toHaveTextContent("$52,800");
    expect(yearRow(2030)).toHaveTextContent("$62,400");
    expect(yearRow(2035)).toHaveTextContent("$75,525");
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$75,525");
  });

  it("retains exact published national anchors and published BLS shares across scenarios through 2025", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    for (const scenario of ["ce_trend", "zero_real"]) {
      selectScenario(scenario);
      for (const [year, base] of [
        [2022, "$34,518"],
        [2023, "$36,606"],
        [2024, "$39,430"],
        [2025, "$41,701"],
      ]) {
        selectYear(year);
        expect(screen.getByText("Published by BLS")).toBeTruthy();
        expect(
          screen.getByText("Housing shares published by BLS"),
        ).toBeTruthy();
        expect(yearRow(year)).toHaveTextContent(base);
      }
    }
    expect(screen.getByText("Modeled geography")).toBeTruthy();
    expect(screen.getByTestId("methodology-card")).toHaveTextContent("0.400");
    expect(screen.getByTestId("version-footer")).not.toHaveTextContent(
      /carried/,
    );
  });

  it("uses selected-area status even when the year's geography summary is mixed", () => {
    const data = makeRollingCalculatorData();
    expect(data.forecast.scenarios.ce_trend.years[2024].geography_status).toBe(
      "mixed",
    );
    render(<CalculatorWorkbench data={data} />);
    selectYear(2024);
    expect(screen.getByText("2024 published geography anchor")).toBeTruthy();
    expect(screen.queryByText("Modeled geography")).toBeNull();
    selectArea(MODELED_AREA_ID);
    expect(screen.getByText("Modeled geography")).toBeTruthy();
    expect(screen.queryByText("2024 published geography anchor")).toBeNull();
    expect(screen.getByText("Published by BLS")).toBeTruthy();
    expect(screen.getByText("Housing shares published by BLS")).toBeTruthy();
    expect(screen.getByTestId("acs-validation-warning")).toHaveTextContent(
      /no published Census anchor/,
    );
    selectArea("35620");
    selectYear(2025);
    expect(screen.getByText("Modeled geography")).toBeTruthy();
    expect(screen.getByText("Housing shares published by BLS")).toBeTruthy();
    selectYear(2026);
    expect(screen.queryByText("Published by BLS")).toBeNull();
    expect(screen.getByText("Modeled housing shares")).toBeTruthy();
    expect(screen.getByTestId("forecast-disclaimer")).toHaveTextContent(
      /conditional research forecast/i,
    );
    expect(screen.getByTestId("forecast-disclaimer")).toHaveTextContent(
      /not (?:official )?BLS or CBO forecasts/i,
    );
  });

  it("applies household composition without changing national bases", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    selectYear(2026);
    fireEvent.change(screen.getByLabelText("Adults"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByLabelText("Children"), {
      target: { value: "0" },
    });
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$27,252");
    expect(yearRow(2026)).toHaveTextContent("$42,000");
    expect(yearRow(2026)).toHaveTextContent("1.400");
    expect(yearRow(2030)).toHaveTextContent("$34,111");
  });

  it("uses the selected tenure's rolling housing share", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    selectYear(2026);
    fireEvent.mouseDown(
      screen.getByRole("tab", { name: "Mortgage", exact: true }),
      { button: 0, ctrlKey: false },
    );
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$50,840");
    expect(screen.getByTestId("primary-result")).toHaveTextContent("1.240");
    expect(yearRow(2026)).toHaveTextContent("$41,000");
    expect(yearRow(2026)).toHaveTextContent("$50,840");
  });

  it("shows annual CE and ACS windows and observed versus projected counts", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    for (const [year, ce, acs, ceCounts, acsCounts] of [
      [
        2022,
        "2017Q2–2022Q1",
        "2017–2021",
        "20 observed / 0 projected quarters",
        "5 observed / 0 projected years",
      ],
      [
        2025,
        "2020Q2–2025Q1",
        "2020–2024",
        "20 observed / 0 projected quarters",
        "5 observed / 0 projected years",
      ],
      [
        2026,
        "2021Q2–2026Q1",
        "2021–2025",
        "16 observed / 4 projected quarters",
        "4 observed / 1 projected years",
      ],
      [
        2035,
        "2030Q2–2035Q1",
        "2030–2034",
        "0 observed / 20 projected quarters",
        "0 observed / 5 projected years",
      ],
    ]) {
      selectYear(year);
      const windows = screen.getByTestId("source-windows");
      for (const text of [ce, acs, ceCounts, acsCounts])
        expect(windows).toHaveTextContent(text);
    }
  });

  it("identifies uniform CBO CPI component and rent growth as an assumption and retains real spending choices", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    selectYear(2026);
    const methodology = screen.getByTestId("methodology-card");
    expect(methodology).toHaveTextContent(/CBO.*annual.*CPI/i);
    expect(methodology).toHaveTextContent(/uniform.*component.*rent/i);
    expect(methodology).toHaveTextContent(/modeling assumption/i);
    expect(methodology).toHaveTextContent(/not a CBO rent forecast/i);
    expect(methodology).toHaveTextContent("2026: 2.3%");
    expect(methodology).toHaveTextContent("-1.25%");
    expect(methodology).not.toHaveTextContent("+-1.25%");
    expect(methodology).toHaveTextContent(/rolling history (?:is )?retained/i);
    expect(methodology).toHaveTextContent(
      /CE replication (?:is )?approximate/i,
    );
    expect(methodology).toHaveTextContent(/uncertainty (?:is )?not estimated/i);
    expect(methodology).not.toHaveTextContent(
      /empirically best|best scenario/i,
    );
    selectScenario("zero_real");
    expect(methodology).toHaveTextContent("0.00%");
    expect(methodology).toHaveTextContent("2026: 2.3%");
  });

  it("reproduces the canonical content, year and selected scenario without obsolete execution paths", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    for (const year of [2022, 2025, 2026, 2035]) {
      selectYear(year);
      const snippet = screen.getByText(
        /from spm_calculator import/,
      ).textContent;
      expect(snippet).toContain(
        "from spm_calculator import load_forecast, SPMUnit",
      );
      expect(snippet).toContain(
        `load_forecast(expected_sha256="${FORECAST_CONTENT_SHA256}")`,
      );
      expect(snippet).toContain("projection.calculate_unit(SPMUnit(");
      expect(snippet).toContain(`year=${year}`);
      expect(snippet).toContain('scenario="ce_trend"');
      expect(snippet).toContain('print(result["threshold"])');
      expect(snippet).not.toMatch(
        /load_release|inflation_factor|nowcast|price-only forecast/i,
      );
    }
    selectScenario("zero_real");
    selectArea("1002");
    const snippet = screen.getByText(/from spm_calculator import/).textContent;
    expect(snippet).toContain('scenario="zero_real"');
    expect(snippet).toContain('geography_kind="metro"');
    expect(snippet).toContain('geography_id="1002"');
    expect(screen.getByTestId("forecast-provenance")).toHaveTextContent(
      FORECAST_CONTENT_SHA256,
    );
    expect(screen.getByTestId("version-footer")).toHaveTextContent(
      "a".repeat(64),
    );
  });

  it("refuses missing annual rent indices without substituting another year's geography", () => {
    const data = makeRollingCalculatorData();
    delete data.forecast.scenarios.ce_trend.years[2025].rent_indices["35620"];
    render(<CalculatorWorkbench data={data} />);
    expect(screen.getByTestId("primary-result")).toHaveTextContent(
      "Unavailable",
    );
    expect(screen.getByTestId("primary-result")).not.toHaveTextContent(/\$/);
    expect(yearRow(2025)).toHaveTextContent("Unavailable");
    selectYear(2026);
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$58,800");
  });

  it("warns for the selected spending scenario when its matching horizon fails baseline", () => {
    const data = makeRollingCalculatorData();
    data.forecast.validation.ce.by_horizon[5].scenarios.ce_trend = {
      mean_absolute_percentage_error: 3,
      beats_baseline: false,
    };
    render(<CalculatorWorkbench data={data} />);
    selectYear(2026);
    expect(screen.queryByTestId("ce-validation-warning")).toBeNull();
    selectYear(2030);
    expect(screen.getByTestId("ce-validation-warning")).toHaveTextContent(
      /did not outperform inflation-only/,
    );
    expect(screen.getByTestId("forecast-methodology")).toHaveTextContent(
      "5-year CE MAPE: 3.00% vs 1.20% (2 folds)",
    );
    selectScenario("zero_real");
    expect(screen.queryByTestId("ce-validation-warning")).toBeNull();
    expect(screen.getByTestId("forecast-methodology")).toHaveTextContent(
      "5-year CE MAPE: 0.90% vs 1.20% (2 folds)",
    );
  });

  it("explicitly identifies horizons beyond retrospective support instead of applying aggregate validation", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    expect(screen.queryByTestId("acs-validation-warning")).toBeNull();
    selectYear(2026);
    expect(screen.getByTestId("acs-validation-warning")).toHaveTextContent(
      /2-year geographic horizon.*no retrospective backtest support/i,
    );
    expect(screen.queryByTestId("ce-validation-warning")).toBeNull();
    selectYear(2035);
    expect(screen.getByTestId("ce-validation-warning")).toHaveTextContent(
      /10-year spending horizon.*no retrospective backtest support/i,
    );
    expect(screen.getByTestId("acs-validation-warning")).toHaveTextContent(
      /11-year geographic horizon.*no retrospective backtest support/i,
    );
    const methodology = screen.getByTestId("forecast-methodology");
    expect(methodology).toHaveTextContent(/CE scores cover 1–6 years/);
    expect(methodology).toHaveTextContent(
      /does not validate the selected 11-year geographic horizon/,
    );
    expect(methodology).not.toHaveTextContent(/10-year CE MAPE:/);
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$94,350");
  });

  it("keeps failed ACS validation adjacent only where the projected component is used", () => {
    const data = makeRollingCalculatorData();
    data.forecast.validation.acs.mean_absolute_percentage_error = 1.6;
    data.forecast.validation.acs.beats_baseline = false;
    render(<CalculatorWorkbench data={data} />);
    expect(
      within(screen.getByTestId("primary-result")).getByTestId(
        "acs-validation-warning",
      ),
    ).toHaveTextContent(
      "Modeled geographic change did not outperform unchanged indices",
    );
    selectYear(2024);
    expect(screen.queryByTestId("acs-validation-warning")).toBeNull();
  });

  it("updates rental-support diagnostics by area and year while preserving calculated thresholds", () => {
    const data = makeRollingCalculatorData();
    data.forecast.scenarios.ce_trend.years[2026].median_diagnostics = {
      35620: {
        unique_records: 12,
        kish_effective_count: 8.5,
        thin_support: true,
        topcoded_weight_share: 0,
      },
      41940: {
        unique_records: 120,
        kish_effective_count: 80,
        thin_support: false,
        topcoded_weight_share: 0.6,
        material_topcoding: true,
      },
      1002: {
        unique_records: 300,
        kish_effective_count: 250,
        thin_support: false,
        topcoded_weight_share: 0,
      },
    };
    render(<CalculatorWorkbench data={data} />);
    selectYear(2026);
    const result = screen.getByTestId("primary-result");
    let diagnostic = within(result).getByTestId("median-diagnostics-warning");
    expect(diagnostic).toHaveTextContent("Thin rental support");
    expect(diagnostic).toHaveTextContent("12 unique records");
    expect(diagnostic).toHaveTextContent("Kish effective count 8.5");
    expect(diagnostic).toHaveTextContent(
      "Repeated future cohorts do not add independent observations",
    );
    expect(diagnostic).toHaveTextContent(
      "research diagnostics, not Census publication rules",
    );
    expect(result).toHaveTextContent("$58,800");
    selectArea("41940");
    diagnostic = within(result).getByTestId("median-diagnostics-warning");
    expect(diagnostic).toHaveTextContent("Topcoding may affect this median");
    expect(diagnostic).toHaveTextContent("60.0% topcoded weight");
    expect(diagnostic).not.toHaveTextContent("Thin rental support");
    expect(result).toHaveTextContent("$67,200");
    selectYear(2025);
    expect(
      within(result).queryByTestId("median-diagnostics-warning"),
    ).toBeNull();
    selectYear(2026);
    selectArea("1002");
    expect(
      within(result).queryByTestId("median-diagnostics-warning"),
    ).toBeNull();
    expect(result).toHaveTextContent("$33,600");
  });
});
