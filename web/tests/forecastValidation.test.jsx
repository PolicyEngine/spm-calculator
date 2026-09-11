import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { getForecastValidation } from "../lib/forecastValidation";
import {
  ForecastMethodology,
  ForecastWarnings,
} from "../src/components/ForecastDiagnostics";

const AREA = "35620";
const RESIDUAL = "modeled_residual_metro:06";

function makeEntry(year) {
  return {
    national_status: year <= 2025 ? "published" : "forecast",
    housing_share_status: year <= 2025 ? "published_anchor" : "modeled",
    geography_status: "mixed",
    geography_by_area: {
      [AREA]: {
        status: year <= 2024 ? "published_anchor" : "modeled",
        anchor_status: "published_anchor",
        official_published_area: true,
      },
      [RESIDUAL]: {
        status: "modeled_unanchored",
        anchor_status: "modeled_unanchored",
        official_published_area: false,
      },
    },
  };
}

function makeForecast() {
  const scores = (mape = 0.8) => ({
    mean_absolute_percentage_error: mape,
    beats_baseline: true,
    horizon_balanced_mean_absolute_percentage_error: 0.9,
    beats_horizon_balanced_baseline: true,
  });
  const years = Object.fromEntries(
    Array.from({ length: 14 }, (_, i) => [
      String(2022 + i),
      makeEntry(2022 + i),
    ]),
  );
  return {
    method: "rolling_ce_acs_v1",
    baseYear: 2025,
    geographyAnchorYear: 2024,
    defaultScenario: "ce_trend",
    scenarios: {
      ce_trend: {
        label: "CE real-spending trend",
        realGrowthRate: 0.005,
        years,
      },
      zero_real: { label: "No real spending growth", realGrowthRate: 0, years },
    },
    validation: {
      ce: {
        status: "complete",
        unvalidated: false,
        metric: "mean_absolute_percentage_error",
        scenarios: { ce_trend: scores(), zero_real: scores(1.1) },
        baseline: {
          mean_absolute_percentage_error: 1.2,
          horizon_balanced_mean_absolute_percentage_error: 1.3,
        },
        by_horizon: Object.fromEntries(
          Array.from({ length: 6 }, (_, i) => [
            String(i + 1),
            {
              scenarios: {
                ce_trend: {
                  mean_absolute_percentage_error: 0.7,
                  beats_baseline: true,
                },
                zero_real: {
                  mean_absolute_percentage_error: 0.9,
                  beats_baseline: true,
                },
              },
              baseline: { mean_absolute_percentage_error: 1.4 },
              fold_count: 6 - i,
            },
          ]),
        ),
      },
      acs: {
        status: "complete",
        unvalidated: false,
        origin_spm_year: 2023,
        target_spm_year: 2024,
        area_count: 341,
        mean_absolute_percentage_error: 1.1,
        baseline_mean_absolute_percentage_error: 1.5,
        beats_baseline: true,
      },
    },
  };
}

function evaluation(forecast, kind, props = {}) {
  const year = props.year ?? (kind === "ce" ? 2026 : 2025);
  return getForecastValidation(
    forecast,
    props.scenarioId ?? "ce_trend",
    year,
    props.entry ?? makeEntry(year),
    props.areaId ?? AREA,
  )[kind];
}

function warnings(forecast = makeForecast(), props = {}) {
  const year = props.year ?? 2025;
  return (
    <ForecastWarnings
      forecast={forecast}
      scenarioId="ce_trend"
      year={year}
      entry={makeEntry(year)}
      areaId={AREA}
      {...props}
    />
  );
}

function methodology(forecast = makeForecast(), props = {}) {
  const year = props.year ?? 2030;
  return (
    <ForecastMethodology
      forecast={forecast}
      scenarioId="ce_trend"
      year={year}
      entry={makeEntry(year)}
      areaId={AREA}
      {...props}
    />
  );
}

