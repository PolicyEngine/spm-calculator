"""Prevent superseded pre-repair benchmark values from returning."""

import subprocess

BANNED_MARKERS = (
    "1." + "35%",
    "41," + "099.57",
    "34," + "250.70",
    "40," + "791.72",
    "-0.6%" + " to -2.4",
    "biased low" + " in 2022",
)


def test_tracked_repository_has_no_stale_pre_repair_markers():
    """Search every tracked text file, including generated artifacts."""
    for marker in BANNED_MARKERS:
        result = subprocess.run(
            ["git", "grep", "-n", "-I", "-F", "-e", marker, "--", "."],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1, (
            f"Found superseded marker {marker!r}:\n{result.stdout}"
        )
