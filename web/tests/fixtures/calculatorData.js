/**
 * Minimal CalculatorWorkbench data fixture for unit tests.
 *
 * Shape mirrors what `loadCalculatorData()` returns at runtime
 * (merging `spm_config.json` with the metro-data header fields).
 * Only the fields the component actually reads are populated — enough
 * to render without crashing under jsdom.
 */
export function makeCalculatorData(overrides = {}) {
  return {
    packageVersion: "0.3.0",
    baseThresholds: {
      "2023": {
        renter: 36606,
        owner_with_mortgage: 36192,
        owner_without_mortgage: 30347,
      },
      "2024": {
        renter: 39430,
        owner_with_mortgage: 39068,
        owner_without_mortgage: 32586,
      },
    },
    methodology: {
      referenceRawScale: 3 ** 0.7,
      housingShares: {
        renter: 0.443,
        owner_with_mortgage: 0.434,
        owner_without_mortgage: 0.323,
      },
      equivalenceScale: {
        singleAdultFirstChild: 0.8,
        additionalChild: 0.5,
        economiesOfScale: 0.7,
        twoAdultNoChild: 1.41,
        referenceFamilyRaw: 3 ** 0.7,
      },
    },
    forecast: {
      latestPublishedYear: 2024,
      cpiProjections: { "2025": 0.025, "2026": 0.023 },
    },
    metroAreas: {
      "35620": {
        name: "New York-Newark-Jersey City, NY-NJ-PA MSA",
        rentIndex: 1.361,
        adjustments: {
          renter: 1.159928988080142,
          owner_with_mortgage: 1.1566755400839561,
          owner_without_mortgage: 1.1166144970232614,
        },
        referenceThresholds: {
          renter: 45736,
          owner_with_mortgage: 45189,
          owner_without_mortgage: 36386,
        },
      },
      "41940": {
        name: "San Jose-Sunnyvale-Santa Clara, CA MSA",
        rentIndex: 2.167,
        adjustments: {
          renter: 1.5169921379660156,
          owner_with_mortgage: 1.506475888194942,
          owner_without_mortgage: 1.3769410176149266,
        },
        referenceThresholds: {
          renter: 59815,
          owner_with_mortgage: 58855,
          owner_without_mortgage: 44869,
        },
      },
      "1002": {
        name: "Alabama Nonmetro",
        rentIndex: 0.553,
        adjustments: {
          renter: 0.8019781891960436,
          owner_with_mortgage: 0.8060049145080372,
          owner_without_mortgage: 0.8556128398698828,
        },
        referenceThresholds: {
          renter: 31622,
          owner_with_mortgage: 31489,
          owner_without_mortgage: 27881,
        },
      },
    },
    metroDataYear: 2024,
    metroSource: "Census Bureau SPM Thresholds by Metro Area 2024",
    metroSourceUrl:
      "https://www2.census.gov/programs-surveys/demo/tables/p60/287/SPM-pov-threshold-2024.xlsx",
    ...overrides,
  };
}
