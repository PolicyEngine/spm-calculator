"""Reproduce Census's published SPM poverty estimates from the CPS ASEC.

The Census Bureau publishes the Supplemental Poverty Measure (SPM) in its
annual P60 report. For calendar year 2025 that report is P60-290
(September 2026), computed from the 2026 Current Population Survey Annual
Social and Economic Supplement (CPS ASEC). The public-use release of the
same survey carries, for every person, the SPM unit's resources, threshold
and poverty status, the components of those resources, and 160 replicate
weights. This module rebuilds P60-290's SPM estimates from those fields:

- the SPM rate and its 90 percent margin of error for all people and by
  age (Table 5's first row);
- the effect of each resource element on the SPM rate (Table 5): the rate
  with every element minus the rate with one element removed from
  resources and every other element held fixed;
- the number and percentage of people in SPM poverty, with margins of
  error, by the characteristics in Table 4.

Census bases its published margins of error on standard errors computed
from replicate weights (P60-290 Table 4, note 2), and the public-use file
carries 160 of them. We compute standard errors with the successive
difference replication formula ``SE^2 = (4 / 160) * sum_r (theta_r -
theta_0)^2`` over those weights and report 90 percent margins of error as
``1.645 * SE``. Our margins differ from Census's Table 5 margins by at most
0.01 points; ``docs/census-spm-reproduction.md`` reports the comparison.

Variable names and codes follow Census's data dictionary for the release
(``asec2026_ddl_pub_full.pdf``). The module reads only pandas, numpy and
the standard library, so it runs wherever the package does.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

SURVEY_YEAR = 2026
REFERENCE_YEAR = 2025
ZIP_NAME = "asecpub26csv.zip"
ZIP_URL = (
    "https://www2.census.gov/programs-surveys/cps/datasets/2026/march/"
    + ZIP_NAME
)
ZIP_SHA256 = "fe819d0d2fc4470c282e76c247b8aa8b6054811619730307e9f2fe6186707d93"
ZIP_BYTES = 139103894
PERSON_MEMBER = "pppub26.csv"
HOUSEHOLD_MEMBER = "hhpub26.csv"
REPLICATE_MEMBER = "asec_csv_repwgt_2026.csv"

N_REPLICATES = 160
REPLICATE_FACTOR = 4.0 / N_REPLICATES
MOE_Z = 1.645

ADDITION = "addition"
SUBTRACTION = "subtraction"

#: Person columns read from ``pppub26.csv``.
PERSON_COLUMNS: Tuple[str, ...] = (
    "PH_SEQ",
    "PPPOS",
    "MARSUPWT",
    "A_AGE",
    "A_SEX",
    "PRDTRACE",
    "PEHSPNON",
    "PRCITSHP",
    "A_HGA",
    "WEXP",
    "PRDISFLG",
    "COV",
    "PRIV",
    "PUB",
    "PTOTVAL",
    "SS_VAL",
    "SSI_VAL",
    "PAW_VAL",
    "CSP_VAL",
    "UC_VAL",
    "WC_VAL",
    "TAX_ID",
    "DEP_STAT",
    "WSAL_VAL",
    "SEMP_VAL",
    "FRSE_VAL",
    "EIT_CRED",
    "ACTC_CRD",
    "CTC_CRD",
    "FEDTAX_BC",
    "FEDTAX_AC",
    "STATETAX_A",
    "FICA",
    "SPM_ID",
    "SPM_HEAD",
    "SPM_WEIGHT",
    "SPM_RESOURCES",
    "SPM_POVTHRESHOLD",
    "SPM_POOR",
    "SPM_TOTVAL",
    "SPM_SNAPSUB",
    "SPM_CAPHOUSESUB",
    "SPM_SCHLUNCH",
    "SPM_ENGVAL",
    "SPM_WICVAL",
    "SPM_FEDTAX",
    "SPM_FEDTAXBC",
    "SPM_EITC",
    "SPM_ACTC",
    "SPM_STTAX",
    "SPM_FICA",
    "SPM_CAPWKCCXPNS",
    "SPM_MEDXPNS",
    "SPM_CHILDSUPPD",
    "SPM_FAMTYPE",
    "SPM_TENMORTSTATUS",
)
HOUSEHOLD_COLUMNS: Tuple[str, ...] = (
    "H_SEQ",
    "GEREG",
    "GTMETSTA",
    "GTCBSAST",
)
#: SPM-unit columns, constant within an SPM unit in the public-use file.
#: SPM_FAMTYPE, which the data dictionary calls the "SPM unit's family
#: type", is left out: it varies across members of some units, and Table 4
#: reads each person's own value.
SPM_UNIT_COLUMNS: Tuple[str, ...] = tuple(
    c
    for c in PERSON_COLUMNS
    if c.startswith("SPM_") and c not in {"SPM_ID", "SPM_HEAD", "SPM_FAMTYPE"}
)
REPLICATE_COLUMNS: Tuple[str, ...] = tuple(
    f"repwgt_{i}" for i in range(1, N_REPLICATES + 1)
)


# ---------------------------------------------------------------------------
# Input files
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def default_zip_path() -> Path:
    """Where the package's ASEC cache keeps the 2026 public-use zip.

    The cache directory is the one ``spm_calculator.cps_asec`` uses:
    ``$SPM_CALCULATOR_CPS_CACHE`` or ``~/.cache/spm-calculator/cps-asec``.
    """
    from .cps_asec import default_cache_dir

    return default_cache_dir() / ZIP_NAME


def ensure_zip(path: Optional[Path] = None, download: bool = False) -> Path:
    """Return the verified 2026 ASEC public-use zip.

    Args:
        path: Location of the zip. Defaults to :func:`default_zip_path`.
        download: Fetch the zip from Census when it is missing.

    Raises:
        FileNotFoundError: If the zip is missing and ``download`` is false.
        ValueError: If the file's SHA-256 differs from :data:`ZIP_SHA256`.
    """
    path = Path(path).expanduser() if path else default_zip_path()
    if not path.exists():
        if not download:
            raise FileNotFoundError(
                f"{path} not found. Download {ZIP_URL} there, or pass "
                "download=True."
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(path.suffix + ".part")
        urllib.request.urlretrieve(ZIP_URL, partial)
        digest = sha256_file(partial)
        if digest != ZIP_SHA256:
            raise ValueError(
                f"The download from {ZIP_URL} has SHA-256 {digest}, expected "
                f"{ZIP_SHA256}; it stays at {partial} for inspection."
            )
        partial.replace(path)
    digest = sha256_file(path)
    if digest != ZIP_SHA256:
        raise ValueError(
            f"{path} has SHA-256 {digest}, expected {ZIP_SHA256}. Census "
            "may have replaced the file; check its release notes first."
        )
    return path


def _read_member(
    archive: zipfile.ZipFile, name: str, columns: Sequence[str]
) -> pd.DataFrame:
    # ZipExtFile checks each member's CRC-32 when it reaches the end.
    with archive.open(name) as handle:
        return pd.read_csv(handle, usecols=list(columns))


def load_persons(zip_path: Optional[Path] = None) -> pd.DataFrame:
    """Read the person records this module needs from the public-use zip.

    Returns one row per person with :data:`PERSON_COLUMNS`, the household's
    region and metropolitan codes, ``weight`` (``MARSUPWT / 100``, people),
    ``weight_rep0`` (the replicate file's full-sample weight ``pwwgt0``)
    and ``repwgt_1`` to ``repwgt_160``.
    """
    path = ensure_zip(zip_path)
    with zipfile.ZipFile(path) as archive:
        persons = _read_member(archive, PERSON_MEMBER, PERSON_COLUMNS)
        households = _read_member(archive, HOUSEHOLD_MEMBER, HOUSEHOLD_COLUMNS)
        replicate_names = ["h_seq", "PPPOS"] + [
            f"pwwgt{i}" for i in range(0, N_REPLICATES + 1)
        ]
        replicates = _read_member(archive, REPLICATE_MEMBER, replicate_names)
    return assemble_persons(persons, households, replicates)


def assemble_persons(
    persons: pd.DataFrame,
    households: pd.DataFrame,
    replicates: pd.DataFrame,
) -> pd.DataFrame:
    """Join household codes and replicate weights onto person records."""
    households = households.rename(columns={"H_SEQ": "PH_SEQ"})
    out = persons.merge(
        households, on="PH_SEQ", how="left", validate="many_to_one"
    )
    if out["GEREG"].isna().any():
        raise ValueError("Some persons have no household record.")
    replicates = replicates.rename(
        columns={
            "h_seq": "PH_SEQ",
            "pwwgt0": "weight_rep0",
            **{f"pwwgt{i}": f"repwgt_{i}" for i in range(1, N_REPLICATES + 1)},
        }
    )
    out = out.merge(
        replicates,
        on=["PH_SEQ", "PPPOS"],
        how="left",
        validate="one_to_one",
    )
    if out[list(REPLICATE_COLUMNS)].isna().any().any():
        raise ValueError("Some persons have no replicate weights.")
    out = out.copy()  # Consolidate the merged blocks before adding a column.
    out["weight"] = out["MARSUPWT"] / 100.0
    return out.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Resource elements (Table 5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Element:
    """One element of SPM resources, as Table 5 of P60-290 names it.

    ``unit_columns`` hold SPM-unit totals already; ``person_columns`` hold
    person amounts that sum to the unit's value. Additions raise resources
    and subtractions lower them.
    """

    key: str
    label: str
    kind: str
    unit_columns: Tuple[str, ...] = ()
    person_columns: Tuple[str, ...] = ()
    published: bool = True


#: Table 5's elements in its order, plus state income tax, which resources
#: subtract but Table 5 does not show.
ELEMENTS: Tuple[Element, ...] = (
    Element(
        "social_security",
        "Social Security",
        ADDITION,
        person_columns=("SS_VAL",),
    ),
    Element(
        "refundable_tax_credits",
        "Refundable tax credits",
        ADDITION,
        unit_columns=("SPM_EITC", "SPM_ACTC"),
    ),
    Element(
        "eitc",
        "Earned Income Tax Credit (EITC)",
        ADDITION,
        unit_columns=("SPM_EITC",),
    ),
    Element("snap", "SNAP", ADDITION, unit_columns=("SPM_SNAPSUB",)),
    Element(
        "refundable_ctc",
        "Child Tax Credit (refundable portion)",
        ADDITION,
        unit_columns=("SPM_ACTC",),
    ),
    Element("ssi", "SSI", ADDITION, person_columns=("SSI_VAL",)),
    Element(
        "housing_subsidies",
        "Housing subsidies",
        ADDITION,
        unit_columns=("SPM_CAPHOUSESUB",),
    ),
    Element(
        "school_lunch",
        "School lunch",
        ADDITION,
        unit_columns=("SPM_SCHLUNCH",),
    ),
    Element(
        "child_support_received",
        "Child support received",
        ADDITION,
        person_columns=("CSP_VAL",),
    ),
    Element(
        "tanf",
        "TANF/general assistance",
        ADDITION,
        person_columns=("PAW_VAL",),
    ),
    Element(
        "unemployment_insurance",
        "Unemployment insurance",
        ADDITION,
        person_columns=("UC_VAL",),
    ),
    Element(
        "energy_assistance",
        "Energy assistance",
        ADDITION,
        unit_columns=("SPM_ENGVAL",),
    ),
    Element("wic", "WIC", ADDITION, unit_columns=("SPM_WICVAL",)),
    Element(
        "workers_compensation",
        "Workers' compensation",
        ADDITION,
        person_columns=("WC_VAL",),
    ),
    Element(
        "child_support_paid",
        "Child support paid",
        SUBTRACTION,
        unit_columns=("SPM_CHILDSUPPD",),
    ),
    Element(
        "federal_income_tax",
        "Federal income tax",
        SUBTRACTION,
        unit_columns=("SPM_FEDTAXBC",),
    ),
    Element(
        "work_expenses",
        "Work expenses",
        SUBTRACTION,
        unit_columns=("SPM_CAPWKCCXPNS",),
    ),
    Element("fica", "FICA", SUBTRACTION, unit_columns=("SPM_FICA",)),
    Element(
        "medical_expenses",
        "Medical expenses",
        SUBTRACTION,
        unit_columns=("SPM_MEDXPNS",),
    ),
    Element(
        "state_income_tax",
        "State income tax",
        SUBTRACTION,
        unit_columns=("SPM_STTAX",),
        published=False,
    ),
)
ELEMENTS_BY_KEY: Dict[str, Element] = {e.key: e for e in ELEMENTS}

#: Every public-use field behind a published Table 5 element.
PUBLISHED_ELEMENT_COLUMNS: Tuple[str, ...] = tuple(
    sorted(
        {
            column
            for e in ELEMENTS
            if e.published
            for column in e.unit_columns + e.person_columns
        }
    )
)


def element_values(persons: pd.DataFrame, element: Element) -> np.ndarray:
    """Each person's SPM-unit amount of one element."""
    total = np.zeros(len(persons))
    for column in element.unit_columns:
        total = total + persons[column].to_numpy(dtype=float)
    for column in element.person_columns:
        total = total + (
            persons.groupby("SPM_ID")[column]
            .transform("sum")
            .to_numpy(dtype=float)
        )
    return total


def counterfactual_resources(
    resources: np.ndarray, values: np.ndarray, kind: str
) -> np.ndarray:
    """Resources with one element removed and every other element fixed.

    Removing an addition lowers resources by its amount; removing a
    subtraction raises them by its amount.
    """
    if kind == ADDITION:
        return resources - values
    if kind == SUBTRACTION:
        return resources + values
    raise ValueError(f"Unknown element kind {kind!r}")


# ---------------------------------------------------------------------------
# Poverty, rates and replicate standard errors
# ---------------------------------------------------------------------------


def poverty_flags(resources: np.ndarray, thresholds: np.ndarray) -> np.ndarray:
    """A person is in SPM poverty when unit resources fall below the threshold.

    The comparison is strict: resources equal to the threshold are not poor.
    """
    return np.asarray(resources, dtype=float) < np.asarray(
        thresholds, dtype=float
    )


def weight_matrix(persons: pd.DataFrame) -> np.ndarray:
    """Columns: the full-sample person weight, then the 160 replicates."""
    columns = ["weight", *REPLICATE_COLUMNS]
    return persons[columns].to_numpy(dtype=float)


def replicate_se(estimates: np.ndarray) -> np.ndarray:
    """Successive difference replication SE over the last axis.

    The last axis holds the full-sample estimate followed by the replicate
    estimates.
    """
    estimates = np.asarray(estimates, dtype=float)
    n_replicates = estimates.shape[-1] - 1
    deviations = estimates[..., 1:] - estimates[..., :1]
    return np.sqrt(4.0 / n_replicates * np.square(deviations).sum(axis=-1))


def margin_of_error(estimates: np.ndarray) -> np.ndarray:
    """Census's 90 percent margin of error, ``1.645 * SE``."""
    return MOE_Z * replicate_se(estimates)


def group_totals(
    values: np.ndarray, groups: np.ndarray, weights: np.ndarray
) -> np.ndarray:
    """Weighted totals of ``values`` within each group, per weight column.

    Args:
        values: Person values, shape ``(n_persons,)``.
        groups: Membership, shape ``(n_persons, n_groups)``.
        weights: Weights, shape ``(n_persons, n_weights)``.

    Returns:
        Array of shape ``(n_groups, n_weights)``.
    """
    member = np.asarray(groups, dtype=float)
    return (member * np.asarray(values, dtype=float)[:, None]).T @ weights


def group_rates(
    flags: np.ndarray, groups: np.ndarray, weights: np.ndarray
) -> np.ndarray:
    """Weighted share of each group flagged, per weight column.

    An empty group has no rate; it comes back as NaN without a warning.
    """
    numerator = group_totals(flags, groups, weights)
    denominator = np.asarray(groups, dtype=float).T @ weights
    with np.errstate(invalid="ignore", divide="ignore"):
        return numerator / denominator


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

TABLE5_GROUPS: Tuple[str, ...] = (
    "All people",
    "Under 18 years",
    "18 to 64 years",
    "65 years and older",
)


def age_groups(persons: pd.DataFrame) -> np.ndarray:
    """Membership in Table 5's four groups, in :data:`TABLE5_GROUPS` order."""
    age = persons["A_AGE"].to_numpy()
    return np.column_stack(
        [
            np.ones(len(persons), dtype=bool),
            age < 18,
            (age >= 18) & (age < 65),
            age >= 65,
        ]
    )


@dataclass(frozen=True)
class Table4Row:
    """One row of P60-290 Table 4 and how the public-use file defines it.

    ``identifiable`` is false where the public-use file cannot place every
    person in the row: it leaves some households' metropolitan or
    principal-city status unidentified.
    """

    section: str
    label: str
    mask: Callable[[pd.DataFrame], np.ndarray]
    definition: str = ""
    identifiable: bool = True
    note: str = ""


def _age(p: pd.DataFrame) -> pd.Series:
    return p["A_AGE"]


def _working_age(p: pd.DataFrame) -> pd.Series:
    return (p["A_AGE"] >= 18) & (p["A_AGE"] < 65)


def _adult_25(p: pd.DataFrame) -> pd.Series:
    return p["A_AGE"] >= 25


_UNIDENTIFIED_METRO = (
    "The public-use file leaves some households' metropolitan status "
    "unidentified (GTMETSTA = 3)."
)
_UNIDENTIFIED_CITY = (
    "The public-use file leaves some households' principal-city status "
    "unidentified (GTCBSAST = 4)."
)

TABLE4_ROWS: Tuple[Table4Row, ...] = (
    Table4Row(
        "",
        "All people",
        lambda p: np.ones(len(p), dtype=bool),
        definition="Everyone",
    ),
    Table4Row(
        "Sex", "Male", lambda p: p["A_SEX"] == 1, definition="A_SEX = 1"
    ),
    Table4Row(
        "Sex", "Female", lambda p: p["A_SEX"] == 2, definition="A_SEX = 2"
    ),
    Table4Row(
        "Age",
        "Under 18 years",
        lambda p: _age(p) < 18,
        definition="A_AGE < 18",
    ),
    Table4Row(
        "Age", "18 to 64 years", _working_age, definition="18 <= A_AGE < 65"
    ),
    Table4Row(
        "Age",
        "65 years and older",
        lambda p: _age(p) >= 65,
        definition="A_AGE >= 65",
    ),
    Table4Row(
        "Type of Unit",
        "Married couple",
        lambda p: p["SPM_FAMTYPE"] == 1,
        definition="SPM_FAMTYPE = 1",
    ),
    Table4Row(
        "Type of Unit",
        "Cohabiting partners",
        lambda p: p["SPM_FAMTYPE"] == 2,
        definition="SPM_FAMTYPE = 2",
    ),
    Table4Row(
        "Type of Unit",
        "Female reference person",
        lambda p: p["SPM_FAMTYPE"] == 3,
        definition="SPM_FAMTYPE = 3",
    ),
    Table4Row(
        "Type of Unit",
        "Male reference person",
        lambda p: p["SPM_FAMTYPE"] == 4,
        definition="SPM_FAMTYPE = 4",
    ),
    Table4Row(
        "Type of Unit",
        "Unrelated individuals",
        lambda p: p["SPM_FAMTYPE"] == 5,
        definition="SPM_FAMTYPE = 5",
    ),
    Table4Row(
        "Race and Hispanic Origin",
        "White",
        lambda p: p["PRDTRACE"] == 1,
        definition="PRDTRACE = 1",
    ),
    Table4Row(
        "Race and Hispanic Origin",
        "White, not Hispanic",
        lambda p: (p["PRDTRACE"] == 1) & (p["PEHSPNON"] == 2),
        definition="PRDTRACE = 1 and PEHSPNON = 2",
    ),
    Table4Row(
        "Race and Hispanic Origin",
        "Black",
        lambda p: p["PRDTRACE"] == 2,
        definition="PRDTRACE = 2",
    ),
    Table4Row(
        "Race and Hispanic Origin",
        "Asian",
        lambda p: p["PRDTRACE"] == 4,
        definition="PRDTRACE = 4",
    ),
    Table4Row(
        "Race and Hispanic Origin",
        "American Indian and Alaska Native",
        lambda p: p["PRDTRACE"] == 3,
        definition="PRDTRACE = 3",
    ),
    Table4Row(
        "Race and Hispanic Origin",
        "Two or More Races",
        lambda p: p["PRDTRACE"] >= 6,
        definition="PRDTRACE >= 6",
    ),
    Table4Row(
        "Race and Hispanic Origin",
        "Hispanic (any race)",
        lambda p: p["PEHSPNON"] == 1,
        definition="PEHSPNON = 1",
    ),
    Table4Row(
        "Nativity",
        "Native-born",
        lambda p: p["PRCITSHP"].isin([1, 2, 3]),
        definition="PRCITSHP in 1-3",
    ),
    Table4Row(
        "Nativity",
        "Foreign-born",
        lambda p: p["PRCITSHP"].isin([4, 5]),
        definition="PRCITSHP in 4-5",
    ),
    Table4Row(
        "Nativity",
        "Naturalized citizen",
        lambda p: p["PRCITSHP"] == 4,
        definition="PRCITSHP = 4",
    ),
    Table4Row(
        "Nativity",
        "Not a citizen",
        lambda p: p["PRCITSHP"] == 5,
        definition="PRCITSHP = 5",
    ),
    Table4Row(
        "Educational Attainment",
        "Total, 25 years old and older",
        _adult_25,
        definition="A_AGE >= 25",
    ),
    Table4Row(
        "Educational Attainment",
        "No high school diploma",
        lambda p: _adult_25(p) & (p["A_HGA"] <= 38),
        definition="A_AGE >= 25 and A_HGA <= 38",
    ),
    Table4Row(
        "Educational Attainment",
        "High school, no college",
        lambda p: _adult_25(p) & (p["A_HGA"] == 39),
        definition="A_AGE >= 25 and A_HGA = 39",
    ),
    Table4Row(
        "Educational Attainment",
        "Some college",
        lambda p: _adult_25(p) & p["A_HGA"].isin([40, 41, 42]),
        definition="A_AGE >= 25 and A_HGA in 40-42",
    ),
    Table4Row(
        "Educational Attainment",
        "Bachelor's degree or higher",
        lambda p: _adult_25(p) & (p["A_HGA"] >= 43),
        definition="A_AGE >= 25 and A_HGA >= 43",
    ),
    Table4Row(
        "Tenure",
        "Owner/mortgage",
        lambda p: p["SPM_TENMORTSTATUS"] == 1,
        definition="SPM_TENMORTSTATUS = 1",
    ),
    Table4Row(
        "Tenure",
        "Owner/no mortgage/rent free",
        lambda p: p["SPM_TENMORTSTATUS"] == 2,
        definition="SPM_TENMORTSTATUS = 2",
    ),
    Table4Row(
        "Tenure",
        "Renter",
        lambda p: p["SPM_TENMORTSTATUS"] == 3,
        definition="SPM_TENMORTSTATUS = 3",
    ),
    Table4Row(
        "Residence",
        "Inside metropolitan statistical areas",
        lambda p: p["GTMETSTA"] == 1,
        definition="GTMETSTA = 1",
        identifiable=False,
        note=_UNIDENTIFIED_METRO,
    ),
    Table4Row(
        "Residence",
        "Inside principal cities",
        lambda p: (p["GTMETSTA"] == 1) & (p["GTCBSAST"] == 1),
        definition="GTMETSTA = 1 and GTCBSAST = 1",
        identifiable=False,
        note=_UNIDENTIFIED_CITY,
    ),
    Table4Row(
        "Residence",
        "Outside principal cities",
        lambda p: (p["GTMETSTA"] == 1) & (p["GTCBSAST"] == 2),
        definition="GTMETSTA = 1 and GTCBSAST = 2",
        identifiable=False,
        note=_UNIDENTIFIED_CITY,
    ),
    Table4Row(
        "Residence",
        "Outside metropolitan statistical areas",
        lambda p: p["GTMETSTA"] == 2,
        definition="GTMETSTA = 2",
        identifiable=False,
        note=_UNIDENTIFIED_METRO,
    ),
    Table4Row(
        "Region",
        "Northeast",
        lambda p: p["GEREG"] == 1,
        definition="GEREG = 1",
    ),
    Table4Row(
        "Region", "Midwest", lambda p: p["GEREG"] == 2, definition="GEREG = 2"
    ),
    Table4Row(
        "Region", "South", lambda p: p["GEREG"] == 3, definition="GEREG = 3"
    ),
    Table4Row(
        "Region", "West", lambda p: p["GEREG"] == 4, definition="GEREG = 4"
    ),
    Table4Row(
        "Health Insurance Coverage",
        "With private insurance",
        lambda p: p["PRIV"] == 1,
        definition="PRIV = 1",
    ),
    Table4Row(
        "Health Insurance Coverage",
        "With public, no private insurance",
        lambda p: (p["PUB"] == 1) & (p["PRIV"] != 1),
        definition="PUB = 1 and PRIV != 1",
    ),
    # COV = 0 marks infants born after the calendar year. Counting them as
    # not insured reproduces the published row; the reproduction's
    # "alternatives" block reports the row without them.
    Table4Row(
        "Health Insurance Coverage",
        "Not insured",
        lambda p: p["COV"].isin([0, 2]),
        definition="COV in {0, 2}",
    ),
    Table4Row(
        "Work Experience",
        "Total, 18 to 64 years old",
        _working_age,
        definition="18 <= A_AGE < 65",
    ),
    Table4Row(
        "Work Experience",
        "All workers",
        lambda p: _working_age(p) & p["WEXP"].between(1, 12),
        definition="18 <= A_AGE < 65 and WEXP in 1-12",
    ),
    Table4Row(
        "Work Experience",
        "Worked full-time, year-round",
        lambda p: _working_age(p) & (p["WEXP"] == 1),
        definition="18 <= A_AGE < 65 and WEXP = 1",
    ),
    Table4Row(
        "Work Experience",
        "Less than full-time, year-round",
        lambda p: _working_age(p) & p["WEXP"].between(2, 12),
        definition="18 <= A_AGE < 65 and WEXP in 2-12",
    ),
    Table4Row(
        "Work Experience",
        "Did not work",
        lambda p: _working_age(p) & (p["WEXP"] == 13),
        definition="18 <= A_AGE < 65 and WEXP = 13",
    ),
    Table4Row(
        "Disability Status",
        "Total, 18 to 64 years old",
        _working_age,
        definition="18 <= A_AGE < 65",
    ),
    Table4Row(
        "Disability Status",
        "With a disability",
        lambda p: _working_age(p) & (p["PRDISFLG"] == 1),
        definition="18 <= A_AGE < 65 and PRDISFLG = 1",
    ),
    Table4Row(
        "Disability Status",
        "With no disability",
        lambda p: _working_age(p) & (p["PRDISFLG"] == 2),
        definition="18 <= A_AGE < 65 and PRDISFLG = 2",
    ),
)


def table4_masks(
    persons: pd.DataFrame, rows: Sequence[Table4Row] = TABLE4_ROWS
) -> np.ndarray:
    """Membership in each row, by default every Table 4 row in order."""
    return np.column_stack(
        [np.asarray(row.mask(persons), dtype=bool) for row in rows]
    )


# ---------------------------------------------------------------------------
# Identity checks
# ---------------------------------------------------------------------------

#: SPM-unit tax fields and the tax-unit fields they sum.
TAX_FIELD_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("SPM_EITC", "EIT_CRED"),
    ("SPM_ACTC", "ACTC_CRD"),
    ("SPM_FEDTAXBC", "FEDTAX_BC"),
    ("SPM_FEDTAX", "FEDTAX_AC"),
    ("SPM_STTAX", "STATETAX_A"),
    ("SPM_FICA", "FICA"),
)


