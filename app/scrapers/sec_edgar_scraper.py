import feedparser
import requests
from datetime import datetime
from dateutil import parser
from app.scrapers.base import BaseScraper
from app.database.repository import save_sec_filing

class SECScraper(BaseScraper):
    def __init__(self, db):
        super().__init__(db)
        self.rss_url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&CIK=&type=&company=&dateb=&owner=include&start=0&count=40&output=atom"
        self.headers = {"User-Agent": "AlphaRadarAPP (contact @yourdomain.com)"}

    def run(self):
        self.logger.info("Starting SEC EDGAR Scraper...")
        response = requests.get(self.rss_url, headers=self.headers)
        feed = feedparser.parse(response.content)

        count = 0
        for entry in feed.entries:
            form_type = entry.title.split('-')[0].strip() if '-' in entry.title else "Unknown"

            filing_data = {
                "id": entry.id,
                "ticker":"VARIOUS",
                "form_type": form_type,
                "url": entry.link,
                "content": entry.summary if hasattr(entry, 'summary') else "",
                "filing_date": parser.parse(entry.updated) if hasattr(entry, 'updated') else datetime.now()
            }
            if save_sec_filing(self.db, filing_data):
                count+= 1
        self.logger.info(f"Saved {count} new SEC filings.")