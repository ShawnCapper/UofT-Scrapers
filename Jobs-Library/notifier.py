import requests
import time
from bs4 import BeautifulSoup
import os
import json
import datetime
import re


def check_for_new_postings(vacancies_url, known_ids_file="known_postings.json"):
    """
    Checks the given library jobs vacancies page for new postings.
    If new postings are found, returns a list of new IDs.
    Otherwise, returns an empty list.
    """
    # Load previously known postings from JSON (if the file exists)
    if os.path.exists(known_ids_file):
        with open(known_ids_file, "r", encoding="utf-8") as f:
            known_ids = json.load(f)
    else:
        known_ids = []

    # Also check the archive.json for existing postings
    archive_file = "archive.json"
    archived_ids = set()
    if os.path.exists(archive_file):
        try:
            with open(archive_file, "r", encoding="utf-8") as f:
                archive_data = json.load(f)
                archived_ids = {entry["id"] for entry in archive_data}
        except (json.JSONDecodeError, KeyError):
            print(f"Warning: Could not read IDs from {archive_file}")

    # Combine both known and archived IDs
    all_known_ids = set(known_ids) | archived_ids

    # Fetch vacancies page
    response = requests.get(vacancies_url, timeout=10)
    if response.status_code != 200:
        print(f"Failed to fetch vacancies page (Status: {response.status_code}).")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    # Look for links to job postings
    new_postings = []
    view_links = soup.find_all("a", href=True)

    # Pattern to extract posting IDs from URLs
    url_pattern = re.compile(r'/posting/view/(\d+)')

    for link in view_links:
        href = link.get('href')
        match = url_pattern.search(href)
        if match:
            posting_id = int(match.group(1))
            if posting_id not in all_known_ids:
                new_postings.append(posting_id)
                print(f"Found new posting with ID: {posting_id}")

    # Update local file if new postings are found
    if new_postings:
        all_postings = list(all_known_ids) + new_postings
        with open(known_ids_file, "w", encoding="utf-8") as f:
            json.dump(all_postings, f, indent=2)

    return new_postings


def scrape_posting(posting_id):
    """
    Scrape a single job posting by ID and save it to the valid_postings directory.
    Returns the path to the saved HTML file.
    """
    output_dir = "valid_postings"
    os.makedirs(output_dir, exist_ok=True)

    base_url = "https://studentjobs.library.utoronto.ca/index.php/posting/view/{}"
    url = base_url.format(posting_id)

    try:
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            print(f"Posting {posting_id} returned status code {response.status_code}")
            return None

        html_content = response.text

        if "Invalid posting ID" in html_content:
            print(f"Posting {posting_id} is invalid, skipping.")
            return None

        file_path = os.path.join(output_dir, f"posting_{posting_id}.html")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"Saved posting {posting_id} successfully.")
        return file_path

    except requests.RequestException as e:
        print(f"Error fetching posting {posting_id}: {e}")
        return None


def extract_id_from_filename(file_path):
    """
    Extract the numeric id from the HTML file name.
    For example, if the file name is "14.html" or "posting_14.html", it returns 14.
    """
    import re
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    m = re.search(r'\d+', base_name)
    if m:
        return int(m.group())
    return None


def process_new_postings(html_files, archive_file="archive.json"):
    """
    Process the newly scraped HTML files and add them to the archive.
    """
    from parser import parse_html_file

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

    # Process the new HTML files
    new_data = []
    for html_file in html_files:
        file_id = extract_id_from_filename(html_file)
        if file_id is None:
            print(f"Could not extract ID from {html_file}")
            continue

        if file_id not in existing_ids:
            try:
                posting_data = parse_html_file(html_file, file_id)
                posting_data["html_folder"] = os.path.dirname(html_file)
                posting_data["timestamp"] = datetime.datetime.now().isoformat()
                new_data.append(posting_data)
                print(f"Parsed new posting: {html_file} with ID: {file_id}")
            except Exception as e:
                print(f"Error parsing {html_file}: {e}")
        else:
            print(f"Skipping already archived posting with ID: {file_id}")

    if not new_data:
        print("No new postings found to add to archive.")
        return

    # Combine existing and new data
    combined_data = existing_data + new_data

    # Sort the aggregated data by ID
    combined_data.sort(key=lambda x: (x["id"] if x["id"] is not None else float('inf')))

    # Write the updated data back to the archive file
    with open(archive_file, "w", encoding="utf-8") as f:
        json.dump(combined_data, f, ensure_ascii=False, indent=4)

    print(f"Added {len(new_data)} new postings to {archive_file}")


def main():
    vacancies_url = "https://studentjobs.library.utoronto.ca/index.php/student/vacancies"
    print(f"Checking for new postings at {datetime.datetime.now().isoformat()}...")

    try:
        new_postings = check_for_new_postings(vacancies_url)

        if new_postings:
            print(f"Found {len(new_postings)} new posting(s): {new_postings}")

            # Scrape each new posting
            scraped_files = []
            for job_id in new_postings:
                print(f"Scraping job ID {job_id}...")
                file_path = scrape_posting(job_id)
                if file_path:
                    scraped_files.append(file_path)
                time.sleep(1)  # Be nice to the server

            # Process and parse the scraped files
            if scraped_files:
                print("Processing scraped files...")
                process_new_postings(scraped_files)
        else:
            print("No new postings found.")

    except Exception as e:
        print(f"Error during main execution: {e}")


if __name__ == "__main__":
    while True:
        main()
        print(f"Completed check at {datetime.datetime.now().isoformat()}, sleeping for 1 hour...\n")
        time.sleep(3600)
