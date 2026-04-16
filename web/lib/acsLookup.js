"use client";

const ACS_VARIABLE = "B25031_004E";
const ACS_BASE_URL = "https://api.census.gov/data";

const STATE_OPTIONS = [
  { fips: "01", abbr: "AL", name: "Alabama" },
  { fips: "02", abbr: "AK", name: "Alaska" },
  { fips: "04", abbr: "AZ", name: "Arizona" },
  { fips: "05", abbr: "AR", name: "Arkansas" },
  { fips: "06", abbr: "CA", name: "California" },
  { fips: "08", abbr: "CO", name: "Colorado" },
  { fips: "09", abbr: "CT", name: "Connecticut" },
  { fips: "10", abbr: "DE", name: "Delaware" },
  { fips: "11", abbr: "DC", name: "District of Columbia" },
  { fips: "12", abbr: "FL", name: "Florida" },
  { fips: "13", abbr: "GA", name: "Georgia" },
  { fips: "15", abbr: "HI", name: "Hawaii" },
  { fips: "16", abbr: "ID", name: "Idaho" },
  { fips: "17", abbr: "IL", name: "Illinois" },
  { fips: "18", abbr: "IN", name: "Indiana" },
  { fips: "19", abbr: "IA", name: "Iowa" },
  { fips: "20", abbr: "KS", name: "Kansas" },
  { fips: "21", abbr: "KY", name: "Kentucky" },
  { fips: "22", abbr: "LA", name: "Louisiana" },
  { fips: "23", abbr: "ME", name: "Maine" },
  { fips: "24", abbr: "MD", name: "Maryland" },
  { fips: "25", abbr: "MA", name: "Massachusetts" },
  { fips: "26", abbr: "MI", name: "Michigan" },
  { fips: "27", abbr: "MN", name: "Minnesota" },
  { fips: "28", abbr: "MS", name: "Mississippi" },
  { fips: "29", abbr: "MO", name: "Missouri" },
  { fips: "30", abbr: "MT", name: "Montana" },
  { fips: "31", abbr: "NE", name: "Nebraska" },
  { fips: "32", abbr: "NV", name: "Nevada" },
  { fips: "33", abbr: "NH", name: "New Hampshire" },
  { fips: "34", abbr: "NJ", name: "New Jersey" },
  { fips: "35", abbr: "NM", name: "New Mexico" },
  { fips: "36", abbr: "NY", name: "New York" },
  { fips: "37", abbr: "NC", name: "North Carolina" },
  { fips: "38", abbr: "ND", name: "North Dakota" },
  { fips: "39", abbr: "OH", name: "Ohio" },
  { fips: "40", abbr: "OK", name: "Oklahoma" },
  { fips: "41", abbr: "OR", name: "Oregon" },
  { fips: "42", abbr: "PA", name: "Pennsylvania" },
  { fips: "44", abbr: "RI", name: "Rhode Island" },
  { fips: "45", abbr: "SC", name: "South Carolina" },
  { fips: "46", abbr: "SD", name: "South Dakota" },
  { fips: "47", abbr: "TN", name: "Tennessee" },
  { fips: "48", abbr: "TX", name: "Texas" },
  { fips: "49", abbr: "UT", name: "Utah" },
  { fips: "50", abbr: "VT", name: "Vermont" },
  { fips: "51", abbr: "VA", name: "Virginia" },
  { fips: "53", abbr: "WA", name: "Washington" },
  { fips: "54", abbr: "WV", name: "West Virginia" },
  { fips: "55", abbr: "WI", name: "Wisconsin" },
  { fips: "56", abbr: "WY", name: "Wyoming" },
];

const STATE_MAP = Object.fromEntries(
  STATE_OPTIONS.map((state) => [state.fips, state]),
);

const CACHE = new Map();

function getStateInfo(stateFips) {
  return STATE_MAP[stateFips] ?? { abbr: stateFips, name: stateFips };
}

function getCacheKey(kind, acsYear, locationKey = "") {
  return `${kind}:${acsYear}:${locationKey}`;
}

