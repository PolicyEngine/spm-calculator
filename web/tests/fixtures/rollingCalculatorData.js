import { makeCalculatorData } from "./calculatorData";

export const FORECAST_CONTENT_SHA256 = "c".repeat(64);

/**
 * Small rolling-contract fixture. Legacy metadata deliberately has different
 * rent indices and shares, so using it for a modeled year changes the result.
 * Published national anchors retain the legacy fixture's exact values.
 */
export function makeRollingCalculatorData(overrides = {}) {
  const legacy = makeCalculatorData();
  const makeYears = (scenario) =>
    Object.fromEntries(
      Array.from({ length: 7 }, (_, offset) => {
        const year = 2024 + offset;
        const future = year >= 2026;
        const futureOffset = year - 2026;
        const base = scenario === "ce_trend" ? 42000 : 44000;
        const thresholds = future
          ? {
              renter: base + futureOffset * 1000,
              owner_with_mortgage: base - 1000 + futureOffset * 1000,
              owner_without_mortgage: base - 7000 + futureOffset * 1000,
            }
          : { ...legacy.baseThresholds[year] };
        const housing_shares =
          year === 2024
            ? { ...legacy.methodology.housingShares }
            : year === 2025
              ? {
                  renter: 0.4,
                  owner_with_mortgage: 0.3,
                  owner_without_mortgage: 0.2,
                }
              : {
                  renter: scenario === "ce_trend" ? 0.5 : 0.25,
                  owner_with_mortgage: 0.3,
                  owner_without_mortgage: 0.2,
                };
        const rent_indices =
          year === 2024
            ? Object.fromEntries(
                Object.entries(legacy.metroAreas).map(([id, area]) => [
                  id,
                  area.rentIndex,
                ]),
              )
            : year === 2025
              ? { 35620: 1.5, 41940: 2, 1002: 0.5 }
              : {
                  35620: 1.8 + futureOffset * 0.1,
                  41940: 2.2 + futureOffset * 0.1,
                  1002: 0.6 + futureOffset * 0.05,
                };
        const projectedQuarters = Math.min(20, Math.max(0, year - 2025) * 4);
        const projectedYears = Math.min(5, Math.max(0, year - 2025));

        return [
          String(year),
          {
            thresholds,
            housing_shares,
            rent_indices,
            national_status: future ? "forecast" : "published",
            geography_status: year === 2024 ? "published_anchor" : "modeled",
            ce_window: {
              start: `${year - 5}Q2`,
              end: `${year}Q1`,
              observed_quarters: 20 - projectedQuarters,
              projected_quarters: projectedQuarters,
            },
            acs_window: {
              start: year - 5,
              end: year - 1,
              observed_years: 5 - projectedYears,
              projected_years: projectedYears,
            },
          },
        ];
      }),
    );
  const scenarios = {
    ce_trend: {
      label: "CE real-spending trend",
      realGrowthRate: -0.0125,
      shrinkage: 0.5,
      years: makeYears("ce_trend"),
    },
    zero_real: {
      label: "No real spending growth",
      realGrowthRate: 0,
      years: makeYears("zero_real"),
    },
  };
  const score = (mape) => ({
    mean_absolute_percentage_error: mape,
    beats_baseline: true,
    beats_horizon_balanced_baseline: true,
    horizon_balanced_mean_absolute_percentage_error: mape,
  });

  return {
    ...legacy,
    releaseMetadata: {
      id: "synthetic-published-release",
      informationDate: "2026-09-08",
      sha256: "b".repeat(64),
    },
    housingSharesByYear: {
      2025: { ...legacy.methodology.housingShares },
    },
    housingShareProvenanceByYear: {
      2025: { reference_year: 2024, status: "carried" },
    },
    forecast: {
      latestPublishedYear: 2025,
      baseYear: 2025,
      baseReleaseSha256: "b".repeat(64),
      assumptionSha256: "a".repeat(64),
      contentSha256: FORECAST_CONTENT_SHA256,
      informationDate: "2026-09-08",
      method: "rolling_ce_acs_v1",
      defaultScenario: "ce_trend",
      cpiProjections: {
        2026: 0.023,
        2027: 0.022,
        2028: 0.02,
        2029: 0.02,
        2030: 0.02,
      },
      thresholdsByYear: Object.fromEntries(
        Object.entries(scenarios.ce_trend.years)
          .filter(([year]) => Number(year) >= 2026)
          .map(([year, entry]) => [year, { ...entry.thresholds }]),
      ),
      scenarios,
      validation: {
        ce: {
          status: "complete",
          unvalidated: false,
          metric: "mean_absolute_percentage_error",
          fold_count: 21,
          fold_tenure_observations: 63,
          scenarios: { ce_trend: score(0.8), zero_real: score(0.9) },
          baseline: {
            mean_absolute_percentage_error: 1.2,
            horizon_balanced_mean_absolute_percentage_error: 1.2,
          },
          by_horizon: Object.fromEntries(
            Array.from({ length: 6 }, (_, offset) => [
              String(offset + 1),
              {
                scenarios: {
                  ce_trend: {
                    mean_absolute_percentage_error: 0.8,
                    beats_baseline: true,
                  },
                  zero_real: {
                    mean_absolute_percentage_error: 0.9,
                    beats_baseline: true,
                  },
                },
                baseline: { mean_absolute_percentage_error: 1.2 },
                fold_count: 6 - offset,
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
          area_count: 341,
        },
        note: "Retrospective, current-vintage tests conditional on realized prices.",
      },
    },
    ...overrides,
  };
}
