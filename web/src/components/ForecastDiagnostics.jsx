import { Alert, AlertDescription, AlertTitle } from "@policyengine/ui-kit";

import {
  getForecastValidation,
  getHistoricalSeriesBreaks,
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

function horizonRange(horizons) {
  if (horizons.length === 1) return `${horizons[0]} year`;
  if (
    horizons.some(
      (value, index) => index > 0 && value !== horizons[index - 1] + 1,
    )
  )
    return `${horizons.join(", ")} years`;
  return `${horizons[0]}–${horizons.at(-1)} years`;
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
      <AlertDescription className="space-y-1">
        {evaluation.unsupportedArea ? (
          <p>
            This unpublished area has no published Census anchor and no
            area-matched retrospective validation. The geographic backtest
            covers published, anchored areas.
          </p>
        ) : evaluation.unsupportedHorizon ? (
          <p>
            The selected {evaluation.horizon}-year{" "}
            {spending ? "spending" : "geographic"} horizon has no retrospective
            backtest support. Available {spending ? "CE" : "ACS"} tests cover{" "}
            {spending
              ? horizonRange(evaluation.supportedHorizons)
              : `${evaluation.testedHorizon} year`}
            .
          </p>
        ) : !evaluation.complete ? (
          <p>
            This projected component has not been retrospectively validated.
          </p>
        ) : null}
        {evaluation.underperformed && (
          <p>
            {spending
              ? "The selected spending scenario did not outperform inflation-only in retrospective tests."
              : "Modeled geographic change did not outperform unchanged indices in retrospective tests."}
          </p>
        )}
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
  const validation = getForecastValidation(
    forecast,
    scenarioId,
    year,
    entry,
    areaId,
  );
  const median = getMedianDiagnostic(entry, areaId);
  const seriesBreaks = getHistoricalSeriesBreaks(
    forecast,
    scenarioId,
    areaId,
    entry,
  );
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
    seriesBreaks.length === 0 &&
    ![validation.ce, validation.acs].some(
      (value) => value.used && (!value.complete || value.underperformed),
    )
  )
    return null;
  return (
    <div className="mt-3 space-y-2">
      {seriesBreaks.length > 0 && (
        <Alert
          data-testid="historical-series-break-warning"
          className="border-border bg-muted/40"
        >
          <AlertTitle>Historical geography series break</AlertTitle>
          <AlertDescription className="space-y-1">
            {seriesBreaks.map((disclosure, index) => (
              <p key={index}>
                {disclosure.from_year}→{disclosure.to_year}:{" "}
                {disclosure.interpretation}
              </p>
            ))}
          </AlertDescription>
        </Alert>
      )}
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

export function ForecastMethodology({
  forecast,
  scenarioId,
  year,
  entry,
  areaId,
}) {
  if (!forecast) return null;
  const { ce, acs } = getForecastValidation(
    forecast,
    scenarioId,
    year,
    entry,
    areaId,
  );
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
          {ce.used && !ce.unsupportedHorizon && (
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
          {ce.unsupportedHorizon && (
            <p>
              The selected {ce.horizon}-year spending horizon has no
              retrospective backtest support. CE scores cover{" "}
              {horizonRange(ce.supportedHorizons)}.
            </p>
          )}
          <p>
            ACS MAPE: {fmtMape(acs.scenario?.mean_absolute_percentage_error)} vs{" "}
            {fmtMape(acs.baseline?.mean_absolute_percentage_error)} unchanged
            indices.
          </p>
          {!ce.researchComplete && <p>CE validation incomplete.</p>}
          {!acs.researchComplete && <p>ACS validation incomplete.</p>}
          {acs.researchComplete && (
            <p>
              The ACS backtest covers {acs.scenario.origin_spm_year}–
              {acs.scenario.target_spm_year}
              {Number.isInteger(acs.scenario.area_count)
                ? ` across ${acs.scenario.area_count} published areas`
                : ""}
              .
              {acs.unsupportedArea
                ? " It does not validate this unpublished, unanchored area."
                : acs.unsupportedHorizon
                  ? ` It does not validate the selected ${acs.horizon}-year geographic horizon.`
                  : ""}
            </p>
          )}
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
        <p>
          Future estimates are conditional rolling CE and ACS projections. CBO
          annual CPI ratios are applied uniformly to spending components and
          rent growth as a modeling assumption, not a CBO rent forecast.
        </p>
        <p data-testid="rent-index-stabilization">
          Under uniform national rent growth, relative rent indices stabilize
          from 2029, once the five-year window contains only the 2024 donor
          distribution and its projected copies. The whole-threshold geography
          factor can still change as the housing share changes.
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