def resources_from_components(persons: pd.DataFrame) -> pd.Series:
    """Rebuild SPM resources from the file's components.

    Cash income plus SNAP, housing, school lunch, energy and WIC, less
    federal income tax after refundable credits, state income tax, FICA,
    capped work and child care expenses, medical expenses and child
    support paid.
    """
    p = persons
    return (
        p["SPM_TOTVAL"]
        + p["SPM_SNAPSUB"]
        + p["SPM_CAPHOUSESUB"]
        + p["SPM_SCHLUNCH"]
        + p["SPM_ENGVAL"]
        + p["SPM_WICVAL"]
        - p["SPM_FEDTAX"]
        - p["SPM_STTAX"]
        - p["SPM_FICA"]
        - p["SPM_CAPWKCCXPNS"]
        - p["SPM_MEDXPNS"]
        - p["SPM_CHILDSUPPD"]
    )


def check_identities(persons: pd.DataFrame) -> Dict[str, float]:
    """Check how the file assembles SPM resources and poverty.

    Every check in :data:`ZERO_CHECKS` comes out zero on the 2026
    public-use file, and the reproduction relies on each of them. The
    others only inform: ``weight_rep0_max_gap``, the largest difference
    between the replicate file's full-sample weight and ``MARSUPWT / 100``
    (about 0.005 people on the 2026 file); the SPM units whose members carry
    different SPM_FAMTYPE codes; the people with a negative amount in any
    published element's field; and the people with negative state income
    tax.
    """
    p = persons
    by_unit = p.groupby("SPM_ID")
    varies = by_unit[list(SPM_UNIT_COLUMNS)].nunique().gt(1).any(axis=1)
    famtype_varies = by_unit["SPM_FAMTYPE"].nunique().gt(1)
    heads = by_unit["SPM_HEAD"].sum()
    tax_unit_spm = p.groupby("TAX_ID")["SPM_ID"].nunique()
    federal_rebuilt = p["SPM_FEDTAXBC"] - p["SPM_EITC"] - p["SPM_ACTC"]
    poor = poverty_flags(
        p["SPM_RESOURCES"].to_numpy(), p["SPM_POVTHRESHOLD"].to_numpy()
    )
    checks = {
        "resources_identity_max_gap": float(
            (resources_from_components(p) - p["SPM_RESOURCES"]).abs().max()
        ),
        "poor_flag_mismatches": int((poor != (p["SPM_POOR"] == 1)).sum()),
        "federal_tax_identity_max_gap": float(
            (federal_rebuilt - p["SPM_FEDTAX"]).abs().max()
        ),
        "cash_income_identity_max_gap": float(
            (by_unit["PTOTVAL"].transform("sum") - p["SPM_TOTVAL"]).abs().max()
        ),
        "units_with_varying_spm_fields": int(varies.sum()),
        "units_with_varying_famtype": int(famtype_varies.sum()),
        "persons_in_units_with_varying_famtype": int(
            p["SPM_ID"].isin(famtype_varies[famtype_varies].index).sum()
        ),
        "persons_with_negative_published_element": int(
            (p[list(PUBLISHED_ELEMENT_COLUMNS)] < 0).any(axis=1).sum()
        ),
        "persons_with_negative_state_tax": int((p["SPM_STTAX"] < 0).sum()),
        "units_without_one_head": int((heads != 1).sum()),
        "tax_units_spanning_spm_units": int((tax_unit_spm > 1).sum()),
        "persons_without_replicate_weights": int(
            p[list(REPLICATE_COLUMNS)].isna().any(axis=1).sum()
        ),
        "negative_weights": int(
            (p[["weight", *REPLICATE_COLUMNS]] < 0).any(axis=1).sum()
        ),
        "weight_rep0_max_gap": float(
            (p["weight_rep0"] - p["weight"]).abs().max()
        ),
    }
    for spm_column, tax_column in TAX_FIELD_PAIRS:
        gap = (by_unit[tax_column].transform("sum") - p[spm_column]).abs()
        checks[f"{spm_column.lower()}_vs_{tax_column.lower()}_max_gap"] = (
            float(gap.max())
        )
    return checks


