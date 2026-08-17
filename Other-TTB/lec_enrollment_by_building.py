#!/usr/bin/env python3
"""Pivot LEC enrollment by building with one column per session code."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


DEFAULT_BUILDINGS = [
    "BA",
    "ES",
    "EX",
    "GB",
    "HH",
    "HS",
    "MC",
    "MP",
    "MS",
    "MY",
    "OI",
    "PB",
    "RL",
    "RT",
    "RU",
    "RW",
    "SF",
    "SM",
    "SS",
    "WB",
]


def parse_buildings(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]


def aggregate_lec_enrollment(
    input_csv: Path,
    buildings: list[str] | None,
    campus: str | None,
    teach_method: str,
) -> tuple[dict[str, dict[str, int]], list[str], list[str]]:
    building_set = set(buildings) if buildings else None
    data: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    sessions: set[str] = set()
    discovered_buildings: set[str] = set()

    with input_csv.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)

        required = {"teach_method", "session_codes", "location", "current_enrolment", "campus"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            missing_text = ", ".join(sorted(missing))
            raise ValueError(f"Input CSV is missing required column(s): {missing_text}")

        for row in reader:
            if (row.get("teach_method") or "").strip() != teach_method:
                continue

            if campus:
                row_campus = (row.get("campus") or "").strip()
                if row_campus != campus:
                    continue

            session = (row.get("session_codes") or "").strip()
            if not session:
                continue
            sessions.add(session)

            raw_location = (row.get("location") or "").strip()
            if not raw_location:
                continue

            # De-duplicate buildings per section row if location repeats.
            locations = {item.strip() for item in raw_location.split("|") if item.strip()}

            try:
                current_enrolment = int((row.get("current_enrolment") or "").strip())
            except ValueError:
                current_enrolment = 0

            for building in locations:
                # If building_set is specified, only include buildings in that set
                if building_set is not None and building not in building_set:
                    continue
                discovered_buildings.add(building)
                data[building][session] += current_enrolment

    return data, sorted(sessions), sorted(discovered_buildings)


def write_pivot_csv(
    output_csv: Path,
    buildings: list[str],
    data: dict[str, dict[str, int]],
    sessions: list[str],
) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["building", *sessions])

        for building in buildings:
            row = [building]
            by_session = data.get(building, {})
            row.extend(by_session.get(session, 0) for session in sessions)
            writer.writerow(row)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate pivoted LEC enrollment totals by building and session.",
    )
    parser.add_argument(
        "--input",
        default="ttb_enrollment.csv",
        help="Path to source enrollment CSV (default: ttb_enrollment.csv)",
    )
    parser.add_argument(
        "--output",
        default="lec_enrollment_by_building_session.csv",
        help="Path to output CSV (default: lec_enrollment_by_building_session.csv)",
    )
    parser.add_argument(
        "--buildings",
        default=None,
        help="Comma-separated building codes to include. Defaults to the standard 20-building list.",
    )
    parser.add_argument(
        "--teach-method",
        default="LEC",
        help="Section teach_method filter (default: LEC)",
    )
    parser.add_argument(
        "--campus",
        default="St. George",
        help="Campus filter (default: St. George). Use 'all' to include all campuses.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    input_csv = Path(args.input)
    output_csv = Path(args.output)
    buildings = parse_buildings(args.buildings)
    campus = args.campus if args.campus.lower() != "all" else None

    data, sessions, discovered_buildings = aggregate_lec_enrollment(
        input_csv=input_csv,
        buildings=buildings,
        campus=campus,
        teach_method=args.teach_method,
    )
    write_pivot_csv(
        output_csv=output_csv,
        buildings=discovered_buildings,
        data=data,
        sessions=sessions,
    )

    print(f"Wrote {output_csv} with {len(discovered_buildings)} building rows and {len(sessions)} session columns.")


if __name__ == "__main__":
    main()