describe("canonical component validation", () => {
  it("uses selected area status in a mixed year, including unpublished historical groups", () => {
    const forecast = makeForecast();
    expect(evaluation(forecast, "acs", { year: 2022 }).used).toBe(false);
    expect(
      evaluation(forecast, "acs", { year: 2022, areaId: RESIDUAL }),
    ).toMatchObject({
      used: true,
      complete: false,
      unsupportedArea: true,
    });
    expect(evaluation(forecast, "acs", { year: 2025 })).toMatchObject({
      used: true,
      complete: true,
      unsupportedArea: false,
    });
    expect(evaluation(forecast, "ce", { year: 2025 }).used).toBe(false);
  });

  it.each(["ce", "acs"])(
    "rejects incomplete %s evaluation status despite favorable scores",
    (kind) => {
      for (const status of ["blocked", "failed", "partial", undefined]) {
        const forecast = makeForecast();
        forecast.validation[kind].status = status;
        expect(evaluation(forecast, kind).complete).toBe(false);
      }
      for (const unvalidated of [true, undefined, "false"]) {
        const forecast = makeForecast();
        forecast.validation[kind].unvalidated = unvalidated;
        expect(evaluation(forecast, kind).complete).toBe(false);
      }
    },
  );

  const ceFields = [
    ["metric"],
    ["scenarios", "ce_trend", "mean_absolute_percentage_error"],
    ["scenarios", "ce_trend", "beats_baseline"],
    [
      "scenarios",
      "ce_trend",
      "horizon_balanced_mean_absolute_percentage_error",
    ],
    ["scenarios", "ce_trend", "beats_horizon_balanced_baseline"],
    ["baseline", "mean_absolute_percentage_error"],
    ["baseline", "horizon_balanced_mean_absolute_percentage_error"],
    [
      "by_horizon",
      "1",
      "scenarios",
      "ce_trend",
      "mean_absolute_percentage_error",
    ],
    ["by_horizon", "1", "scenarios", "ce_trend", "beats_baseline"],
    ["by_horizon", "1", "baseline", "mean_absolute_percentage_error"],
    ["by_horizon", "1", "fold_count"],
  ];
  it.each(ceFields.map((path) => [path.join("."), path]))(
    "requires CE field %s",
    (_, path) => {
      const forecast = makeForecast();
      const target = path
        .slice(0, -1)
        .reduce((value, key) => value[key], forecast.validation.ce);
      delete target[path.at(-1)];
      expect(evaluation(forecast, "ce").complete).toBe(false);
    },
  );

  it.each([
    "mean_absolute_percentage_error",
    "baseline_mean_absolute_percentage_error",
    "beats_baseline",
    "origin_spm_year",
    "target_spm_year",
    "area_count",
  ])("requires ACS field %s", (key) => {
    const forecast = makeForecast();
    delete forecast.validation.acs[key];
    expect(evaluation(forecast, "acs").complete).toBe(false);
  });

  it.each([NaN, Infinity, -0.1, "0.8", null])(
    "rejects malformed MAPE %s",
    (mape) => {
      const forecast = makeForecast();
      forecast.validation.ce.scenarios.ce_trend.mean_absolute_percentage_error =
        mape;
      forecast.validation.acs.mean_absolute_percentage_error = mape;
      expect(evaluation(forecast, "ce").complete).toBe(false);
      expect(evaluation(forecast, "acs").complete).toBe(false);
    },
  );

  it("requires boolean performance flags", () => {
    const forecast = makeForecast();
    forecast.validation.ce.scenarios.ce_trend.beats_baseline = "true";
    forecast.validation.acs.beats_baseline = 1;
    expect(evaluation(forecast, "ce").complete).toBe(false);
    expect(evaluation(forecast, "acs").complete).toBe(false);
  });

  it.each([0, -1, 1.5, "6", Infinity])(
    "rejects invalid horizon fold count %s",
    (count) => {
      const forecast = makeForecast();
      forecast.validation.ce.by_horizon["1"].fold_count = count;
      expect(evaluation(forecast, "ce").complete).toBe(false);
    },
  );

  it.each(["overall", "balanced", "horizon"])(
    "detects %s CE underperformance and inconsistent ties",
    (comparison) => {
      const forecast = makeForecast();
      const target =
        comparison === "horizon"
          ? forecast.validation.ce.by_horizon["1"].scenarios.ce_trend
          : forecast.validation.ce.scenarios.ce_trend;
      const flag =
        comparison === "balanced"
          ? "beats_horizon_balanced_baseline"
          : "beats_baseline";
      target[flag] = false;
      expect(evaluation(forecast, "ce").underperformed).toBe(true);
      target[flag] = true;
      target[
        comparison === "balanced"
          ? "horizon_balanced_mean_absolute_percentage_error"
          : "mean_absolute_percentage_error"
      ] =
        comparison === "horizon" ? 1.4 : comparison === "balanced" ? 1.3 : 1.2;
      expect(evaluation(forecast, "ce").underperformed).toBe(true);
    },
  );

  it("requires the selected scenario and horizon to outperform the baseline", () => {
    const forecast = makeForecast();
    forecast.validation.ce.by_horizon["5"].scenarios.ce_trend.beats_baseline =
      false;
    expect(evaluation(forecast, "ce").underperformed).toBe(false);
    expect(evaluation(forecast, "ce", { year: 2030 }).underperformed).toBe(
      true,
    );
    expect(
      evaluation(forecast, "ce", { year: 2030, scenarioId: "zero_real" })
        .underperformed,
    ).toBe(false);
  });

  it("never treats a completed research suite as support for an untested forecast horizon", () => {
    const forecast = makeForecast();
    expect(evaluation(forecast, "ce", { year: 2035 })).toMatchObject({
      researchComplete: true,
      complete: false,
      unsupportedHorizon: true,
      horizon: 10,
    });
    expect(evaluation(forecast, "acs", { year: 2026 })).toMatchObject({
      researchComplete: true,
      complete: false,
      unsupportedHorizon: true,
      horizon: 2,
    });
    forecast.validation.ce.by_horizon["10"] =
      forecast.validation.ce.by_horizon["1"];
    expect(evaluation(forecast, "ce", { year: 2035 }).complete).toBe(true);
    expect(evaluation(forecast, "ce", { year: 2032 })).toMatchObject({
      complete: false,
      unsupportedHorizon: true,
    });
    forecast.validation.acs.target_spm_year = 2025;
    expect(evaluation(forecast, "acs", { year: 2026 }).complete).toBe(true);
  });
});

