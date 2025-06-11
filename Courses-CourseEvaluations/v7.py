import time
import json
import csv
import re
import traceback
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd


class UofTCourseEvaluationScraper:
    def __init__(self, headless=True, wait_time=10, max_pages=None):
        """
        Initialize the scraper with Chrome driver
        
        Args:
            headless (bool): Run browser in headless mode
            wait_time (int): Maximum wait time for elements to load
            max_pages (int, optional): DEPRECATED - No longer used, kept for backward compatibility
        """
        self.wait_time = wait_time
        self.max_pages = max_pages  # Kept for backward compatibility but no longer used
        self.driver = self._setup_driver(headless)
        self.wait = WebDriverWait(self.driver, wait_time)
        self.url = None
        self.base_filename = f"course_evaluation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.all_data = []
        # Initialize the combined data structure
        self.combined_data = {
            'page_info': {
                'total_pages': 0,
                'total_records': 0,
                'scraped_at': datetime.now().isoformat(),
                'table_structure': {}
            },
            'evaluation_data': []
        }
        
    def _setup_driver(self, headless):
        """Setup Chrome driver with appropriate options"""
        chrome_options = Options()
        
        if headless:
            chrome_options.add_argument("--headless=new")
        
        # Additional options for stability
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        # Use webdriver-manager to automatically handle ChromeDriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    
    def scrape_course_evaluation(self, url):
        """
        Scrape course evaluation data from the given URL
        
        Args:
            url (str): URL of the course evaluation page
            
        Returns:
            dict: Scraped course evaluation data
        """
        print(f"Scraping course evaluation from: {url}")
        try:
            self.driver.get(url)
            # Wait for page to load completely - improved wait for data table
            print("Waiting for page to load completely...")
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
            
            # Set maximum page size first to reduce the number of pages to scrape
            page_size_changed = self._set_max_page_size()
            # Additional wait for dynamic content and data table to fully load
            # Wait longer if page size was changed to allow table refresh
            if page_size_changed:
                print("Page size was changed, waiting for table to refresh...")
                time.sleep(5)  # Extra wait for table refresh
            
            self._wait_for_data_table_to_load(page_size_changed)
            
            # Initialize combined_data URL
            self.combined_data['page_info']['source_url'] = url
            
            # Get all data using fixed pagination approach
            all_table_data = self._scrape_all_pages_fixed()
            
            # Extract page metadata
            page_metadata = self._extract_page_info()
            
            # Add additional metadata to page_info
            for key, value in page_metadata.items():
                self.combined_data['page_info'][key] = value
            # The combined_data structure is already updated throughout scraping
            # by the save_incremental_data method, just return it
            return self.combined_data
        except Exception as e:
            print(f"Error scraping course evaluation: {str(e)}")
            traceback.print_exc()
            return None
            
    def _wait_for_data_table_to_load(self, page_size_changed=False):
        """
        Wait for the actual data table to be fully loaded.
        This is particularly important for the first page where the data table
        might be loaded dynamically via JavaScript.
        
        Args:
            page_size_changed (bool): If True, wait longer for table refresh
        """
        print("Waiting for data table to fully load...")
        
        max_attempts = 7 if page_size_changed else 5
        attempt = 1
        initial_wait = 5 if page_size_changed else 3
        
        while attempt <= max_attempts:
            try:
                # Wait a bit for dynamic content to load
                time.sleep(initial_wait if attempt == 1 else 3)
                
                # Find all tables
                tables = self.driver.find_elements(By.TAG_NAME, "table")
                print(f"Attempt {attempt}: Found {len(tables)} table(s)")
                
                # Look for the table with substantial rows (the data table)
                data_table_found = False
                for i, table in enumerate(tables):
                    try:
                        rows = table.find_elements(By.TAG_NAME, "tr")
                        expected_min_rows = 10 if page_size_changed else 5  # Expect more rows if page size was increased
                        
                        if len(rows) > expected_min_rows:  # Must have substantial data
                            table_text = table.text.strip()
                            # Check if it contains course data patterns
                            if any(pattern in table_text for pattern in ['AFR', 'ANA', 'ANT', 'Fall', 'Winter', 'Instructor', 'Course', 'Dept']):
                                print(f"Found data table {i+1} with {len(rows)} rows on attempt {attempt}")
                                # Simplified validation: if we found a table with the right patterns and enough rows, consider it valid
                                print(f"Data table {i+1} is ready with {len(rows)} rows")
                                data_table_found = True
                                break
                    except Exception as e:
                        print(f"Error checking table {i+1}: {e}")
                        continue
                
                if data_table_found:
                    print("Data table is fully loaded and validated!")
                    return True
                    
                print(f"Data table not ready yet, waiting... (attempt {attempt}/{max_attempts})")
                attempt += 1
                
            except Exception as e:
                print(f"Error checking for data table on attempt {attempt}: {e}")
                attempt += 1
                time.sleep(2)
        
        print("Warning: Data table may not be fully loaded, but proceeding...")
        return False
        
    def scrape_first_page_with_retry(self):
        """
        Special method to handle first page scraping with retry logic
        """
        print("Processing first page with enhanced retry logic...")
        max_retry_attempts = 3
        
        for retry in range(max_retry_attempts):
            print(f"\n--- First Page Attempt {retry + 1}/{max_retry_attempts} ---")
            
            try:
                # Enhanced wait for data table
                data_table_ready = self._wait_for_data_table_to_load()
                
                if not data_table_ready:
                    print(f"Data table not ready on attempt {retry + 1}, will retry...")
                    if retry < max_retry_attempts - 1:
                        # Refresh page and try again
                        print("Refreshing page and retrying...")
                        self.driver.refresh()
                        time.sleep(5)
                        continue
                
                # Try to extract data
                first_page_data = self._extract_main_table()
                
                if first_page_data and len(first_page_data) > 0:
                    print(f"Successfully extracted {len(first_page_data)} records from first page")
                    return first_page_data
                else:
                    print(f"No data extracted on attempt {retry + 1}")
                    if retry < max_retry_attempts - 1:
                        print("Refreshing page and retrying...")
                        self.driver.refresh()
                        time.sleep(5)
                        continue
                        
            except Exception as e:
                print(f"Error on first page attempt {retry + 1}: {e}")
                if retry < max_retry_attempts - 1:
                    print("Refreshing page and retrying...")
                    self.driver.refresh()
                    time.sleep(5)
                    continue
                else:
                    print("All retry attempts failed for first page")
                    traceback.print_exc()
        
        print("Failed to extract data from first page after all retry attempts")
        return []
    
    def _scrape_all_pages_fixed(self):
        """
        Scrape data from all pages using a fixed approach for UofT course evaluations.
        Instead of using a max_pages limit, this method will continue scraping until
        navigation to the next page fails twice consecutively, indicating that we've 
        reached the end of available data.
        
        Returns:
            list: Combined list of data from all pages
        """
        all_data = []
        current_page = 1
        has_more_pages = True
        consecutive_failures = 0
        
        # Loop through pages until we fail to navigate to the next page twice in a row
        while has_more_pages:
            print(f"\n--- Processing Page {current_page} ---")
            
            # Special handling for first page - ensure data table is loaded with retry logic
            if current_page == 1:
                print("First page - ensuring data table is fully loaded with enhanced retry...")
                current_page_data = self.scrape_first_page_with_retry()
                
                # Only process data for the first page here
                # (subsequent pages will be handled in the navigation section)
                if current_page_data:
                    print(f"Found {len(current_page_data)} records on page {current_page}")
                    all_data.extend(current_page_data)
                    # Save data from the first page incrementally
                    self.save_incremental_data(current_page_data, current_page)
                else:
                    print(f"No data found on page {current_page}")
            else:
                # For pages after the first, data extraction is done after successful navigation
                # to avoid duplicate processing
                current_page_data = []
            
            # Store initial data from first record to verify page change
            first_record_text = ""
            if current_page_data and len(current_page_data) > 0:
                first_record_text = str(current_page_data[0])
            
            # Look for next button - SPECIFICALLY for the UofT course evaluation format
            # This targets the button with onclick="__getFbvGrid(n);" value=">"
            try:
                # Wait for a moment to ensure page is fully loaded
                time.sleep(2)
                
                # Find the '>' button that calls __getFbvGrid function
                next_button = self.driver.find_element(By.XPATH, f"//input[@type='button' and @value='>' and contains(@onclick, '__getFbvGrid')]")
                
                if next_button:
                    print(f"Found 'Next' button for page {current_page + 1}")
                    
                    # Get the onclick attribute to see which page it will navigate to
                    onclick_attr = next_button.get_attribute('onclick')
                    print(f"Next button onclick: {onclick_attr}")
                    
                    # Click the button using JavaScript (more reliable)
                    self.driver.execute_script("arguments[0].click();", next_button)
                    print(f"Clicked 'Next' button to navigate to page {current_page + 1}")
                    
                    # Wait for page to refresh
                    time.sleep(3)
                    
                    # Verify page changed by checking if the data is different
                    new_data = self._extract_main_table()
                    new_first_record = str(new_data[0]) if new_data and len(new_data) > 0 else ""
                    
                    # Check for meaningful change between pages
                    if new_first_record and new_first_record != first_record_text:
                        print(f"Successfully navigated to page {current_page + 1}")
                        current_page += 1
                        consecutive_failures = 0  # Reset failure counter on success
                        
                        # Add new data only if we're sure it's from a new page
                        print(f"Found {len(new_data)} records on new page {current_page}")
                        all_data.extend(new_data)
                        self.save_incremental_data(new_data, current_page)
                    else:
                        print("Navigation failed or reached end of data - page content didn't change")
                        consecutive_failures += 1
                        if consecutive_failures >= 2:
                            print(f"Encountered {consecutive_failures} consecutive navigation failures - ending pagination")
                            has_more_pages = False
                        else:
                            print(f"First navigation failure (attempt {consecutive_failures}/2) - will try again")
                else:
                    print("No 'Next' button found - reached the last page")
                    consecutive_failures += 1
                    if consecutive_failures >= 2:
                        print(f"No 'Next' button found {consecutive_failures} times in a row - ending pagination")
                        has_more_pages = False
                    else:
                        print(f"No 'Next' button (attempt {consecutive_failures}/2) - will try again")
                    
            except NoSuchElementException:
                print("No 'Next' button found - reached the last page")
                consecutive_failures += 1
                if consecutive_failures >= 2:
                    print(f"No 'Next' button found {consecutive_failures} times in a row - ending pagination")
                    has_more_pages = False
                else:
                    print(f"No 'Next' button (attempt {consecutive_failures}/2) - will try again")
                
            except Exception as e:
                print(f"Error during pagination: {e}")
                traceback.print_exc()
                consecutive_failures += 1
                if consecutive_failures >= 2:
                    print(f"Pagination errors occurred {consecutive_failures} times in a row - ending pagination")
                    has_more_pages = False
                else:
                    print(f"Pagination error (attempt {consecutive_failures}/2) - will try again")
        
        print(f"\nCompleted scraping all {current_page} pages, found total {len(all_data)} records")
        return all_data
    
    def _analyze_table_structure(self, table):
        """
        Analyze the table structure to understand column patterns
        This helps adapt to different evaluation formats
        """
        structure_info = {
            'total_columns': 0,
            'has_instructor_ratings': False,
            'has_course_ratings': False,
            'has_response_counts': False,
            'division_type': 'unknown',
            'detected_headers': []
        }
        
        try:
            # Get a sample of rows to analyze
            rows = table.find_elements(By.TAG_NAME, "tr")[:10]  # First 10 rows
            
            # Find the longest row (likely data row)
            max_cols = 0
            sample_row = None
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) > max_cols:
                    max_cols = len(cells)
                    sample_row = row
            
            structure_info['total_columns'] = max_cols
            
            # Analyze header patterns
            header_row = None
            for row in rows[:3]:  # Check first 3 rows for headers
                cells = row.find_elements(By.TAG_NAME, "th") or row.find_elements(By.TAG_NAME, "td")
                if cells:
                    row_text = " ".join(cell.text.strip().lower() for cell in cells)
                    
                    # Check for common header patterns
                    if any(pattern in row_text for pattern in ['dept', 'course', 'instructor', 'term']):
                        header_row = row
                        structure_info['detected_headers'] = [cell.text.strip() for cell in cells]
                        break
            
            # Analyze content patterns from the table text
            table_text = table.text.lower()
            
            # Check for instructor rating patterns (INS1, INS2, etc.)
            if any(pattern in table_text for pattern in ['ins1', 'ins2', 'ins3', 'instructor']):
                structure_info['has_instructor_ratings'] = True
            
            # Check for course rating patterns (ARTSC, course evaluation, etc.)
            if any(pattern in table_text for pattern in ['artsc', 'course', 'rating', 'evaluation']):
                structure_info['has_course_ratings'] = True
            
            # Check for response count patterns
            if any(pattern in table_text for pattern in ['invited', 'responses', 'number', 'size']):
                structure_info['has_response_counts'] = True
            
            # Try to determine division type based on content
            if 'arts' in table_text and 'science' in table_text:
                structure_info['division_type'] = 'arts_science'
            elif 'engineering' in table_text:
                structure_info['division_type'] = 'engineering'
            elif 'medicine' in table_text:
                structure_info['division_type'] = 'medicine'
            elif 'business' in table_text:
                structure_info['division_type'] = 'business'
                
            print(f"Table structure analysis: {structure_info}")
            
        except Exception as e:
            print(f"Error analyzing table structure: {e}")
        
        return structure_info
    
    def _extract_main_table(self):
        """Extract the main course evaluation data table with enhanced column detection"""
        table_data = []
        
        try:
            print("Looking for the main course evaluation table...")
            
            # Find all tables
            tables = self.driver.find_elements(By.TAG_NAME, "table")
            print(f"Found {len(tables)} table(s) on the page")
            
            # Strategy: Look for the table with actual course data
            table_element = None
            table_structure = None
            for i, table in enumerate(tables):
                try:
                    rows = table.find_elements(By.TAG_NAME, "tr")
                    print(f"Table {i+1}: {len(rows)} rows")
                    
                    if len(rows) > 5:  # Must have substantial data
                        # Check first few rows for course data patterns
                        table_text = table.text.strip()
                        # Look for course codes like AFR, ANA, etc.
                        if any(pattern in table_text for pattern in ['AFR', 'ANA', 'ANT', 'Fall', 'Winter', 'Instructor', 'Course', 'Dept']):
                            print(f"Table {i+1} contains course evaluation data")
                            print(f"Table {i+1} first 200 chars: {table_text[:200]}")
                            
                            # Analyze table structure
                            table_structure = self._analyze_table_structure(table)
                            
                            # Try to find headers in multiple ways
                            headers = self._extract_table_headers(table, rows, table_structure)
                            
                            if headers and len(headers) > 3:  # Must have meaningful headers
                                table_element = table
                                print(f"Selected table {i+1} with headers: {headers}")
                                break
                        
                except Exception as e:
                    print(f"Error analyzing table {i+1}: {e}")
                    continue
            
            if not table_element:
                print("Could not find the main data table")
                return table_data
            
            # Store table structure info
            if table_structure:
                self.combined_data['page_info']['table_structure'] = table_structure
            
            # Extract table data with the found table
            print("Extracting data from the selected table...")
            rows = table_element.find_elements(By.TAG_NAME, "tr")
            print(f"Table has {len(rows)} total rows")
            
            # Get headers
            headers = self._extract_table_headers(table_element, rows, table_structure)
            print(f"Final headers ({len(headers)}): {headers}")
            
            if not headers:
                print("No valid headers found")
                return table_data
            
            # Extract data rows
            data_rows_processed = 0
            header_row_index = self._find_header_row_index(table_element, rows)
            print(f"Starting data extraction from row {header_row_index + 2} (after headers)")
            
            for i, row in enumerate(rows[header_row_index + 1:], header_row_index + 1):
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    
                    if len(cells) > 0:
                        row_data = {}
                        
                        # Handle cases where row has different number of columns than headers
                        max_cols = max(len(cells), len(headers))
                        
                        # Ensure we have enough headers for all columns
                        if len(headers) < max_cols:
                            additional_headers = [f"Column_{j+1}" for j in range(len(headers), max_cols)]
                            headers.extend(additional_headers)
                            print(f"Extended headers to {len(headers)} columns for row with {len(cells)} cells")
                        
                        # Map each cell to its corresponding header
                        for j, cell in enumerate(cells):
                            header = headers[j] if j < len(headers) else f"Column_{j+1}"
                            cell_text = cell.text.strip()
                            row_data[header] = cell_text
                        
                        # Add empty values for missing columns if row has fewer cells than headers
                        for j in range(len(cells), len(headers)):
                            header = headers[j]
                            row_data[header] = ""
                        
                        # Debug: Show first few rows being processed
                        if data_rows_processed < 5:
                            first_few_cells = {k: v for k, v in list(row_data.items())[:5]}
                            print(f"Row {i}: {first_few_cells}")
                        
                        # Validate that this is actual course data, not headers or malformed data
                        if self._is_valid_course_data_row(row_data):
                            table_data.append(row_data)
                            data_rows_processed += 1
                        else:
                            if data_rows_processed < 5:  # Only show rejections for first few rows
                                print(f"  -> Row {i} rejected by validation")
                    
                    # Print progress for large tables
                    if i % 50 == 0 and i > 0:
                        print(f"Processed {i} rows, extracted {data_rows_processed} data rows...")
                        
                except Exception as e:
                    print(f"Error processing row {i}: {e}")
                    continue
            
            print(f"Successfully extracted {len(table_data)} course evaluation records")
            
        except Exception as e:
            print(f"Error extracting main table: {str(e)}")
            traceback.print_exc()
        
        return table_data
    
    def _extract_table_headers(self, table, rows, structure_info=None):
        """Extract headers from table using multiple strategies with dynamic column detection"""
        headers = []
        
        try:
            # Strategy 1: Look for TH elements in first few rows
            for row_index in range(min(3, len(rows))):
                row = rows[row_index]
                th_cells = row.find_elements(By.TAG_NAME, "th")
                
                if th_cells:
                    candidate_headers = []
                    for cell in th_cells:
                        text = cell.text.strip()
                        # If text is empty, try to get it from child elements
                        if not text:
                            child_elements = cell.find_elements(By.XPATH, ".//*")
                            for child in child_elements:
                                child_text = child.text.strip()
                                if child_text:
                                    text = child_text
                                    break
                        candidate_headers.append(text if text else f"Column_{len(candidate_headers)+1}")
                    
                    # Check if these look like valid headers
                    if candidate_headers and any(h for h in candidate_headers if len(h) > 0):
                        headers = candidate_headers
                        print(f"Found headers in row {row_index + 1}: {headers}")
                        break
            
            # Strategy 2: If no TH headers found, look for TD headers with expanded keyword detection
            if not headers or all(not h or h.startswith('Column_') for h in headers):
                print("No TH headers found, trying TD headers...")
                
                for row_index in range(min(3, len(rows))):
                    row = rows[row_index]
                    td_cells = row.find_elements(By.TAG_NAME, "td")
                    
                    if td_cells:
                        candidate_headers = []
                        valid_header_count = 0
                        
                        for cell in td_cells:
                            text = cell.text.strip()
                            # Expanded header keywords to handle different divisions
                            header_keywords = [
                                'dept', 'course', 'instructor', 'term', 'year', 'name', 'division',
                                'ins1', 'ins2', 'ins3', 'ins4', 'ins5', 'ins6',
                                'artsc1', 'artsc2', 'artsc3', 'artsc4', 'artsc5', 'artsc6',
                                'number', 'invited', 'responses', 'response', 'size',
                                'first', 'last', 'faculty', 'school', 'program',
                                'evaluation', 'rating', 'score', 'mean', 'average',
                                'section', 'class', 'enrollment'
                            ]
                            
                            # Skip if this looks like actual data (e.g., course codes)
                            if (any(pattern in text.upper() for pattern in ['AFR', 'ANA', 'ANT', 'AST', 'BCH', 'BIO', 'CHM', 'CSC', 'ECO', 'ENG', 'HIS', 'MAT', 'PHY', 'PSY', 'SOC']) 
                                and any(char.isdigit() for char in text)):
                                # This looks like course data, not headers
                                break
                            
                            # Check for header patterns
                            if any(keyword in text.lower() for keyword in header_keywords):
                                candidate_headers.append(text)
                                valid_header_count += 1
                            elif text and not text.isdigit() and len(text) > 1 and not self._looks_like_data(text):
                                candidate_headers.append(text)
                            else:
                                candidate_headers.append(f"Column_{len(candidate_headers)+1}")
                        
                        # Accept if we found reasonable headers (more flexible threshold)
                        if valid_header_count >= 2 and len(candidate_headers) >= 5:
                            headers = candidate_headers
                            print(f"Found TD headers in row {row_index + 1}: {headers}")
                            break
            
            # Strategy 3: Generate dynamic headers based on actual column count
            if not headers or len([h for h in headers if h and not h.startswith('Column_')]) < 3:
                print("Using dynamic column detection for headers")
                
                # Count columns from the first data row
                max_cols = 0
                for row in rows[:5]:  # Check first 5 rows
                    cells = row.find_elements(By.TAG_NAME, "td")
                    max_cols = max(max_cols, len(cells))
                
                if max_cols > 0:
                    headers = [f"Column_{i+1}" for i in range(max_cols)]
                    print(f"Generated {max_cols} dynamic headers: {headers}")
                else:
                    # Ultimate fallback
                    headers = [
                        "Dept", "Division", "Course", "Last Name", "First Name", 
                        "Term", "Year", "INS1", "INS2", "INS3", "INS4", "INS5", "INS6",
                        "ARTSC1", "ARTSC2", "ARTSC3", "Number Invited", "Number Responses"
                    ]
                    print("Using fallback predefined headers")
            
        except Exception as e:
            print(f"Error extracting headers: {e}")
            # Fallback to dynamic column generation
            try:
                max_cols = 0
                for row in rows[:5]:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    max_cols = max(max_cols, len(cells))
                headers = [f"Column_{i+1}" for i in range(max(max_cols, 15))]
            except:
                headers = [f"Column_{i+1}" for i in range(20)]  # Ultimate fallback
        
        return headers
    
    def _looks_like_data(self, text):
        """Check if text looks like actual data rather than a header"""
        # Check for course code patterns
        if re.match(r'^[A-Z]{3}\d+[A-Z]?\d?$', text):
            return True
        # Check for numeric patterns
        if text.isdigit() or re.match(r'^\d+\.\d+$', text):
            return True
        # Check for semester patterns
        if text in ['Fall', 'Winter', 'Summer', 'Spring']:
            return True
        return False
    
    def _find_header_row_index(self, table, rows):
        """Find which row contains the headers"""
        try:
            # Look for row with TH elements
            for i, row in enumerate(rows[:3]):
                th_cells = row.find_elements(By.TAG_NAME, "th")
                if th_cells:
                    return i
            
            # Look for row with header-like content
            for i, row in enumerate(rows[:3]):
                td_cells = row.find_elements(By.TAG_NAME, "td")
                if td_cells:
                    row_text = row.text.strip().lower()
                    if any(keyword in row_text for keyword in ['dept', 'course', 'instructor', 'term']):
                        return i
            
            # Default to first row
            return 0
        except Exception as e:
            print(f"Error finding header row: {e}")
            return 0
    
    def _is_valid_course_data_row(self, row_data):
        """
        Validate that a row contains actual course data, not headers or malformed data
        Enhanced to handle different column structures from different divisions
        
        Args:
            row_data (dict): Dictionary containing row data with headers as keys
            
        Returns:
            bool: True if this appears to be valid course data
        """
        try:
            # Check if we have any data at all
            if not any(value for value in row_data.values() if value and value.strip()):
                return False
            
            # Get key fields for validation with flexible field names
            dept = ""
            course = ""
            name_field = ""
            
            # Try different possible column names for common fields
            for key, value in row_data.items():
                key_lower = key.lower()
                if 'dept' in key_lower or 'department' in key_lower:
                    dept = value.strip()
                elif 'course' in key_lower or 'subject' in key_lower:
                    course = value.strip()
                elif 'name' in key_lower or 'instructor' in key_lower:
                    name_field = value.strip()
            
            # Skip obvious header rows
            header_indicators = [
                'dept', 'department', 'division', 'course', 'subject', 'code',
                'last name', 'first name', 'instructor', 'term', 'year', 'semester',
                'number', 'invited', 'responses', 'evaluation', 'rating', 'mean'
            ]
            
            # Check if any field contains header-like text
            for value in [dept, course, name_field]:
                if value.lower() in header_indicators:
                    print(f"Skipping header row: {dept}, {course}, {name_field}")
                    return False
            
            # More sophisticated validation
            valid_indicators = 0
            
            # Check for department codes (usually 3-4 capital letters)
            if dept and re.match(r'^[A-Z]{2,5}$', dept):
                valid_indicators += 1
            
            # Check for course patterns (letters followed by numbers)
            if course and re.match(r'^[A-Z]{2,5}\d+[A-Z]?\d*$', course):
                valid_indicators += 2  # Course patterns are strong indicators
            
            # Check for names (contains letters and possibly spaces/apostrophes)
            if name_field and re.match(r"^[A-Za-z\s'\-\.]+$", name_field) and len(name_field) > 2:
                valid_indicators += 1
            
            # Check for numeric data in evaluation columns
            numeric_count = 0
            for key, value in row_data.items():
                if value and value.strip():
                    # Check for numeric patterns that suggest evaluation data
                    if re.match(r'^\d+\.?\d*$', value.strip()) or value.strip() in ['Fall', 'Winter', 'Summer', 'Spring']:
                        numeric_count += 1
            
            if numeric_count >= 3:  # At least 3 numeric/term fields
                valid_indicators += 1
            
            # Accept if we have strong indicators of course data
            if valid_indicators >= 2:
                return True
            
            # Fallback: if we have substantial non-empty data, accept it
            non_empty_count = sum(1 for value in row_data.values() if value and value.strip())
            if non_empty_count >= 5:  # At least 5 fields with data
                # Make sure it's not all header text
                header_like_count = 0
                for value in row_data.values():
                    if value and any(indicator in value.lower() for indicator in header_indicators):
                        header_like_count += 1
                
                if header_like_count < non_empty_count * 0.3:  # Less than 30% header-like text
                    return True
            
            return False
            
        except Exception as e:
            print(f"Error validating row data: {e}")
            return False
    
    def _extract_page_info(self):
        """Extract general page information"""
        page_info = {}
        
        try:
            # Try to find any page headers or descriptions
            header_selectors = ["h1", "h2", ".page-title", ".header", "[class*='title']"]
            for selector in header_selectors:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element.text.strip():
                        page_info['page_header'] = element.text.strip()
                        break
                except NoSuchElementException:
                    continue
                
        except Exception as e:
            print(f"Error extracting page info: {str(e)}")
        
        return page_info
    
    def save_data(self, data, filename=None):
        """
        Save scraped data to files
        
        Args:
            data (dict): Scraped data
            filename (str): Base filename (without extension)
        """
        if not filename:
            filename = f"course_evaluation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Save as JSON
        json_filename = f"{filename}.json"
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Data saved to {json_filename}")
        
        # Save as CSV - use the evaluation_data directly if it exists
        csv_filename = f"{filename}.csv"
        
        if data.get('evaluation_data') and isinstance(data['evaluation_data'], list):
            # Save the table data directly as CSV
            df = pd.DataFrame(data['evaluation_data'])
            df.to_csv(csv_filename, index=False)
            print(f"Course evaluation data saved to {csv_filename} ({len(data['evaluation_data'])} records)")
        else:
            # Fallback to flattened data
            flattened_data = self._flatten_data(data)
            df = pd.DataFrame([flattened_data])
            df.to_csv(csv_filename, index=False)
            print(f"Flattened data saved to {csv_filename}")
    
    def _flatten_data(self, data):
        """Flatten nested dictionary for CSV export"""
        flattened = {}
        
        def flatten(obj, parent_key=''):
            for key, value in obj.items():
                new_key = f"{parent_key}_{key}" if parent_key else key
                
                if isinstance(value, dict):
                    flatten(value, new_key)
                elif isinstance(value, list):
                    if value and isinstance(value[0], dict):
                        # Skip complex list data for flattening
                        flattened[f"{new_key}_count"] = len(value)
                    else:
                        flattened[new_key] = '; '.join(map(str, value))
                else:
                    flattened[new_key] = value
        
        flatten(data)
        return flattened
    
    def close(self):
        """Close the browser driver"""
        if self.driver:
            self.driver.quit()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def _set_max_page_size(self):
        """
        Set the page size to the maximum available value to reduce the number of pages needed to scrape
        Targets the specific element: fbvGridPageSizeSelectLvl1
        
        Returns:
            bool: True if successfully changed page size, False otherwise
        """
        try:
            print("Attempting to set maximum page size...")
            
            # Wait for the page size selector to be present using the specific ID
            try:
                self.wait.until(EC.presence_of_element_located((By.ID, "fbvGridPageSizeSelectLvl1")))
                print("Found page size selector container")
            except TimeoutException:
                print("Page size selector container not found - continuing with default page size")
                return False
            
            # Wait longer for dynamic content to load - the page size selector might be populated via JavaScript
            print("Waiting for page size selector to be populated with options...")
            time.sleep(8)  # Increased wait time for dynamic loading
            
            # Try multiple approaches to wait for the selector to be populated
            max_wait_attempts = 10
            for attempt in range(max_wait_attempts):
                try:
                    # Check if the container now has content
                    container = self.driver.find_element(By.ID, "fbvGridPageSizeSelectLvl1")
                    container_html = container.get_attribute("innerHTML")
                    
                    if container_html.strip():
                        print(f"Page size container populated on attempt {attempt + 1}")
                        print(f"Container content: {container_html}")
                        break
                    else:
                        print(f"Attempt {attempt + 1}: Container still empty, waiting...")
                        time.sleep(2)
                        
                        # Try to trigger any JavaScript that might populate the selector
                        if attempt == 3:
                            print("Trying to trigger page size selector loading...")
                            self.driver.execute_script("""
                                // Try to trigger any onload or initialization functions
                                if (typeof window.initPageSize === 'function') window.initPageSize();
                                if (typeof window.loadPageSizeSelector === 'function') window.loadPageSizeSelector();
                                
                                // Try to find and trigger any page size related functions
                                for (var prop in window) {
                                    if (prop.toLowerCase().includes('pagesize') && typeof window[prop] === 'function') {
                                        try { window[prop](); } catch(e) {}
                                    }
                                }
                            """)
                        
                except Exception as e:
                    print(f"Error checking container on attempt {attempt + 1}: {e}")
                    continue
            
            # Check final state
            try:
                container = self.driver.find_element(By.ID, "fbvGridPageSizeSelectLvl1")
                container_html = container.get_attribute("innerHTML")
                if not container_html.strip():
                    print("Page size container remained empty - selector may not be available for this dataset")
                    return False
            except Exception as e:
                print(f"Could not inspect final container state: {e}")
                return False            
            # Try to find page size selectors using multiple strategies
            page_size_selectors = [
                "#fbvGridPageSizeSelectBlock select",
                ".pageSizeSelectWrapper select", 
                ".select-pageSize select",
                "#fbvGridPageSizeSelectLvl1 select",
                "select[name*='PageSize']",
                "select[name*='pagesize']", 
                "select[id*='PageSize']",
                "select[id*='pagesize']",
                "select[onchange*='PageSize']",
                "select[onchange*='pagesize']"
            ]
            
            select_element = None
            current_page_size = None
            
            print("Searching for page size selector using multiple strategies...")
            for i, selector in enumerate(page_size_selectors):
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        select_element = elements[0]
                        current_page_size = int(select_element.get_attribute("value"))
                        print(f"Found page size select using selector #{i+1} '{selector}' with current value: {current_page_size}")
                        break
                except Exception as e:
                    continue
            
            # If still not found, try a more comprehensive approach
            if not select_element:
                print("Standard selectors failed, trying comprehensive search...")
                try:
                    # Find all select elements on the page
                    all_selects = self.driver.find_elements(By.TAG_NAME, "select")
                    print(f"Found {len(all_selects)} total select elements on page")
                    
                    for i, select in enumerate(all_selects):
                        try:
                            options = select.find_elements(By.TAG_NAME, "option")
                            if len(options) >= 3:  # Must have multiple options
                                # Check if options look like page sizes (numbers like 5, 10, 25, 50, 100)
                                option_values = []
                                for option in options:
                                    try:
                                        val = int(option.get_attribute("value"))
                                        option_values.append(val)
                                    except (ValueError, TypeError):
                                        continue
                                
                                # Check if this looks like page size options
                                if (len(option_values) >= 3 and 
                                    any(val >= 50 for val in option_values) and  # Has large page size option
                                    all(val > 0 for val in option_values)):  # All positive numbers
                                    
                                    select_element = select
                                    current_page_size = int(select.get_attribute("value"))
                                    print(f"Found page size select #{i+1} by content analysis")
                                    print(f"Available page sizes: {sorted(option_values)}")
                                    print(f"Current page size: {current_page_size}")
                                    break
                        except Exception as e:
                            continue
                            
                except Exception as e:
                    print(f"Comprehensive search failed: {e}")
            
            if not select_element:
                print("Could not find any page size selector on the page")
                return False            # Get all available options and find the maximum (ideally 100)
            options = select_element.find_elements(By.TAG_NAME, "option")
            print(f"Found {len(options)} page size options")
            
            # Display all available options
            available_options = []
            for option in options:
                try:
                    value = int(option.get_attribute("value"))
                    option_text = option.text.strip()
                    available_options.append((value, option_text, option))
                    print(f"Option: {option_text} (value: {value})")
                except (ValueError, TypeError):
                    continue
            
            # Sort by value to find the best option
            available_options.sort(key=lambda x: x[0])
            
            if not available_options:
                print("No valid page size options found")
                return False
            
            # Try to find 100 first, then fall back to maximum available
            target_option = None
            for value, text, option in available_options:
                if value == 100:
                    target_option = (value, text, option)
                    print(f"Found target page size of 100!")
                    break
            
            # If 100 not available, use the maximum available
            if not target_option:
                target_option = available_options[-1]  # Last (highest) value
                print(f"100 not available, using maximum: {target_option[0]}")
            
            max_value, option_text, max_option = target_option
            
            # Only proceed if the target is larger than current
            if max_value > (current_page_size or 0):
                print(f"Changing page size from {current_page_size} to {max_value} records per page")
                
                try:
                    # Use multiple methods to ensure the change is applied
                    success_methods = []
                    
                    # Method 1: Direct click on option
                    try:
                        max_option.click()
                        success_methods.append("direct_click")
                    except Exception as e:
                        print(f"Direct click failed: {e}")
                    
                    # Method 2: JavaScript selection with comprehensive event triggering
                    try:
                        self.driver.execute_script("""
                            var select = arguments[0];
                            var value = arguments[1];
                            
                            // Set the value
                            select.value = value;
                            
                            // Trigger comprehensive events
                            var events = ['input', 'change', 'blur', 'click'];
                            events.forEach(function(eventType) {
                                var event = new Event(eventType, { bubbles: true, cancelable: true });
                                select.dispatchEvent(event);
                            });
                            
                            // Also trigger jQuery events if available
                            if (typeof jQuery !== 'undefined' && jQuery(select).length) {
                                jQuery(select).trigger('change').trigger('blur');
                            }
                            
                            // Try onchange handler if exists
                            if (select.onchange) {
                                select.onchange();
                            }
                            
                            // Try to submit parent form if exists
                            var form = select.closest('form');
                            if (form && form.onsubmit) {
                                // Don't actually submit, just trigger the handler
                                try { form.onsubmit(); } catch(e) {}
                            }
                        """, select_element, str(max_value))
                        success_methods.append("javascript_comprehensive")
                    except Exception as e:
                        print(f"JavaScript method failed: {e}")
                    
                    print(f"Applied page size change using methods: {success_methods}")
                    
                    # Wait for the page to refresh after changing page size
                    print("Waiting for table to refresh after page size change...")
                    time.sleep(8)  # Longer wait for larger datasets
                    
                    # Check for page refresh indicators
                    try:
                        # Method 1: Wait for stale element (indicates page refresh)
                        WebDriverWait(self.driver, 15).until(EC.staleness_of(select_element))
                        print("Page refresh detected via stale element")
                    except TimeoutException:
                        print("No stale element detected, checking other refresh indicators...")
                        
                        # Method 2: Check if table content changed significantly
                        try:
                            tables = self.driver.find_elements(By.TAG_NAME, "table")
                            for table in tables:
                                rows = table.find_elements(By.TAG_NAME, "tr")
                                if len(rows) > 50:  # If we see many more rows, page size likely changed
                                    print(f"Detected larger table with {len(rows)} rows - page size change likely successful")
                                    break
                        except Exception as e:
                            print(f"Could not check table size: {e}")
                    
                    # Wait for new table to be present and stable
                    try:
                        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
                        time.sleep(3)  # Additional stability wait
                        print("New table loaded after page size change")
                    except TimeoutException:
                        print("Warning: Table not detected after page size change")
                    
                    # Verify the change was successful
                    verification_success = False
                    try:
                        # Try to find the select element again and check its value
                        new_select = None
                        for selector in page_size_selectors:
                            try:
                                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                                if elements:
                                    new_select = elements[0]
                                    break
                            except:
                                continue
                        
                        if new_select:
                            new_value = int(new_select.get_attribute("value"))
                            print(f"Page size after change: {new_value}")
                            if new_value == max_value:
                                verification_success = True
                                print(f"✓ Successfully changed page size to {new_value}")
                            else:
                                print(f"Page size verification failed: expected {max_value}, got {new_value}")
                        else:
                            print("Could not find page size selector for verification")
                    except Exception as verify_error:
                        print(f"Could not verify page size change: {verify_error}")
                    
                    # Return True if we applied methods successfully, even if verification failed
                    return len(success_methods) > 0 or verification_success
                        
                except Exception as e:
                    print(f"Error selecting page size: {e}")
                    return False
            else:
                print(f"Target page size {max_value} is not larger than current {current_page_size}")
                return False
                
        except Exception as e:
            print(f"Error setting max page size: {e}")
            traceback.print_exc()
            return False
      
    def save_incremental_data(self, page_data, current_page):
        """
        Add data from a single page to the combined data structure
        
        Args:
            page_data (list): List of records from the current page
            current_page (int): Current page number
        """
        if not page_data:
            print(f"No data to save for page {current_page}")
            return
        
        # Update the combined data structure
        self.combined_data['evaluation_data'].extend(page_data)
        self.combined_data['page_info']['total_pages'] = max(current_page, self.combined_data['page_info']['total_pages'])
        self.combined_data['page_info']['total_records'] = len(self.combined_data['evaluation_data'])
        
        # Save the updated combined data to JSON and CSV
        json_filename = f"{self.base_filename}.json"
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(self.combined_data, f, indent=2, ensure_ascii=False)
        # Save or update the CSV file
        csv_filename = f"{self.base_filename}.csv"
        df = pd.DataFrame(self.combined_data['evaluation_data'])
        df.to_csv(csv_filename, index=False)
        
        print(f"✓ Page {current_page} data added to combined files: {json_filename} and {csv_filename} (Total: {len(self.combined_data['evaluation_data'])} records)")


