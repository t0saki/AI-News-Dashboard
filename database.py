import sqlite3
import json
import time
from typing import List, Dict, Optional, Any
from config import config

class Database:
    def __init__(self, db_path: str = config.DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # News table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                title TEXT,
                source_name TEXT,
                published_at REAL,
                fetched_at REAL,
                
                -- L1 Analysis
                l1_score INTEGER DEFAULT 0,
                l1_reason TEXT,
                
                -- L2 Analysis
                l2_score INTEGER DEFAULT 0,
                l2_summary TEXT,
                l2_title_zh TEXT,
                category TEXT,
                
                -- Status
                status TEXT DEFAULT 'pending' -- pending, filtered, processed
            )
        ''')
        
        conn.commit()
        conn.close()

    def add_news(self, url: str, title: str, source_name: str, published_at: float) -> bool:
        """Returns True if added, False if already exists."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO news (url, title, source_name, published_at, fetched_at, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
            ''', (url, title, source_name, published_at, time.time()))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def get_pending_news(self, limit: int = 20) -> List[Dict]:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM news WHERE status = 'pending' LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def update_l1_result(self, news_id: int, score: int, reason: str, status: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE news 
            SET l1_score = ?, l1_reason = ?, status = ?
            WHERE id = ?
        ''', (score, reason, status, news_id))
        conn.commit()
        conn.close()

    def get_high_score_pending_l2(self, min_score: int = 70, limit: int = 20) -> List[Dict]:
        """Get news that passed L1 but haven't been processed by L2 yet."""
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # We define a temporary status 'l1_passed' or just check if score is high and l2_score is 0/default?
        # Let's rely on 'status' being 'filtered' if it failed.
        # Use a new L2 check: if status='processed' check if l2 is done?
        # Actually simplest is: Status='pending' -> L1 -> Status='filtered' (if fail) OR 'l1_done' (if success)
        # Then L2 picks up 'l1_done' -> Status='processed'
        
        # Let's adjust status logic in code.
        # But for now, let's look for "l1_done" status.
        cursor.execute("SELECT * FROM news WHERE status = 'l1_done' AND l1_score >= ? LIMIT ?", (min_score, limit))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def update_l2_result(self, news_id: int, score: int, summary: str, title_zh: str, category: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE news 
            SET l2_score = ?, l2_summary = ?, l2_title_zh = ?, category = ?, status = 'processed'
            WHERE id = ?
        ''', (score, summary, title_zh, category, news_id))
        conn.commit()
        conn.close()

    def get_processed_news(self, limit: int = 50) -> List[Dict]:
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM news WHERE status = 'processed' ORDER BY published_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
        
    def get_conn(self):
        return self._get_conn()

    def get_recent_processed_news(self, hours: int = config.RANKING_WINDOW_HOURS) -> List[Dict]:
        """Get all processed news from the last N hours."""
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cutoff = time.time() - (hours * 3600)
        cursor.execute("SELECT * FROM news WHERE status = 'processed' AND published_at > ? ORDER BY published_at DESC", (cutoff,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

db = Database()
