#!/usr/bin/env python3
"""
Enhanced TTB Scraper with improved features:
- Can run without specifying a subject (scrapes all subjects)
- Opens course dropdowns to scrape detailed information
- Handles pagination to scrape multiple pages
- Extracts lecture, tutorial, and lab information
- Scrapes course notes and additional details
"""

import time
import csv
import os
import re
from typing import List, Optional, Dict, Any, Set
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    TimeoutException, 
    NoSuchElementException, 
    ElementClickInterceptedException,
    WebDriverException,
    StaleElementReferenceException
)
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd

from models import Course, ScrapingResult
from logger_utils import setup_logger, log_scraping_session, log_error
from config import *

class CourseDetail:
    """Extended course information including detailed session data."""
    
    def __init__(self):
        self.course_code = ""
        self.course_title = ""
        self.description = ""
        self.prerequisites = ""
        self.notes = ""
        self.sections = []  # List of section details
        self.lectures = []  # List of lecture sessions
        self.tutorials = []  # List of tutorial sessions
        self.labs = []  # List of lab sessions
        self.credit_value = ""
        self.campus = ""
        self.breadth_categories = []
        
    def to_dict(self) -> dict:
        """Convert to dictionary for CSV export."""
        return {
            'Course Code': self.course_code,
            'Course Title': self.course_title,
            'Description': self.description,
            'Prerequisites': self.prerequisites,
            'Notes': self.notes,
            'Credit Value': self.credit_value,
            'Campus': self.campus,
            'Breadth Categories': ', '.join(self.breadth_categories),
            'Lectures': '; '.join([f"{lec['section']}: {lec['instructor']} - {lec['time']} @ {lec['location']}" for lec in self.lectures]),
            'Tutorials': '; '.join([f"{tut['section']}: {tut['instructor']} - {tut['time']} @ {tut['location']}" for tut in self.tutorials]),
            'Labs': '; '.join([f"{lab['section']}: {lab['instructor']} - {lab['time']} @ {lab['location']}" for lab in self.labs]),
            'Total Sections': len(self.sections)
        }

