import requests
import os
import json
import re
import time
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("lsm_scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("LSMScraper")

class LSMScraper:
    """
    Scraper for the Learning Space Management (LSM) website at U of T,
    which extracts room information, images, and PDFs.
    """
    
    BASE_URL = "https://lsm.utoronto.ca/webapp/f?p=210:1::::::"
    DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloaded")
    
    # Common room number patterns based on sample files
    ROOM_PATTERNS = [
        # First floor rooms
        "1010", "1020", "1030", "1040", "1050", "1060", "1070", "1080", "1090", 
        "1100", "1110", "1120", "1130", "1140", "1150", "1160", "1170", "1180", "1190",
        # Second floor rooms
        "2010", "2020", "2030", "2040", "2050", "2060", "2070", "2080", "2090",
        "2100", "2110", "2120", "2130", "2140", "2150", "2160", "2170", "2175", "2180", "2190",
        # Common lecture halls with 3-digit numbers
        "100", "101", "102", "103", "104", "105", "110", "120", "130", "140", "150",
        "200", "201", "202", "203", "204", "205", "210", "220", "230", "240", "250",
        "300", "301", "302", "310", "320", "330", "340", "350",
        """Create necessary directories for downloaded files"""
        subdirs = ["images", "pdfs"]
        for subdir in subdirs:
            path = os.path.join(self.DOWNLOAD_DIR, subdir)
            if not os.path.exists(path):
                os.makedirs(path)
    
    def run(self):
        """Main method to run the scraper"""
        logger.info("Starting LSM scraper...")
        
        if self.use_local_files:
            logger.info("Using local sample HTML files")
            self.process_local_samples()
        else:
            logger.info("Scraping live website")
            self.scrape_live_website()
        
        # Save the dataset to room_information.json
        with open("room_information.json", 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2)
        
        logger.info("Scraping completed! Data saved to room_information.json")
    
    def process_local_samples(self):
        """Process the local sample HTML files"""
        # Process BA2175.html
        ba_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "BA2175.html")
        if os.path.exists(ba_path):
            logger.info(f"Processing sample file: {ba_path}")
            with open(ba_path, 'r', encoding='utf-8') as f:
                ba_html = f.read()
            self.process_sample_file("BA", "2175", ba_html)
        else:
            logger.error(f"Sample file not found: {ba_path}")
            
        # Process OI11200.html
        oi_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "OI11200.html")
        if os.path.exists(oi_path):
            logger.info(f"Processing sample file: {oi_path}")
            with open(oi_path, 'r', encoding='utf-8') as f:
                oi_html = f.read()
            self.process_sample_file("OI", "11200", oi_html)
        else:
            logger.error(f"Sample file not found: {oi_path}")
    
    def scrape_live_website(self):
        """Scrape data from the live website"""
        # Start with the main page to get all buildings
        try:
            logger.info("Fetching main page to extract all buildings...")
            all_buildings = self.extract_all_buildings()
            logger.info(f"Found {len(all_buildings)} buildings")
            
            for building_code, building_name in all_buildings.items():
                logger.info(f"Processing building: {building_code} - {building_name}")
                
                # For each building, get all rooms
                rooms = self.extract_rooms_for_building(building_code)
                
                if not rooms:
                    logger.warning(f"No rooms found for building {building_code}")
                    continue
                
                logger.info(f"Found {len(rooms)} rooms for {building_code}")
                
                for room_id in rooms:
                    logger.info(f"  - Processing room: {building_code} {room_id}")
                    html_content = self.get_room_page(building_code, room_id)
                    
                    if html_content:
                        self.process_sample_file(building_code, room_id, html_content)
                    else:
                        logger.warning(f"Failed to get content for {building_code} {room_id}")
                    
                    # Be nice to the server
                    time.sleep(1)
                
        except Exception as e:
            logger.error(f"Error in scrape_live_website: {e}")
    
    def extract_all_buildings(self):
        """Extract all building codes and names from the main page"""
        buildings = {}
        
        try:
            response = self.session.get(self.BASE_URL)
            if response.status_code != 200:
                logger.error(f"Failed to get main page: {response.status_code}")
                return buildings
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the building dropdown selector
            building_select = soup.find('select', {'id': 'P1_BLDG'})
            
            if not building_select:
                logger.error("Building selector not found on the page")
                return buildings
            
            # Process all building options
            for option in building_select.find_all('option'):
                value = option.get('value')
                text = option.text.strip()
                
                # Skip the "Select a Building" option
                if value and value != '%null%':
                    # The building code is usually the first part before the space
                    # For example: "BA Bahen Centre Information Tech" -> "BA"
                    code = value.split()[0] if ' ' in value else value
                    buildings[code] = text
            
        except Exception as e:
            logger.error(f"Error extracting buildings: {e}")
        
        return buildings
    
    def extract_rooms_for_building(self, building_code):
        """Extract all room IDs for a specific building"""
        rooms = []
        
        try:
            # Construct URL to view rooms for this building
            url = f"https://lsm.utoronto.ca/webapp/f?p=210:1::::P1_BLDG:{building_code}"
            response = self.session.get(url)
            
            if response.status_code != 200:
                logger.error(f"Failed to get rooms for building {building_code}: {response.status_code}")
                return rooms
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the room dropdown selector
            room_select = soup.find('select', {'id': 'P1_ROOM'})
            
            if not room_select:
                logger.error(f"Room selector not found for building {building_code}")
                return rooms
            
            # Process all room options
            for option in room_select.find_all('option'):
                value = option.get('value')
                
                # Skip the "Select a Room" option
                if value and value != '%null%':
                    # The room ID is the first part before any space
                    room_id = value.split()[0]
                    rooms.append(room_id)
            
        except Exception as e:
            logger.error(f"Error extracting rooms for building {building_code}: {e}")
        
        return rooms
    
    def get_room_page(self, building_code, room_id):
        """Get HTML content for a specific room"""
        try:
            # Direct URL to the room page
            url = f"https://lsm.utoronto.ca/webapp/f?p=210:1::::P1_BLDG,P1_ROOM:{building_code},{room_id}"
            
            response = self.session.get(url)
            if response.status_code != 200:
                logger.error(f"Failed to get page for {building_code} {room_id}: {response.status_code}")
                return None
            
            return response.text
            
        except Exception as e:
            logger.error(f"Error getting room page for {building_code} {room_id}: {e}")
            return None
    
    def process_sample_file(self, building_code, room_id, html_content):
        """Process HTML content for a room"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract room data
            room_data = self.extract_room_data(soup)
            if not room_data:
                logger.warning(f"No room data found for {building_code} {room_id}")
                return
            
            logger.info(f"Room data extracted for {building_code} {room_id}: {room_data}")
            
            # Save room data
            self.save_room_data(building_code, room_id, room_data)
            
            # Extract and download images
            image_urls = self.extract_image_urls(soup, building_code, room_id)
            if image_urls:
                logger.info(f"Found {len(image_urls)} images for {building_code} {room_id}")
                for i, img_url in enumerate(image_urls, 1):
                    self.download_image(img_url, building_code, room_id, i)
            else:
                logger.warning(f"No images found for {building_code} {room_id}")
            
            # Extract and download PDF
            pdf_url = self.extract_pdf_url(soup, building_code, room_id)
            if pdf_url:
                logger.info(f"Found PDF for {building_code} {room_id}")
                self.download_pdf(pdf_url, building_code, room_id)
            else:
                logger.warning(f"No PDF found for {building_code} {room_id}")
                
        except Exception as e:
            logger.error(f"Error processing HTML for {building_code} {room_id}: {e}")
    
    def extract_room_data(self, soup):
        """Extract room data from the page"""
        room_data = {}
        
        try:
            # Find all vertical1 tables which might contain room data
            vertical_tables = soup.find_all('table', {'class': 'vertical1'})
            
            for table in vertical_tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        # Check for cells with specific classes or positions
                        key_cell = None
                        value_cell = None
                        
                        # Try by class first
                        for cell in cells:
                            if 'L' in cell.get('class', []):
                                key_cell = cell
                            elif 'R' in cell.get('class', []):
                                value_cell = cell
                        
                        # If not found by class, use positional
                        if not (key_cell and value_cell) and len(cells) >= 2:
                            key_cell = cells[0]
                            value_cell = cells[1]
                        
                        if key_cell and value_cell:
                            key = key_cell.text.strip()
                            value = value_cell.text.strip()
                            
                            # Add all relevant fields, focusing on required ones
                            if key and value and key != " ":
                                # Check if this is a field we want
                                if key in ['Room Capacity', 'Testing Capacity', 'Seating Type', 
                                         'Writing Surface', 'Teaching station Type']:
                                    room_data[key] = value
            
        except Exception as e:
            logger.error(f"Error extracting room data: {e}")
        
        return room_data
    
    def extract_image_urls(self, soup, building_code, room_id):
        """Extract image URLs from the room page"""
        image_urls = []
        
        try:
            # Find all images in the page
            for img in soup.find_all('img'):
                if not img.has_attr('src'):
                    continue
                    
                src = img['src']
                # Look for room view images
                if 'RoomViews' in src:
                    # Make sure it's a full URL
                    full_url = src if src.startswith('http') else urljoin("https://lsm.utoronto.ca", src)
                    image_urls.append(full_url)
            
        except Exception as e:
            logger.error(f"Error extracting image URLs: {e}")
        
        return image_urls
    
    def extract_pdf_url(self, soup, building_code, room_id):
        """Extract PDF URL from the room page"""
        try:
            # Look for PDF links
            for a in soup.find_all('a', href=True):
                href = a['href']
                if 'RoomPlansPDF' in href and '.pdf' in href:
                    full_url = href if href.startswith('http') else urljoin("https://lsm.utoronto.ca", href)
                    return full_url
            
        except Exception as e:
            logger.error(f"Error extracting PDF URL: {e}")
        
        return None
    
    def download_image(self, url, building_code, room_id, img_num):
        """Download image file"""
        try:
            filename = f"{building_code}_{room_id}_{img_num}.jpg"
            filepath = os.path.join(self.DOWNLOAD_DIR, "images", filename)
            
            # Skip if already downloaded
            if os.path.exists(filepath):
                logger.info(f"Image already exists: {filename}")
                return
            
            # Download the image
            response = self.session.get(url, stream=True)
            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                logger.info(f"Downloaded image: {filename}")
            else:
                logger.error(f"Failed to download image {url}: {response.status_code}")
            
        except Exception as e:
            logger.error(f"Error downloading image {url}: {e}")
    
    def download_pdf(self, url, building_code, room_id):
        """Download PDF file"""
        try:
            filename = f"{building_code}{room_id}.pdf"
            filepath = os.path.join(self.DOWNLOAD_DIR, "pdfs", filename)
            
            # Skip if already downloaded
            if os.path.exists(filepath):
                logger.info(f"PDF already exists: {filename}")
                return
            
            # Download the PDF
            response = self.session.get(url, stream=True)
            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                logger.info(f"Downloaded PDF: {filename}")
            else:
                logger.error(f"Failed to download PDF {url}: {response.status_code}")
            
        except Exception as e:
            logger.error(f"Error downloading PDF {url}: {e}")
    
    def save_room_data(self, building_code, room_id, room_data):
        """Add room data to the main dictionary"""
        # Add to master dataset
        if building_code not in self.data:
            self.data[building_code] = {}
        
        self.data[building_code][room_id] = room_data
        logger.info(f"Added data for {building_code} {room_id} to the dataset")

if __name__ == "__main__":
    # Set use_local_files to False to scrape from the live website
    scraper = LSMScraper(use_local_files=False)
    scraper.run()