#: Checks that must come out exactly zero. ``weight_rep0_max_gap`` may
#: differ by rounding; :data:`WEIGHT_REP0_TOLERANCE` bounds it.
ZERO_CHECKS: Tuple[str, ...] = (
    "resources_identity_max_gap",
    "poor_flag_mismatches",
    "federal_tax_identity_max_gap",
    "cash_income_identity_max_gap",
    "units_with_varying_spm_fields",
    "units_without_one_head",
    "tax_units_spanning_spm_units",
    "persons_without_replicate_weights",
    "negative_weights",
    *(f"{s.lower()}_vs_{t.lower()}_max_gap" for s, t in TAX_FIELD_PAIRS),
)
WEIGHT_REP0_TOLERANCE = 0.01


def failed_identities(checks: Dict[str, float]) -> List[str]:
    """Names of identity checks that did not pass."""
    failed = [name for name in ZERO_CHECKS if checks.get(name) != 0]
    if not checks.get("weight_rep0_max_gap", math.inf) <= (
        WEIGHT_REP0_TOLERANCE
    ):
        failed.append("weight_rep0_max_gap")
    return failed


# ---------------------------------------------------------------------------
# Estimates
# ---------------------------------------------------------------------------


def estimate_table5(
    persons: pd.DataFrame,
    weights: Optional[np.ndarray] = None,
    elements: Iterable[Element] = ELEMENTS,
) -> Dict[str, Dict[str, List[float]]]:
    """SPM rates and element effects for Table 5's groups, in percent.

    Returns a mapping from ``"spm_rate"`` and each element key to
    ``{"estimate": [...], "moe": [...]}`` in :data:`TABLE5_GROUPS` order.
    An element's effect is the SPM rate minus the rate without that
    element. Removing an addition with nonnegative amounts can only raise
    the rate, so its effect is zero or negative; removing such a
    subtraction can only lower the rate, so its effect is zero or positive.
    State income tax, whose amounts can be negative, can go either way.
    """
    weights = weight_matrix(persons) if weights is None else weights
    groups = age_groups(persons)
    resources = persons["SPM_RESOURCES"].to_numpy(dtype=float)
    thresholds = persons["SPM_POVTHRESHOLD"].to_numpy(dtype=float)
    base = group_rates(poverty_flags(resources, thresholds), groups, weights)
    out = {"spm_rate": _pack(100.0 * base)}
    for element in elements:
        values = element_values(persons, element)
        without = counterfactual_resources(resources, values, element.kind)
        rates = group_rates(
            poverty_flags(without, thresholds), groups, weights
        )
        out[element.key] = _pack(100.0 * (base - rates))
    return out


