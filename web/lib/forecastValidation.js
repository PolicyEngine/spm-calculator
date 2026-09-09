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
 * Artifact generation owns checking all 341 ACS areas and 21 CE folds/63 tenure
 * observations. The UI additionally requires valid scores for the chosen scenario
 * and horizon, even if an inconsistent artifact claims validation is complete.
 */
export function getForecastValidation(forecast, scenarioId, year) {
  const ce = forecast?.validation?.ce;
  const scenario = ce?.scenarios?.[scenarioId];
  const baseline = ce?.baseline;
  const horizon = Number(year) - forecast?.baseYear;
  const usesCe = Number(year) >= 2026;
  const selectedHorizon = ce?.by_horizon?.[String(horizon)];
  const horizonScenario = selectedHorizon?.scenarios?.[scenarioId];
  const ceComplete =
    completed(ce) &&
    ce.metric === MAPE &&
    hasComparison(scenario, baseline) &&
    hasComparison(
      scenario,
      baseline,
      BALANCED_MAPE,
      "beats_horizon_balanced_baseline",
    ) &&
    (!usesCe ||
      (Number.isInteger(forecast?.baseYear) &&
        Number.isInteger(horizon) &&
        horizon > 0 &&
        Number.isInteger(selectedHorizon?.fold_count) &&
        selectedHorizon.fold_count > 0 &&
        hasComparison(horizonScenario, selectedHorizon?.baseline)));
  const ceUnderperformed =
    ceComplete &&
    (!outperforms(scenario, baseline) ||
      !outperforms(
        scenario,
        baseline,
        BALANCED_MAPE,
        "beats_horizon_balanced_baseline",
      ) ||
      (usesCe && !outperforms(horizonScenario, selectedHorizon.baseline)));

  const acs = forecast?.validation?.acs;
  const acsBaseline = { [MAPE]: acs?.baseline_mean_absolute_percentage_error };
  const acsComplete = completed(acs) && hasComparison(acs, acsBaseline);

  return {
    ce: {
      used: usesCe,
      complete: ceComplete,
      underperformed: ceUnderperformed,
      scenario,
      baseline,
      horizon,
      selectedHorizon,
      horizonScenario,
    },
    acs: {
      used: Number(year) >= 2025,
      complete: acsComplete,
      underperformed: acsComplete && !outperforms(acs, acsBaseline),
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
  if (entry?.geography_status === "published_anchor") return null;
  const diagnostic = entry?.median_diagnostics?.[areaId];
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
