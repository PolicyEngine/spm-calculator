"""Per-interview in-kind export: the observer, the rows and the file.

Invariants (stated in docs/ce-inkind-export.md):

1. Recording the participation draws changes nothing: the imputation is
   the same with and without the observer.
2. Every modeled draw is recorded once, and the recorded draws give the
   imputation's own participation rates.
3. A positive amount implies participation; LIHEAP and broadband
   participation equals a positive amount.
4. WIC follows the universe every threshold before 2025 used.
5. Broadband participation is missing, not zero, before its first year.
6. The file reads back to the frames, to the cent, and its bytes depend
   only on its contents.
"""

import csv
import gzip
import inspect
import io
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from spm_calculator import ce_inkind
from spm_calculator.ce_inkind import (
    IN_KIND_COMPONENTS,
    InKindConfig,
    ce_unit_covariates,
    impute_in_kind,
)
from spm_calculator.ce_inkind_export import (
    COLUMNS,
    DICTIONARY,
    FMLI_COLUMNS,
    MODELED_COMPONENTS,
    WIC_EXPORT_TARGET,
    dictionary_csv,
    dictionary_markdown,
    export_frames,
    observe_participation,
    read_csv_gz,
    write_csv_gz,
)
from tests.test_ce_inkind import ce_units, cps_donors

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs/ce-inkind-export.md"
PUBLISH = ROOT / ".github/workflows/publish.yaml"
#: A school lunch formula year, a year with WIC and a year with broadband.
YEARS = (2017, 2019, 2022)


@pytest.fixture(scope="module")
def observed():
    units = ce_units(11, YEARS)
    donors = cps_donors(11, YEARS)
    config = InKindConfig(implicates=3)
    with observe_participation() as draws:
        imputation = impute_in_kind(units, donors, config)
    return units, donors, config, imputation, draws


@pytest.fixture(scope="module")
def frames(observed):
    units, _, config, imputation, draws = observed
    return export_frames(units, imputation, draws, config)


def test_observer_changes_nothing(observed):
    units, donors, config, imputation, _ = observed
    plain = impute_in_kind(units, donors, config)
    for wrapped, unwrapped in zip(imputation.implicates, plain.implicates):
        pd.testing.assert_frame_equal(wrapped, unwrapped)
    assert json.dumps(imputation.diagnostics, sort_keys=True) == json.dumps(
        plain.diagnostics, sort_keys=True
    )


def test_observer_restores_the_function_even_after_an_error():
    original = ce_inkind._participation
    with pytest.raises(ZeroDivisionError):
        with observe_participation():
            assert ce_inkind._participation is not original
            1 / 0
    assert ce_inkind._participation is original


def test_observer_rejects_a_second_imputation():
    units = ce_units(3, (2019,), n=150)
    donors = cps_donors(3, (2019,), n=600)
    config = InKindConfig(implicates=1)
    with observe_participation():
        impute_in_kind(units, donors, config)
        with pytest.raises(RuntimeError, match="Second participation draw"):
            impute_in_kind(units, donors, config)


def test_every_modeled_draw_is_recorded(observed):
    _, _, _, _, draws = observed
    expected = {(c, y) for c in ("nslp", "wic", "liheap") for y in YEARS}
    expected.add(("broadband", 2022))
    assert set(draws) == expected


def test_rows_keys_and_columns(observed, frames):
    units, _, config, _, _ = observed
    assert len(frames) == config.implicates
    for m, frame in enumerate(frames):
        assert tuple(frame.columns) == COLUMNS
        assert frame["NEWID"].tolist() == units["key"].tolist()
        assert (frame["implicate"] == m + 1).all()
        assert (
            frame["reference_year"].tolist()
            == units["reference_year"].tolist()
        )
        assert frame["ce_year"].tolist() == units["ce_year"].tolist()
        assert frame["ce_quarter"].tolist() == units["ce_quarter"].tolist()


def test_amounts_match_the_imputation(observed, frames):
    _, _, _, imputation, _ = observed
    for m, frame in enumerate(frames):
        used = imputation.for_target(m, WIC_EXPORT_TARGET)
        for component in IN_KIND_COMPONENTS:
            np.testing.assert_array_equal(
                frame[f"{component}_amount"].to_numpy(),
                used[component].to_numpy(),
            )


def test_positive_amounts_imply_participation(frames):
    for frame in frames:
        for component in IN_KIND_COMPONENTS:
            flag = frame[f"{component}_participant"].fillna(0).astype(int)
            amount = frame[f"{component}_amount"]
            assert not ((amount > 0) & (flag == 0)).any(), component
        for component in ("liheap", "broadband"):
            modeled = frame[f"{component}_participant"].notna()
            flag = frame.loc[modeled, f"{component}_participant"].astype(int)
            assert (
                (flag == 1)
                .eq(frame.loc[modeled, f"{component}_amount"] > 0)
                .all()
            )