def estimate_table4(
    persons: pd.DataFrame,
    weights: Optional[np.ndarray] = None,
    rows: Sequence[Table4Row] = TABLE4_ROWS,
) -> List[Dict[str, object]]:
    """Number (thousands) and percent in SPM poverty for each Table 4 row."""
    weights = weight_matrix(persons) if weights is None else weights
    masks = table4_masks(persons, rows)
    poor = poverty_flags(
        persons["SPM_RESOURCES"].to_numpy(dtype=float),
        persons["SPM_POVTHRESHOLD"].to_numpy(dtype=float),
    ).astype(float)
    number = group_totals(poor, masks, weights) / 1000.0
    percent = 100.0 * group_rates(poor, masks, weights)
    population = group_totals(np.ones(len(persons)), masks, weights)
    out = []
    for i, row in enumerate(rows):
        out.append(
            {
                "section": row.section,
                "label": row.label,
                "definition": row.definition,
                "identifiable": row.identifiable,
                "number_thousands": float(number[i, 0]),
                "number_moe": float(margin_of_error(number[i])),
                "percent": float(percent[i, 0]),
                "percent_moe": float(margin_of_error(percent[i])),
                "population_thousands": float(population[i, 0] / 1000.0),
                "persons": int(masks[:, i].sum()),
            }
        )
    return out


def _pack(estimates: np.ndarray) -> Dict[str, List[float]]:
    return {
        "estimate": [float(x) for x in estimates[:, 0]],
        "moe": [float(x) for x in margin_of_error(estimates)],
    }


def sample_counts(persons: pd.DataFrame) -> Dict[str, int]:
    """People, SPM units, households and tax units in the file."""
    return {
        "persons": int(len(persons)),
        "spm_units": int(persons["SPM_ID"].nunique()),
        "households": int(persons["PH_SEQ"].nunique()),
        "tax_units": int(persons["TAX_ID"].nunique()),
    }


