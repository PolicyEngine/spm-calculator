const MAPE = "mean_absolute_percentage_error";
const BALANCED_MAPE = "horizon_balanced_mean_absolute_percentage_error";

function isErrorMetric(value) {
  return Number.isFinite(value) && value >= 0;
}

function hasComparison(
  candidate,
  baseline,
  metric = MAPE,
  flag = "beats_baseline",
) {
  return (
    isErrorMetric(candidate?.[metric]) &&
    isErrorMetric(baseline?.[metric]) &&
    typeof candidate?.[flag] === "boolean"
  );
}

function outperforms(
  candidate,
  baseline,
  metric = MAPE,
  flag = "beats_baseline",
) {
  return candidate[flag] && candidate[metric] < baseline[metric];
}

function completed(evaluation) {
  return evaluation?.status === "complete" && evaluation?.unvalidated === false;
}

/**
 * Consume normalized export metrics defensively. MAPE values already use
 * percent units; annual real-spending rates elsewhere in the export are fractions.
 * A completed research evaluation does not validate every displayed projection.
 * Require scores for the selected spending horizon and apply the geographic
 * evaluation only to its tested horizon and published, anchored area coverage.
 */
export function getForecastValidation(
  forecast,
  scenarioId,
  year,
  entry,
  areaId,
) {
  const selectedEntry =
    entry ?? forecast?.scenarios?.[scenarioId]?.years?.[String(year)];
  const area = selectedEntry?.geography_by_area?.[areaId];
  const ce = forecast?.validation?.ce;
  const scenario = ce?.scenarios?.[scenarioId];
  const baseline = ce?.baseline;
  const horizon = Number(year) - forecast?.baseYear;
  const usesCe = selectedEntry?.national_status === "forecast";
  const selectedHorizon = ce?.by_horizon?.[String(horizon)];
  const horizonScenario = selectedHorizon?.scenarios?.[scenarioId];
  const supportedHorizons = Object.entries(ce?.by_horizon ?? {})
    .filter(
      ([key, value]) =>
        Number.isInteger(Number(key)) &&
        Number(key) > 0 &&
        Number.isInteger(value?.fold_count) &&
        value.fold_count > 0,
    )
    .map(([key]) => Number(key))
    .sort((a, b) => a - b);
  const ceResearchComplete =
    completed(ce) &&
    ce.metric === MAPE &&
    hasComparison(scenario, baseline) &&
    hasComparison(
      scenario,
      baseline,
      BALANCED_MAPE,
      "beats_horizon_balanced_baseline",
    );
  const ceComplete =
    ceResearchComplete &&
    (!usesCe ||
      (Number.isInteger(forecast?.baseYear) &&
        Number.isInteger(horizon) &&
        horizon > 0 &&
        Number.isInteger(selectedHorizon?.fold_count) &&
        selectedHorizon.fold_count > 0 &&
        hasComparison(horizonScenario, selectedHorizon?.baseline)));
  const ceUnderperformed =
    ceResearchComplete &&
    (!outperforms(scenario, baseline) ||
      !outperforms(
        scenario,
        baseline,
        BALANCED_MAPE,
        "beats_horizon_balanced_baseline",
      ) ||
      (usesCe &&
        hasComparison(horizonScenario, selectedHorizon?.baseline) &&
        !outperforms(horizonScenario, selectedHorizon.baseline)));
  const ceUnsupportedHorizon =
    usesCe &&
    Number.isInteger(horizon) &&
    horizon > 0 &&
    supportedHorizons.length > 0 &&
    !supportedHorizons.includes(horizon);

  const acs = forecast?.validation?.acs;
  const acsBaseline = { [MAPE]: acs?.baseline_mean_absolute_percentage_error };
  const usesAcs = ["modeled", "modeled_unanchored"].includes(area?.status);
  const acsHorizon = Number(year) - forecast?.geographyAnchorYear;
  const testedAcsHorizon = acs?.target_spm_year - acs?.origin_spm_year;
  const acsResearchComplete =
    completed(acs) &&
    hasComparison(acs, acsBaseline) &&
    Number.isInteger(acs?.origin_spm_year) &&
    Number.isInteger(acs?.target_spm_year) &&
    testedAcsHorizon > 0 &&
    Number.isInteger(acs?.area_count) &&
    acs.area_count > 0;
  const acsHorizonSupported =
    Number.isInteger(testedAcsHorizon) &&
    testedAcsHorizon > 0 &&
    acsHorizon === testedAcsHorizon;
  const acsAreaSupported =
    area?.official_published_area === true &&
    area?.anchor_status === "published_anchor";
  const acsComplete =
    acsResearchComplete &&
    (!usesAcs || (acsHorizonSupported && acsAreaSupported));

  return {
    ce: {
      used: usesCe,
      complete: ceComplete,
      researchComplete: ceResearchComplete,
      underperformed: ceUnderperformed,
      unsupportedHorizon: ceUnsupportedHorizon,
      supportedHorizons,
      scenario,
      baseline,
      horizon,
      selectedHorizon,
      horizonScenario,
    },
    acs: {
      used: usesAcs,
      complete: acsComplete,
      researchComplete: acsResearchComplete,
      underperformed: acsResearchComplete && !outperforms(acs, acsBaseline),
      unsupportedArea:
        usesAcs &&
        (area?.official_published_area === false ||
          area?.anchor_status === "modeled_unanchored"),
      unsupportedHorizon:
        usesAcs &&
        Number.isInteger(acsHorizon) &&
        Number.isInteger(testedAcsHorizon) &&
        testedAcsHorizon > 0 &&
        !acsHorizonSupported,
      horizon: acsHorizon,
      testedHorizon: testedAcsHorizon,
      scenario: acs,
      baseline: acsBaseline,
    },
  };
}

