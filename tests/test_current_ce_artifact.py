"""Ensure the real-data acceptance receipt is complete and tied to its code."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "spm_calculator/data/current/ce_replication_2019_2025.json"


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


def test_real_replication_receipt_hashes_current_inputs_and_scientific_code():
    document = json.loads(ARTIFACT.read_text())
    hashes = {
        **document["code_sha256"],
        document["cpi_input"]["path"]: document["cpi_input"]["sha256"],
        document["published_threshold_input"]["path"]: document[
            "published_threshold_input"
        ]["sha256"],
    }
    assert "spm_calculator/forecast.py" in hashes
    assert "spm_calculator/data/bls/threshold_series.json" in hashes
    for path, expected in hashes.items():
        actual = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        assert actual == expected, (
            f"{path} changed after the raw-data acceptance run; rerun "
            "scripts/replicate_current_ce.py to produce current evidence"
        )
