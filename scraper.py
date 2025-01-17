import os
import time
import json
import requests
import argparse
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import csv
from pathlib import Path
from bs4 import BeautifulSoup
from typing import List, Dict, Tuple
from urllib.parse import urlparse
from requests.exceptions import RequestException

class GovInfoScraper:
    def __init__(self):
        self.api_key = os.getenv('GOVINFO_API_KEY')
        self.base_url = 'https://www.govinfo.gov'
        self.downloads_dir = 'downloads'
        self.scraped_data_dir = 'scraped_data'
        self.bill_types = [
            'hconres',  # House Concurrent Resolution
            'hjres',    # House Joint Resolution
            'hr',       # House Bill
            'hres',     # House Simple Resolution
            's',        # Senate Bill
            'sconres',  # Senate Concurrent Resolution
            'sjres',    # Senate Joint Resolution
            'sres'      # Senate Simple Resolution
        ]
        # Common bill versions that might exist
        self.bill_versions = [
            'ih',  # Introduced in House
            'eh',  # Engrossed in House
            'rh',  # Reported in House
            'rfs', # Referred to Senate
            'is',  # Introduced in Senate
            'es',  # Engrossed in Senate
            'rs',  # Reported in Senate
            'ats', # Agreed to Senate
            'enr'  # Enrolled Bill
        ]
        os.makedirs(self.downloads_dir, exist_ok=True)
        os.makedirs(self.scraped_data_dir, exist_ok=True)

    def load_progress(self):
        """Load progress from JSON file"""
        progress_file = os.path.join(self.downloads_dir, 'progress.json')
        if os.path.exists(progress_file):
            try:
                with open(progress_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print("Error reading progress file. Starting fresh.")
        return []

    def save_progress(self, results):
        """Save progress to JSON file"""
        progress_file = os.path.join(self.downloads_dir, 'progress.json')
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)

    def get_downloaded_bills(self):
        """Get set of already downloaded bill IDs"""
        progress = self.load_progress()
        return {result['bill_id'] for result in progress}

    def validate_url(self, url: str) -> Tuple[bool, str]:
        """
        Validate if a URL exists and is accessible
        Returns: (exists: bool, error_message: str)
        """
        try:
            # Use GET instead of HEAD to properly validate PDF existence
            response = requests.get(url, stream=True)
            if response.status_code == 200:
                # Check if it's actually a PDF by looking at the first few bytes
                content_type = response.headers.get('content-type', '').lower()
                if 'application/pdf' in content_type:
                    # Read just the first few bytes to verify PDF header
                    pdf_header = response.raw.read(5)
                    if pdf_header.startswith(b'%PDF-'):
                        return True, ""
                    else:
                        return False, "Not a valid PDF file"
                else:
                    return False, f"Not a PDF file (content-type: {content_type})"
            elif response.status_code == 404:
                return False, "Bill not found (404)"
            else:
                return False, f"Unexpected status code: {response.status_code}"
        except RequestException as e:
            return False, f"Error checking URL: {str(e)}"

    def extract_bill_id_from_url(self, url: str) -> str:
        """Extract bill ID from URL"""
        path = urlparse(url).path
        filename = os.path.splitext(os.path.basename(path))[0]
        return filename

    def generate_bill_urls(self, congress: str, bill_type: str, start_number: int, end_number: int) -> List[str]:
        """Generate potential bill URLs for a range of numbers"""
        urls = []
        for number in range(start_number, end_number + 1):
            for version in self.bill_versions:
                bill_id = f"BILLS-{congress}{bill_type}{number}{version}"
                url = f"{self.base_url}/content/pkg/{bill_id}/pdf/{bill_id}.pdf"
                # Validate URL before adding
                exists, _ = self.validate_url(url)
                if exists:
                    urls.append(url)
                    print(f"Found valid bill: {bill_id}")
                time.sleep(0.1)  # Rate limiting for validation
        return urls

    def download_bills_from_urls(self, urls: List[str], skip_existing: bool = True) -> List[Dict]:
        """Download bills from a list of direct URLs"""
        all_results = self.load_progress()
        downloaded_bills = self.get_downloaded_bills()
        total_found = len(downloaded_bills)
        failed_urls = []
        
        for i, url in enumerate(urls, 1):
            try:
                bill_id = self.extract_bill_id_from_url(url)
                
                if skip_existing and bill_id in downloaded_bills:
                    print(f"\nSkipping already downloaded bill {i}/{len(urls)}: {bill_id}")
                    continue
                
                print(f"\nProcessing bill {i}/{len(urls)}: {bill_id}")
                
                bill_data = {
                    'bill_id': bill_id,
                    'pdf_url': url,
                    'title': f"Bill {bill_id}"
                }
                
                results = self.download_bill(bill_data, skip_existing)
                if results:
                    all_results.append(results)
                    total_found += 1
                    print(f"Successfully downloaded bill (Total found: {total_found})")
                    self.save_progress(all_results)
                
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                error_message = f"Error processing URL {url}: {str(e)}"
                print(error_message)
                failed_urls.append((url, error_message))
                continue
        
        if failed_urls:
            print("\nFailed URLs Summary:")
            for url, error in failed_urls:
                print(f"- {url}: {error}")
        
        return all_results

    def download_bill_from_url(self, url, bill_id, format_type, skip_existing=True):
        """Download bill from direct URL"""
        bill_dir = os.path.join(self.downloads_dir, bill_id)
        format_dir = os.path.join(bill_dir, format_type)
        os.makedirs(format_dir, exist_ok=True)

        file_name = f"{bill_id}.{format_type}"
        if format_type == 'htm':
            file_name = f"{bill_id}.html"
        
        file_path = os.path.join(format_dir, file_name)
        
        if skip_existing and os.path.exists(file_path):
            print(f"File already exists: {file_path}")
            return file_path

        try:
            print(f"Downloading {format_type} from: {url}")
            response = requests.get(url)
            response.raise_for_status()
            
            write_mode = 'wb' if format_type == 'pdf' else 'w'
            encoding = None if format_type == 'pdf' else 'utf-8'
            
            with open(file_path, write_mode, encoding=encoding) as f:
                if format_type == 'pdf':
                    f.write(response.content)
                else:
                    f.write(response.text)
                    
            print(f"Saved {format_type} to: {file_path}")
            return file_path
            
        except requests.exceptions.RequestException as e:
            print(f"Error downloading {format_type}: {str(e)}")
            return None

    def download_bill(self, bill_data, skip_existing=True):
        """Download bill in all available formats using direct URLs"""
        results = {
            'bill_id': bill_data['bill_id'],
            'title': bill_data.get('title', ''),
            'files': {}
        }
        
        format_map = {
            'pdf_url': 'pdf',
            'html_url': 'htm',
            'xml_url': 'xml'
        }
        
        success = False
        for url_key, format_type in format_map.items():
            if url_key in bill_data:
                file_path = self.download_bill_from_url(
                    bill_data[url_key],
                    bill_data['bill_id'],
                    format_type,
                    skip_existing
                )
                if file_path:
                    results['files'][format_type] = file_path
                    success = True
        
        return results if success else None

    def batch_download_bills(self, congress: str, start_number: int = 1, end_number: int = 100):
        """Download bills in batch for all types"""
        all_results = []
        for bill_type in self.bill_types:
            print(f"\nProcessing {bill_type} bills for {congress}th Congress ({start_number}-{end_number})")
            urls = self.generate_bill_urls(congress, bill_type, start_number, end_number)
            print(f"Found {len(urls)} valid bills to download")
            if urls:
                results = self.download_bills_from_urls(urls)
                if results:
                    all_results.extend(results)
        return all_results

