#!/usr/bin/env python3
"""
TA Postings Parser

This script parses University of Toronto TA posting HTML files and extracts
job information into a structured JSON format. It excludes policy information
and focuses on the actual job details.

Usage:
    python parser.py [input_directory] [output_file]

If no arguments provided, it will process all HTML files in the current directory
and output to 'ta_postings.json'.
"""

import os
import sys
import json
import html
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
try:
    from tqdm import tqdm  # type: ignore
except ImportError:
    # Fallback tqdm if not installed: iterate without progress bar
    def tqdm(iterable, **kwargs):
        return iterable
    tqdm.write = lambda msg: print(msg, file=sys.stderr)
from typing import Dict, List, Optional, Any


class TAPostingParser:
    """Parser for University of Toronto TA job postings."""
    
    def __init__(self):
        self.parsed_postings = []
        self.errors = []
    
    def parse_html_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Parse a single HTML file and extract TA posting information.
        
        Args:
            file_path: Path to the HTML file to parse
            
        Returns:
            Dictionary containing parsed job posting data, or None if parsing fails
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse HTML
            soup = BeautifulSoup(content, 'html.parser')
            app_div = soup.find('div', {'id': 'app'})
            
            if not app_div:
                raise ValueError("No app div found in HTML")
            
            data_page = app_div.get('data-page')
            if not data_page:
                raise ValueError("No data-page attribute found")
            
            # Unescape HTML entities and parse JSON
            unescaped_data = html.unescape(data_page)
            data = json.loads(unescaped_data)
            
            # Extract the item data
            item = data.get('props', {}).get('item', {})
            if not item:
                raise ValueError("No item data found in JSON")
            
            # Parse and structure the data
            posting = self._extract_posting_data(item, file_path)
            return posting
            
        except Exception as e:
            error_msg = f"Error parsing {file_path}: {str(e)}"
            self.errors.append(error_msg)
            tqdm.write(f"ERROR: {error_msg}")
            return None
    
    def _extract_posting_data(self, item: Dict[str, Any], file_path: str) -> Dict[str, Any]:
        """
        Extract and structure posting data from the raw item data.
        
        Args:
            item: Raw item data from the HTML
            file_path: Path to the source file
            
        Returns:
            Structured posting data
        """
        posting = {
            # Basic Job Information
            "id": item.get("id"),
            "course_id": item.get("course_id"),
            "course_title": item.get("job_title"),
            "course_enrolment": self._safe_int(item.get("course_enrolment")),
            "positions": self._safe_int(item.get("positions")),
            "emergency": bool(item.get("emergency", 0)),
            
            # Appointment Details
            "appointment_date": item.get("appointment_date"),
            "appointment_startdate": self._parse_date(item.get("appointment_startdate")),
            "appointment_enddate": self._parse_date(item.get("appointment_enddate")),
            "appointment_duration": self._safe_float(item.get("appointment_duration")),
            "appointment_size": item.get("appointment_size"),
            
            # Job Content
            "duties": self._clean_text(item.get("duties")),
            "qualifications": self._clean_text(item.get("qualifications")),
            "qualifications_minimum": self._clean_text(item.get("qualifications_minimum")),
            "qualifications_preferred": self._clean_text(item.get("qualifications_preferred")),
            "tutorial": self._clean_text(item.get("tutorial")),
            "experience": self._clean_text(item.get("experience")),
            "ta_support": item.get("ta_support"),
            
            # Compensation
            "salary": self._clean_text(item.get("salery")),  # Note: typo in original field name
            
            # Application Process
            "application_procedure": item.get("application_procedure"),
            "posting_date": self._parse_date(item.get("posting_date")),
            "closing_date": self._parse_date(item.get("closing_date")),
            "expiry_date": self._parse_date(item.get("expiry_date")),
            
            # Organizational Information (job-relevant only)
            "department_name": (item.get("department") or {}).get("name"),
            "campus_name": (item.get("campus") or {}).get("name"),
            "position_type": (item.get("position_type") or {}).get("name"),
        }
        
        # Remove None values to keep JSON clean
        posting = {k: v for k, v in posting.items() if v is not None}
        
        return posting
    
    def _safe_int(self, value: Any) -> Optional[int]:
        """Safely convert value to integer."""
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float."""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def _clean_text(self, text: Optional[str]) -> Optional[str]:
        """Clean and normalize text fields."""
        if not text or text.strip() == "":
            return None
        
        # Remove excessive whitespace and normalize
        cleaned = " ".join(text.split())
        return cleaned if cleaned else None
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[str]:
        """Parse and normalize date strings."""
        if not date_str:
            return None
        
        # Return as-is for now, could add more sophisticated parsing later
        return date_str
    
    def parse_directory(self, directory: str = ".") -> List[Dict[str, Any]]:
        """
        Parse all HTML files in a directory.
        
        Args:
            directory: Directory to search for HTML files
            
        Returns:
            List of parsed posting dictionaries
        """
        directory_path = Path(directory)
        html_files = list(directory_path.glob("posting_*.html"))
        
        if not html_files:
            print(f"No posting_*.html files found in {directory}")
            return []
        
        print(f"Found {len(html_files)} HTML files to parse")
        # Use a progress bar to show parsing progress, only errors will be logged
        for file_path in tqdm(html_files, desc="Parsing HTML files", unit="file"):
            posting = self.parse_html_file(str(file_path))
            if posting:
                self.parsed_postings.append(posting)
        
        print(f"Successfully parsed {len(self.parsed_postings)} postings")
        if self.errors:
            print(f"Encountered {len(self.errors)} errors")
        
        return self.parsed_postings
    
    def save_to_json(self, output_file: str = "ta_postings.json") -> None:
        """
        Save parsed postings to a JSON file.
        
        Args:
            output_file: Path to output JSON file
        """
        if not self.parsed_postings:
            print("No postings to save")
            return
        
        output_data = {
            "postings": self.parsed_postings,
            "metadata": {
                "total_postings": len(self.parsed_postings),
                "total_errors": len(self.errors),
                "parsed_at": datetime.now().isoformat(),
                "errors": self.errors if self.errors else None
            }
        }
        
        # Remove None values from metadata
        output_data["metadata"] = {k: v for k, v in output_data["metadata"].items() if v is not None}
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"Saved {len(self.parsed_postings)} postings to {output_file}")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of parsed postings."""
        if not self.parsed_postings:
            return {"total_postings": 0, "summary": "No postings parsed"}
        
        # Basic statistics
        total_postings = len(self.parsed_postings)
        departments = set()
        campuses = set()
        position_types = set()
        courses = set()
        
        for posting in self.parsed_postings:
            if posting.get("department_name"):
                departments.add(posting["department_name"])
            if posting.get("campus_name"):
                campuses.add(posting["campus_name"])
            if posting.get("position_type"):
                position_types.add(posting["position_type"])
            if posting.get("course_id"):
                courses.add(posting["course_id"])
        
        return {
            "total_postings": total_postings,
            "unique_departments": len(departments),
            "unique_campuses": len(campuses),
            "unique_position_types": len(position_types),
            "unique_courses": len(courses),
            "departments": sorted(list(departments)),
            "campuses": sorted(list(campuses)),
            "position_types": sorted(list(position_types)),
            "courses": sorted(list(courses)),
            "errors": len(self.errors)
        }


def main():
    """Main function to run the parser."""
    # Parse command line arguments
    input_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    output_file = sys.argv[2] if len(sys.argv) > 2 else "ta_postings.json"
    
    print(f"TA Postings Parser")
    print(f"Input directory: {input_dir}")
    print(f"Output file: {output_file}")
    print("-" * 50)
    
    # Create parser and process files
    parser = TAPostingParser()
    postings = parser.parse_directory(input_dir)
    
    if postings:
        parser.save_to_json(output_file)
        
        # Print summary
        summary = parser.get_summary()
        print("\n" + "=" * 50)
        print("SUMMARY")
        print("=" * 50)
        print(f"Total postings: {summary['total_postings']}")
        print(f"Unique departments: {summary['unique_departments']}")
        print(f"Unique campuses: {summary['unique_campuses']}")
        print(f"Unique position types: {summary['unique_position_types']}")
        print(f"Unique courses: {summary['unique_courses']}")
        
        if summary['errors'] > 0:
            print(f"Errors encountered: {summary['errors']}")
        
        print(f"\nCampuses: {', '.join(summary['campuses'])}")
        print(f"Position types: {', '.join(summary['position_types'])}")
        
        return True
    else:
        print("No postings were successfully parsed.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)