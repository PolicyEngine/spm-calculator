"""FCSUti CPI-U Composite Index for SPM threshold inflation adjustment.

The FCSUti composite re-weights five CPI-U component series (food, apparel,
shelter, utilities, telephone, and — for post-2018 vintages — internet) in
proportion to the FCSUti expenditure shares of consumer units with children.
It replaces the All-Items CPI-U used in the pre-2021 SPM methodology.

BLS re-derives the component weights from the CE expenditure sample used
for the target-year threshold itself, so the weights roll with the 5-year
lagged window. This module supports three ways of supplying weights:

1. Pass a ``weights`` dict explicitly (highest precedence).
2. Compute weights from a CE FMLI DataFrame with
   :func:`compute_fcsuti_weights_from_ce`.
3. Fall back to :data:`FCSUTI_WEIGHTS`, a static approximation. A
   :class:`RuntimeWarning` is emitted in this case so runs using the
   fallback are visible in logs.

References
----------
- Garner, T. (2021). *Alternative Measures of the Extent and Severity
  of Poverty: A Review and Data Users' Guide to the Supplemental
  Poverty Measure.* BLS, https://www.bls.gov/pir/spm/garner_spm_choices_03_15_21.pdf
- BLS SPM Thresholds: https://www.bls.gov/pir/spm/spm_thresholds_2024.htm
"""

import os
import warnings
from functools import lru_cache
from typing import Mapping, Optional

import numpy as np
import pandas as pd

# BLS CPI series IDs for FCSUti components.
# Source: https://www.bls.gov/cpi/data.htm
CPI_SERIES = {
    "food": "CUUR0000SAF",  # Food
    "food_at_home": "CUUR0000SAF11",  # Food at home
    "food_away": "CUUR0000SEFV",  # Food away from home
    "apparel": "CUUR0000SAA",  # Apparel
    "shelter": "CUUR0000SAH1",  # Shelter
    "utilities": "CUUR0000SAH2",  # Fuels and utilities
    "telephone": "CUUR0000SEED",  # Telephone services
    "internet": "CUUR0000SEEE",  # Internet services
    "all_items": "CUUR0000SA0",  # All items (reference only)
}

# Static fallback FCSUti expenditure shares for consumer units with
# children. These are a rough approximation of CE shares; BLS re-derives
# them annually from the 5-year CE sample used for each threshold year.
# Prefer supplying ``weights=`` explicitly or deriving via
# :func:`compute_fcsuti_weights_from_ce`.
FCSUTI_WEIGHTS: dict[str, float] = {
    "food": 0.30,
    "apparel": 0.05,
    "shelter": 0.45,
    "utilities": 0.12,
    "telephone": 0.04,
    "internet": 0.04,
}

# FMLI expenditure-column pairs (PQ = previous quarter, CQ = current
# quarter) for each FCSUti component. Used by
# :func:`compute_fcsuti_weights_from_ce`.
_FMLI_EXPENDITURE_COLUMNS: dict[str, tuple[str, str]] = {
    "food": ("FOODPQ", "FOODCQ"),
    "apparel": ("APPARPQ", "APPARCQ"),
    "shelter": ("SHELTPQ", "SHELTCQ"),
    "utilities": ("UTILPQ", "UTILCQ"),
    "telephone": ("TELEPHPQ", "TELEPHCQ"),
    "internet": ("INFOTECHPQ", "INFOTECHCQ"),
}

_MORTGAGE_PRINCIPAL_COLUMNS: tuple[str, str] = ("MRTPRINPQ", "MRTPRINCQ")


