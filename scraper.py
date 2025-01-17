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
            response = requests.get(url, stream=True)
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                if 'application/pdf' in content_type:
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

    def process_bill(self, congress: str, bill_type: str, number: int, version: str) -> Dict:
        """Process a single bill"""
        bill_id = f"BILLS-{congress}{bill_type}{number}{version}"
        url = f"{self.base_url}/content/pkg/{bill_id}/pdf/{bill_id}.pdf"
        
        exists, error = self.validate_url(url)
        if not exists:
            return None
            
        print(f"Found valid bill: {bill_id}")
        
        bill_data = {
            'bill_id': bill_id,
            'pdf_url': url,
            'title': f"Bill {bill_id}"
        }
        
        results = self.download_bill({
            'bill_id': bill_id,
            'pdf_url': url,
            'title': f"Bill {bill_id}"
        })
        
        if results:
            print(f"Successfully downloaded bill: {bill_id}")
            
        time.sleep(0.1)  # Rate limiting
        return results

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

    def batch_download_bills(self, congress: str, bill_type: str, start_number: int = 1, end_number: int = 100):
        """Download bills in batch for specific bill type"""
        print(f"\nProcessing {bill_type} bills for {congress}th Congress ({start_number}-{end_number})")
        
        all_results = self.load_progress()
        downloaded_bills = self.get_downloaded_bills()
        total_found = 0
        
        for number in range(start_number, end_number + 1):
            for version in self.bill_versions:
                if total_found % 10 == 0:  # Progress update every 10 bills
                    print(f"\nChecking bill number {number} with version {version}")
                
                results = self.process_bill(congress, bill_type, number, version)
                if results and results['bill_id'] not in downloaded_bills:
                    all_results.append(results)
                    downloaded_bills.add(results['bill_id'])
                    total_found += 1
                    print(f"Total bills found and downloaded: {total_found}")
                    self.save_progress(all_results)
        
        return all_results

def get_user_input(scraper):
    """Get bill type, start and end numbers from user input"""
    print("\nAvailable bill types:")
    for i, bill_type in enumerate(scraper.bill_types, 1):
        print(f"{i}. {bill_type}")
    
    while True:
        try:
            bill_type = input("\nEnter bill type (e.g., hconres, hr, s): ").lower()
            if bill_type in scraper.bill_types:
                break
            print("Invalid bill type. Please choose from the list above.")
        except ValueError:
            print("Please enter a valid bill type")
    
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
    
    return bill_type, start, end

def main():
    parser = argparse.ArgumentParser(description='Download and extract data from congressional bills')
    parser.add_argument('--congress', default="118", help='Congress number (default: 118)')
    parser.add_argument('--bill-type', help='Bill type (e.g., hconres, hr, s)')
    parser.add_argument('--start', type=int, help='Start number for bill range')
    parser.add_argument('--end', type=int, help='End number for bill range')
    parser.add_argument('--force', action='store_true', help='Force download even if files exist')
    args = parser.parse_args()
    
    scraper = GovInfoScraper()
    
    # If any required parameter is missing, get them from user input
    if args.bill_type is None or args.start is None or args.end is None:
        print("\nMissing parameters. Please enter them now:")
        bill_type, start_number, end_number = get_user_input(scraper)
    else:
        bill_type = args.bill_type
        start_number = args.start
        end_number = args.end
        
        # Validate bill type
        if bill_type not in scraper.bill_types:
            print(f"Invalid bill type: {bill_type}")
            print("Available bill types:", ", ".join(scraper.bill_types))
            return
    
    print(f"\nStarting batch download for {args.congress}th Congress...")
    print(f"Bill type: {bill_type}")
    print(f"Bill range: {start_number}-{end_number}")
    print(f"Force download: {args.force}")
    
    results = scraper.batch_download_bills(
        congress=args.congress,
        bill_type=bill_type,
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