def get_user_input():
    """Get start and end numbers from user input"""
    while True:
        try:
            start = int(input("Enter start number (1-9999): "))
            if 1 <= start <= 9999:
                break
            print("Start number must be between 1 and 9999")
        except ValueError:
            print("Please enter a valid number")
    
    while True:
        try:
            end = int(input("Enter end number (must be >= start number): "))
            if end >= start and end <= 9999:
                break
            print("End number must be between start number and 9999")
        except ValueError:
            print("Please enter a valid number")
    
    return start, end

def main():
    parser = argparse.ArgumentParser(description='Download and extract data from congressional bills')
    parser.add_argument('--congress', default="118", help='Congress number (default: 118)')
    parser.add_argument('--start', type=int, help='Start number for bill range')
    parser.add_argument('--end', type=int, help='End number for bill range')
    parser.add_argument('--force', action='store_true', help='Force download even if files exist')
    parser.add_argument('--urls', nargs='+', help='List of direct URLs to download')
    args = parser.parse_args()
    
    scraper = GovInfoScraper()
    
    if args.urls:
        print(f"\nStarting to download {len(args.urls)} bills from direct URLs...")
        results = scraper.download_bills_from_urls(args.urls, skip_existing=not args.force)
    else:
        # If start or end not provided, get them from user input
        start_number = args.start
        end_number = args.end
        
        if start_number is None or end_number is None:
            print("\nNo start/end numbers provided via command line. Please enter them now:")
            start_number, end_number = get_user_input()
        
        print(f"\nStarting batch download for {args.congress}th Congress...")
        print(f"Bill range: {start_number}-{end_number}")
        print(f"Force download: {args.force}")
        results = scraper.batch_download_bills(
            congress=args.congress,
            start_number=start_number,
            end_number=end_number
        )
    
    if results:
        print(f"\nSuccessfully downloaded {len(results)} bills")
        print("Progress saved in downloads/progress.json")
        print("Bill information saved in scraped_data directory")
    else:
        print("\nNo bills were downloaded. Please check the error messages above.")

if __name__ == "__main__":
    main()