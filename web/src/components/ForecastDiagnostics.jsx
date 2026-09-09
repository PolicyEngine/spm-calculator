import { Alert, AlertDescription, AlertTitle } from "@policyengine/ui-kit";

import {
  getForecastValidation,
  getMedianDiagnostic,
  getRealGrowthFits,
} from "@/lib/forecastValidation";

function fmtMape(value) {
  return Number.isFinite(value) && value >= 0
    ? `${value.toFixed(2)}%`
    : "unavailable";
}

function fmtGrowth(value) {
  const sign = value < 0 ? "−" : value > 0 ? "+" : "";
  return `${sign}${Math.abs(value * 100).toFixed(2)}%`;
}

function ComponentWarning({ kind, evaluation }) {
  if (!evaluation.used || (evaluation.complete && !evaluation.underperformed))
    return null;
  const spending = kind === "ce";
  return (
    <Alert
      data-testid={`${kind}-validation-warning`}
      className="border-border bg-muted/40"
    >
      <AlertTitle>
        {spending ? "Spending projection" : "Geographic projection"}
      </AlertTitle>
      <AlertDescription>
        {!evaluation.complete
          ? "This projected component has not been retrospectively validated."
          : spending
            ? "The selected spending scenario did not outperform inflation-only in retrospective tests."
            : "Modeled geographic change did not outperform unchanged indices in retrospective tests."}
      </AlertDescription>
    </Alert>
  );
}

export function ForecastWarnings({
  forecast,
  scenarioId,
  year,
  entry,
  areaId,
}) {
  if (forecast?.method !== "rolling_ce_acs_v1") return null;
  const validation = getForecastValidation(forecast, scenarioId, year);
  const median = getMedianDiagnostic(entry, areaId);
  const counts = median
    ? [
        Number.isFinite(median.unique_records) &&
          `${median.unique_records.toLocaleString("en-US")} unique records`,
        Number.isFinite(median.kish_effective_count) &&
          `Kish effective count ${median.kish_effective_count.toFixed(1)}`,
        Number.isFinite(median.topcodedShare) &&
          `${(median.topcodedShare * 100).toFixed(1)}% topcoded weight in local sample`,
      ].filter(Boolean)
    : [];
  if (
    !median &&
    ![validation.ce, validation.acs].some(
      (value) => value.used && (!value.complete || value.underperformed),
    )
  )
    return null;
  return (
    <div className="mt-3 space-y-2">
      <ComponentWarning kind="ce" evaluation={validation.ce} />
      <ComponentWarning kind="acs" evaluation={validation.acs} />
      {median && (
        <Alert
          data-testid="median-diagnostics-warning"
          className="border-border bg-muted/40"
        >
          <AlertTitle>
            {median.thinSupport ? "Thin rental support" : "Rental topcoding"}
          </AlertTitle>
          <AlertDescription className="space-y-1">
            {median.hasTopcoding && (
              <p>
                {median.indexTopcoding
                  ? "Topcoding may affect a local or national median used by this projected rent index, including its vintage bridge."
                  : median.materialTopcoding
                    ? "Topcoding may affect this median."
                    : "Some rental weight is topcoded."}
              </p>
            )}
            {counts.length > 0 && <p>{counts.join("; ")}.</p>}
            <p>
              Repeated future cohorts do not add independent observations. These
              are research diagnostics, not Census publication rules; the Kish
              count is not a survey-design effective sample size.
            </p>
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}

export function ForecastMethodology({ forecast, scenarioId, year }) {
  if (forecast?.method !== "rolling_ce_acs_v1") return null;
  const { ce, acs } = getForecastValidation(forecast, scenarioId, year);
  const fits = getRealGrowthFits(forecast.realGrowthDiagnostics);
  return (
    <details
      data-testid="forecast-methodology"
      className="rounded-lg border border-border p-3 text-sm"
    >
      <summary className="cursor-pointer font-medium">
        Research validation and fit diagnostics
      </summary>
      <div className="mt-3 space-y-3 text-muted-foreground">
        <p>
          Retrospective, current-vintage validation, conditional on realized
          prices. MAPE is mean absolute percentage error; these tests do not
          measure price forecast accuracy.
        </p>
        <div className="space-y-1">
          <p>
            Overall CE MAPE:{" "}
            {fmtMape(ce.scenario?.mean_absolute_percentage_error)} vs{" "}
            {fmtMape(ce.baseline?.mean_absolute_percentage_error)}{" "}
            inflation-only.
          </p>
          <p>
            Horizon-balanced CE MAPE (1–5 years):{" "}
            {fmtMape(
              ce.scenario?.horizon_balanced_mean_absolute_percentage_error,
            )}{" "}
            vs{" "}
            {fmtMape(
              ce.baseline?.horizon_balanced_mean_absolute_percentage_error,
            )}
            .
          </p>
          {ce.used && (
            <p>
              {ce.horizon}-year CE MAPE:{" "}
              {fmtMape(ce.horizonScenario?.mean_absolute_percentage_error)} vs{" "}
              {fmtMape(
                ce.selectedHorizon?.baseline?.mean_absolute_percentage_error,
              )}{" "}
              (
              {Number.isInteger(ce.selectedHorizon?.fold_count)
                ? ce.selectedHorizon.fold_count
                : "unknown"}{" "}
              folds).
            </p>
          )}
          <p>
            ACS MAPE: {fmtMape(acs.scenario?.mean_absolute_percentage_error)} vs{" "}
            {fmtMape(acs.baseline?.mean_absolute_percentage_error)} unchanged
            indices.
          </p>
          {!ce.complete && <p>CE validation incomplete.</p>}
          {!acs.complete && <p>ACS validation incomplete.</p>}
        </div>
        <p>
          Shorter horizons have more folds and more weight in the overall CE
          score. There are few long-horizon folds; the balanced score weights
          horizons 1–5 equally. Horizon 6 is supplemental. Required coverage is
          21 CE folds / 63 fold-tenure observations per scenario and 341 ACS
          areas.
        </p>
        <p>
          The CE trend uses 0.5 shrinkage and is predeclared independently of
          holdout results. Unshrunk fits are diagnostic sensitivities only; zero
          real growth is a separate scored scenario.
        </p>
        {fits.length > 0 && (
          <div data-testid="real-growth-fits" className="space-y-1">
            {fits.map((fit, index) => (
              <p key={`${fit.label}-${index}`}>
                {fit.label} fit: {fmtGrowth(fit.realGrowthRate)}
                {fit.n ? ` (${fit.n} annual blocks)` : ""}
                {fit.olsSlopeStandardError !== undefined
                  ? `; OLS slope SE ${fit.olsSlopeStandardError.toFixed(4)}`
                  : ""}
                .
              </p>
            ))}
            <p>
              OLS fit diagnostics are not survey-design uncertainty or forecast
              intervals. Repeated interviews and serial dependence remain
              unmodeled.
            </p>
          </div>
        )}
      </div>
    </details>
  );
}
