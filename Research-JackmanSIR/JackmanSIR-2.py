import json
import re
from bs4 import BeautifulSoup
import requests

def extract_sir_projects(url):
    """
    Extract SiR projects data from the Victoria College webpage
    and save to a structured JSON file
    """
    # Fetch the webpage content
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Failed to fetch page: {response.status_code}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')

    # Find all the accordion elements containing past projects
    accordions = soup.select('details.accordion')

    all_projects = {}

    for accordion in accordions:
        # Get the year from the summary element
        year = accordion.select_one('summary').text.strip()

        # Get the content of this year's projects
        content = accordion.select_one('.accordion-content')

        # Extract projects from the content
        projects = extract_projects_for_year(content, year)

        # Add to the overall dictionary
        all_projects[year] = projects

    # Save to JSON file
    with open('sir_projects.json', 'w', encoding='utf-8') as f:
        json.dump(all_projects, f, indent=4, ensure_ascii=False)

    print(f"Extracted projects for {len(all_projects)} years and saved to sir_projects.json")
    return all_projects

def extract_projects_for_year(content, year):
    """Extract project information from the HTML content for a specific year"""
    projects = []

    # Locate project sections - each project starts with an h3 (title)
    h3_elements = content.find_all('h3')

    for h3 in h3_elements:
        project = {'title': h3.text.strip()}

        # Initialize variables for project metadata
        supervisor = None
        location = None
        description = []

        # Process elements that follow until the next h3 or end of content
        current_element = h3.next_sibling

        while current_element and not (hasattr(current_element, 'name') and current_element.name == 'h3'):
            if hasattr(current_element, 'name') and current_element.name == 'p':
                text = current_element.text.strip()

                # Check if this is supervisor information
                if text.startswith('Supervisor:'):
                    project['supervisor'] = text.replace('Supervisor:', '').strip()

                # Check if this is location information
                elif text.startswith('Location:') or 'Campus' in text:
                    project['location'] = text.strip()

                # Otherwise, it's part of the description
                else:
                    description.append(text)

            # Move to the next element
            if current_element.next_sibling:
                current_element = current_element.next_sibling
            else:
                break

        # Join description paragraphs
        if description:
            project['description'] = '\n\n'.join(description)

        # Add to projects list if we have at least a title
        if project['title']:
            projects.append(project)

    # If there are no h3 elements, try a different approach
    if not projects:
        # Try looking for project information by paragraphs
        paragraphs = content.find_all('p')
        current_project = None

        for p in paragraphs:
            text = p.text.strip()

            # Skip empty paragraphs
            if not text:
                continue

            # Look for title-like text (check for bold or strong elements)
            bold_text = p.find('strong')

            if bold_text or (len(text) < 100 and not text.startswith('Supervisor:') and not text.startswith('Location:')):
                # This might be a title
                if current_project:
                    projects.append(current_project)

                current_project = {'title': text}
            elif text.startswith('Supervisor:'):
                if current_project:
                    current_project['supervisor'] = text.replace('Supervisor:', '').strip()
            elif 'Campus' in text:
                if current_project:
                    current_project['location'] = text.strip()
            else:
                if current_project:
                    if 'description' in current_project:
                        current_project['description'] += '\n\n' + text
                    else:
                        current_project['description'] = text

        # Add the last project
        if current_project:
            projects.append(current_project)

    # For years with special formatting, use specific handling
    if year == "2020":
        # 2020 projects have h3 for titles and various paragraphs for details
        projects = extract_2020_projects(content)

    return projects

def extract_2020_projects(content):
    """Special handler for 2020 projects which have a different structure"""
    projects = []

    # Get campus headings (h2 elements)
    campuses = content.find_all('h2')

    for campus in campuses:
        location = campus.text.strip()

        # Find all project titles (h3 elements) until the next h2
        current = campus.next_sibling
        while current:
            if hasattr(current, 'name') and current.name == 'h2':
                break

            if hasattr(current, 'name') and current.name == 'h3':
                project = {'title': current.text.strip(), 'location': location}

                # Extract supervisor and description
                description_parts = []
                supervisor_element = current.find_next('p')

                if supervisor_element and supervisor_element.text.strip().startswith('Supervisor:'):
                    project['supervisor'] = supervisor_element.text.replace('Supervisor:', '').strip()

                    # Find description paragraphs (all p elements until next h3/h2)
                    desc_element = supervisor_element.next_sibling
                    while desc_element:
                        if hasattr(desc_element, 'name'):
                            if desc_element.name in ['h2', 'h3']:
                                break
                            elif desc_element.name == 'p' and not desc_element.text.strip().startswith('Supervisor:'):
                                description_parts.append(desc_element.text.strip())

                        desc_element = desc_element.next_sibling

                if description_parts:
                    project['description'] = '\n\n'.join(description_parts)

                projects.append(project)

            current = current.next_sibling

    return projects

if __name__ == "__main__":
    url = "https://www.vic.utoronto.ca/academic-programs/scholars-in-residence/sir-past-projects"
    projects = extract_sir_projects(url)

    if projects:
        # Print summary
        for year, year_projects in projects.items():
            print(f"{year}: {len(year_projects)} projects")