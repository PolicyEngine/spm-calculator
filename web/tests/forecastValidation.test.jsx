import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ForecastMethodology,
  ForecastWarnings,
} from "../src/components/ForecastDiagnostics";

function makeForecast() {
  const scores = (mape = 0.8) => ({
    mean_absolute_percentage_error: mape,
    beats_baseline: true,
    horizon_balanced_mean_absolute_percentage_error: 0.9,
    beats_horizon_balanced_baseline: true,
  });
  return {
    method: "rolling_ce_acs_v1",
    baseYear: 2025,
    defaultScenario: "ce_trend",
    scenarios: {
      ce_trend: { label: "CE real-spending trend", realGrowthRate: 0.005 },
      zero_real: { label: "No real spending growth", realGrowthRate: 0 },
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
          Array.from({ length: 6 }, (_, index) => [
            String(index + 1),
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
              fold_count: 6 - index,
            },
          ]),
        ),
      },
      acs: {
        status: "complete",
        unvalidated: false,
        mean_absolute_percentage_error: 1.1,
        baseline_mean_absolute_percentage_error: 1.5,
        beats_baseline: true,
      },
    },
  };
}

function warnings(forecast = makeForecast(), props = {}) {
  return (
    <ForecastWarnings
      forecast={forecast}
      scenarioId="ce_trend"
      year={2026}
      areaId="35620"
      {...props}
    />
  );
}

it("warns about an affected national or bridge median even without local topcoding", () => {
  const entry = {
    geography_status: "modeled",
    median_diagnostics: {
      35620: {
        thin_support: false,
        topcoded_weight_share: 0,
        median_topcode_warning: false,
        rent_index_topcode_warning: true,
      },
    },
  };
  const { rerender } = render(warnings(makeForecast(), { entry }));
  expect(screen.getByTestId("median-diagnostics-warning")).toHaveTextContent(
    "local or national median used by this projected rent index",
  );
  rerender(
    warnings(makeForecast(), {
      year: 2024,
      entry: { ...entry, geography_status: "published_anchor" },
    }),
  );
  expect(screen.queryByTestId("median-diagnostics-warning")).toBeNull();
});

