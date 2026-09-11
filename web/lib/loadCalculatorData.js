function hasCalculatorData(data) {
  const years = data?.availableYears;
  const forecast = data?.forecast;
  if (
    data?.schemaVersion !== 2 ||
    !data.methodology?.equivalenceScale ||
    !Array.isArray(years) ||
    !years.length ||
    !years.every(Number.isInteger) ||
    !forecast?.scenarios?.[forecast.defaultScenario] ||
    !years.includes(forecast.latestPublishedYear)
  ) {
    return false;
  }

  return Object.values(forecast.scenarios).every((scenario) =>
    years.every((year) => {
      const entry = scenario?.years?.[year];
      return (
        Object.keys(data.areasByYear?.[year] ?? {}).length > 0 &&
        entry?.thresholds &&
        entry.housing_shares &&
        entry.rent_indices &&
        entry.geography_by_area
      );
    }),
  );
}

function poolEntry(pool, index) {
  if (!Number.isInteger(index) || index < 0 || !pool[index]) {
    throw new Error(
      "Calculator data contains an invalid shared-data reference.",
    );
  }
  return pool[index];
}

// Identical menus and geography inputs are serialized once. Expansion shares
// those same read-only objects; it never recomputes or rounds scientific values.
export function expandCalculatorData(wire) {
  if (
    wire?.uiSchemaVersion !== 1 ||
    !Array.isArray(wire.areaMenus) ||
    !Array.isArray(wire.geographies) ||
    !wire.areaMenuByYear ||
    !wire.forecast?.scenarios
  ) {
    throw new Error("Calculator data has an unsupported compact format.");
  }
  const {
    uiSchemaVersion,
    areaMenus,
    areaMenuByYear,
    geographies,
    forecast,
    ...data
  } = wire;
  const areasByYear = Object.fromEntries(
    Object.entries(areaMenuByYear).map(([year, index]) => [
      year,
      poolEntry(areaMenus, index),
    ]),
  );
  const scenarios = Object.fromEntries(
    Object.entries(forecast.scenarios).map(([id, scenario]) => [
      id,
      {
        ...scenario,
        years: Object.fromEntries(
          Object.entries(scenario?.years ?? {}).map(([year, entry]) => {
            const { geographyRef, ...inputs } = entry;
            return [
              year,
              { ...inputs, ...poolEntry(geographies, geographyRef) },
            ];
          }),
        ),
      },
    ]),
  );
  const expanded = {
    ...data,
    areasByYear,
    forecast: { ...forecast, scenarios },
  };
  if (!hasCalculatorData(expanded)) {
    throw new Error(
      "Calculator data is incomplete or has an unsupported format.",
    );
  }
  return expanded;
}

// This module must never import the JSON: the static page and its RSC payload
// contain only the loading shell. The browser requests the compact inputs once.
export async function loadCalculatorData({ signal } = {}) {
  const basePath = (process.env.NEXT_PUBLIC_BASE_PATH ?? "").replace(
    /\/+$/,
    "",
  );
  const response = await fetch(`${basePath}/data/release_config.json`, {
    signal,
    cache: "no-cache",
  });
  if (!response.ok) {
    throw new Error(`Calculator data request failed (${response.status}).`);
  }
  return expandCalculatorData(await response.json());
}
