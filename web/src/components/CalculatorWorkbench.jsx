"use client";

import { useMemo, useState } from "react";

import {
  DashboardShell,
  Command,
  CommandInput,
  CommandList,
  CommandItem,
  CommandEmpty,
  SidebarLayout,
  InputPanel,
  ResultsPanel,
  SidebarSection,
  SidebarDivider,
  SelectInput,
  NumberInput,
  SegmentedControl,
  MetricCard,
  DataTable,
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  Badge,
  Text,
  Title,
  Separator,
} from "@policyengine/ui-kit";

import { calculateGeoadj } from "@/lib/geoadj";
import { ForecastMethodology, ForecastWarnings } from "./ForecastDiagnostics";

const TENURE_OPTIONS = [
  { value: "renter", label: "Renter" },
  { value: "owner_with_mortgage", label: "Mortgage" },
  { value: "owner_without_mortgage", label: "No mortgage" },
];

const TENURE_LABELS = {
  renter: "Renter",
  owner_with_mortgage: "Owner with mortgage",
  owner_without_mortgage: "Owner without mortgage",
};

const PYPI_URL = "https://pypi.org/project/spm-calculator/";
const GITHUB_URL = "https://github.com/PolicyEngine/spm-calculator";
const PREVIEW_URL = `${GITHUB_URL}/pull/36`;

function fmtCurrency(value, fractionDigits = 0) {
  if (!Number.isFinite(value)) return "Unavailable";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: fractionDigits,
    minimumFractionDigits: fractionDigits,
  }).format(value);
}

