"""Scrapes project information for current and past Jackman Scholars-in-Residence projects."""
import requests
from bs4 import BeautifulSoup
import json
import re
import os

def extract_supervisors(supervisor_text):
    """Extract supervisor names from text and return as a list of objects with name and empty url."""
    if not supervisor_text:
        return []
    
    # Remove "Supervisor:" or "Supervisors:" prefix
    supervisor_text = re.sub(r'^(Supervisor|Supervisors):\s*', '', supervisor_text.strip())
    
    # First, remove all parenthetical content
    cleaned_text = re.sub(r'\s*\([^)]*\)', '', supervisor_text)
    
    # Split by both commas and "and"
    # First replace " and " with comma for uniform splitting
    cleaned_text = cleaned_text.replace(" and ", ", ")
    
    # Now split by commas
    supervisors_names = [s.strip() for s in cleaned_text.split(",")]
    
    # Filter out any empty strings
    supervisors_names = [s for s in supervisors_names if s]
    
    # Convert to list of objects
    supervisors = []
    for name in supervisors_names:
        # Include both name and empty url for each supervisor
        supervisor = {
            "name": name,
            "url": ""
        }
        supervisors.append(supervisor)
    
    return supervisors

def scrape_sir_projects(url):
    """Scrape Scholars-in-Residence projects from the given URL."""
    try:
        # For local testing with the HTML file
        if os.path.exists(url):
            with open(url, 'r', encoding='utf-8') as f:
                html_content = f.read()
        else:
            # For actual web scraping
            response = requests.get(url)
            html_content = response.text
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find all accordion elements (years)
        accordions = soup.select('details.accordion')
        
        all_projects = []
        
        for accordion in accordions:
            # Extract year from summary
            year_element = accordion.find('summary')
            if year_element:
                year = year_element.text.strip()
            else:
                continue
            
            # Find all project content within this year's accordion
            content = accordion.select_one('.accordion-content')
            if not content:
                continue
            
            # Find all h3 elements (project titles)
            projects_h3 = content.find_all('h3')
            
            for h3 in projects_h3:
                project = {
                    "year": year,
                    "code": None,
                    "title": None,
                    "supervisors": [],
                    "description": ""
                }
                
                # Extract project title and code if present
                title_text = h3.text.strip()
                code_match = re.match(r'^([A-Z]+\d+)[\s—–-]+(.+)$', title_text)
                
                if code_match:
                    project["code"] = code_match.group(1)
                    project["title"] = code_match.group(2).strip()
                else:
                    project["title"] = title_text
                
                # Find supervisor info - typically in a p tag following the h3
                supervisor_elem = h3.find_next('p')
                if supervisor_elem and ('Supervisor' in supervisor_elem.text or 'supervisor' in supervisor_elem.text.lower()):
                    project["supervisors"] = extract_supervisors(supervisor_elem.text)
                
                # Extract description - all p tags until the next h3 or end of section
                description_elements = []
                current_elem = supervisor_elem
                
                while current_elem and current_elem.find_next_sibling() and current_elem.find_next_sibling().name != 'h3':
                    current_elem = current_elem.find_next_sibling()
                    if current_elem and current_elem.name in ['p', 'ul']:
                        description_elements.append(current_elem.get_text().strip())
                
                project["description"] = " ".join(description_elements)
                
                all_projects.append(project)
        
        return all_projects
    
    except Exception as e:
        print(f"Error scraping data: {e}")
        return []

def save_to_json(projects, output_file):
    """Save projects data to a JSON file."""
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(projects, f, ensure_ascii=False, indent=2)
        print(f"Data successfully saved to {output_file}")
    except Exception as e:
        print(f"Error saving data: {e}")

if __name__ == "__main__":
    url = "https://www.vic.utoronto.ca/academic-programs/scholars-in-residence/sir-past-projects"
    output_file = "sir_projects.json"
    
    # For local testing, use the saved HTML file path
    # url = "d:/Programming/OLD/OLD/SIR_Archive.html"
    
    projects = scrape_sir_projects(url)
    
    if projects:
        save_to_json(projects, output_file)
        print(f"Successfully scraped {len(projects)} projects.")
    else:
        print("No projects found or an error occurred.")
