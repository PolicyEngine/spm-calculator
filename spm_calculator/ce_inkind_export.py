"""Per-interview export of the CE in-kind imputations.

The export holds one row per CE Interview (FMLI ``NEWID``) per implicate,
with each component's modeled participation and annual dollar amount from
:func:`spm_calculator.ce_inkind.impute_in_kind`. ``scripts/
export_ce_inkind_by_interview.py`` builds it from the cached public-use
files, and ``docs/ce-inkind-export.md`` documents it.

:func:`impute_in_kind` returns amounts but not the participation draws, so
:func:`observe_participation` records them while it runs. It wraps the
module's ``_participation`` for the length of a ``with`` block, records each
call's result and returns that result unchanged; it draws no random numbers
and copies the arrays, so the imputation is the same with or without it.
:func:`export_frames` then checks the recorded draws against the amounts and
the diagnostics before building the rows.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import inspect
import io
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from spm_calculator import ce_inkind
from spm_calculator.ce_inkind import (
    IN_KIND_COMPONENTS,
    WIC_BROAD_UNIVERSE_FIRST_TARGET,
    InKindConfig,
    InKindImputation,
)

#: FMLI columns :func:`spm_calculator.ce_inkind.ce_unit_covariates` reads.
#: It treats a missing column as all missing, so the export script checks
#: that every quarter carries each one.
FMLI_COLUMNS = (
    "NEWID",
    "FINLWT21",
    "ce_year",
    "ce_quarter",
    "QINTRVYR",
    "QINTRVMO",
    "REGION",
    "STATE",
    "CUTENURE",
    "FAM_SIZE",
    "FINCBTXM",
    "JFS_AMT",
    "JFS_AMTM",
    "FS_MTHI",
    "WELFAREM",
    "FSSIXM",
    "NO_EARNR",
    "AGE_REF",
    "SEX_REF",
    "REF_RACE",
    "HISP_REF",
    "EDUC_REF",
    "BEDROOMQ",
    "BATHRMQ",
    "BUILDING",
    "BLS_URBN",
    "POPSIZE",
)

#: Components whose participation :func:`impute_in_kind` draws from a model.
#: Rental assistance participation comes from the CE report itself.
MODELED_COMPONENTS = ("nslp", "wic", "liheap", "broadband")

#: Target year whose rules give the WIC values the export carries: the
#: universe every threshold before 2025 used. Thresholds from 2025 use only
#: reference years 2020 on, where no unit gets WIC, so these values are the
#: ones every target used.
WIC_EXPORT_TARGET = WIC_BROAD_UNIVERSE_FIRST_TARGET - 1


@dataclass(frozen=True)
class Column:
    """One column of the export."""

    name: str
    kind: str
    description: str


def _participant(component: str, rule: str) -> Column:
    return Column(
        f"{component}_participant",
        "0/1 or empty" if component == "broadband" else "0/1",
        rule,
    )


def _amount(component: str, rule: str) -> Column:
    return Column(f"{component}_amount", "dollars", rule)


DICTIONARY: tuple[Column, ...] = (
    Column(
        "NEWID",
        "integer",
        "CE Interview FMLI record id. Unique across every row of one "
        "implicate; join on it as a number.",
    ),
    Column(
        "implicate",
        "integer",
        "Implicate number, 1 to 5 (the receipts' index plus 1). Analyze each "
        "implicate separately and combine estimates with Rubin's rules. Do "
        "not pair implicate m with the CE income imputation FINCBTXm: each CE "
        "unit's poverty ratio uses FINCBTXM, the mean of the five.",
    ),
    Column(
        "ce_year",
        "integer",
        "Collection year of the interview: the year in the FMLI file name "
        "(fmliYYq.csv). Quarter 1 files ship in the previous year's release.",
    ),
    Column(
        "ce_quarter",
        "integer",
        "Collection quarter of the interview, 1 to 4: the quarter in the "
        "FMLI file name.",
    ),
    Column(
        "reference_year",
        "integer",
        "Year whose program rules, CPS ASEC donors and dollars the values "
        "use: ce_year for quarters 2-4 and ce_year - 1 for quarter 1.",
    ),
    Column(
        "wic_broad_universe_only",
        "0/1",
        "1 if the unit has a child under 5 but no woman aged 15 or older. "
        "BLS's WIC universe adds these units from the 2025 thresholds; the "
        "WIC columns here leave them out.",
    ),
    _participant(
        "nslp",
        "1 if the imputation assigns free or reduced-price school lunch, "
        "the outcome CPS ASEC households report in HFLUNCH. Paid lunches "
        "never count as participation. Only units with a member aged 5-18 "
        "can be 1.",
    ),
    _amount(
        "nslp",
        "Annual school lunch value, in nominal dollars of the reference "
        "year: a matched CPS ASEC household's value, scaled to the unit's "
        "children aged 5-18. For 2014-2017 the donor value covers free and "
        "reduced-price lunches; from 2018 it is Census's SPM_SCHLUNCH summed "
        "over the donor household's SPM units, which can include paid "
        "lunches for the donor's other children.",
    ),
    _participant(
        "wic",
        "1 if modeled as receiving WIC. Only units with a woman aged 15-45, "
        "or with a child under 5 and a woman aged 15 or older, can be 1.",
    ),
    _amount(
        "wic",
        "Annual WIC food value, in nominal dollars of the reference year: "
        "Census's participant count x 12 x the state's average monthly food "
        "cost per person. Where the CE withholds the state, the cost is the "
        "weighted mean for known-state units in the unit's region and "
        "quarter whose state had not finished WIC EBT. Zero where the state "
        "had finished statewide WIC EBT and in every reference year from "
        "2020.",
    ),
    _participant(
        "liheap",
        "1 if modeled as receiving energy assistance. Any unit can be 1.",
    ),
    _amount(
        "liheap",
        "Annual energy assistance, in nominal dollars of the reference "
        "year: a matched CPS ASEC recipient's reported amount.",
    ),
    _participant(
        "broadband",
        "1 if modeled as receiving a broadband subsidy. Empty before "
        "reference year 2022, when the subsidy is not modeled.",
    ),
    _amount(
        "broadband",
        "Annual broadband subsidy, in nominal dollars of the reference year: "
        "a matched CPS ASEC household's Census-assigned EBB or ACP value. "
        "Zero before reference year 2022.",
    ),
    _participant(
        "rental_assistance",
        "1 if the unit rents and reports government-subsidized or public "
        "housing in the CE rent file. The same in every implicate.",
    ),
    _amount(
        "rental_assistance",
        "Annual rental assistance, in nominal dollars of the reference year: "
        "12 x (imputed market rent - rent paid).",
    ),
)

COLUMNS = tuple(column.name for column in DICTIONARY)


@contextmanager
def observe_participation():
    """Record each participation draw :func:`impute_in_kind` makes.

    Yields a dict keyed by ``(component, reference_year)``. Each value is
    ``(keys, takes)``: the CE unit keys passed to the draw, in the order
    used, and one boolean array per implicate. A second draw for the same
    key raises, so the block should hold one :func:`impute_in_kind` call.

    Raises:
        RuntimeError: If another observer is already recording.
    """
    original = ce_inkind._participation
    if getattr(original, "_records_participation", False):
        raise RuntimeError("Participation draws are already being observed")
    signature = inspect.signature(original)
    records: dict = {}

    def recording(*args, **kwargs):
        takes = original(*args, **kwargs)
        bound = signature.bind(*args, **kwargs).arguments
        key = (str(bound["component"]), int(bound["reference_year"]))
        if key in records:
            raise RuntimeError(f"Second participation draw for {key}")
        records[key] = (
            bound["ce"]["key"].to_numpy(dtype="int64").copy(),
            [np.array(take, dtype=bool, copy=True) for take in takes],
        )
        return takes

    recording._records_participation = True
    ce_inkind._participation = recording
    try:
        yield records
    finally:
        ce_inkind._participation = original


def _expected_draws(reference_years, config: InKindConfig) -> set:
    expected = set()
    for year in reference_years:
        for component in MODELED_COMPONENTS:
            if component not in config.components:
                continue
            if (
                component == "broadband"
                and year < config.broadband_first_reference_year
            ):
                continue
            expected.add((component, int(year)))
    return expected


def _weighted_rate(take: np.ndarray, weight: np.ndarray) -> float:
    total = weight.sum()
    return float(np.sum(take * weight) / total) if total > 0 else 0.0


def export_frames(
    ce_units: pd.DataFrame,
    imputation: InKindImputation,
    draws: dict,
    config: InKindConfig,
) -> list[pd.DataFrame]:
    """Build one export frame per implicate and check it.

    Args:
        ce_units: The frame passed to :func:`impute_in_kind`.
        imputation: Its result.
        draws: What :func:`observe_participation` recorded during that call.
        config: The settings passed to :func:`impute_in_kind`.

    Returns:
        One frame per implicate with :data:`COLUMNS`, unrounded. Participant
        columns are nullable integers; broadband's is missing before
        ``config.broadband_first_reference_year``.

    Raises:
        RuntimeError: If the imputation left out a component, or if the
            recorded draws are not exactly the ones the imputation used.
    """
    if set(config.components) != set(IN_KIND_COMPONENTS):
        raise RuntimeError(
            "The export needs every in-kind component imputed, not "
            f"{sorted(config.components)}"
        )
    ce = ce_units.reset_index(drop=True)
    keys = ce["key"].to_numpy(dtype="int64")
    reference_year = ce["reference_year"].to_numpy(dtype=int)
    weight = ce["weight"].to_numpy(dtype=float)
    years = sorted(set(reference_year.tolist()))
    expected = _expected_draws(years, config)
    if set(draws) != expected:
        raise RuntimeError(
            f"Recorded participation draws {sorted(set(draws) ^ expected)} "
            "differ from the expected set"
        )
    index = pd.Index(keys)
    implicates = range(config.implicates)
    takes = {
        component: [np.zeros(len(ce), dtype=bool) for _ in implicates]
        for component in MODELED_COMPONENTS
    }
    for (component, year), (draw_keys, draw_takes) in draws.items():
        positions = index.get_indexer(draw_keys)
        if (positions < 0).any() or len(draw_takes) != config.implicates:
            raise RuntimeError(f"Draw for {component} {year} does not match")
        if (reference_year[positions] != year).any():
            raise RuntimeError(f"Draw for {component} {year} spans years")
        rates = imputation.diagnostics[component][str(year)][
            "ce_participation_rate_by_implicate"
        ]
        for m in implicates:
            takes[component][m][positions] = draw_takes[m]
            rate = _weighted_rate(draw_takes[m], weight[positions])
            if not np.isclose(rate, rates[m], rtol=1e-12, atol=0.0):
                raise RuntimeError(
                    f"Recorded {component} draws for {year}, implicate {m}, "
                    "do not give the imputation's participation rate"
                )
    renter = ce["cutenure"].to_numpy() == 4
    assisted = renter & ce["housing_assistance"].to_numpy(dtype=bool)
    if "rental_assistance" in config.components:
        for year in years:
            in_year = renter & (reference_year == year)
            rate = (
                _weighted_rate(assisted[in_year], weight[in_year])
                if in_year.any()
                else 0.0
            )
            recorded = imputation.diagnostics["rental_assistance"][str(year)][
                "ce_participation_rate_by_implicate"
            ]
            if not np.allclose(rate, recorded, rtol=1e-12, atol=0.0):
                raise RuntimeError(
                    f"Rental assistance participation for {year} differs "
                    "from the imputation's"
                )
    broad_only = imputation.implicates[0]["wic_broad_universe_only"].to_numpy(
        dtype=bool
    )
    modeled_broadband = reference_year >= config.broadband_first_reference_year
    frames = []
    for m in implicates:
        raw = imputation.implicates[m]
        if not np.array_equal(raw["NEWID"].to_numpy(dtype="int64"), keys):
            raise RuntimeError("Imputation rows are not in ce_units order")
        if not np.array_equal(
            raw["wic_broad_universe_only"].to_numpy(dtype=bool), broad_only
        ):
            raise RuntimeError("WIC universe flag differs across implicates")
        used = imputation.for_target(m, WIC_EXPORT_TARGET)
        amounts = {
            component: used[component].to_numpy(dtype=float)
            for component in IN_KIND_COMPONENTS
        }
        participant = {
            **{c: takes[c][m] for c in MODELED_COMPONENTS},
            "rental_assistance": assisted,
        }
        participant["wic"] = participant["wic"] & ~broad_only
        for component in IN_KIND_COMPONENTS:
            positive = amounts[component] > 0
            if (positive & ~participant[component]).any():
                raise RuntimeError(
                    f"{component}: a nonparticipant has a positive amount"
                )
        for component in ("liheap", "broadband"):
            if not np.array_equal(
                participant[component], amounts[component] > 0
            ):
                raise RuntimeError(
                    f"{component}: participation differs from amount > 0"
                )
        if (amounts["broadband"][~modeled_broadband] != 0).any():
            raise RuntimeError("Broadband is positive before its first year")
        frame = pd.DataFrame(
            {
                "NEWID": keys,
                "implicate": m + 1,
                "ce_year": ce["ce_year"].to_numpy(dtype=int),
                "ce_quarter": ce["ce_quarter"].to_numpy(dtype=int),
                "reference_year": reference_year,
                "wic_broad_universe_only": broad_only.astype("int8"),
            }
        )
        for component in IN_KIND_COMPONENTS:
            flag = pd.array(
                participant[component].astype("int8"), dtype="Int8"
            )
            if component == "broadband":
                flag[~modeled_broadband] = pd.NA
            frame[f"{component}_participant"] = flag
            frame[f"{component}_amount"] = amounts[component]
        frames.append(frame[list(COLUMNS)])
    return frames


def write_csv_gz(frames: list[pd.DataFrame], path: Path) -> dict:
    """Write the export as gzipped CSV, sorted by implicate and NEWID.

    Amounts are rounded to cents. The gzip header carries no file name or
    time, so the same frames give the same bytes with the same zlib.

    Returns:
        Row count and the SHA-256 and size of the CSV before and after
        compression.
    """
    table = pd.concat(frames, ignore_index=True).sort_values(
        ["implicate", "NEWID"], kind="stable"
    )
    amount_columns = [c for c in COLUMNS if c.endswith("_amount")]
    table[amount_columns] = table[amount_columns].round(2)
    text = table.to_csv(index=False, float_format="%.2f", lineterminator="\n")
    data = text.encode("ascii")
    path = Path(path)
    with (
        path.open("wb") as raw,
        gzip.GzipFile(
            filename="", mode="wb", compresslevel=9, fileobj=raw, mtime=0
        ) as stream,
    ):
        stream.write(data)
    return {
        "rows": int(len(table)),
        "csv_sha256": hashlib.sha256(data).hexdigest(),
        "csv_bytes": len(data),
        "csv_gz_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "csv_gz_bytes": path.stat().st_size,
    }


def read_csv_gz(path: Path) -> pd.DataFrame:
    """Read the export back as a user would, with pandas defaults."""
    return pd.read_csv(path)


#: Largest gap allowed between a written amount and the imputation's: half
#: a cent of rounding, plus float noise.
CENT_TOLERANCE = 0.005 + 1e-9

#: Largest distance, in cents, between a read-back amount and a whole number
#: of cents: parsing noise only.
CENT_GRID_TOLERANCE = 1e-6


def _leaf_integer(value) -> bool:
    return isinstance(value, (int, np.integer)) and not isinstance(
        value, (bool, np.bool_)
    )


def _leaf_number(value) -> bool:
    return isinstance(
        value, (int, float, np.integer, np.floating)
    ) and not isinstance(value, (bool, np.bool_))


def diagnostics_difference(ours, theirs, path: str = "") -> float:
    """Largest relative difference between two diagnostics trees.

    Integer leaves, such as unit counts, must be equal. Other numbers are
    compared by relative difference.

    Raises:
        RuntimeError: If the trees differ in structure, keys, any integer
            or any non-numeric value, or if either holds a NaN or infinity.
    """
    if isinstance(ours, dict) and isinstance(theirs, dict):
        if set(ours) != set(theirs):
            raise RuntimeError(f"Diagnostics keys differ at {path or '/'}")
        children = [(ours[k], theirs[k], f"{path}/{k}") for k in ours]
    elif isinstance(ours, list) and isinstance(theirs, list):
        if len(ours) != len(theirs):
            raise RuntimeError(f"Diagnostics lengths differ at {path}")
        children = [
            (a, b, f"{path}[{i}]")
            for i, (a, b) in enumerate(zip(ours, theirs))
        ]
    elif _leaf_integer(ours) and _leaf_integer(theirs):
        if int(ours) != int(theirs):
            raise RuntimeError(
                f"Diagnostics differ at {path}: {ours!r} != {theirs!r}"
            )
        return 0.0
    elif _leaf_number(ours) and _leaf_number(theirs):
        a, b = float(ours), float(theirs)
        if not (np.isfinite(a) and np.isfinite(b)):
            raise RuntimeError(
                f"Diagnostics hold a non-finite value at {path}"
            )
        if a == b:
            return 0.0
        return abs(a - b) / max(abs(a), abs(b))
    else:
        if _leaf_number(ours) or _leaf_number(theirs) or ours != theirs:
            raise RuntimeError(
                f"Diagnostics differ at {path}: {ours!r} != {theirs!r}"
            )
        return 0.0
    worst = 0.0
    for a, b, where in children:
        worst = max(worst, diagnostics_difference(a, b, where))
    return worst


def _flag_values(column: pd.Series, name: str) -> np.ndarray:
    values = column.to_numpy(dtype=float)
    if not np.isin(values, (0.0, 1.0)).all():
        raise RuntimeError(f"{name} holds values other than 0 and 1")
    return values


def verify_written(
    path: Path,
    frames: list[pd.DataFrame],
    ce_units: pd.DataFrame,
    diagnostics: dict,
    config: InKindConfig,
) -> dict:
    """Read the written file back and check it against the frames.

    Every column must read back with pandas defaults to the frames' values:
    keys and flags exactly, as integers (broadband's flag as numbers that
    are missing exactly before its first year), and amounts finite, in whole
    cents and within half a cent. Each implicate must cover every unit once, in implicate and
    ``NEWID`` order. Per-year weighted mean amounts must match the
    diagnostics' ``ce_mean_amount_per_unit`` within half a cent, except
    WIC, whose diagnostics value the broad universe.

    Raises:
        RuntimeError: On any difference.
    """
    table = read_csv_gz(path)
    if tuple(table.columns) != COLUMNS:
        raise RuntimeError("Written columns differ from the dictionary")
    expected = (
        pd.concat(frames, ignore_index=True)
        .sort_values(["implicate", "NEWID"], kind="stable")
        .reset_index(drop=True)
    )
    if len(table) != len(expected):
        raise RuntimeError("Written row count differs")
    first_year = config.broadband_first_reference_year
    for name in COLUMNS:
        got, want = table[name], expected[name]
        if name.endswith("_amount"):
            if not pd.api.types.is_numeric_dtype(got):
                raise RuntimeError(f"{name} does not read back as numbers")
            values = got.to_numpy(dtype=float)
            if not np.isfinite(values).all():
                raise RuntimeError(
                    f"{name} holds a missing or non-finite value"
                )
            cents = values * 100
            if not (
                np.abs(cents - np.round(cents)) <= CENT_GRID_TOLERANCE
            ).all():
                raise RuntimeError(f"{name} is not rounded to cents")
            gap = np.abs(values - want.to_numpy(dtype=float)).max()
            if not gap <= CENT_TOLERANCE:
                raise RuntimeError(f"{name} differs by more than rounding")
        elif name == "broadband_participant":
            if not (
                pd.api.types.is_float_dtype(got)
                or pd.api.types.is_integer_dtype(got)
            ):
                raise RuntimeError(f"{name} does not read back as numbers")
            missing = got.isna().to_numpy()
            if not np.array_equal(
                missing, table["reference_year"].to_numpy() < first_year
            ) or not np.array_equal(missing, want.isna().to_numpy()):
                raise RuntimeError(f"{name} is missing in the wrong rows")
            values = _flag_values(got[~missing], name)
            if not np.array_equal(
                values, want[~missing].to_numpy(dtype=float)
            ):
                raise RuntimeError(f"{name} differs")
        else:
            if not pd.api.types.is_integer_dtype(got):
                raise RuntimeError(f"{name} does not read back as integers")
            if name.endswith("_participant") or name == (
                "wic_broad_universe_only"
            ):
                _flag_values(got, name)
            if not np.array_equal(
                got.to_numpy(dtype="int64"), want.to_numpy(dtype="int64")
            ):
                raise RuntimeError(f"{name} differs")
    keys = np.sort(ce_units["key"].to_numpy(dtype="int64"))
    for m in range(config.implicates):
        rows = table.loc[table["implicate"] == m + 1, "NEWID"].to_numpy()
        if not np.array_equal(rows, keys):
            raise RuntimeError(
                f"Implicate {m + 1} does not cover every unit once, in order"
            )
    weight = pd.Series(
        ce_units["weight"].to_numpy(dtype=float),
        index=ce_units["key"].to_numpy(dtype="int64"),
    )
    table_weight = weight.loc[table["NEWID"].to_numpy()].to_numpy()
    worst = 0.0
    for component in IN_KIND_COMPONENTS:
        if component == "wic":
            continue
        for year, recorded in diagnostics[component].items():
            if "ce_mean_amount_per_unit" not in recorded:
                continue
            in_year = table["reference_year"].to_numpy() == int(year)
            means = []
            for m in range(config.implicates):
                rows = in_year & (table["implicate"].to_numpy() == m + 1)
                w = table_weight[rows]
                amount = table[f"{component}_amount"].to_numpy(dtype=float)
                means.append(float(np.sum(amount[rows] * w) / w.sum()))
            gap = abs(
                float(np.mean(means)) - recorded["ce_mean_amount_per_unit"]
            )
            if not gap <= CENT_TOLERANCE:
                raise RuntimeError(
                    f"Written {component} mean for {year} differs from the "
                    "diagnostics"
                )
            worst = max(worst, gap)
    return {
        "read_back_rows": int(len(table)),
        "newid_dtype": str(table["NEWID"].dtype),
        "max_mean_gap_vs_diagnostics_dollars": worst,
    }


def dictionary_csv() -> str:
    """The data dictionary as CSV text: column, type, description."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["column", "type", "description"])
    for column in DICTIONARY:
        writer.writerow([column.name, column.kind, column.description])
    return buffer.getvalue()


def dictionary_markdown() -> str:
    """The data dictionary as the Markdown table in the docs."""
    lines = ["| Column | Type | Description |", "|---|---|---|"]
    for column in DICTIONARY:
        lines.append(
            f"| `{column.name}` | {column.kind} | {column.description} |"
        )
    return "\n".join(lines) + "\n"