function fmtPercent(value) {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(1)}%`;
}

function fmtInput(value) {
  return Number.isFinite(value) ? value.toFixed(3) : "Unavailable";
}

export function getRawEquivalenceScale(adults, children, methodology) {
  // Child-only ("0 adults, N children") units aren't valid SPM households,
  // so we return 0 rather than synthesising a single-parent scale from a
  // ghost adult. This matches the Python helper in
  // `spm_calculator.equivalence_scale.spm_equivalence_scale`.
  if (adults === 0) return 0;

  if (children > 0) {
    if (adults === 1) {
      return (
        (1 +
          methodology.equivalenceScale.singleAdultFirstChild +
          methodology.equivalenceScale.additionalChild *
            Math.max(children - 1, 0)) **
        methodology.equivalenceScale.economiesOfScale
      );
    }

    return (
      (adults + methodology.equivalenceScale.additionalChild * children) **
      methodology.equivalenceScale.economiesOfScale
    );
  }

  if (adults === 1) return 1;
  if (adults === 2) return methodology.equivalenceScale.twoAdultNoChild;
  return adults ** methodology.equivalenceScale.economiesOfScale;
}

function describeEquivalenceFormula(adults, children, methodology) {
  const {
    singleAdultFirstChild,
    additionalChild,
    economiesOfScale,
    twoAdultNoChild,
  } = methodology.equivalenceScale;
  if (adults === 0 && children === 0) return "0";
  if (children > 0) {
    if (adults <= 1) {
      return `(1 + ${singleAdultFirstChild} + ${additionalChild} * (${children} - 1))^${economiesOfScale}`;
    }
    return `(${adults} + ${additionalChild} * ${children})^${economiesOfScale}`;
  }
  if (adults <= 1) return "1.0";
  if (adults === 2) return String(twoAdultNoChild);
  return `${adults}^${economiesOfScale}`;
}

function rollingAdjustment(entry, areaId, tenure) {
  if (!entry?.geography_by_area?.[areaId]) return null;
  const rentIndex = entry?.rent_indices?.[areaId];
  const housingShare = entry?.housing_shares?.[tenure];
  if (
    !Number.isFinite(rentIndex) ||
    rentIndex <= 0 ||
    !Number.isFinite(housingShare) ||
    housingShare <= 0 ||
    housingShare >= 1
  )
    return null;
  return calculateGeoadj({ rentIndex, housingShare });
}

export default function CalculatorWorkbench({ data }) {
  const {
    methodology: baseMethodology,
    forecast,
    areasByYear,
    packageVersion,
    packageDistribution,
  } = data;
  const latestPublishedYear = forecast.latestPublishedYear;
  const [scenarioId, setScenarioId] = useState(forecast.defaultScenario);
  const selectedScenario = forecast.scenarios[scenarioId];
  const availableYears = Object.keys(selectedScenario.years).sort(
    (left, right) => Number(right) - Number(left),
  );
  const [year, setYear] = useState(String(latestPublishedYear));
  const selectedEntry = selectedScenario.years[year];
  const areas = areasByYear[year] ?? {};
  const metroEntries = useMemo(
    () =>
      Object.entries(areas)
        .filter(([id]) => selectedEntry?.geography_by_area?.[id])
        .sort(([, left], [, right]) => left.name.localeCompare(right.name)),
    [areas, selectedEntry],
  );
  const methodology = {
    ...baseMethodology,
    housingShares: selectedEntry?.housing_shares ?? {},
  };
  const [numAdults, setNumAdults] = useState(2);
  const [numChildren, setNumChildren] = useState(2);
  const [tenure, setTenure] = useState("renter");
  const [selectedGeographyId, setSelectedGeographyId] = useState(() =>
    areas["35620"] ? "35620" : (Object.keys(areas)[0] ?? ""),
  );
  const [locationQuery, setLocationQuery] = useState("");
  const selectedAreaStatus =
    selectedEntry?.geography_by_area?.[selectedGeographyId];
  const selectedArea = selectedAreaStatus ? areas[selectedGeographyId] : null;
  const currentLocation = selectedArea
    ? { id: selectedGeographyId, label: selectedArea.name }
    : null;
  const yearIsForecast = selectedEntry?.national_status === "forecast";
  const geographyPublished = selectedAreaStatus?.status === "published_anchor";
  const sharesPublished =
    selectedEntry?.housing_share_status === "published_anchor";
  const publishedPackage =
    packageDistribution?.status === "published" &&
    packageDistribution.version === packageVersion &&
    packageDistribution.publishedVersion === packageVersion;
  const packageUrl = publishedPackage
    ? `${PYPI_URL}${packageVersion}/`
    : PREVIEW_URL;
  const packageLabel = publishedPackage
    ? `spm-calculator ${packageVersion}`
    : "Preview Python API: calculator PR36";
  const ceSurveyWindow = selectedEntry?.ce_window
    ? `${selectedEntry.ce_window.start}–${selectedEntry.ce_window.end}`
    : "Unavailable";
  const annualForecastAssumptions = Object.entries(
    forecast.cpiProjections ?? {},
  )
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([target, rate]) => `${target}: ${(rate * 100).toFixed(1)}%`)
    .join("; ");
  const filteredMetroEntries = useMemo(() => {
    const query = locationQuery.trim().toLowerCase();
    return query
      ? metroEntries.filter(([id, area]) =>
          `${id} ${area.name}`.toLowerCase().includes(query),
        )
      : metroEntries;
  }, [locationQuery, metroEntries]);
  const base = selectedEntry?.thresholds?.[tenure] ?? null;
  const rawScale = getRawEquivalenceScale(numAdults, numChildren, methodology);
  const compositionValid =
    Number.isInteger(numAdults) &&
    numAdults >= 1 &&
    Number.isInteger(numChildren) &&
    numChildren >= 0;
  const equivalenceScale =
    rawScale / methodology.equivalenceScale.referenceFamilyRaw;
  function areaAdjustment(areaTenure) {
    return selectedArea
      ? rollingAdjustment(selectedEntry, selectedGeographyId, areaTenure)
      : null;
  }
  const geoadj = areaAdjustment(tenure);
  const rollingDataUnavailable =
    !selectedArea || geoadj === null || !Number.isFinite(base) || base <= 0;
  const locationError = !selectedArea
    ? `The selected area is unavailable in ${year}. Choose an area available for this year.`
    : rollingDataUnavailable
      ? "Rolling forecast data is unavailable for this area, tenure and year."
      : "";
  const threshold =
    rollingDataUnavailable || !compositionValid
      ? null
      : base * equivalenceScale * geoadj;
  const monthlyThreshold = threshold === null ? null : threshold / 12;
  const thresholdVsReference =
    threshold === null ? null : ((threshold - base) / base) * 100;
  const officialReferenceThreshold = rollingDataUnavailable
    ? null
    : base * geoadj;
  const selectedTenureLabel = TENURE_LABELS[tenure];
  const selectedLocationRentIndex = selectedArea
    ? selectedEntry?.rent_indices?.[selectedGeographyId]
    : null;
  const tenureComparisonData = TENURE_OPTIONS.map((option) => {
    const adjustment = areaAdjustment(option.value);
    const nationalBase = selectedEntry?.thresholds?.[option.value] ?? null;
    return {
      tenure: option.label,
      nationalBase,
      adjustment,
      locationThreshold:
        adjustment === null || !Number.isFinite(nationalBase)
          ? null
          : nationalBase * adjustment,
    };
  });
  const yearComparisonData = [...availableYears].reverse().map((targetYear) => {
    const entry = selectedScenario.years[targetYear];
    const nationalBase = entry?.thresholds?.[tenure] ?? null;
    const adjustment = areasByYear[targetYear]?.[selectedGeographyId]
      ? rollingAdjustment(entry, selectedGeographyId, tenure)
      : null;
    const areaStatus = entry?.geography_by_area?.[selectedGeographyId];
    return {
      year: targetYear,
      nationalBase,
      adjustment,
      componentStatus: !areaStatus
        ? "Area unavailable"
        : `${entry.national_status === "published" ? "Published national base" : "Forecast national base"}; ${areaStatus.status === "published_anchor" ? "published geography" : "modeled geography"}; ${entry.housing_share_status === "published_anchor" ? "published shares" : "modeled shares"}`,
      localThreshold:
        !compositionValid ||
        !Number.isFinite(nationalBase) ||
        nationalBase <= 0 ||
        adjustment === null
          ? null
          : nationalBase * equivalenceScale * adjustment,
    };
  });
  const packageSnippet = !compositionValid
    ? "# Enter valid classified adult and child counts to generate a calculation."
    : rollingDataUnavailable
      ? "# Rolling forecast data is unavailable for the selected area, tenure and year."
      : `from spm_calculator import load_forecast, SPMUnit

