import os
import json
import time
import smtplib
import logging
import requests
from datetime import datetime
from email.message import EmailMessage
from bs4 import BeautifulSoup
from typing import Dict, Set, List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('job_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class JobMonitorCI:
    """Monitor UofT Libraries student job postings - CI/CD version."""
    
    def __init__(self):
        """Initialize the job monitor with environment variables."""
        self.jobs_file = 'known_jobs.json'
        self.base_url = "https://studentjobs.library.utoronto.ca/index.php/student/vacancies"
        
        # Load configuration from environment variables
        self.config = self.load_config_from_env()
        
        # Load known jobs
        self.known_jobs = self.load_known_jobs()
        
    def load_config_from_env(self) -> Dict:
        """Load email configuration from environment variables."""
        config = {
            "email": {
                "smtp_server": os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
                "smtp_port": int(os.getenv('SMTP_PORT', '587')),
                "sender_email": os.getenv('SENDER_EMAIL', ''),
                "sender_password": os.getenv('SENDER_PASSWORD', ''),
                "recipient_email": os.getenv('RECIPIENT_EMAIL', ''),
                "use_ssl": os.getenv('USE_SSL', 'false').lower() == 'true'
            },
            "monitoring": {
                "timeout_seconds": 30
            }
        }
        
        # Validate required environment variables
        required_vars = ['SENDER_EMAIL', 'SENDER_PASSWORD', 'RECIPIENT_EMAIL']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            logger.error(f"Missing required environment variables: {missing_vars}")
            raise ValueError(f"Missing required environment variables: {missing_vars}")
        
        logger.info("Configuration loaded from environment variables")
        return config
    
    def load_known_jobs(self) -> Set[str]:
        """Load previously seen job numbers."""
        if os.path.exists(self.jobs_file):
            try:
                with open(self.jobs_file, 'r') as f:
                    data = json.load(f)
                    jobs = set(data.get('job_numbers', []))
                    logger.info(f"Loaded {len(jobs)} previously known jobs")
                    return jobs
            except Exception as e:
                logger.error(f"Error loading known jobs: {e}")
        
        logger.info("No previous job data found, starting fresh")
        return set()
    
    def save_known_jobs(self):
        """Save known job numbers to file."""
        try:
            data = {
                'job_numbers': list(self.known_jobs),
                'last_updated': datetime.now().isoformat()
            }
            with open(self.jobs_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved {len(self.known_jobs)} known jobs to file")
        except Exception as e:
            logger.error(f"Error saving known jobs: {e}")
    
    def scrape_current_jobs(self) -> Optional[Dict[str, Dict]]:
        """Scrape current job listings from the website."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            logger.info(f"Fetching job listings from {self.base_url}")
            response = requests.get(
                self.base_url, 
                headers=headers, 
                timeout=self.config['monitoring']['timeout_seconds']
            )
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find the vacancies table
            jobs = {}
            table = soup.find('table')
            
            if not table:
                logger.warning("No table found on the page")
                return {}
            
            # Parse job rows (skip header row)
            for row in table.find_all('tr')[1:]:  # Skip header
                cells = row.find_all('td')
                if len(cells) >= 4:
                    # Extract job number
                    job_number = cells[0].get_text(strip=True)
                    
                    # Extract job details from the second cell
                    details_cell = cells[1]
                    detail_items = details_cell.find_all('li')
                    
                    position = ""
                    department = ""
                    hours = ""
                    
                    for item in detail_items:
                        text = item.get_text(strip=True)
                        if text.startswith("Position:"):
                            position = text.replace("Position:", "").strip()
                        elif text.startswith("Department:"):
                            department = text.replace("Department:", "").strip()
                        elif text.startswith("Hours:"):
                            hours = text.replace("Hours:", "").strip()
                    
                    # Extract additional details from third cell
                    extra_details_cell = cells[2]
                    extra_items = extra_details_cell.find_all('li')
                    
                    period = ""
                    rate = ""
                    closing = ""
                    
                    for item in extra_items:
                        text = item.get_text(strip=True)
                        if text.startswith("Period:"):
                            period = text.replace("Period:", "").strip()
                        elif text.startswith("Rate:"):
                            rate = text.replace("Rate:", "").strip()
                        elif text.startswith("Closing:"):
                            closing = text.replace("Closing:", "").strip()
                    
                    # Extract view link
                    view_link = ""
                    view_cell = cells[3]
                    link = view_cell.find('a')
                    if link and link.get('href'):
                        href = link.get('href')
                        # Handle relative URLs
                        if href.startswith('//'):
                            view_link = "https:" + href
                        elif href.startswith('/'):
                            view_link = "https://studentjobs.library.utoronto.ca" + href
                        else:
                            view_link = href
                    
                    jobs[job_number] = {
                        'position': position,
                        'department': department,
                        'hours': hours,
                        'period': period,
                        'rate': rate,
                        'closing': closing,
                        'view_link': view_link,
                        'scraped_at': datetime.now().isoformat()
                    }
            
            logger.info(f"Successfully scraped {len(jobs)} current job postings")
            return jobs
            
        except requests.RequestException as e:
            logger.error(f"Error fetching job listings: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing job listings: {e}")
            return None
    
    def send_email_notification(self, new_jobs: Dict[str, Dict]):
        """Send email notification for new job postings."""
        if not new_jobs:
            return
        
        email_config = self.config['email']
        
        try:
            # Create email content
            subject = f"UofT Library Job Alert - {len(new_jobs)} New Position{'s' if len(new_jobs) > 1 else ''}"
            
            body = f"New library job posting{'s' if len(new_jobs) > 1 else ''} found!\n\n"
            
            for job_num, details in new_jobs.items():
                body += f"📌 Job #{job_num}\n"
                body += f"     👔 Position: {details['position']}\n"
                body += f"     🏢 Department: {details['department']}\n"
                body += f"     ⏱️ Hours: {details['hours']}\n"
                body += f"     📅 Period: {details['period']}\n"
                body += f"     💰 Rate: {details['rate']}\n"
                body += f"     ⏳ Closing: {details['closing']}\n"
                if details['view_link']:
                    body += f"    🔗 Apply: {details['view_link']}\n"
                body += "\n" + "─" * 40 + "\n\n"
            
            # Toronto is UTC-5 (Eastern Time), UTC-4 during DST
            def is_dst(dt):
                """Return True if dt is in DST for Toronto (Eastern Time)."""
                year = dt.year
                # DST starts: Second Sunday in March
                dst_start = datetime(year, 3, 8)
                dst_start += timedelta(days=(6 - dst_start.weekday()))  # Go to next Sunday
                # DST ends: First Sunday in November
                dst_end = datetime(year, 11, 1)
                dst_end += timedelta(days=(6 - dst_end.weekday()))  # Go to next Sunday
                return dst_start <= dt < dst_end

            from datetime import timedelta
            utc_now = datetime.utcnow().replace(microsecond=0)
            offset = -4 if is_dst(utc_now) else -5
            toronto_time = utc_now + timedelta(hours=offset)
            tz_label = 'UTC-4 (DST)' if offset == -4 else 'UTC-5'
            body += f"Checked at: {toronto_time.strftime('%Y-%m-%d %H:%M')} (Toronto time, {tz_label})\n"
            
            # Create message
            msg = EmailMessage()
            msg['From'] = email_config['sender_email']
            msg['To'] = email_config['recipient_email']
            msg['Subject'] = subject
            msg.set_content(body)
            
            # Send email
            smtp_port = email_config['smtp_port']
            use_ssl = email_config.get('use_ssl', False)
            
            logger.info(f"Sending email notification for {len(new_jobs)} new job(s)")
            logger.info(f"SMTP: {email_config['smtp_server']}:{smtp_port} (SSL: {use_ssl})")
            
            if use_ssl or smtp_port == 465:
                server = smtplib.SMTP_SSL(email_config['smtp_server'], smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(email_config['smtp_server'], smtp_port, timeout=30)
                server.starttls()
            
            server.login(email_config['sender_email'], email_config['sender_password'])
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Email notification sent successfully for {len(new_jobs)} new job(s)")
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP Authentication failed: {e}")
            logger.error("Check your email credentials in GitHub Secrets")
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
        except Exception as e:
            logger.error(f"Error sending email: {e}")
    
    def check_for_updates(self):
        """Check for new job postings and handle notifications."""
        logger.info("Checking for job updates...")
        
        current_jobs = self.scrape_current_jobs()
        
        if current_jobs is None:
            logger.error("Failed to scrape current jobs")
            return False
        
        current_job_numbers = set(current_jobs.keys())
        
        # Check if this is the first run (only when there are jobs to track)
        is_first_run = len(self.known_jobs) == 0 and len(current_job_numbers) > 0
        
        # Find new jobs
        new_job_numbers = current_job_numbers - self.known_jobs
        new_jobs = {num: current_jobs[num] for num in new_job_numbers}
        
        # Find removed jobs
        removed_job_numbers = self.known_jobs - current_job_numbers
        
        # Log findings
        if is_first_run:
            logger.info(f"First run detected - Found {len(current_jobs)} existing job postings")
            logger.info("No notifications will be sent for existing jobs on first run")
        elif new_jobs:
            logger.info(f"Found {len(new_jobs)} new job posting(s): {list(new_jobs.keys())}")
            self.send_email_notification(new_jobs)
        
        if removed_job_numbers:
            logger.info(f"Removed {len(removed_job_numbers)} job posting(s): {list(removed_job_numbers)}")
        
        if not new_jobs and not removed_job_numbers and not is_first_run:
            logger.info("No changes in job postings")
        
        # Update known jobs only if there are changes or it's the first run
        if new_jobs or removed_job_numbers or is_first_run:
            self.known_jobs = current_job_numbers
            self.save_known_jobs()
            logger.info(f"Updated known jobs file - now monitoring {len(self.known_jobs)} total job postings")
        else:
            logger.info(f"No changes detected - known jobs file not updated. Currently monitoring {len(self.known_jobs)} total job postings")
        
        return True

def main():
    """Main function to run the job monitor in CI environment."""
    try:
        logger.info("Starting UofT Library Job Monitor (CI Version)")
        monitor = JobMonitorCI()
        
        # Run single check (not a loop since GitHub Actions handles scheduling)
        success = monitor.check_for_updates()
        
        if success:
            logger.info("Job monitor completed successfully")
        else:
            logger.error("Job monitor completed with errors")
            exit(1)
            
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please check your GitHub Secrets configuration")
        exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
