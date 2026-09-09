"""Preserve the frozen real-data acceptance receipt and its source provenance."""

import hashlib
import json
from pathlib import Path

from spm_calculator.published_thresholds import get_published_thresholds

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "spm_calculator/data/current/ce_replication_2019_2025.json"
ARCHIVED_SHA256 = (
    "d04e2a61552795f9d90e282045610774a4ff68f67b97067677358741f58a289c"
)


def test_current_replication_receipt_has_all_windows_and_no_hidden_fallback():
    document = json.loads(ARTIFACT.read_text())
    assert set(document["results"]) == {
        str(year) for year in range(2019, 2026)
    }
    assert len(document["source_quarters"]) == 44
    assert len(document["source_bundles"]) == 11
    for result in document["results"].values():
        assert len(result["quarters"]) == 20
        assert result[
            "exact_mode_error"
        ]  # every real window exposed this issue
        baseline = result["variants"]["exclude_unresolved"]
        assert (
            baseline["construction"]["cpi_input_mode"]
            == "explicit_pinned_series"
        )
        assert baseline["sample"]["youth_policy"] == "exclude_unresolved"
        assert not baseline["estimation"]["band_fallback"]
        assert not any(
            t["pooled_fallback"]
            for t in baseline["estimation"]["tenures"].values()
        )
        sample = baseline["sample"]
        assert sample["raw"]["rows"] == (
            sample["included"]["rows"]
            + sum(
                exclusion["rows"]
                for exclusion in sample["exclusions"].values()
            )
        )
    assert document["results"]["2024"]["duplicate_index_check"][
        "identical_thresholds"
    ]
    assert (
        document["projection_evaluation"]["classification"]
        == "retrospective_current_method_not_a_frozen_commitment"
    )


def test_archived_replication_receipt_bytes_remain_immutable():
    assert hashlib.sha256(ARTIFACT.read_bytes()).hexdigest() == ARCHIVED_SHA256


def test_archived_replication_receipt_retains_scientific_code_identity():
    document = json.loads(ARTIFACT.read_text())
    assert document["schema_version"] == 1
    # These identify the archived run, including implementations since retired.
    # Current components carry current code identities in separate receipts.
    assert set(document["code_sha256"]) == {
        "scripts/replicate_current_ce.py",
        "spm_calculator/ce_threshold.py",
        "spm_calculator/equivalence_scale.py",
        "spm_calculator/fcsuti_cpi.py",
        "spm_calculator/forecast.py",
        "spm_calculator/projection.py",
    }
    for digest in document["code_sha256"].values():
        assert len(bytes.fromhex(digest)) == 32


def test_archived_replication_receipt_matches_retained_source_inputs():
    document = json.loads(ARTIFACT.read_text())
    hashes = {
        document["cpi_input"]["path"]: document["cpi_input"]["sha256"],
        document["published_threshold_input"]["path"]: document[
            "published_threshold_input"
        ]["sha256"],
    }
    for path, expected in hashes.items():
        actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        assert actual == expected, (
            f"{path} no longer matches the archived acceptance run's source; "
            "retain the original input and receipt as reproducibility evidence"
        )
    source = document["published_threshold_input"]
    assert source["series_id"] == "bls-corrected-2026-07-17"
    for year, result in document["results"].items():
        assert result["published"] == get_published_thresholds(
            int(year), series=source["series_id"]
        )
        assert set(result["quarters"]) <= set(document["source_quarters"])
    for bundle_name, bundle in document["source_bundles"].items():
        assert bundle["url"].startswith("https://www.bls.gov/cex/pumd/data/")
        assert bundle["url"].endswith("/" + bundle_name)
        assert bundle["size_bytes"] > 0
        assert len(bytes.fromhex(bundle["sha256"])) == 32
    for quarter in document["source_quarters"].values():
        assert quarter["bundle"] in document["source_bundles"]
        assert quarter["member"].endswith(".csv")
        assert quarter["raw_rows"] > 0
        assert len(bytes.fromhex(quarter["sha256"])) == 32
