"""Replicate-weight standard errors for the CE threshold replication.

The Consumer Expenditure Survey (CE) estimates sampling error by balanced
repeated replication (BRR). BLS divides the sampled primary sampling units
into 43 strata, splits the consumer units within each stratum at random
into two half samples, and forms 44 replicate weights from a 44 x 44
Hadamard matrix (Handbook of Methods,
https://www.bls.gov/opub/hom/cex/calculation.htm). Through 2024 CE data,
each public-use replicate weight is positive for about half the records
and blank for the rest, and users read the blanks as zero. From 2025 CE
data, BLS uses Fay's method, which multiplies the variance by four
(https://www.bls.gov/cex/ce-standarderrors.htm). With replicate estimates
``theta_r`` and the full-sample estimate ``theta``::

    V = sum_r (theta_r - theta) ** 2 / (R * (1 - k) ** 2)

where ``R = 44`` and Fay's coefficient ``k`` is 0 for standard BRR and 0.5
for the CE's Fay weights. The interview files the replication reads,
2014Q2 through 2025Q1, carry standard BRR weights, and
:func:`check_standard_brr` verifies that record by record.

:func:`replicate_estimates` reruns the whole threshold estimator under each
replicate weight, with and without the in-kind stage: the sample (records
whose replicate weight is zero drop out), the CPI component weights that
the package deflator derives from CE spending, normalization, the
47th-53rd percentile band and the band means. Each implicate's imputed
amounts stay as the full-sample imputation drew them.

:func:`combine_implicates` pools each implicate's replicate variance with
the variance between implicates by Rubin's rules (Rubin 1987, Multiple
Imputation for Nonresponse in Surveys), with Barnard and Rubin's (1999,
Biometrika 86: 948-955) degrees of freedom and the CE's 43 strata as the
complete-data degrees of freedom.

Invariants, tested in ``tests/test_ce_replicates.py``:

- a replicate variance is nonnegative; it is zero when every replicate
  equals the full sample; shifting every value by one constant or
  reordering the replicates leaves it unchanged; and Fay's coefficient
  ``k`` scales it by ``1 / (1 - k) ** 2``;
- the total variance is at least the mean within-implicate variance and
  at least ``(1 + 1/M)`` times the between-implicate variance, the
  fraction of missing information lies in [0, 1], and the degrees of
  freedom never exceed the complete-data value;
- when every replicate weight equals the full-sample weight, every
  replicate reproduces the full-sample thresholds exactly;
- each replicate's band means reproduce its thresholds;
- results are deterministic.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from spm_calculator.ce_bls_shares import BandComponents, band_components
from spm_calculator.ce_inkind_stage import add_in_kind
from spm_calculator.ce_threshold import (
    MEDIAN_SHARE,
    TENURES,
    construct_normalized_expenditures,
    estimate_thresholds,
    normalize_ce_sample,
)

#: Replicate weights in each CE Interview record.
REPLICATES = 44
#: Strata of the CE's BRR design, the complete-data degrees of freedom.
STRATA = 43
#: The full-sample weight the replicate weights stand in for.
FULL_SAMPLE_WEIGHT = "FINLWT21"
#: CE PUMD names of the replicate weights.
REPLICATE_WEIGHTS = tuple(f"WTREP{r:02d}" for r in range(1, REPLICATES + 1))
#: Fay's coefficient of standard BRR, the form of CE data through 2024.
STANDARD_BRR = 0.0
#: Fay's coefficient of the CE's replicate weights from 2025 CE data.
CE_FAY = 0.5
#: Largest relative gap allowed between a band's components and the
#: thresholds estimated from the same frame.
IDENTITY_TOLERANCE = 1e-9
#: Markers CE PUMD files use for a blank replicate weight.
_BLANKS = ("", ".")


def _parse_weight(value, name: str) -> float:
    """One replicate weight; NaN marks a blank.

    Text goes through ``float``, which rounds correctly, so a weight
    stored as text reads exactly as the number it spells.
    """
    if value is None or value is pd.NA:
        return math.nan
    if isinstance(value, (float, np.floating)):
        return float(value)
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    if text in _BLANKS:
        return math.nan
    try:
        number = float(text)
    except ValueError:
        number = math.nan
    if math.isnan(number):
        raise ValueError(f"{name} holds a non-numeric value {value!r}")
    return number


def replicate_weight_matrix(frame: pd.DataFrame) -> np.ndarray:
    """The ``(rows, 44)`` replicate weights, with blanks read as zero.

    CE PUMD leaves a replicate weight blank where standard BRR sets it to
    zero; older files write the blank as ``.``, so those columns load as
    text. Every other entry must be a finite, nonnegative number.
    """
    missing = [c for c in REPLICATE_WEIGHTS if c not in frame]
    if missing:
        raise ValueError(f"CE records lack replicate weights {missing}")
    columns = []
    for name in REPLICATE_WEIGHTS:
        raw = frame[name]
        if pd.api.types.is_float_dtype(raw) or pd.api.types.is_integer_dtype(
            raw
        ):
            values = raw.to_numpy(dtype=float, na_value=np.nan)
        else:
            values = np.array(
                [_parse_weight(v, name) for v in raw.to_numpy(dtype=object)],
                dtype=float,
            )
        columns.append(np.where(np.isnan(values), 0.0, values))
    matrix = np.column_stack(columns)
    if not (np.isfinite(matrix).all() and (matrix >= 0).all()):
        raise ValueError("Replicate weights must be finite and nonnegative")
    return matrix


def check_standard_brr(matrix: np.ndarray) -> None:
    """Require the standard BRR form: half the weights positive in each row.

    CE data through 2024 take this form. Fay's method, which BLS uses from
    2025 CE data, keeps every replicate weight positive and needs a
    different variance factor, so a window that mixed the forms would have
    no single correct formula.
    """
    matrix = np.asarray(matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != REPLICATES:
        raise ValueError(f"Expected {REPLICATES} replicate weights per row")
    positive = (matrix > 0).sum(axis=1)
    irregular = np.flatnonzero(positive != REPLICATES // 2)
    if irregular.size:
        rows = irregular[:5].tolist()
        raise ValueError(
            f"Rows {rows} carry {positive[rows].tolist()} positive "
            f"replicate weights, not {REPLICATES // 2}; CE data from 2025 "
            "on use Fay's method"
        )


def reweight(frame: pd.DataFrame, weights: np.ndarray) -> pd.DataFrame:
    """``frame`` under one replicate weight: zero-weight rows drop out."""
    weights = np.asarray(weights, dtype=float)
    if weights.shape != (len(frame),):
        raise ValueError("One replicate weight per row is required")
    keep = weights > 0
    out = frame.loc[keep].copy()
    out[FULL_SAMPLE_WEIGHT] = weights[keep]
    return out


def replicate_variance(
    estimate: float, replicates: Sequence[float], fay: float = STANDARD_BRR
) -> float:
    """BRR variance of ``estimate`` from its replicate estimates.

    ``fay`` is Fay's coefficient ``k``: 0 for standard BRR, 0.5 for the
    CE's Fay weights. The sum is exact (``math.fsum``), so the result does
    not depend on the replicates' order.
    """
    values = [float(v) for v in replicates]
    if not values:
        raise ValueError("At least one replicate estimate is required")
    if not 0 <= fay < 1:
        raise ValueError("Fay's coefficient must lie in [0, 1)")
    estimate = float(estimate)
    if not all(math.isfinite(v) for v in (estimate, *values)):
        raise ValueError("Estimates must be finite")
    squares = math.fsum((v - estimate) ** 2 for v in values)
    return squares / (len(values) * (1 - fay) ** 2)


@dataclass(frozen=True)
class Combined:
    """Implicate estimates and variances pooled by Rubin's rules.

    Attributes:
        estimate: Mean of the implicate estimates.
        within: Mean of the implicates' sampling variances.
        between: Variance of the implicate estimates (divisor M - 1).
        total: ``within + (1 + 1/M) * between``.
        implicates: Number of implicates, M.
        fraction_missing: ``(1 + 1/M) * between / total``, the fraction of
            missing information; zero when ``total`` is zero.
        complete_df: Degrees of freedom of one implicate's variance.
        df: Barnard and Rubin's degrees of freedom.
        df_rubin: Rubin's ``(M - 1) / fraction_missing ** 2``, or None
            where it is infinite: no between-implicate variance, or a
            fraction whose square rounds to zero.
    """

    estimate: float
    within: float
    between: float
    total: float
    implicates: int
    fraction_missing: float
    complete_df: float
    df: float
    df_rubin: Optional[float]

    @property
    def standard_error(self) -> float:
        return math.sqrt(self.total)

    def to_dict(self) -> dict:
        return {
            "estimate": self.estimate,
            "standard_error": self.standard_error,
            "within_standard_error": math.sqrt(self.within),
            "within_variance": self.within,
            "between_variance": self.between,
            "total_variance": self.total,
            "implicates": self.implicates,
            "fraction_missing_information": self.fraction_missing,
            "complete_data_df": self.complete_df,
            "df": self.df,
            "df_rubin": self.df_rubin,
        }


def combine_implicates(
    estimates: Sequence[float],
    within: Sequence[float],
    complete_df: float = STRATA,
) -> Combined:
    """Pool implicates by Rubin's rules with Barnard and Rubin's df.

    Args:
        estimates: One full-sample estimate per implicate.
        within: Each implicate's sampling variance.
        complete_df: Degrees of freedom of one implicate's variance.
    """
    q = [float(v) for v in estimates]
    u = [float(v) for v in within]
    m = len(q)
    if m < 2 or len(u) != m:
        raise ValueError("Rubin's rules need two or more implicates")
    if not all(math.isfinite(v) for v in (*q, *u)):
        raise ValueError("Estimates and variances must be finite")
    if min(u) < 0:
        raise ValueError("Within-implicate variances must be nonnegative")
    if not complete_df > 0:
        raise ValueError("Complete-data degrees of freedom must be positive")
    # Correctly rounded means, so identical implicates have no spread.
    q_bar = statistics.mean(q)
    u_bar = statistics.mean(u)
    between = math.fsum((v - q_bar) ** 2 for v in q) / (m - 1)
    inflated = (1 + 1 / m) * between
    total = u_bar + inflated
    fraction = min(inflated / total, 1.0) if total > 0 else 0.0
    nu_obs = (
        complete_df * (complete_df + 1) * (1 - fraction) / (complete_df + 3)
    )
    squared = fraction**2
    if squared == 0:
        # Rubin's df is infinite, or too large to hold, so Barnard and
        # Rubin's df reaches its limit.
        df_rubin = None
        df = nu_obs
    else:
        df_rubin = (m - 1) / squared
        df = 0.0 if nu_obs == 0 else 1 / (1 / df_rubin + 1 / nu_obs)
    return Combined(
        estimate=q_bar,
        within=u_bar,
        between=between,
        total=total,
        implicates=m,
        fraction_missing=fraction,
        complete_df=float(complete_df),
        df=df,
        df_rubin=df_rubin,
    )


def combine_replicated(
    by_implicate: Sequence[Sequence[float]],
    fay: float = STANDARD_BRR,
    complete_df: float = STRATA,
) -> Combined:
    """Rubin's rules over implicates, each given as full sample then replicates.

    ``by_implicate[m][0]`` is implicate ``m``'s full-sample estimate and
    ``by_implicate[m][1:]`` its replicate estimates.
    """
    estimates, within = [], []
    for values in by_implicate:
        values = list(values)
        if len(values) < 2:
            raise ValueError("Each implicate needs replicate estimates")
        estimates.append(values[0])
        within.append(replicate_variance(values[0], values[1:], fay))
    return combine_implicates(estimates, within, complete_df)


def _largest_identity_gap(band: BandComponents, thresholds: dict) -> float:
    largest = 0.0
    for tenure in TENURES:
        gap = abs(band.threshold(tenure) / thresholds[tenure] - 1.0)
        if not gap <= IDENTITY_TOLERANCE:
            raise RuntimeError(
                f"Band means give {band.threshold(tenure)} for {tenure}, "
                f"not the estimated {thresholds[tenure]}"
            )
        largest = max(largest, gap)
    return largest


@dataclass(frozen=True)
class ReplicateEstimates:
    """Thresholds and band means under the full-sample and replicate weights.

    Position 0 of every sequence holds the full sample and position ``i``
    replicate ``replicates[i - 1]``.

    Attributes:
        replicates: The 1-based replicate numbers that ran.
        without: Out-of-pocket thresholds by tenure.
        with_stage: Thresholds with the in-kind stage, by implicate.
        bands: Band means with the in-kind stage, by implicate.
        identity_gap: The largest relative gap between band means and
            thresholds over every run, with and without the stage.
    """

    replicates: tuple[int, ...]
    without: tuple[dict[str, float], ...]
    with_stage: tuple[tuple[dict[str, float], ...], ...]
    bands: tuple[tuple[BandComponents, ...], ...]
    identity_gap: float


def replicate_estimates(
    frame: pd.DataFrame,
    target_year: int,
    in_kind: Sequence[pd.DataFrame] = (),
    *,
    weights: Optional[np.ndarray] = None,
    replicates: Optional[Sequence[int]] = None,
    youth_policy: str = "error",
    tenure_policy: str = "exclude_5_6_code3_mortgage",
    median_share: float = MEDIAN_SHARE,
    cpi_series: Optional[Mapping[str, pd.Series]] = None,
) -> ReplicateEstimates:
    """Rerun the threshold estimator under each replicate weight.

    Args:
        frame: One target year's CE FMLI records, with ``FINLWT21``. Any
            replicate weight columns are dropped before estimation.
        target_year: The threshold year.
        in_kind: One in-kind table per implicate, in the form
            :func:`spm_calculator.ce_inkind_stage.add_in_kind` takes. Each
            stays fixed across replicates.
        weights: The ``(rows, 44)`` replicate weights in ``frame``'s row
            order. Read from the ``WTREP`` columns when omitted.
        replicates: 1-based replicate numbers to run; all by default. The
            full sample always runs.
        youth_policy, tenure_policy, median_share, cpi_series: As in
            :func:`spm_calculator.ce_inkind_stage.prepare_out_of_pocket`,
            which this matches on the full sample. Principal and
            annualization keep their defaults, which the band means need.
    """
    if weights is None:
        weights = replicate_weight_matrix(frame)
    weights = np.asarray(weights, dtype=float)
    if weights.ndim != 2 or weights.shape[0] != len(frame):
        raise ValueError("weights needs one row per frame row")
    numbers = (
        tuple(range(1, weights.shape[1] + 1))
        if replicates is None
        else tuple(int(r) for r in replicates)
    )
    if any(not 1 <= r <= weights.shape[1] for r in numbers):
        raise ValueError(
            f"Replicate numbers must lie in 1..{weights.shape[1]}"
        )
    base = frame.drop(columns=[c for c in REPLICATE_WEIGHTS if c in frame])
    tables = list(in_kind)
    without, with_stage, bands = [], [[] for _ in tables], [[] for _ in tables]
    identity_gap = 0.0
    for number in (0, *numbers):
        sample = (
            base if number == 0 else reweight(base, weights[:, number - 1])
        )
        normalized, _ = normalize_ce_sample(
            sample, youth_policy=youth_policy, tenure_policy=tenure_policy
        )
        expenditures, _ = construct_normalized_expenditures(
            normalized, target_year, cpi_series=cpi_series
        )
        thresholds, _ = estimate_thresholds(expenditures, median_share)
        identity_gap = max(
            identity_gap,
            _largest_identity_gap(
                band_components(expenditures, median_share), thresholds
            ),
        )
        without.append(thresholds)
        for implicate, table in enumerate(tables):
            staged, _ = add_in_kind(expenditures, table)
            staged_thresholds, _ = estimate_thresholds(staged, median_share)
            band = band_components(staged, median_share)
            identity_gap = max(
                identity_gap, _largest_identity_gap(band, staged_thresholds)
            )
            with_stage[implicate].append(staged_thresholds)
            bands[implicate].append(band)
    return ReplicateEstimates(
        replicates=numbers,
        without=tuple(without),
        with_stage=tuple(tuple(runs) for runs in with_stage),
        bands=tuple(tuple(runs) for runs in bands),
        identity_gap=identity_gap,
    )
