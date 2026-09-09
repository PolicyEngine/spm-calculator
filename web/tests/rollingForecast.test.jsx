import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import CalculatorWorkbench from "../src/components/CalculatorWorkbench";
import RootLayout from "../app/layout";
import {
  FORECAST_CONTENT_SHA256,
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

function yearRow(year) {
  const table = within(screen.getByTestId("year-by-year-card")).getByRole(
    "table",
  );
  return within(table)
    .getAllByRole("row")
    .find((row) => {
      const cells = within(row).queryAllByRole("cell");
      return cells[0]?.textContent === String(year);
    });
}

describe("rolling CE and ACS forecasts", () => {
  it("uses the declared scenario and the selected year's modeled geography", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);

    expect(screen.getByLabelText("Real spending")).toHaveValue("ce_trend");
    expect(screen.getByLabelText("Threshold year")).toHaveValue("2025");
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$50,041");
    expect(screen.getByTestId("primary-result")).toHaveTextContent("1.200");
    expect(yearRow(2025)).toHaveTextContent("$41,701");

    selectYear(2026);
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$58,800");
    expect(screen.getByTestId("primary-result")).toHaveTextContent("1.400");
    expect(yearRow(2026)).toHaveTextContent("$42,000");

    selectScenario("zero_real");
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$52,800");
    expect(screen.getByTestId("primary-result")).toHaveTextContent("1.200");
    expect(yearRow(2026)).toHaveTextContent("$44,000");
  });

  it("honors a different artifact default scenario", () => {
    const data = makeRollingCalculatorData();
    data.forecast.defaultScenario = "zero_real";
    render(<CalculatorWorkbench data={data} />);

    expect(screen.getByLabelText("Real spending")).toHaveValue("zero_real");
    selectYear(2026);
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$52,800");
  });

  it("shows all seven rolling years and updates every forecast row with the scenario", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    const years = screen.getByLabelText("Threshold year");
    expect(Array.from(years.options, (option) => option.value).sort()).toEqual([
      "2024",
      "2025",
      "2026",
      "2027",
      "2028",
      "2029",
      "2030",
    ]);
    const table = within(screen.getByTestId("year-by-year-card")).getByRole(
      "table",
    );
    expect(within(table).getAllByRole("row")).toHaveLength(8);
    for (const [year, base, factor, local] of [
      [2024, "$39,430", "1.160", "$45,736"],
      [2025, "$41,701", "1.200", "$50,041"],
      [2026, "$42,000", "1.400", "$58,800"],
      [2027, "$43,000", "1.450", "$62,350"],
      [2028, "$44,000", "1.500", "$66,000"],
      [2029, "$45,000", "1.550", "$69,750"],
      [2030, "$46,000", "1.600", "$73,600"],
    ]) {
      expect(yearRow(year)).toHaveTextContent(base);
      expect(yearRow(year)).toHaveTextContent(factor);
      expect(yearRow(year)).toHaveTextContent(local);
    }

    // Detail selection does not filter the history table.
    selectYear(2030);
    expect(within(table).getAllByRole("row")).toHaveLength(8);
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$73,600");
    selectScenario("zero_real");
    for (const [year, local] of [
      [2026, "$52,800"],
      [2027, "$55,125"],
      [2028, "$57,500"],
      [2029, "$59,925"],
      [2030, "$62,400"],
    ]) {
      expect(yearRow(year)).toHaveTextContent(local);
    }
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$62,400");
  });

  it("keeps both published national anchors exact across scenarios", () => {
    const data = makeRollingCalculatorData();
    render(<CalculatorWorkbench data={data} />);

    for (const scenario of ["ce_trend", "zero_real"]) {
      selectScenario(scenario);
      for (const year of [2024, 2025]) {
        expect(
          data.forecast.scenarios[scenario].years[year].thresholds,
        ).toEqual(data.baseThresholds[year]);
        selectYear(year);
        expect(screen.getAllByText("Published by BLS").length).toBeGreaterThan(
          0,
        );
        expect(yearRow(year)).toHaveTextContent(
          year === 2024 ? "$39,430" : "$41,701",
        );
      }
    }
  });

  it("applies household composition to every local year without changing national bases", () => {
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
    expect(yearRow(2026)).toHaveTextContent("$27,252");
    expect(yearRow(2030)).toHaveTextContent("$34,111");
  });

  it("uses the selected tenure's rolling share in the result and history", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    selectYear(2026);
    fireEvent.mouseDown(
      screen.getByRole("tab", { name: "Mortgage", exact: true }),
      {
        button: 0,
        ctrlKey: false,
      },
    );

    expect(screen.getByTestId("primary-result")).toHaveTextContent("$50,840");
    expect(screen.getByTestId("primary-result")).toHaveTextContent("1.240");
    expect(yearRow(2026)).toHaveTextContent("$41,000");
    expect(yearRow(2026)).toHaveTextContent("$50,840");
  });

  it("distinguishes published national values from modeled geography and the 2024 anchor", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    expect(screen.getAllByText("Published by BLS").length).toBeGreaterThan(0);
    expect(
      screen.getByText("Modeled geography and housing shares"),
    ).toBeTruthy();
    expect(screen.queryByText(/2024 Census rent index \(carried\)/)).toBeNull();
    expect(screen.getByTestId("version-footer")).not.toHaveTextContent(
      /carried/,
    );

    selectYear(2024);
    expect(screen.getByText("2024 published geography anchor")).toBeTruthy();
    expect(
      screen.queryByText("Modeled geography and housing shares"),
    ).toBeNull();

    selectYear(2026);
    expect(screen.queryByText("Published by BLS")).toBeNull();
    expect(screen.getByTestId("forecast-disclaimer")).toHaveTextContent(
      /conditional research forecast/i,
    );
    expect(screen.getByTestId("forecast-disclaimer")).toHaveTextContent(
      /not (?:official )?BLS or CBO (?:predictions|forecasts)/i,
    );
  });

  it("shows each year's CE and ACS windows with observed and projected counts", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    for (const [year, ce, acs, ceCounts, acsCounts] of [
      [
        2024,
        "2019Q2–2024Q1",
        "2019–2023",
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
        2030,
        "2025Q2–2030Q1",
        "2025–2029",
        "0 observed / 20 projected quarters",
        "0 observed / 5 projected years",
      ],
    ]) {
      selectYear(year);
      const windows = screen.getByTestId("source-windows");
      expect(windows).toHaveTextContent(ce);
      expect(windows).toHaveTextContent(acs);
      expect(windows).toHaveTextContent(ceCounts);
      expect(windows).toHaveTextContent(acsCounts);
    }
  });

  it("separates common prices from negative real spending and explains the retained history", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    selectYear(2026);
    const methodology = screen.getByTestId("methodology-card");
    expect(methodology).toHaveTextContent(/common price assumptions/i);
    expect(methodology).toHaveTextContent("2026: 2.3%");
    expect(methodology).toHaveTextContent("-1.25%");
    expect(methodology).not.toHaveTextContent("+-1.25%");
    expect(methodology).toHaveTextContent(
      /new observations (?:are )?projected/i,
    );
    expect(methodology).toHaveTextContent(/rolling history (?:is )?retained/i);
    expect(methodology).toHaveTextContent(/public PUMS rents/i);
    expect(methodology).toHaveTextContent(
      /fractionally mapped from PUMAs to Census areas/i,
    );
    expect(methodology).toHaveTextContent(/anchored to (?:published )?2024/i);
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

  it("reproduces the exact rolling content, selected year and scenario with the preview API", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    for (const year of [2024, 2025, 2026, 2030]) {
      selectYear(year);
      const snippet = screen.getByText(
        /from spm_calculator import/,
      ).textContent;
      expect(snippet).toContain(
        "from spm_calculator import load_forecast, SPMUnit",
      );
      expect(snippet).toMatch(
        new RegExp(
          `load_forecast\\(expected_sha256=['"]${FORECAST_CONTENT_SHA256}['"]\\)`,
        ),
      );
      expect(snippet).toContain("projection.calculate_unit(SPMUnit(");
      expect(snippet).toContain(`year=${year}`);
      expect(snippet).toMatch(/scenario=['"]ce_trend['"]/);
      expect(snippet).toMatch(/print\(result\[['"]threshold['"]\]\)/);
      expect(snippet).not.toMatch(
        /load_release|inflation_factor|price-only forecast/,
      );
    }
    selectScenario("zero_real");
    fireEvent.change(screen.getByLabelText("Census metro/nonmetro area"), {
      target: { value: "1002" },
    });
    const snippet = screen.getByText(/from spm_calculator import/).textContent;
    expect(snippet).toMatch(/scenario=['"]zero_real['"]/);
    expect(snippet).toMatch(/geography_kind=['"]metro['"]/);
    expect(snippet).toMatch(/geography_id=['"]1002['"]/);
    const footnote = screen.getByTestId("version-footer");
    expect(
      within(footnote).getByRole("link", {
        name: "Preview Python API: calculator PR36",
      }),
    ).toHaveAttribute(
      "href",
      "https://github.com/PolicyEngine/spm-calculator/pull/36",
    );
    expect(screen.getByTestId("forecast-provenance")).toHaveTextContent(
      FORECAST_CONTENT_SHA256,
    );
    expect(footnote).toHaveTextContent("a".repeat(64));
  });

  it("keeps search selection working with year-specific rent indices", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    selectYear(2026);
    const search = screen.getByLabelText("Search Census areas");
    fireEvent.change(search, { target: { value: "san jose" } });
    const matches = screen.getByRole("listbox", {
      name: "Matching Census areas",
    });
    expect(within(matches).getAllByRole("option")).toHaveLength(1);
    fireEvent.click(within(matches).getByRole("option"));
    expect(screen.getByLabelText("Census metro/nonmetro area")).toHaveValue(
      "41940",
    );
    expect(search).toHaveValue("");
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$67,200");
    expect(yearRow(2026)).toHaveTextContent("1.600");

    fireEvent.change(search, { target: { value: "1002" } });
    fireEvent.keyDown(search, { key: "Enter", code: "Enter" });
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$33,600");
    expect(yearRow(2026)).toHaveTextContent("0.800");
    fireEvent.change(search, { target: { value: "not a Census area" } });
    expect(screen.getByText("No Census areas match your search.")).toBeTruthy();
  });

  it("retains a single shared header and keeps forecast provenance inside the app", () => {
    const layout = RootLayout({
      children: <CalculatorWorkbench data={makeRollingCalculatorData()} />,
    });
    render(
      layout.props.children.find((child) => child.type === "body").props
        .children,
    );
    selectYear(2026);
    expect(
      screen.getAllByRole("button", { name: "Toggle navigation" }),
    ).toHaveLength(1);
    const footnote = screen.getByTestId("version-footer");
    expect(footnote).toContainElement(
      screen.getByTestId("forecast-provenance"),
    );
    const sharedChrome = Array.from(
      document.querySelectorAll("header, footer"),
    ).filter((element) => element !== footnote);
    expect(sharedChrome.length).toBeGreaterThan(0);
    for (const element of sharedChrome) {
      expect(element).not.toHaveTextContent(
        /SHA-256|Preview Python API|rolling_ce_acs_v1|research forecast/i,
      );
      expect(element).not.toHaveTextContent(FORECAST_CONTENT_SHA256);
    }
  });

  it("refuses a legacy rent-index fallback when a rolling area entry is missing", () => {
    const data = makeRollingCalculatorData();
    delete data.forecast.scenarios.ce_trend.years["2025"].rent_indices["35620"];
    render(<CalculatorWorkbench data={data} />);

    expect(screen.getByRole("alert")).toHaveTextContent(/unavailable.*area/i);
    expect(screen.getByTestId("primary-result")).toHaveTextContent(
      "Unavailable",
    );
    expect(screen.getByTestId("primary-result")).not.toHaveTextContent(/\$/);
    expect(yearRow(2025)).toHaveTextContent("Unavailable");

    selectYear(2026);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$58,800");
  });

  it("moves adjacent retrospective warnings with the selected scenario and projected year", () => {
    const data = makeRollingCalculatorData();
    data.forecast.validation.ce.scenarios.ce_trend.mean_absolute_percentage_error = 1.3;
    data.forecast.validation.ce.scenarios.ce_trend.beats_baseline = false;
    data.forecast.validation.acs.mean_absolute_percentage_error = 1.6;
    data.forecast.validation.acs.beats_baseline = false;
    render(<CalculatorWorkbench data={data} />);
    const result = screen.getByTestId("primary-result");

    // The 2025 national threshold is published, while geography is modeled.
    expect(within(result).queryByTestId("ce-validation-warning")).toBeNull();
    expect(
      within(result).getByTestId("acs-validation-warning"),
    ).toHaveTextContent(
      "Modeled geographic change did not outperform unchanged indices",
    );
    selectYear(2024);
    expect(within(result).queryByTestId("ce-validation-warning")).toBeNull();
    expect(within(result).queryByTestId("acs-validation-warning")).toBeNull();

    selectYear(2026);
    expect(
      within(result).getByTestId("ce-validation-warning"),
    ).toHaveTextContent(
      "The selected spending scenario did not outperform inflation-only",
    );
    expect(within(result).getByTestId("acs-validation-warning")).toBeTruthy();
    expect(screen.getByTestId("forecast-methodology")).toHaveTextContent(
      "Overall CE MAPE: 1.30% vs 1.20%",
    );
    expect(screen.getByTestId("forecast-methodology")).toHaveTextContent(
      "ACS MAPE: 1.60% vs 1.50%",
    );

    selectScenario("zero_real");
    expect(within(result).queryByTestId("ce-validation-warning")).toBeNull();
    expect(within(result).getByTestId("acs-validation-warning")).toBeTruthy();
    expect(screen.getByTestId("forecast-methodology")).toHaveTextContent(
      "Overall CE MAPE: 0.90% vs 1.20%",
    );
    selectScenario("ce_trend");
    expect(within(result).getByTestId("ce-validation-warning")).toBeTruthy();
    selectYear(2025);
    expect(within(result).queryByTestId("ce-validation-warning")).toBeNull();
  });

  it("uses the displayed horizon's validation even when aggregate scores beat baseline", () => {
    const data = makeRollingCalculatorData();
    data.forecast.validation.ce.by_horizon["5"].scenarios.ce_trend = {
      mean_absolute_percentage_error: 3,
      beats_baseline: false,
    };
    render(<CalculatorWorkbench data={data} />);
    const result = screen.getByTestId("primary-result");
    selectYear(2026);
    expect(within(result).queryByTestId("ce-validation-warning")).toBeNull();
    selectYear(2030);
    expect(
      within(result).getByTestId("ce-validation-warning"),
    ).toHaveTextContent(/did not outperform inflation-only/);
    const methodology = screen.getByTestId("forecast-methodology");
    expect(methodology).toHaveTextContent(
      "5-year CE MAPE: 3.00% vs 1.20% (2 folds)",
    );
    expect(methodology).toHaveTextContent(/shorter horizons have more folds/i);
    expect(methodology).toHaveTextContent(/few long-horizon folds/i);
    expect(methodology).toHaveTextContent(
      /current-vintage.*conditional on realized prices/i,
    );
    expect(methodology).toHaveTextContent(
      /0.5 shrinkage.*predeclared independently/i,
    );
    selectScenario("zero_real");
    expect(within(result).queryByTestId("ce-validation-warning")).toBeNull();
    expect(methodology).toHaveTextContent(
      "5-year CE MAPE: 0.90% vs 1.20% (2 folds)",
    );
  });

  it.each(["absent", "blocked", "missing required booleans"])(
    "warns about %s validation only while each projected component is used",
    (condition) => {
      const data = makeRollingCalculatorData();
      if (condition === "absent") {
        delete data.forecast.validation;
      } else if (condition === "blocked") {
        data.forecast.validation.ce.status = "blocked";
        data.forecast.validation.acs.status = "blocked";
      } else {
        delete data.forecast.validation.ce.scenarios.ce_trend.beats_baseline;
        delete data.forecast.validation.acs.beats_baseline;
      }
      render(<CalculatorWorkbench data={data} />);
      const result = screen.getByTestId("primary-result");
      const message =
        "This projected component has not been retrospectively validated.";
      expect(
        within(result).getByTestId("acs-validation-warning"),
      ).toHaveTextContent(message);
      expect(within(result).queryByTestId("ce-validation-warning")).toBeNull();
      selectYear(2024);
      expect(within(result).queryByTestId("acs-validation-warning")).toBeNull();
      expect(within(result).queryByTestId("ce-validation-warning")).toBeNull();
      selectYear(2026);
      expect(
        within(result).getByTestId("acs-validation-warning"),
      ).toHaveTextContent(message);
      expect(
        within(result).getByTestId("ce-validation-warning"),
      ).toHaveTextContent(message);
      expect(result).toHaveTextContent("$58,800");
    },
  );

  it("updates inline rental support diagnostics by area and year without substituting a threshold", () => {
    const data = makeRollingCalculatorData();
    data.forecast.scenarios.ce_trend.years["2026"].median_diagnostics = {
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

    fireEvent.change(screen.getByLabelText("Census metro/nonmetro area"), {
      target: { value: "41940" },
    });
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
    fireEvent.change(screen.getByLabelText("Census metro/nonmetro area"), {
      target: { value: "1002" },
    });
    expect(
      within(result).queryByTestId("median-diagnostics-warning"),
    ).toBeNull();
    expect(result).toHaveTextContent("$33,600");
  });
});
