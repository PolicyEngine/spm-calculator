"use client";

import { useEffect, useMemo, useState } from "react";

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
  Button,
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
const ROLLING_YEARS = Array.from({ length: 7 }, (_, index) =>
  String(2024 + index),
);

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

function getRawEquivalenceScale(adults, children, methodology) {
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

function getCeSurveyWindow(thresholdYear) {
  // BLS revised-methodology window: collection quarters (T-5)Q2
  // through (T)Q1 (corrected workbook, footnote 3).
  const t = Number(thresholdYear);
  return `${t - 5}Q2\u2013${t}Q1`;
}

function rollingAdjustment(entry, areaId, tenure) {
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
    baseThresholds: publishedThresholds,
    methodology: baseMethodology,
    releaseMetadata,
    housingSharesByYear = {},
    housingShareProvenanceByYear = {},
    forecast,
    nowcast = {},
    nowcastEvaluation = {},
    paperUrl,
    metroAreas,
    metroData,
    metroDataYear,
    packageVersion,
    metroSource,
    metroSourceUrl,
  } = data;
  const latestPublishedYear = forecast.latestPublishedYear;
  const isRolling = forecast.method === "rolling_ce_acs_v1";
  const [scenarioId, setScenarioId] = useState(
    forecast.defaultScenario ?? "ce_trend",
  );
  const selectedScenario = isRolling ? forecast.scenarios?.[scenarioId] : null;
  const baseThresholds = isRolling
    ? Object.fromEntries(
        ROLLING_YEARS.map((y) => [y, selectedScenario?.years?.[y]?.thresholds]),
      )
    : {
        ...publishedThresholds,
        ...forecast.thresholdsByYear,
      };
  // Legacy metro rent indices ship as a single Census vintage. Historical years
  // (< earliestMetroYear) are unsupported for metros because back-casting
  // a current rent index to earlier base thresholds does not match any
  // published BLS or Census table. Later threshold years carry the latest
  // bundled rent-index vintage and surface a warning badge.
  const earliestMetroYear =
    metroData?.earliestYear ?? metroDataYear ?? latestPublishedYear;
  const latestMetroYear =
    metroData?.latestYear ?? metroDataYear ?? latestPublishedYear;
  const availableYears = Object.keys(baseThresholds)
    .filter((value) => isRolling || Number(value) >= earliestMetroYear)
    .sort((left, right) => Number(right) - Number(left));

  const metroEntries = useMemo(
    () =>
      Object.entries(metroAreas).sort(([, left], [, right]) =>
        left.name.localeCompare(right.name),
      ),
    [metroAreas],
  );

  const [year, setYear] = useState(String(latestPublishedYear));
  const selectedEntry = selectedScenario?.years?.[year];
  const methodology = {
    ...baseMethodology,
    housingShares: isRolling
      ? (selectedEntry?.housing_shares ?? {})
      : (housingSharesByYear[year] ?? baseMethodology.housingShares),
  };
  const [numAdults, setNumAdults] = useState(2);
  const [numChildren, setNumChildren] = useState(2);
  const [tenure, setTenure] = useState("renter");
  const [selectedGeographyId, setSelectedGeographyId] = useState("35620");
  const [locationQuery, setLocationQuery] = useState("");
  const yearNowcast = isRolling ? null : (nowcast[year] ?? null);
  const yearNowcastEvaluation = isRolling
    ? null
    : (nowcastEvaluation[year] ?? null);
  const yearIsNowcast = Boolean(yearNowcast);
  const yearIsForecast = isRolling
    ? selectedEntry?.national_status === "forecast" ||
      Number(year) > latestPublishedYear
    : Number(year) > latestPublishedYear && !yearIsNowcast;
  const projectionFactor = forecast.factorsByYear?.[year];
  const projectionBaseYear = forecast.baseYear ?? latestPublishedYear;
  const ceSurveyWindow = isRolling
    ? selectedEntry?.ce_window
      ? `${selectedEntry.ce_window.start}\u2013${selectedEntry.ce_window.end}`
      : "Unavailable"
    : getCeSurveyWindow(yearIsForecast ? projectionBaseYear : year);
  const annualForecastAssumptions = Object.entries(
    forecast.cpiProjections ?? {},
  )
    .filter(([target]) => isRolling || Number(target) <= Number(year))
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([target, rate]) => `${target}: ${(rate * 100).toFixed(1)}%`)
    .join("; ");
  const shareProvenance =
    housingShareProvenanceByYear[year] ??
    housingShareProvenanceByYear[projectionBaseYear];

  useEffect(() => {
    setSelectedGeographyId((current) =>
      metroAreas[current] ? current : (Object.keys(metroAreas)[0] ?? ""),
    );
  }, [metroAreas]);

  const filteredMetroEntries = useMemo(() => {
    const query = locationQuery.trim().toLowerCase();
    if (!query) return metroEntries;
    return metroEntries.filter(([code, info]) =>
      `${code} ${info.name}`.toLowerCase().includes(query),
    );
  }, [locationQuery, metroEntries]);

  // ── Derived calculations ────────────────────────────────────

  const base = baseThresholds[year]?.[tenure] ?? null;
  const rawScale = getRawEquivalenceScale(numAdults, numChildren, methodology);
  const compositionValid =
    Number.isInteger(numAdults) &&
    numAdults >= 1 &&
    Number.isInteger(numChildren) &&
    numChildren >= 0;
  const equivalenceScale =
    rawScale / methodology.equivalenceScale.referenceFamilyRaw;

  const selectedMetroData = metroAreas[selectedGeographyId];
  const currentLocation = selectedMetroData
    ? { id: selectedGeographyId, label: selectedMetroData.name }
    : null;

  // Earlier local years need a matching historical Census rent-index
  // vintage. Later years carry the bundled index with an explicit label.
  const metroYearIsHistorical = !isRolling && Number(year) < earliestMetroYear;
  const metroIndexIsCarried = !isRolling && Number(year) > latestMetroYear;
  const rollingDataUnavailable =
    isRolling &&
    (!selectedMetroData ||
      rollingAdjustment(selectedEntry, selectedGeographyId, tenure) === null ||
      !Number.isFinite(base) ||
      base <= 0);
  const locationError = rollingDataUnavailable
    ? "Rolling forecast data is unavailable for this area, tenure and year."
    : metroYearIsHistorical
      ? `The bundled Census rent indices start in ${earliestMetroYear}. ` +
        `Choose ${earliestMetroYear} or later.`
      : "";

  function areaAdjustment(areaTenure) {
    if (!selectedMetroData || metroYearIsHistorical) return null;
    if (isRolling)
      return rollingAdjustment(selectedEntry, selectedGeographyId, areaTenure);
    return releaseMetadata
      ? calculateGeoadj({
          rentIndex: selectedMetroData.rentIndex,
          housingShare: methodology.housingShares[areaTenure],
        })
      : selectedMetroData.adjustments[areaTenure];
  }

  const geoadj = areaAdjustment(tenure);

  const threshold =
    geoadj === null || !compositionValid || rollingDataUnavailable
      ? null
      : base * equivalenceScale * geoadj;
  const monthlyThreshold = threshold === null ? null : threshold / 12;
  const nationalReferenceThreshold = base;
  const thresholdVsReference =
    threshold === null
      ? null
      : ((threshold - nationalReferenceThreshold) /
          nationalReferenceThreshold) *
        100;

  const officialReferenceThreshold =
    geoadj === null || rollingDataUnavailable ? null : base * geoadj;
  const selectedTenureLabel = TENURE_LABELS[tenure] ?? tenure;

  const selectedLocationRentIndex = isRolling
    ? (selectedEntry?.rent_indices?.[selectedGeographyId] ?? null)
    : (selectedMetroData?.rentIndex ?? null);

  const tenureComparisonData = TENURE_OPTIONS.map((option) => {
    const adjustment = areaAdjustment(option.value);
    const nationalBase = baseThresholds[year]?.[option.value] ?? null;
    return {
      tenure: option.label,
      nationalBase,
      locationThreshold:
        adjustment === null || nationalBase === null
          ? null
          : nationalBase * adjustment,
      adjustment,
    };
  });

  const yearComparisonData = isRolling
    ? ROLLING_YEARS.map((targetYear) => {
        const entry = selectedScenario?.years?.[targetYear];
        const nationalBase = entry?.thresholds?.[tenure] ?? null;
        const adjustment = rollingAdjustment(
          entry,
          selectedGeographyId,
          tenure,
        );
        return {
          year: targetYear,
          nationalBase,
          adjustment,
          localThreshold:
            !compositionValid ||
            !Number.isFinite(nationalBase) ||
            nationalBase <= 0 ||
            adjustment === null
              ? null
              : nationalBase * equivalenceScale * adjustment,
        };
      })
    : [];

  const packageSnippet = !compositionValid
    ? "# Enter valid classified adult and child counts to generate a calculation."
    : rollingDataUnavailable
      ? "# Rolling forecast data is unavailable for the selected area, tenure and year."
      : isRolling
        ? `from spm_calculator import load_forecast, SPMUnit

projection = load_forecast(expected_sha256="${forecast.contentSha256}")
result = projection.calculate_unit(SPMUnit(
    unit_id="household-1",
    num_adults=${numAdults}, num_children=${numChildren},
    tenure="${tenure}", year=${year},
    geography_kind="metro",
    geography_id="${currentLocation?.id}",
), scenario="${scenarioId}")
print(result["threshold"])`
        : `from spm_calculator import load_release, SPMUnit

release = load_release(${releaseMetadata ? `expected_sha256="${releaseMetadata.sha256}"` : ""})
result = release.calculate_unit(SPMUnit(
    unit_id="household-1",
    num_adults=${numAdults}, num_children=${numChildren},
    tenure="${tenure}", year=${yearIsForecast ? projectionBaseYear : year},
    geography_kind="metro",
    geography_id="${currentLocation?.id ?? "<select an area>"}",
))
${
  yearIsForecast
    ? `# ${year} price-only forecast; carry the base-year geography and shares.
