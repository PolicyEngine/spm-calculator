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
import dataclasses
import gzip
import importlib.util
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
    WIC_ATTRIBUTION,
    WIC_EXPORT_TARGET,
    diagnostics_difference,
    dictionary_csv,
    dictionary_markdown,
    export_frames,
    observe_participation,
    read_csv_gz,
    verify_written,
    write_csv_gz,
)
from tests.test_ce_inkind import ce_units, cps_donors

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs/ce-inkind-export.md"
PUBLISH = ROOT / ".github/workflows/publish.yaml"
SCRIPT = ROOT / "scripts/export_ce_inkind_by_interview.py"
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


def test_observer_refuses_to_nest():
    original = ce_inkind._participation
    with observe_participation():
        with pytest.raises(RuntimeError, match="already being observed"):
            with observe_participation():
                pass
    assert ce_inkind._participation is original


def test_export_needs_every_component(observed):
    units, _, config, imputation, draws = observed
    partial = dataclasses.replace(
        config,
        components=tuple(
            c for c in config.components if c != "rental_assistance"
        ),
    )
    with pytest.raises(RuntimeError, match="every in-kind component"):
        export_frames(units, imputation, draws, partial)


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
    wic_amount = next(c for c in DICTIONARY if c.name == "wic_amount")
    assert WIC_ATTRIBUTION in wic_amount.description


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


def test_verify_written_accepts_the_file(observed, frames, tmp_path):
    units, _, config, imputation, _ = observed
    path = tmp_path / "export.csv.gz"
    write_csv_gz(frames, path)
    checks = verify_written(
        path, frames, units, imputation.diagnostics, config
    )
    assert checks["read_back_rows"] == sum(len(f) for f in frames)
    assert checks["max_mean_gap_vs_diagnostics_dollars"] <= 0.005


def _corrupt(table: pd.DataFrame, how: str) -> pd.DataFrame:
    table = table.copy()
    positive = table.index[table["liheap_amount"] > 0][0]
    if how == "blank_amount":
        table["nslp_amount"] = table["nslp_amount"].astype(float)
        table.loc[0, "nslp_amount"] = np.nan
    elif how == "blank_and_wrong_amounts":
        table["nslp_amount"] = table["nslp_amount"].astype(float)
        table.loc[0, "nslp_amount"] = np.nan
        table.loc[positive, "liheap_amount"] += 500.0
    elif how == "wrong_amount":
        table.loc[positive, "liheap_amount"] += 0.02
    elif how == "infinite_amount":
        table.loc[positive, "liheap_amount"] = np.inf
    elif how == "fractional_flag":
        table["liheap_participant"] = table["liheap_participant"].astype(float)
        table.loc[positive, "liheap_participant"] = 0.5
    elif how == "flag_two":
        table.loc[positive, "rental_assistance_participant"] = 2
    elif how == "blank_flag":
        table["nslp_participant"] = table["nslp_participant"].astype(float)
        table.loc[0, "nslp_participant"] = np.nan
    elif how == "broadband_filled":
        early = table.index[table["broadband_participant"].isna()][0]
        table.loc[early, "broadband_participant"] = 0
    elif how == "broadband_blanked":
        late = table.index[table["broadband_participant"].notna()][0]
        table.loc[late, "broadband_participant"] = np.nan
    elif how == "dropped_row":
        table = table.drop(index=positive)
    elif how == "duplicated_row":
        table = pd.concat([table, table.iloc[[0]]], ignore_index=True)
    elif how == "swapped_rows":
        table.iloc[[0, 1]] = table.iloc[[1, 0]].to_numpy()
    elif how == "text_amount":
        table["nslp_amount"] = table["nslp_amount"].astype(object)
        table.loc[0, "nslp_amount"] = "unknown"
    elif how == "unrounded_amount":
        table.loc[positive, "liheap_amount"] += 0.001
    elif how in ("broadband_half", "broadband_two"):
        late = table.index[table["broadband_participant"].notna()][0]
        value = 0.5 if how == "broadband_half" else 2
        table.loc[late, "broadband_participant"] = value
    elif how == "broadband_text":
        table["broadband_participant"] = table["broadband_participant"].map(
            lambda v: v if pd.isna(v) else ("yes" if v else "no")
        )
    return table


