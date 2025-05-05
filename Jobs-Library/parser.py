import os
import json
import re
import glob
from datetime import datetime
from bs4 import BeautifulSoup


def extract_id_from_filename(file_path):
    """
    Extract the numeric id from the HTML file name.
    For example, if the file name is "14.html" or "posting_14.html", it returns 14.
    """
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    m = re.search(r'\d+', base_name)
    if m:
        return int(m.group())
    return None


def normalize_position_title(position):
    """
    Normalize position titles according to standard naming conventions.
    Maps full titles and abbreviations to standardized names.
    """
    mapping = {
        "Student Library Assistant (SLA)": "Student Library Assistant",
        "SLA": "Student Library Assistant",
        "Graduate Library Assistant (GSLA)": "Graduate Library Assistant",
        "GSLA": "Graduate Library Assistant",
        "Assistant Help Desk Advisor (AHDA)": "Assistant Help Desk Advisor",
        "AHDA": "Assistant Help Desk Advisor",
        "Assistant Computer Library Assistant (ACAFA)": "Assistant Computer Library Assistant",
        "ACAFA": "Assistant Computer Library Assistant"
    }

    # Check for exact matches
    if position in mapping:
        return mapping[position]

    # Check for case-insensitive matches
    for key, value in mapping.items():
        if position.upper() == key.upper():
            return value

    return position


def parse_html_file(html_file_path, file_id):
    """Parse a single HTML file and extract job posting details, adding the provided ID."""
    with open(html_file_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, "html.parser")

    # Extract posting number from the <h2> element containing "Posting No."
    posting_no = ""
    h2 = soup.find("h2", string=re.compile(r"Posting No\.", re.I))
    if h2:
        m = re.search(r"Posting No\.\s*(\d+)", h2.get_text())
        if m:
            posting_no = m.group(1)

    # Define a dictionary to map field labels to JSON keys.
    fields = {
        "Position": "position",
        "Department": "department",
        "Period of Employment": "period_of_employment",
        "Qualifications": "qualifications",
        "Duties": "duties",
        "Hours per Week": "hours_per_week",
        "Hourly Rate": "hourly_rate"
    }

    posting_data = {
        "id": file_id,  # Added ID from filename
        "period_position_number": posting_no
    }

    # Locate the ordered list containing job details.
    ol = soup.find("ol", class_="no_bullets")
    if ol:
        li_items = ol.find_all("li")
        for li in li_items:
            label_div = li.find("div", class_="label")
            if not label_div:
                continue
            label_text = label_div.get_text(strip=True).rstrip(":")
            if label_text in fields:
                value_div = label_div.find_next_sibling("div")
                if value_div:
                    value_text = " ".join(value_div.stripped_strings)
                    field_key = fields[label_text]

                    if label_text == "Hourly Rate":
                        # Check for '-' as the separator; otherwise, use comma.
                        if '-' in value_text:
                            rate_strings = [rate.strip() for rate in value_text.split('-')]
                        else:
                            rate_strings = [rate.strip() for rate in value_text.split(',')]

                        # Convert strings with dollar signs to numeric values
                        rates = []
                        for rate_str in rate_strings:
                            try:
                                # Remove '$' and convert to float
                                rate_numeric = float(rate_str.replace('$', '').strip())
                                rates.append(rate_numeric)
                            except (ValueError, TypeError):
                                # Keep original string if conversion fails
                                if rate_str.strip():  # Only add non-empty strings
                                    rates.append(rate_str)
                        posting_data[field_key] = rates
                    elif label_text == "Position":
                        # Apply position normalization
                        posting_data[field_key] = normalize_position_title(value_text)
                    else:
                        # For all other fields, store the value text directly
                        posting_data[field_key] = value_text

    # Extract the accepted applications deadline from a <p> tag.
    accepted_until = ""
    p_tags = soup.find_all("p")
    for p in p_tags:
        if "accepted until" in p.get_text().lower():
            b = p.find("b")
            if b:
                accepted_until = b.get_text(strip=True)
            break
    posting_data["accepted_until"] = accepted_until

    return posting_data


def process_all_postings(html_folder, archive_file):
    """Process HTML files and append new postings to the existing archive file."""
    # Load existing archive data if it exists
    existing_data = []
    existing_ids = set()
    try:
        with open(archive_file, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
            existing_ids = {entry["id"] for entry in existing_data}
        print(f"Loaded {len(existing_data)} existing postings from {archive_file}")
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"No existing archive found at {archive_file} or invalid JSON. Creating new file.")

    # Process HTML files not already in the archive
    new_data = []
    html_files = glob.glob(os.path.join(html_folder, "*.html"))

    for html_file in html_files:
        file_id = extract_id_from_filename(html_file)
        if file_id not in existing_ids:
            posting_data = parse_html_file(html_file, file_id)
            new_data.append(posting_data)
            print(f"Parsed new posting: {html_file} with ID: {file_id}")
        else:
            print(f"Skipping already archived posting with ID: {file_id}")

    if not new_data:
        print("No new postings found to add to archive.")
        return

    # Combine existing and new data
    combined_data = existing_data + new_data

    # Sort the aggregated data by ID in descending order (newest on top, oldest on bottom)
    combined_data.sort(key=lambda x: (x["id"] if x["id"] is not None else float('-inf')), reverse=True)

    # Write the updated data back to the archive file
    with open(archive_file, "w", encoding="utf-8") as f:
        json.dump(combined_data, f, ensure_ascii=False, indent=4)

    print(f"Added {len(new_data)} new postings to {archive_file}")


if __name__ == "__main__":
    html_folder = "valid_postings"
    archive_file = "archive.json"
    process_all_postings(html_folder, archive_file)
