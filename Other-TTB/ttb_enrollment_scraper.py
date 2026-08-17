#!/usr/bin/env python3
"""Collect course enrollment data from U of T Timetable Builder (TTB).

This script calls the public TTB API endpoint and exports section-level
enrollment information to CSV.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

DEFAULT_ENDPOINT = "https://api.easi.utoronto.ca/ttb/getCourses"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect section-level enrollment data from ttb.utoronto.ca"
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=f"TTB API endpoint (default: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--output",
        default="ttb_enrollment.csv",
        help="Output CSV file path (default: ttb_enrollment.csv)",
    )
    parser.add_argument(
        "--session",
        action="append",
        default=[],
        help="Filter to one or more session codes (repeatable, e.g. --session 20259)",
    )
    parser.add_argument(
        "--division",
        action="append",
        default=[],
        help="Filter to one or more division/faculty codes (repeatable, e.g. --division ARTSC)",
    )
    parser.add_argument(
        "--course-prefix",
        action="append",
        default=[],
        help="Filter by course code prefix (repeatable, e.g. --course-prefix CSC)",
    )
    parser.add_argument(
        "--max-courses",
        type=int,
        default=0,
        help="Stop after parsing this many courses (0 means no limit)",
    )
    parser.add_argument(
        "--keep-xml",
        default="",
        help="Optional path to keep raw XML response",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="HTTP timeout in seconds (default: 120)",
    )
    return parser.parse_args()


def download_xml(endpoint: str, destination: Path, timeout: int) -> None:
    payload = b"{}"
    req = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/xml, text/xml, */*",
            "User-Agent": "ttb-enrollment-scraper/1.0",
        },
    )

    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp, destination.open(
                "wb"
            ) as out:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            return
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == 3:
                break
            time.sleep(1.5 * attempt)

    raise RuntimeError(f"Failed to download XML from {endpoint}: {last_error}")


def text_at(elem: ET.Element, path: str, default: str = "") -> str:
    found = elem.find(path)
    if found is None or found.text is None:
        return default
    return found.text.strip()


def to_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def format_day(day_value: str) -> str:
    day_map = {
        "1": "Mon",
        "2": "Tue",
        "3": "Wed",
        "4": "Thu",
        "5": "Fri",
        "6": "Sat",
        "7": "Sun",
    }
    return day_map.get(day_value, day_value)


def format_millis_of_day(value: str) -> str:
    millis = to_int(value)
    if millis is None or millis < 0:
        return ""
    total_minutes = millis // 60000
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours:02d}:{minutes:02d}"


def iter_rows(
    xml_path: Path,
    session_filter: set[str],
    division_filter: set[str],
    course_prefix_filter: set[str],
    max_courses: int,
) -> Iterable[dict[str, str | int]]:
    parsed_courses = 0
    retrieved_at = dt.datetime.now(dt.timezone.utc).isoformat()

    context = ET.iterparse(xml_path, events=("end",))
    for _, elem in context:
        if elem.tag != "payload":
            continue

        # Distinguish course payloads from non-course payload objects.
        if elem.find("code") is None or elem.find("sections") is None:
            elem.clear()
            continue

        parsed_courses += 1
        if parsed_courses % 500 == 0:
            print(f"Parsed {parsed_courses} courses...", file=sys.stderr)

        if max_courses and parsed_courses > max_courses:
            break

        course_code = text_at(elem, "code")
        course_title = text_at(elem, "name")
        campus = text_at(elem, "campus")

        if course_prefix_filter and not any(
            course_code.startswith(prefix) for prefix in course_prefix_filter
        ):
            elem.clear()
            continue

        default_sessions = [
            s.text.strip()
            for s in elem.findall("./sessions/sessions")
            if s.text and s.text.strip()
        ]

        for section in elem.findall("./sections/sections"):
            section_name = text_at(section, "name")
            section_type = text_at(section, "type")
            teach_method = text_at(section, "teachMethod")

            meeting_slots: list[str] = []
            locations: list[str] = []
            for meeting in section.findall("./meetingTimes/meetingTimes"):
                day = format_day(text_at(meeting, "./start/day"))
                start_time = format_millis_of_day(text_at(meeting, "./start/millisofday"))
                end_time = format_millis_of_day(text_at(meeting, "./end/millisofday"))
                session_code = text_at(meeting, "sessionCode")

                slot = " ".join(
                    part
                    for part in (
                        day,
                        f"{start_time}-{end_time}" if start_time and end_time else "",
                        f"({session_code})" if session_code else "",
                    )
                    if part
                )
                if slot:
                    meeting_slots.append(slot)

                building_code = text_at(meeting, "./building/buildingCode")
                room_number = text_at(meeting, "./building/buildingRoomNumber")
                room_suffix = text_at(meeting, "./building/buildingRoomSuffix")
                building_name = text_at(meeting, "./building/buildingName")

                location = " ".join(
                    part
                    for part in (
                        building_code,
                        f"{room_number}{room_suffix}" if room_number or room_suffix else "",
                    )
                    if part
                )
                if not location:
                    location = building_name
                if location:
                    locations.append(location)

            instructors = [
                " ".join(
                    part
                    for part in (
                        text_at(instructor, "firstName"),
                        text_at(instructor, "lastName"),
                    )
                    if part
                )
                for instructor in section.findall("./instructors/instructors")
            ]
            instructors = [name for name in instructors if name]

            delivery_modes = [
                text_at(mode, "mode")
                for mode in section.findall("./deliveryModes/deliveryModes")
                if text_at(mode, "mode")
            ]

            section_sessions = {
                s.text.strip()
                for s in section.findall(".//meetingTimes/meetingTimes/sessionCode")
                if s.text and s.text.strip()
            }
            if not section_sessions:
                section_sessions = set(default_sessions)

            if session_filter and not section_sessions.intersection(session_filter):
                continue

            division_code = text_at(
                section,
                "./enrolmentControls/enrolmentControls/primaryOrg/code",
            )
            if division_filter and division_code not in division_filter:
                continue

            current_enrolment = text_at(section, "currentEnrolment")
            max_enrolment = text_at(section, "maxEnrolment")
            current_waitlist = text_at(section, "currentWaitlist")
            waitlist_ind = text_at(section, "waitlistInd")
            cancel_ind = text_at(section, "cancelInd")
            enrolment_ind = text_at(section, "enrolmentInd")

            cur = to_int(current_enrolment)
            max_cap = to_int(max_enrolment)
            available_space = ""
            if cur is not None and max_cap is not None:
                available_space = max_cap - cur

            yield {
                "retrieved_at_utc": retrieved_at,
                "course_code": course_code,
                "course_title": course_title,
                "campus": campus,
                "session_codes": ";".join(sorted(section_sessions)),
                "section_name": section_name,
                "section_type": section_type,
                "teach_method": teach_method,
                "day_time": " | ".join(dict.fromkeys(meeting_slots)),
                "location": " | ".join(dict.fromkeys(locations)),
                "instructors": " | ".join(dict.fromkeys(instructors)),
                "delivery_mode": " | ".join(dict.fromkeys(delivery_modes)),
                "division_code": division_code,
                "current_enrolment": current_enrolment,
                "max_enrolment": max_enrolment,
                "available_space": available_space,
                "current_waitlist": current_waitlist,
                "waitlist_enabled": waitlist_ind,
                "cancelled": cancel_ind,
                "enrolment_indicator": enrolment_ind,
            }

        elem.clear()


def main() -> int:
    args = parse_args()

    session_filter = {s.strip() for s in args.session if s.strip()}
    division_filter = {d.strip().upper() for d in args.division if d.strip()}
    course_prefix_filter = {p.strip().upper() for p in args.course_prefix if p.strip()}

    output_path = Path(args.output)

    if args.keep_xml:
        xml_path = Path(args.keep_xml)
        xml_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        tmp = tempfile.NamedTemporaryFile(prefix="ttb_courses_", suffix=".xml", delete=False)
        tmp.close()
        xml_path = Path(tmp.name)

    try:
        print(f"Downloading XML from {args.endpoint} ...", file=sys.stderr)
        download_xml(args.endpoint, xml_path, timeout=args.timeout)

        fieldnames = [
            "retrieved_at_utc",
            "course_code",
            "course_title",
            "campus",
            "session_codes",
            "section_name",
            "section_type",
            "teach_method",
            "day_time",
            "location",
            "instructors",
            "delivery_mode",
            "division_code",
            "current_enrolment",
            "max_enrolment",
            "available_space",
            "current_waitlist",
            "waitlist_enabled",
            "cancelled",
            "enrolment_indicator",
        ]

        written = 0
        with output_path.open("w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in iter_rows(
                xml_path=xml_path,
                session_filter=session_filter,
                division_filter=division_filter,
                course_prefix_filter=course_prefix_filter,
                max_courses=args.max_courses,
            ):
                writer.writerow(row)
                written += 1

        print(f"Wrote {written} rows to {output_path}")
        if args.keep_xml:
            print(f"Saved raw XML to {xml_path}")
        return 0

    finally:
        if not args.keep_xml and xml_path.exists():
            xml_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
