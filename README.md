# GovInfo API Scraper

A Python-based scraper for collecting data from the GovInfo API (https://api.govinfo.gov/).

## Features

- Fetches data from multiple GovInfo collections
- Supports date-based filtering
- Saves data in CSV format
- Implements rate limiting and error handling
- Supports pagination for large datasets

## Requirements

- Python 3.8+
- Required packages:
  - requests
  - pandas
  - python-dotenv

## Setup

1. Clone the repository
2. Install dependencies:
```bash
pip install requests pandas python-dotenv
```

3. Create a `.env` file in the project root and add your GovInfo API key:
```
GOVINFO_API_KEY=your_api_key_here
```

## Usage

Run the scraper:
```bash
python scraper.py
```

By default, it will:
1. List all available collections
2. Scrape the BILLS collection for the current year
3. Save the data to CSV in the `scraped_data` directory

## Customizing the Scraper

You can modify the `main()` function in `scraper.py` to:
- Change the target collection
- Adjust date ranges
- Modify the number of items to collect
- Add different data processing steps

Example:
```python
scraper = GovInfoScraper()
result = scraper.scrape_collection(
    'BILLS',
    start_date='2024-01-01T00:00:00Z',
    end_date='2024-03-19T23:59:59Z',
    max_items=500
)
```

## Data Storage

Scraped data is saved in the `scraped_data` directory with filenames formatted as:
`{collection_code}_{timestamp}.csv`

## Error Handling

The scraper includes:
- Rate limiting (0.1s between requests)
- Request error handling
- Data validation
- Automatic directory creation

## License

MIT License