async function fetchCensusRows(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Census API request failed (${response.status}).`);
  }

  return response.json();
}

function rowsToObjects([headers, ...rows]) {
  return rows.map((row) =>
    Object.fromEntries(headers.map((header, index) => [header, row[index]])),
  );
}

function sortByLabel(left, right) {
  return left.label.localeCompare(right.label);
}

function buildUrl(acsYear, clauses) {
  const query = new URLSearchParams({
    get: `NAME,${ACS_VARIABLE}`,
    ...clauses,
  });
  return `${ACS_BASE_URL}/${acsYear}/acs/acs5?${query.toString()}`;
}

async function getNationalMedianRent(acsYear) {
  const cacheKey = getCacheKey("national", acsYear);
  if (CACHE.has(cacheKey)) {
    return CACHE.get(cacheKey);
  }

  const rows = rowsToObjects(
    await fetchCensusRows(buildUrl(acsYear, { for: "us:*" })),
  );
  const nationalMedianRent = Number(rows[0]?.[ACS_VARIABLE]);

  if (!Number.isFinite(nationalMedianRent)) {
    throw new Error("National median rent was missing from the Census API.");
  }

  CACHE.set(cacheKey, nationalMedianRent);
  return nationalMedianRent;
}

export function getLatestAvailableAcsYear(now = new Date()) {
  return now.getMonth() === 11 ? now.getFullYear() - 1 : now.getFullYear() - 2;
}

export function getAcsYearForThresholdYear(thresholdYear, now = new Date()) {
  return Math.min(Number(thresholdYear) - 1, getLatestAvailableAcsYear(now));
}

export function calculateCustomGeoadj({
  localMedianRent,
  nationalMedianRent,
  tenure,
  housingShares,
}) {
  const housingShare = housingShares[tenure];
  return (
    (Number(localMedianRent) / Number(nationalMedianRent)) * housingShare +
    (1 - housingShare)
  );
}

export async function loadStateRentOptions(acsYear) {
  const cacheKey = getCacheKey("state", acsYear);
  if (CACHE.has(cacheKey)) {
    return CACHE.get(cacheKey);
  }

  const [rows, nationalMedianRent] = await Promise.all([
    fetchCensusRows(buildUrl(acsYear, { for: "state:*" })),
    getNationalMedianRent(acsYear),
  ]);

  const options = rowsToObjects(rows)
    .filter((row) => STATE_MAP[row.state])
    .map((row) => {
      const state = getStateInfo(row.state);
      return {
        id: row.state,
        label: state.name,
        shortLabel: state.abbr,
        medianRent: Number(row[ACS_VARIABLE]),
      };
    })
    .filter((option) => Number.isFinite(option.medianRent))
    .sort(sortByLabel);

  const value = { nationalMedianRent, options };
  CACHE.set(cacheKey, value);
  return value;
}

export async function loadCountyRentOptions(acsYear, stateFips) {
  const cacheKey = getCacheKey("county", acsYear, stateFips);
  if (CACHE.has(cacheKey)) {
    return CACHE.get(cacheKey);
  }

  const [rows, nationalMedianRent] = await Promise.all([
    fetchCensusRows(
      buildUrl(acsYear, {
        for: "county:*",
        in: `state:${stateFips}`,
      }),
    ),
    getNationalMedianRent(acsYear),
  ]);

  const options = rowsToObjects(rows)
    .map((row) => ({
      id: `${row.state}${row.county}`,
      label: row.NAME,
      shortLabel: row.NAME.split(",")[0],
      medianRent: Number(row[ACS_VARIABLE]),
    }))
    .filter((option) => Number.isFinite(option.medianRent))
    .sort(sortByLabel);

  const value = { nationalMedianRent, options };
  CACHE.set(cacheKey, value);
  return value;
}

export async function loadDistrictRentOptions(acsYear, stateFips) {
  const cacheKey = getCacheKey("district", acsYear, stateFips);
  if (CACHE.has(cacheKey)) {
    return CACHE.get(cacheKey);
  }

  const [rows, nationalMedianRent] = await Promise.all([
    fetchCensusRows(
      buildUrl(acsYear, {
        for: "congressional district:*",
        in: `state:${stateFips}`,
      }),
    ),
    getNationalMedianRent(acsYear),
  ]);

  const state = getStateInfo(stateFips);
  const options = rowsToObjects(rows)
    .map((row) => {
      const districtCode = String(row["congressional district"]).padStart(2, "0");
      const shortDistrict = districtCode === "00" ? "AL" : districtCode;
      return {
        id: `${row.state}${districtCode}`,
        label: `${state.abbr}-${shortDistrict} · ${row.NAME}`,
        shortLabel: `${state.abbr}-${shortDistrict}`,
        medianRent: Number(row[ACS_VARIABLE]),
      };
    })
    .filter((option) => Number.isFinite(option.medianRent))
    .sort(sortByLabel);

  const value = { nationalMedianRent, options };
  CACHE.set(cacheKey, value);
  return value;
}

export const STATE_SELECTOR_OPTIONS = STATE_OPTIONS;
