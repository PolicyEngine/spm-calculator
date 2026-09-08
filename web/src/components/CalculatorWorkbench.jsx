"use client";

import {
  useDeferredValue,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useSearchParams } from "next/navigation";

import {
  DashboardShell,
  Header,
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
  logos,
  Input,
} from "@policyengine/ui-kit";

import { calculateGeoadj } from "@/lib/geoadj";

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

export default function CalculatorWorkbench({ data }) {
  const searchParams = useSearchParams();
  const {
    baseThresholds,
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
  const isEmbedded =
    searchParams.get("embed") === "true" ||
    searchParams.get("embedded") === "true";
  const latestPublishedYear = forecast.latestPublishedYear;
  // Metro rent indices ship as a single Census vintage. Historical years
  // (< earliestMetroYear) are unsupported for metros because back-casting
  // a current rent index to earlier base thresholds does not match any
  // published BLS or Census table. Later threshold years carry the latest
  // bundled rent-index vintage and surface a warning badge.
  const earliestMetroYear =
    metroData?.earliestYear ?? metroDataYear ?? latestPublishedYear;
  const latestMetroYear =
    metroData?.latestYear ?? metroDataYear ?? latestPublishedYear;
  const availableYears = Object.keys(baseThresholds)
    .filter((value) => Number(value) >= earliestMetroYear)
    .sort((left, right) => Number(right) - Number(left));

  const metroEntries = useMemo(
    () =>
      Object.entries(metroAreas).sort(([, left], [, right]) =>
        left.name.localeCompare(right.name),
      ),
    [metroAreas],
  );

  const [year, setYear] = useState(String(latestPublishedYear));
  const methodology = { ...baseMethodology, housingShares: housingSharesByYear[year] ?? baseMethodology.housingShares };
  const [numAdults, setNumAdults] = useState(2);
  const [numChildren, setNumChildren] = useState(2);
  const [tenure, setTenure] = useState("renter");
  const [selectedGeographyId, setSelectedGeographyId] = useState("35620");
  const [locationQuery, setLocationQuery] = useState("");
  const deferredLocationQuery = useDeferredValue(locationQuery);
  const yearNowcast = nowcast[year] ?? null;
  const yearNowcastEvaluation = nowcastEvaluation[year] ?? null;
  const yearIsNowcast = Boolean(yearNowcast);
  const yearIsForecast =
    Number(year) > latestPublishedYear && !yearIsNowcast;
  const ceSurveyWindow = getCeSurveyWindow(year);

  useEffect(() => {
    setSelectedGeographyId((current) =>
      metroAreas[current] ? current : Object.keys(metroAreas)[0] ?? "",
    );
  }, [metroAreas]);

  const filteredMetroEntries = useMemo(() => {
    const query = deferredLocationQuery.trim().toLowerCase();
    if (!query) return metroEntries;
    return metroEntries
      .filter(([code, info]) =>
        `${code} ${info.name}`.toLowerCase().includes(query),
      );
  }, [deferredLocationQuery, metroEntries]);

  const displayedMetroEntries = useMemo(() => {
    const entries = new Map(filteredMetroEntries);
    const selected = metroAreas[selectedGeographyId];
    if (!entries.has(selectedGeographyId) && selected) {
      entries.set(selectedGeographyId, selected);
    }
    return Array.from(entries.entries()).sort(([, left], [, right]) =>
      left.name.localeCompare(right.name),
    );
  }, [filteredMetroEntries, metroAreas, selectedGeographyId]);

  // ── Derived calculations ────────────────────────────────────

  const base = baseThresholds[year][tenure];
  const rawScale = getRawEquivalenceScale(numAdults, numChildren, methodology);
  const compositionValid = Number.isInteger(numAdults) && numAdults >= 1 && Number.isInteger(numChildren) && numChildren >= 0;
  const equivalenceScale =
    rawScale / methodology.equivalenceScale.referenceFamilyRaw;

  const selectedMetroData = metroAreas[selectedGeographyId];
  const currentLocation = selectedMetroData
    ? { id: selectedGeographyId, label: selectedMetroData.name }
    : null;

  // Earlier local years need a matching historical Census rent-index
  // vintage. Later years carry the bundled index with an explicit label.
  const metroYearIsHistorical = Number(year) < earliestMetroYear;
  const metroIndexIsCarried = Number(year) > latestMetroYear;
  const locationError = metroYearIsHistorical
    ? `The bundled Census rent indices start in ${earliestMetroYear}. ` +
      `Choose ${earliestMetroYear} or later.`
    : "";

  function areaAdjustment(areaTenure) {
    if (!selectedMetroData || metroYearIsHistorical) return null;
    return releaseMetadata
      ? calculateGeoadj({
          rentIndex: selectedMetroData.rentIndex,
          housingShare: methodology.housingShares[areaTenure],
        })
      : selectedMetroData.adjustments[areaTenure];
  }

  const geoadj = areaAdjustment(tenure);

  const threshold = geoadj === null || !compositionValid ? null : base * equivalenceScale * geoadj;
  const monthlyThreshold = threshold === null ? null : threshold / 12;
  const nationalReferenceThreshold = base;
  const thresholdVsReference =
    threshold === null
      ? null
      : ((threshold - nationalReferenceThreshold) / nationalReferenceThreshold) * 100;

  const officialReferenceThreshold =
    geoadj === null ? null : baseThresholds[year][tenure] * geoadj;
  const selectedTenureLabel = TENURE_LABELS[tenure] ?? tenure;

  const selectedLocationRentIndex = selectedMetroData?.rentIndex ?? null;

  const tenureComparisonData = TENURE_OPTIONS.map((option) => {
    const adjustment = areaAdjustment(option.value);
    const nationalBase = baseThresholds[year][option.value];
    return {
      tenure: option.label,
      nationalBase,
      locationThreshold: adjustment === null ? null : nationalBase * adjustment,
      adjustment,
    };
  });

  const packageSnippet = !compositionValid ? "# Enter valid classified adult and child counts to generate a calculation." : `from spm_calculator import load_release, SPMUnit

release = load_release(${releaseMetadata ? `expected_sha256="${releaseMetadata.sha256}"` : ""})
result = release.calculate_unit(SPMUnit(
    unit_id="household-1",
    num_adults=${numAdults}, num_children=${numChildren},
    tenure="${tenure}", year=${year},
    geography_kind="metro",
    geography_id="${currentLocation?.id ?? "<select an area>"}",
))
print(result["threshold"])`;

  // ── Location selector options ───────────────────────────────

  const locationSelectOptions = useMemo(
    () => displayedMetroEntries.map(([code, info]) => ({
      value: code,
      label: info.name,
    })),
    [displayedMetroEntries],
  );

  const yearSelectOptions = useMemo(
    () =>
      availableYears.map((y) => ({
        value: y,
        label: `${y} ${
          nowcast[y]
            ? "(nowcast)"
            : Number(y) > latestPublishedYear
              ? "(forecast)"
              : ""
        }`.trim(),
      })),
    [availableYears, latestPublishedYear, nowcast],
  );

  // ── Render ──────────────────────────────────────────────────

  const sidebar = (
    <InputPanel title="Household and geography">
      {!compositionValid && <p role="alert">Enter at least one classified SPM adult and a nonnegative whole number of children. Minor-only units need a separate classification decision.</p>}
      <SidebarSection title="Threshold year">
        <SelectInput
          options={yearSelectOptions}
          value={year}
          onChange={setYear}
        />
      </SidebarSection>

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
          <div>
            <label
              htmlFor="spm-area-search"
              className="mb-1.5 block text-sm font-medium text-muted-foreground"
            >
              Search Census areas
            </label>
            <Input
              id="spm-area-search"
              placeholder="New York, Alabama Nonmetro, 35620..."
              value={locationQuery}
              onChange={(event) => setLocationQuery(event.target.value)}
            />
          </div>
          <SelectInput
            id="spm-census-area"
            aria-label="Census metro/nonmetro area"
            label="Census metro/nonmetro area"
            options={locationSelectOptions}
            value={selectedGeographyId}
            onChange={setSelectedGeographyId}
          />
          <p className="text-xs leading-5 text-muted-foreground">
            Published Census SPM areas: identified metropolitan areas and
            state residual metro/nonmetro groups.
          </p>
        </div>
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
              {latestMetroYear} Census workbook
            </span>
          </div>
          <div className="flex justify-between">
            <span>Housing share</span>
            <span className="font-medium text-foreground">
              {methodology.housingShares[tenure]}
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

  return (
    <DashboardShell>
      <Header
        navItems={[]}
        logoSrc={logos.whiteWordmark}
        logoHref="/"
      />

      <SidebarLayout sidebar={sidebar} sidebarWidth="320px">
        <ResultsPanel>
          <div className="space-y-6">
            {/* Primary result */}
            <div>
              <div className="mb-4 flex flex-wrap items-center gap-2">
                <Title order={2} className="text-xl">
                  {currentLocation?.label ?? "Loading geography"}
                </Title>
                <Badge variant="secondary">
                  {selectedTenureLabel}
                </Badge>
                {yearIsForecast && (
                  <Badge variant="warning">Forecast</Badge>
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
                  value={threshold === null ? "..." : fmtCurrency(threshold)}
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
                  value={geoadj === null ? "..." : geoadj.toFixed(3)}
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
                      <Text className="font-medium">{selectedTenureLabel}</Text>
                    </div>
                    <div className="flex justify-between">
                      <Text className="text-muted-foreground">Base threshold</Text>
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
                            : "Published"}
                      </Badge>
                    </div>
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
                        {describeEquivalenceFormula(numAdults, numChildren, methodology)}
                      </Text>
                    </div>
                    <div className="flex justify-between">
                      <Text className="text-muted-foreground">Normalized scale</Text>
                      <Text className="font-medium">{equivalenceScale.toFixed(3)}</Text>
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
                      <Text className="text-muted-foreground">Location factor</Text>
                      <Text className="font-medium">
                        {geoadj === null ? "..." : geoadj.toFixed(3)}
                      </Text>
                    </div>
                    <div className="flex justify-between">
                      <Text className="text-muted-foreground">Ref. 2A2C threshold</Text>
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
                  National base thresholds adjusted using Census SPM area rent indices
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
                    <strong>Base</strong>: BLS FCSUti thresholds for the
                    reference family (2 adults, 2 children), by tenure,
                    from BLS, estimated over CE quarters {ceSurveyWindow}.
                    The 2019–2024 values use the corrected workbook BLS
                    published July 17, 2026, and 2025 uses the current
                    workbook published August 24, 2026. National 2025
                    renter base ={" "}
                    <span className="font-mono">
                      {fmtCurrency(baseThresholds["2025"].renter)}
                    </span>
                    .
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
                    <strong>GEOADJ</strong>: Census {latestMetroYear} rent indices
                    for identified metro and state residual metro/nonmetro
                    areas. The housing share for the selected tenure adjusts
                    only the housing portion of the national base: renter{" "}
                    {methodology.housingShares.renter}, owner with mortgage{" "}
                    {methodology.housingShares.owner_with_mortgage}, owner
                    without mortgage{" "}
                    {methodology.housingShares.owner_without_mortgage}. The app
                    uses the published Census area definitions; it does not
                    construct separate state, county or district thresholds.
                    Housing shares and rent indices carried into another year
                    are approximations. These calculated thresholds combine
                    the selected national series with the bundled geography
                    vintage and may differ from the original Census workbook
                    amounts.
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
                  Replay this release without credentials or a data download
                </CardDescription>
              </CardHeader>
              <CardContent>
                <pre className="overflow-x-auto rounded-lg bg-gray-900 p-4 text-sm leading-6 text-white">
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

            {/* Version + data vintage footer */}
            <footer
              data-testid="version-footer"
              className="pt-2 text-xs text-muted-foreground"
            >
              {releaseMetadata && (
                <p data-testid="release-provenance">
                  Release {releaseMetadata.id} · information date {releaseMetadata.informationDate}.
                  {" "}Housing shares: {housingShareProvenanceByYear[year]?.reference_year ?? 2024}
                  {housingShareProvenanceByYear[year]?.status === "carried" ? " (carried to the selected year)" : ""}.
                  {" "}SHA-256: <code className="break-all">{releaseMetadata.sha256}</code>
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
      </SidebarLayout>
    </DashboardShell>
  );
}
