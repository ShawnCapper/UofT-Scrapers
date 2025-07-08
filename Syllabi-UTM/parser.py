import requests
import json
import fitz  # PyMuPDF
from docx import Document # For .docx files
from pathlib import Path
import sys

# --- Configuration ---
SYLLABUS_DIRECTORY = "syllabi"
OLLAMA_MODEL = "gemma3:4b"
OLLAMA_API_URL = "http://localhost:11434/api/generate"
OUTPUT_FILENAME = "marking_schemes_extracted.json"

# --- The Prompt Sent to the LLM (No changes needed here) ---
PROMPT_TEMPLATE = """
You are an expert data extraction assistant. Your task is to analyze the text from a university course syllabus and extract the course's marking scheme.

You MUST follow these rules:
1.  Identify the course code, course name, and the detailed marking scheme.
2.  The output MUST be a single, valid JSON object. Do not include any text, explanations, or code formatting before or after the JSON object.
3.  If a component is broken down into sub-components (e.g., an Essay worth 30% has an Outline for 5% and a Final Essay for 25%), represent this using a nested `sub_components` array.
4.  If you cannot find a marking scheme in the provided text, you MUST return a JSON object with a single key: {{"error": "Marking scheme not found in text"}}.

Here is the exact JSON schema to use:
{{
  "course_code": "string | null",
  "course_name": "string | null",
  "source_file": "string",
  "marking_scheme": [
    {{
      "component_name": "string",
      "weight_percentage": "number",
      "details": "string | null",
      "sub_components": [
        {{
          "component_name": "string",
          "weight_percentage": "number",
          "details": "string | null"
        }}
      ]
    }}
  ]
}}

Now, analyze the following syllabus text and provide the JSON output.

Syllabus Text:
---
{syllabus_text}
---
"""

def extract_text_from_file(file_path: Path) -> str | None:
    """
    Extracts all text from a given file, supporting .pdf and .docx formats.
    """
    extension = file_path.suffix.lower()
    
    if extension == '.pdf':
        try:
            with fitz.open(file_path) as doc:
                text = "".join(page.get_text() for page in doc)
            print(f"  ✓ Extracted text from PDF: {file_path.name}")
            return text
        except Exception as e:
            print(f"  ✗ Error reading PDF {file_path.name}: {e}")
            return None
            
    elif extension == '.docx':
        try:
            doc = Document(file_path)
            full_text = [para.text for para in doc.paragraphs]
            text = "\n".join(full_text)
            print(f"  ✓ Extracted text from DOCX: {file_path.name}")
            return text
        except Exception as e:
            print(f"  ✗ Error reading DOCX {file_path.name}: {e}")
            return None
            
    else:
        print(f"  - Skipping unsupported file type: {file_path.name}")
        return None

def query_ollama(syllabus_text: str, filename: str) -> dict:
    """Sends the syllabus text to Ollama and returns the parsed JSON response."""
    print(f"  > Querying Ollama for {filename}...")
    
    full_prompt = PROMPT_TEMPLATE.format(syllabus_text=syllabus_text)

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": full_prompt,
        "stream": False,
        "format": "json",
    }

    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=300)
        response.raise_for_status()

        response_content = response.json().get("response", "{}")
        extracted_data = json.loads(response_content)
        
        extracted_data['source_file'] = filename
        
        print(f"  ✓ Successfully extracted data for {filename}")
        return extracted_data
        
    except requests.exceptions.RequestException as e:
        print(f"  ✗ Network error querying Ollama: {e}")
        return {"error": f"Network error: {e}", "source_file": filename}
    except json.JSONDecodeError:
        print(f"  ✗ Failed to decode JSON from Ollama's response for {filename}.")
        return {"error": "Invalid JSON received from Ollama", "source_file": filename}
    except Exception as e:
        print(f"  ✗ An unexpected error occurred for {filename}: {e}")
        return {"error": f"An unexpected error occurred: {e}", "source_file": filename}

def main():
    """Main function to orchestrate the syllabus extraction process."""
    syllabus_dir = Path(SYLLABUS_DIRECTORY)
    if not syllabus_dir.is_dir():
        print(f"Error: Directory '{SYLLABUS_DIRECTORY}' not found.")
        print("Please create it and place your syllabus files inside.")
        sys.exit(1)

    # Find both .pdf and .docx files
    pdf_files = list(syllabus_dir.glob("*.pdf"))
    docx_files = list(syllabus_dir.glob("*.docx"))
    all_files = sorted(pdf_files + docx_files) # Sort for consistent processing order

    if not all_files:
        print(f"No PDF or DOCX files found in '{SYLLABUS_DIRECTORY}'.")
        sys.exit(0)
        
    print(f"Found {len(all_files)} syllabus files to process in '{SYLLABUS_DIRECTORY}'.\n")

    all_results = []
    for file_path in all_files:
        print(f"--- Processing: {file_path.name} ---")
        text = extract_text_from_file(file_path) # Use the new generalized function
        if text:
            result = query_ollama(text, file_path.name)
            all_results.append(result)
        else:
            all_results.append({
                "error": f"Could not read text from file ({file_path.suffix})",
                "source_file": file_path.name
            })
        print("-" * (len(file_path.name) + 20) + "\n")

    # Save all results to a single file
    with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\n✅ All processing complete. Results saved to '{OUTPUT_FILENAME}'.")


if __name__ == "__main__":
    main()