# Annual inflation assumptions: ${annualForecastAssumptions}
inflation_factor = ${projectionFactor}
print(result["threshold"] * inflation_factor)`
    : 'print(result["threshold"])'
}`;

  // ── Location selector options ───────────────────────────────

  const locationSelectOptions = useMemo(
    () =>
      metroEntries.map(([code, info]) => ({
        value: code,
        label: info.name,
      })),
    [metroEntries],
  );

  const yearSelectOptions = useMemo(
    () =>
      availableYears.map((y) => ({
        value: y,
        label: `${y} ${
          !isRolling && nowcast[y]
            ? "(nowcast)"
            : Number(y) > latestPublishedYear
              ? "(forecast)"
              : ""
        }`.trim(),
      })),
    [availableYears, latestPublishedYear, nowcast, isRolling],
  );

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

      {isRolling && (
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
      )}

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
          <Command label="Search Census areas" shouldFilter={false}>
            <p className="mb-1.5 text-sm font-medium text-muted-foreground">
              Search Census areas
            </p>
            <CommandInput
              placeholder="New York, Alabama Nonmetro, 35620..."
              value={locationQuery}
              onValueChange={setLocationQuery}
            />
            {locationQuery.trim() && (
              <CommandList label="Matching Census areas" className="max-h-60">
                <CommandEmpty>No Census areas match your search.</CommandEmpty>
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
            aria-label="Census metro/nonmetro area"
            label="Census metro/nonmetro area"
            options={locationSelectOptions}
            value={selectedGeographyId}
            onChange={setSelectedGeographyId}
          />
          <p className="text-xs leading-5 text-muted-foreground">
            Published Census SPM areas: identified metropolitan areas and state
            residual metro/nonmetro groups.
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
              {isRolling
                ? `${year} rolling windows`
                : `${latestMetroYear} Census workbook`}
            </span>
          </div>
          <div className="flex justify-between">
            <span>Housing share</span>
            <span className="font-medium text-foreground">
              {isRolling
                ? Number.isFinite(methodology.housingShares[tenure])
                  ? methodology.housingShares[tenure].toFixed(3)
                  : "Unavailable"
                : methodology.housingShares[tenure]}
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
      format: (v) => (v === null ? "..." : fmtCurrency(v)),
    },
    {
      key: "adjustment",
      header: "Adjustment",
      align: "right",
      format: (v) => (v === null ? "..." : `\u00D7${v.toFixed(3)}`),
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
                  {currentLocation?.label ?? "Loading geography"}
                </Title>
                <Badge variant="secondary">{selectedTenureLabel}</Badge>
                {yearIsForecast && (
                  <Badge variant="warning">
                    {isRolling ? "Research forecast" : "Forecast"}
                  </Badge>
                )}
                {isRolling && selectedEntry && (
                  <Badge
                    variant={
                      selectedEntry.geography_status === "published_anchor"
                        ? "secondary"
                        : "warning"
                    }
                  >
                    {selectedEntry.geography_status === "published_anchor"
                      ? `${year} published geography anchor`
                      : "Modeled geography and housing shares"}
                  </Badge>
                )}
                {yearIsNowcast && (
                  <Badge variant="warning">Nowcast — not BLS</Badge>
                )}
                {metroIndexIsCarried && (
                  <Badge variant="warning">
                    {latestMetroYear} Census rent index (carried)
                  </Badge>
                )}
              </div>

              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <MetricCard
                  label="SPM threshold"
                  value={
                    threshold === null
                      ? isRolling
                        ? "Unavailable"
                        : "..."
                      : fmtCurrency(threshold)
                  }
                  format="string"
                />
                <MetricCard
                  label="Monthly"
                  value={
                    monthlyThreshold === null
                      ? "..."
                      : fmtCurrency(monthlyThreshold)
                  }
                  format="string"
                />
                <MetricCard
                  label="vs. national ref."
                  value={
                    thresholdVsReference === null
                      ? "..."
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
                  value={
                    geoadj === null
                      ? isRolling
                        ? "Unavailable"
                        : "..."
                      : geoadj.toFixed(3)
                  }
                  format="string"
                />
              </div>
              {isRolling && (
                <ForecastWarnings
                  forecast={forecast}
                  scenarioId={scenarioId}
                  year={year}
                  entry={selectedEntry}
                  areaId={selectedGeographyId}
                />
              )}
            </div>

            {isRolling && (
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
                  <div
                    className="overflow-x-auto"
                    role="region"
                    aria-label="Year-by-year thresholds"
                    tabIndex={0}
                  >
                    <DataTable
                      columns={yearTableColumns}
                      data={yearComparisonData}
                      styles={{ root: { minWidth: "440px" } }}
                    />
                  </div>
                  <p className="mt-3 text-xs text-muted-foreground">
                    2024: published geography anchor. 2025: published national
                    base with modeled geography and housing shares. 2026–2030:
                    conditional research forecasts.
                  </p>
                </CardContent>
              </Card>
            )}

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
                        variant={
                          yearIsForecast || yearIsNowcast
                            ? "warning"
                            : "secondary"
                        }
                        className="text-xs"
                      >
                        {yearIsNowcast
                          ? "Nowcast"
                          : yearIsForecast
                            ? "Forecast"
                            : "Published by BLS"}
                      </Badge>
                    </div>
                    {isRolling && (
                      <p
                        className="pt-1 text-xs text-muted-foreground"
                        data-testid="forecast-disclaimer"
                      >
                        Both spending scenarios are conditional research
                        forecasts, not BLS or CBO forecasts. Published national
                        2024 and 2025 values are retained; geography and housing
                        shares are modeled from 2025.
                      </p>
                    )}
                    {yearIsForecast && !isRolling && (
                      <p
                        className="pt-1 text-xs text-muted-foreground"
                        data-testid="forecast-disclaimer"
                      >
                        Price-only forecast from the published{" "}
                        {projectionBaseYear} national base. Inflation
                        assumptions: {annualForecastAssumptions}. These are
                        package modeling assumptions, not BLS or CBO forecasts.
                        Consumption growth and forecast uncertainty are not
                        estimated.
                      </p>
                    )}
                    {!yearIsForecast &&
                      !yearIsNowcast &&
                      Number(year) === 2025 && (
                        <p className="pt-1 text-xs text-muted-foreground">
                          BLS finalized the national 2025 thresholds on{" "}
                          <a
                            className="underline"
                            href="https://www.bls.gov/pir/spm/spm_thresholds_2025.htm"
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            August 24, 2026
                          </a>
                          . This is a threshold, not a published poverty rate.
                        </p>
                      )}
                    {yearIsNowcast && (
                      <p
                        className="pt-1 text-xs text-muted-foreground"
                        data-testid="nowcast-disclaimer"
                      >
                        {yearNowcast.label}. {yearNowcast.method}{" "}
                        {paperUrl && (
                          <a
                            className="underline"
                            href={paperUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            Working paper
                          </a>
                        )}
                      </p>
                    )}
                    {yearNowcastEvaluation && (
                      <p
                        className="pt-1 text-xs text-muted-foreground"
                        data-testid="nowcast-evaluation"
                      >
                        {yearNowcastEvaluation.label}. For{" "}
                        {selectedTenureLabel.toLowerCase()}, the archived
                        estimate was{" "}
                        {fmtCurrency(
                          yearNowcastEvaluation.tenures[tenure].nowcast,
                        )}
                        ,{" "}
                        {yearNowcastEvaluation.tenures[
                          tenure
                        ].percentage_error.toFixed(2)}
                        % versus BLS; mean absolute error across tenures was{" "}
                        {yearNowcastEvaluation.mean_absolute_percentage_error.toFixed(
                          2,
                        )}
                        %.
                      </p>
                    )}
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
                    Census area rent index with tenure-specific housing share
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <Text className="text-muted-foreground">Location</Text>
                      <Text className="font-medium">
                        {currentLocation?.label ?? "Loading"}
                      </Text>
                    </div>
                    <div className="flex justify-between">
                      <Text className="text-muted-foreground">
                        Location factor
                      </Text>
                      <Text className="font-medium">
                        {geoadj === null ? "..." : geoadj.toFixed(3)}
                      </Text>
                    </div>
                    <div className="flex justify-between">
                      <Text className="text-muted-foreground">
                        Ref. 2A2C threshold
                      </Text>
                      <Text className="font-medium">
                        {officialReferenceThreshold === null
                          ? "..."
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
                  {currentLocation?.label ?? "Loading geography"}
                </Text>
              </div>
              <DataTable
                columns={tenureTableColumns}
                data={tenureComparisonData}
              />
            </div>

            <Separator />

            {/* Methodology explainer */}
            <Card data-testid="methodology-card">
              <CardHeader>
                <CardTitle>How this is calculated</CardTitle>
                <CardDescription>
                  {isRolling
                    ? "National bases, rolling CE spending and ACS rent windows"
                    : "National base thresholds adjusted using Census SPM area rent indices"}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm leading-6">
                <p>
                  Threshold = <code className="font-mono">base[tenure]</code> ×{" "}
                  <code className="font-mono">equivalence_scale</code> ×{" "}
                  <code className="font-mono">geoadj[tenure]</code>
                </p>
                {isRolling && (
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
                    <p className="text-muted-foreground">
                      Research note: public PUMS rents are fractionally mapped
                      from PUMAs to Census areas; results are anchored to
                      published 2024 geography. CE replication is approximate;
                      uncertainty is not estimated.
                    </p>
                  </div>
                )}
                <ul className="list-disc space-y-1 pl-6 text-muted-foreground">
                  <li>
                    {isRolling ? (
                      <>
                        <strong>Base</strong>: published national BLS thresholds
                        for 2024 and 2025; later reference-family thresholds are
                        conditional research forecasts using each year's CE
                        window.
                      </>
                    ) : (
                      <>
                        <strong>Base</strong>: BLS FCSUti thresholds for the
                        reference family (2 adults, 2 children), by tenure, from
                        BLS, estimated over CE quarters {ceSurveyWindow}.
                        {yearIsForecast &&
                          ` The ${year} forecast compounds inflation assumptions from the published ${projectionBaseYear} base; it does not estimate a new CE expenditure window.`}
                        The 2019–2024 values use the corrected workbook BLS
                        published July 17, 2026, and 2025 uses the current
                        workbook published August 24, 2026. National 2025 renter
                        base ={" "}
                        <span className="font-mono">
                          {fmtCurrency(baseThresholds["2025"].renter)}
                        </span>
                        .
                      </>
                    )}
                  </li>
                  <li>
                    <strong>Equivalence scale</strong>: Betson three-parameter.
                    Single-adult with K children:{" "}
                    <code className="font-mono">(1 + 0.8 + 0.5·(K−1))^0.7</code>
                    . Multi-adult with children:{" "}
                    <code className="font-mono">(A + 0.5·K)^0.7</code>.
                    Reference 2A2C = <code className="font-mono">3^0.7</code>.
                  </li>
                  <li>
                    {isRolling ? (
                      <>
                        <strong>GEOADJ</strong>:{" "}
                        <code className="font-mono">
                          1 + housing_share * (rent_index - 1)
                        </code>
                        , using the selected scenario and year's inputs for
                        Census metro/nonmetro areas. Housing shares: renter{" "}
                        {fmtInput(methodology.housingShares.renter)}, owner with
                        mortgage{" "}
                        {fmtInput(
                          methodology.housingShares.owner_with_mortgage,
                        )}
                        , owner without mortgage{" "}
                        {fmtInput(
                          methodology.housingShares.owner_without_mortgage,
                        )}
                        .
                      </>
                    ) : (
                      <>
                        <strong>GEOADJ</strong>: Census {latestMetroYear} rent
                        indices for identified metro and state residual
                        metro/nonmetro areas. The housing share for the selected
                        tenure adjusts only the housing portion of the national
                        base: renter {methodology.housingShares.renter}, owner
                        with mortgage{" "}
                        {methodology.housingShares.owner_with_mortgage}, owner
                        without mortgage{" "}
                        {methodology.housingShares.owner_without_mortgage}. The
                        app uses the published Census area definitions; it does
                        not construct separate state, county or district
                        thresholds. Housing shares and rent indices carried into
                        another year are approximations. These calculated
                        thresholds combine the selected national series with the
                        bundled geography vintage and may differ from the
                        original Census workbook amounts.
                      </>
                    )}
                  </li>
                </ul>
                {isRolling && (
                  <ForecastMethodology
                    forecast={forecast}
                    scenarioId={scenarioId}
                    year={year}
                  />
                )}
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
                  . Metro workbook:{" "}
                  <a
                    className="underline"
                    href="https://www.census.gov/library/publications/2025/demo/p60-287.html"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    P60-287
                  </a>
                  . Corrected thresholds and nowcast evaluation:{" "}
                  <a
                    className="underline"
                    href={paperUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    working paper
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
                  {isRolling
                    ? "Reproduce this scenario with the preview Python API in calculator PR36"
                    : "Replay this release without credentials or a data download"}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <pre className="overflow-x-auto rounded-lg bg-muted p-4 text-sm leading-6 text-foreground">
                  <code>{packageSnippet}</code>
                </pre>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button
                    variant="default"
                    size="sm"
                    onClick={() =>
                      window.open(
                        isRolling ? PREVIEW_URL : PYPI_URL,
                        "_blank",
                        "noopener,noreferrer",
                      )
                    }
                  >
                    {isRolling ? "Preview Python API" : "PyPI"}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => window.open(GITHUB_URL, "_blank")}
                  >
                    GitHub
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Version + data vintage footer */}
            <footer
              data-testid="version-footer"
              className="pt-2 text-xs text-muted-foreground"
            >
              {releaseMetadata && (
                <p data-testid="release-provenance">
                  Release {releaseMetadata.id} · information date{" "}
                  {releaseMetadata.informationDate}
                  {!isRolling && (
                    <>
                      . Housing shares:{" "}
                      {shareProvenance?.reference_year ?? 2024}
                      {shareProvenance?.status === "carried"
                        ? " (carried to the selected year)"
                        : ""}
                    </>
                  )}
                  . SHA-256:{" "}
                  <code className="break-all">{releaseMetadata.sha256}</code>
                </p>
              )}
              {isRolling && (
                <p className="mt-2" data-testid="forecast-provenance">
                  Rolling CE + ACS research forecast · information date{" "}
                  {forecast.informationDate}. Forecast SHA-256:{" "}
                  <code className="break-all">{forecast.contentSha256}</code>.{" "}
                  Base release SHA-256:{" "}
                  <code className="break-all">
                    {forecast.baseReleaseSha256}
                  </code>
                  . Assumption SHA-256:{" "}
                  <code className="break-all">{forecast.assumptionSha256}</code>
                  .{" "}
                  <a
                    className="underline"
                    href={PREVIEW_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Preview Python API: calculator PR36
                  </a>
                  . This API is not yet published on PyPI.
                </p>
              )}
              {yearIsForecast && !isRolling && (
                <p className="mt-2" data-testid="forecast-provenance">
                  Forecast assumptions are separate from the published release.
                  Assumption SHA-256:{" "}
                  <code className="break-all">{forecast.assumptionSha256}</code>
                  . Rent indices and housing shares remain at {latestMetroYear}{" "}
                  values.
                </p>
              )}
              <p>
                Based on{" "}
                <a
                  className="underline"
                  href={metroSourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {metroSource}
                </a>
                {packageVersion && !isRolling ? (
                  <>
                    {" · "}
                    <a
                      className="underline"
                      href={PYPI_URL}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      spm-calculator {packageVersion}
                    </a>
                  </>
                ) : null}
              </p>
            </footer>
          </div>
        </ResultsPanel>
      </SidebarLayout>
    </DashboardShell>
  );
}