# ---------------------------------------------------------------------------
# Alternative definitions
# ---------------------------------------------------------------------------

#: Definitions the reproduction reports beside its main ones, each with the
#: key of the published Table 5 row it competes with.
ALTERNATIVE_ELEMENTS: Tuple[Tuple[Element, str], ...] = (
    (
        Element(
            "federal_income_tax_after_credits",
            "Federal income tax after refundable credits",
            SUBTRACTION,
            unit_columns=("SPM_FEDTAX",),
            published=False,
        ),
        "federal_income_tax",
    ),
)


#: Table 4 rows defined another way, each with the label of the published
#: row it competes with.
def _head_famtype(p: pd.DataFrame) -> pd.Series:
    """Each person's SPM unit head's SPM_FAMTYPE."""
    heads = p.loc[p["SPM_HEAD"] == 1].set_index("SPM_ID")["SPM_FAMTYPE"]
    return p["SPM_ID"].map(heads)


ALTERNATIVE_TABLE4_ROWS: Tuple[Tuple[Table4Row, str], ...] = (
    (
        Table4Row(
            "Type of Unit",
            "Cohabiting partners, by the unit head's code",
            lambda p: _head_famtype(p) == 2,
            definition="SPM_FAMTYPE of the unit's SPM_HEAD = 2",
        ),
        "Cohabiting partners",
    ),
    (
        Table4Row(
            "Health Insurance Coverage",
            "Not insured, without infants born after the calendar year",
            lambda p: p["COV"] == 2,
            definition="COV = 2",
        ),
        "Not insured",
    ),
)


# ---------------------------------------------------------------------------
# The refundable Child Tax Credit's response to the EITC
# ---------------------------------------------------------------------------

#: The 2025 Child Tax Credit parameters, as PolicyEngine US 2.2.1 sets them
#: under ``gov.irs.credits.ctc``: the credit per qualifying child
#: (``amount.base``) and per other dependent (``amount.adult_dependent``),
#: the refundable maximum per child (``refundable.individual_max``), and the
#: phase-in threshold, rate and minimum number of children for the payroll
#: tax alternative (``refundable.phase_in``).
CTC_2025: Dict[str, float] = {
    "amount_per_child": 2200.0,
    "amount_per_other_dependent": 500.0,
    "refundable_max_per_child": 1700.0,
    "phase_in_threshold": 2500.0,
    "phase_in_rate": 0.15,
    "min_children_for_payroll_alternative": 3,
}
#: Age below which a dependent counts as a qualifying child.
CTC_CHILD_AGE_LIMIT = 17
#: The employee's Social Security tax rate, the 2025 wage base it applies
#: to and the employee's Medicare tax rate, as PolicyEngine US 2.2.1 sets
#: them (``gov.irs.payroll.social_security.rate.employee``,
#: ``gov.irs.payroll.social_security.cap`` and
#: ``gov.irs.payroll.medicare.rate.employee``).
EMPLOYEE_SOCIAL_SECURITY_RATE = 0.062
SOCIAL_SECURITY_WAGE_BASE_2025 = 176_100.0
EMPLOYEE_MEDICARE_RATE = 0.0145
#: The share of self-employment tax that 26 U.S.C. 164(f) deducts
#: (``gov.irs.ald.self_employment_tax.percent_deductible``).
SELF_EMPLOYMENT_TAX_DEDUCTIBLE_SHARE = 0.5
#: The file records credits in whole dollars, so comparisons allow a dollar.
CREDIT_TOLERANCE = 1.0
#: The tax-unit columns that hold earned income as 26 U.S.C. 32(c)(2)
#: defines it, after the section 164(f) deduction, and earnings before it.
EARNINGS = "earnings"
EARNINGS_BEFORE_DEDUCTION = "earnings_before_deduction"
#: The two versions of the rule that :func:`credit_interaction` reports:
#: the statute's, and one whose earnings skip the section 164(f) deduction.
RULE_EARNINGS = {
    "statute": EARNINGS,
    "before_deduction": EARNINGS_BEFORE_DEDUCTION,
}


def employee_payroll_tax(wages) -> np.ndarray:
    """The employee's Social Security and Medicare tax on ``wages``.

    Social Security tax applies to wages up to the 2025 wage base and
    Medicare tax to all wages; negative wages count as zero. It leaves out
    the additional Medicare tax.
    """
    wages = np.maximum(np.asarray(wages, dtype=float), 0.0)
    social_security = EMPLOYEE_SOCIAL_SECURITY_RATE * np.minimum(
        wages, SOCIAL_SECURITY_WAGE_BASE_2025
    )
    return social_security + EMPLOYEE_MEDICARE_RATE * wages


def self_employment_tax(persons: pd.DataFrame) -> np.ndarray:
    """Each person's self-employment tax, as the file's ``FICA`` carries it.

    Among filers with one source of earnings, ``FICA`` has a median of 7.65
    percent of wages and of about 14.13 percent of self-employment income
    (:func:`fica_shares`), the whole self-employment tax. For people whose
    self-employment and farm income sum above zero, this returns ``FICA``
    beyond :func:`employee_payroll_tax` on their wages; for everyone else
    it returns zero, and all of ``FICA`` counts as the employee's tax. The
    split approximates: any additional Medicare tax or federal retirement
    contribution that ``FICA`` holds for a self-employed person counts as
    self-employment tax.
    """
    fica = persons["FICA"].to_numpy(dtype=float)
    wages = persons["WSAL_VAL"].to_numpy(dtype=float)
    employee = np.minimum(fica, employee_payroll_tax(wages))
    self_employed = (
        persons["SEMP_VAL"].to_numpy(dtype=float)
        + persons["FRSE_VAL"].to_numpy(dtype=float)
    ) > 0
    return np.where(self_employed, fica - employee, 0.0)


def ctc_payroll_tax(persons: pd.DataFrame) -> np.ndarray:
    """Each person's payroll tax as the refundable CTC rule counts it.

    The rule counts the employee's tax in full and half of
    self-employment tax (26 U.S.C. 24(d)(2)(A); the
    ``self_employment_tax_ald`` in PolicyEngine US 2.2.1's
    ``ctc_social_security_tax``), so this returns ``FICA`` less half of
    :func:`self_employment_tax`.
    """
    fica = persons["FICA"].to_numpy(dtype=float)
    deduction = SELF_EMPLOYMENT_TAX_DEDUCTIBLE_SHARE * self_employment_tax(
        persons
    )
    return fica - deduction


def fica_shares(persons: pd.DataFrame) -> Dict[str, float]:
    """Median ``FICA`` as a share of earnings, for filers with one source.

    Covers filers (``DEP_STAT`` = 0) with $1,000 to $150,000 of wages and
    no self-employment or farm income, and filers with $1,000 to $150,000
    of self-employment income and no wages or farm income, and counts
    each group. The shares are medians over those groups: individual
    filers' shares differ.
    """
    p = persons.loc[persons["DEP_STAT"] == 0]
    in_range = lambda s: (s > 1000) & (s < 150_000)  # noqa: E731
    wages = p.loc[
        in_range(p["WSAL_VAL"]) & (p["SEMP_VAL"] == 0) & (p["FRSE_VAL"] == 0)
    ]
    self_employed = p.loc[
        in_range(p["SEMP_VAL"]) & (p["WSAL_VAL"] == 0) & (p["FRSE_VAL"] == 0)
    ]
    return {
        "wages": float((wages["FICA"] / wages["WSAL_VAL"]).median()),
        "self_employment": float(
            (self_employed["FICA"] / self_employed["SEMP_VAL"]).median()
        ),
        "wage_filers": int(len(wages)),
        "self_employment_filers": int(len(self_employed)),
    }