class TTBScraperEnhanced:
    """Enhanced web scraper for University of Toronto Timetable with detailed course information extraction."""
    
    def __init__(self, headless: bool = False):
        """Initialize the scraper with Chrome WebDriver."""
        self.logger = setup_logger()
        self.headless = headless
        self.driver = None
        self.wait = None
        self.scraped_courses = set()  # Track scraped courses to avoid duplicates
        self.current_page = 1
        self.max_pages = 10  # Safety limit for pagination
        self.config = type('Config', (), {
            'page_load_timeout': 20,
            'webdriver_timeout': 15,
            'request_delay': 2,
            'course_detail_delay': 3
        })()
        self.setup_driver()
    
    def setup_driver(self):
        """Set up Chrome WebDriver with appropriate options."""
        try:
            chrome_options = Options()
            
            if self.headless:
                chrome_options.add_argument("--headless")
            
            # Additional Chrome options for stability
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Use WebDriver Manager to automatically handle ChromeDriver
            service = Service(ChromeDriverManager().install())
            
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.driver.implicitly_wait(5)
            self.driver.set_page_load_timeout(self.config.page_load_timeout)
            
            self.wait = WebDriverWait(self.driver, self.config.webdriver_timeout)
            self.logger.info("Chrome WebDriver initialized successfully")
            
        except Exception as e:
            log_error(self.logger, e, "setting up WebDriver")
            raise
    
    def navigate_to_timetable(self) -> bool:
        """Navigate to the TTB main page and wait for Angular to load."""
        try:
            self.logger.info("Navigating to TTB website...")
            self.driver.get("https://ttb.utoronto.ca/")
            
            # Wait for Angular to load
            wait = WebDriverWait(self.driver, self.config.page_load_timeout)
            
            # Wait for the main Angular app to be present
            try:
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "app-root")))
                self.logger.info("Angular app loaded successfully")
            except TimeoutException:
                self.logger.warning("Could not find Angular app-root, continuing...")
            
            # Additional wait for dynamic content to load
            time.sleep(5)
            
            # Check that we can find the key elements we need
            try:
                wait.until(EC.presence_of_element_located((By.ID, "division-combo-top-container")))
                self.logger.info("Faculty/Division dropdown found")
            except TimeoutException:
                self.logger.warning("Faculty/Division dropdown not found immediately")
            
            try:
                wait.until(EC.presence_of_element_located((By.ID, "session-combo-top-container")))
                self.logger.info("Session dropdown found")
            except TimeoutException:
                self.logger.warning("Session dropdown not found immediately")
            
            self.logger.info("Successfully navigated to timetable page")
            return True
            
        except Exception as e:
            log_error(self.logger, e, "navigating to timetable")
            return False
    
    def select_division(self, division_name: str = "Faculty of Arts and Science") -> bool:
        """Select the Faculty/Division dropdown."""
        try:
            self.logger.info(f"Selecting division: {division_name}")
            
            # Find and click the Faculty/Division dropdown
            division_dropdown = self.wait.until(
                EC.element_to_be_clickable((By.ID, "division-combo-top-container"))
            )
            division_dropdown.click()
            self.logger.info("Clicked Faculty/Division dropdown")
            
            # Wait for options to appear
            time.sleep(2)
            
            # Look for options
            division_options = self.driver.find_elements(By.CSS_SELECTOR, "#division-combo-bottom-container .ttb-option")
            self.logger.info(f"Found {len(division_options)} division options")
            
            # Click on the specified division option
            for option in division_options:
                option_text = option.get_attribute('aria-label') or option.text
                if division_name in option_text:
                    option.click()
                    self.logger.info(f"Selected division: {division_name}")
                    time.sleep(self.config.request_delay)
                    return True
            
            # If not found, select the first available option
            if division_options:
                division_options[0].click()
                option_text = division_options[0].get_attribute('aria-label') or division_options[0].text
                self.logger.info(f"Selected first available division: {option_text}")
                time.sleep(self.config.request_delay)
                return True
            
            self.logger.error("No division options found")
            return False
            
        except Exception as e:
            log_error(self.logger, e, f"selecting division {division_name}")
            return False
    
    def get_available_sessions(self) -> List[Dict[str, str]]:
        """Get list of available sessions."""
        sessions = []
        try:
            # Check currently selected sessions
            session_pills = self.driver.find_elements(By.CSS_SELECTOR, "#session .ttb-pill")
            self.logger.info(f"Found {len(session_pills)} currently selected sessions")
            
            for pill in session_pills:
                text = pill.find_element(By.TAG_NAME, "span").text
                sessions.append({"name": text, "selected": True})
            
            # Try to open session dropdown to see all options
            try:
                session_dropdown = self.driver.find_element(By.ID, "session-combo-top-container")
                session_dropdown.click()
                time.sleep(2)
                
                # Look for session options
                session_options = self.driver.find_elements(By.CSS_SELECTOR, "#session-combo-bottom-container .ttb-option")
                self.logger.info(f"Found {len(session_options)} total session options")
                
                for option in session_options:
                    option_text = option.get_attribute('aria-label') or option.text
                    if option_text and not any(s["name"] == option_text for s in sessions):
                        sessions.append({"name": option_text, "selected": False})
                
                # Close dropdown by clicking elsewhere
                self.driver.find_element(By.TAG_NAME, "body").click()
                
            except Exception as e:
                self.logger.debug(f"Could not access session dropdown: {e}")
            
        except Exception as e:
            log_error(self.logger, e, "getting available sessions")
        
        return sessions
    
    def ensure_sessions_selected(self) -> bool:
        """Ensure that sessions are selected (Summer 2025 sessions are pre-selected)."""
        try:
            session_pills = self.driver.find_elements(By.CSS_SELECTOR, "#session .ttb-pill")
            if len(session_pills) > 0:
                self.logger.info(f"Sessions already selected: {len(session_pills)} sessions")
                return True
            
            # If no sessions selected, try to select default ones
            self.logger.info("No sessions selected, attempting to select default sessions")
            
            session_dropdown = self.driver.find_element(By.ID, "session-combo-top-container")
            session_dropdown.click()
            time.sleep(2)
            
            # Select first available session
            session_options = self.driver.find_elements(By.CSS_SELECTOR, "#session-combo-bottom-container .ttb-option")
            if session_options:
                session_options[0].click()
                self.logger.info("Selected first available session")
                time.sleep(1)
                
                # Close dropdown
                self.driver.find_element(By.TAG_NAME, "body").click()
                return True
            
            return False
            
        except Exception as e:
            log_error(self.logger, e, "ensuring sessions selected")
            return False
    
    def perform_search(self) -> bool:
        """Perform the search after division and sessions are selected."""
        try:
            self.logger.info("Performing search...")
            
            # Find search button
            search_button = None
            search_buttons = self.driver.find_elements(By.CSS_SELECTOR, ".btn.btn-primary")
            
            for btn in search_buttons:
                if "Search" in btn.text:
                    search_button = btn
                    break
            
            if not search_button:
                self.logger.error("Could not find Search button")
                return False
            
            if not search_button.is_enabled():
                self.logger.error("Search button is not enabled")
                return False
            
            search_button.click()
            self.logger.info("Clicked Search button")
            
            # Wait for results or next step
            time.sleep(8)  # Increased wait time for page transition
            
            # Check if we're now on a results page or step 2
            current_url = self.driver.current_url
            page_text = self.driver.page_source
            
            self.logger.info(f"After search - URL: {current_url}")
            
            if "course" in page_text.lower() or "result" in page_text.lower():
                self.logger.info("Search successful! Found course results")
                return True
            else:
                self.logger.warning("Search completed but unclear if successful")
                return True  # Continue anyway
                
        except Exception as e:
            log_error(self.logger, e, "performing search")
            return False
    
    def get_all_course_links(self) -> List[str]:
        """Get all course links/identifiers from the current page."""
        course_links = []
        try:
            # Try different selectors for course links or expandable elements
            course_selectors = [
                "a[href*='course']",
                "[data-course-code]",
                ".course-title",
                ".course-link",
                "[class*='course'] a",
                "button[aria-expanded]",  # Expandable course buttons
                ".expandable-course",
                "[data-testid*='course']"
            ]
            
            for selector in course_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        self.logger.info(f"Found {len(elements)} course elements with selector: {selector}")
                        for element in elements:
                            try:
                                link = element.get_attribute('href') or element.get_attribute('data-course-code')
                                if link and link not in course_links:
                                    course_links.append(link)
                            except:
                                continue
                        if course_links:
                            break
                except:
                    continue
            
            self.logger.info(f"Found {len(course_links)} unique course links")
            return course_links
            
        except Exception as e:
            log_error(self.logger, e, "getting course links")
            return []
    def extract_course_details(self, course_element) -> Optional[CourseDetail]:
        """Extract detailed course information by expanding course dropdown/accordion."""
        try:
            course_detail = CourseDetail()
            
            # Get the full text content first for fallback parsing
            element_text = course_element.text
            self.logger.debug(f"Processing course element with text: {element_text[:200]}...")
            
            # Try multiple strategies to expand course details
            expanded = False
            
            # Strategy 1: Look for expand buttons/toggles
            expand_selectors = [
                "button[aria-expanded='false']",
                "button[aria-expanded]",
                ".expand-btn",
                ".toggle-btn", 
                "[class*='expand']",
                "[class*='toggle']",
                "button[title*='expand']",
                "button[title*='show']",
                ".course-toggle",
                "[data-toggle]"
            ]
            
            for selector in expand_selectors:
                try:
                    expand_buttons = course_element.find_elements(By.CSS_SELECTOR, selector)
                    for button in expand_buttons:
                        if button.is_displayed() and button.is_enabled():
                            # Scroll to button and click
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", button)
                            time.sleep(1)
                            self.driver.execute_script("arguments[0].click();", button)
                            self.logger.info(f"Clicked expand button using selector: {selector}")
                            time.sleep(self.config.course_detail_delay)
                            expanded = True
                            break
                    if expanded:
                        break
                except Exception as e:
                    self.logger.debug(f"Failed to expand with selector {selector}: {e}")
                    continue
            
            # Strategy 2: Try clicking on the course element itself (some have click handlers)
            if not expanded:
                try:
                    # Try clicking on course title or course code elements
                    clickable_selectors = [
                        ".course-title",
                        ".course-code", 
                        "h3",
                        "h4",
                        ".course-header"
                    ]
                    
                    for selector in clickable_selectors:
                        try:
                            clickable_elem = course_element.find_element(By.CSS_SELECTOR, selector)
                            if clickable_elem.is_displayed():
                                self.driver.execute_script("arguments[0].click();", clickable_elem)
                                self.logger.info(f"Clicked course element using selector: {selector}")
                                time.sleep(self.config.course_detail_delay)
                                expanded = True
                                break
                        except:
                            continue
                    
                    # If still not expanded, try clicking the main element
                    if not expanded:
                        self.driver.execute_script("arguments[0].click();", course_element)
                        self.logger.info("Clicked main course element")
                        time.sleep(self.config.course_detail_delay)
                        expanded = True
                        
                except Exception as e:
                    self.logger.debug(f"Failed to click course element: {e}")
            
            # After expanding, get the updated text content
            if expanded:
                time.sleep(2)  # Give time for content to load
                element_text = course_element.text
                self.logger.debug(f"After expansion, element text: {element_text[:300]}...")
              
            # Extract course code and title with improved methods
            try:
                # Method 1: Look for specific CSS selectors
                code_selectors = [
                    ".course-code",
                    "[class*='course-code']", 
                    ".code",
                    "[data-course-code]",
                    "h3",
                    "h4",
                    ".course-header",
                    ".title"
                ]
                
                for selector in code_selectors:
                    try:
                        code_element = course_element.find_element(By.CSS_SELECTOR, selector)
                        code_text = code_element.text.strip()
                        # Look for course code pattern in the text
                        code_match = re.search(r'([A-Z]{3}[A-Z0-9]{3}[HY][01])', code_text)
                        if code_match:
                            course_detail.course_code = code_match.group(1)
                            self.logger.debug(f"Found course code via selector {selector}: {course_detail.course_code}")
                            break
                    except:
                        continue
                
                # Method 2: Extract from text content using regex
                if not course_detail.course_code:
                    code_match = re.search(r'([A-Z]{3}[A-Z0-9]{3}[HY][01])', element_text)
                    if code_match:
                        course_detail.course_code = code_match.group(1)
                        self.logger.debug(f"Found course code via regex: {course_detail.course_code}")
                
            except Exception as e:
                self.logger.debug(f"Error extracting course code: {e}")
            
            # Extract course title
            try:
                # Method 1: Look for title-specific selectors
                title_selectors = [
                    ".course-title",
                    "[class*='course-title']",
                    ".title",
                    "[class*='title']",
                    "h3",
                    "h4"
                ]
                
                for selector in title_selectors:
                    try:
                        title_element = course_element.find_element(By.CSS_SELECTOR, selector)
                        title_text = title_element.text.strip()
                        # Skip if it's just the course code
                        if title_text and not re.match(r'^[A-Z]{3}[A-Z0-9]{3}[HY][01]$', title_text):
                            course_detail.course_title = title_text
                            self.logger.debug(f"Found course title via selector {selector}: {course_detail.course_title[:50]}...")
                            break
                    except:
                        continue
                
                # Method 2: Extract title from text content after course code
                if not course_detail.course_title and course_detail.course_code:
                    # Look for text after course code
                    parts = element_text.split(course_detail.course_code, 1)
                    if len(parts) > 1:
                        title_candidates = parts[1].strip().split('\n')
                        for candidate in title_candidates:
                            candidate = candidate.strip()
                            if len(candidate) > 10 and not re.match(r'^[A-Z]{3}[0-9]+$', candidate):
                                course_detail.course_title = candidate
                                self.logger.debug(f"Found course title via text parsing: {course_detail.course_title[:50]}...")
                                break
                
                # Method 3: Try to find any meaningful title in the element
                if not course_detail.course_title:
                    lines = element_text.split('\n')
                    for line in lines:
                        line = line.strip()
                        if (len(line) > 15 and 
                            not re.match(r'^[A-Z]{3}[A-Z0-9]{3}[HY][01]$', line) and
                            not re.match(r'^(LEC|TUT|LAB|PRA)\d+', line) and
                            'Notes:' not in line and
                            'Delivery' not in line):
                            course_detail.course_title = line
                            self.logger.debug(f"Found course title via line parsing: {course_detail.course_title[:50]}...")
                            break
                            
            except Exception as e:
                self.logger.debug(f"Error extracting course title: {e}")
            
            # Extract description with better selectors
            try:
                desc_selectors = [
                    ".course-description",
                    ".description", 
                    "[class*='description']",
                    ".course-desc",
                    "[class*='desc']"
                ]
                
                for selector in desc_selectors:
                    try:
                        desc_element = course_element.find_element(By.CSS_SELECTOR, selector)
                        desc_text = desc_element.text.strip()
                        if desc_text and len(desc_text) > 20:
                            course_detail.description = desc_text
                            self.logger.debug(f"Found description via selector {selector}: {desc_text[:50]}...")
                            break
                    except:
                        continue
                        
            except Exception as e:
                self.logger.debug(f"Error extracting description: {e}")
            
            # Extract prerequisites with better selectors
            try:
                prereq_selectors = [
                    ".prerequisites",
                    "[class*='prerequisite']", 
                    ".prereq",
                    "[class*='prereq']"
                ]
                
                for selector in prereq_selectors:
                    try:
                        prereq_element = course_element.find_element(By.CSS_SELECTOR, selector)
                        prereq_text = prereq_element.text.strip()
                        if prereq_text:
                            course_detail.prerequisites = prereq_text
                            self.logger.debug(f"Found prerequisites via selector {selector}: {prereq_text[:50]}...")
                            break
                    except:
                        continue
                        
            except Exception as e:
                self.logger.debug(f"Error extracting prerequisites: {e}")
              # Extract notes
            try:
                notes_elements = course_element.find_elements(By.CSS_SELECTOR,".notes, .note, [class*='note'], .remark, [class*='remark']")
                notes = []
                for note_elem in notes_elements:
                    note_text = note_elem.text.strip()
                    if note_text and note_text not in notes:
                        notes.append(note_text)
                course_detail.notes = '; '.join(notes)
            except:
                # Try to find notes in text content - look for "Notes:" keyword
                try:
                    text = course_element.text
                    notes_patterns = [
                        r'Notes?:\s*(.+?)(?=\n\n|\nLEC|\nTUT|\nLAB|$)',
                        r'Delivery Instructions:\s*(.+?)(?=\n\n|\nLEC|\nTUT|\nLAB|$)',
                        r'Timetable Instructions:\s*(.+?)(?=\n\n|\nLEC|\nTUT|\nLAB|$)',
                        r'CANCELLED[;:\s]*(.+?)(?=\n\n|\nLEC|\nTUT|\nLAB|$)'
                    ]
                    notes_found = []
                    for pattern in notes_patterns:
                        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
                        for match in matches:
                            clean_note = match.strip()
                            if clean_note and clean_note not in notes_found:
                                notes_found.append(clean_note)
                    
                    if notes_found:
                        course_detail.notes = '; '.join(notes_found)
                except:
                    # If we can't get text content, just skip notes extraction
                    pass
            
            # Extract session information (lectures, tutorials, labs)
            self.extract_session_info(course_element, course_detail)
              # Extract additional metadata
            try:
                element_text = course_element.text
                
                # Credit value
                credit_match = re.search(r'(\d+\.?\d*)\s*credit', element_text, re.IGNORECASE)
                if credit_match:
                    course_detail.credit_value = credit_match.group(1)
                  # Campus information
                campus_keywords = ['St. George', 'Mississauga', 'Scarborough', 'UTM', 'UTSC']
                course_detail.campus = "St. George"  # Default campus
                for keyword in campus_keywords:
                    if keyword.lower() in element_text.lower():
                        course_detail.campus = keyword
                        break
                
                # Breadth categories
                breadth_pattern = r'BR=(\d+)'                
                breadth_matches = re.findall(breadth_pattern, element_text)
                course_detail.breadth_categories = breadth_matches
                
            except:
                pass
            
            # Set default campus if not already set
            if not course_detail.campus:
                course_detail.campus = "St. George"
            
            return course_detail if course_detail.course_code else None
            
        except Exception as e:
            log_error(self.logger, e, "extracting course details")
            return None
    
    def extract_session_info(self, course_element, course_detail: CourseDetail):
        """Extract lecture, tutorial, and lab session information."""
        try:
            # Look for session tables or lists
            session_selectors = [
                "table tr",
                ".session-row",
                ".meeting-pattern",
                "[class*='session']",
                "[class*='meeting']"
            ]
            
            session_elements = []
            for selector in session_selectors:
                try:
                    elements = course_element.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        session_elements = elements
                        break
                except:
                    continue
            
            for element in session_elements:
                try:
                    text = element.text.strip()
                    if not text or len(text) < 10:
                        continue
                    
                    # Parse session information
                    session_info = self.parse_session_text(text)
                    if session_info:
                        session_type = session_info.get('type', '').upper()
                        
                        if 'LEC' in session_type:
                            course_detail.lectures.append(session_info)
                        elif 'TUT' in session_type:
                            course_detail.tutorials.append(session_info)
                        elif 'LAB' in session_type or 'PRA' in session_type:
                            course_detail.labs.append(session_info)
                        else:
                            course_detail.sections.append(session_info)
                
                except:
                    continue
                    
        except Exception as e:
            self.logger.debug(f"Error extracting session info: {e}")
    
    def parse_session_text(self, text: str) -> Optional[Dict[str, str]]:
        """Parse session text to extract structured information."""
        try:
            # Common patterns for course sessions
            patterns = [
                # Pattern: LEC01 - Instructor Name - MWF 10:00-11:00 - Room BA1234
                r'(LEC|TUT|LAB|PRA)\s*(\d+)\s*-?\s*([^-]+)\s*-\s*([A-Z]{1,3}\s*[\d:]+(?:-[\d:]+)?)\s*-\s*(.+)',
                # Pattern: LEC01    Instructor Name    MWF 10:00-11:00    Room BA1234
                r'(LEC|TUT|LAB|PRA)\s*(\d+)\s+([^\t]+)\s+([A-Z]{1,3}\s*[\d:]+(?:-[\d:]+)?)\s+(.+)',
                # More flexible pattern
                r'(LEC|TUT|LAB|PRA)\s*(\d+).*?([A-Z]{1,3}\s*[\d:]+(?:-[\d:]+)?).*?([A-Z]{2,4}\s*\d+)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    groups = match.groups()
                    return {
                        'type': groups[0],
                        'section': f"{groups[0]}{groups[1]}",
                        'instructor': groups[2].strip() if len(groups) > 2 else '',
                        'time': groups[3].strip() if len(groups) > 3 else '',
                        'location': groups[4].strip() if len(groups) > 4 else ''
                    }
            
            # Fallback: extract what we can
            section_match = re.search(r'(LEC|TUT|LAB|PRA)\s*(\d+)', text, re.IGNORECASE)
            time_match = re.search(r'([A-Z]{1,3}\s*[\d:]+(?:-[\d:]+)?)', text)
            location_match = re.search(r'([A-Z]{2,4}\s*\d+)', text)
            
            if section_match:
                return {
                    'type': section_match.group(1),
                    'section': section_match.group(0),
                    'instructor': '',
                    'time': time_match.group(1) if time_match else '',
                    'location': location_match.group(1) if location_match else ''
                }
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Error parsing session text: {e}")
            return None
    
    def check_for_next_page(self) -> bool:
        """Check if there's a next page and navigate to it."""
        try:
            # Look for pagination elements
            next_selectors = [
                "a[aria-label*='next']",
                ".next-page",
                ".pagination .next",
                "button[title*='next']",
                "[class*='next']:not([disabled])",
                ".page-next",
                "a[rel='next']"
            ]
            
            for selector in next_selectors:
                try:
                    next_buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for button in next_buttons:
                        if button.is_displayed() and button.is_enabled():
                            # Check if button is not disabled
                            disabled = button.get_attribute('disabled')
                            aria_disabled = button.get_attribute('aria-disabled')
                            
                            if not disabled and aria_disabled != 'true':
                                self.logger.info(f"Found next page button with selector: {selector}")
                                
                                # Scroll to button and click
                                self.driver.execute_script("arguments[0].scrollIntoView(true);", button)
                                time.sleep(1)
                                button.click()
                                self.logger.info("Clicked next page button")
                                
                                # Wait for page to load
                                time.sleep(5)
                                self.current_page += 1
                                return True
                except:
                    continue
            
            # Also try looking for page numbers
            try:
                page_links = self.driver.find_elements(By.CSS_SELECTOR, 
                    ".pagination a, .page-numbers a, [class*='page'] a")
                
                for link in page_links:
                    if link.text.strip().isdigit():
                        page_num = int(link.text.strip())
                        if page_num == self.current_page + 1:
                            link.click()
                            self.logger.info(f"Clicked page {page_num}")
                            time.sleep(5)
                            self.current_page = page_num
                            return True
            except:
                pass
            
            self.logger.info("No next page found")
            return False
        except Exception as e:
            log_error(self.logger, e, "checking for next page")
            return False
    
    def extract_from_table(self) -> List[CourseDetail]:
        """Extract course data from table structure."""
        courses = []
        
        try:
            # Find all course rows
            course_rows = self.driver.find_elements(By.CSS_SELECTOR, "table tr")
            
            if not course_rows:
                self.logger.warning("No table rows found")
                return courses
            
            self.logger.info(f"Found {len(course_rows)} table rows")
            
            for i, row in enumerate(course_rows):
                try:
                    # Skip header rows
                    if i == 0 or 'header' in row.get_attribute('class').lower():
                        continue
                    
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) < 3:  # Minimum expected columns
                        continue
                    
                    course_detail = CourseDetail()
                    
                    # Extract data from cells - adjust based on actual table structure
                    # Common TTB table structure: Course Code | Course Title | Section | Instructor | Time | Location
                    if len(cells) >= 1:
                        course_detail.course_code = self.safe_extract_text(cells[0])
                    if len(cells) >= 2:
                        course_detail.course_title = self.safe_extract_text(cells[1])
                    
                    # Extract detailed session info from remaining cells
                    if len(cells) >= 3:
                        section_text = self.safe_extract_text(cells[2])
                        if section_text:
                            course_detail.sections.append({
                                'section': section_text,
                                'instructor': self.safe_extract_text(cells[3]) if len(cells) > 3 else '',
                                'time': self.safe_extract_text(cells[4]) if len(cells) > 4 else '',
                                'location': self.safe_extract_text(cells[5]) if len(cells) > 5 else ''
                            })
                    
                    # Set campus to default
                    course_detail.campus = "St. George"
                    
                    # Try to extract notes from remaining cells or row text
                    row_text = row.text
                    if "Notes:" in row_text:
                        notes_start = row_text.find("Notes:")
                        course_detail.notes = row_text[notes_start:].strip()
                    
                    if course_detail.course_code:
                        courses.append(course_detail)
                        self.logger.info(f"Extracted from table: {course_detail.course_code}")
                    
                except Exception as e:
                    self.logger.debug(f"Error extracting from table row {i}: {e}")
                    continue
            
        except Exception as e:
            log_error(self.logger, e, "extracting from table")
        
        return courses
    
    def extract_from_containers(self, course_elements) -> List[CourseDetail]:
        """Extract course data from container elements."""
        courses = []
        processed_codes = set()
        
        try:
            for i, element in enumerate(course_elements):
                try:
                    # Skip if we've processed too many elements (safety check)
                    if i > 100:
                        break
                    
                    # Extract course details
                    course_detail = self.extract_course_details(element)
                    
                    if course_detail and course_detail.course_code:
                        # Avoid duplicates
                        if course_detail.course_code in processed_codes:
                            continue
                        
                        processed_codes.add(course_detail.course_code)
                        courses.append(course_detail)
                        
                        self.logger.info(f"Extracted from container: {course_detail.course_code} - {course_detail.course_title}")
                    
                    # Small delay between processing courses
                    time.sleep(0.5)
                    
                except StaleElementReferenceException:
                    self.logger.debug(f"Stale element reference for course {i}")
                    continue
                except Exception as e:
                    self.logger.debug(f"Error processing course element {i}: {e}")
                    continue
        
        except Exception as e:
            log_error(self.logger, e, "extracting from containers")
        
        return courses
    
    def safe_extract_text(self, cells, index: int) -> str:
        """Safely extract text from table cell."""
        try:
            if isinstance(cells, list) and len(cells) > index:
                return cells[index].text.strip()
            elif hasattr(cells, 'text'):
                return cells.text.strip()
            return ""
        except:
            return ""
    
    def extract_all_courses_from_page(self, csv_writer=None, file_handle=None) -> List[CourseDetail]:
        """Extract all courses from the current page with detailed information."""
        courses = []
        
        try:
            self.logger.info(f"Extracting courses from page {self.current_page}")
            
            # Wait for content to load
            time.sleep(3)
            
            # First try to find table structure (most common for TTB)
            table_found = False
            try:
                # Wait for table to load
                table = self.driver.find_element(By.CSS_SELECTOR, "table")
                if table:
                    table_found = True
                    self.logger.info("Found table structure, extracting from table rows")
                    courses = self.extract_from_table()
            except:
                self.logger.info("No table found, trying alternative extraction methods")
            
            # If no table found or table extraction failed, try container-based extraction
            if not table_found or not courses:
                self.logger.info("Trying container-based extraction")
                
                # Try different selectors for course containers
                course_selectors = [
                    ".course-container",
                    ".course-item", 
                    ".course-row",
                    "[class*='course']:not([class*='search'])",
                    ".result-item",
                    "[data-course]",
                    ".expandable-section",
                    "div[class*='course']"
                ]
                
                course_elements = []
                for selector in course_selectors:
                    try:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements and len(elements) > 1:
                            course_elements = elements
                            self.logger.info(f"Found {len(elements)} course elements with selector: {selector}")
                            break
                    except:
                        continue
                
                if not course_elements:
                    # Fallback: try to find any clickable/expandable elements
                    course_elements = self.driver.find_elements(By.CSS_SELECTOR, 
                        "button[aria-expanded], .clickable, [onclick], [data-toggle]")
                    self.logger.info(f"Fallback: Found {len(course_elements)} potential course elements")
                
                courses = self.extract_from_containers(course_elements)
            
            # Save courses incrementally if writer is provided
            if csv_writer is not None and file_handle is not None:
                for course_detail in courses:
                    self.save_course_to_csv_incremental(course_detail, csv_writer, file_handle)
            
            self.logger.info(f"Successfully extracted {len(courses)} courses from page {self.current_page}")
            
        except Exception as e:
            log_error(self.logger, e, f"extracting courses from page {self.current_page}")
        
        return courses
    def scrape_all_courses(self, division: str = "Faculty of Arts and Science", filename: str = None) -> ScrapingResult:
        """Scrape all courses without subject filter, handling pagination and saving incrementally."""
        all_courses = []
        errors = []
        csv_filepath = None
        file_handle = None
        csv_writer = None
        
        try:
            self.logger.info(f"Starting to scrape ALL courses for division: {division}")
            
            # Set up incremental CSV saving at the start
            csv_filepath, file_handle, csv_writer = self.setup_incremental_csv(filename)
            if not csv_writer:
                errors.append("Failed to set up incremental CSV saving")
                self.logger.warning("Could not set up incremental CSV saving, continuing anyway")
            
            # Navigate to timetable
            if not self.navigate_to_timetable():
                errors.append("Failed to navigate to timetable page")
                return ScrapingResult(all_courses, 0, errors, "", "ALL")
            
            # Select division
            if not self.select_division(division):
                errors.append(f"Failed to select division {division}")
                return ScrapingResult(all_courses, 0, errors, "", "ALL")
            
            # Ensure sessions are selected
            if not self.ensure_sessions_selected():
                errors.append("Failed to ensure sessions are selected")
                return ScrapingResult(all_courses, 0, errors, "", "ALL")
            
            # Perform initial search (without subject filter)
            if not self.perform_search():
                errors.append("Failed to perform search")
                return ScrapingResult(all_courses, 0, errors, "", "ALL")
            
            # Extract courses from all pages
            page_count = 0
            while page_count < self.max_pages:
                page_count += 1
                
                # Extract courses from current page with incremental saving
                page_courses = self.extract_all_courses_from_page(csv_writer, file_handle)
                
                if page_courses:
                    all_courses.extend(page_courses)
                    self.logger.info(f"Page {self.current_page}: Found {len(page_courses)} courses, saved incrementally")
                else:
                    self.logger.warning(f"Page {self.current_page}: No courses found")
                
                # Try to go to next page
                if not self.check_for_next_page():
                    self.logger.info("No more pages to process")
                    break
                
                # Safety delay between pages
                time.sleep(3)
            
            # Convert CourseDetail objects to Course objects for consistency
            courses = []
            for course_detail in all_courses:
                course = Course(
                    course_code=course_detail.course_code,
                    course_title=course_detail.course_title,
                    section="", # Will be filled from sessions
                    instructor="", # Will be filled from sessions
                    day_time="", # Will be filled from sessions
                    location="", # Will be filled from sessions
                    session="Summer 2025",  # Default session
                    subject=course_detail.course_code[:3] if course_detail.course_code else "ALL",
                    delivery_mode="",
                    meeting_type="",
                    enrollment_indicator="",
                    waitlist_indicator="",
                    cancel_indicator=""                )
                courses.append(course)
            
            self.logger.info(f"Scraping completed! Processed {len(courses)} courses total")
            if csv_filepath:
                self.logger.info(f"All course data saved incrementally to: {csv_filepath}")
            
            log_scraping_session(self.logger, "Summer 2025", "ALL", len(courses))
            
        except Exception as e:
            log_error(self.logger, e, "scraping all courses")
            errors.append(f"Unexpected error: {str(e)}")
        finally:
            # Always close the file handle
            if file_handle:
                try:
                    file_handle.close()
                    self.logger.info("Closed incremental CSV file")
                except:
                    pass
        
        return ScrapingResult(courses, len(courses), errors, "Summer 2025", "ALL")
    
    def setup_incremental_csv(self, filename: str = None) -> tuple:
        """Set up incremental CSV saving. Returns (filepath, file_handle, csv_writer)."""
        try:
            if not filename:
                filename = f"ttb_courses_incremental_{int(time.time())}.csv"
            
            # Create output directory if it doesn't exist
            output_dir = "output"
            os.makedirs(output_dir, exist_ok=True)
            filepath = os.path.join(output_dir, filename)
            
            # Open file in write mode and create CSV writer
            file_handle = open(filepath, 'w', newline='', encoding='utf-8')
            csv_writer = csv.writer(file_handle)
            
            # Write header row
            headers = [
                'Course Code', 'Course Title', 'Description', 'Prerequisites', 
                'Notes', 'Credit Value', 'Campus', 'Breadth Categories',
                'Lectures', 'Tutorials', 'Labs', 'Total Sections',
                'Session', 'Subject', 'Timestamp'
            ]
            csv_writer.writerow(headers)
            
            self.logger.info(f"Set up incremental CSV saving to: {filepath}")
            return filepath, file_handle, csv_writer
            
        except Exception as e:
            log_error(self.logger, e, "setting up incremental CSV")
            return None, None, None
    
    def save_course_to_csv_incremental(self, course_detail: CourseDetail, csv_writer, file_handle):
        """Save a single course to CSV file immediately."""
        try:
            if not csv_writer or not course_detail or not course_detail.course_code:
                return False
            
            # Convert course detail to row data
            row_data = [
                course_detail.course_code,
                course_detail.course_title,
                course_detail.description,
                course_detail.prerequisites,
                course_detail.notes,
                course_detail.credit_value,
                course_detail.campus,
                ', '.join(course_detail.breadth_categories),
                '; '.join([f"{lec['section']}: {lec['instructor']} - {lec['time']} @ {lec['location']}" for lec in course_detail.lectures]),
                '; '.join([f"{tut['section']}: {tut['instructor']} - {tut['time']} @ {tut['location']}" for tut in course_detail.tutorials]),
                '; '.join([f"{lab['section']}: {lab['instructor']} - {lab['time']} @ {lab['location']}" for lab in course_detail.labs]),
                len(course_detail.sections),
                "Summer 2025",  # Default session
                course_detail.course_code[:3] if course_detail.course_code else "ALL",
                time.strftime("%Y-%m-%d %H:%M:%S")  # Timestamp
            ]
            
            # Write row and flush to ensure immediate save
            csv_writer.writerow(row_data)
            file_handle.flush()
            self.logger.info(f"Saved course to CSV: {course_detail.course_code}")
            return True
            
        except Exception as e:
            log_error(self.logger, e, f"saving course {course_detail.course_code if course_detail else 'unknown'} to CSV")
            return False

    def save_detailed_courses_to_csv(self, course_details: List[CourseDetail], filename: str = None) -> bool:
        """Save detailed course information to CSV file."""
        try:
            if not filename:
                filename = f"ttb_detailed_courses_{int(time.time())}.csv"
            
            # Create output directory if it doesn't exist
            output_dir = "output"
            os.makedirs(output_dir, exist_ok=True)
            filepath = os.path.join(output_dir, filename)
            
            # Convert course details to dictionaries
            course_dicts = [course.to_dict() for course in course_details]
            
            # Create DataFrame and save to CSV
            df = pd.DataFrame(course_dicts)
            df.to_csv(filepath, index=False)
            
            self.logger.info(f"Successfully saved {len(course_details)} detailed courses to {filepath}")
            return True
            
        except Exception as e:
            log_error(self.logger, e, f"saving detailed courses to {filename}")
            return False
    
    def save_to_csv(self, courses: List[Course], filename: str = None) -> bool:
        """Save courses to CSV file."""
        try:
            if not filename:
                filename = f"ttb_courses_{int(time.time())}.csv"
            
            # Create output directory if it doesn't exist
            output_dir = "output"
            os.makedirs(output_dir, exist_ok=True)
            filepath = os.path.join(output_dir, filename)
            
            # Convert courses to dictionaries
            course_dicts = [course.to_dict() for course in courses]
            
            # Create DataFrame and save to CSV
            df = pd.DataFrame(course_dicts)
            df.to_csv(filepath, index=False)
            
            self.logger.info(f"Successfully saved {len(courses)} courses to {filepath}")
            return True
            
        except Exception as e:
            log_error(self.logger, e, f"saving courses to {filename}")
            return False
    
    def close(self):
        """Close the WebDriver."""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("WebDriver closed successfully")
            except Exception as e:
                log_error(self.logger, e, "closing WebDriver")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

if __name__ == "__main__":
    # Quick test
    with TTBScraperEnhanced(headless=False) as scraper:
        result = scraper.scrape_all_courses()
        if result.courses:
            print(f"Found {len(result.courses)} courses")
            scraper.save_to_csv(result.courses, "enhanced_courses.csv")
        else:
            print("No courses found")
            print("Errors:", result.errors)