def fetch_bls_cpi_series(
    series_id: str,
    start_year: int = 2010,
    end_year: int = 2024,
    registration_key: Optional[str] = None,
) -> pd.Series:
    """Fetch an annual-average CPI series from the BLS public API.

    Args:
        series_id: BLS series ID (e.g. ``"CUUR0000SA0"``).
        start_year: Inclusive start year.
        end_year: Inclusive end year.
        registration_key: Optional BLS v2 registration key. Defaults to
            ``$BLS_API_KEY`` if set. Without a key, BLS rate-limits
            unauthenticated requests to 25 queries per IP per day —
            enough to break `get_fcsuti_cpi` (six component series) after
            four calls.

    Returns:
        Series of annual-average CPI values indexed by calendar year.
    """
    import requests

    # BLS Public Data API v2. Registered access is documented at
    # https://www.bls.gov/developers/; registered callers get 500
    # queries/day per key with ten-year history and annual averages.
    url = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    payload = {
        "seriesid": [series_id],
        "startyear": str(start_year),
        "endyear": str(end_year),
        "annualaverage": True,
    }
    key = registration_key or os.environ.get("BLS_API_KEY")
    if key:
        payload["registrationkey"] = key

    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    if data["status"] != "REQUEST_SUCCEEDED":
        raise ValueError(
            f"BLS API error: {data.get('message', 'Unknown error')}"
        )

    series_data = data["Results"]["series"][0]["data"]
    # Filter to annual averages (period code M13).
    annual = [d for d in series_data if d["period"] == "M13"]
    return pd.Series(
        {int(d["year"]): float(d["value"]) for d in annual},
        name=series_id,
    ).sort_index()


def compute_fcsuti_weights_from_ce(
    ce_df: pd.DataFrame,
    weight_col: str = "FINLWT21",
    children_col: str = "PERSLT18",
    subtract_mortgage_principal: bool = True,
) -> dict[str, float]:
    """Derive FCSUti expenditure shares from a CE FMLI DataFrame.

    For each FCSUti component, computes the survey-weighted total
    expenditure across consumer units with at least one child, then
    normalizes so the returned shares sum to 1.0. Matches the BLS
    Garner (2021) methodology where the composite weights are derived
    from the same CE sample used to compute the threshold itself.

    The ``shelter`` component follows the SPM convention of excluding
    mortgage principal (investment, not consumption) when the
    ``MRTPRINPQ``/``MRTPRINCQ`` columns are present.

    Args:
        ce_df: CE FMLI DataFrame (one row per CU-interview).
        weight_col: Column with the CU's calibrated survey weight.
            Defaults to ``FINLWT21`` (standard FMLI name).
        children_col: Column with the number of persons under 18 in
            the CU. Defaults to ``PERSLT18``.
        subtract_mortgage_principal: When True (default) and
            ``MRTPRINPQ``/``MRTPRINCQ`` are in ``ce_df``, subtract
            mortgage principal from shelter expenditure.

    Returns:
        Dict mapping each FCSUti component present in ``ce_df`` to a
        share in ``[0, 1]``. Shares sum to 1.0. Components without
        their expenditure columns in the data are omitted.

    Raises:
        ValueError: If ``ce_df`` is missing ``weight_col`` or
            ``children_col``, or if no CUs have children, or if no
            FCSUti component columns are present.
    """
    if weight_col not in ce_df.columns:
        raise ValueError(
            f"CE DataFrame is missing weight column '{weight_col}'"
        )
    if children_col not in ce_df.columns:
        raise ValueError(
            f"CE DataFrame is missing children column '{children_col}'"
        )

    with_children = ce_df[ce_df[children_col] > 0]
    if len(with_children) == 0:
        raise ValueError("No consumer units with children in CE DataFrame")

    weights = with_children[weight_col].astype(float).to_numpy()

    def _weighted_expenditure(pq: str, cq: str) -> Optional[float]:
        if pq not in with_children.columns or cq not in with_children.columns:
            return None
        values = (
            with_children[pq].fillna(0).to_numpy()
            + with_children[cq].fillna(0).to_numpy()
        )
        return float(np.sum(values * weights))

    shelter_principal_offset: Optional[float] = None
    if subtract_mortgage_principal:
        shelter_principal_offset = _weighted_expenditure(
            *_MORTGAGE_PRINCIPAL_COLUMNS
        )

    totals: dict[str, float] = {}
    for component, (pq, cq) in _FMLI_EXPENDITURE_COLUMNS.items():
        exp = _weighted_expenditure(pq, cq)
        if exp is None:
            continue
        if component == "shelter" and shelter_principal_offset is not None:
            exp = max(exp - shelter_principal_offset, 0.0)
        totals[component] = exp

    if not totals:
        raise ValueError(
            "CE DataFrame has no FCSUti expenditure columns "
            f"({list(_FMLI_EXPENDITURE_COLUMNS)})"
        )

    total = sum(totals.values())
    if total <= 0:
        raise ValueError("Total FCSUti expenditure is zero or negative")

    return {component: value / total for component, value in totals.items()}


