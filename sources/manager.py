from typing import List, Dict
from config import config
from sources.rss import RSSFetcher
from database import db

class SourceManager:
    def __init__(self):
        self.rss_fetcher = RSSFetcher()
        self.feeds = config.RSS_FEEDS

    def fetch_all(self) -> int:
        """
        Fetches all feeds and saves new items to DB.
        Returns number of new items added.
        """
        new_count = 0
        for url in self.feeds:
            print(f"Fetching {url}...")
            items = self.rss_fetcher.fetch(url)
            for item in items:
                # Add to DB
                added = db.add_news(
                    url=item['url'],
                    title=item['title'],
                    source_name=item['source_name'],
                    published_at=item['published_at']
                )
                if added:
                    new_count += 1
        return new_count

source_manager = SourceManager()