describe("forecast warnings", () => {
  it("keeps published components and supported outperforming geography free of warnings", () => {
    const { rerender } = render(warnings());
    expect(screen.queryByRole("alert")).toBeNull();
    const forecast = makeForecast();
    delete forecast.validation;
    rerender(warnings(forecast, { year: 2024 }));
    expect(screen.queryByRole("alert")).toBeNull();
    rerender(warnings(forecast));
    expect(screen.getByTestId("acs-validation-warning")).toHaveTextContent(
      "has not been retrospectively validated",
    );
    expect(screen.queryByTestId("ce-validation-warning")).toBeNull();
  });

  it("explicitly labels unsupported CE and ACS horizons", () => {
    render(warnings(makeForecast(), { year: 2035 }));
    expect(screen.getByTestId("ce-validation-warning")).toHaveTextContent(
      "10-year spending horizon has no retrospective backtest support",
    );
    expect(screen.getByTestId("ce-validation-warning")).toHaveTextContent(
      "CE tests cover 1–6 years",
    );
    expect(screen.getByTestId("acs-validation-warning")).toHaveTextContent(
      "11-year geographic horizon has no retrospective backtest support",
    );
    expect(screen.getByTestId("acs-validation-warning")).toHaveTextContent(
      "ACS tests cover 1 year",
    );
  });

  it("warns about unpublished-area applicability within otherwise published years", () => {
    render(warnings(makeForecast(), { year: 2022, areaId: RESIDUAL }));
    expect(screen.getByTestId("acs-validation-warning")).toHaveTextContent(
      "no published Census anchor and no area-matched retrospective validation",
    );
    expect(screen.queryByTestId("ce-validation-warning")).toBeNull();
  });

  it("preserves underperformance warnings including ACS ties", () => {
    const forecast = makeForecast();
    forecast.validation.ce.scenarios.ce_trend.beats_baseline = false;
    forecast.validation.acs.mean_absolute_percentage_error = 1.5;
    render(warnings(forecast, { year: 2026 }));
    expect(screen.getByTestId("ce-validation-warning")).toHaveTextContent(
      "did not outperform inflation-only",
    );
    expect(screen.getByTestId("acs-validation-warning")).toHaveTextContent(
      "did not outperform unchanged indices",
    );
  });
});