describe("rolling forecast validation warnings", () => {
  it("keeps completed, outperforming research components free of evaluation warnings", () => {
    render(warnings());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("does not apply new validation requirements to legacy fixtures", () => {
    render(warnings({ baseYear: 2025 }));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows missing-validation warnings only when each projected component is used", () => {
    const forecast = makeForecast();
    delete forecast.validation;
    const { rerender } = render(warnings(forecast, { year: 2024 }));
    expect(screen.queryByRole("alert")).toBeNull();
    rerender(warnings(forecast, { year: 2025 }));
    expect(screen.queryByTestId("ce-validation-warning")).toBeNull();
    expect(screen.getByTestId("acs-validation-warning")).toHaveTextContent(
      "has not been retrospectively validated",
    );
    rerender(warnings(forecast, { year: 2026 }));
    expect(screen.getByTestId("ce-validation-warning")).toHaveTextContent(
      "has not been retrospectively validated",
    );
    expect(screen.getByTestId("acs-validation-warning")).toHaveTextContent(
      "has not been retrospectively validated",
    );
  });

  it.each(["blocked", "failed", "partial", undefined])(
    "flags CE and ACS status %s despite favorable scores",
    (status) => {
      const forecast = makeForecast();
      forecast.validation.ce.status = status;
      forecast.validation.acs.status = status;
      render(warnings(forecast));
      expect(screen.getByTestId("ce-validation-warning")).toHaveTextContent(
        "has not been retrospectively validated",
      );
      expect(screen.getByTestId("acs-validation-warning")).toHaveTextContent(
        "has not been retrospectively validated",
      );
    },
  );

  it.each([true, undefined, "false"])(
    "requires explicit unvalidated=false (%s)",
    (unvalidated) => {
      const forecast = makeForecast();
      forecast.validation.ce.unvalidated = unvalidated;
      forecast.validation.acs.unvalidated = unvalidated;
      render(warnings(forecast));
      expect(
        screen.getAllByText(/has not been retrospectively validated/),
      ).toHaveLength(2);
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
    "flags absent required CE field %s",
    (_, path) => {
      const forecast = makeForecast();
      const target = path
        .slice(0, -1)
        .reduce((value, field) => value[field], forecast.validation.ce);
      delete target[path.at(-1)];
      render(warnings(forecast));
      expect(screen.getByTestId("ce-validation-warning")).toHaveTextContent(
        "has not been retrospectively validated",
      );
      expect(screen.queryByTestId("acs-validation-warning")).toBeNull();
    },
  );

  it.each([
    "mean_absolute_percentage_error",
    "baseline_mean_absolute_percentage_error",
    "beats_baseline",
  ])("flags absent required ACS field %s", (field) => {
    const forecast = makeForecast();
    delete forecast.validation.acs[field];
    render(warnings(forecast));
    expect(screen.getByTestId("acs-validation-warning")).toHaveTextContent(
      "has not been retrospectively validated",
    );
  });

  it.each([NaN, Infinity, -0.1, "0.8", null])(
    "rejects malformed MAPE %s",
    (mape) => {
      const forecast = makeForecast();
      forecast.validation.ce.scenarios.ce_trend.mean_absolute_percentage_error =
        mape;
      forecast.validation.acs.mean_absolute_percentage_error = mape;
      render(warnings(forecast));
      expect(
        screen.getAllByText(/has not been retrospectively validated/),
      ).toHaveLength(2);
    },
  );

  it("rejects truthy nonboolean performance flags", () => {
    const forecast = makeForecast();
    forecast.validation.ce.scenarios.ce_trend.beats_baseline = "true";
    forecast.validation.acs.beats_baseline = 1;
    render(warnings(forecast));
    expect(
      screen.getAllByText(/has not been retrospectively validated/),
    ).toHaveLength(2);
  });

  it.each([0, -1, 1.5, "6", Infinity])(
    "rejects invalid selected-horizon fold count %s",
    (foldCount) => {
      const forecast = makeForecast();
      forecast.validation.ce.by_horizon["1"].fold_count = foldCount;
      render(warnings(forecast));
      expect(screen.getByTestId("ce-validation-warning")).toHaveTextContent(
        "has not been retrospectively validated",
      );
    },
  );

  it.each(["overall", "balanced", "horizon"])(
    "warns on %s CE underperformance independently",
    (comparison) => {
      const forecast = makeForecast();
      if (comparison === "overall")
        forecast.validation.ce.scenarios.ce_trend.beats_baseline = false;
      if (comparison === "balanced")
        forecast.validation.ce.scenarios.ce_trend.beats_horizon_balanced_baseline = false;
      if (comparison === "horizon")
        forecast.validation.ce.by_horizon[
          "1"
        ].scenarios.ce_trend.beats_baseline = false;
      render(warnings(forecast));
      expect(screen.getByTestId("ce-validation-warning")).toHaveTextContent(
        "selected spending scenario did not outperform inflation-only in retrospective tests",
      );
      expect(
        screen.queryByText(/has not been retrospectively validated/),
      ).toBeNull();
    },
  );

  it.each(["overall", "balanced", "horizon"])(
    "warns on numerical %s CE ties even if an inconsistent flag claims improvement",
    (comparison) => {
      const forecast = makeForecast();
      if (comparison === "overall")
        forecast.validation.ce.scenarios.ce_trend.mean_absolute_percentage_error = 1.2;
      if (comparison === "balanced")
        forecast.validation.ce.scenarios.ce_trend.horizon_balanced_mean_absolute_percentage_error = 1.3;
      if (comparison === "horizon")
        forecast.validation.ce.by_horizon[
          "1"
        ].scenarios.ce_trend.mean_absolute_percentage_error = 1.4;
      render(warnings(forecast));
      expect(screen.getByTestId("ce-validation-warning")).toHaveTextContent(
        "did not outperform inflation-only",
      );
    },
  );

  it("updates warnings with selected scenario and displayed horizon", () => {
    const forecast = makeForecast();
    forecast.validation.ce.by_horizon["5"].scenarios.ce_trend.beats_baseline =
      false;
    const { rerender } = render(warnings(forecast));
    expect(screen.queryByRole("alert")).toBeNull();
    rerender(warnings(forecast, { year: 2030 }));
    expect(screen.getByTestId("ce-validation-warning")).toHaveTextContent(
      "did not outperform inflation-only",
    );
    rerender(warnings(forecast, { year: 2030, scenarioId: "zero_real" }));
    expect(screen.queryByRole("alert")).toBeNull();
    rerender(warnings(forecast, { year: 2025 }));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("warns about geographic underperformance starting in 2025, including numeric ties", () => {
    const forecast = makeForecast();
    forecast.validation.acs.mean_absolute_percentage_error = 1.5;
    const { rerender } = render(warnings(forecast, { year: 2024 }));
    expect(screen.queryByRole("alert")).toBeNull();
    rerender(warnings(forecast, { year: 2025 }));
    expect(screen.getByTestId("acs-validation-warning")).toHaveTextContent(
      "Modeled geographic change did not outperform unchanged indices in retrospective tests",
    );
    expect(screen.queryByTestId("ce-validation-warning")).toBeNull();
  });

  it("warns on the ACS boolean even when metrics favor the modeled result", () => {
    const forecast = makeForecast();
    forecast.validation.acs.beats_baseline = false;
    render(warnings(forecast));
    expect(screen.getByTestId("acs-validation-warning")).toHaveTextContent(
      "did not outperform unchanged indices",
    );
  });
});

describe("selected-area research diagnostics", () => {
  it("shows thin support and material topcoding for the selected area only", () => {
    const entry = {
      median_diagnostics: {
        35620: {
          unique_records: 24,
          kish_effective_count: 18.3,
          thin_support: true,
          topcoded_weight_share: 0.12,
          material_topcoding: true,
        },
        41940: {
          unique_records: 80,
          kish_effective_count: 61,
          thin_support: false,
          topcoded_weight_share: 0,
        },
      },
    };
    const { rerender } = render(warnings(makeForecast(), { entry }));
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
    rerender(warnings(makeForecast(), { entry, areaId: "41940" }));
    expect(screen.queryByTestId("median-diagnostics-warning")).toBeNull();
  });

  it("warns for material topcoding independently of thin support", () => {
    render(
      warnings(makeForecast(), {
        entry: {
          median_diagnostics: {
            35620: {
              unique_records: 100,
              kish_effective_count: 90,
              thin_support: false,
              material_topcoding: true,
              topcoded_weight_share: 0.55,
            },
          },
        },
      }),
    );
    expect(screen.getByTestId("median-diagnostics-warning")).toHaveTextContent(
      "Topcoding may affect this median",
    );
  });

  it("reports nonzero topcoded weight when no materiality flag is provided", () => {
    render(
      warnings(makeForecast(), {
        entry: {
          median_diagnostics: {
            35620: {
              unique_records: 100,
              kish_effective_count: 90,
              thin_support: false,
              topcoded_weight_share: 0.03,
            },
          },
        },
      }),
    );
    const warning = screen.getByTestId("median-diagnostics-warning");
    expect(warning).toHaveTextContent("Some rental weight is topcoded");
    expect(warning).toHaveTextContent("3.0% topcoded weight");
    expect(warning).not.toHaveTextContent("Thin rental support");
  });
});

describe("forecast methodology diagnostics", () => {
  it("reports numeric comparisons and their limits in a compact disclosure", () => {
    render(
      <ForecastMethodology
        forecast={makeForecast()}
        scenarioId="ce_trend"
        year={2030}
      />,
    );
    const details = screen.getByTestId("forecast-methodology");
    expect(details.tagName).toBe("DETAILS");
    expect(details).not.toHaveAttribute("open");
    expect(details).toHaveTextContent(
      "Retrospective, current-vintage validation",
    );
    expect(details).toHaveTextContent("conditional on realized prices");
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
    expect(details).toHaveTextContent("Shorter horizons have more folds");
    expect(details).toHaveTextContent("few long-horizon folds");
    expect(details).toHaveTextContent("0.5 shrinkage");
    expect(details).toHaveTextContent(
      "predeclared independently of holdout results",
    );
    expect(details).not.toHaveTextContent(/best/i);
  });

  it("updates selected-scenario scores without presenting unavailable horizons as zeros", () => {
    const { rerender } = render(
      <ForecastMethodology
        forecast={makeForecast()}
        scenarioId="zero_real"
        year={2026}
      />,
    );
    expect(screen.getByTestId("forecast-methodology")).toHaveTextContent(
      "Overall CE MAPE: 1.10% vs 1.20%",
    );
    rerender(
      <ForecastMethodology
        forecast={makeForecast()}
        scenarioId="ce_trend"
        year={2025}
      />,
    );
    expect(screen.getByTestId("forecast-methodology")).not.toHaveTextContent(
      "0-year CE MAPE",
    );
  });

  it("labels fitted sensitivities and OLS uncertainty without calling them forecast intervals", () => {
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
    render(
      <ForecastMethodology
        forecast={forecast}
        scenarioId="ce_trend"
        year={2026}
      />,
    );
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

  it("does not invent validation scores or successful status when required data is absent", () => {
    const forecast = makeForecast();
    delete forecast.validation;
    render(
      <ForecastMethodology
        forecast={forecast}
        scenarioId="ce_trend"
        year={2026}
      />,
    );
    expect(screen.getByTestId("forecast-methodology")).toHaveTextContent(
      "CE validation incomplete",
    );
    expect(screen.getByTestId("forecast-methodology")).toHaveTextContent(
      "ACS validation incomplete",
    );
    expect(screen.getByTestId("forecast-methodology")).not.toHaveTextContent(
      "0.00%",
    );
  });

  it("accepts named snake-case diagnostic fits while omitting unavailable fits", () => {
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
    render(
      <ForecastMethodology
        forecast={forecast}
        scenarioId="ce_trend"
        year={2026}
      />,
    );
    const fits = screen.getByTestId("real-growth-fits");
    expect(fits).toHaveTextContent("5-year trend fit: −1.20%");
    expect(fits).toHaveTextContent("Pandemic excluded fit: +0.80%");
    expect(fits).not.toHaveTextContent("10-year trend fit");
  });
});