def test_universes_and_rules(observed, frames):
    units, _, config, imputation, _ = observed
    school_age = units["n_5_18"].to_numpy() >= 1
    narrow = (units["n_women_15_45"].to_numpy() >= 1) | (
        (units["n_lt5"].to_numpy() >= 1)
        & (units["n_women_15_plus"].to_numpy() >= 1)
    )
    assisted = (units["cutenure"].to_numpy() == 4) & units[
        "housing_assistance"
    ].to_numpy()
    before = units["reference_year"].to_numpy() < 2022
    for frame in frames:
        assert (frame.loc[~school_age, "nslp_participant"] == 0).all()
        assert (frame.loc[~narrow, "wic_participant"] == 0).all()
        assert (frame.loc[~narrow, "wic_amount"] == 0).all()
        assert frame.loc[before, "broadband_participant"].isna().all()
        assert frame.loc[~before, "broadband_participant"].notna().all()
        assert (frame.loc[before, "broadband_amount"] == 0).all()
        np.testing.assert_array_equal(
            frame["rental_assistance_participant"].to_numpy(dtype=bool),
            assisted,
        )
        other = [c for c in COLUMNS if c != "broadband_participant"]
        assert frame[other].notna().all().all()
    broad_only = imputation.implicates[0]["wic_broad_universe_only"]
    np.testing.assert_array_equal(
        frames[0]["wic_broad_universe_only"].to_numpy(dtype=bool),
        broad_only.to_numpy(),
    )
    np.testing.assert_array_equal(
        broad_only.to_numpy(), ~narrow & (units["n_lt5"].to_numpy() >= 1)
    )


def test_wic_is_zero_from_2020_but_participation_is_modeled(frames):
    later = frames[0]["reference_year"] >= 2020
    assert (frames[0].loc[later, "wic_amount"] == 0).all()
    assert (frames[0].loc[later, "wic_participant"] == 1).any()
    assert (frames[0].loc[~later, "wic_amount"] > 0).any()


@pytest.mark.parametrize("tamper", ["flip", "drop", "extra"])
def test_draws_that_differ_from_the_imputation_are_rejected(observed, tamper):
    units, _, config, imputation, draws = observed
    changed = dict(draws)
    if tamper == "flip":
        keys, takes = changed[("liheap", 2019)]
        takes = [t.copy() for t in takes]
        takes[0][0] = not takes[0][0]
        changed[("liheap", 2019)] = (keys, takes)
    elif tamper == "drop":
        del changed[("wic", 2017)]
    else:
        changed[("broadband", 2019)] = changed[("liheap", 2019)]
    with pytest.raises(RuntimeError):
        export_frames(units, imputation, changed, config)


def test_file_reads_back_to_the_frames(frames, tmp_path):
    path = tmp_path / "export.csv.gz"
    written = write_csv_gz(frames, path)
    table = read_csv_gz(path)
    assert written["rows"] == len(table) == sum(len(f) for f in frames)
    assert tuple(table.columns) == COLUMNS
    assert pd.api.types.is_integer_dtype(table["NEWID"])
    assert not table.duplicated(["NEWID", "implicate"]).any()
    expected = pd.concat(frames, ignore_index=True).sort_values(
        ["implicate", "NEWID"], kind="stable"
    )
    assert table["NEWID"].tolist() == expected["NEWID"].tolist()
    assert table["implicate"].tolist() == expected["implicate"].tolist()
    for column in COLUMNS:
        got, want = table[column].to_numpy(), expected[column].to_numpy()
        if column.endswith("_amount"):
            assert np.abs(got - want.astype(float)).max() <= 0.005 + 1e-9
            np.testing.assert_array_equal(got, np.round(got, 2))
        else:
            np.testing.assert_array_equal(pd.isna(got), pd.isna(want))
            keep = ~pd.isna(want)
            np.testing.assert_array_equal(
                got[keep].astype(int), want[keep].astype(int)
            )


def test_file_bytes_depend_only_on_contents(frames, tmp_path):
    first = write_csv_gz(frames, tmp_path / "a.csv.gz")
    second = write_csv_gz(list(reversed(frames)), tmp_path / "b.csv.gz")
    assert (tmp_path / "a.csv.gz").read_bytes() == (
        tmp_path / "b.csv.gz"
    ).read_bytes()
    assert first["csv_gz_sha256"] == second["csv_gz_sha256"]
    header = (tmp_path / "a.csv.gz").read_bytes()[:10]
    assert header[3] == 0, "no file name or other optional header fields"
    assert header[4:8] == b"\x00\x00\x00\x00", "no timestamp"
    text = gzip.decompress((tmp_path / "a.csv.gz").read_bytes())
    assert text.decode("ascii").splitlines()[0] == ",".join(COLUMNS)


def test_dictionary_describes_every_column_once():
    names = [column.name for column in DICTIONARY]
    assert len(names) == len(set(names))
    assert names[:6] == [
        "NEWID",
        "implicate",
        "ce_year",
        "ce_quarter",
        "reference_year",
        "wic_broad_universe_only",
    ]
    for component in IN_KIND_COMPONENTS:
        assert f"{component}_participant" in names
        assert f"{component}_amount" in names
    assert set(MODELED_COMPONENTS) < set(IN_KIND_COMPONENTS)
    rows = list(csv.reader(io.StringIO(dictionary_csv())))
    assert rows[0] == ["column", "type", "description"]
    assert [row[0] for row in rows[1:]] == names
    assert all(column.description for column in DICTIONARY)


def test_docs_carry_the_dictionary_table():
    assert dictionary_markdown() in DOC.read_text()


def test_fmli_columns_cover_what_the_covariates_read():
    source = inspect.getsource(ce_unit_covariates)
    read = set(re.findall(r'_numeric\(f, "([A-Za-z0-9_]+)"\)', source))
    assert read == set(FMLI_COLUMNS)


def test_publish_workflow_skips_export_releases():
    """A data release must not start the PyPI pipeline."""
    test_job = (
        PUBLISH.read_text()
        .split("\n  test:\n", 1)[1]
        .split("\n  publish:\n", 1)[0]
    )
    assert (
        "if: github.event_name != 'release' || "
        "!startsWith(github.event.release.tag_name, 'ce-inkind-')"
    ) in test_job
    publish_job = PUBLISH.read_text().split("\n  publish:\n", 1)[1]
    assert "needs: test" in publish_job