_STATIC_WEIGHTS_WARNING = (
    "Using static FCSUti weights approximation. For BLS-fidelity "
    "inflation adjustment, derive weights from the CE sample via "
    "compute_fcsuti_weights_from_ce() or supply an explicit "
    "weights= dict keyed by component name."
)


def _resolve_weights(
    weights: Optional[Mapping[str, float]],
) -> dict[str, float]:
    """Normalize a supplied ``weights`` mapping (never warns).

    The fallback-use RuntimeWarning is emitted by the public
    entry-point functions (``get_fcsuti_cpi``,
    ``get_fcsuti_inflation_factor``) so that ``stacklevel=2`` attributes
    the warning to the user regardless of which entry point is called.
    """
    if weights is None:
        return dict(FCSUTI_WEIGHTS)
    if not weights:
        raise ValueError("weights mapping is empty")
    return dict(weights)


@lru_cache(maxsize=8)
def _cached_fcsuti_cpi(
    start_year: int,
    end_year: int,
    base_year: int,
    weights_items: tuple[tuple[str, float], ...],
) -> pd.Series:
    """Immutable-inputs worker for :func:`get_fcsuti_cpi`."""
    weights = dict(weights_items)
    components: dict[str, pd.Series] = {}
    for component in weights:
        series_id = CPI_SERIES.get(component)
        if series_id is None:
            warnings.warn(
                f"No CPI series known for component '{component}'; skipping.",
                RuntimeWarning,
                stacklevel=2,
            )
            continue
        try:
            components[component] = fetch_bls_cpi_series(
                series_id, start_year, end_year
            )
        except Exception as e:
            warnings.warn(
                f"Could not fetch {component} CPI: {e}",
                RuntimeWarning,
                stacklevel=2,
            )

    if not components:
        raise ValueError("Could not fetch any CPI component data")

    df = pd.DataFrame(components)
    used_weights = {c: weights[c] for c in df.columns if c in weights}
    if not used_weights:
        raise ValueError(
            "None of the requested FCSUti components returned CPI data"
        )

    denom = sum(used_weights.values())
    if denom <= 0:
        raise ValueError("Requested FCSUti weights sum to zero")
    # Renormalize over the components we actually have so dropped series
    # don't shrink the composite.
    renormalized = {c: w / denom for c, w in used_weights.items()}

    fcsuti = pd.Series(0.0, index=df.index)
    for component, weight in renormalized.items():
        fcsuti += df[component] * weight

    if base_year in fcsuti.index:
        fcsuti = fcsuti / fcsuti[base_year] * 100
    fcsuti.name = "FCSUti CPI-U"
    return fcsuti


def get_fcsuti_cpi(
    start_year: int = 2010,
    end_year: int = 2024,
    base_year: int = 2024,
    weights: Optional[Mapping[str, float]] = None,
) -> pd.Series:
    """Compute the FCSUti composite CPI index.

    Args:
        start_year: Inclusive start year for the index.
        end_year: Inclusive end year for the index.
        base_year: Year normalized to 100.
        weights: Optional component-share mapping (e.g. the output of
            :func:`compute_fcsuti_weights_from_ce`). When None, falls
            back to :data:`FCSUTI_WEIGHTS` with a
            :class:`RuntimeWarning` so callers notice when the static
            approximation is in use.

    Returns:
        Annual FCSUti CPI index with base ``base_year`` = 100.
    """
    if weights is None:
        warnings.warn(
            _STATIC_WEIGHTS_WARNING,
            RuntimeWarning,
            stacklevel=2,
        )
    resolved = _resolve_weights(weights)
    return _cached_fcsuti_cpi(
        start_year,
        end_year,
        base_year,
        tuple(sorted(resolved.items())),
    )