# Example usage
if __name__ == "__main__":
    # Test with multiple URLs to demonstrate flexibility
    urls = [
        "https://course-evals.utoronto.ca/BPI/fbview.aspx?blockid=kTfZagKZMxZWpUF6Ou",  # Faculty of Applied Science & Engineering (Graduate)
        "https://course-evals.utoronto.ca/BPI/fbview.aspx?blockid=J3BZ4LNpJW9g4hRs1u",  # Faculty of Applied Science & Engineering (Undergraduate)
        "https://course-evals.utoronto.ca/BPI/fbview.aspx?blockid=EyDZtY6EMQEiMbkuuu",  # Faculty of Arts & Science (Undergraduate)
        "https://course-evals.utoronto.ca/BPI/fbview.aspx?blockid=1KZMor95HdQEJAxPIu",  # Dalla Lana School of Public Health (Graduate)
        "https://course-evals.utoronto.ca/BPI/fbview.aspx?blockid=PpNZa5Z5J-vsumbEJu",  # Faculty of Information (Graduate)
        "https://course-evals.utoronto.ca/BPI/fbview.aspx?blockid=JUQZzhjkpV_vJLo_Yu",  # Faculty of Information (Undergraduate)
        "https://course-evals.utoronto.ca/BPI/fbview.aspx?blockid=649MtMlNtiaQpFT0ou",  # Faculty of Nursing (Graduate)
        "https://course-evals.utoronto.ca/BPI/fbview.aspx?blockid=0zcMSZH0gdFSM23lDu",  # Faculty of Nursing (Undergraduate)
        "https://course-evals.utoronto.ca/BPI/fbview.aspx?blockid=pLxMMsJsuCScpZyo4u",  # Rotman School of Management (Graduate)
        "https://course-evals.utoronto.ca/BPI/fbview.aspx?blockid=keAZ9E3HJwletmKJju",  # Factor-Inwentash School Of Social Work
        "https://course-evals.utoronto.ca/BPI/fbview.aspx?blockid=JrVZ4758JVxAggdMLu",  # UT Mississauga (Undergraduate)
        "https://course-evals.utoronto.ca/BPI/fbview.aspx?blockid=DWXMtjqntQ0CuFq5_u",  # UT Scarborough (Graduate)
        "https://course-evals.utoronto.ca/BPI/fbview.aspx?blockid=06hZnPtQJdcYZAV8ru",  # UT Scarborough (Undergraduate)
    ]
    
    print("University of Toronto Course Evaluation Scraper - Enhanced Version")
    print("=" * 60)
    
    for i, url in enumerate(urls, 1):
        print(f"\n--- Testing URL {i}/{len(urls)} ---")
        print(f"URL: {url}")
        
        # Create scraper instance
        with UofTCourseEvaluationScraper(headless=False) as scraper:  # max_pages parameter removed as it's no longer used
            try:
                # Scrape course evaluation data
                result = scraper.scrape_course_evaluation(url)
                
                if result:
                    print(f"\nScraping completed successfully!")
                    print(f"Total pages scraped: {result['page_info']['total_pages']}")
                    print(f"Total records found: {result['page_info']['total_records']}")
                    
                    # Show table structure info
                    if 'table_structure' in result['page_info']:
                        structure = result['page_info']['table_structure']
                        print(f"Detected table structure:")
                        print(f"  - Total columns: {structure.get('total_columns', 'Unknown')}")
                        print(f"  - Division type: {structure.get('division_type', 'Unknown')}")
                        print(f"  - Has instructor ratings: {structure.get('has_instructor_ratings', False)}")
                        print(f"  - Has course ratings: {structure.get('has_course_ratings', False)}")
                        print(f"  - Has response counts: {structure.get('has_response_counts', False)}")
                    
                    # Save data with URL-specific filename
                    url_identifier = url.split('blockid=')[1][:10] if 'blockid=' in url else str(i)
                    filename = f"course_evaluation_{url_identifier}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    scraper.save_data(result, filename)
                    print(f"Data saved to files with base name: {filename}")
                else:
                    print("Failed to scrape course evaluation data")
                    
            except KeyboardInterrupt:
                print("\nScraping interrupted by user")
                break
            except Exception as e:
                print(f"Error during scraping: {e}")
                traceback.print_exc()
            finally:
                print("Scraping session ended for this URL")
    
    print("\nAll scraping sessions completed.")
