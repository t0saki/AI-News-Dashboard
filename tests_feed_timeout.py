"""
Tests for the feed download hard timeout and the cycle watchdog.

Regression target: on 2026-07-25 both workers hung forever inside
feedparser.parse(url) on a silent peer, freezing the whole pipeline while the
container still reported healthy.
"""
import os
import socket
import sys
import threading
import time

os.environ.setdefault("FEED_TIMEOUT_SECONDS", "3")
os.environ.setdefault("FEED_SOCKET_TIMEOUT_SECONDS", "2")

from config import config  # noqa: E402
from sources.rss import RSSFetcher  # noqa: E402

failures = []


def check(name, cond):
    print(f"  {'ok ' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(name)


def serve(handler):
    """Start a one-shot TCP server, return its port."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def run():
        try:
            conn, _ = srv.accept()
            handler(conn)
        except Exception:
            pass
        finally:
            srv.close()

    threading.Thread(target=run, daemon=True).start()
    return port


def test_silent_peer():
    """Peer accepts the connection and then says nothing: must not hang."""
    def handler(conn):
        time.sleep(30)  # outlives the budget; never sends a byte
        conn.close()

    port = serve(handler)
    start = time.monotonic()
    items = RSSFetcher().fetch(f"http://127.0.0.1:{port}/feed")
    elapsed = time.monotonic() - start
    check("silent peer gives up instead of hanging", elapsed < 10)
    check("silent peer returns no items", items == [])


def test_trickle_peer():
    """
    Peer sends valid headers then dribbles bytes slower than the total budget.
    Per-socket timeouts never fire here; only the wall-clock deadline saves us.
    """
    def handler(conn):
        conn.sendall(b"HTTP/1.0 200 OK\r\nContent-Type: application/rss+xml\r\n\r\n")
        try:
            for _ in range(60):
                conn.sendall(b"<item>")
                time.sleep(1)  # well under FEED_SOCKET_TIMEOUT_SECONDS
        except Exception:
            pass
        conn.close()

    port = serve(handler)
    start = time.monotonic()
    items = RSSFetcher().fetch(f"http://127.0.0.1:{port}/feed")
    elapsed = time.monotonic() - start
    # Upper bound: the deadline can only be overshot by one blocking socket read.
    check("slow trickle hits the wall-clock budget",
          config.FEED_TIMEOUT_SECONDS <= elapsed
          < config.FEED_TIMEOUT_SECONDS + config.FEED_SOCKET_TIMEOUT_SECONDS + 2)
    check("slow trickle returns no items", items == [])


def test_healthy_feed():
    """A normal feed still parses."""
    body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<rss version="2.0"><channel><title>Test Feed</title>'
        '<item><title>Hello</title><link>https://example.com/a</link>'
        '<description>Body</description>'
        '<pubDate>Mon, 27 Jul 2026 10:00:00 +0000</pubDate></item>'
        '</channel></rss>'
    ).encode()

    def handler(conn):
        conn.sendall(
            b"HTTP/1.0 200 OK\r\nContent-Type: application/rss+xml\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
        conn.close()

    port = serve(handler)
    items = RSSFetcher().fetch(f"http://127.0.0.1:{port}/feed")
    check("healthy feed parses one item", len(items) == 1)
    if items:
        check("title parsed", items[0]["title"] == "Hello")
        check("url parsed", items[0]["url"] == "https://example.com/a")
        check("source name parsed", items[0]["source_name"] == "Test Feed")


def test_oversized_feed():
    """Unbounded stream must be cut off rather than eating memory."""
    prev = config.FEED_MAX_BYTES
    config.FEED_MAX_BYTES = 4096

    def handler(conn):
        conn.sendall(b"HTTP/1.0 200 OK\r\nContent-Type: application/rss+xml\r\n\r\n")
        try:
            while True:
                conn.sendall(b"x" * 8192)
        except Exception:
            pass
        conn.close()

    try:
        port = serve(handler)
        items = RSSFetcher().fetch(f"http://127.0.0.1:{port}/feed")
        check("oversized feed rejected", items == [])
    finally:
        config.FEED_MAX_BYTES = prev


def test_watchdog_arm_disarm():
    """Watchdog must fire on a stuck cycle and stay quiet while sleeping."""
    os.makedirs("data", exist_ok=True)  # main -> database opens data/news.db at import
    import main

    main.config.WATCHDOG_CHECK_INTERVAL_SECONDS = 0.2
    main.config.CYCLE_TIMEOUT_SECONDS = 1

    exits = []
    real_exit = os._exit
    os._exit = lambda code: exits.append(code)  # type: ignore[assignment]
    try:
        threading.Thread(target=main.watchdog_loop, daemon=True).start()

        main.disarm_watchdog()
        time.sleep(1.5)
        check("idle (sleeping) never trips the watchdog", exits == [])

        main.arm_watchdog()
        time.sleep(2.0)
        check("stuck cycle trips the watchdog", exits and exits[0] == 1)

        main.disarm_watchdog()
    finally:
        os._exit = real_exit  # type: ignore[assignment]


if __name__ == "__main__":
    for test in (test_silent_peer, test_trickle_peer, test_healthy_feed,
                 test_oversized_feed, test_watchdog_arm_disarm):
        print(f"{test.__name__}:")
        test()
    print()
    if failures:
        print(f"RESULT: {len(failures)} FAILED -> {failures}")
        sys.exit(1)
    print("RESULT: ALL PASS")
