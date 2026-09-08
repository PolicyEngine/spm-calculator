"use client";

import releaseConfig from "@/public/data/release_config.json";

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


export const STATE_SELECTOR_OPTIONS = STATE_OPTIONS;

export function getLatestAvailableAcsYear() {
  return releaseConfig.acsLookup.state.year;
}

export function getAcsYearForThresholdYear(thresholdYear) {
  return Math.min(Number(thresholdYear) - 1, getLatestAvailableAcsYear());
}

export function calculateCustomGeoadj({ localMedianRent, nationalMedianRent, tenure, housingShares }) {
  const rent = Number(localMedianRent);
  const national = Number(nationalMedianRent);
  const share = housingShares[tenure];
  if (!Number.isFinite(rent) || rent <= 0 || !Number.isFinite(national) || national <= 0 || !Number.isFinite(share) || share <= 0 || share >= 1) {
    throw new Error("Rent and housing-share inputs must be valid positive values.");
  }
  return 1 - share + share * rent / national;
}

function loadOptions(kind, year, stateFips) {
  const table = releaseConfig.acsLookup[kind];
  if (Number(year) !== table.year) {
    throw new Error(`This release bundles ACS ${table.year} rents; ACS ${year} is unavailable. Choose a supported year or national geography.`);
  }
  const states = new Set(STATE_OPTIONS.map(state => state.fips));
  const options = table.options.filter(option => kind === "state" ? states.has(option.id) : option.id.slice(0, 2) === stateFips)
    .map(option => ({...option})).sort((a, b) => a.label.localeCompare(b.label));
  if (!options.length) throw new Error("No published rent data for the requested area in this release.");
  return { nationalMedianRent: table.nationalMedianRent, options, year: table.year, sourceId: table.sourceId, releaseId: releaseConfig.releaseMetadata.id };
}

export async function loadStateRentOptions(year) {
  return loadOptions("state", year);
}

export async function loadCountyRentOptions(year, stateFips) {
  return loadOptions("county", year, stateFips);
}

export async function loadDistrictRentOptions(year, stateFips) {
  return loadOptions("congressional_district", year, stateFips);
}
