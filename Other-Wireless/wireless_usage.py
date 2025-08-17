#!/usr/bin/env python3
"""
UofT Wireless Usage Scraper
Scrapes current wireless device usage from https://status.wireless.utoronto.ca/
and saves the data to CSV files.
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import csv
from datetime import datetime
import os
import sys
import time
import logging
import urllib3

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('wireless_scraper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class WirelessUsageScraper:
    def __init__(self):
        self.url = "https://status.wireless.utoronto.ca/"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        # Disable SSL verification for this specific site (common for university internal sites)
        self.session.verify = False
        # Suppress SSL warnings
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
    def fetch_page(self):
        """Fetch the wireless status page"""
        try:
            logger.info(f"Fetching data from {self.url}")
            response = self.session.get(self.url, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"Error fetching page: {e}")
            raise
    
    def parse_usage_data(self, html_content):
        """Parse the wireless usage data from HTML"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Look for the table with campus data
        tables = soup.find_all('table')
        usage_data = {}
        timestamp = datetime.now()
        
        for table in tables:
            rows = table.find_all('tr')
            if len(rows) < 2:
                continue
                
            # Check if this is the usage table by looking for campus names
            header_cells = rows[0].find_all(['th', 'td'])
            if len(header_cells) < 5:
                continue
                
            # Check if we have the right table structure
            header_text = [cell.get_text(strip=True).upper() for cell in header_cells]
            if 'CAMPUS' in header_text and 'NOW' in header_text:
                logger.info("Found usage data table")
                
                for row in rows[1:]:  # Skip header row
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 5:
                        campus = cells[0].get_text(strip=True)
                        now_usage = cells[1].get_text(strip=True)
                        daily_peak = cells[2].get_text(strip=True)
                        weekly_peak = cells[3].get_text(strip=True)
                        monthly_peak = cells[4].get_text(strip=True)
                        yearly_peak = cells[5].get_text(strip=True) if len(cells) > 5 else ""
                        
                        # Clean the data - extract numbers and percentages
                        now_clean = self.extract_number(now_usage)
                        daily_peak_clean = self.extract_number(daily_peak)
                        weekly_peak_clean = self.extract_number(weekly_peak)
                        monthly_peak_clean = self.extract_number(monthly_peak)
                        yearly_peak_clean = self.extract_number(yearly_peak)
                        
                        # Extract percentage if present
                        now_percentage = self.extract_percentage(now_usage)
                        yearly_percentage = self.extract_percentage(yearly_peak)
                        
                        if campus and now_clean is not None:
                            usage_data[campus] = {
                                'campus': campus,
                                'timestamp': timestamp,
                                'now_usage': now_clean,
                                'now_percentage': now_percentage,
                                'daily_peak': daily_peak_clean,
                                'weekly_peak': weekly_peak_clean,
                                'monthly_peak': monthly_peak_clean,
                                'yearly_peak': yearly_peak_clean,
                                'yearly_percentage': yearly_percentage
                            }
                            logger.info(f"Parsed data for {campus}: {now_clean} devices")
                break
        
        if not usage_data:
            # Fallback: try to find data in a different format
            logger.warning("Standard table not found, trying alternative parsing")
            usage_data = self.parse_alternative_format(soup, timestamp)
        
        return usage_data
    
    def parse_alternative_format(self, soup, timestamp):
        """Alternative parsing method for different HTML structure"""
        usage_data = {}
        
        # Look for specific campus names and nearby numbers
        text_content = soup.get_text()
        lines = text_content.split('\n')
        
        current_data = {}
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Look for campus indicators
            if any(campus in line.upper() for campus in ['ST.GEORGE', 'ST. GEORGE', 'UTM', 'UTSC', 'TOTAL']):
                # Try to extract numbers from this line and surrounding lines
                campus_name = line
                for j in range(max(0, i-2), min(len(lines), i+3)):
                    check_line = lines[j].strip()
                    numbers = self.extract_all_numbers(check_line)
                    if numbers:
                        # Assume first number is current usage
                        current_data[campus_name] = {
                            'campus': campus_name,
                            'timestamp': timestamp,
                            'now_usage': numbers[0],
                            'now_percentage': None,
                            'daily_peak': numbers[1] if len(numbers) > 1 else None,
                            'weekly_peak': numbers[2] if len(numbers) > 2 else None,
                            'monthly_peak': numbers[3] if len(numbers) > 3 else None,
                            'yearly_peak': numbers[4] if len(numbers) > 4 else None,
                            'yearly_percentage': None
                        }
                        break
        
        return current_data
    
    def extract_number(self, text):
        """Extract the first number from text"""
        import re
        if not text:
            return None
        # Remove commas and extract first number
        numbers = re.findall(r'[\d,]+', text.replace(',', ''))
        return int(numbers[0]) if numbers else None
    
    def extract_percentage(self, text):
        """Extract percentage from text"""
        import re
        if not text:
            return None
        percentages = re.findall(r'(\d+\.?\d*)%', text)
        return float(percentages[0]) if percentages else None
    
    def extract_all_numbers(self, text):
        """Extract all numbers from text"""
        import re
        if not text:
            return []
        numbers = re.findall(r'\d+', text.replace(',', ''))
        return [int(num) for num in numbers]
    
    def save_to_csv(self, usage_data, filename=None):
        """Save usage data to CSV file"""
        if not usage_data:
            logger.warning("No data to save")
            return
        
        if filename is None:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"wireless_usage_{timestamp_str}.csv"
        
        # Ensure data directory exists
        os.makedirs('data', exist_ok=True)
        filepath = os.path.join('data', filename)
        
        # Convert to DataFrame for easy CSV writing
        df = pd.DataFrame(list(usage_data.values()))
        
        # Reorder columns
        column_order = ['timestamp', 'campus', 'now_usage', 'now_percentage', 
                       'daily_peak', 'weekly_peak', 'monthly_peak', 
                       'yearly_peak', 'yearly_percentage']
        
        # Only include columns that exist
        existing_columns = [col for col in column_order if col in df.columns]
        df = df[existing_columns]
        
        df.to_csv(filepath, index=False)
        logger.info(f"Data saved to {filepath}")
        
        return filepath
    
    def append_to_historical_csv(self, usage_data, historical_file="data/wireless_usage_historical.csv"):
        """Append current data to historical CSV file"""
        if not usage_data:
            return
        
        os.makedirs('data', exist_ok=True)
        
        # Convert to DataFrame
        df = pd.DataFrame(list(usage_data.values()))
        
        # Check if historical file exists
        if os.path.exists(historical_file):
            # Append to existing file
            df.to_csv(historical_file, mode='a', header=False, index=False)
        else:
            # Create new file with headers
            df.to_csv(historical_file, index=False)
        
        logger.info(f"Data appended to {historical_file}")
    
    def scrape_and_save(self):
        """Main method to scrape and save data"""
        try:
            # Fetch and parse data
            html_content = self.fetch_page()
            usage_data = self.parse_usage_data(html_content)
            
            if not usage_data:
                logger.error("No usage data found")
                return False
            
            # Save data
            timestamp_file = self.save_to_csv(usage_data)
            self.append_to_historical_csv(usage_data)
            
            # Print summary
            total_devices = sum(data['now_usage'] for data in usage_data.values() 
                              if data['now_usage'] is not None)
            logger.info(f"Successfully scraped data for {len(usage_data)} campuses")
            logger.info(f"Total devices: {total_devices}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            return False

def main():
    """Main function for command line usage"""
    scraper = WirelessUsageScraper()
    
    if scraper.scrape_and_save():
        logger.info("Scraping completed successfully")
        sys.exit(0)
    else:
        logger.error("Scraping failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
