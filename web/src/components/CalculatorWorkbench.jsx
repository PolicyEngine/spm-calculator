"use client";

import { useMemo, useState } from "react";

import {
  DashboardShell,
  Header,
  InputPanel,
  ResultsPanel,
  SidebarSection,
  SidebarDivider,
  SelectInput,
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
  logos,
  Input,
} from "@policyengine/ui-kit";

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
const API_DOCS_URL =
  "https://github.com/PolicyEngine/spm-calculator/tree/main/docs/api";
const UNIT_ID_DOCS_URL =
  "https://github.com/PolicyEngine/spm-calculator/blob/main/docs/api/units.md";

function fmtCurrency(value, fractionDigits = 0) {
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

function compareStrings(left, right) {
  if (left < right) return -1;
  if (left > right) return 1;
  return 0;
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
        1 +
        methodology.equivalenceScale.singleAdultFirstChild +
        methodology.equivalenceScale.additionalChild * Math.max(children - 1, 0)
      ) ** methodology.equivalenceScale.economiesOfScale;
    }

    return (
      adults + methodology.equivalenceScale.additionalChild * children
    ) ** methodology.equivalenceScale.economiesOfScale;
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
  if (adults === 0) return "requires adult";
  if (children > 0) {
    if (adults === 1) {
      return `(1 + ${singleAdultFirstChild} + ${additionalChild} * (${children} - 1))^${economiesOfScale}`;
    }
    return `(${adults} + ${additionalChild} * ${children})^${economiesOfScale}`;
  }
  if (adults <= 1) return "1.0";
  if (adults === 2) return String(twoAdultNoChild);
  return `${adults}^${economiesOfScale}`;
}

