import os
import json
import re
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from bs4 import BeautifulSoup, NavigableString
from typing import Dict, List, Any, Optional

def html_to_markdown(element) -> str:
    """
    Convert HTML element to Markdown-formatted text.
    Preserves bold, italic, and line breaks.
    
    Args:
        element: BeautifulSoup element
        
    Returns:
        Markdown-formatted string
    """
    if element is None:
        return ""
        
    if isinstance(element, NavigableString):
        return str(element)
        
    result = ""
    for child in element.children:
        if isinstance(child, NavigableString):
            result += str(child)
        elif child.name == 'b' or child.name == 'strong':
            result += f"**{html_to_markdown(child)}**"
        elif child.name == 'i' or child.name == 'em':
            result += f"*{html_to_markdown(child)}*"
        elif child.name == 'br':
            result += "\n"
        elif child.name == 'p':
            inner_content = html_to_markdown(child)
            if inner_content:
                result += f"{inner_content}\n\n"
        elif child.name == 'ul':
            for li in child.find_all('li', recursive=False):
                result += f"- {html_to_markdown(li)}\n"
        elif child.name == 'ol':
            for i, li in enumerate(child.find_all('li', recursive=False), 1):
                result += f"{i}. {html_to_markdown(li)}\n"
        else:
            result += html_to_markdown(child)
            
    return result

