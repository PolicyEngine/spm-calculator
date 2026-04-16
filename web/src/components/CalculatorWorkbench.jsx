"use client";

import {
  startTransition,
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

import {
  STATE_SELECTOR_OPTIONS,
  calculateCustomGeoadj,
  getAcsYearForThresholdYear,
  loadCountyRentOptions,
  loadDistrictRentOptions,
  loadStateRentOptions,
} from "@/lib/acsLookup";

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

const GEOGRAPHY_OPTIONS = [
  { value: "nation", label: "National average" },
  { value: "metro_area", label: "Metro area" },
  { value: "state", label: "State" },
  { value: "county", label: "County" },
  { value: "congressional_district", label: "Congressional district" },
];

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
  if (adults === 0 && children === 0) return 0;

  if (children > 0) {
    if (adults <= 1) {
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

  if (adults <= 1) return 1;
  if (adults === 2) return methodology.equivalenceScale.twoAdultNoChild;
  return adults ** methodology.equivalenceScale.economiesOfScale;
}

function describeEquivalenceFormula(adults, children) {
  if (adults === 0 && children === 0) return "0";
  if (children > 0) {
    if (adults <= 1) {
      return `(1 + 0.8 + 0.5 * (${children} - 1))^0.7`;
    }
    return `(${adults} + 0.5 * ${children})^0.7`;
  }
  if (adults <= 1) return "1.0";
  if (adults === 2) return "1.41";
  return `${adults}^0.7`;
}

function getCeSurveyYears(thresholdYear) {
  const endYear = Number(thresholdYear) - 2;
  return Array.from({ length: 5 }, (_, index) => endYear - 4 + index);
}

export default function CalculatorWorkbench({ data }) {
  const searchParams = useSearchParams();
  const { baseThresholds, methodology, forecast, metroAreas } = data;
  const isEmbedded =
    searchParams.get("embed") === "true" ||
    searchParams.get("embedded") === "true";
  const latestPublishedYear = forecast.latestPublishedYear;
  const availableYears = Object.keys(baseThresholds).sort(
    (left, right) => Number(right) - Number(left),
  );

  const metroEntries = useMemo(
    () =>
      Object.entries(metroAreas).sort(([, left], [, right]) =>
        left.name.localeCompare(right.name),
      ),
    [metroAreas],
  );

  const [year, setYear] = useState(String(latestPublishedYear));
  const [numAdults, setNumAdults] = useState(2);
  const [numChildren, setNumChildren] = useState(2);
  const [tenure, setTenure] = useState("renter");
  const [geographyType, setGeographyType] = useState("metro_area");
  const [selectedStateFips, setSelectedStateFips] = useState("06");
  const [selectedGeographyId, setSelectedGeographyId] = useState("35620");
  const [locationQuery, setLocationQuery] = useState("");
  const [acsLookup, setAcsLookup] = useState({
    status: "idle",
    error: "",
    nationalMedianRent: null,
    options: [],
  });

  const deferredLocationQuery = useDeferredValue(locationQuery);
  const acsYear = useMemo(
    () => getAcsYearForThresholdYear(Number(year)),
    [year],
  );
  const yearIsForecast = Number(year) > latestPublishedYear;
  const ceSurveyYears = getCeSurveyYears(year);

  useEffect(() => {
    if (geographyType === "metro_area") {
      setSelectedGeographyId((current) =>
        metroAreas[current] ? current : "35620",
      );
      return;
    }

    if (geographyType === "nation") {
      setSelectedGeographyId("US");
      return;
    }

    let cancelled = false;

    async function loadLookup() {
      setAcsLookup({
        status: "loading",
        error: "",
        nationalMedianRent: null,
        options: [],
      });

      try {
        let nextLookup;
        if (geographyType === "state") {
          nextLookup = await loadStateRentOptions(acsYear);
        } else if (geographyType === "county") {
          nextLookup = await loadCountyRentOptions(acsYear, selectedStateFips);
        } else {
          nextLookup = await loadDistrictRentOptions(acsYear, selectedStateFips);
        }

        if (cancelled) return;

        setAcsLookup({
          status: "ready",
          error: "",
          nationalMedianRent: nextLookup.nationalMedianRent,
          options: nextLookup.options,
        });

        setSelectedGeographyId((current) => {
          const preferredId =
            geographyType === "state" ? selectedStateFips : nextLookup.options[0]?.id;
          const hasCurrent = nextLookup.options.some(
            (option) => option.id === current,
          );
          if (hasCurrent) return current;
          if (preferredId) {
            const hasPreferred = nextLookup.options.some(
              (option) => option.id === preferredId,
            );
            if (hasPreferred) return preferredId;
          }
          return nextLookup.options[0]?.id ?? "";
        });
      } catch (error) {
        if (cancelled) return;
        setAcsLookup({
          status: "error",
          error:
            error instanceof Error
              ? error.message
              : "Unable to load Census geography data.",
          nationalMedianRent: null,
          options: [],
        });
      }
    }

    loadLookup();
    return () => {
      cancelled = true;
    };
  }, [acsYear, geographyType, metroAreas, selectedStateFips]);

  const filteredMetroEntries = useMemo(() => {
    const query = deferredLocationQuery.trim().toLowerCase();
    if (!query) return metroEntries.slice(0, 150);
    return metroEntries
      .filter(([code, info]) =>
        `${code} ${info.name}`.toLowerCase().includes(query),
      )
      .slice(0, 150);
  }, [deferredLocationQuery, metroEntries]);

  const filteredAcsOptions = useMemo(() => {
    const query = deferredLocationQuery.trim().toLowerCase();
    if (!query) return acsLookup.options.slice(0, 150);
    return acsLookup.options
      .filter((option) =>
        `${option.id} ${option.label} ${option.shortLabel ?? ""}`
          .toLowerCase()
          .includes(query),
      )
      .slice(0, 150);
  }, [acsLookup.options, deferredLocationQuery]);

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

  const displayedAcsOptions = useMemo(() => {
    const entries = new Map(filteredAcsOptions.map((option) => [option.id, option]));
    const selected = acsLookup.options.find(
      (option) => option.id === selectedGeographyId,
    );
    if (selected && !entries.has(selectedGeographyId)) {
      entries.set(selectedGeographyId, selected);
    }
    return Array.from(entries.values()).sort((left, right) =>
      left.label.localeCompare(right.label),
    );
  }, [acsLookup.options, filteredAcsOptions, selectedGeographyId]);

  // ── Derived calculations ────────────────────────────────────

  const base = baseThresholds[year][tenure];
  const rawScale = getRawEquivalenceScale(numAdults, numChildren, methodology);
  const equivalenceScale =
    rawScale / methodology.equivalenceScale.referenceFamilyRaw;

  const selectedMetroData =
    geographyType === "metro_area" ? metroAreas[selectedGeographyId] : null;
  const selectedCustomLocation =
    geographyType === "state" ||
    geographyType === "county" ||
    geographyType === "congressional_district"
      ? acsLookup.options.find((option) => option.id === selectedGeographyId)
      : null;

  const currentLocation = useMemo(() => {
    if (geographyType === "nation") {
      return { id: "US", label: "United States", shortLabel: "Nation" };
    }
    if (selectedMetroData) {
      return {
        id: selectedGeographyId,
        label: selectedMetroData.name,
        shortLabel: "Metro area",
      };
    }
    if (selectedCustomLocation) {
      return {
        id: selectedCustomLocation.id,
        label: selectedCustomLocation.label,
        shortLabel:
          GEOGRAPHY_OPTIONS.find((option) => option.value === geographyType)
            ?.label ?? geographyType,
      };
    }
    return null;
  }, [geographyType, selectedCustomLocation, selectedGeographyId, selectedMetroData]);

  const geoadj = useMemo(() => {
    if (geographyType === "nation") return 1;
    if (selectedMetroData) return selectedMetroData.adjustments[tenure];
    if (selectedCustomLocation && acsLookup.nationalMedianRent) {
      return calculateCustomGeoadj({
        localMedianRent: selectedCustomLocation.medianRent,
        nationalMedianRent: acsLookup.nationalMedianRent,
        tenure,
        housingShares: methodology.housingShares,
      });
    }
    return null;
  }, [
    acsLookup.nationalMedianRent,
    geographyType,
    methodology.housingShares,
    selectedCustomLocation,
    selectedMetroData,
    tenure,
  ]);

  const threshold = geoadj === null ? null : base * equivalenceScale * geoadj;
  const monthlyThreshold = threshold === null ? null : threshold / 12;
  const nationalReferenceThreshold = base;
  const thresholdVsReference =
    threshold === null
      ? null
      : ((threshold - nationalReferenceThreshold) / nationalReferenceThreshold) * 100;

  const officialReferenceThreshold =
    geoadj === null ? null : baseThresholds[year][tenure] * geoadj;
  const selectedTenureLabel = TENURE_LABELS[tenure] ?? tenure;

  const selectedLocationRentIndex =
    selectedMetroData?.rentIndex ??
    (selectedCustomLocation && acsLookup.nationalMedianRent
      ? selectedCustomLocation.medianRent / acsLookup.nationalMedianRent
      : null);

  const isLocationLoading =
    geographyType !== "metro_area" &&
    geographyType !== "nation" &&
    acsLookup.status === "loading";
  const locationError = acsLookup.status === "error" ? acsLookup.error : "";

  const tenureComparisonData = TENURE_OPTIONS.map((option) => {
    let adjustment = 1;
    let isReady = geographyType === "nation" || Boolean(selectedMetroData);

    if (selectedMetroData) {
      adjustment = selectedMetroData.adjustments[option.value];
    } else if (selectedCustomLocation && acsLookup.nationalMedianRent) {
      adjustment = calculateCustomGeoadj({
        localMedianRent: selectedCustomLocation.medianRent,
        nationalMedianRent: acsLookup.nationalMedianRent,
        tenure: option.value,
        housingShares: methodology.housingShares,
      });
      isReady = true;
    }

    const nationalBase = baseThresholds[year][option.value];
    return {
      tenure: option.label,
      nationalBase,
      locationThreshold: isReady ? nationalBase * adjustment : null,
      adjustment: isReady ? adjustment : null,
    };
  });

  const packageSnippet = `from spm_calculator import SPMCalculator

calc = SPMCalculator(year=${year})
threshold = calc.calculate_threshold(
    num_adults=${numAdults},
    num_children=${numChildren},
    tenure="${tenure}",
    geography_type="${geographyType}",
    geography_id="${currentLocation?.id ?? "<loading>"}"
)

print(f"SPM threshold: \${threshold:,.0f}")`;

  // ── Location selector options ───────────────────────────────

  const locationSelectOptions = useMemo(() => {
    if (geographyType === "metro_area") {
      return displayedMetroEntries.map(([code, info]) => ({
        value: code,
        label: info.name,
      }));
    }
    return displayedAcsOptions.map((option) => ({
      value: option.id,
      label: option.label,
    }));
  }, [geographyType, displayedMetroEntries, displayedAcsOptions]);

  const stateSelectOptions = useMemo(
    () =>
      STATE_SELECTOR_OPTIONS.map((option) => ({
        value: option.fips,
        label: option.name,
      })),
    [],
  );

  const yearSelectOptions = useMemo(
    () =>
      availableYears.map((y) => ({
        value: y,
        label: `${y} ${Number(y) > latestPublishedYear ? "(forecast)" : ""}`.trim(),
      })),
    [availableYears, latestPublishedYear],
  );

  // ── Render ──────────────────────────────────────────────────

  const sidebar = (
    <InputPanel title="Household and geography">
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
            value={numAdults}
            onChange={setNumAdults}
            min={0}
            max={12}
          />
          <NumberInput
            label="Children"
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
        <SelectInput
          label="Geography type"
          options={GEOGRAPHY_OPTIONS}
          value={geographyType}
          onChange={(value) => {
            startTransition(() => {
              setGeographyType(value);
              setLocationQuery("");
            });
          }}
        />

        {(geographyType === "county" ||
          geographyType === "congressional_district") && (
          <div className="mt-3">
            <SelectInput
              label="State"
              options={stateSelectOptions}
              value={selectedStateFips}
              onChange={(value) => {
                startTransition(() => {
                  setSelectedStateFips(value);
                  setLocationQuery("");
                });
              }}
            />
          </div>
        )}

        {geographyType !== "nation" && (
          <div className="mt-3 space-y-3">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-muted-foreground">
                Search
              </label>
              <Input
                placeholder={
                  geographyType === "metro_area"
                    ? "New York, San Jose, 35620..."
                    : geographyType === "state"
                      ? "California, Texas..."
                      : geographyType === "county"
                        ? "Los Angeles, Cook..."
                        : "CA-12, NY-01..."
                }
                value={locationQuery}
                onChange={(event) => setLocationQuery(event.target.value)}
              />
            </div>

            <SelectInput
              label={
                geographyType === "metro_area"
                  ? "Metro area"
                  : geographyType === "state"
                    ? "State"
                    : geographyType === "county"
                      ? "County"
                      : "District"
              }
              options={locationSelectOptions}
              value={selectedGeographyId}
              onChange={(value) => {
                setSelectedGeographyId(value);
                if (geographyType === "state") {
                  setSelectedStateFips(value);
                }
              }}
              disabled={isLocationLoading || Boolean(locationError)}
            />
          </div>
        )}
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
              {geographyType === "metro_area"
                ? "2024 Census workbook"
                : geographyType === "nation"
                  ? "National baseline"
                  : `ACS ${acsYear}`}
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
          {geographyType !== "metro_area" &&
            geographyType !== "nation" &&
            selectedCustomLocation && (
              <div className="flex justify-between">
                <span>Median 2BR rent</span>
                <span className="font-medium text-foreground">
                  {fmtCurrency(selectedCustomLocation.medianRent)}
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
        variant="dark"
        logo={
          <img
            src={logos.whiteWordmark}
            alt="PolicyEngine"
            className="h-5"
          />
        }
        actions={
          <span className="text-sm font-semibold text-white/90">
            SPM threshold calculator
          </span>
        }
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
                      <Badge variant={yearIsForecast ? "warning" : "secondary"} className="text-xs">
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
                    <div className="flex justify-between">
                      <Text className="text-muted-foreground">Formula</Text>
                      <Text className="font-mono text-xs font-medium">
                        {describeEquivalenceFormula(numAdults, numChildren)}
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
                    {geographyType === "metro_area"
                      ? "Published metro adjustment factor"
                      : geographyType === "nation"
                        ? "No additional geography factor"
                        : `ACS ${acsYear} rent-based adjustment`}
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

            {/* Python package */}
            <Card>
              <CardHeader>
                <CardTitle>Reproduce with Python</CardTitle>
                <CardDescription>
                  Use the spm-calculator package for PUMAs, tracts, and batch workflows
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
          </div>
        </ResultsPanel>
      </SidebarLayout>
    </DashboardShell>
  );
}