describe("selected-area research diagnostics", () => {
  const massachusettsBreak = {
    kind: "published_series_break",
    from_year: 2022,
    to_year: 2023,
    from_area_id: "25002",
    to_area_id: "25002",
    interpretation:
      "Massachusetts Nonmetro: the published Census rent index changes from 1.551 in 2022 to 1.043 in 2023; this is a published-source break, not estimated annual rent growth.",
  };
  const sumterBreak = {
    kind: "published_to_modeled_break",
    from_year: 2022,
    to_year: 2023,
    from_area_id: "45001",
    to_area_id: "modeled_residual_metro:45",
    interpretation:
      "Sumter County, South Carolina: the 2022 published South Carolina Metro area disappears from the 2023 Census menu. Its assignment changes to an unanchored modeled residual metro area; the resulting change must not be interpreted as annual rent growth.",
  };

  function withSeriesBreak(disclosure) {
    const forecast = makeForecast();
    const years = forecast.scenarios.ce_trend.years;
    for (const [year, id] of [
      [disclosure.from_year, disclosure.from_area_id],
      [disclosure.to_year, disclosure.to_area_id],
    ]) {
      years[year].geography_by_area[id] = {
        status: "published_anchor",
        series_breaks: [disclosure],
      };
    }
    return forecast;
  }

  it("keeps the Massachusetts published-source break visible across the comparison and deduplicates annual metadata", () => {
    const forecast = withSeriesBreak(massachusettsBreak);
    const { rerender } = render(
      warnings(forecast, { year: 2022, areaId: "25002" }),
    );
    const warning = screen.getByTestId("historical-series-break-warning");
    expect(warning).toHaveTextContent("2022→2023");
    expect(warning).toHaveTextContent(massachusettsBreak.interpretation);
    expect(within(warning).getAllByText(/Massachusetts Nonmetro/)).toHaveLength(
      1,
    );
    expect(screen.queryByTestId("median-diagnostics-warning")).toBeNull();
    rerender(warnings(forecast, { year: 2035, areaId: "25002" }));
    expect(
      screen.getByTestId("historical-series-break-warning"),
    ).toHaveTextContent(massachusettsBreak.interpretation);
    rerender(warnings(forecast, { year: 2035, areaId: AREA }));
    expect(screen.queryByTestId("historical-series-break-warning")).toBeNull();
  });

  it.each([
    [2022, "45001"],
    [2023, "modeled_residual_metro:45"],
    [2035, "modeled_residual_metro:45"],
  ])(
    "shows the Sumter published-to-modeled break for year %s and area %s",
    (year, areaId) => {
      render(warnings(withSeriesBreak(sumterBreak), { year, areaId }));
      expect(
        screen.getByTestId("historical-series-break-warning"),
      ).toHaveTextContent(sumterBreak.interpretation);
    },
  );

  it("uses per-area status and diagnostics instead of suppressing a mixed year's modeled areas", () => {
    const entry = makeEntry(2024);
    const diagnostic = {
      unique_records: 24,
      kish_effective_count: 18.3,
      thin_support: true,
      material_topcoding: true,
      topcoded_weight_share: 0.12,
    };
    entry.geography_by_area[AREA].diagnostics = diagnostic;
    entry.geography_by_area[RESIDUAL].diagnostics = diagnostic;
    const { rerender } = render(
      warnings(makeForecast(), { year: 2024, entry }),
    );
    expect(screen.queryByTestId("median-diagnostics-warning")).toBeNull();
    rerender(warnings(makeForecast(), { year: 2024, entry, areaId: RESIDUAL }));
    const warning = screen.getByTestId("median-diagnostics-warning");
    expect(warning).toHaveTextContent("Thin rental support");
    expect(warning).toHaveTextContent("Topcoding may affect this median");
    expect(warning).toHaveTextContent("24 unique records");
    expect(warning).toHaveTextContent("Kish effective count 18.3");
    expect(warning).toHaveTextContent("12.0% topcoded weight");
    expect(warning).toHaveTextContent(
      "Repeated future cohorts do not add independent observations",
    );
    expect(warning).toHaveTextContent(
      "research diagnostics, not Census publication rules",
    );
  });

  it.each([
    [
      { rent_index_topcode_warning: true, topcoded_weight_share: 0 },
      "local or national median used by this projected rent index",
    ],
    [
      { material_topcoding: true, topcoded_weight_share: 0.55 },
      "Topcoding may affect this median",
    ],
    [{ topcoded_weight_share: 0.03 }, "Some rental weight is topcoded"],
  ])(
    "reports scientifically warranted topcoding without requiring thin support",
    (diagnostic, message) => {
      const entry = makeEntry(2026);
      entry.median_diagnostics = {
        [AREA]: { thin_support: false, ...diagnostic },
      };
      render(warnings(makeForecast(), { year: 2026, entry }));
      const warning = screen.getByTestId("median-diagnostics-warning");
      expect(warning).toHaveTextContent(message);
      expect(warning).not.toHaveTextContent("Thin rental support");
    },
  );

  it("does not fabricate topcoding or thin support for an unaffected selected area", () => {
    const entry = makeEntry(2026);
    entry.median_diagnostics = {
      [AREA]: { thin_support: false, topcoded_weight_share: 0 },
      [RESIDUAL]: { thin_support: true },
    };
    render(warnings(makeForecast(), { year: 2026, entry }));
    expect(screen.queryByTestId("median-diagnostics-warning")).toBeNull();
  });
});