export default function CalculatorWorkbench({ data }) {
  const {
    baseThresholds,
    methodology,
    forecast,
    metroAreas,
    metroData,
    packageVersion,
    metroSource,
    metroSourceUrl,
  } = data;
  const latestPublishedYear = forecast.latestPublishedYear;
  // Metro rent indices ship as a single Census vintage. Historical years
  // (< earliestMetroYear) are unsupported for metros because back-casting
  // a current rent index to earlier base thresholds does not match any
  // published BLS or Census table. Forecast years (> latestMetroYear)
  // pin to the latest bundled vintage and surface a warning badge.
  const earliestMetroYear = metroData?.earliestYear ?? latestPublishedYear;
  const latestMetroYear = metroData?.latestYear ?? latestPublishedYear;
  const availableYears = Object.keys(baseThresholds).sort(
    (left, right) => Number(right) - Number(left),
  );
  const metroEntries = useMemo(
    () =>
      Object.entries(metroAreas).sort(([leftCode, left], [rightCode, right]) =>
        compareStrings(left.name, right.name) ||
        compareStrings(leftCode, rightCode),
      ),
    [metroAreas],
  );

  const [year, setYear] = useState("");
  const [numAdultsInput, setNumAdultsInput] = useState("");
  const [numChildrenInput, setNumChildrenInput] = useState("");
  const [tenure, setTenure] = useState("");
  const [selectedGeographyId, setSelectedGeographyId] = useState("");
  const geographyType = "metro_area";

  const yearIsSelected = Boolean(year);
  const numAdults = Number(numAdultsInput);
  const numChildren = Number(numChildrenInput);
  const compositionIsComplete =
    numAdultsInput !== "" && numChildrenInput !== "";
  const tenureIsSelected = Boolean(tenure);
  const yearIsForecast = yearIsSelected && Number(year) > latestPublishedYear;

  // ── Derived calculations ────────────────────────────────────

  const base =
    yearIsSelected && tenureIsSelected
      ? (baseThresholds[year]?.[tenure] ?? null)
      : null;
  const compositionError =
    compositionIsComplete && numAdults === 0
      ? "SPM units must include at least one adult. Add an adult to calculate a threshold."
      : "";
  const compositionIsValid = compositionIsComplete && !compositionError;
  const rawScale = compositionIsComplete
    ? getRawEquivalenceScale(numAdults, numChildren, methodology)
    : null;
  const equivalenceScale = compositionIsValid && rawScale !== null
    ? rawScale / methodology.equivalenceScale.referenceFamilyRaw
    : null;

  const selectedMetroData = metroAreas[selectedGeographyId] ?? null;

  const currentLocation = useMemo(() => {
    if (selectedMetroData) {
      return {
        id: selectedGeographyId,
        label: selectedMetroData.name,
        shortLabel: "Census area",
      };
    }
    return null;
  }, [selectedGeographyId, selectedMetroData]);

  // Metros only support years >= earliestMetroYear. Older years come back
  // as an error state (mirrors Python's ValueError in
  // `_resolve_bundled_metro_year`) so the UI doesn't silently compound a
  // 2024 rent index against a 2015 base threshold.
  const metroYearIsHistorical =
    yearIsSelected && Number(year) < earliestMetroYear;
  const metroYearIsForecast = yearIsSelected && Number(year) > latestMetroYear;

  const geoadj = useMemo(() => {
    if (metroYearIsHistorical) return null;
    if (selectedMetroData && tenureIsSelected) {
      return selectedMetroData.adjustments[tenure] ?? null;
    }
    return null;
  }, [metroYearIsHistorical, selectedMetroData, tenure, tenureIsSelected]);

  const metroYearError = metroYearIsHistorical
    ? `Metro rent indices are only published for ${earliestMetroYear} and later. ` +
      `Choose ${earliestMetroYear} or later.`
    : "";

  const calculatorIsReady =
    yearIsSelected &&
    tenureIsSelected &&
    compositionIsValid &&
    Boolean(selectedMetroData) &&
    base !== null &&
    geoadj !== null &&
    !metroYearIsHistorical;

  const threshold =
    !calculatorIsReady || geoadj === null || equivalenceScale === null
      ? null
      : base * equivalenceScale * geoadj;
  const monthlyThreshold = threshold === null ? null : threshold / 12;
  const nationalReferenceThreshold = base;
  const thresholdVsReference =
    threshold === null
      ? null
      : ((threshold - nationalReferenceThreshold) / nationalReferenceThreshold) * 100;

  const officialReferenceThreshold =
    geoadj === null || base === null ? null : base * geoadj;
  const selectedTenureLabel = tenure ? (TENURE_LABELS[tenure] ?? tenure) : "";

  const selectedLocationRentIndex = selectedMetroData?.rentIndex ?? null;
  const locationError = metroYearError;

  const tenureComparisonData = TENURE_OPTIONS.map((option) => {
    let adjustment = 1;
    let isReady = Boolean(selectedMetroData);

    if (metroYearIsHistorical) {
      isReady = false;
    } else if (selectedMetroData) {
      adjustment = selectedMetroData.adjustments[option.value];
    }

    const nationalBase = yearIsSelected
      ? (baseThresholds[year]?.[option.value] ?? null)
      : null;
    return {
      tenure: option.label,
      nationalBase,
      locationThreshold:
        isReady && nationalBase !== null ? nationalBase * adjustment : null,
      adjustment: isReady ? adjustment : null,
    };
  });

  const packageSnippet = calculatorIsReady
    ? `import spm_calculator as spm

calc = spm.SPMCalculator(${year})
t = calc.calculate_threshold(
    num_adults=${numAdults},
    num_children=${numChildren},
    tenure="${tenure}",
    geography_type="${geographyType}",
    geography_id="${currentLocation?.id ?? "<loading>"}"
)

print(f"SPM threshold: \${t:,.0f}")`
    : "";

  const microdataSnippet = `from spm_calculator import (
    spm_unit_id,
    spm_unit_id_match,
)

ids, diagnostics = spm_unit_id(
    persons,
    diagnostics=True,
)
report = spm_unit_id_match(
    persons,
    reference_spm_unit_id="SPM_ID",
)`;

  // ── Location selector options ───────────────────────────────

  const locationSelectOptions = useMemo(() => {
    return metroEntries.map(([code, info]) => ({
      value: code,
      label: info.name,
    }));
  }, [metroEntries]);

  const yearSelectOptions = useMemo(
    () =>
      availableYears.map((y) => ({
        value: y,
        label: `${y} ${Number(y) > latestPublishedYear ? "(forecast)" : ""}`.trim(),
      })),
    [availableYears, latestPublishedYear],
  );

  const setupSteps = [
    {
      label: "Threshold year",
      complete: yearIsSelected,
      detail: yearIsSelected ? year : "Choose a year",
    },
    {
      label: "Household",
      complete: compositionIsValid,
      detail: compositionIsComplete
        ? compositionError || `${numAdults} adults, ${numChildren} children`
        : "Enter adults and children",
    },
    {
      label: "Tenure",
      complete: tenureIsSelected,
      detail: tenureIsSelected ? selectedTenureLabel : "Choose housing tenure",
    },
    {
      label: "Census area",
      complete: Boolean(selectedMetroData) && !metroYearIsHistorical,
      detail:
        metroYearError ||
        currentLocation?.label ||
        "Choose a metro/nonmetro area",
    },
  ];

  // ── Render ──────────────────────────────────────────────────

  const sidebar = (
    <InputPanel title="Household and geography">
      <SidebarSection title="Threshold year">
        <SelectInput
          placeholder="Select threshold year"
          options={yearSelectOptions}
          value={year}
          onChange={setYear}
        />
      </SidebarSection>

      <SidebarDivider />

      <SidebarSection title="Household composition">
        <div className="flex gap-3">
          <label className="flex flex-1 flex-col gap-1 text-sm font-medium text-muted-foreground">
            Adults
            <Input
              type="number"
              min={0}
              max={12}
              value={numAdultsInput}
              placeholder="Adults"
              onChange={(event) => setNumAdultsInput(event.target.value)}
            />
          </label>
          <label className="flex flex-1 flex-col gap-1 text-sm font-medium text-muted-foreground">
            Children
            <Input
              type="number"
              min={0}
              max={16}
              value={numChildrenInput}
              placeholder="Children"
              onChange={(event) => setNumChildrenInput(event.target.value)}
            />
          </label>
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
        <SelectInput
          label="Census metro/nonmetro area"
          placeholder="Select Census area"
          options={locationSelectOptions}
          value={selectedGeographyId}
          onChange={setSelectedGeographyId}
          disabled={Boolean(locationError)}
        />
      </SidebarSection>

      {locationError && (
        <div className="mx-4 mb-4 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {locationError}
        </div>
      )}

      <SidebarDivider />

      <SidebarSection title="Method details">
        <div className="space-y-2 text-sm text-muted-foreground">
          <div className="flex justify-between">
            <span>Data source</span>
            <span className="font-medium text-foreground">
              2024 Census workbook
            </span>
          </div>
          <div className="flex justify-between">
            <span>Housing share</span>
            <span className="font-medium text-foreground">
              {tenure ? methodology.housingShares[tenure] : "..."}
            </span>
          </div>
          {selectedLocationRentIndex !== null && (
            <div className="flex justify-between">
              <span>Rent index</span>
              <span className="font-medium text-foreground">
                {selectedLocationRentIndex.toFixed(3)}
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
      header: yearIsSelected ? `${year} national base` : "National base",
      align: "right",
      format: (v) => (v === null ? "..." : fmtCurrency(v)),
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

  return (
    <DashboardShell>
      <Header
        variant="dark"
        logo={
          <img
            src={logos.whiteWordmark}
            alt="PolicyEngine"
            className="h-5"
          />
        }
        actions={
          <div className="flex items-center gap-4 text-sm font-semibold text-white/90">
            <span className="hidden sm:inline">SPM threshold calculator</span>
            <a href={API_DOCS_URL} target="_blank" rel="noopener noreferrer">
              Docs
            </a>
            <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
              GitHub
            </a>
          </div>
        }
      />

      <div className="flex min-h-screen flex-col md:flex-row">
        <aside className="order-1 w-full border-r border-border bg-background md:w-[320px] md:flex-shrink-0 md:overflow-y-auto">
          {sidebar}
        </aside>
        <main className="order-2 flex-1 overflow-y-auto">
          <ResultsPanel>
          <div className="space-y-6">
            {!calculatorIsReady && (
              <Card data-testid="setup-wizard">
                <CardHeader>
                  <CardTitle>Set up an SPM threshold</CardTitle>
                  <CardDescription>
                    Census metro-area threshold inputs
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    {setupSteps.map((step, index) => (
                      <div
                        key={step.label}
                        className={
                          step.complete
                            ? "rounded-md border border-teal-200 bg-teal-50 px-3 py-3"
                            : "rounded-md border border-border bg-background px-3 py-3"
                        }
                      >
                        <div className="mb-2 flex items-center gap-2">
                          <span
                            className={
                              step.complete
                                ? "flex h-6 w-6 items-center justify-center rounded-full bg-teal-700 text-xs font-semibold text-white"
                                : "flex h-6 w-6 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground"
                            }
                          >
                            {index + 1}
                          </span>
                          <Text className="font-medium">{step.label}</Text>
                        </div>
                        <Text className="text-sm text-muted-foreground">
                          {step.detail}
                        </Text>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {compositionError && (
              <div
                data-testid="composition-error"
                className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
              >
                {compositionError}
              </div>
            )}

            {calculatorIsReady && (
              <>
                {/* Primary result */}
                <div>
                  <div className="mb-4 flex flex-wrap items-center gap-2">
                    <Title order={2} className="text-xl">
                      {currentLocation.label}
                    </Title>
                    <Badge variant="secondary">{selectedTenureLabel}</Badge>
                    {yearIsForecast && (
                      <Badge variant="warning">Forecast</Badge>
                    )}
                    {metroYearIsForecast && (
                      <Badge variant="warning">
                        {latestMetroYear} metro rent index
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
                      value={fmtCurrency(monthlyThreshold)}
                      format="string"
                    />
                    <MetricCard
                      label="vs. national ref."
                      value={fmtPercent(thresholdVsReference)}
                      format="string"
                      trend={thresholdVsReference > 0 ? "negative" : "positive"}
                    />
                    <MetricCard
                      label="Location factor"
                      value={geoadj.toFixed(3)}
                      format="string"
                    />
                  </div>
                </div>

                <Separator />

                {/* Breakdown cards */}
                <div className="grid gap-4 lg:grid-cols-3">
                  <Card>
                    <CardHeader>
                      <CardTitle>Base threshold</CardTitle>
                      <CardDescription>
                        National BLS reference-family threshold before adjustments
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <Text className="text-muted-foreground">Tenure</Text>
                          <Text className="font-medium">
                            {selectedTenureLabel}
                          </Text>
                        </div>
                        <div className="flex justify-between">
                          <Text className="text-muted-foreground">Base threshold</Text>
                          <Text className="font-medium">{fmtCurrency(base)}</Text>
                        </div>
                        <div className="flex justify-between">
                          <Text className="text-muted-foreground">Status</Text>
                          <Badge
                            variant={yearIsForecast ? "warning" : "secondary"}
                            className="text-xs"
                          >
                            {yearIsForecast ? "Forecast" : "Published"}
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
                        <div className="flex justify-between gap-4">
                          <Text className="text-muted-foreground">Formula</Text>
                          <Text className="min-w-0 text-right font-mono text-xs font-medium break-words">
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
                            {numChildren} child
                            {numChildren === 1 ? "" : "ren"}
                          </Text>
                        </div>
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle>Location adjustment</CardTitle>
                      <CardDescription>
                        Published Census workbook adjustment factor
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between gap-4">
                          <Text className="text-muted-foreground">Location</Text>
                          <Text className="min-w-0 text-right font-medium leading-snug break-words">
                            {currentLocation.label}
                          </Text>
                        </div>
                        <div className="flex justify-between">
                          <Text className="text-muted-foreground">
                            Location factor
                          </Text>
                          <Text className="font-medium">{geoadj.toFixed(3)}</Text>
                        </div>
                        <div className="flex justify-between">
                          <Text className="text-muted-foreground">
                            Ref. 2A2C threshold
                          </Text>
                          <Text className="font-medium">
                            {fmtCurrency(officialReferenceThreshold)}
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
                      {currentLocation.label}
                    </Text>
                  </div>
                  <DataTable
                    columns={tenureTableColumns}
                    data={tenureComparisonData}
                  />
                </div>

                <Separator />
              </>
            )}

            {/* Methodology explainer */}
            <Card data-testid="methodology-card">
              <CardHeader>
                <CardTitle>How this is calculated</CardTitle>
                <CardDescription>
                  Official Census SPM methodology
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm leading-6">
                <p>
                  Threshold = <code className="font-mono">base[tenure]</code>{" "}
                  × <code className="font-mono">equivalence_scale</code> ×{" "}
                  <code className="font-mono">geoadj[tenure]</code>
                </p>
                <ul className="list-disc space-y-1 pl-6 text-muted-foreground">
                  <li>
                    <strong>Base</strong>: BLS-published FCSUti thresholds
                    for the reference family (2 adults, 2 children), by
                    tenure. National 2024 renter base ={" "}
                    <span className="font-mono">$39,430</span>.
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
                    <strong>GEOADJ</strong>: for Census metro and nonmetro
                    workbook areas, the published per-tenure reference
                    thresholds.
                  </li>
                </ul>
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
                  .
                </p>
              </CardContent>
            </Card>

            {calculatorIsReady && (
              <Card>
                <CardHeader>
                  <CardTitle>Reproduce with Python</CardTitle>
                  <CardDescription>
                    Use the spm-calculator package for reproducible and batch workflows
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-gray-900 p-4 text-xs leading-6 text-white sm:text-sm">
                    <code>{packageSnippet}</code>
                  </pre>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button
                      variant="default"
                      size="sm"
                      onClick={() => window.open(PYPI_URL, "_blank")}
                    >
                      PyPI
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
            )}

            {/* Microdata workflows */}
            <Card data-testid="microdata-card">
              <CardHeader>
                <CardTitle>Person microdata</CardTitle>
                <CardDescription>
                  Reconstruct SPM resource-unit IDs before batch threshold or resource calculations
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(280px,0.8fr)]">
                  <div className="space-y-4">
                    <p className="text-sm leading-6 text-muted-foreground">
                      Native Census <code className="font-mono">SPM_ID</code>{" "}
                      is preserved exactly. When IDs are missing, the Python
                      helper can rebuild resource units from household,
                      family, parent, spouse, cohabiting-partner, foster, and
                      Census SPM assignment fields.
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="secondary">Preserves SPM_ID</Badge>
                      <Badge variant="secondary">Uses PECOHAB</Badge>
                      <Badge variant="secondary">Validates partitions</Badge>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="default"
                        size="sm"
                        onClick={() => window.open(UNIT_ID_DOCS_URL, "_blank")}
                      >
                        Unit ID docs
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => window.open(GITHUB_URL, "_blank")}
                      >
                        Source
                      </Button>
                    </div>
                  </div>
                  <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-gray-900 p-4 text-xs leading-6 text-white sm:text-sm">
                    <code>{microdataSnippet}</code>
                  </pre>
                </div>
              </CardContent>
            </Card>

            {/* Version + data vintage footer */}
            <footer
              data-testid="version-footer"
              className="pt-2 text-xs text-muted-foreground"
            >
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
                {packageVersion ? (
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
        </main>
      </div>
    </DashboardShell>
  );
}
