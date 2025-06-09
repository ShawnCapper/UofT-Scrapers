from random import randint
import argparse
import requests
import json
import time
from bs4 import BeautifulSoup
import re

COURSE_URL = "https://artsci.calendar.utoronto.ca/search-courses"
PROGRAM_URL = "https://artsci.calendar.utoronto.ca/search-programs"

def parse_course_block(header):
    data = {}
    # get the full header text (aria-label may sometimes truncate around punctuation)
    title_str = header.get_text(strip=True)

    # match "CODE – Course Title" or "CODE - Course Title", once only
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

def parse_program_block(header):
    data = {}
    # Get the full header text
    title_str = header.get_text(strip=True)
    
    # Regular expression to match program title pattern:
    # "Program Name (Program Category) - PROGRAM_CODE"
    m = re.match(r'^(?P<name>.+?)\s*\((?P<category>[^)]+)\)\s*-\s*(?P<code>[A-Z0-9]+)', title_str)
    
    if m:
        program_name = m.group("name").strip()
        program_category = m.group("category").strip()
        program_code = m.group("code").strip()
    else:
        program_name = title_str
        program_category = None
        program_code = None

    data["name"] = program_name
    data["category"] = program_category
    data["code"] = program_code
    
    # Get program content
    details = header.parent.find("div", class_="views-row")
    
    # Extract the content
    if details:
        # Get all paragraphs from the program description
        paragraphs = details.find_all("p")
        if paragraphs:
            data["description"] = "\n".join(p.get_text(strip=True) for p in paragraphs)
        else:
            data["description"] = details.get_text(strip=True)
            
        # Look for completion requirements section which is often formatted differently
        completion_reqs = details.find(string=re.compile("Completion Requirements", re.IGNORECASE))
        if completion_reqs:
            # Find the parent element and get all the text afterwards
            parent = completion_reqs.parent
            if parent:
                # Get all siblings after the completion requirements header
                requirements_text = []
                for sibling in parent.next_siblings:
                    if sibling.name == "h3":  # Stop at next header
                        break
                    if hasattr(sibling, "get_text"):
                        requirements_text.append(sibling.get_text(strip=True))
                
                data["completion_requirements"] = "\n".join(requirement for requirement in requirements_text if requirement)
    
    return data

def scrape_courses():
    print("Scraping courses...")
    page = 0
    courses = []

    while True:
        resp = requests.get(COURSE_URL, params={"page": page})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        if soup.find(string="Your search yielded no results."):
            break

        headers = soup.select("h3.js-views-accordion-group-header")
        if not headers:
            break
            
        for header in headers:
            courses.append(parse_course_block(header))

        print(f"Page {page}: collected {len(headers)} courses")
        page += 1
        time.sleep(randint(2, 5))  # Add some random delay to be more polite to the server

    print(f"Total courses collected: {len(courses)}")
    with open('courses.json', 'w', encoding='utf-8') as f:
        json.dump(courses, f, ensure_ascii=False, indent=4)
        f.write("\n")
    
    return courses

def scrape_programs():
    print("Scraping programs...")
    page = 0
    programs = []
    
    while True:
        resp = requests.get(PROGRAM_URL, params={"page": page})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        if soup.find(string="Your search yielded no results."):
            break

        headers = soup.select("h3.js-views-accordion-group-header")
        if not headers:  # If no headers are found, we've reached the end
            break
            
        for header in headers:
            programs.append(parse_program_block(header))

        print(f"Page {page}: collected {len(headers)} programs")
        page += 1
        time.sleep(randint(2, 5))  # Add some random delay to be more polite to the server

    print(f"Total programs collected: {len(programs)}")
    with open('programs.json', 'w', encoding='utf-8') as f:
        json.dump(programs, f, ensure_ascii=False, indent=4)
        f.write("\n")
    
    return programs

def main():
    parser = argparse.ArgumentParser(description='Scrape UofT Arts & Science Calendar for courses and/or programs.')
    parser.add_argument('--courses', action='store_true', help='Scrape courses')
    parser.add_argument('--programs', action='store_true', help='Scrape programs')
    
    args = parser.parse_args()
    
    # If neither flag is specified, scrape both
    if not args.courses and not args.programs:
        args.courses = True
        args.programs = True
        
    if args.courses:
        scrape_courses()
        
    if args.programs:
        scrape_programs()

if __name__ == "__main__":
    main()
