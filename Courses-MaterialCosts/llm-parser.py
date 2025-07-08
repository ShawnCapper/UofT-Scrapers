import csv
import json
import requests
import time
from tqdm import tqdm
import os

# --- Configuration ---
OLLAMA_ENDPOINT = 'http://localhost:11434/api/generate'
OLLAMA_MODEL = 'gemma3:4b'
INPUT_CSV = 'Courses-MaterialCosts/MaterialCost_Winter2025.csv'
OUTPUT_JSONL = 'structured_costs.jsonl'
RETRY_ATTEMPTS = 2

# --- NEW CHANGE 1: EVEN MORE ROBUST PROMPT ---
PROMPT_TEMPLATE = """
You are a precise data extraction assistant. Your task is to analyze text describing course materials and convert it into a structured JSON format. 
From the provided text, extract all learning materials. For each distinct item, provide its type, title, author, cost, currency, and any other relevant notes.

Return a JSON object with a single key "materials" which contains a list of objects. Each object should have these keys:
- "type": (string) "book", "software", "equipment", "coursepack", "ebook", "other", "no_cost".
- "title": (string or null) The title of the book or name of the item.
- "author": (string or null) The author(s) of the book. Null for non-book items.
- "cost": (float or null) The lowest cost mentioned as a number. If no cost is specified, use null. For free items, use 0.0.
- "currency": (string or null) e.g., "CAD" or "USD". If not specified, assume "CAD".
- "notes": (string) Include ALL original details about the specific item.

If the text says materials are available via the library, it is "no_cost".

--- EXAMPLE 1: Complex Input ---
Input Text:
"Michelle Good, Five Little Indians. Toronto: Harper Perennial, 2020. $22.99  Brianna Jonnie & Nahanni Shingoose, If I Go Missing. Toronto: James Lorimer, 2019. $24.95"

Expected JSON Output:
{{
  "materials": [
    {{"type": "book", "title": "Five Little Indians", "author": "Michelle Good", "cost": 22.99, "currency": "CAD", "notes": "Michelle Good, Five Little Indians. Toronto: Harper Perennial, 2020. $22.99"}},
    {{"type": "book", "title": "If I Go Missing", "author": "Brianna Jonnie & Nahanni Shingoose", "cost": 24.95, "currency": "CAD", "notes": "Brianna Jonnie & Nahanni Shingoose, If I Go Missing. Toronto: James Lorimer, 2019. $24.95"}}
  ]
}}

--- EXAMPLE 2: No-Cost Input ---
Input Text:
"No cost - all available via UofT library"

Expected JSON Output:
{{
  "materials": [
    {{"type": "no_cost", "title": null, "author": null, "cost": 0.0, "currency": null, "notes": "No cost - all available via UofT library"}}
  ]
}}

--- EXAMPLE 3: Input with Notes ---
Input Text:
"S. Broverman, Actuarial Science Coursebook for [ACT247H + ACT348H 2024-25] Edition. PowerPoint slides - Basil Singer"

Expected JSON Output:
{{
    "materials": [
        {{"type": "coursepack", "title": "Actuarial Science Coursebook for [ACT247H + ACT348H 2024-25] Edition", "author": "S. Broverman", "cost": null, "currency": null, "notes": "S. Broverman, Actuarial Science Coursebook for [ACT247H + ACT348H 2024-25] Edition."}},
        {{"type": "other", "title": "PowerPoint slides", "author": "Basil Singer", "cost": null, "currency": null, "notes": "PowerPoint slides - Basil Singer"}}
    ]
}}

--- REAL TASK ---
Input Text:
{text_to_process}

Expected JSON Output:
"""


def call_ollama(text):
    """Sends a request to the Ollama API, with retries, and returns the structured JSON response."""
    if not text or text.strip() == '':
        return {"materials": []}

    cleaned_text = text.replace('\n', ' ').replace('"', "'").strip()
    
    prompt = PROMPT_TEMPLATE.format(text_to_process=cleaned_text)
    
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }

    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = requests.post(OLLAMA_ENDPOINT, json=payload, timeout=300)
            response.raise_for_status()
            response_data_str = response.json().get('response', '{}')
            parsed_json = json.loads(response_data_str)
            # Check for a valid response structure
            if "materials" in parsed_json and isinstance(parsed_json["materials"], list):
                return parsed_json # Success!
            else:
                 # The model returned valid JSON, but not in the format we want.
                print(f"\n[WARNING] Attempt {attempt + 1}: Model returned valid JSON but wrong structure. Retrying...")
                time.sleep(2) # Wait 2 seconds before retrying

        except requests.exceptions.ReadTimeout:
            print(f"\n[ERROR] Attempt {attempt + 1}: Read timed out.")
            if attempt < RETRY_ATTEMPTS - 1:
                time.sleep(5) # Wait longer after a timeout
            else:
                return {"error": "Request timed out after multiple attempts", "materials": []}
        except requests.exceptions.RequestException as e:
            return {"error": f"RequestException: {e}", "materials": []}
        except json.JSONDecodeError as e:
            print(f"\n[WARNING] Attempt {attempt + 1}: Error decoding JSON. Retrying...")
            print(f"Model output was: {response_data_str}")
            time.sleep(2)

    # If all retries fail
    return {"error": "Failed to get valid response from model after multiple attempts", "materials": []}


def process_csv_to_jsonl():
    """Reads the CSV, processes each row, and appends to a .jsonl file."""
    processed_courses = set()
    if os.path.exists(OUTPUT_JSONL):
        try:
            with open(OUTPUT_JSONL, 'r', encoding='utf-8') as f:
                for line in f:
                    processed_courses.add(json.loads(line)['course_code'])
            print(f"Found {len(processed_courses)} already processed courses in {OUTPUT_JSONL}. Resuming.")
        except (json.JSONDecodeError, IOError):
            print(f"Warning: Could not read {OUTPUT_JSONL} to resume. Starting fresh.")
            processed_courses = set()

    try:
        with open(INPUT_CSV, mode='r', encoding='utf-8-sig') as infile, \
             open(OUTPUT_JSONL, mode='a', encoding='utf-8') as outfile:
            reader = csv.DictReader(infile)
            rows_to_process = [row for row in reader if row.get('Course', '').strip() and row.get('Course', '').strip() not in processed_courses]
            
            if not rows_to_process:
                print("All courses from CSV already processed. Nothing to do.")
                return

            for row in tqdm(rows_to_process, desc="Processing Courses"):
                course_code = row.get('Course', '').strip()
                if not course_code: continue

                mandatory_text = row.get('Mandatory Learning Materials', '').strip()
                mandatory_data = call_ollama(mandatory_text)

                course_entry = {"course_code": course_code, "mandatory_materials": mandatory_data}
                json.dump(course_entry, outfile, ensure_ascii=False)
                outfile.write('\n')

    except FileNotFoundError:
        print(f"Error: The file {INPUT_CSV} was not found.")
        return

    print(f"\nProcessing complete. Structured data saved to {OUTPUT_JSONL}")


if __name__ == "__main__":
    process_csv_to_jsonl()
