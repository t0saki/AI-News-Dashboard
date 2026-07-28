import feedparser
import time
import calendar
import socket
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from urllib.request import Request, urlopen

from config import config

USER_AGENT = "Mozilla/5.0 (compatible; AI-News-Dashboard/1.0; +https://github.com/t0saki/AI-News-Dashboard)"


class FeedTimeout(Exception):
    """Raised when a feed exceeds its wall-clock download budget."""


class RSSFetcher:
    def parse_date(self, entry) -> float:
        """Parse published date to timestamp."""
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            return calendar.timegm(entry.published_parsed)
        if hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            return calendar.timegm(entry.updated_parsed)
        return time.time()

    def download(self, url: str) -> Tuple[bytes, str]:
        """
        Downloads a feed with hard timeouts.

        feedparser.parse(url) delegates to urllib without any timeout, so a peer
        that accepts the connection and then goes silent blocks forever (this took
        the whole pipeline down on 2026-07-25). We fetch the bytes ourselves with
        both a per-socket timeout and a total wall-clock deadline, then hand the
        raw bytes to feedparser.
        """
        deadline = time.monotonic() + config.FEED_TIMEOUT_SECONDS
        socket_timeout = min(config.FEED_SOCKET_TIMEOUT_SECONDS, config.FEED_TIMEOUT_SECONDS)
        request = Request(url, headers={'User-Agent': USER_AGENT})

        with urlopen(request, timeout=socket_timeout) as response:
            content_type = response.headers.get('Content-Type', '')
            # read1() returns whatever one underlying socket read yields, so each
            # call blocks at most the socket timeout and we get to re-check the
            # deadline. Plain read(n) would sit there until n bytes or EOF, which
            # lets a slow trickle outlast the budget.
            read_chunk = getattr(response, 'read1', response.read)
            chunks = []
            total = 0
            while True:
                if time.monotonic() > deadline:
                    raise FeedTimeout(
                        f"exceeded {config.FEED_TIMEOUT_SECONDS:.0f}s budget after {total} bytes")
                chunk = read_chunk(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > config.FEED_MAX_BYTES:
                    raise FeedTimeout(
                        f"feed larger than FEED_MAX_BYTES ({config.FEED_MAX_BYTES} bytes)")
                chunks.append(chunk)

        return b''.join(chunks), content_type

    def fetch(self, url: str) -> List[Dict]:
        """
        Fetches an RSS feed and returns normalized items.
        Returns list of dicts: {title, url, published_at, source_name, summary}
        """
        try:
            raw, content_type = self.download(url)
            feed = feedparser.parse(
                raw, response_headers={'content-type': content_type} if content_type else None)
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
        except (FeedTimeout, socket.timeout, TimeoutError) as e:
            print(f"Timeout fetching {url}: {e}")
            return []
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return []
