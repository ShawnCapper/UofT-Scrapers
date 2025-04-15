import os
import json
import argparse
from bs4 import BeautifulSoup
import re
from datetime import datetime

def parse_job_posting(html_content, filename):
    """Parse a single on-campus job posting HTML and return structured data."""
    soup = BeautifulSoup(html_content, "html.parser")
    job_data = {"source_file": filename}

    # Extract job ID and title
    job_title_elem = soup.select_one("h1.dashboard-header__profile-information-name")
    if job_title_elem:
        title_text = job_title_elem.text.strip()
        # Extract job ID and clean the title
        match = re.search(r'(\d+)\s*-\s*(.+)', title_text)
        if match:
            job_data["job_id"] = match.group(1).strip()
            job_data["job_title"] = match.group(2).strip()
        else:
            job_data["job_title"] = title_text

    # Extract organization and division
    org_elem = soup.select_one("h2.h6")
    if org_elem:
        org_text = org_elem.text.strip()
        if "-" in org_text:
            parts = org_text.split("-", 1)
            job_data["organization"] = parts[0].strip()
            job_data["division"] = parts[1].strip()
        else:
            job_data["organization"] = org_text

    # Extract job details from the Job Posting Information panel
    job_info_panel = soup.select_one(".panel-heading:-soup-contains('Job Posting Information') + .panel-body")
    if job_info_panel:
        for row in job_info_panel.select("tr"):
            cells = row.select("td")
            if len(cells) >= 2:
                header_elem = cells[0].select_one("strong")
                if header_elem:
                    field_name = header_elem.text.strip().replace(":", "").lower()
                    value = cells[1].text.strip()

                    # Map fields to standardized names
                    mapping = {
                        "position type": "position_type",
                        "is this a research opportunity?": "research_opportunity",
                        "job title": "job_title",
                        "occupation type": "occupation_type",
                        "job description": "job_description",
                        "job requirements": "job_requirements",
                        "contract or permanent?": "employment_type",
                        "start date": "start_date",
                        "end date": "end_date",
                        "number of positions": "positions_available",
                        "campus job location": "campus",
                        "job location details (i.e. building/faculty)": "location_details",
                        "annual salary or per hour?": "payment_type",
                        "salary or hourly wage": "wage",
                        "hours per week": "hours_per_week",
                        "type of schedule": "schedule_type",
                        "schedule details": "schedule_details",
                        "target all programs of study": "all_programs"
                    }

                    field_key = mapping.get(field_name)
                    if field_key:
                        # Process specific fields with special handling
                        if field_key == "research_opportunity":
                            job_data[field_key] = value.lower() == "yes"
                        elif field_key in ["start_date", "end_date"]:
                            try:
                                # Try to parse date in MM/DD/YYYY format
                                date_obj = datetime.strptime(value, "%m/%d/%Y")
                                job_data[field_key] = date_obj.strftime("%B %d, %Y")
                            except ValueError:
                                # If parsing fails, keep the original value
                                job_data[field_key] = value
                        elif field_key == "positions_available":
                            try:
                                job_data[field_key] = int(value)
                            except (ValueError, TypeError):
                                # If conversion fails, keep as string
                                job_data[field_key] = value
                        elif field_key == "all_programs":
                            job_data[field_key] = value.lower() == "yes"
                        else:
                            job_data[field_key] = value

    # Extract application information
    app_info_panel = soup.select_one(".panel-heading:-soup-contains('Application Information') + .panel-body")
    if app_info_panel:
        # Get application deadline
        deadline_row = app_info_panel.select_one("tr:-soup-contains('Application Deadline')")
        if deadline_row:
            deadline_cell = deadline_row.select_one("td:nth-of-type(2)")
            if deadline_cell:
                job_data["application_deadline"] = deadline_cell.text.replace("\n", "").strip()

        # Process other application info
        for row in app_info_panel.select("tr"):
            cells = row.select("td")
            if len(cells) >= 2:
                header_elem = cells[0].select_one("strong")
                if header_elem:
                    field_name = header_elem.text.strip().replace(":", "").lower()
                    value = cells[1].text.strip()

                    mapping = {
                        "application procedure": "application_procedure",
                        "if by website, go to": "application_website",
                        "additional application information": "additional_info",
                        "application documents required": "documents_required"
                    }

                    field_key = mapping.get(field_name)
                    if field_key:
                        job_data[field_key] = value

    # Extract company information
    company_info_panel = soup.select_one(".panel-heading:-soup-contains('Company Info') + .panel-body")
    if company_info_panel:
        for row in company_info_panel.select("tr"):
            cells = row.select("td")
            if len(cells) >= 2:
                header_elem = cells[0].select_one("strong")
                if header_elem:
                    field_name = header_elem.text.strip().replace(":", "").lower()
                    value = cells[1].text.strip()

                    mapping = {
                        "organization": "organization",
                        "division": "division",
                        "department": "department",
                        "salutation": "contact_salutation",
                        "first name": "contact_first_name",
                        "last name": "contact_last_name",
                        "building": "building",
                        "website": "website"
                    }

                    field_key = mapping.get(field_name)
                    if field_key:
                        # Special case for website (extract just the text)
                        if field_key == "website" and cells[1].select_one("a"):
                            job_data[field_key] = cells[1].select_one("a").text.strip()
                        else:
                            job_data[field_key] = value

    return job_data

def process_directory(directory_path):
    """Process all HTML files in the given directory and return list of job data."""
    job_data_list = []

    for filename in os.listdir(directory_path):
        if filename.endswith(".html"):
            file_path = os.path.join(directory_path, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    html_content = file.read()
                    job_data = parse_job_posting(html_content, filename)
                    job_data_list.append(job_data)
                    print(f'Processed: "{filename}"')
            except Exception as e:
                print(f'Error processing "{filename}": {str(e)}')

    return job_data_list

def main():
    parser = argparse.ArgumentParser(description="Parse on-campus job postings from HTML files.")
    parser.add_argument("input_dir", help="Directory containing HTML job postings")
    parser.add_argument("--output", "-o", default="on_campus_jobs.json",
                        help="Output JSON file path (default: on_campus_jobs.json)")

    args = parser.parse_args()

    if not os.path.isdir(args.input_dir):
        print(f"Error: {args.input_dir} is not a valid directory")
        return

    # Process all job postings
    job_data_list = process_directory(args.input_dir)

    # Remove source_file key from each job data
    for job_data in job_data_list:
        job_data.pop("source_file", None)

    # Write to JSON file
    with open(args.output, "w", encoding="utf-8") as json_file:
        json.dump(job_data_list, json_file, indent=2)

    print(f"Processed {len(job_data_list)} job postings. Data saved to {args.output}")

if __name__ == "__main__":
    main()
