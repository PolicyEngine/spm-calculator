"""Research forecasts from weighted ACS rent records and explicit geography.

Public PUMS geography allocation and discrete weighted medians approximate
Census's confidential records and grouped-median interpolation. This module
does not estimate survey-design uncertainty or a forecast confidence interval.
It performs no source I/O and never substitutes a missing area's index.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

TOPCODE_COMPONENTS = ("rent", "electricity", "gas", "fuel", "water")
SUPPORT_THRESHOLD = 30


def weighted_median(values, weights) -> float:
    """First value whose positive cumulative weight reaches half the total."""
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if (
        values.ndim != 1
        or values.shape != weights.shape
        or not len(values)
        or not np.isfinite(values).all()
        or not np.isfinite(weights).all()
        or (values < 0).any()
        or (weights <= 0).any()
    ):
        raise ValueError("Median requires finite values and positive weights")
    return _median(values, weights)


def _median(values, weights) -> float:
    order = np.argsort(values, kind="stable")
    cumulative = np.cumsum(weights[order])
    return float(
        values[order[np.searchsorted(cumulative, cumulative[-1] / 2)]]
    )


def _records(records: pd.DataFrame) -> pd.DataFrame:
    required = {"record_id", "cohort_year", "puma_geoid", "rent", "weight"}
    if not required <= set(records):
        raise ValueError(
            f"Missing record fields: {sorted(required - set(records))}"
        )
    data = records.copy()
    if "source_vintage" in data and data.source_vintage.nunique() != 1:
        raise ValueError("A pooled record set must use one source vintage")
    if data.empty or data[list(required)].isna().any().any():
        raise ValueError("Records must be nonempty and complete")
    for field in ("rent", "weight"):
        if not np.isfinite(data[field]).all() or (data[field] <= 0).any():
            raise ValueError(f"Invalid {field}: must be finite and positive")
    if not np.equal(data.cohort_year, data.cohort_year.astype(int)).all():
        raise ValueError("Invalid cohort year")
    data["cohort_year"] = data.cohort_year.astype(int)
    if data.duplicated(["record_id", "cohort_year"]).any():
        raise ValueError("Duplicate original record in the same cohort")
    if "source_year" not in data:
        data["source_year"] = data.cohort_year
    if "projected" not in data:
        data["projected"] = False
    for component in TOPCODE_COMPONENTS:
        field = f"top_{component}"
        if field not in data:
            data[field] = False
        if data[field].isna().any():
            raise ValueError("Missing component topcoding flag")
        data[field] = data[field].astype(bool)
    if "rent_lower_bound" not in data:
        # The conservative bound for an unspecified censored component is zero.
        flags = data[[f"top_{c}" for c in TOPCODE_COMPONENTS]].any(axis=1)
        data["rent_lower_bound"] = data.rent.where(~flags, 0.0)
    lower = data.rent_lower_bound
    if (
        not np.isfinite(lower).all()
        or (lower < 0).any()
        or (lower > data.rent).any()
    ):
        raise ValueError("Invalid censored rent lower bound")
    return data


def _growth(path: Mapping[int, float], year: int) -> float:
    if year not in path:
        raise ValueError(f"Missing growth rate for {year}")
    rate = path[year]
    if isinstance(rate, bool) or not np.isfinite(rate) or rate <= -1:
        raise ValueError(f"Invalid growth rate for {year}")
    return 1 + float(rate)


def build_window(
    records: pd.DataFrame,
    spm_year: int,
    *,
    donor_year: int,
    nominal_rent_growth_by_year: Mapping[int, float],
    price_growth_by_year: Mapping[int, float],
) -> pd.DataFrame:
    """Select T-5..T-1; future copies retain their original IDs and weights.

    Observed rents already use their product's ADJHSG. Future nominal growth
    divided by the price deflator keeps all rents in that same dollar basis.
    """
    data = _records(records)
    if data.cohort_year.max() != donor_year:
        raise ValueError("Donor year must be the last observed cohort")
    donor = data[data.cohort_year == donor_year]
    if donor.empty:
        raise ValueError("Missing donor cohort")
    observed = set(data.cohort_year)
    factors = {donor_year: 1.0}
    for year in range(donor_year + 1, spm_year):
        factors[year] = factors[year - 1] * (
            _growth(nominal_rent_growth_by_year, year)
            / _growth(price_growth_by_year, year)
        )
    pieces = []
    for year in range(spm_year - 5, spm_year):
        if year <= donor_year:
            if year not in observed:
                raise ValueError(f"Missing observed cohort {year}")
            piece = data[data.cohort_year == year].copy()
        else:
            piece = donor.copy()
            piece["cohort_year"] = year
            piece["projected"] = True
            piece["rent"] *= factors[year]
            piece["rent_lower_bound"] *= factors[year]
        pieces.append(piece)
    return pd.concat(pieces, ignore_index=True)


def _allocations(allocations: pd.DataFrame, pumas, area_codes) -> pd.DataFrame:
    required = {"puma_geoid", "area_code", "fraction"}
    if not required <= set(allocations):
        raise ValueError("Missing allocation columns")
    mapping = allocations[list(required)].copy()
    if mapping.puma_geoid.isna().any():
        raise ValueError("Missing allocation PUMA")
    if (
        not np.isfinite(mapping.fraction).all()
        or not mapping.fraction.between(0, 1 + 1e-12).all()
    ):
        raise ValueError("Invalid allocation fraction")
    # Summing county population shares can exceed one by machine epsilon.
    mapping["fraction"] = mapping.fraction.clip(upper=1.0)
    if set(pumas) - set(mapping.puma_geoid):
        raise ValueError("Incomplete PUMA allocation coverage")
    if set(mapping.area_code.dropna()) - set(area_codes):
        raise ValueError("Allocation contains unrequested area codes")
    mapping = mapping.groupby(
        ["puma_geoid", "area_code"], dropna=False, as_index=False
    ).fraction.sum()
    sums = mapping.groupby("puma_geoid").fraction.sum()
    if not np.allclose(sums, 1, rtol=0, atol=1e-10):
        raise ValueError("PUMA allocation fractions must sum to one")
    return mapping[mapping.fraction > 0]


def _support(group: pd.DataFrame) -> dict:
    originals = group.groupby("record_id", sort=False).agg(
        weight=("allocated_weight", "sum"), fraction=("fraction", "max")
    )
    weight = originals.weight.to_numpy()
    unique = len(originals)
    expected = float(originals.fraction.sum())
    kish = (
        float(weight.sum() ** 2 / np.square(weight).sum()) if unique else 0.0
    )
    return {
        "unique_records": unique,
        "expected_whole_record_count": expected,
        "kish_effective_count": kish,
        "thin_support": min(unique, expected, kish) < SUPPORT_THRESHOLD,
    }


def _censoring(group: pd.DataFrame, weights: np.ndarray) -> dict:
    flags = group[[f"top_{c}" for c in TOPCODE_COMPONENTS]].to_numpy(bool)
    any_flag = flags.any(axis=1)
    values = group.rent.to_numpy(float)
    lower = _median(group.rent_lower_bound.to_numpy(float), weights)
    upper = _median(np.where(any_flag, np.inf, values), weights)
    component_shares = {
        name: float(weights[flags[:, i]].sum() / weights.sum())
        for i, name in enumerate(TOPCODE_COMPONENTS)
    }
    return {
        "component_topcoding_weight_shares": component_shares,
        "topcoded_weight_share": float(
            weights[any_flag].sum() / weights.sum()
        ),
        "rent_topcoded_weight_share": component_shares["rent"],
        "utility_topcoded_weight_share": float(
            weights[flags[:, 1:].any(axis=1)].sum() / weights.sum()
        ),
        "median_topcode_warning": not np.isclose(
            lower, upper, rtol=0, atol=1e-8
        ),
        "median_topcode_lower_bound": lower,
        "median_topcode_upper_bound": upper if np.isfinite(upper) else None,
    }


def summarize_window(
    records: pd.DataFrame,
    area_allocations: pd.DataFrame,
    area_codes: Sequence[str],
) -> dict:
    """Pool record weights, retain all US records and report allocation limits."""
    data = _records(records)
    area_codes = sorted(area_codes)
    mapping = _allocations(area_allocations, data.puma_geoid, area_codes)
    national_weight = float(data.weight.sum())
    national_median = weighted_median(data.rent, data.weight)
    national_topcoding = _censoring(data, data.weight.to_numpy(float))
    expanded = data.merge(
        mapping, on="puma_geoid", how="left", validate="many_to_many"
    )
    expanded["allocated_weight"] = expanded.weight * expanded.fraction
    unassigned = float(
        expanded.loc[expanded.area_code.isna(), "allocated_weight"].sum()
    )
    areas = {}
    for code, group in expanded.dropna(subset=["area_code"]).groupby(
        "area_code", sort=True
    ):
        weights = group.allocated_weight.to_numpy(float)
        median = weighted_median(group.rent, weights)
        donor_year = int(group.source_year.max())
        donor = group[group.source_year == donor_year]
        support = _support(group)
        donor_support = _support(donor)
        local_topcoding = _censoring(group, weights)
        index_sources = {
            "target_local_median": local_topcoding["median_topcode_warning"],
            "target_national_median": national_topcoding[
                "median_topcode_warning"
            ],
        }
        areas[code] = {
            "model_rent_index": median / national_median,
            "local_median_gross_rent": median,
            "allocated_weight": float(weights.sum()),
            "eligible_record_count_by_cohort": {
                str(int(year)): int(count)
                for year, count in group.groupby("cohort_year").size().items()
            },
            "allocated_weight_by_cohort": {
                str(int(year)): float(weight)
                for year, weight in group.groupby("cohort_year")
                .allocated_weight.sum()
                .items()
            },
            **support,
            "unique_original_donor_count": donor_support["unique_records"],
            "donor_support": donor_support,
            **local_topcoding,
            "local_median_topcode_warning": local_topcoding[
                "median_topcode_warning"
            ],
            "model_rent_index_topcode_warning": any(index_sources.values()),
            "rent_index_topcode_warning": any(index_sources.values()),
            "rent_index_topcode_sources": index_sources,
            "rent_index_topcode_scope": "local_to_national_pums_ratio",
        }
        if group.projected.any() and donor_support["thin_support"]:
            areas[code]["thin_support"] = True
    if set(areas) != set(area_codes):
        raise ValueError(
            f"Missing positive area coverage: {set(area_codes) - set(areas)}"
        )
    assigned = sum(x["allocated_weight"] for x in areas.values())
    if not np.isclose(assigned + unassigned, national_weight, rtol=1e-10):
        raise ValueError("Allocated weights do not conserve national weight")
    observed = sorted(
        int(y) for y in data.loc[~data.projected, "cohort_year"].unique()
    )
    projected = sorted(
        int(y) for y in data.loc[data.projected, "cohort_year"].unique()
    )
    return {
        "window": {
            "start": int(data.cohort_year.min()),
            "end": int(data.cohort_year.max()),
            "observed_years": observed,
            "projected_years": projected,
        },
        "national_median_gross_rent": national_median,
        "national_weight": national_weight,
        "national_eligible_records": len(data),
        "national_weight_by_cohort": {
            str(int(y)): float(w)
            for y, w in data.groupby("cohort_year").weight.sum().items()
        },
        "assigned_weight": assigned,
        "unassigned_weight": unassigned,
        "unassigned_weight_share": unassigned / national_weight,
        "national_topcoding": national_topcoding,
        "areas": areas,
    }


def _indices(summary: dict) -> dict[str, float]:
    return {
        code: entry["model_rent_index"]
        for code, entry in summary["areas"].items()
    }


def add_index_topcode_diagnostics(summary: dict, references: Mapping) -> None:
    """Flag potential censoring sensitivity in every contributing ratio.

    These conservative input flags do not imply known index bias, independent
    medians, or a confidence interval. Shared inputs can cancel algebraically.
    """
    for code, area in summary["areas"].items():
        sources = {
            "target_local_median": area["local_median_topcode_warning"],
            "target_national_median": summary["national_topcoding"][
                "median_topcode_warning"
            ],
        }
        for label, reference in references.items():
            sources[f"{label}_local_median"] = reference["areas"][code][
                "local_median_topcode_warning"
            ]
            sources[f"{label}_national_median"] = reference[
                "national_topcoding"
            ]["median_topcode_warning"]
        area["rent_index_topcode_sources"] = sources
        area["rent_index_topcode_warning"] = any(sources.values())
        area["rent_index_topcode_scope"] = "all_anchored_index_ratio_inputs"


def _anchors(values: Mapping[str, float]) -> dict[str, float]:
    if not values or any(not isinstance(k, str) for k in values):
        raise ValueError("Anchor area codes must be nonempty strings")
    result = {key: float(value) for key, value in sorted(values.items())}
    if not all(np.isfinite(v) and v > 0 for v in result.values()):
        raise ValueError("Anchor indices must be finite and positive")
    return result


def project_acs_windows(
    baseline_records: pd.DataFrame,
    observed_records: pd.DataFrame,
    area_allocations: pd.DataFrame,
    official_anchor_indices: Mapping[str, float],
    *,
    anchor_spm_year: int = 2024,
    observed_acs_end_year: int = 2024,
    donor_year: int = 2024,
    end_spm_year: int = 2030,
    nominal_rent_growth_by_year: Mapping[int, float],
    price_growth_by_year: Mapping[int, float],
    anchor_status_by_area: Mapping[str, str] | None = None,
) -> dict:
    """Anchor rolling ratios; bridge whole PUMS products on common cohorts."""
    anchor = _anchors(official_anchor_indices)
    anchor_status = dict(
        anchor_status_by_area or {code: "published_anchor" for code in anchor}
    )
    if set(anchor_status) != set(anchor) or set(anchor_status.values()) - {
        "published_anchor",
        "modeled_unanchored",
    }:
        raise ValueError("Anchor statuses must cover all areas explicitly")
    old, new = _records(baseline_records), _records(observed_records)
    if donor_year != observed_acs_end_year or set(new.cohort_year) != set(
        range(donor_year - 4, donor_year + 1)
    ):
        raise ValueError(
            "Observed source must contain exactly five required cohorts"
        )
    if anchor_spm_year not in (
        observed_acs_end_year,
        observed_acs_end_year + 1,
    ):
        raise ValueError(
            "Anchor must correspond to old or new observed product"
        )
    if end_spm_year < anchor_spm_year:
        raise ValueError("End year precedes anchor")
    bridge = {}
    reference_summaries = {}
    if anchor_spm_year == observed_acs_end_year:
        if set(old.cohort_year) != set(
            range(anchor_spm_year - 5, anchor_spm_year)
        ):
            raise ValueError(
                "Baseline source must contain exactly five required cohorts"
            )
        full = summarize_window(old, area_allocations, list(anchor))
        overlap_start = donor_year - 4
        old_overlap = summarize_window(
            old[old.cohort_year >= overlap_start],
            area_allocations,
            list(anchor),
        )
        new_overlap = summarize_window(
            new[new.cohort_year < donor_year], area_allocations, list(anchor)
        )
        reference_summaries = {
            "old_full": full,
            "old_overlap": old_overlap,
            "new_overlap": new_overlap,
        }
        for code in anchor:
            of = full["areas"][code]["model_rent_index"]
            oo = old_overlap["areas"][code]["model_rent_index"]
            no = new_overlap["areas"][code]["model_rent_index"]
            bridge[code] = {
                "old_full_ratio": of,
                "old_overlap_ratio": oo,
                "new_overlap_ratio": no,
                "overlap_vintage_multiplier": no / oo,
            }
        anchor_summary = full
    else:
        anchor_summary = summarize_window(new, area_allocations, list(anchor))
        reference_summaries = {"anchor_window": anchor_summary}
    anchor_ratios = _indices(anchor_summary)
    indices = {str(anchor_spm_year): anchor}
    diagnostics = {str(anchor_spm_year): anchor_summary}
    for year in range(anchor_spm_year + 1, end_spm_year + 1):
        window = build_window(
            new,
            year,
            donor_year=donor_year,
            nominal_rent_growth_by_year=nominal_rent_growth_by_year,
            price_growth_by_year=price_growth_by_year,
        )
        summary = summarize_window(window, area_allocations, list(anchor))
        add_index_topcode_diagnostics(summary, reference_summaries)
        target = _indices(summary)
        indices[str(year)] = {
            code: anchor[code]
            * (
                bridge[code]["old_overlap_ratio"]
                / bridge[code]["old_full_ratio"]
                * target[code]
                / bridge[code]["new_overlap_ratio"]
                if bridge
                else target[code] / anchor_ratios[code]
            )
            for code in anchor
        }
        diagnostics[str(year)] = summary
    # The published anchor is used exactly. Its PUMS approximation's warning
    # remains in model_rent_index_topcode_warning, not the official index.
    for code, area in anchor_summary["areas"].items():
        if anchor_status[code] == "published_anchor":
            area["rent_index_topcode_warning"] = False
            area["rent_index_topcode_sources"] = {}
            area["rent_index_topcode_scope"] = (
                "published_anchor_not_pums_estimate"
            )
        area["anchor_status"] = anchor_status[code]
    return {
        "indices_by_year": indices,
        "diagnostics_by_year": diagnostics,
        "metadata": {
            "anchor_spm_year": anchor_spm_year,
            "anchor_status_by_area": anchor_status,
            "anchor_acs_window": [anchor_spm_year - 5, anchor_spm_year - 1],
            "observed_acs_end_year": observed_acs_end_year,
            "donor_year": donor_year,
            "overlap_bridge": bridge,
            "nominal_rent_growth_by_year": {
                str(y): float(r)
                for y, r in sorted(nominal_rent_growth_by_year.items())
            },
            "price_growth_by_year": {
                str(y): float(r)
                for y, r in sorted(price_growth_by_year.items())
            },
            "support_threshold": SUPPORT_THRESHOLD,
            "support_rule": "min(unique originals, allocation-expected originals, donor-collapsed Kish)<30; projected windows also flag thin donor support",
            "thin_support_policy": "Retain the computed area/window estimate with immutable support counts and warnings; no donor widening, carryforward or substitution. Empty or nonpositive numerical support raises an error.",
            "kish_interpretation": "Unequal-weight diagnostic; not survey-design effective sample size",
            "uncertainty_status": "Survey-design uncertainty and forecast intervals are not estimated",
            "index_topcoding_interpretation": "Potential sensitivity from local or national medians in any contributing target, anchor or overlap ratio; conservative input flags, not known bias or confidence intervals. Exact published anchors are not PUMS estimates.",
        },
    }


def evaluate_indices(candidate, target, carry) -> dict:
    """Equal-area historical comparison, with identical complete coverage."""
    candidate, target, carry = map(_anchors, (candidate, target, carry))
    if set(candidate) != set(target) or set(candidate) != set(carry):
        raise ValueError(
            "Evaluation requires identical complete area coverage"
        )
    areas = {}
    for code in target:
        error = 100 * (candidate[code] / target[code] - 1)
        baseline_error = 100 * (carry[code] / target[code] - 1)
        areas[code] = {
            "prediction": candidate[code],
            "target": target[code],
            "carry": carry[code],
            "signed_percent_error": error,
            "absolute_percent_error": abs(error),
            "carry_signed_percent_error": baseline_error,
            "carry_absolute_percent_error": abs(baseline_error),
        }

    def metrics(field):
        errors = np.array([x[field] for x in areas.values()])
        return {
            "mape": float(errors.mean()),
            "median_absolute_percent_error": float(np.median(errors)),
            "p90_absolute_percent_error": float(np.percentile(errors, 90)),
            "area_count": len(errors),
        }

    cm = metrics("absolute_percent_error")
    bm = metrics("carry_absolute_percent_error")
    beats = cm["mape"] < bm["mape"]
    return {
        "status": "complete",
        "unvalidated": False,
        "common_area_count": len(areas),
        "candidate_metrics": cm,
        "carry_metrics": bm,
        "beats_baseline": beats,
        "underperformance_warning": (
            None
            if beats
            else "Modeled geographic change did not outperform unchanged indices in the retrospective test."
        ),
        "areas": areas,
    }
