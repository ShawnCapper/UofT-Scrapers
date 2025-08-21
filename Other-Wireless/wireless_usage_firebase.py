"""
UofT Wireless Usage Scraper
Scrapes current wireless device usage from https://status.wireless.utoronto.ca/
and saves the data to Firebase Realtime Database.
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import csv
from datetime import datetime
import os
import sys
import time
import argparse
import logging
import firebase_admin  # type: ignore
from firebase_admin import credentials, db  # type: ignore
# Load environment variables from a .env file
from dotenv import load_dotenv  # type: ignore
load_dotenv()

# Configure logging
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# File handler keeps INFO and above
file_handler = logging.FileHandler('wireless_scraper.log')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

# Console/stream handler is quieter by default (WARNING+). Use --verbose to enable INFO on console.
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.WARNING)
stream_handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)
# Initialize Firebase Admin SDK
firebase_cred_path = os.environ.get('FIREBASE_CREDENTIAL_PATH')
firebase_db_url = os.environ.get('FIREBASE_DATABASE_URL')
if firebase_cred_path and firebase_db_url:
    try:
        cred = credentials.Certificate(firebase_cred_path)
        firebase_admin.initialize_app(cred, {'databaseURL': firebase_db_url})
        logger.info("Initialized Firebase Admin SDK")
    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin: {e}")
else:
    logger.warning("Firebase credentials or database URL not set; Firebase disabled")

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

    def build_combined_record(self, usage_data, timestamp=None):
        """Build a single combined record containing only now_usage for St. George, UTM, and UTSC.

        Returns a dict suitable for DataFrame(list(...)) with one entry.
        """
        # Normalize keys and search for campus variants
        def find_usage(keywords):
            for k, v in usage_data.items():
                if not k:
                    continue
                kn = k.upper()
                if any(kw in kn for kw in keywords):
                    return v.get('now_usage') if isinstance(v, dict) else None
            return None

        if timestamp is None:
            # try to find timestamp from any campus entry
            timestamp = None
            for v in usage_data.values():
                if isinstance(v, dict) and 'timestamp' in v:
                    timestamp = v['timestamp']
                    break
            if timestamp is None:
                from datetime import datetime
                timestamp = datetime.now()

        record = {
            'timestamp': timestamp,
            'st_george_now': find_usage(['GEORGE', 'ST.GEORGE', 'ST. GEORGE']),
            'utm_now': find_usage(['UTM']),
            'utsc_now': find_usage(['UTSC'])
        }

        return {'combined': record}

    def print_combined_to_console(self, stg, utm, utsc, timestamp=None):
        """Print a single timestamped INFO-formatted line to console with per-campus now_usage."""
        from datetime import datetime
        ts = timestamp or datetime.now()
        # Format timestamp with milliseconds to match logging format: YYYY-mm-dd HH:MM:SS,mmm
        ms = int(ts.microsecond / 1000)
        timestr = ts.strftime('%Y-%m-%d %H:%M:%S') + f',{ms:03d}'
        print(f"{timestr} - INFO - Per-campus now_usage -> StGeorge: {stg}, UTM: {utm}, UTSC: {utsc}")
    
    def save_to_csv(self, usage_data, filename=None):
        """Save usage data to CSV file"""
        if not usage_data:
            logger.warning("No data to save")
            return
        # Default to single historical file in data/ so each run appends to the same file
        if filename is None:
            filename = "data/wireless_usage_historical.csv"

        # Ensure data directory exists
        os.makedirs('data', exist_ok=True)
        filepath = filename

        # Convert to DataFrame for easy CSV writing
        df = pd.DataFrame(list(usage_data.values()))

        # Determine columns to write. Support both legacy per-campus rows and
        # the new combined single-row format which contains only now_usage for
        # St. George, UTM, and UTSC.
        if any(col in df.columns for col in ('st_george_now', 'utm_now', 'utsc_now')):
            column_order = ['timestamp', 'st_george_now', 'utm_now', 'utsc_now']
        else:
            # Reorder columns for legacy format
            column_order = ['timestamp', 'campus', 'now_usage', 'now_percentage', 
                           'daily_peak', 'weekly_peak', 'monthly_peak', 
                           'yearly_peak', 'yearly_percentage']

        # Only include columns that exist in the DataFrame
        existing_columns = [col for col in column_order if col in df.columns]
        df = df[existing_columns]

        # Append to historical file if it exists, otherwise create it with headers
        if os.path.exists(filepath):
            # Special handling for combined single-row CSV: if the existing file
            # doesn't have the expected combined headers, back it up and recreate
            # the file so headers are preserved.
            if any(col in df.columns for col in ('st_george_now', 'utm_now', 'utsc_now')):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        first_line = f.readline().strip()
                except Exception:
                    first_line = ''

                expected_headers = ','.join(column_order)
                # If headers don't match (or file contains a single "timestamp" header), backup and recreate
                if not all(h in first_line for h in ['st_george_now', 'utm_now', 'utsc_now']):
                    backup_path = filepath + '.bak'
                    try:
                        os.replace(filepath, backup_path)
                        logger.info(f"Backed up existing file to {backup_path} and will write new headers")
                    except Exception as e:
                        logger.warning(f"Could not backup existing file: {e}; will attempt to append without headers")
                        # Fall back to appending without header
                        df.to_csv(filepath, mode='a', header=False, index=False)
                    else:
                        # Write new file with headers
                        df.to_csv(filepath, index=False)
                else:
                    df.to_csv(filepath, mode='a', header=False, index=False)
            else:
                # Legacy behavior: append rows without headers
                df.to_csv(filepath, mode='a', header=False, index=False)
        else:
            # Create new file with headers
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

        # If combined single-row format, ensure we only write the combined columns
        if any(col in df.columns for col in ('st_george_now', 'utm_now', 'utsc_now')):
            cols = [c for c in ['timestamp', 'st_george_now', 'utm_now', 'utsc_now'] if c in df.columns]
            df = df[cols]
        
        # Check if historical file exists
        if os.path.exists(historical_file):
            # If combined-format and existing file doesn't have combined headers,
            # back it up and recreate so headers are present
            if any(col in df.columns for col in ('st_george_now', 'utm_now', 'utsc_now')):
                try:
                    with open(historical_file, 'r', encoding='utf-8') as f:
                        first_line = f.readline().strip()
                except Exception:
                    first_line = ''

                if not all(h in first_line for h in ['st_george_now', 'utm_now', 'utsc_now']):
                    backup_path = historical_file + '.bak'
                    try:
                        os.replace(historical_file, backup_path)
                        logger.info(f"Backed up existing historical file to {backup_path} and will write new headers")
                    except Exception as e:
                        logger.warning(f"Could not backup historical file: {e}; will attempt to append without headers")
                        df.to_csv(historical_file, mode='a', header=False, index=False)
                    else:
                        df.to_csv(historical_file, index=False)
                else:
                    df.to_csv(historical_file, mode='a', header=False, index=False)
            else:
                # Append to existing file
                df.to_csv(historical_file, mode='a', header=False, index=False)
        else:
            # Create new file with headers
            df.to_csv(historical_file, index=False)
        
        logger.info(f"Data appended to {historical_file}")
    
    def save_to_firebase(self, combined_data):
        """Save combined record to Firebase Realtime Database."""
        try:
            # Helper to convert non-JSON-serializable objects (like datetime)
            # into JSON-friendly types (ISO strings for datetimes).
            def _serialize_for_firebase(obj):
                from datetime import datetime, date
                if isinstance(obj, (datetime, date)):
                    return obj.isoformat()
                if isinstance(obj, dict):
                    return {k: _serialize_for_firebase(v) for k, v in obj.items()}
                if isinstance(obj, (list, tuple)):
                    return [_serialize_for_firebase(v) for v in obj]
                return obj

            ref = db.reference('wireless_usage')
            payload = combined_data.get('combined', combined_data)
            payload = _serialize_for_firebase(payload)
            ref.push(payload)
            logger.info("Data saved to Firebase")
        except Exception as e:
            logger.error(f"Error saving data to Firebase: {e}")
    
    def scrape_and_save(self):
        """Main method to scrape and save data"""
        try:
            # Fetch and parse data
            html_content = self.fetch_page()
            usage_data = self.parse_usage_data(html_content)
            
            if not usage_data:
                logger.error("No usage data found")
                return False

            # Build a single combined record with only the now_usage values
            combined = self.build_combined_record(usage_data)

            # Save the single-row combined data to Firebase
            self.save_to_firebase(combined)

            # Print summary for the three campuses we track
            stg = combined['combined'].get('st_george_now')
            utm = combined['combined'].get('utm_now')
            utsc = combined['combined'].get('utsc_now')
            total_devices = sum(x for x in (stg, utm, utsc) if x is not None)
            # Log full details to file
            logger.info("Successfully scraped combined data for St. George, UTM, UTSC")
            logger.info(f"Per-campus now_usage -> StGeorge: {stg}, UTM: {utm}, UTSC: {utsc}")
            logger.info(f"Total devices (sum of available values): {total_devices}")
            # Print only the single combined summary line to console
            try:
                self.print_combined_to_console(stg, utm, utsc, combined['combined'].get('timestamp'))
            except Exception:
                # Fallback to a simple print if formatting fails
                print(f"Per-campus now_usage -> StGeorge: {stg}, UTM: {utm}, UTSC: {utsc}")

            return True
            
        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            return False

def main():
    """Main function for command line usage"""
    parser = argparse.ArgumentParser(description='Wireless usage scraper runner')
    parser.add_argument('--continuous', action='store_true', help='Run continuously, minute-by-minute (default: run once)')
    parser.add_argument('--interval', type=int, default=60, help='Interval in seconds between scrapes when running continuously (default: 60)')
    parser.add_argument('--no-align', action='store_true', help='Do not align runs to the interval boundary (only relevant for continuous mode)')
    args = parser.parse_args()

    scraper = WirelessUsageScraper()

    # Keep console output minimal; we'll print a single combined INFO line below.

    # Default behavior: run once. Use --continuous to run minute-by-minute.
    if not args.continuous:
        success = scraper.scrape_and_save()
        if success:
            logger.info("Scraping completed successfully (once)")
            sys.exit(0)
        else:
            logger.error("Scraping failed (once)")
            sys.exit(1)

    # Continuous run (only entered when --continuous is provided)
    interval = max(1, args.interval)
    try:
        logger.info(f"Starting continuous scraping every {interval} seconds")
        while True:
            # Optionally align to wall-clock interval (e.g., start at top of minute)
            if not args.no_align:
                # Calculate seconds until next aligned boundary
                now = time.time()
                next_boundary = ((now // interval) + 1) * interval
                wait = next_boundary - now
                if wait > 0:
                    logger.info(f"Waiting {wait:.1f}s until next aligned run")
                    time.sleep(wait)

            start = time.time()
            try:
                scraper.scrape_and_save()
            except Exception as e:
                logger.error(f"Unhandled error during scrape: {e}")

            elapsed = time.time() - start
            # Sleep remaining time until next interval (only if not aligning above)
            if args.no_align:
                sleep_time = max(0, interval - elapsed)
                if sleep_time > 0:
                    logger.info(f"Sleeping {sleep_time:.1f}s until next run")
                    time.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, shutting down")
        sys.exit(0)

if __name__ == "__main__":
    main()