def ctc_tax_units(persons: pd.DataFrame) -> pd.DataFrame:
    """The inputs to the refundable CTC rule, one row per tax unit.

    Dependents are people whose ``DEP_STAT`` exceeds zero; qualifying
    children are dependents younger than :data:`CTC_CHILD_AGE_LIMIT` at the
    interview, and other dependents are the rest. Earned income
    (:data:`EARNINGS`) is the filers' wages, self-employment and farm
    income less the section 164(f) deduction, half of
    :func:`self_employment_tax`, as 26 U.S.C. 32(c)(2)(A)(ii) and
    PolicyEngine US 2.2.1's ``eitc_earned_income`` define it;
    :data:`EARNINGS_BEFORE_DEDUCTION` skips the deduction. Both are
    floored at zero for the unit. Payroll tax is the filers'
    :func:`ctc_payroll_tax`, and ``self_employed_filers`` counts filers
    whose self-employment and farm income sum above zero. The credits are
    the file's own: ``EIT_CRED``, ``ACTC_CRD`` and ``CTC_CRD`` (the
    nonrefundable credit for children and other dependents).
    """
    p = persons
    dependent = p["DEP_STAT"].to_numpy() > 0
    filer = ~dependent
    child = dependent & (p["A_AGE"].to_numpy() < CTC_CHILD_AGE_LIMIT)
    self_employment = p["SEMP_VAL"].to_numpy(dtype=float) + p[
        "FRSE_VAL"
    ].to_numpy(dtype=float)
    gross = p["WSAL_VAL"].to_numpy(dtype=float) + self_employment
    deduction = SELF_EMPLOYMENT_TAX_DEDUCTIBLE_SHARE * self_employment_tax(p)
    frame = pd.DataFrame(
        {
            "TAX_ID": p["TAX_ID"].to_numpy(),
            "SPM_ID": p["SPM_ID"].to_numpy(),
            "children": child.astype(int),
            "other_dependents": (dependent & ~child).astype(int),
            EARNINGS: np.where(filer, gross - deduction, 0.0),
            EARNINGS_BEFORE_DEDUCTION: np.where(filer, gross, 0.0),
            "payroll_tax": np.where(filer, ctc_payroll_tax(p), 0.0),
            "self_employed_filers": (filer & (self_employment > 0)).astype(
                int
            ),
            "eitc": p["EIT_CRED"].to_numpy(dtype=float),
            "actc": p["ACTC_CRD"].to_numpy(dtype=float),
            "nonrefundable_ctc": p["CTC_CRD"].to_numpy(dtype=float),
        }
    )
    units = frame.groupby("TAX_ID", sort=True).agg(
        SPM_ID=("SPM_ID", "first"),
        children=("children", "sum"),
        other_dependents=("other_dependents", "sum"),
        **{
            EARNINGS: (EARNINGS, "sum"),
            EARNINGS_BEFORE_DEDUCTION: (EARNINGS_BEFORE_DEDUCTION, "sum"),
        },
        payroll_tax=("payroll_tax", "sum"),
        self_employed_filers=("self_employed_filers", "sum"),
        eitc=("eitc", "sum"),
        actc=("actc", "sum"),
        nonrefundable_ctc=("nonrefundable_ctc", "sum"),
    )
    for column in (EARNINGS, EARNINGS_BEFORE_DEDUCTION):
        units[column] = units[column].clip(lower=0.0)
    return units


def ctc_earnings_branch(
    units: pd.DataFrame, earnings: str = EARNINGS
) -> np.ndarray:
    """Fifteen percent of each tax unit's ``earnings`` over $2,500."""
    excess = (
        units[earnings].to_numpy(dtype=float) - CTC_2025["phase_in_threshold"]
    )
    return CTC_2025["phase_in_rate"] * np.maximum(excess, 0.0)


def refundable_ctc_rule(
    units: pd.DataFrame, eitc, earnings: str = EARNINGS
) -> np.ndarray:
    """Each tax unit's refundable CTC under the 2025 rule, given its EITC.

    The credit is the smallest of the refundable maximum per child, the
    credit left after the nonrefundable part (``CTC_CRD``), and the greater
    of the earnings branch and, for units with at least three qualifying
    children, payroll tax less the EITC (26 U.S.C. 24(d)(1)(B);
    ``refundable_ctc`` and ``ctc_phase_in`` in PolicyEngine US 2.2.1).
    ``eitc`` is an array aligned with ``units`` or a scalar, and
    ``earnings`` names the column the earnings branch reads.
    """
    children = units["children"].to_numpy(dtype=float)
    total = CTC_2025["amount_per_child"] * children + CTC_2025[
        "amount_per_other_dependent"
    ] * units["other_dependents"].to_numpy(dtype=float)
    cap = np.minimum(
        CTC_2025["refundable_max_per_child"] * children,
        np.maximum(total - units["nonrefundable_ctc"].to_numpy(float), 0.0),
    )
    eitc = np.broadcast_to(np.asarray(eitc, dtype=float), children.shape)
    payroll = np.where(
        children >= CTC_2025["min_children_for_payroll_alternative"],
        np.maximum(units["payroll_tax"].to_numpy(dtype=float) - eitc, 0.0),
        0.0,
    )
    branch = ctc_earnings_branch(units, earnings)
    return np.minimum(cap, np.maximum(branch, payroll))


def rule_reproduces_credit(
    units: pd.DataFrame, earnings: str = EARNINGS
) -> np.ndarray:
    """Whether the rule gives each tax unit its ``ACTC_CRD``, within a dollar."""
    eitc = units["eitc"].to_numpy(dtype=float)
    rule = refundable_ctc_rule(units, eitc, earnings)
    actc = units["actc"].to_numpy(dtype=float)
    return np.abs(actc - rule) <= CREDIT_TOLERANCE


def ctc_response_to_eitc(
    units: pd.DataFrame, earnings: str = EARNINGS
) -> np.ndarray:
    """How much each tax unit's refundable CTC would rise without its EITC.

    The rule with the EITC set to zero less the rule with the file's EITC,
    for tax units whose credit the rule reproduces
    (:func:`rule_reproduces_credit`); zero for the rest. It is never
    negative and never exceeds the unit's EITC or its payroll tax, and it
    is zero for units with fewer than three qualifying children.
    """
    eitc = units["eitc"].to_numpy(dtype=float)
    with_eitc = refundable_ctc_rule(units, eitc, earnings)
    rise = refundable_ctc_rule(units, 0.0, earnings) - with_eitc
    return np.where(rule_reproduces_credit(units, earnings), rise, 0.0)


def eitc_net_of_ctc_response(
    persons: pd.DataFrame, earnings: str = EARNINGS
) -> np.ndarray:
    """Each person's SPM-unit EITC less the refundable CTC it would free.

    Removing this amount instead of ``SPM_EITC`` removes the EITC and lets
    each tax unit's refundable CTC rise as the rule allows.
    """
    units = ctc_tax_units(persons)
    response = pd.Series(
        ctc_response_to_eitc(units, earnings), index=units.index
    )
    by_unit = response.groupby(units["SPM_ID"]).sum()
    freed = persons["SPM_ID"].map(by_unit).fillna(0.0).to_numpy(dtype=float)
    return persons["SPM_EITC"].to_numpy(dtype=float) - freed


#: The EITC with the refundable CTC's response, which the note sets beside
#: the EITC row. Its amounts live in a column that
#: :func:`credit_interaction` adds.
EITC_WITH_CTC_RESPONSE = Element(
    "eitc_with_ctc_response",
    "EITC, letting the refundable CTC respond",
    ADDITION,
    unit_columns=("EITC_NET_OF_CTC_RESPONSE",),
    published=False,
)


def _rule_check(
    persons: pd.DataFrame,
    units: pd.DataFrame,
    weights: np.ndarray,
    earnings: str,
) -> Tuple[dict, np.ndarray, np.ndarray]:
    """One version of the rule, checked against the file's credits.

    Returns the summary :func:`credit_interaction` reports for it, whether
    the rule reproduces each unit's ``ACTC_CRD``, and which units with
    three or more qualifying children have an ``ACTC_CRD`` above the
    earnings branch.
    """
    actc = units["actc"].to_numpy(dtype=float)
    with_credit = actc > 0
    children = units["children"].to_numpy()
    three_plus = children >= CTC_2025["min_children_for_payroll_alternative"]
    one_or_two = (children >= 1) & ~three_plus
    matches = rule_reproduces_credit(units, earnings)
    branch = ctc_earnings_branch(units, earnings)
    above = with_credit & three_plus & (actc > branch + CREDIT_TOLERANCE)
    response = ctc_response_to_eitc(units, earnings)
    raised = units.loc[response > 0, "SPM_ID"].unique()
    in_raised = persons["SPM_ID"].isin(raised).to_numpy()
    net_eitc = eitc_net_of_ctc_response(persons, earnings)
    resources = persons["SPM_RESOURCES"].to_numpy(dtype=float)
    thresholds = persons["SPM_POVTHRESHOLD"].to_numpy(dtype=float)
    eitc_alone = poverty_flags(
        resources - persons["SPM_EITC"].to_numpy(dtype=float), thresholds
    )
    with_response = poverty_flags(resources - net_eitc, thresholds)
    with_column = persons.assign(EITC_NET_OF_CTC_RESPONSE=net_eitc)
    effect = estimate_table5(with_column, weights, [EITC_WITH_CTC_RESPONSE])
    with_eitc = units["eitc"].to_numpy() > 0
    summary = {
        "rule_matches": {
            "one_or_two_children": int(
                (with_credit & one_or_two & matches).sum()
            ),
            "three_or_more_children": int(
                (with_credit & three_plus & matches).sum()
            ),
        },
        "units_without_credit_not_reproduced": int(
            (~with_credit & ~matches).sum()
        ),
        "units_without_credit_not_reproduced_with_eitc": int(
            (~with_credit & ~matches & with_eitc).sum()
        ),
        "three_plus_above_earnings_branch": int(above.sum()),
        "three_plus_above_earnings_branch_reproduced": int(
            (above & matches).sum()
        ),
        "units_raised": int((response > 0).sum()),
        "persons_in_raised_units_thousands": float(
            persons["weight"].to_numpy(dtype=float)[in_raised].sum() / 1000.0
        ),
        "largest_rise_dollars": float(response.max(initial=0.0)),
        "persons_whose_status_changes": int(
            (eitc_alone != with_response).sum()
        ),
        "eitc_with_ctc_response": effect[EITC_WITH_CTC_RESPONSE.key],
    }
    return summary, matches, above


