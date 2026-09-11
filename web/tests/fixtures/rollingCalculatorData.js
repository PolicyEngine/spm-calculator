export const FORECAST_CONTENT_SHA256 = "c".repeat(64);
export const AVAILABLE_YEARS = Array.from(
  { length: 14 },
  (_, offset) => 2022 + offset,
);
export const MODELED_AREA_ID = "modeled_residual_metro:01";
export const HISTORICAL_AREA_ID = "2022-only";

/** Small schema-2 fixture with deliberately distinct annual/scenario inputs. */
export function makeRollingCalculatorData(overrides = {}) {
  const publishedThresholds = {
    2022: {
      renter: 34518,
      owner_with_mortgage: 34097,
      owner_without_mortgage: 28520,
    },
    2023: {
      renter: 36606,
      owner_with_mortgage: 36192,
      owner_without_mortgage: 30347,
    },
    2024: {
      renter: 39430,
      owner_with_mortgage: 39068,
      owner_without_mortgage: 32586,
    },
    2025: {
      renter: 41700.555713,
      owner_with_mortgage: 41322.707394,
      owner_without_mortgage: 34325.99772,
    },
  };
  const areaDefinitions = {
    35620: {
      name: "New York-Newark-Jersey City, NY-NJ-PA MSA",
      area_type: "msa",
    },
    41940: { name: "San Jose-Sunnyvale-Santa Clara, CA MSA", area_type: "msa" },
    1002: { name: "Alabama Nonmetro", area_type: "state_nonmetro" },
    [MODELED_AREA_ID]: {
      name: "Alabama residual Metro (modeled)",
      area_type: "modeled_residual_metro",
    },
    [HISTORICAL_AREA_ID]: {
      name: "Historical Metro Group",
      area_type: "state_metro_residual",
    },
  };
  const areasByYear = Object.fromEntries(
    AVAILABLE_YEARS.map((year) => [
      year,
      Object.fromEntries(
        Object.entries(areaDefinitions)
          .filter(([id]) => id !== HISTORICAL_AREA_ID || year === 2022)
          .map(([id, area]) => [
            id,
            {
              ...area,
              status:
                id === MODELED_AREA_ID
                  ? "modeled_unanchored"
                  : year <= 2024
                    ? "published_anchor"
                    : "modeled",
              anchor_status:
                id === MODELED_AREA_ID
                  ? "modeled_unanchored"
                  : "published_anchor",
              official_published_area: id !== MODELED_AREA_ID,
              source_ids:
                id === MODELED_AREA_ID
                  ? ["acs_forecast_inputs"]
                  : [`census-spm-${Math.min(year, 2024)}`],
              puma_vintage: year === 2022 ? 2010 : 2020,
              allocation_county_vintage: year === 2022 ? 2010 : 2020,
            },
          ]),
      ),
    ]),
  );
  const makeYears = (scenario) =>
    Object.fromEntries(
      AVAILABLE_YEARS.map((year) => {
        const future = year >= 2026;
        const futureOffset = year - 2026;
        const base = scenario === "ce_trend" ? 42000 : 44000;
        const thresholds = future
          ? {
              renter: base + futureOffset * 1000,
              owner_with_mortgage: base - 1000 + futureOffset * 1000,
              owner_without_mortgage: base - 7000 + futureOffset * 1000,
            }
          : { ...publishedThresholds[year] };
        const housing_shares =
          year <= 2024
            ? {
                renter: 0.443,
                owner_with_mortgage: 0.434,
                owner_without_mortgage: 0.323,
              }
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
          year <= 2024
            ? { 35620: 1.361, 41940: 2.167, 1002: 0.553 }
            : year === 2025
              ? { 35620: 1.5, 41940: 2, 1002: 0.5 }
              : {
                  35620: 1.8 + futureOffset * 0.1,
                  41940: 2.2 + futureOffset * 0.1,
                  1002: 0.6 + futureOffset * 0.05,
                };
        rent_indices[MODELED_AREA_ID] = 0.8;
        if (year === 2022) rent_indices[HISTORICAL_AREA_ID] = 1.1;
        const projectedQuarters = Math.min(20, Math.max(0, year - 2025) * 4);
        const projectedYears = Math.min(5, Math.max(0, year - 2025));
        return [
          year,
          {
            thresholds,
            housing_shares,
            rent_indices,
            national_status: future ? "forecast" : "published",
            national_source_ids: future
              ? ["ce_forecast_inputs"]
              : ["bls-spm-thresholds"],
            housing_share_status: future ? "modeled" : "published_anchor",
            housing_share_source_ids: future
              ? ["ce_forecast_inputs"]
              : ["bls-spm-shares"],
            // The aggregate never decides the selected area's published status.
            geography_status: "mixed",
            geography_by_area: structuredClone(areasByYear[year]),
            median_diagnostics: {},
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
  const score = (mape) => ({
    mean_absolute_percentage_error: mape,
    beats_baseline: true,
    beats_horizon_balanced_baseline: true,
    horizon_balanced_mean_absolute_percentage_error: mape,
  });
  const prices = Object.fromEntries(
    AVAILABLE_YEARS.filter((year) => year >= 2026).map((year) => [
      year,
      year === 2026 ? 0.023 : year === 2027 ? 0.022 : 0.02,
    ]),
  );
  return {
    schemaVersion: 2,
    packageVersion: "0.3.0",
    packageDistribution: {
      status: "local_preview",
      version: "0.3.0",
      publishedVersion: null,
      pypiUrl: null,
    },
    availableYears: [...AVAILABLE_YEARS],
    areasByYear,
    methodology: {
      equivalenceScale: {
        singleAdultFirstChild: 0.8,
        additionalChild: 0.5,
        economiesOfScale: 0.7,
        twoAdultNoChild: 1.41,
        referenceFamilyRaw: 3 ** 0.7,
      },
    },
    paperUrl: "https://spm-threshold-paper.vercel.app",
    forecast: {
      schemaVersion: 2,
      latestPublishedYear: 2025,
      baseYear: 2025,
      geographyAnchorYear: 2024,
      baseReleaseSha256: "b".repeat(64),
      assumptionSha256: "a".repeat(64),
      contentSha256: FORECAST_CONTENT_SHA256,
      informationDate: "2026-09-09",
      method: "rolling_ce_acs_v1",
      defaultScenario: "ce_trend",
      cpiProjections: prices,
      assumptions: {
        price_projections: prices,
        acs: { anchor_spm_year: 2024 },
        ce: { national_anchor_year: 2025 },
      },
      sources: [
        {
          id: "bls-spm-thresholds",
          url: "https://www.bls.gov/pir/spm/spm_thresholds.xlsx",
        },
        {
          id: "bls-spm-shares",
          url: "https://www.bls.gov/pir/spm/spm_shares.xlsx",
        },
        {
          id: "census-spm-2024",
          url: "https://www2.census.gov/programs-surveys/demo/tables/p60/287/SPM-pov-threshold-2024.xlsx",
        },
      ],
      forwardTest: {
        status: "awaiting_published_target",
        target_spm_year: 2025,
        information_date: "2026-09-09",
      },
      scenarios: {
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
      },
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
              offset + 1,
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
          origin_spm_year: 2023,
          target_spm_year: 2024,
        },
        note: "Retrospective, current-vintage tests conditional on realized prices.",
      },
    },
    ...overrides,
  };
}
