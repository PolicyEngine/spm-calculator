"""Regression tests for the scheduled BLS drift workflow."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).parents[1] / ".github/workflows/bls-drift-watch.yaml"


def test_drift_workflow_preserves_checker_exit_status():
    """The issue gate must see the checker status, not ``tee``'s status."""
    text = WORKFLOW.read_text()

    assert "shell: bash" in text
    assert "code=${PIPESTATUS[0]}" in text
    assert "code=$?" not in text


@pytest.mark.parametrize("existing", ["", "42"])
def test_drift_issue_step_works_without_optional_repository_labels(
    tmp_path, existing
):
    """Execute the real workflow step against an unlabeled GitHub stub."""
    issue_step = WORKFLOW.read_text().split(
        "- name: Open or update drift issue\n", 1
    )[1]
    script = textwrap.dedent(issue_step.split("        run: |\n", 1)[1])
    executable = tmp_path / "gh"
    executable.write_text(
        f"#!{sys.executable}\n"
        + textwrap.dedent(
            """\
            import json, os, sys
            from pathlib import Path
            args = sys.argv[1:]
            with open(os.environ['CALLS'], 'a') as log:
                log.write(json.dumps(args) + '\\n')
            if args[:2] == ['issue', 'list']:
                print(os.environ['EXISTING'])
            elif args[:2] in (['issue', 'create'], ['issue', 'comment']):
                if '--label' in args:
                    sys.exit('could not add label: not found')
                body = Path(args[args.index('--body-file') + 1]).read_text()
                assert body == 'Observed threshold drift\\n'
            else:
                sys.exit('unexpected GitHub operation')
            """
        )
    )
    executable.chmod(0o755)
    calls = tmp_path / "calls.jsonl"
    (tmp_path / "drift.log").write_text("Observed threshold drift\n")
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", script],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "CALLS": str(calls),
            "EXISTING": existing,
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    actions = [json.loads(line) for line in calls.read_text().splitlines()]
    assert len(actions) == 2
    if existing:
        assert actions[1] == [
            "issue",
            "comment",
            existing,
            "--body-file",
            "drift.log",
        ]
    else:
        assert actions[1] == [
            "issue",
            "create",
            "--title",
            "BLS SPM threshold series has diverged from the packaged data",
            "--body-file",
            "drift.log",
        ]