/**
 * Preferred optional shape: realGrowthDiagnostics.fits =
 * [{ label, realGrowthRate, olsSlopeStandardError?, n? }]. Rates are fractions;
 * OLS SE is in annual log-slope units. Snake-case equivalents and keyed fits are
 * accepted for exporters that preserve their scientific module's naming.
 */
export function getRealGrowthFits(diagnostics) {
  if (!diagnostics || typeof diagnostics !== "object") return [];
  const source = diagnostics.fits ?? diagnostics;
  const entries = Array.isArray(source)
    ? source.map((fit, index) => [String(index), fit])
    : Object.entries(source);
  const labels = {
    five_year: "5-year trend",
    five_year_trend: "5-year trend",
    ten_year: "10-year trend",
    ten_year_trend: "10-year trend",
    pandemic_excluded: "Pandemic excluded",
  };
  return entries.flatMap(([key, fit]) => {
    if (!fit || typeof fit !== "object") return [];
    const slope = fit.annual_log_slope ?? fit.annualLogSlope;
    const rate =
      fit.realGrowthRate ??
      fit.real_growth_rate ??
      fit.annual_growth_rate ??
      (Number.isFinite(slope) ? Math.expm1(slope) : undefined);
    if (!Number.isFinite(rate)) return [];
    const label = fit.label ?? labels[key] ?? key.replaceAll("_", " ");
    const standardError =
      fit.olsSlopeStandardError ??
      fit.ols_slope_standard_error ??
      fit.slope_standard_error;
    return [
      {
        label: typeof label === "string" ? label : key,
        realGrowthRate: rate,
        olsSlopeStandardError: isErrorMetric(standardError)
          ? standardError
          : undefined,
        n: Number.isInteger(fit.n) && fit.n > 0 ? fit.n : undefined,
      },
    ];
  });
}

export function getMedianDiagnostic(entry, areaId) {
  const area = entry?.geography_by_area?.[areaId];
  if (!area || area.status === "published_anchor") return null;
  const diagnostic = area.diagnostics ?? entry?.median_diagnostics?.[areaId];
  if (!diagnostic) return null;
  const materialTopcoding = [
    diagnostic.material_topcoding,
    diagnostic.material_topcoding_flag,
    diagnostic.materialTopcoding,
    diagnostic.materialTopcodingFlag,
    diagnostic.topcoding_material,
    diagnostic.topcoding_material_flag,
  ].some((flag) => flag === true);
  const topcodedShare = diagnostic.topcoded_weight_share;
  const validShare =
    Number.isFinite(topcodedShare) && topcodedShare >= 0 && topcodedShare <= 1;
  // The required contract may only provide the share. Report any nonzero share
  // factually rather than inventing a materiality cutoff or censored median.
  const indexTopcoding = diagnostic.rent_index_topcode_warning === true;
  const hasTopcoding =
    indexTopcoding || materialTopcoding || (validShare && topcodedShare > 0);
  const thinSupport = diagnostic.thin_support === true;
  return thinSupport || hasTopcoding
    ? {
        ...diagnostic,
        thinSupport,
        materialTopcoding,
        hasTopcoding,
        indexTopcoding,
        topcodedShare: validShare ? topcodedShare : undefined,
      }
    : null;
}

/**
 * A selected area's comparison includes every available year, so retain source
 * breaks recorded on historical entries even when a later year is selected.
 * Disclosure text and transition values come directly from the audit artifact.
 */
export function getHistoricalSeriesBreaks(forecast, scenarioId, areaId, entry) {
  const entries = [
    entry,
    ...Object.values(forecast?.scenarios?.[scenarioId]?.years ?? {}),
  ];
  const unique = new Map();
  for (const candidate of entries) {
    const disclosures = candidate?.geography_by_area?.[areaId]?.series_breaks;
    if (!Array.isArray(disclosures)) continue;
    for (const disclosure of disclosures) {
      if (
        !Number.isInteger(disclosure?.from_year) ||
        !Number.isInteger(disclosure?.to_year) ||
        typeof disclosure?.interpretation !== "string" ||
        !disclosure.interpretation.trim()
      )
        continue;
      const key = JSON.stringify([
        disclosure.kind,
        disclosure.from_year,
        disclosure.to_year,
        disclosure.from_area_id,
        disclosure.to_area_id,
      ]);
      unique.set(key, disclosure);
    }
  }
  return [...unique.values()];
}