def extract_posting_info(html_content: str, filename: str) -> Dict[str, Any]:
    """
    Extract job posting information from HTML content.

    Args:
        html_content: HTML content of the job posting
        filename: The filename, which may contain the posting ID if not found in title

    Returns:
        Dictionary containing the extracted job information
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # Initialize the result dictionary
    result = {}

    # Extract posting ID from title
    title = soup.find('title').text if soup.find('title') else ""
    posting_id_match = re.search(r'(\d+)\s*-\s*', title)

    # If not found in title, try looking in the header/h1 elements
    if not posting_id_match:
        headers = soup.find_all(['h1', 'h2', 'h3'])
        for header in headers:
            posting_id_match = re.search(r'(\d+)\s*-\s*', header.text)
            if posting_id_match:
                break

    # If still not found, try to extract from filename
    if not posting_id_match:
        posting_id_match = re.search(r'(\d+)', filename)

    # Finally, look for any text containing "Posting ID" or similar
    if not posting_id_match:
        id_elements = soup.find_all(string=re.compile(r'(Posting|Job|Position)\s*(ID|Number|#)'))
        for element in id_elements:
            posting_id_match = re.search(r'(\d+)', element.parent.text)
            if posting_id_match:
                break

    if posting_id_match:
        result['posting_id'] = int(posting_id_match.group(1))

    # Define field mappings (HTML label text -> JSON field name)
    field_mappings = {
        'Work Study Stream': 'work_study_stream',
        'Position Type': 'position_type',
        'Campus Location': 'campus_location',
        'Work Study Position Title': 'work_study_position_title',
        '# of Vacancies': 'vacancies',
        'This opportunity usually occurs during the following days/hours': 'days_hours',
        'Hours Per Week': 'hours_per_week',
        'Degree / Credential Level': 'degree_credential_level',
        'Department / Unit Overview': 'department_unit_overview',
        'Position Description': 'position_description',
        'Qualifications': 'qualifications',
        'Accessibility Considerations': 'accessibility_considerations',
        'Skills': 'skills',
        'Scholarship Recipients': 'scholarship_recipients',
        'Application Deadline': 'application_deadline',
        'Application Documents Required': 'application_documents_required',
        'Division': 'division',
        'Department / Unit': 'department_unit',
        "Supervisor's Name": 'supervisor_name',
        "Supervisor's Title": 'supervisor_title'
    }

    # Fields that should be stored as arrays
    array_fields = ['days_hours', 'accessibility_considerations', 'skills',
                   'scholarship_recipients', 'application_documents_required']

    # Text fields that should preserve formatting (as markdown)
    formatted_fields = ['department_unit_overview', 'position_description', 'qualifications']

    # Find job details table(s)
    tables = soup.find_all('table')

    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 2:
                label_cell = cells[0]
                value_cell = cells[1]
                label_text = label_cell.text.strip()

                # Match the label to our field mappings
                for field_label, field_name in field_mappings.items():
                    if field_label in label_text:
                        # Process the value based on the field type
                        if field_name in array_fields:
                            # For array fields, first check if there are list items
                            list_items = value_cell.find_all('li')
                            if list_items:
                                # Extract text from list items
                                result[field_name] = [html_to_markdown(item).strip() for item in list_items]
                            else:
                                # Split by commas, new lines, or bullet points
                                value_text = value_cell.text.strip()
                                result[field_name] = [item.strip() for item in re.split(r'[,\n•]+', value_text) if item.strip()]
                        elif field_name in formatted_fields:
                            # Preserve formatting for text fields
                            result[field_name] = html_to_markdown(value_cell).strip()
                        elif field_name == 'vacancies':
                            # Try to convert to integer
                            try:
                                result[field_name] = int(re.search(r'\d+', value_cell.text).group())
                            except (ValueError, AttributeError):
                                result[field_name] = value_cell.text.strip()
                        elif field_name == 'application_deadline':
                            # Clean up application deadline specifically - remove line breaks
                            deadline_text = value_cell.text.strip()
                            # Replace newlines and multiple spaces with a single space
                            deadline_text = re.sub(r'\s+', ' ', deadline_text)
                            result[field_name] = deadline_text
                        else:
                            # Replace newlines with \n for other text fields
                            result[field_name] = value_cell.text.strip().replace('\n', '\\n')
                        break

    # Filter out environment statements from accessibility considerations
    if 'accessibility_considerations' in result:
        # Patterns to filter out
        environment_patterns = [
            r"Occurs in an? (remote|in-person|hybrid) environment",
        ]
        filtered_considerations = []

        for item in result['accessibility_considerations']:
            should_keep = True
            for pattern in environment_patterns:
                if re.search(pattern, item, re.IGNORECASE):
                    should_keep = False
                    break
            if should_keep:
                filtered_considerations.append(item)

        result['accessibility_considerations'] = filtered_considerations

    # Determine work environment
    work_environment = "unspecified"
    if 'accessibility_considerations' in result:
        # We pass the original accessibility considerations (before filtering)
        # to the determine_job_environment function
        original_considerations = []
        for cell in soup.find_all('td'):
            if 'Accessibility Considerations' in cell.text and cell.find_next('td'):
                value_cell = cell.find_next('td')
                list_items = value_cell.find_all('li')
                if list_items:
                    original_considerations = [item.text.strip() for item in list_items]
                else:
                    original_considerations = [item.strip() for item in re.split(r'[,\n•]+', value_cell.text.strip()) if item.strip()]
                break

        work_environment = determine_job_environment(original_considerations)

    # Add work environment to the result
    result['work_environment'] = work_environment

    return result

def process_html_files(folder_path: str, existing_posting_ids: set = None) -> List[Dict[str, Any]]:
    """
    Process all HTML files in the specified folder and extract job posting information.
    Skip files with posting IDs that already exist in the provided set.

    Args:
        folder_path: Path to the folder containing HTML files
        existing_posting_ids: Set of posting IDs that have already been processed

    Returns:
        List of dictionaries containing the extracted job information
    """
    if existing_posting_ids is None:
        existing_posting_ids = set()

    results = []
    processed_ids = set()  # Track posting IDs to avoid duplicates within this run

    # Get all HTML files in the folder
    html_files = [f for f in os.listdir(folder_path) if f.endswith('.html')]

    for html_file in html_files:
        file_path = os.path.join(folder_path, html_file)

        try:
            # Read the HTML content
            with open(file_path, 'r', encoding='utf-8') as file:
                html_content = file.read()

            # Extract information from the HTML content
            posting_info = extract_posting_info(html_content, html_file)

            # Skip if no data was found
            if not posting_info:
                print(f"No job data found in: {html_file}")
                continue

            # Check for posting ID
            if 'posting_id' not in posting_info:
                print(f"Warning: No posting ID found for {html_file}")
            else:
                posting_id = posting_info['posting_id']

                # Skip if this posting ID is already in existing data
                if posting_id in existing_posting_ids:
                    print(f"Skipping existing posting ID {posting_id} in {html_file}")
                    continue

                # Check for duplicates within this processing run
                if posting_id in processed_ids:
                    print(f"Skipping duplicate posting ID {posting_id} in {html_file}")
                    continue

                processed_ids.add(posting_id)

            # Add the result to the list
            results.append(posting_info)
            print(f"Successfully processed: {html_file}")

        except Exception as e:
            print(f"Error processing {html_file}: {str(e)}")

    return results

def determine_job_environment(accessibility_items):
    """
    Determine if a job is hybrid, remote, or in-person based on accessibility considerations.
    Handles all possible combinations of environment indicators.

    Args:
        accessibility_items: List of accessibility consideration strings

    Returns:
        String indicating work environment: "hybrid", "remote", "in-person", or "unspecified"
    """
    # If we got passed a single string instead of a list, convert it
    if isinstance(accessibility_items, str):
        accessibility_items = [accessibility_items]

    # Handle empty or None input
    if not accessibility_items:
        return "unspecified"

    # Initialize flags
    is_remote = False
    is_in_person = False
    is_hybrid = False

    # Check each item in the accessibility considerations
    for item in accessibility_items:
        if isinstance(item, str):  # Make sure item is a string
            if "Occurs in a hybrid environment" in item:
                is_hybrid = True
            if "Occurs in a remote environment" in item:
                is_remote = True
            if "Occurs in an in-person environment" in item:
                is_in_person = True

    # Apply logic to handle all possible combinations
    if is_hybrid:
        # If hybrid is explicitly mentioned, it takes precedence regardless
        # of other flags (handles cases like hybrid+remote, hybrid+in-person)
        return "Hybrid"
    elif is_remote and is_in_person:
        # Both remote and in-person implies hybrid
        return "Hybrid"
    elif is_remote:
        # Only remote
        return "Remote"
    elif is_in_person:
        # Only in-person
        return "In-person"
    else:
        # None specified
        return "Unspecified"

class HTMLFileHandler(FileSystemEventHandler):
    """
    Event handler for monitoring HTML file changes in the input folder.
    """
    
    def __init__(self, output_path: str, split_output: bool = False):
        super().__init__()
        self.output_path = output_path
        self.split_output = split_output
        self.processed_files = set()
        self.existing_posting_ids = set()
        self._load_existing_data()
    
    def _load_existing_data(self):
        """Load existing posting IDs to avoid duplicates."""
        if self.split_output:
            if os.path.isdir(self.output_path):
                for fname in os.listdir(self.output_path):
                    if fname.endswith('.json'):
                        try:
                            with open(os.path.join(self.output_path, fname), 'r', encoding='utf-8') as jf:
                                item = json.load(jf)
                                if 'posting_id' in item:
                                    self.existing_posting_ids.add(item['posting_id'])
                        except Exception:
                            continue
        else:
            if os.path.exists(self.output_path):
                try:
                    with open(self.output_path, 'r', encoding='utf-8') as json_file:
                        existing_data = json.load(json_file)
                        self.existing_posting_ids = {item.get('posting_id') for item in existing_data if 'posting_id' in item}
                except Exception:
                    pass
    
    def on_created(self, event):
        """Handle file creation events."""
        if not event.is_directory and event.src_path.endswith('.html'):
            self._process_new_file(event.src_path)
    
    def on_modified(self, event):
        """Handle file modification events."""
        if not event.is_directory and event.src_path.endswith('.html'):
            self._process_new_file(event.src_path)
    
    def _process_new_file(self, file_path: str):
        """Process a single new or modified HTML file."""
        # Add a small delay to ensure file is fully written
        time.sleep(1)
        
        if file_path in self.processed_files:
            return
            
        try:
            print(f"Processing new file: {os.path.basename(file_path)}")
            
            with open(file_path, 'r', encoding='utf-8') as file:
                html_content = file.read()
            
            posting_info = extract_posting_info(html_content, os.path.basename(file_path))
            
            if not posting_info:
                print(f"No job data found in: {os.path.basename(file_path)}")
                return
            
            # Check for posting ID
            if 'posting_id' not in posting_info:
                print(f"Warning: No posting ID found for {os.path.basename(file_path)}")
            else:
                posting_id = posting_info['posting_id']
                
                if posting_id in self.existing_posting_ids:
                    print(f"Skipping existing posting ID {posting_id}")
                    return
                
                self.existing_posting_ids.add(posting_id)
            
            # Save the new posting
            if self.split_output:
                pid = posting_info.get('posting_id', 'unknown')
                outpath = os.path.join(self.output_path, f"{pid}.json")
                with open(outpath, 'w', encoding='utf-8') as jf:
                    json.dump(posting_info, jf, indent=4)
                print(f"Saved job posting to: {outpath}")
            else:
                # Load existing data, add new posting, and save
                existing_data = []
                if os.path.exists(self.output_path):
                    try:
                        with open(self.output_path, 'r', encoding='utf-8') as json_file:
                            existing_data = json.load(json_file)
                    except Exception:
                        pass
                
                existing_data.append(posting_info)
                existing_data.sort(key=lambda x: x.get('posting_id', float('inf')))
                
                with open(self.output_path, 'w', encoding='utf-8') as json_file:
                    json.dump(existing_data, json_file, indent=4)
                print(f"Added new job posting to: {self.output_path}")
            
            self.processed_files.add(file_path)
            
        except Exception as e:
            print(f"Error processing {os.path.basename(file_path)}: {str(e)}")

def run_continuous_monitor(folder_path: str, output_path: str, split_output: bool = False):
    """
    Run continuous monitoring of the folder for new HTML files.
    
    Args:
        folder_path: Path to monitor for HTML files
        output_path: Path for output JSON file(s)
        split_output: Whether to split output into individual files
    """
    print(f"Starting continuous monitoring of: {folder_path}")
    print(f"Output: {output_path}")
    print("Press Ctrl+C to stop monitoring...")
    
    # Create output directory if using split output
    if split_output:
        os.makedirs(output_path, exist_ok=True)
    
    # Create event handler and observer
    event_handler = HTMLFileHandler(output_path, split_output)
    observer = Observer()
    observer.schedule(event_handler, folder_path, recursive=False)
    
    # Process any existing files first
    print("Processing existing files...")
    initial_results = process_html_files(folder_path, event_handler.existing_posting_ids)
    
    if initial_results:
        if split_output:
            for job in initial_results:
                pid = job.get('posting_id', 'unknown')
                outpath = os.path.join(output_path, f"{pid}.json")
                with open(outpath, 'w', encoding='utf-8') as jf:
                    json.dump(job, jf, indent=4)
            print(f"Processed {len(initial_results)} existing files")
        else:
            existing_data = []
            if os.path.exists(output_path):
                try:
                    with open(output_path, 'r', encoding='utf-8') as json_file:
                        existing_data = json.load(json_file)
                except Exception:
                    pass
            
            combined_results = existing_data + initial_results
            combined_results.sort(key=lambda x: x.get('posting_id', float('inf')))
            
            with open(output_path, 'w', encoding='utf-8') as json_file:
                json.dump(combined_results, json_file, indent=4)
            print(f"Added {len(initial_results)} new job postings")
    
    # Start monitoring
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping monitor...")
        observer.stop()
    
    observer.join()
    print("Monitor stopped.")

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Parse University of Toronto Work Study job postings from HTML files.")
    parser.add_argument("folder_path", help="Path to the folder containing HTML files")
    parser.add_argument("--output", default="work_study_jobs.json", help="Output JSON file path")
    parser.add_argument("--split", action="store_true", help="Write each job to its own JSON file in the output directory")
    parser.add_argument("--monitor", action="store_true", help="Continuously monitor folder for new HTML files")

    args = parser.parse_args()

    if not os.path.exists(args.folder_path):
        print(f"Error: The folder path '{args.folder_path}' does not exist.")
        return

    if args.split:
        if os.path.isfile(args.output):
            print(f"Error: The output path '{args.output}' exists as a file. Please specify a directory for split output.")
            return
    else:
        # For non-split output, ensure the directory exists
        output_dir = os.path.dirname(args.output)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"Created output directory: {output_dir}")

    if args.monitor:
        # Run the continuous monitor function
        run_continuous_monitor(args.folder_path, args.output, args.split)
    else:
        # Process files once and exit
        results = process_html_files(args.folder_path)

        if not results:
            print("No valid job postings found in the HTML files.")
            return

        if args.split:
            os.makedirs(args.output, exist_ok=True)

            # Write each job to its own JSON file
            for job in results:
                posting_id = job.get('posting_id', 'unknown')
                output_file = os.path.join(args.output, f"{posting_id}.json")

                with open(output_file, 'w', encoding='utf-8') as json_file:
                    json.dump(job, json_file, indent=4)

            print(f"Successfully processed {len(results)} job postings into {args.output}/")
        else:
            # Write all results to a single JSON file
            with open(args.output, 'w', encoding='utf-8') as json_file:
                json.dump(results, json_file, indent=4)

            print(f"Successfully processed {len(results)} job postings and saved to {args.output}")

if __name__ == "__main__":
    main()
