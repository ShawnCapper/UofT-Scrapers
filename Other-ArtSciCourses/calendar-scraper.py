from random import randint

import requests
import json
import time
from bs4 import BeautifulSoup
import re

BASE_URL = "https://artsci.calendar.utoronto.ca/search-courses"

def parse_course_block(header):
    data = {}
    # get the full header text (aria-label may sometimes truncate around punctuation)
    title_str = header.get_text(strip=True)

    # match “CODE – Course Title” or “CODE - Course Title”, once only
    m = re.match(r'^(?P<code>[^–-]+?)\s*[–-]\s*(?P<name>.+)$', title_str)
    if m:
        code = m.group("code").strip()
        name = m.group("name").strip()
    else:
        code = title_str
        name = None

    data["code"] = code
    data["name"] = name

    details = header.parent.find("div", class_="views-row")
    def get_text(selector):
        elm = details.select_one(selector)
        return elm.get_text(strip=True) if elm else None

    def get_list(selector):
        elm = details.select(selector + " a")
        return [a.get_text(strip=True) for a in elm] or None

    data["previous_course_number"] = get_text(".views-field-field-previous-course-number .field-content")
    data["hours"]                  = get_text(".views-field-field-hours .field-content")
    data["description"]            = "\n".join(
        p.get_text(strip=True)
        for p in details.select(".views-field-body .field-content p")
    )
    data["exclusions"]             = get_list(".views-field-field-exclusion .field-content")
    data["prerequisites"]          = get_text(".views-field-field-prerequisite .field-content")
    data["corequisites"]           = get_text(".views-field-field-corequisite .field-content")
    data["recommended"]            = get_text(".views-field-field-recommended .field-content")
    data["breadth_requirements"]   = get_text(".views-field-field-breadth-requirements .field-content")

    return data

def main():
    page = 0
    courses = []

    while True:
        resp = requests.get(BASE_URL, params={"page": page})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        if soup.find(string="Your search yielded no results."):
            break

        headers = soup.select("h3.js-views-accordion-group-header")
        for header in headers:
            courses.append(parse_course_block(header))

        print(f"Page {page}: collected {len(headers)} courses")
        page += 1
        time.sleep(3)

    with open('courses.json', 'w', encoding='utf-8') as f:
        json.dump(courses, f, ensure_ascii=False, indent=4)
        f.write("\n")

if __name__ == "__main__":
    main()
