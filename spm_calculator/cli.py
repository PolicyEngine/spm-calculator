"""Offline commands for inspecting and applying a pinned SPM release."""

from __future__ import annotations

import argparse
import csv
import json
import sys

from .release import TENURES, SPMUnit, load_release


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="spm-calculator", description=__doc__
    )
    parser.add_argument(
        "--release", help="Local release JSON; default is the bundled release"
    )
    parser.add_argument(
        "--expect-sha256", help="Independently retained release content digest"
    )
    parser.add_argument(
        "--as-of", help="Required information date (YYYY-MM-DD)"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "info", help="Show release identity, coverage and sources"
    )
    commands.add_parser(
        "verify", help="Verify schema, content digest and information date"
    )
    table = commands.add_parser(
        "export", help="Export the release or its national threshold table"
    )
    table.add_argument("--format", choices=("json", "csv"), default="json")
    calc = commands.add_parser(
        "calculate", help="Compute one annual SPM unit threshold"
    )
    calc.add_argument("--year", type=int, required=True)
    calc.add_argument("--adults", type=int, required=True)
    calc.add_argument("--children", type=int, default=0)
    calc.add_argument("--tenure", choices=TENURES, default="renter")
    calc.add_argument("--resources", type=float)
    calc.add_argument("--unit-id", default="unit-1")
    calc.add_argument(
        "--geography-kind",
        choices=(
            "national",
            "metro",
            "congressional_district",
            "state",
            "county",
        ),
        default="national",
    )
    calc.add_argument("--geography-id")
    calc.add_argument("--geographic-adjustment", type=float)
    calc.add_argument("--allow-estimated", action="store_true")
    args = parser.parse_args(argv)
    try:
        release = load_release(
            args.release, expected_sha256=args.expect_sha256, as_of=args.as_of
        )
        if args.command == "calculate":
            result = release.calculate_unit(
                SPMUnit(
                    unit_id=args.unit_id,
                    num_adults=args.adults,
                    num_children=args.children,
                    tenure=args.tenure,
                    year=args.year,
                    resources=args.resources,
                    geography_kind=args.geography_kind,
                    geography_id=args.geography_id,
                    geographic_adjustment=args.geographic_adjustment,
                ),
                allow_estimated=args.allow_estimated,
                as_of=args.as_of,
            )
        elif args.command == "export":
            if args.format == "csv":
                writer = csv.writer(sys.stdout, lineterminator="\n")
                writer.writerow(
                    [
                        "release_id",
                        "release_sha256",
                        "year",
                        "status",
                        "tenure",
                        "threshold",
                        "housing_share",
                        "housing_share_reference_year",
                        "housing_share_status",
                    ]
                )
                for year in release.years:
                    entry = release.entry(year, allow_estimated=True)
                    for tenure in TENURES:
                        share = entry["housing_share_provenance"]
                        writer.writerow(
                            [
                                release.release_id,
                                release.content_sha256,
                                year,
                                entry["status"],
                                tenure,
                                entry["thresholds"][tenure],
                                entry["housing_shares"][tenure],
                                share["reference_year"],
                                share["status"],
                            ]
                        )
                return 0
            result = release.to_dict()
        else:
            doc = release.to_dict()
            result = {
                "release_id": release.release_id,
                "content_sha256": release.content_sha256,
                "valid": True,
                "information_date": doc["information_date"],
                "years": release.years,
                "sources": doc["sources"],
                "verification_scope": "Schema and integrity; not a source-authenticity signature",
            }
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (ValueError, TypeError, OSError) as error:
        parser.exit(2, f"spm-calculator: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
