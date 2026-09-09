"""Offline commands for inspecting and applying a pinned SPM forecast."""

from __future__ import annotations

import argparse
import csv
import json
import sys

from .release import TENURES, SPMUnit
from .rolling_forecast import load_forecast


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="spm-calculator", description=__doc__
    )
    parser.add_argument(
        "--forecast",
        help="Local forecast JSON; default is the bundled artifact",
    )
    parser.add_argument(
        "--expect-sha256",
        help="Independently retained forecast content digest",
    )
    parser.add_argument(
        "--as-of", help="Required information date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--scenario", help="Scenario identity; default is the artifact default"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "info", help="Show artifact identity, coverage and sources"
    )
    commands.add_parser(
        "verify", help="Verify schema, digest and information date"
    )
    table = commands.add_parser(
        "export",
        help="Export the artifact or selected scenario's national table",
    )
    table.add_argument("--format", choices=("json", "csv"), default="json")
    areas = commands.add_parser(
        "areas", help="List the selected year's actual SPM estimation areas"
    )
    areas.add_argument("--year", type=int, required=True)
    calc = commands.add_parser(
        "calculate", help="Compute one annual SPM unit threshold"
    )
    calc.add_argument("--year", type=int, required=True)
    calc.add_argument("--adults", type=int, required=True)
    calc.add_argument("--children", type=int, default=0)
    calc.add_argument("--tenure", choices=TENURES, default="renter")
    calc.add_argument("--resources", type=float)
    calc.add_argument("--unit-id", default="unit-1")
    location = calc.add_mutually_exclusive_group(required=True)
    location.add_argument(
        "--national",
        action="store_true",
        help="Explicitly use the national reference",
    )
    location.add_argument(
        "--area",
        help="SPM estimation-area ID (MSA, residual metro or state nonmetro)",
    )
    location.add_argument(
        "--county", help="Resolve a five-digit county FIPS to its SPM area"
    )
    calc.add_argument("--county-vintage", default="2020")
    args = parser.parse_args(argv)
    try:
        forecast = load_forecast(
            args.forecast, expected_sha256=args.expect_sha256, as_of=args.as_of
        )
        scenario = (
            forecast.default_scenario
            if args.scenario is None
            else args.scenario
        )
        # Validate the scenario even for commands that do not calculate an amount.
        forecast.entry(forecast.years[0], scenario=scenario, as_of=args.as_of)
        if args.command == "calculate":
            assignment = None
            area = args.area
            if args.county is not None:
                assignment = forecast.resolve_county(
                    args.year,
                    args.county,
                    county_vintage=args.county_vintage,
                    scenario=scenario,
                    as_of=args.as_of,
                )
                area = assignment["area_id"]
            result = forecast.calculate_unit(
                SPMUnit(
                    unit_id=args.unit_id,
                    num_adults=args.adults,
                    num_children=args.children,
                    tenure=args.tenure,
                    year=args.year,
                    resources=args.resources,
                    geography_kind="national" if args.national else "metro",
                    geography_id=area,
                ),
                scenario=scenario,
                as_of=args.as_of,
            )
            if assignment is not None:
                result["provenance"]["county_assignment"] = assignment
        elif args.command == "areas":
            result = forecast.areas_for_year(
                args.year, scenario=scenario, as_of=args.as_of
            )
        elif args.command == "export":
            if args.format == "csv":
                writer = csv.writer(sys.stdout, lineterminator="\n")
                writer.writerow(
                    [
                        "forecast_id",
                        "forecast_sha256",
                        "scenario",
                        "year",
                        "national_status",
                        "tenure",
                        "threshold",
                        "housing_share",
                        "housing_share_status",
                        "geography_status",
                    ]
                )
                for year in forecast.years:
                    entry = forecast.entry(
                        year, scenario=scenario, as_of=args.as_of
                    )
                    for tenure in TENURES:
                        writer.writerow(
                            [
                                forecast.forecast_id,
                                forecast.content_sha256,
                                scenario,
                                year,
                                entry["national_status"],
                                tenure,
                                entry["thresholds"][tenure],
                                entry["housing_shares"][tenure],
                                entry["housing_share_status"],
                                entry["geography_status"],
                            ]
                        )
                return 0
            result = forecast.to_dict()
        else:
            doc = forecast.to_dict()
            result = {
                "forecast_id": forecast.forecast_id,
                "content_sha256": forecast.content_sha256,
                "valid": True,
                "information_date": doc["information_date"],
                "years": forecast.years,
                "scenario": scenario,
                "scenarios": list(doc["scenarios"]),
                "sources": doc["sources"],
                "verification_scope": "Schema and integrity; not a source-authenticity signature",
            }
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (ValueError, TypeError, OSError) as error:
        parser.exit(2, f"spm-calculator: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