def credit_interaction(
    persons: pd.DataFrame, weights: Optional[np.ndarray] = None
) -> dict:
    """How the refundable CTC's payroll tax alternative bears on the EITC.

    Checks two versions of the 2025 rule against the file's credits
    (:data:`RULE_EARNINGS`): the statute's, whose earned income takes out
    the section 164(f) deduction, and one whose earnings skip it. For each
    it counts the tax units with a refundable CTC whose ``ACTC_CRD`` it
    reproduces within :data:`CREDIT_TOLERANCE`, by number of qualifying
    children; the units with three or more children whose ``ACTC_CRD``
    exceeds the earnings branch, which only the payroll tax alternative
    allows, and how many of them the rule reproduces; and the units whose
    credit would rise without the EITC. It then estimates the EITC's Table
    5 effect with that rise. It also describes the units with a credit
    that the statute's version misses.
    """
    weights = weight_matrix(persons) if weights is None else weights
    units = ctc_tax_units(persons)
    with_credit = units["actc"].to_numpy(dtype=float) > 0
    children = units["children"].to_numpy()
    three_plus = children >= CTC_2025["min_children_for_payroll_alternative"]
    one_or_two = (children >= 1) & ~three_plus
    checks = {
        name: _rule_check(persons, units, weights, column)
        for name, column in RULE_EARNINGS.items()
    }
    _, statute_matches, statute_above = checks["statute"]
    _, before_matches, _ = checks["before_deduction"]
    missed = with_credit & ~statute_matches
    self_employed = units["self_employed_filers"].to_numpy() > 0
    return {
        "fica_shares": fica_shares(persons),
        "social_security_wage_base": SOCIAL_SECURITY_WAGE_BASE_2025,
        "employee_social_security_rate": EMPLOYEE_SOCIAL_SECURITY_RATE,
        "employee_medicare_rate": EMPLOYEE_MEDICARE_RATE,
        "units_with_credit": {
            "one_or_two_children": int((with_credit & one_or_two).sum()),
            "three_or_more_children": int((with_credit & three_plus).sum()),
        },
        **{name: check[0] for name, check in checks.items()},
        "statute_misses": {
            "units": int(missed.sum()),
            "with_self_employment": int((missed & self_employed).sum()),
            "reproduced_before_deduction": int(
                (missed & before_matches).sum()
            ),
        },
        "statute_above_branch_reproduced_before_deduction": int(
            (statute_above & before_matches).sum()
        ),
    }


def unidentified_geography(persons: pd.DataFrame) -> Dict[str, float]:
    """People whose metropolitan or principal-city status the file hides."""
    weight = persons["weight"]
    metro = persons["GTMETSTA"] == 3
    city = persons["GTCBSAST"] == 4
    return {
        "metro_status_persons": int(metro.sum()),
        "metro_status_thousands": float(weight[metro].sum() / 1000.0),
        "principal_city_persons": int(city.sum()),
        "principal_city_thousands": float(weight[city].sum() / 1000.0),
    }


# ---------------------------------------------------------------------------
# Published tables
# ---------------------------------------------------------------------------

PUBLISHED_DIR = Path(__file__).parent / "data" / "census_spm" / "p60_290"
PUBLISHED_RECEIPT = PUBLISHED_DIR / "receipt.json"


def load_receipt() -> dict:
    """Source URLs and SHA-256 digests of the inputs."""
    return json.loads(PUBLISHED_RECEIPT.read_text())


def verified_table(name: str) -> Path:
    """Path to a bundled P60-290 workbook, after checking its SHA-256."""
    entry = load_receipt()["tables"][name]
    path = PUBLISHED_DIR / entry["file"]
    digest = sha256_file(path)
    if digest != entry["sha256"]:
        raise ValueError(
            f"{path} has SHA-256 {digest}, expected {entry['sha256']}."
        )
    return path


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and not value.strip()


def _clean_label(raw: object) -> str:
    """A row label without leader dots or trailing footnote numbers."""
    if _is_blank(raw):
        return ""
    label = str(raw).strip().lstrip(".").strip()
    # Census appends footnote numbers to some labels ("SNAP3").
    while label and label[-1].isdigit():
        label = label[:-1]
    return label.strip()


def _cell(value: object) -> Optional[float]:
    """A published number. "Z" (rounds to zero) reads as 0.0."""
    if _is_blank(value):
        return None
    if isinstance(value, str):
        text = value.strip()
        if text == "Z":
            return 0.0
        if text in {"N", "X"}:
            return None
        return float(text)
    return float(value)


def _cell_text(value: object) -> Optional[str]:
    """A Table 5 cell as printed: two decimals, or "Z"."""
    if _is_blank(value):
        return None
    if isinstance(value, str) and value.strip() in {"Z", "N", "X"}:
        return value.strip()
    return f"{float(value):.2f}"


#: Table 5's published row labels, after footnote numbers are removed.
TABLE5_LABELS: Dict[str, str] = {
    "SPM rate for all people": "spm_rate",
    **{e.label: e.key for e in ELEMENTS if e.published},
}


def published_table5(year: int = REFERENCE_YEAR) -> Dict[str, dict]:
    """Table 5 of P60-290 for one year, keyed like :func:`estimate_table5`.

    Each entry holds ``estimate`` and ``moe`` lists in
    :data:`TABLE5_GROUPS` order, and the same cells as printed in
    ``estimate_text`` and ``moe_text``. A published "Z" reads as 0.0.
    """
    sheet = pd.read_excel(verified_table("table_5"), header=None)
    start = None
    for i, raw in enumerate(sheet.iloc[:, 0]):
        text = "" if _is_blank(raw) else str(raw).strip()
        # Year rows look like "....2025"; the 2024 row carries a footnote
        # ("....20244").
        if text.startswith(".") and text.lstrip(".")[:4] == str(year):
            start = i + 1
            break
    if start is None:
        raise ValueError(f"Table 5 has no block for {year}.")
    out: Dict[str, dict] = {}
    for i in range(start, len(sheet)):
        raw = sheet.iloc[i, 0]
        text = "" if _is_blank(raw) else str(raw).strip()
        if text.startswith(".") or text.startswith("Element"):
            break  # The next year's block starts here.
        key = TABLE5_LABELS.get(_clean_label(raw))
        if key is None:
            continue
        cells = sheet.iloc[i, 1:9].tolist()
        out[key] = {
            "estimate": [_cell(v) for v in cells[0::2]],
            "moe": [_cell(v) for v in cells[1::2]],
            "estimate_text": [_cell_text(v) for v in cells[0::2]],
            "moe_text": [_cell_text(v) for v in cells[1::2]],
        }
    missing = sorted(set(TABLE5_LABELS.values()) - set(out))
    if missing:
        raise ValueError(f"Table 5 is missing rows: {missing}")
    return out


def published_table4() -> List[Dict[str, object]]:
    """Table 4 of P60-290 for 2025, in :data:`TABLE4_ROWS` order.

    Each entry holds the section, label, number in poverty and its margin
    (thousands), and the percentage and its margin. The 2025 columns are
    the workbook's sixth through ninth; the second through fifth hold 2024.
    The receipt's digest pins the workbook, so those positions cannot shift
    under the parser.
    """
    sheet = pd.read_excel(verified_table("table_4"), header=None)
    labels = [_clean_label(v) for v in sheet.iloc[:, 0]]
    if "All people" not in labels:
        raise ValueError("Table 4 has no 'All people' row.")
    start = labels.index("All people")
    section = ""
    found: Dict[Tuple[str, str], dict] = {}
    for i in range(start, len(sheet)):
        raw = sheet.iloc[i, 0]
        if not _is_blank(raw) and str(raw).strip().startswith("*"):
            break  # The footnotes start here.
        values = [_cell(v) for v in sheet.iloc[i, 5:9].tolist()]
        if all(v is None for v in values):
            # Section headers carry footnote numbers ("Race4 and
            # Hispanic Origin", "Residence5"); none has a digit of its own.
            section = " ".join(re.sub(r"\d+", "", labels[i]).split())
            continue
        found[(section, labels[i])] = {
            "section": section,
            "label": labels[i],
            "number_thousands": values[0],
            "number_moe": values[1],
            "percent": values[2],
            "percent_moe": values[3],
        }
    defined = [(r.section, r.label) for r in TABLE4_ROWS]
    missing = [key for key in defined if key not in found]
    extra = sorted(set(found) - set(defined))
    if missing or extra:
        raise ValueError(
            f"Table 4 rows differ from TABLE4_ROWS: missing {missing}, "
            f"extra {extra}"
        )
    return [found[key] for key in defined]


# ---------------------------------------------------------------------------
# Comparison with the published tables
# ---------------------------------------------------------------------------

#: Stated tolerances between our estimates and P60-290, in percentage
#: points unless named otherwise. Table 5 gaps compare our estimates,
#: rounded to the published two decimals, with the published values.
#: ``docs/census-spm-reproduction.md`` explains each one.
TOLERANCES: Dict[str, float] = {
    "table5_spm_rate": 0.01,
    "table5_spm_rate_moe": 0.01,
    "table5_effect": 0.06,
    "table5_effect_moe": 0.01,
    "table4_percent_moe": 0.1,
    "table4_number_moe_relative": 0.03,
}


