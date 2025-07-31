"""
University of Toronto Awards Explorer HTML Parser

This script parses the HTML file from the UofT Awards Explorer and converts
award information into a structured JSON format.

The parser extracts the following fields for each award:
- Award Name
- Description
- Offered By
- Type
- Citizenship
- Application Required (as boolean)
- Nature of Award
- Application Deadline
- Estimated Value

Author: Parser for UofT-Scrapers project
Date: July 19, 2025
"""

import json
import re
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
import html


def clean_text(text: str) -> str:
    """
    Clean and normalize text content.
    
    Args:
        text: Raw text to clean
        
    Returns:
        Cleaned text string
    """
    if not text:
        return ""
    
    # Decode HTML entities
    text = html.unescape(text)
    
    # Remove extra whitespace and normalize
    text = ' '.join(text.split())
    
    # Remove HTML tags if any remain
    text = re.sub(r'<[^>]+>', '', text)
    
    return text.strip()


def extract_links(cell) -> List[str]:
    """
    Extract all links from a table cell.
    
    Args:
        cell: BeautifulSoup cell element
        
    Returns:
        List of URLs found in the cell
    """
    links = []
    if cell:
        for link in cell.find_all('a', href=True):
            href = link['href']
            if href.startswith('http'):
                links.append(href)
    return links


def parse_application_required(cell) -> bool:
    """
    Parse the Application Required field and return boolean.
    
    Args:
        cell: BeautifulSoup cell element containing application info
        
    Returns:
        True if application is required, False otherwise
    """
    if not cell:
        return False
    
    text = clean_text(cell.get_text())
    
    # Check for explicit "Yes" or "No"
    if 'Yes' in text or 'apply' in text.lower():
        return True
    elif 'No' in text:
        return False
    
    # Check for application links
    links = extract_links(cell)
    if links:
        return True
    
    return False


def parse_citizenship(text: str) -> List[str]:
    """
    Parse citizenship requirements into a list.
    
    Args:
        text: Raw citizenship text
        
    Returns:
        List of citizenship requirements
    """
    if not text:
        return []
    
    text = clean_text(text)
    if not text:
        return []
    
    # Split on semicolon and clean each part
    citizenships = [c.strip() for c in text.split(';') if c.strip()]
    return citizenships


def parse_nature_of_award(text: str) -> List[str]:
    """
    Parse nature of award into a list of categories.
    
    Args:
        text: Raw nature of award text
        
    Returns:
        List of award nature categories
    """
    if not text:
        return []
    
    text = clean_text(text)
    if not text:
        return []
    
    # Split on comma and clean each part
    natures = [n.strip() for n in text.split(',') if n.strip()]
    return natures


def extract_deadline(text: str) -> Optional[str]:
    """
    Extract application deadline from text.
    
    Args:
        text: Raw deadline text
        
    Returns:
        Formatted deadline string or None
    """
    text = clean_text(text)
    if not text:
        return None
    
    # Look for date patterns (YYYY-MM-DD HH:MM format)
    date_pattern = r'\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2})?'
    match = re.search(date_pattern, text)
    if match:
        return match.group()
    
    return text if text else None


