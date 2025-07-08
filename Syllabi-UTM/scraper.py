import os
import csv
import time
from urllib.parse import urlparse
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def sanitize_filename(filename):
    """Remove or replace characters that are not allowed in filenames"""
    # Replace problematic characters with underscores
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove extra spaces and replace with single underscore
    filename = re.sub(r'\s+', '_', filename)
    return filename

def setup_chrome_driver(download_folder):
    """Set up Chrome driver with download preferences"""
    chrome_options = Options()
    
    # Set download preferences
    prefs = {
        "download.default_directory": download_folder,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "plugins.always_open_pdf_externally": True  # Disable PDF viewer
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    # Disable PDF viewer plugin
    chrome_options.add_argument("--disable-plugins-discovery")
    chrome_options.add_argument("--disable-web-security")
    
    # Optional: run headless (comment out if you want to see the browser)
    # chrome_options.add_argument("--headless")
    
    # Set up the driver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    return driver

def wait_for_download_completion(download_folder, timeout=30):
    """Wait for download to complete by checking for .crdownload files"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        # Check if there are any .crdownload files (incomplete downloads)
        temp_files = [f for f in os.listdir(download_folder) if f.endswith('.crdownload')]
        if not temp_files:
            time.sleep(1)  # Give it a moment to ensure download is complete
            return True
        time.sleep(1)
    return False

def rename_downloaded_file(download_folder, expected_filename, timeout=10):
    """Find and rename the most recently downloaded file"""
    start_time = time.time()
    initial_files = set(os.listdir(download_folder))
    
    while time.time() - start_time < timeout:
        current_files = set(os.listdir(download_folder))
        new_files = current_files - initial_files
        
        if new_files:
            # Get the most recently downloaded file
            newest_file = max([os.path.join(download_folder, f) for f in new_files], 
                            key=os.path.getctime)
            newest_filename = os.path.basename(newest_file)
            
            # Skip temporary files
            if not newest_filename.endswith('.crdownload'):
                try:
                    new_path = os.path.join(download_folder, expected_filename)
                    os.rename(newest_file, new_path)
                    return True
                except Exception as e:
                    print(f"Error renaming file: {str(e)}")
                    return False
        time.sleep(0.5)
    
    return False

def check_if_pdf_viewer_opened(driver):
    """Check if Chrome PDF viewer is showing instead of downloading"""
    try:
        current_url = driver.current_url
        # Check if URL contains PDF viewer indicators
        if 'chrome-extension://' in current_url and 'pdf' in current_url.lower():
            return True
        # Check if page title indicates PDF viewer
        if 'pdf' in driver.title.lower():
            return True
        # Check for PDF viewer elements
        try:
            driver.find_element(By.TAG_NAME, "embed")
            return True
        except:
            pass
        return False
    except:
        return False

def force_download_from_viewer(driver):
    """Try to force download from PDF viewer"""
    try:
        # Try Ctrl+S to save
        actions = ActionChains(driver)
        actions.key_down(Keys.CONTROL).send_keys('s').key_up(Keys.CONTROL).perform()
        time.sleep(2)
        return True
    except:
        return False

def download_file_with_browser(driver, url, filename_base, download_folder):
    """Navigate to URL using browser to trigger download and rename the file with original extension"""
    try:
        print(f"Navigating to download: {filename_base}")
        
        # Get list of files before download
        files_before = set(os.listdir(download_folder))
        
        # Navigate to the URL to trigger download
        driver.get(url)
        
        # Wait a moment for the page to load
        time.sleep(3)
        
        # Check if PDF opened in viewer instead of downloading
        if check_if_pdf_viewer_opened(driver):
            print(f"PDF opened in viewer for: {filename_base}")
            print("Attempting to force download...")
            
            # Try to force download
            if force_download_from_viewer(driver):
                time.sleep(3)  # Wait for save dialog/download
        
        # Wait for download to complete
        if wait_for_download_completion(download_folder, timeout=30):
            # Find the new file and rename it
            files_after = set(os.listdir(download_folder))
            new_files = files_after - files_before
            
            if new_files:
                # Get the newest file
                newest_file = max([os.path.join(download_folder, f) for f in new_files], 
                                key=os.path.getctime)
                newest_filename = os.path.basename(newest_file)
                
                # Extract the original file extension
                _, original_extension = os.path.splitext(newest_filename)
                if not original_extension:
                    original_extension = '.pdf'  # Default if no extension found
                
                # Create the new filename with original extension
                final_filename = filename_base + original_extension
                  # Rename to expected filename with original extension
                if newest_filename != final_filename:
                    try:
                        new_path = os.path.join(download_folder, final_filename)
                        os.rename(newest_file, new_path)
                        print(f"Successfully downloaded and renamed: {final_filename}")
                    except Exception as e:
                        print(f"Downloaded but couldn't rename {newest_filename} to {final_filename}: {str(e)}")
                        return True  # Still consider it successful even if rename failed
                else:
                    print(f"Successfully downloaded: {final_filename}")
                return True
            else:
                # No automatic download occurred
                print(f"⚠️  MANUAL DOWNLOAD REQUIRED for: {filename_base}")
                print(f"   URL: {url}")
                print(f"   Expected filename: {filename_base}.[extension]")
                print("   Please download manually using Ctrl+S or right-click -> Save As")
                print("   Press Enter when you've saved the file to continue...")
                input("   > ")
                
                # Check if file was manually downloaded
                files_after_manual = set(os.listdir(download_folder))
                new_files_manual = files_after_manual - files_before
                
                if new_files_manual:
                    print(f"✓ Manual download detected for: {filename_base}")
                    return True
                else:
                    print(f"✗ No file detected after manual download for: {filename_base}")
                    return False
        else:
            print(f"Download timeout for: {filename_base}")
            return False
        
    except Exception as e:
        print(f"Error downloading {filename_base}: {str(e)}")
        return False

def process_csv_file(csv_path, download_folder, driver):
    """Process a single CSV file and download all linked files using browser"""
    csv_filename = os.path.basename(csv_path)
    print(f"\nProcessing CSV file: {csv_filename}")
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            header = next(reader)  # Skip header row
            
            download_count = 0
            error_count = 0
            
            for row_num, row in enumerate(reader, start=2):
                if len(row) < 7:  # Make sure we have enough columns
                    print(f"Row {row_num}: Insufficient columns, skipping")
                    continue
                
                session = row[0].strip()
                activity_code = row[1].strip()
                section_code = row[2].strip()
                meeting_section = row[3].strip()
                url = row[6].strip() if len(row) > 6 else ""
                
                if not url or not url.startswith('http'):
                    print(f"Row {row_num}: No valid URL found, skipping")
                    continue
                  # Create filename in format: Code_Section Code_Session_Meeting Section
                filename_base = f"{activity_code}_{section_code}_{session}_{meeting_section}"
                filename_base = sanitize_filename(filename_base)
                
                # Download the file using browser (extension will be preserved from original file)
                if download_file_with_browser(driver, url, filename_base, download_folder):
                    download_count += 1
                else:
                    error_count += 1
                
                # Add a delay between downloads to be respectful
                time.sleep(3)
            
            print(f"Completed {csv_filename}: {download_count} downloads, {error_count} errors")
            
    except Exception as e:
        print(f"Error processing CSV file {csv_filename}: {str(e)}")

def main():
    """Main function to process all CSV files in the directory"""
    # Get the directory containing this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Create downloads folder
    download_folder = os.path.join(script_dir, "downloads")
    os.makedirs(download_folder, exist_ok=True)
    
    print(f"Script directory: {script_dir}")
    print(f"Download folder: {download_folder}")
    
    # Find all CSV files in the directory
    csv_files = []
    for filename in os.listdir(script_dir):
        if filename.lower().endswith('.csv'):
            csv_path = os.path.join(script_dir, filename)
            csv_files.append(csv_path)
    
    if not csv_files:
        print("No CSV files found in the directory.")
        return
    
    print(f"Found {len(csv_files)} CSV file(s): {[os.path.basename(f) for f in csv_files]}")
    
    # Set up Chrome driver
    print("Setting up Chrome browser...")
    driver = setup_chrome_driver(download_folder)
    
    try:
        print("\nPlease log in to the required website in the browser window that just opened.")
        print("Once you're logged in, press Enter to continue with the downloads...")
        input()
        
        # Process each CSV file
        total_start_time = time.time()
        for csv_path in csv_files:
            process_csv_file(csv_path, download_folder, driver)
        
        total_time = time.time() - total_start_time
        print(f"\nAll downloads completed in {total_time:.2f} seconds")
        print(f"Files saved to: {download_folder}")
        
    finally:
        # Close the browser
        print("Closing browser...")
        driver.quit()

if __name__ == "__main__":
    main()