@pytest.mark.parametrize(
    "how, message",
    [
        ("blank_amount", "nslp_amount holds a missing"),
        ("blank_and_wrong_amounts", "nslp_amount holds a missing"),
        ("wrong_amount", "liheap_amount differs by more than rounding"),
        ("unrounded_amount", "liheap_amount is not rounded to cents"),
        ("infinite_amount", "liheap_amount holds a missing or non-finite"),
        ("text_amount", "nslp_amount does not read back as numbers"),
        ("fractional_flag", "liheap_participant does not read back as int"),
        ("flag_two", "rental_assistance_participant holds values other"),
        ("blank_flag", "nslp_participant does not read back as integers"),
        ("broadband_filled", "broadband_participant is missing in the wrong"),
        ("broadband_blanked", "broadband_participant is missing in the wrong"),
        ("broadband_half", "broadband_participant holds values other"),
        ("broadband_two", "broadband_participant holds values other"),
        ("broadband_text", "broadband_participant does not read back as num"),
        ("dropped_row", "Written row count differs"),
        ("duplicated_row", "Written row count differs"),
        ("swapped_rows", "NEWID differs"),
    ],
)
def test_verify_written_rejects_a_corrupted_file(
    observed, frames, tmp_path, how, message
):
    units, _, config, imputation, _ = observed
    path = tmp_path / "export.csv.gz"
    write_csv_gz(frames, path)
    corrupted = _corrupt(read_csv_gz(path), how)
    bad = tmp_path / "bad.csv.gz"
    corrupted.to_csv(bad, index=False, compression="gzip")
    with pytest.raises(RuntimeError, match=message):
        verify_written(bad, frames, units, imputation.diagnostics, config)


def test_diagnostics_difference_measures_relative_gaps():
    ours = {"a": {"units": 2, "mean": [1.0, 2.0]}, "b": "x", "c": None}
    theirs = {
        "a": {"units": 2, "mean": [1.0, 2.0 * (1 + 1e-12)]},
        "b": "x",
        "c": None,
    }
    assert diagnostics_difference(ours, ours) == 0.0
    assert 0 < diagnostics_difference(ours, theirs) < 1e-11
    numpy_leaves = {"units": np.int64(2), "mean": np.float32(1.5)}
    assert diagnostics_difference(numpy_leaves, {"units": 2, "mean": 1.5}) == 0


@pytest.mark.parametrize(
    "ours, theirs",
    [
        ({"units": 2, "mean": float("nan")}, {"units": 2, "mean": 1.0}),
        ({"units": 2, "mean": 1.0}, {"units": 2, "mean": float("nan")}),
        (
            {"units": 2, "mean": float("nan")},
            {"units": 2, "mean": float("nan")},
        ),
        ({"x": [1.0, float("inf")]}, {"x": [1.0, float("inf")]}),
        ({"x": [5.0, 1.0]}, {"x": [5.0, float("-inf")]}),
        ({"x": 1.0}, {"y": 1.0}),
        ({"x": [1.0]}, {"x": [1.0, 2.0]}),
        ({"x": "a"}, {"x": "b"}),
        ({"x": True}, {"x": 1}),
        ({"x": np.bool_(True)}, {"x": 1}),
        ({"x": None}, {"x": 0.0}),
        ({"units": 2}, {"units": 3}),
        ({"units": 2**53}, {"units": 2**53 + 1}),
        ({"units": np.int64(7)}, {"units": 8}),
    ],
)
def test_diagnostics_difference_rejects_mismatches(ours, theirs):
    with pytest.raises(RuntimeError):
        diagnostics_difference(ours, theirs)


def test_release_files_carry_cc0():
    spec = importlib.util.spec_from_file_location("export_script", SCRIPT)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    counts = {"interviews": 2, "implicates": 5, "rows": 10}
    readme = script.readme_text(
        "x.csv.gz", ("2014Q2", "2025Q1"), counts, "abc123"
    )
    citation = (
        'cite "PolicyEngine SPM calculator, CE in-kind imputations by '
        'interview, v1"; CC0 does not require it.'
    )
    for text in (readme, DOC.read_text()):
        assert "CC0 1.0" in text
        assert "creativecommons.org/publicdomain/zero/1.0/" in text
        assert "CC BY" not in text
        assert citation in " ".join(text.split())
    assert WIC_ATTRIBUTION in readme
    assert "blob/abc123/docs/ce-inkind-export.md" in readme
