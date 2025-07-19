import os
import json
import time
import smtplib
import logging
import schedule
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

class JobMonitor:
    """Monitor UofT Libraries student job postings."""
    
    def __init__(self, config_file: str = 'job_monitor_config.json'):
        """Initialize the job monitor with configuration."""
        self.config_file = config_file
        self.jobs_file = 'known_jobs.json'
        self.base_url = "https://studentjobs.library.utoronto.ca/index.php/student/vacancies"
        
        # Load configuration
        self.config = self.load_config()
        
        # Load known jobs
        self.known_jobs = self.load_known_jobs()
        
    def load_config(self) -> Dict:
        """Load email configuration from file."""
        default_config = {
            "email": {
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "sender_email": "",
                "sender_password": "",
                "recipient_email": "",
                "use_app_password": True
            },
            "monitoring": {
                "check_interval_hours": 1,
                "timeout_seconds": 30
            }
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    # Merge with defaults to ensure all keys exist
                    for key in default_config:
                        if key not in config:
                            config[key] = default_config[key]
                        elif isinstance(default_config[key], dict):
                            for subkey in default_config[key]:
                                if subkey not in config[key]:
                                    config[key][subkey] = default_config[key][subkey]
                    return config
            except Exception as e:
                logger.error(f"Error loading config: {e}")
                
        # Create default config file
        with open(self.config_file, 'w') as f:
            json.dump(default_config, f, indent=2)
        
        logger.info(f"Created default config file: {self.config_file}")
        logger.info("Please update the email configuration before running.")
        return default_config
    
    def load_known_jobs(self) -> Set[str]:
        """Load previously seen job numbers."""
        if os.path.exists(self.jobs_file):
            try:
                with open(self.jobs_file, 'r') as f:
                    data = json.load(f)
                    return set(data.get('job_numbers', []))
            except Exception as e:
                logger.error(f"Error loading known jobs: {e}")
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
        except Exception as e:
            logger.error(f"Error saving known jobs: {e}")
    
    def scrape_current_jobs(self) -> Optional[Dict[str, Dict]]:
        """Scrape current job listings from the website."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
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
        
        # Validate email configuration
        if not email_config['sender_email'] or not email_config['recipient_email']:
            logger.error("Email configuration incomplete. Please update config file.")
            return
        
        try:
            # Create email content
            subject = f"New UofT Library Job Posting{'s' if len(new_jobs) > 1 else ''} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            body = f"🔔 New job posting{'s' if len(new_jobs) > 1 else ''} found on UofT Libraries Student Jobs board!\n\n"
            
            for job_num, details in new_jobs.items():
                body += f"📌 Job Number: {job_num}\n"
                body += f"   Position: {details['position']}\n"
                body += f"   Department: {details['department']}\n"
                body += f"   Hours: {details['hours']}\n"
                body += f"   Period: {details['period']}\n"
                body += f"   Rate: {details['rate']}\n"
                body += f"   Closing: {details['closing']}\n"
                if details['view_link']:
                    body += f"   View Details: {details['view_link']}\n"
            
            # Create message
            msg = EmailMessage()
            msg['From'] = email_config['sender_email']
            msg['To'] = email_config['recipient_email']
            msg['Subject'] = subject
            msg.set_content(body)
            
            # Determine connection type based on port and SSL setting
            smtp_port = email_config['smtp_port']
            use_ssl = email_config.get('use_ssl', False)
            
            logger.info(f"Attempting to send email via {email_config['smtp_server']}:{smtp_port} (SSL: {use_ssl})")
            
            # Send email with appropriate connection type
            if use_ssl or smtp_port == 465:
                # Use SSL connection for port 465
                server = smtplib.SMTP_SSL(email_config['smtp_server'], smtp_port, timeout=30)
                logger.info("Using SSL connection")
            else:
                # Use regular SMTP with STARTTLS for port 587
                server = smtplib.SMTP(email_config['smtp_server'], smtp_port, timeout=30)
                logger.info("Using STARTTLS connection")
                server.starttls()
            
            # Enable debug output for troubleshooting
            server.set_debuglevel(0)  # Set to 1 for verbose debugging if needed
            
            logger.info("Attempting to log in...")
            server.login(email_config['sender_email'], email_config['sender_password'])
            
            logger.info("Sending email...")
            server.send_message(msg)
            server.quit()
            
            logger.info(f"[SUCCESS] Email notification sent successfully for {len(new_jobs)} new job(s)")
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"[ERROR] SMTP Authentication failed: {e}")
            logger.error("Please check your email address and password")
        except smtplib.SMTPServerDisconnected as e:
            logger.error(f"[ERROR] SMTP Server disconnected: {e}")
            logger.error("Try switching between ports 587 (STARTTLS) and 465 (SSL)")
        except smtplib.SMTPConnectError as e:
            logger.error(f"[ERROR] SMTP Connection error: {e}")
            logger.error("Check your SMTP server address and port")
        except smtplib.SMTPRecipientsRefused as e:
            logger.error(f"[ERROR] Recipients refused: {e}")
            logger.error("Check the recipient email address")
        except smtplib.SMTPException as e:
            logger.error(f"[ERROR] SMTP error: {e}")
        except ConnectionResetError as e:
            logger.error(f"[ERROR] Connection reset by server: {e}")
            logger.error("This often happens with Namecheap. Trying alternative configuration...")
            # Retry with different settings
            self._retry_email_with_alternative_config(new_jobs)
        except Exception as e:
            logger.error(f"[ERROR] Unexpected error sending email: {e}")
            logger.error("Check your email configuration and internet connection")
    
    def _retry_email_with_alternative_config(self, new_jobs: Dict[str, Dict]):
        """Retry email sending with alternative SMTP configuration."""
        email_config = self.config['email']
        
        # Try alternative port/SSL combination
        if email_config['smtp_port'] == 465:
            alt_port = 587
            alt_ssl = False
            logger.info("Retrying with port 587 and STARTTLS...")
        else:
            alt_port = 465
            alt_ssl = True
            logger.info("Retrying with port 465 and SSL...")
        
        try:
            # Create message
            msg = EmailMessage()
            msg['From'] = email_config['sender_email']
            msg['To'] = email_config['recipient_email']
            msg['Subject'] = f"New UofT Library Job Posting{'s' if len(new_jobs) > 1 else ''}: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            body = f"🔔 New job posting{'s' if len(new_jobs) > 1 else ''} found on UofT Libraries Student Jobs board!\n\n"
            for job_num, details in new_jobs.items():
                body += f"📌 Job Number: {job_num}\n"
                body += f"   Position: {details['position']}\n"
                body += f"   Department: {details['department']}\n"
                if details['view_link']:
                    body += f"   View Details: {details['view_link']}\n"
                body += "\n"
            msg.set_content(body)
            
            # Try alternative connection
            if alt_ssl:
                server = smtplib.SMTP_SSL(email_config['smtp_server'], alt_port, timeout=30)
            else:
                server = smtplib.SMTP(email_config['smtp_server'], alt_port, timeout=30)
                server.starttls()
            
            server.login(email_config['sender_email'], email_config['sender_password'])
            server.send_message(msg)
            server.quit()
            
            logger.info(f"[SUCCESS] Email sent successfully using alternative configuration (port {alt_port})")
            logger.info(f"[TIP] Consider updating your config to use port {alt_port} with SSL: {alt_ssl}")
            
        except Exception as e:
            logger.error(f"[ERROR] Retry also failed: {e}")
            logger.error("Please contact Namecheap support or check your email settings")
    
    def check_for_updates(self):
        """Check for new job postings and handle notifications."""
        logger.info("Checking for job updates...")
        
        current_jobs = self.scrape_current_jobs()
        
        if current_jobs is None:
            logger.error("Failed to scrape current jobs")
            return
        
        current_job_numbers = set(current_jobs.keys())
        
        # Find new jobs
        new_job_numbers = current_job_numbers - self.known_jobs
        new_jobs = {num: current_jobs[num] for num in new_job_numbers}
        
        # Find removed jobs
        removed_job_numbers = self.known_jobs - current_job_numbers
        
        # Log findings
        if new_jobs:
            logger.info(f"Found {len(new_jobs)} new job posting(s): {list(new_jobs.keys())}")
            self.send_email_notification(new_jobs)
        
        if removed_job_numbers:
            logger.info(f"Removed {len(removed_job_numbers)} job posting(s): {list(removed_job_numbers)}")
        
        if not new_jobs and not removed_job_numbers:
            logger.info("No changes in job postings")
        
        # Update known jobs only if there are changes
        if new_jobs or removed_job_numbers:
            self.known_jobs = current_job_numbers
            self.save_known_jobs()
            logger.info(f"Updated known jobs file - now monitoring {len(self.known_jobs)} total job postings")
        else:
            logger.info(f"No changes detected - known jobs file not updated. Currently monitoring {len(self.known_jobs)} total job postings")
    
    def run_scheduler(self):
        """Run the monitoring scheduler."""
        interval_hours = self.config['monitoring']['check_interval_hours']
        
        # Schedule the job checking
        schedule.every(interval_hours).hours.do(self.check_for_updates)
        
        logger.info(f"Job monitor started - checking every {interval_hours} hour(s)")
        logger.info("Press Ctrl+C to stop monitoring")
        
        # Run initial check
        self.check_for_updates()
        
        # Keep the script running
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute for scheduled tasks
        except KeyboardInterrupt:
            logger.info("Job monitor stopped by user")

def main():
    """Main function to run the job monitor."""
    monitor = JobMonitor()
    
    # Validate email configuration
    if not monitor.config['email']['sender_email']:
        print("\n[ERROR] Email configuration required!")
        print(f"Please edit {monitor.config_file} and add your email details:")
        print("- sender_email: Your email address")
        print("- sender_password: Your email password")
        print("- recipient_email: Email address to receive notifications")
        return
    
    # Run the monitor
    monitor.run_scheduler()

if __name__ == "__main__":
    main()