projection = load_forecast(expected_sha256="${forecast.contentSha256}")
result = projection.calculate_unit(SPMUnit(
    unit_id="household-1",
    num_adults=${numAdults}, num_children=${numChildren},
    tenure="${tenure}", year=${year},
    geography_kind="metro",
    geography_id="${currentLocation.id}",
), scenario="${scenarioId}")
print(result["threshold"])`;
  const locationSelectOptions = metroEntries.map(([value, area]) => ({
    value,
    label: area.name,
  }));
  const yearSelectOptions = availableYears.map((value) => ({
    value,
    label: `${value}${selectedScenario.years[value].national_status === "forecast" ? " (forecast)" : ""}`,
  }));

  // ── Render ──────────────────────────────────────────────────

  const sidebar = (
    <InputPanel title="Household and geography">
      {!compositionValid && (
        <p role="alert">
          Enter at least one classified SPM adult and a nonnegative whole number
          of children. Minor-only units need a separate classification decision.
        </p>
      )}
      <SidebarSection title="Threshold year">
        <SelectInput
          id="spm-year"
          aria-label="Threshold year"
          options={yearSelectOptions}
          value={year}
          onChange={setYear}
        />
      </SidebarSection>

      {
        <SidebarSection title="Real spending">
          <SelectInput
            id="spm-scenario"
            aria-label="Real spending"
            options={Object.entries(forecast.scenarios ?? {}).map(
              ([value, scenario]) => ({ value, label: scenario.label }),
            )}
            value={scenarioId}
            onChange={setScenarioId}
          />
        </SidebarSection>
      }

      <SidebarDivider />

      <SidebarSection title="Household composition">
        <div className="flex gap-3">
          <NumberInput
            label="Adults"
            id="spm-adults"
            aria-label="Adults"
            value={numAdults}
            onChange={setNumAdults}
            min={1}
            max={12}
          />
          <NumberInput
            label="Children"
            id="spm-children"
            aria-label="Children"
            value={numChildren}
            onChange={setNumChildren}
            min={0}
            max={16}
          />
        </div>
      </SidebarSection>

      <SidebarDivider />

      <SidebarSection title="Housing tenure">
        <SegmentedControl
          options={TENURE_OPTIONS}
          value={tenure}
          onValueChange={setTenure}
          size="sm"
        />
      </SidebarSection>

      <SidebarDivider />

      <SidebarSection title="Geography">
        <div className="space-y-3">
          <Command label="Search SPM areas" shouldFilter={false}>
            <p className="mb-1.5 text-sm font-medium text-muted-foreground">
              Search SPM areas
            </p>
            <CommandInput
              placeholder="New York, Alabama Nonmetro, 35620..."
              value={locationQuery}
              onValueChange={setLocationQuery}
            />
            {locationQuery.trim() && (
              <CommandList label="Matching SPM areas" className="max-h-60">
                <CommandEmpty>No SPM areas match your search.</CommandEmpty>
                {filteredMetroEntries.map(([code, info]) => (
                  <CommandItem
                    key={code}
                    value={code}
                    onSelect={() => {
                      setSelectedGeographyId(code);
                      setLocationQuery("");
                    }}
                  >
                    {info.name}
                  </CommandItem>
                ))}
              </CommandList>
            )}
          </Command>
          <SelectInput
            id="spm-census-area"
            aria-label="SPM estimation area"
            label="SPM estimation area"
            options={locationSelectOptions}
            value={selectedArea ? selectedGeographyId : ""}
            placeholder={
              selectedArea ? undefined : `Selected area unavailable in ${year}`
            }
            onChange={setSelectedGeographyId}
          />
          <p className="text-xs leading-5 text-muted-foreground">
            SPM estimation areas: MSAs, residual metro groups and state nonmetro
            groups. Availability and publication status depend on the year.
          </p>
        </div>
      </SidebarSection>

      {locationError && (
        <div
          role="alert"
          className="mx-4 mb-4 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
        >
          {locationError}
        </div>
      )}

      <SidebarDivider />

      <SidebarSection title="Method details">
        <div className="space-y-2 text-sm text-muted-foreground">
          <div className="flex justify-between">
            <span>Data source</span>
            <span className="font-medium text-foreground">
              {year} rolling windows
            </span>
          </div>
          <div className="flex justify-between">
            <span>Housing share</span>
            <span className="font-medium text-foreground">
              {fmtInput(methodology.housingShares[tenure])}
            </span>
          </div>
          {selectedLocationRentIndex !== null && (
            <div className="flex justify-between">
              <span>Rent index</span>
              <span className="font-medium text-foreground">
                {Number.isFinite(selectedLocationRentIndex)
                  ? selectedLocationRentIndex.toFixed(3)
                  : "Unavailable"}
              </span>
            </div>
          )}
        </div>
      </SidebarSection>
    </InputPanel>
  );

  const tenureTableColumns = [
    {
      key: "tenure",
      header: "Tenure",
      format: (v) => v,
    },
    {
      key: "nationalBase",
      header: `${year} national base`,
      align: "right",
      format: (v) => fmtCurrency(v),
    },
    {
      key: "locationThreshold",
      header: "Location threshold",
      align: "right",
      format: (v) => (v === null ? "Unavailable" : fmtCurrency(v)),
    },
    {
      key: "adjustment",
      header: "Adjustment",
      align: "right",
      format: (v) => (v === null ? "Unavailable" : `\u00D7${v.toFixed(3)}`),
    },
  ];

  const yearTableColumns = [
    {
      key: "year",
      header: "Year",
      format: (value) => (
        <span
          aria-current={value === year ? "date" : undefined}
          className={value === year ? "font-semibold" : undefined}
        >
          {value}
        </span>
      ),
    },
    {
      key: "nationalBase",
      header: "National base",
      align: "right",
      format: (value) => fmtCurrency(value),
    },
    {
      key: "adjustment",
      header: "Location factor",
      align: "right",
      format: (value) =>
        value === null ? "Unavailable" : `\u00D7${value.toFixed(3)}`,
    },
    {
      key: "localThreshold",
      header: "Local threshold",
      align: "right",
      format: (value) => fmtCurrency(value),
    },
    {
      key: "componentStatus",
      header: "Component status",
      format: (value) => value,
    },
  ];

  return (
    <DashboardShell>
      <SidebarLayout sidebar={sidebar} sidebarWidth="320px">
        <ResultsPanel>
          <div className="min-w-0 space-y-6">
            {/* Primary result */}
            <div data-testid="primary-result">
              <div className="mb-4 flex flex-wrap items-center gap-2">
                <Title order={2} className="text-xl">
                  {currentLocation?.label ?? "Area unavailable"}
                </Title>
                <Badge variant="secondary">{selectedTenureLabel}</Badge>
                {yearIsForecast && (
                  <Badge variant="warning">Research forecast</Badge>
                )}
                {selectedAreaStatus && (
                  <Badge variant={geographyPublished ? "secondary" : "warning"}>
                    {geographyPublished
                      ? `${year} published geography anchor`
                      : "Modeled geography"}
                  </Badge>
                )}
                {selectedEntry && (
                  <Badge variant={sharesPublished ? "secondary" : "warning"}>
                    {sharesPublished
                      ? "Housing shares published by BLS"
                      : "Modeled housing shares"}
                  </Badge>
                )}
              </div>

              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <MetricCard
                  label="SPM threshold"
                  value={fmtCurrency(threshold)}
                  format="string"
                />
                <MetricCard
                  label="Monthly"
                  value={
                    monthlyThreshold === null
                      ? "Unavailable"
                      : fmtCurrency(monthlyThreshold)
                  }
                  format="string"
                />
                <MetricCard
                  label="vs. national ref."
                  value={
                    thresholdVsReference === null
                      ? "Unavailable"
                      : fmtPercent(thresholdVsReference)
                  }
                  format="string"
                  trend={
                    thresholdVsReference === null
                      ? "neutral"
                      : thresholdVsReference > 0
                        ? "negative"
                        : "positive"
                  }
                />
                <MetricCard
                  label="Location factor"
                  value={fmtInput(geoadj)}
                  format="string"
                />
              </div>
              {
                <ForecastWarnings
                  forecast={forecast}
                  scenarioId={scenarioId}
                  year={year}
                  entry={selectedEntry}
                  areaId={selectedGeographyId}
                />
              }
            </div>

            {
              <Card data-testid="year-by-year-card" className="min-w-0">
                <CardHeader>
                  <CardTitle>Year by year</CardTitle>
                  <CardDescription>
                    {currentLocation?.label} · {selectedTenureLabel} ·{" "}
                    {numAdults} adults, {numChildren} children ·{" "}
                    {selectedScenario?.label}. National bases are for two adults
                    and two children; local thresholds use your household.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <DataTable
                    className="overflow-x-auto"
                    role="region"
                    aria-label="Year-by-year thresholds"
                    tabIndex={0}
                    columns={yearTableColumns}
                    data={yearComparisonData}
                    styles={{ table: { minWidth: "520px" } }}
                  />
                  <p className="mt-3 text-xs text-muted-foreground">
                    National thresholds and housing shares are published for
                    2022–2025. Geography status is specific to each area and
                    year. From 2026, values are conditional rolling CE and ACS
                    research forecasts.
                  </p>
                </CardContent>
              </Card>
            }

            <Separator />

            {/* Breakdown cards */}
            <div className="grid gap-4 lg:grid-cols-3">
              <Card>
                <CardHeader>
                  <CardTitle>Base threshold</CardTitle>
                  <CardDescription>
                    {yearIsForecast
                      ? "Projected national reference-family threshold before adjustments"
                      : "National BLS reference-family threshold before adjustments"}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <Text className="text-muted-foreground">Tenure</Text>
                      <Text className="font-medium">{selectedTenureLabel}</Text>
                    </div>
                    <div className="flex justify-between">
                      <Text className="text-muted-foreground">
                        Base threshold
                      </Text>
                      <Text className="font-medium">{fmtCurrency(base)}</Text>
                    </div>
                    <div className="flex justify-between">
                      <Text className="text-muted-foreground">Status</Text>
                      <Badge
                        variant={yearIsForecast ? "warning" : "secondary"}
                        className="text-xs"
                      >
                        {yearIsForecast ? "Forecast" : "Published by BLS"}
                      </Badge>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Family size</CardTitle>
                  <CardDescription>
                    Betson equivalence scale normalized to the 2A2C reference
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <Text className="text-muted-foreground">Formula</Text>
                      <Text className="font-mono text-xs font-medium">
                        {describeEquivalenceFormula(
                          numAdults,
                          numChildren,
                          methodology,
                        )}
                      </Text>
                    </div>
                    <div className="flex justify-between">
                      <Text className="text-muted-foreground">
                        Normalized scale
                      </Text>
                      <Text className="font-medium">
                        {equivalenceScale.toFixed(3)}
                      </Text>
                    </div>
                    <div className="flex justify-between">
                      <Text className="text-muted-foreground">Household</Text>
                      <Text className="font-medium">
                        {numAdults} adult{numAdults === 1 ? "" : "s"},{" "}
                        {numChildren} child{numChildren === 1 ? "" : "ren"}
                      </Text>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Location adjustment</CardTitle>
                  <CardDescription>
                    Selected area rent index with tenure-specific housing share
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <Text className="text-muted-foreground">Location</Text>
                      <Text className="font-medium">
                        {currentLocation?.label ?? "Unavailable"}
                      </Text>
                    </div>
                    <div className="flex justify-between">
                      <Text className="text-muted-foreground">
                        Location factor
                      </Text>
                      <Text className="font-medium">
                        {geoadj === null ? "Unavailable" : geoadj.toFixed(3)}
                      </Text>
                    </div>
                    <div className="flex justify-between">
                      <Text className="text-muted-foreground">
                        Ref. 2A2C threshold
                      </Text>
                      <Text className="font-medium">
                        {officialReferenceThreshold === null
                          ? "Unavailable"
                          : fmtCurrency(officialReferenceThreshold)}
                      </Text>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            <Separator />

            {/* Tenure comparison table */}
            <div>
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                <Title order={3} className="text-lg">
                  Tenure comparison
                </Title>
                <Text className="text-sm text-muted-foreground">
                  {currentLocation?.label ?? "Area unavailable"} · Two adults,
                  two children
                </Text>
              </div>
              <DataTable
                className="overflow-x-auto"
                role="region"
                aria-label="Tenure thresholds"
                tabIndex={0}
                columns={tenureTableColumns}
                data={tenureComparisonData}
                styles={{ table: { minWidth: "440px" } }}
              />
            </div>

            <Separator />

            <section
              data-testid="results-footnote"
              aria-label="Methodology and provenance"
              className="space-y-6"
            >
              {/* Methodology explainer */}
              <Card data-testid="methodology-card">
                <CardHeader>
                  <CardTitle>How this is calculated</CardTitle>
                  <CardDescription>
                    National bases, rolling CE spending and ACS rent windows
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-sm leading-6">
                  <p>
                    Threshold = <code className="font-mono">base[tenure]</code>{" "}
                    × <code className="font-mono">equivalence_scale</code> ×{" "}
                    <code className="font-mono">geoadj[tenure]</code>
                  </p>
                  {
                    <div className="space-y-3">
                      <p data-testid="source-windows">
                        <strong>{year} source windows</strong>: CE{" "}
                        {ceSurveyWindow}
                        {selectedEntry?.ce_window &&
                          ` · ${selectedEntry.ce_window.observed_quarters} observed / ${selectedEntry.ce_window.projected_quarters} projected quarters`}
                        . ACS{" "}
                        {selectedEntry?.acs_window
                          ? `${selectedEntry.acs_window.start}\u2013${selectedEntry.acs_window.end} · ${selectedEntry.acs_window.observed_years} observed / ${selectedEntry.acs_window.projected_years} projected years`
                          : "Unavailable"}
                        .
                      </p>
                      <p>
                        <strong>Common price assumptions</strong>:{" "}
                        {annualForecastAssumptions ||
                          "No price projections supplied"}
                        . <strong>Selected real spending growth</strong>:{" "}
                        {Number.isFinite(selectedScenario?.realGrowthRate)
                          ? `${(selectedScenario.realGrowthRate * 100).toFixed(2)}% per year`
                          : "Unavailable"}
                        . New observations are projected; rolling history is
                        retained. CE real spending and ACS rent assumptions are
                        separate.
                      </p>
                      <p
                        data-testid="forecast-disclaimer"
                        className="text-muted-foreground"
                      >
                        Both spending scenarios are conditional research
                        forecasts, not BLS or CBO forecasts. National thresholds
                        and housing shares for 2022–2025 are published by BLS.
                        The 2025 geography is modeled; 2026 onward uses future
                        conditional rolling CE and ACS inputs. Census publishes
                        indices for most historical areas; residual groups
                        without a published anchor are modeled.
                      </p>
                      {selectedAreaStatus && (
                        <p data-testid="area-provenance">
                          <strong>Selected geography</strong>:{" "}
                          {selectedAreaStatus.interpretation}.
                          {selectedAreaStatus.official_published_area
                            ? " This area has a published Census geography anchor."
                            : " This residual group has no published Census geography anchor."}
                        </p>
                      )}
                    </div>
                  }
                  <ul className="list-disc space-y-1 pl-6 text-muted-foreground">
                    <li>
                      <strong>Base</strong>: BLS reference-family thresholds for
                      two adults and two children. Future thresholds use each
                      year's rolling CE window. Public CE replication is
                      approximate; forecast uncertainty is not estimated.
                    </li>
                    <li>
                      <strong>Equivalence scale</strong>: Betson
                      three-parameter. Single-adult with K children:{" "}
                      <code className="font-mono">
                        (1 + 0.8 + 0.5·(K−1))^0.7
                      </code>
                      . Multi-adult with children:{" "}
                      <code className="font-mono">(A + 0.5·K)^0.7</code>.
                      Reference 2A2C = <code className="font-mono">3^0.7</code>.
                    </li>
                    <li>
                      <strong>GEOADJ</strong>:{" "}
                      <code className="font-mono">
                        1 + housing_share * (rent_index - 1)
                      </code>
                      , using the selected scenario and year's inputs for SPM
                      metro/nonmetro estimation areas. Housing shares: renter{" "}
                      {fmtInput(methodology.housingShares.renter)}, owner with
                      mortgage{" "}
                      {fmtInput(methodology.housingShares.owner_with_mortgage)},
                      owner without mortgage{" "}
                      {fmtInput(
                        methodology.housingShares.owner_without_mortgage,
                      )}
                      . County names inside MSA labels identify metropolitan
                      areas; this app does not estimate independent county or
                      congressional district thresholds.
                    </li>
                  </ul>
                  {
                    <ForecastMethodology
                      forecast={forecast}
                      scenarioId={scenarioId}
                      year={year}
                      entry={selectedEntry}
                      areaId={selectedGeographyId}
                    />
                  }
                  <p className="text-xs text-muted-foreground">
                    Census methodology:{" "}
                    <a
                      className="underline"
                      href="https://www.bls.gov/pir/spm/garner_spm_choices_03_15_21.pdf"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Garner (2021)
                    </a>
                    . 2024 anchor workbook:{" "}
                    <a
                      className="underline"
                      href="https://www.census.gov/library/publications/2025/demo/p60-287.html"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      P60-287
                    </a>
                    .
                  </p>
                </CardContent>
              </Card>

              {/* Python package */}
              <Card>
                <CardHeader>
                  <CardTitle>Reproduce with Python</CardTitle>
                  <CardDescription>
                    {publishedPackage
                      ? `Reproduce with published spm-calculator ${packageVersion}`
                      : `Reproduce with local build / development preview ${packageVersion}. This build is not confirmed published on PyPI.`}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <pre className="overflow-x-auto rounded-lg bg-muted p-4 text-sm leading-6 text-foreground">
                    <code>{packageSnippet}</code>
                  </pre>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <a
                      className="text-primary underline"
                      href={packageUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {packageLabel}
                    </a>
                    <a
                      className="text-primary underline"
                      href={GITHUB_URL}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      GitHub
                    </a>
                  </div>
                </CardContent>
              </Card>

              {/* Version + data vintage footer */}
              <footer
                data-testid="version-footer"
                className="pt-2 text-xs text-muted-foreground"
              >
                <p data-testid="forecast-provenance">
                  Rolling CE + ACS research forecast · information date{" "}
                  {forecast.informationDate}. Forecast SHA-256:{" "}
                  <code className="break-all">{forecast.contentSha256}</code>.
                  Base release SHA-256:{" "}
                  <code className="break-all">
                    {forecast.baseReleaseSha256}
                  </code>
                  . Assumption SHA-256:{" "}
                  <code className="break-all">{forecast.assumptionSha256}</code>
                  .
                </p>
                {forecast.auditArtifact?.url && (
                  <p className="mt-2">
                    <a
                      className="underline"
                      href={`${process.env.NEXT_PUBLIC_BASE_PATH ?? ""}${forecast.auditArtifact.url}`}
                      download={forecast.auditArtifact.name || true}
                    >
                      Download full canonical audit data (JSON)
                    </a>
                    . Includes the scientific inputs and diagnostics for the
                    forecast hash above.
                  </p>
                )}
                <p className="mt-2">
                  {publishedPackage
                    ? `Published package: spm-calculator ${packageVersion}.`
                    : `Local build / development preview: spm-calculator ${packageVersion}. Publication on PyPI is not confirmed for this build.`}
                </p>
                <p className="mt-2">
                  Sources:{" "}
                  {(forecast.sources ?? [])
                    .filter((source) => source.url)
                    .map((source, index) => (
                      <span key={source.id}>
                        {index > 0 ? " · " : ""}
                        <a
                          className="underline"
                          href={source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {source.title ?? source.label ?? source.id}
                        </a>
                      </span>
                    ))}
                </p>
              </footer>
            </section>
          </div>
        </ResultsPanel>
      </SidebarLayout>
    </DashboardShell>
  );
}