def get_fcsuti_inflation_factor(
    from_year: int,
    to_year: int,
    weights: Optional[Mapping[str, float]] = None,
) -> float:
    """Inflation factor between two years via the FCSUti composite.

    Resolution order when the BLS API is unreachable:

    1. Consult `PRECOMPUTED_FCSUTI_FACTORS` for an exact year pair.
       These are baked from published BLS FCSUti indices and are
       materially better than the 4% constant-growth estimate when
       they match.
    2. Compose two precomputed factors through a common target year
       (e.g. `(2019, 2024)` × `(2024, 2026)` when only direct pairs
       to 2024 are baked). This extends the precomputed coverage
       across the full range without shipping a quadratic table.
    3. Fall back to 4% annual growth.

    Args:
        from_year: Starting year (sets the index base).
        to_year: Target year.
        weights: Optional FCSUti component shares. See
            :func:`get_fcsuti_cpi`.

    Returns:
        Factor to multiply ``from_year`` dollars by to get ``to_year``
        dollars. Falls back to a ~4%/yr estimate if the BLS series
        fetch fails, and emits a :class:`RuntimeWarning` in that case.
    """
    if from_year == to_year:
        return 1.0

    if weights is None:
        warnings.warn(
            _STATIC_WEIGHTS_WARNING,
            RuntimeWarning,
            stacklevel=2,
        )
        weights = FCSUTI_WEIGHTS

    try:
        fcsuti = get_fcsuti_cpi(
            start_year=min(from_year, to_year) - 1,
            end_year=max(from_year, to_year) + 1,
            base_year=from_year,
            weights=weights,
        )
        return fcsuti[to_year] / 100.0
    except Exception as e:
        direct = get_precomputed_fcsuti_factor(from_year, to_year)
        if direct is not None:
            warnings.warn(
                f"Could not fetch FCSUti CPI ({e}); using precomputed "
                f"factor for ({from_year}, {to_year}).",
                RuntimeWarning,
                stacklevel=2,
            )
            return direct

        composed = _compose_precomputed_fcsuti_factor(from_year, to_year)
        if composed is not None:
            warnings.warn(
                f"Could not fetch FCSUti CPI ({e}); using composed "
                f"precomputed factors for ({from_year}, {to_year}).",
                RuntimeWarning,
                stacklevel=2,
            )
            return composed

        warnings.warn(
            f"Could not fetch FCSUti CPI ({e}); no precomputed factor "
            f"matches ({from_year}, {to_year}), falling back to 4%/yr estimate.",
            RuntimeWarning,
            stacklevel=2,
        )
        return 1.04 ** (to_year - from_year)


def _compose_precomputed_fcsuti_factor(
    from_year: int,
    to_year: int,
) -> Optional[float]:
    """Chain two precomputed factors through a common pivot year.

    Returns ``factor[(from_year, pivot)] * factor[(pivot, to_year)]`` if
    a single pivot year closes the gap. Inverts stored factors as needed
    so we don't need to double the table size to cover both directions.
    """
    pivots = {pair[1] for pair in PRECOMPUTED_FCSUTI_FACTORS} | {
        pair[0] for pair in PRECOMPUTED_FCSUTI_FACTORS
    }
    for pivot in pivots:
        first = _directed_precomputed_factor(from_year, pivot)
        second = _directed_precomputed_factor(pivot, to_year)
        if first is not None and second is not None:
            return first * second
    return None


def _directed_precomputed_factor(
    from_year: int, to_year: int
) -> Optional[float]:
    """Precomputed factor in either direction (invert if stored the
    other way). Returns None if neither direction is stored."""
    if from_year == to_year:
        return 1.0
    direct = PRECOMPUTED_FCSUTI_FACTORS.get((from_year, to_year))
    if direct is not None:
        return direct
    reverse = PRECOMPUTED_FCSUTI_FACTORS.get((to_year, from_year))
    if reverse is not None and reverse != 0:
        return 1.0 / reverse
    return None


# Pre-computed FCSUti inflation factors for common year pairs. Retained
# for offline use when the BLS API is unavailable.
PRECOMPUTED_FCSUTI_FACTORS = {
    (2018, 2024): 1.26,  # ~4.0% annual
    (2019, 2024): 1.22,  # ~4.1% annual
    (2020, 2024): 1.19,  # ~4.5% annual (pandemic effects)
    (2021, 2024): 1.15,  # ~4.8% annual
    (2022, 2024): 1.08,  # ~3.9% annual
    (2023, 2024): 1.04,  # 4.0% (published)
}


def get_precomputed_fcsuti_factor(
    from_year: int,
    to_year: int,
) -> Optional[float]:
    """Return the pre-computed inflation factor for a year pair, or None."""
    return PRECOMPUTED_FCSUTI_FACTORS.get((from_year, to_year))