describe("forecast methodology diagnostics", () => {
  it("reports numeric comparisons, published-area coverage, and assumptions in a compact disclosure", () => {
    render(methodology());
    const details = screen.getByTestId("forecast-methodology");
    expect(details.tagName).toBe("DETAILS");
    expect(details).not.toHaveAttribute("open");
    expect(details).toHaveTextContent(
      "Retrospective, current-vintage validation, conditional on realized prices",
    );
    expect(details).toHaveTextContent(
      "Overall CE MAPE: 0.80% vs 1.20% inflation-only",
    );
    expect(details).toHaveTextContent(
      "Horizon-balanced CE MAPE (1–5 years): 0.90% vs 1.30%",
    );
    expect(details).toHaveTextContent(
      "5-year CE MAPE: 0.70% vs 1.40% (2 folds)",
    );
    expect(details).toHaveTextContent(
      "ACS MAPE: 1.10% vs 1.50% unchanged indices",
    );
    expect(details).toHaveTextContent(
      "ACS backtest covers 2023–2024 across 341 published areas",
    );
    expect(details).toHaveTextContent(
      "does not validate the selected 6-year geographic horizon",
    );
    expect(details).toHaveTextContent("Shorter horizons have more folds");
    expect(details).toHaveTextContent("few long-horizon folds");
    expect(details).toHaveTextContent("0.5 shrinkage");
    expect(details).toHaveTextContent(
      "predeclared independently of holdout results",
    );
    expect(details).toHaveTextContent(
      "zero real growth is a separate scored scenario",
    );
    expect(details).toHaveTextContent(
      "CBO annual CPI ratios are applied uniformly to spending components and rent growth as a modeling assumption, not a CBO rent forecast",
    );
    expect(screen.getByTestId("rent-index-stabilization")).toHaveTextContent(
      "relative rent indices stabilize from 2029",
    );
    expect(screen.getByTestId("rent-index-stabilization")).toHaveTextContent(
      "only the 2024 donor distribution and its projected copies",
    );
    expect(screen.getByTestId("rent-index-stabilization")).toHaveTextContent(
      "whole-threshold geography factor can still change as the housing share changes",
    );
  });

  it("does not present absent long-horizon scores as zero or blanket validation", () => {
    render(methodology(makeForecast(), { year: 2035 }));
    const details = screen.getByTestId("forecast-methodology");
    expect(details).toHaveTextContent(
      "10-year spending horizon has no retrospective backtest support",
    );
    expect(details).not.toHaveTextContent("10-year CE MAPE");
    expect(details).not.toHaveTextContent("0.00%");
    expect(details).not.toHaveTextContent("CE validation incomplete");
  });

  it("updates scenario scores and omits a forecast horizon for published national thresholds", () => {
    const { rerender } = render(
      methodology(makeForecast(), { scenarioId: "zero_real", year: 2026 }),
    );
    expect(screen.getByTestId("forecast-methodology")).toHaveTextContent(
      "Overall CE MAPE: 1.10% vs 1.20%",
    );
    rerender(methodology(makeForecast(), { year: 2025 }));
    expect(screen.getByTestId("forecast-methodology")).not.toHaveTextContent(
      "0-year CE MAPE",
    );
  });

  it("does not invent scores when required evaluation data is absent", () => {
    const forecast = makeForecast();
    delete forecast.validation;
    render(methodology(forecast, { year: 2026 }));
    const details = screen.getByTestId("forecast-methodology");
    expect(details).toHaveTextContent("CE validation incomplete");
    expect(details).toHaveTextContent("ACS validation incomplete");
    expect(details).not.toHaveTextContent("0.00%");
  });

  it("labels fit sensitivities and OLS uncertainty without claiming forecast intervals", () => {
    const forecast = makeForecast();
    forecast.realGrowthDiagnostics = {
      fits: [
        {
          label: "5-year trend",
          realGrowthRate: -0.012,
          olsSlopeStandardError: 0.004,
          n: 5,
        },
        { label: "10-year trend", realGrowthRate: 0.008, n: 10 },
        { label: "Pandemic excluded", realGrowthRate: -0.021, n: 3 },
      ],
    };
    render(methodology(forecast));
    const fits = within(screen.getByTestId("real-growth-fits"));
    expect(fits.getByText(/5-year trend fit: −1.20%/)).toBeTruthy();
    expect(fits.getByText(/10-year trend fit: \+0.80%/)).toBeTruthy();
    expect(fits.getByText(/Pandemic excluded fit: −2.10%/)).toBeTruthy();
    expect(screen.getByTestId("real-growth-fits")).toHaveTextContent(
      "OLS slope SE 0.0040",
    );
    expect(screen.getByTestId("real-growth-fits")).toHaveTextContent(
      "3 annual blocks",
    );
    expect(screen.getByTestId("forecast-methodology")).toHaveTextContent(
      "OLS fit diagnostics are not survey-design uncertainty or forecast intervals",
    );
  });

  it("accepts scientific snake-case fits while omitting unavailable sensitivities", () => {
    const forecast = makeForecast();
    forecast.realGrowthDiagnostics = {
      five_year: {
        real_growth_rate: -0.012,
        ols_slope_standard_error: 0.004,
        n: 5,
      },
      ten_year: { status: "unavailable" },
      pandemic_excluded: { annual_log_slope: Math.log(1.008), n: 3 },
    };
    render(methodology(forecast));
    const fits = screen.getByTestId("real-growth-fits");
    expect(fits).toHaveTextContent("5-year trend fit: −1.20%");
    expect(fits).toHaveTextContent("Pandemic excluded fit: +0.80%");
    expect(fits).not.toHaveTextContent("10-year trend fit");
  });
});