def round_sig(value: float, digits: int = 4) -> float:
    """Round to ``digits`` significant digits, as Table 4's numbers are."""
    if value == 0 or not math.isfinite(value):
        return value
    exponent = digits - int(math.floor(math.log10(abs(value)))) - 1
    return round(value, exponent)


def _gap(
    ours: float, published: Optional[float], decimals: int
) -> Optional[float]:
    if published is None:
        return None
    return round(abs(round(ours, decimals) - published), 6)


def annotate_gaps(results: dict) -> None:
    """Add each row's differences from the published values, in place."""
    for row in results["table5"]["rows"]:
        pub = row.get("published_values")
        if not pub:
            continue
        row["estimate_gap"] = [
            _gap(a, b, 2) for a, b in zip(row["estimate"], pub["estimate"])
        ]
        row["moe_gap"] = [
            _gap(a, b, 2) for a, b in zip(row["moe"], pub["moe"])
        ]
    for row in results["table4"]["rows"]:
        pub = row["published_values"]
        row["percent_gap"] = _gap(row["percent"], pub["percent"], 1)
        row["percent_within_moe"] = bool(
            abs(row["percent"] - pub["percent"]) <= pub["percent_moe"] + 1e-9
        )
        row["percent_moe_gap"] = _gap(
            row["percent_moe"], pub["percent_moe"], 1
        )
        row["number_gap"] = round(
            abs(round_sig(row["number_thousands"]) - pub["number_thousands"]),
            6,
        )
        row["number_within_moe"] = bool(
            abs(row["number_thousands"] - pub["number_thousands"])
            <= pub["number_moe"] + 1e-9
        )
        row["number_moe_relative_gap"] = round(
            abs(row["number_moe"] - pub["number_moe"]) / pub["number_moe"], 6
        )


def summarize(results: dict) -> dict:
    """Largest differences and match counts across the annotated rows."""
    rate = [r for r in results["table5"]["rows"] if r["key"] == "spm_rate"]
    effects = [
        r
        for r in results["table5"]["rows"]
        if r["key"] != "spm_rate" and r.get("published_values")
    ]

    def cells(rows: List[dict], field: str) -> List[float]:
        return [g for r in rows for g in r[field] if g is not None]

    table4 = [r for r in results["table4"]["rows"] if r["identifiable"]]
    t5_all = cells(rate + effects, "estimate_gap") + cells(
        rate + effects, "moe_gap"
    )
    effect_max = max(cells(effects, "estimate_gap"))
    largest = [
        {"element": row["key"], "group": results["table5"]["groups"][j]}
        for row in effects
        for j, gap in enumerate(row["estimate_gap"])
        if gap is not None and abs(gap - effect_max) < 1e-9
    ]
    rate_cells = cells(rate, "estimate_gap") + cells(rate, "moe_gap")
    return {
        "table5_spm_rate_max_gap": max(cells(rate, "estimate_gap")),
        "table5_spm_rate_moe_max_gap": max(cells(rate, "moe_gap")),
        "table5_spm_rate_cells": len(rate_cells),
        "table5_spm_rate_cells_exact": sum(1 for g in rate_cells if g < 1e-9),
        "table5_effect_max_gap": effect_max,
        "table5_effect_max_gap_cells": largest,
        "table5_effect_moe_max_gap": max(cells(effects, "moe_gap")),
        "table5_cells": len(t5_all),
        "table5_cells_exact": sum(1 for g in t5_all if g < 1e-9),
        "table5_effects_within_published_moe": sum(
            1
            for row in effects
            for gap, moe in zip(
                row["estimate_gap"], row["published_values"]["moe"]
            )
            if gap is not None and gap <= moe + 1e-9
        ),
        "table5_effect_cells": len(cells(effects, "estimate_gap")),
        "table4_rows": len(results["table4"]["rows"]),
        "table4_rows_identifiable": len(table4),
        "table4_percent_exact": sum(
            1 for r in table4 if r["percent_gap"] < 1e-9
        ),
        "table4_percent_within_moe": sum(
            1 for r in table4 if r["percent_within_moe"]
        ),
        "table4_number_within_moe": sum(
            1 for r in table4 if r["number_within_moe"]
        ),
        "table4_percent_max_gap": max(r["percent_gap"] for r in table4),
        "table4_percent_moe_max_gap": max(
            r["percent_moe_gap"] for r in table4
        ),
        "table4_number_moe_relative_max_gap": max(
            r["number_moe_relative_gap"] for r in table4
        ),
    }


def tolerance_failures(results: dict) -> List[str]:
    """Each stated tolerance the results break, described in words."""
    s = results["comparison"]
    t = TOLERANCES
    failures = []
    for key, limit in (
        ("table5_spm_rate_max_gap", t["table5_spm_rate"]),
        ("table5_spm_rate_moe_max_gap", t["table5_spm_rate_moe"]),
        ("table5_effect_max_gap", t["table5_effect"]),
        ("table5_effect_moe_max_gap", t["table5_effect_moe"]),
        ("table4_percent_moe_max_gap", t["table4_percent_moe"]),
        (
            "table4_number_moe_relative_max_gap",
            t["table4_number_moe_relative"],
        ),
    ):
        if s[key] > limit + 1e-9:
            failures.append(f"{key} = {s[key]} exceeds {limit}")
    n = s["table4_rows_identifiable"]
    if s["table4_percent_within_moe"] != n:
        failures.append(
            f"{n - s['table4_percent_within_moe']} identifiable Table 4 "
            "rows have percentages outside the published margin"
        )
    if s["table4_number_within_moe"] != n:
        failures.append(
            f"{n - s['table4_number_within_moe']} identifiable Table 4 "
            "rows have numbers outside the published margin"
        )
    return failures


# ---------------------------------------------------------------------------
# The full reproduction
# ---------------------------------------------------------------------------


def reproduce(persons: pd.DataFrame, inputs: Optional[dict] = None) -> dict:
    """Every estimate the step 1 note reports, beside the published values.

    Args:
        persons: Output of :func:`load_persons`.
        inputs: Provenance of the input files, stored as given.

    Raises:
        ValueError: If any identity check fails.
    """
    checks = check_identities(persons)
    failed = failed_identities(checks)
    if failed:
        raise ValueError(f"Identity checks failed: {failed}")
    weights = weight_matrix(persons)
    published5 = published_table5()
    alternative_elements = [element for element, _ in ALTERNATIVE_ELEMENTS]
    table5 = estimate_table5(
        persons, weights, list(ELEMENTS) + alternative_elements
    )

    def t5_row(key: str, label: str, kind: str, published_key: str) -> dict:
        pub = published5.get(published_key)
        return {
            "key": key,
            "label": label,
            "kind": kind,
            **table5[key],
            "published_values": pub,
        }

    t5_rows = [
        t5_row("spm_rate", "SPM rate for all people", "rate", "spm_rate")
    ]
    for element in ELEMENTS:
        row = t5_row(element.key, element.label, element.kind, element.key)
        row["unit_columns"] = list(element.unit_columns)
        row["person_columns"] = list(element.person_columns)
        if not element.published:
            row["published_values"] = None
        t5_rows.append(row)

    table4 = estimate_table4(persons, weights)
    published4 = published_table4()
    for row, pub in zip(table4, published4):
        row["published_values"] = {
            k: pub[k]
            for k in (
                "number_thousands",
                "number_moe",
                "percent",
                "percent_moe",
            )
        }

    by_label4 = {(r["section"], r["label"]): r for r in table4}
    alt4_rows = [row for row, _ in ALTERNATIVE_TABLE4_ROWS]
    alt4 = estimate_table4(persons, weights, alt4_rows)
    for estimate, (row, compares_with) in zip(alt4, ALTERNATIVE_TABLE4_ROWS):
        main = by_label4[(row.section, compares_with)]
        estimate["compares_with"] = compares_with
        estimate["published_values"] = main["published_values"]
    alt5 = []
    for element, compares_with in ALTERNATIVE_ELEMENTS:
        row = t5_row(element.key, element.label, element.kind, compares_with)
        row["unit_columns"] = list(element.unit_columns)
        row["person_columns"] = list(element.person_columns)
        row["compares_with"] = compares_with
        alt5.append(row)

    results = {
        "schema_version": 1,
        "survey_year": SURVEY_YEAR,
        "reference_year": REFERENCE_YEAR,
        "inputs": inputs or {},
        "sample": sample_counts(persons),
        "population_thousands": float(persons["weight"].sum() / 1000.0),
        "identities": checks,
        "unidentified_geography": unidentified_geography(persons),
        "table5": {"groups": list(TABLE5_GROUPS), "rows": t5_rows},
        "table4": {"rows": table4},
        "alternatives": {
            "table5": {"groups": list(TABLE5_GROUPS), "rows": alt5},
            "table4": {"rows": alt4},
        },
        "credit_interaction": credit_interaction(persons, weights),
        "tolerances": dict(TOLERANCES),
    }
    annotate_gaps(results)
    annotate_gaps(results["alternatives"])
    results["comparison"] = summarize(results)
    return results
