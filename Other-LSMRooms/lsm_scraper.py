import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
import time
import os
from urllib.parse import urljoin, urlparse
import logging
from typing import Dict, List, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from pathlib import Path

class ComprehensiveLSMScraper:
    """
    Web scraper for University of Toronto LSM system
    Extracts room images, layouts, and details
    """
    
    def __init__(self, output_dir: str = "lsm_data"):
        self.base_url = "https://lsm.utoronto.ca"
        self.main_url = "https://lsm.utoronto.ca/webapp/f?p=210:1"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Setup output directory structure
        self.output_dir = Path(output_dir)
        self.images_dir = self.output_dir / "images"
        self.pdfs_dir = self.output_dir / "layouts" 
        self.data_dir = self.output_dir / "html_files"
        self.buildings_dir = self.output_dir / "details"
        
        # Create directories
        for dir_path in [self.output_dir, self.images_dir, self.pdfs_dir, self.data_dir, self.buildings_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.output_dir / 'lsm_scraper.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        self.scraped_data = {
            'buildings': [],
            'detailed_rooms': []
        }
    
    def setup_selenium_driver(self):
        """Setup Selenium Chrome driver with options"""
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        return webdriver.Chrome(service=service, options=options)
    
    def download_file(self, url: str, filename: str, file_type: str = "image") -> bool:
        """Download a file (image or PDF) and save it"""
        try:
            if not url.startswith('http'):
                url = urljoin(self.base_url, url)
                
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # Determine save directory
            save_dir = self.images_dir if file_type == "image" else self.pdfs_dir
            file_path = save_dir / filename
            
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            self.logger.info(f"Downloaded {file_type}: {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error downloading {url}: {e}")
            return False
    
    def scrape_main_page(self) -> Dict:
        """Scrape the main LSM page for building information"""
        self.logger.info("Scraping main LSM page...")
        
        try:
            response = self.session.get(self.main_url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
        except Exception as e:
            self.logger.error(f"Error fetching main page: {e}")
            return self.scraped_data
        
        # Extract building dropdown options
        building_select = soup.find('select', {'name': 'P1_BLDG'}) or soup.find('select', {'id': 'P1_BLDG'})
        if building_select:
            buildings = []
            for option in building_select.find_all('option'):
                value = option.get('value', '').strip()
                text = option.text.strip()
                if value and value != '%null%' and text and 'Select a Building' not in text:
                    buildings.append({
                        'code': value,
                        'name': text
                    })
            self.scraped_data['buildings'] = buildings
            self.logger.info(f"Found {len(buildings)} buildings")
        
        return self.scraped_data
    
    def get_rooms_for_building(self, building_code: str) -> List[Dict]:
        """Get available rooms for a specific building using Selenium"""
        self.logger.info(f"Getting rooms for building: {building_code}")
        driver = self.setup_selenium_driver()
        
        try:
            driver.get(self.main_url)
            
            # Wait for and select building
            building_select_element = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "select[name='P1_BLDG']"))
            )
            
            building_select = Select(building_select_element)
            building_select.select_by_value(building_code)
            
            # Wait for room dropdown to populate
            time.sleep(3)
            
            room_select_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "select[name='P1_ROOM']"))
            )
            
            room_options = room_select_element.find_elements(By.TAG_NAME, "option")
            rooms = []
            
            for option in room_options:
                value = option.get_attribute("value")
                text = option.text.strip()
                if value and value != '%null%' and text and 'Select a Room' not in text:
                    rooms.append({
                        'code': value,
                        'name': text
                    })
            
            self.logger.info(f"Found {len(rooms)} rooms for building {building_code}")
            return rooms
            
        except Exception as e:
            self.logger.error(f"Error getting rooms for building {building_code}: {e}")
            return []
        finally:
            driver.quit()
    
    def scrape_room_details(self, building_code: str, room_code: str) -> Dict:
        """Scrape room details"""
        self.logger.info(f"Scraping detailed room info for {building_code}-{room_code}")
        driver = self.setup_selenium_driver()
        
        try:
            driver.get(self.main_url)
            
            # Select building and room
            building_select = Select(WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "select[name='P1_BLDG']"))
            ))
            building_select.select_by_value(building_code)
            time.sleep(2)
            
            room_select = Select(WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "select[name='P1_ROOM']"))
            ))
            room_select.select_by_value(room_code)
            time.sleep(3)
            
            # Get page source and parse
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Initialize room details
            room_details = {
                'building_code': building_code,
                'room_code': room_code,
                'building_info': {},
                'room_specifications': {},
                'accessibility': {},
                'images': [],
                'floor_plan_pdf': None,
                'raw_html_saved': False
            }
            
            # Extract building information
            building_info = self.extract_building_info(soup)
            room_details['building_info'] = building_info
            
            # Extract room specifications
            specifications = self.extract_room_specifications(soup)
            room_details['room_specifications'] = specifications
            
            # Extract accessibility information
            accessibility = self.extract_accessibility_info(soup)
            room_details['accessibility'] = accessibility
            
            # Download images
            images = self.extract_and_download_images(soup, building_code, room_code)
            room_details['images'] = images
            
            # Download floor plan PDF
            pdf_info = self.extract_and_download_pdf(soup, building_code, room_code)
            room_details['floor_plan_pdf'] = pdf_info
            
            # Save raw HTML for reference
            html_filename = f"{building_code}_{room_code}_raw.html"
            html_path = self.data_dir / html_filename
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            room_details['raw_html_saved'] = str(html_path)
            
            return room_details
            
        except Exception as e:
            self.logger.error(f"Error scraping room details for {building_code}-{room_code}: {e}")
            return {}
        finally:
            driver.quit()
    
    def extract_building_info(self, soup: BeautifulSoup) -> Dict:
        """Extract building information from soup"""
        building_info = {
            'name': '',
            'address': '',
            'building_image': None
        }
        
        # Find building photo and address
        building_table = soup.find('table', {'aria-label': 'Building  Image'})
        if building_table:
            # Extract address
            addr_cell = building_table.find('td', {'headers': 'ADDR'})
            if addr_cell:
                building_info['address'] = addr_cell.get_text(strip=True).replace('<br>', '\n')
            
            # Extract building image
            photo_cell = building_table.find('td', {'headers': 'PHOTO'})
            if photo_cell:
                img_link = photo_cell.find('a')
                if img_link and img_link.get('href'):
                    img_url = img_link.get('href')
                    building_info['building_image'] = img_url
        
        return building_info
    
    def extract_room_specifications(self, soup: BeautifulSoup) -> Dict:
        """Extract room specifications"""
        specs = {
            'room_capacity': '',
            'testing_capacity': '',
            'seating_type': '',
            'writing_surface': '',
            'teaching_station_type': ''
        }
        
        # Find the room specifications table
        spec_tables = soup.find_all('table', class_='vertical1')
        for table in spec_tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    
                    if 'Room Capacity' in label:
                        specs['room_capacity'] = value
                    elif 'Testing Capacity' in label:
                        specs['testing_capacity'] = value
                    elif 'Seating Type' in label:
                        specs['seating_type'] = value
                    elif 'Writing Surface' in label:
                        specs['writing_surface'] = value
                    elif 'Teaching station Type' in label or 'Teaching Station Type' in label:
                        specs['teaching_station_type'] = value
        
        return specs
    
    def extract_accessibility_info(self, soup: BeautifulSoup) -> Dict:
        """Extract accessibility information"""
        accessibility = {
            'building_exterior': {},
            'building_entrance': {},
            'elevators': {},
            'washrooms': {},
            'room': {}
        }
        
        # Find all accessibility sections by looking for headers
        accessibility_sections = soup.find_all('td', class_='t3RegionHeader2')
        
        for section in accessibility_sections:
            header_text = section.get_text(strip=True)
            
            # Map headers to categories
            category = None
            if 'Building Exterior' in header_text:
                category = 'building_exterior'
            elif 'Building Entrance' in header_text:
                category = 'building_entrance'
            elif 'Elevators' in header_text:
                category = 'elevators'
            elif 'Washrooms' in header_text:
                category = 'washrooms'
            elif 'Room' in header_text and 'Accessibility' in header_text:
                category = 'room'
            
            if category:
                # Find the corresponding data table
                parent_table = section.find_parent('table')
                if parent_table:
                    next_row = parent_table.find_next_sibling('tr')
                    if next_row:
                        data_table = next_row.find('table', class_='vertical1')
                        if data_table:
                            category_data = {}
                            rows = data_table.find_all('tr')
                            for row in rows:
                                cells = row.find_all('td')
                                if len(cells) >= 2 and cells[0].get('class') == ['L']:
                                    question = cells[0].get_text(strip=True)
                                    answer = cells[1].get_text(strip=True)
                                    if question and answer:  # Only add non-empty entries
                                        category_data[question] = answer
                            accessibility[category] = category_data
        
        return accessibility
    
    def extract_and_download_images(self, soup: BeautifulSoup, building_code: str, room_code: str) -> List[Dict]:
        """Extract and download room images"""
        images = []
        
        # Find room image table
        room_image_table = soup.find('table', {'aria-label': 'Room Image'})
        if room_image_table:
            img_links = room_image_table.find_all('a', href=True)
            
            for i, link in enumerate(img_links, 1):
                img_url = link.get('href')
                if img_url and ('RoomViews' in img_url or '.JPG' in img_url or '.jpg' in img_url):
                    # Extract original filename and create a proper filename
                    original_name = os.path.basename(img_url)
                    img_filename = f"{building_code}_{room_code}_view{i}_{original_name}"
                    
                    # Download image
                    if self.download_file(img_url, img_filename, "image"):
                        images.append({
                            'filename': img_filename,
                            'url': img_url,
                            'view_number': i,
                            'local_path': str(self.images_dir / img_filename)
                        })
        
        return images
    
    def extract_and_download_pdf(self, soup: BeautifulSoup, building_code: str, room_code: str) -> Optional[Dict]:
        """Extract and download floor plan PDF"""
        # Find PDF link
        pdf_links = soup.find_all('a', href=lambda href: href and '.pdf' in href.lower())
        
        for link in pdf_links:
            pdf_url = link.get('href')
            if pdf_url and ('RoomPlansPDF' in pdf_url or 'floor' in pdf_url.lower() or 'plan' in pdf_url.lower()):
                # Create filename
                original_name = os.path.basename(pdf_url)
                pdf_filename = f"{building_code}_{room_code}_floorplan_{original_name}"
                
                # Download PDF
                if self.download_file(pdf_url, pdf_filename, "pdf"):
                    return {
                        'filename': pdf_filename,
                        'url': pdf_url,
                        'local_path': str(self.pdfs_dir / pdf_filename)
                    }
        
        return None
    
    def scrape_all_buildings_and_rooms(self) -> None:
        """Scrape all buildings and their rooms"""
        self.logger.info("Starting scrape of all buildings and rooms...")
        
        # First get all buildings
        self.scrape_main_page()
        
        all_detailed_rooms = []
        
        for building in self.scraped_data['buildings']:
            building_code = building['code']
            self.logger.info(f"Processing building: {building_code} - {building['name']}")
            
            # Get rooms for this building
            rooms = self.get_rooms_for_building(building_code)
            
            # Create building directory
            building_dir = self.buildings_dir / building_code
            building_dir.mkdir(parents=True, exist_ok=True)
            
            # Save building info
            building_data = {
                'building_info': building,
                'rooms': rooms,
                'total_rooms': len(rooms)
            }
            
            with open(building_dir / 'building_info.json', 'w', encoding='utf-8') as f:
                json.dump(building_data, f, indent=2, ensure_ascii=False)
            
            # Scrape details for each room
            for room in rooms:
                room_code = room['code']
                try:
                    room_details = self.scrape_room_details(building_code, room_code)
                    if room_details:
                        all_detailed_rooms.append(room_details)
                        
                        # Save individual room data
                        room_filename = f"room_{building_code}_{room_code}.json"
                        with open(building_dir / room_filename, 'w', encoding='utf-8') as f:
                            json.dump(room_details, f, indent=2, ensure_ascii=False)
                        
                        self.logger.info(f"Completed scraping {building_code}-{room_code}")
                    
                    # Be respectful to the server
                    time.sleep(2)
                    
                except Exception as e:
                    self.logger.error(f"Error processing room {building_code}-{room_code}: {e}")
                    continue
        
        # Save comprehensive data
        self.scraped_data['detailed_rooms'] = all_detailed_rooms
        
        # Save master data file
        with open(self.output_dir / 'complete_lsm_data.json', 'w', encoding='utf-8') as f:
            json.dump(self.scraped_data, f, indent=2, ensure_ascii=False)
        
        # Create summary files
        self.create_summary_files()
        
        self.logger.info("Comprehensive scraping completed!")
    
    def create_summary_files(self) -> None:
        """Create summary CSV files for easy analysis"""
        if not self.scraped_data['detailed_rooms']:
            return
        
        # Room specifications summary
        room_specs = []
        for room in self.scraped_data['detailed_rooms']:
            spec_row = {
                'building_code': room['building_code'],
                'room_code': room['room_code'],
                'building_name': room['building_info'].get('name', ''),
                'address': room['building_info'].get('address', ''),
                **room['room_specifications'],
                'has_images': len(room['images']) > 0,
                'has_floor_plan': room['floor_plan_pdf'] is not None,
                'image_count': len(room['images'])
            }
            room_specs.append(spec_row)
        
        specs_df = pd.DataFrame(room_specs)
        specs_df.to_csv(self.output_dir / 'room_specifications_summary.csv', index=False)
        
        # Accessibility summary
        accessibility_rows = []
        for room in self.scraped_data['detailed_rooms']:
            for category, data in room['accessibility'].items():
                for question, answer in data.items():
                    accessibility_rows.append({
                        'building_code': room['building_code'],
                        'room_code': room['room_code'],
                        'category': category,
                        'question': question,
                        'answer': answer
                    })
        
        if accessibility_rows:
            access_df = pd.DataFrame(accessibility_rows)
            access_df.to_csv(self.output_dir / 'accessibility_summary.csv', index=False)
        
        self.logger.info("Summary CSV files created")
    
    def scrape_single_room(self, building_code: str, room_code: str) -> Dict:
        """Scrape a single room for testing"""
        room_data = self.scrape_room_details(building_code, room_code)
        
        if room_data:
            # Save the room data
            filename = f"single_room_{building_code}_{room_code}.json"
            with open(self.output_dir / filename, 'w', encoding='utf-8') as f:
                json.dump(room_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Single room data saved to {filename}")
        
        return room_data

    def cleanup(self):
        """Clean up selenium driver if it exists"""
        if hasattr(self, 'driver') and self.driver:
            try:
                self.driver.quit()
                self.logger.info("Selenium driver closed successfully")
            except Exception as e:
                self.logger.error(f"Error closing selenium driver: {e}")

if __name__ == "__main__":
    scraper = ComprehensiveLSMScraper()
    
    print("LSM Comprehensive Scraper")
    print("=" * 40)
    print("Starting comprehensive scrape of all buildings and rooms...")
    
    try:
        scraper.scrape_all_buildings_and_rooms()
        print("Comprehensive scrape completed successfully!")
    except Exception as e:
        print(f"Error during scraping: {e}")
    finally:
        scraper.cleanup()
