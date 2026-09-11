"""Build or check the CE rolling-window component using cached inputs only.

Run from the repository root with an explicit output file:
    uv run --no-sync python scripts/build_ce_forecast.py --output RESULT.json
Add --check to reproduce and compare an existing result without writing it.
Raw CE bundles remain outside Git. No downloads or runtime dates are used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from spm_calculator.ce_forecast import (
    INFORMATION_DATE,
    build_ce_forecast,
    corrected_published_thresholds,
)
from spm_calculator.forecast_inputs import (
    load_horizon_inputs,
    projection_rates,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache/spm-calculator/ce-pumd",
    )
    parser.add_argument(
        "--cpi-input",
        type=Path,
        default=Path(__file__).resolve().parent.parent
        / "spm_calculator/data/bls/cpi_annual.json",
    )
    parser.add_argument("--information-date", default=INFORMATION_DATE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(
        "Building CE windows and all 21 retrospective folds from cached inputs",
        flush=True,
    )
    result = build_ce_forecast(
        cache_dir=args.cache_dir,
        cpi_path=args.cpi_input,
        published_thresholds=corrected_published_thresholds(),
        housing_share_anchor=load_horizon_inputs()["published_housing_shares"][
            "2025"
        ],
        inflation_rates=projection_rates(),
        information_date=args.information_date,
    )
    content = (
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode()
    if args.check:
        if args.output.read_bytes() != content:
            raise ValueError(
                "CE result differs from deterministic offline rebuild"
            )
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(content)
    growth = result["real_growth"]
    validation = result["backtest"]
    print(
        json.dumps(
            {
                "output_sha256": hashlib.sha256(content).hexdigest(),
                "output_bytes": len(content),
                "checked": args.check,
                "annual_real_growth": growth["annual_rate"],
                "unshrunk_annual_growth": growth["unshrunk_annual_rate"],
                "sensitivities": {
                    name: {
                        key: fit[key]
                        for key in (
                            "status",
                            "n",
                            "annual_rate",
                            "OLS_slope_standard_error",
                        )
                    }
                    for name, fit in growth["sensitivities"].items()
                },
                "validation_status": validation["status"],
                "fold_count": validation["fold_count"],
                "fold_tenure_observation_count": validation[
                    "fold_tenure_observation_count"
                ],
                "baseline": validation["baseline"],
                "scenarios": validation["scenarios"],
            },
            indent=2,
            allow_nan=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
