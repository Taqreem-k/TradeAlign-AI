import feedparser
import html2text
from datetime import datetime
from dateutil import parser
from app.scrapers.base import BaseScraper
from app.database.repository import save_market_news

class YahooFinanceScraper(BaseScraper):
    def __init__(self, db):
        super().__init__(db)
        self.rss_url = "https://finance.yahoo.com/news/rssindex"
        self.h.ignore_links = False

    def run(self):
        self.logger.info("Starting Yahoo Finance Scraper...")
        feed = feedparser.parse(self.rss_url)

        count = 0
        for entry in feed.entries:
            news_data = {
                "id": entry.id if hasattr(entry, 'id') else entry.link,
                "title": entry.title,
                "source": "Yahoo Finance",
                "url": entry.link,
                "content": self.h.handle(entry.summary) if hasattr(entry, 'summary') else "",
                "published_at": parser.parse(entry.published) if hasattr(entry, 'published') else datetime.now()
            }
            if save_market_news(self.db,news_data):
                count +=1

        self.logger.info(f"Saved {count} new articles from Yahoo Finance.")