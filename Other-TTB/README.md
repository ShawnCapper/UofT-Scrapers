# TTB Enrollment Scraper

This project includes a Python script that collects section-level enrollment data
from U of T Timetable Builder.

## File

- `ttb_enrollment_scraper.py`: downloads XML from TTB and exports enrollment data to CSV.

## Run

```bash
python3 ttb_enrollment_scraper.py --output ttb_enrollment.csv
```

## Useful Filters

Only Fall/Winter 2025-26 session code `20259`:

```bash
python3 ttb_enrollment_scraper.py --session 20259 --output ttb_20259.csv
```

Only Arts & Science divisions for CSC courses:

```bash
python3 ttb_enrollment_scraper.py --division ARTSC --course-prefix CSC --output artsci_csc.csv
```

Quick test run (first 100 courses only):

```bash
python3 ttb_enrollment_scraper.py --max-courses 100 --output sample.csv
```

## LEC Enrollment Pivot By Building

Use this helper script to generate a CSV where each session code is its own
column and rows are building codes.

```bash
python3 lec_enrollment_by_building.py \
	--input ttb_enrollment.csv \
	--output lec_enrollment_by_building_session.csv
```

Optional: pass your own building list.

```bash
python3 lec_enrollment_by_building.py \
	--buildings BA,ES,EX,GB,HH,HS,MC,MP,MS,MY,OI,PB,RL,RT,RU,RW,SF,SM,SS,WB
```

## CSV Columns

- `retrieved_at_utc`
- `course_code`
- `course_title`
- `campus`
- `session_codes`
- `section_name`
- `section_type`
- `teach_method`
- `day_time`
- `location`
- `instructors`
- `delivery_mode`
- `division_code`
- `current_enrolment`
- `max_enrolment`
- `available_space`
- `current_waitlist`
- `waitlist_enabled`
- `cancelled`
- `enrolment_indicator`

## Notes

- Data source endpoint used by this script: `https://api.easi.utoronto.ca/ttb/getCourses`.
- The API returns XML; the script parses it and writes a flat CSV.
- This script reads public timetable data and does not enroll students.
