import feedparser
import time
from datetime import datetime
from typing import List, Dict, Optional


class RSSFetcher:
    def parse_date(self, entry) -> float:
        """Parse published date to timestamp."""
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            return time.mktime(entry.published_parsed)
        if hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            return time.mktime(entry.updated_parsed)
        return time.time()

    def fetch(self, url: str) -> List[Dict]:
        """
        Fetches an RSS feed and returns normalized items.
        Returns list of dicts: {title, url, published_at, source_name, summary}
        """
        try:
            feed = feedparser.parse(url)
            if feed.bozo:
                print(f"Warning parsing {url}: {feed.bozo_exception}")
            
            items = []
            source_name = feed.feed.get('title', 'Unknown Source')
            
            for entry in feed.entries:
                item = {
                    'title': entry.get('title', 'No Title'),
                    'url': entry.get('link', ''),
                    'published_at': self.parse_date(entry),
                    'source_name': source_name,
                    'summary': entry.get('summary', '') or entry.get('description', '')
                }
                if item['url']:
                    items.append(item)
            
            return items
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return []
