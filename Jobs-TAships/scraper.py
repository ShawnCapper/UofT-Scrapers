import requests
import os
import time
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TAPostingScraper:

    def __init__(self, start_id=7625, download_folder="downloads"):
        self.start_id = start_id
        self.download_folder = download_folder
        self.base_url = "https://unit1.hrandequity.utoronto.ca/posting/{}"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent':
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

        # Create download folder if it doesn't exist
        Path(self.download_folder).mkdir(parents=True, exist_ok=True)

    def is_404_page(self, content):
        """Check if the content is a 404 page based on the pattern from the attached HTML"""
        return "404" in content and "Not Found" in content and "relative flex items-top justify-center min-h-screen" in content

    def download_posting(self, posting_id):
        """Download a single posting and return success status"""
        url = self.base_url.format(posting_id)
        filename = f"posting_{posting_id}.html"
        filepath = os.path.join(self.download_folder, filename)

        try:
            logger.info(f"Attempting to download posting {posting_id}")
            response = self.session.get(url, timeout=10)

            # Check if it's a 404 page
            if self.is_404_page(response.text):
                logger.warning(f"404 page detected for posting {posting_id}")
                return False

            # If we get here, it's likely a valid page
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(response.text)

            logger.info(
                f"Successfully downloaded posting {posting_id} to {filename}")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Error downloading posting {posting_id}: {str(e)}")
            return False

    def scrape_all_postings(self):
        """Scrape all postings starting from start_id until 100 consecutive 404s (only after ID 45000)"""
        current_id = self.start_id
        consecutive_404s = 0
        successful_downloads = 0

        logger.info(f"Starting scrape from posting ID {self.start_id}")
        logger.info(
            f"Downloads will be saved to: {os.path.abspath(self.download_folder)}"
        )

        while True:
            # Only apply the 100 consecutive 404s escape rule after posting ID 45000
            if current_id > 45000 and consecutive_404s >= 100:
                break
            success = self.download_posting(current_id)

            if success:
                consecutive_404s = 0  # Reset counter on successful download
                successful_downloads += 1
            else:
                consecutive_404s += 1
                logger.info(f"Consecutive 404s: {consecutive_404s}/100")

            current_id += 1

            # Add a small delay to be respectful to the server
            time.sleep(2)

            # Progress update every 10 attempts
            if (current_id - self.start_id) % 10 == 0:
                logger.info(
                    f"Progress: Checked {current_id - self.start_id} postings, {successful_downloads} downloaded"
                )

        logger.info(f"Scraping completed! Found 100 consecutive 404s after ID 45000.")
        logger.info(f"Total successful downloads: {successful_downloads}")
        logger.info(f"Last attempted posting ID: {current_id - 1}")

        return successful_downloads


def main():
    """Main function to run the scraper"""
    scraper = TAPostingScraper(start_id=7625)

    try:
        total_downloads = scraper.scrape_all_postings()
        print(f"\nScraping completed successfully!")
        print(f"Total files downloaded: {total_downloads}")
        print(f"Files saved to: {os.path.abspath(scraper.download_folder)}")

    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
        print(
            "\nScraping interrupted. Partial downloads may be available in the downloads folder."
        )
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        print(f"An error occurred: {str(e)}")


if __name__ == "__main__":
    main()
