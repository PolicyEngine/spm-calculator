"""Regression tests for the scheduled BLS drift workflow."""

from pathlib import Path


WORKFLOW = (
    Path(__file__).parents[1] / ".github/workflows/bls-drift-watch.yaml"
)


def test_drift_workflow_preserves_checker_exit_status():
    """The issue gate must see the checker status, not ``tee``'s status."""
    text = WORKFLOW.read_text()

    assert "shell: bash" in text
    assert "code=${PIPESTATUS[0]}" in text
    assert "code=$?" not in text