def parse_awards_html(html_file_path: str) -> List[Dict[str, Any]]:
    """
    Parse the UofT Awards Explorer HTML file and extract award information.
    
    Args:
        html_file_path: Path to the HTML file
        
    Returns:
        List of dictionaries containing award information
    """
    awards = []
    
    try:
        with open(html_file_path, 'r', encoding='utf-8') as file:
            content = file.read()
    except UnicodeDecodeError:
        # Try with different encoding if UTF-8 fails
        with open(html_file_path, 'r', encoding='latin-1') as file:
            content = file.read()
    
    print("Parsing awards from HTML...")
    
    # Try to parse the structure differently
    # Look for complete row patterns more flexibly
    # Note: HTML uses &quot; for quotes
    
    # Try a pattern that catches rows at the end properly
    end_pattern = r'<tr><td class=&quot;Data[12] AlignLeft&quot; style=font-weight:800>([^<]+)</td>(.*?)(?=<tr>|</tbody>|</table>|$)'
    row_matches = re.findall(end_pattern, content, re.DOTALL)
    print(f"Found {len(row_matches)} award rows to process")
    
    # Process each row
    for award_name, row_content in row_matches:
        # Extract all td elements from this row
        td_pattern = r'<td class=&quot;Data[12] AlignLeft&quot;[^>]*>(.*?)</td>'
        cells = re.findall(td_pattern, row_content, re.DOTALL)
        
        if len(cells) >= 8:  # Should have at least 8 more cells after the name
            try:
                # Clean the extracted content
                award_name = clean_text(award_name)
                description = clean_text(cells[0])
                offered_by = clean_text(cells[1]) if len(cells) > 1 else ""
                award_type = clean_text(cells[2]) if len(cells) > 2 else ""
                citizenship_raw = clean_text(cells[3]) if len(cells) > 3 else ""
                application_cell = cells[4] if len(cells) > 4 else ""
                nature_raw = clean_text(cells[5]) if len(cells) > 5 else ""
                deadline_raw = clean_text(cells[6]) if len(cells) > 6 else ""
                estimated_value = clean_text(cells[7]) if len(cells) > 7 else ""
                
                # Extract links from description
                description_links = re.findall(r'href=([^>\s]+)', cells[0])
                description_links = [link.strip('"\'') for link in description_links if link.startswith('http')]
                
                # Parse application required
                app_required = 'Yes' in application_cell or 'apply' in application_cell.lower()
                
                # Parse citizenship and nature
                citizenship = parse_citizenship(citizenship_raw)
                nature_of_award = parse_nature_of_award(nature_raw)
                deadline = extract_deadline(deadline_raw)
                
                award_data = {
                    "award_name": award_name,
                    "description": description,
                    "description_links": description_links,
                    "offered_by": offered_by,
                    "type": award_type,
                    "citizenship": citizenship,
                    "application_required": app_required,
                    "nature_of_award": nature_of_award,
                    "application_deadline": deadline,
                    "estimated_value": estimated_value
                }
                
                awards.append(award_data)
                
            except Exception as e:
                print(f"Error processing award row: {e}")
    
    return awards


def save_to_json(awards: List[Dict[str, Any]], output_file: str) -> None:
    """
    Save awards data to a JSON file.
    
    Args:
        awards: List of award dictionaries
        output_file: Path to output JSON file
    """
    output_data = {
        "metadata": {
            "total_awards": len(awards),
            "source": "University of Toronto Awards Explorer",
            "extracted_date": "2025-07-19",
            "fields": [
                "award_name",
                "description", 
                "description_links",
                "offered_by",
                "type",
                "citizenship",
                "application_required",
                "nature_of_award", 
                "application_deadline",
                "estimated_value"
            ]
        },
        "awards": awards
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)


def main():
    """Main function to run the parser."""
    html_file = "Graduate.html"
    output_file = "uoft_awards_2025.json"
    
    print(f"Parsing UofT Awards from {html_file}...")
    
    try:
        awards = parse_awards_html(html_file)
        print(f"Successfully extracted {len(awards)} awards")
        
        save_to_json(awards, output_file)
        print(f"Awards data saved to {output_file}")
        
        # Print some statistics
        print("\n--- Statistics ---")
        print(f"Total awards: {len(awards)}")
        
        # Count application required
        app_required = sum(1 for award in awards if award['application_required'])
        print(f"Awards requiring application: {app_required}")
        print(f"Awards automatically considered: {len(awards) - app_required}")
        
        # Count by type
        types = {}
        for award in awards:
            award_type = award.get('type', 'Unknown')
            types[award_type] = types.get(award_type, 0) + 1
        
        print(f"\nAwards by type:")
        for award_type, count in sorted(types.items()):
            print(f"  {award_type}: {count}")
        
        # Show sample award
        if awards:
            print(f"\n--- Sample Award ---")
            sample = awards[0]
            print(f"Name: {sample['award_name']}")
            print(f"Offered by: {sample['offered_by']}")
            print(f"Type: {sample['type']}")
            print(f"Application required: {sample['application_required']}")
            print(f"Estimated value: {sample['estimated_value']}")
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
