import os
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

class ContactConfig(BaseModel):
    name: str = "Assistant"

class AppConfig:
    # Database
    DB_PATH: str = "news.db"
    
    # AI Provider
    AI_BASE_URL: str = os.getenv("AI_BASE_URL", "https://api.openai.com/v1")
    AI_API_KEY: str = os.getenv("AI_API_KEY", "")
    AI_MODEL_L1: str = os.getenv("AI_MODEL_L1", "gpt-4o-mini") # Fast model for L1
    AI_MODEL_L2: str = os.getenv("AI_MODEL_L2", "gpt-4o") # Strong model for L2
    MAX_L1_LOOPS: int = int(os.getenv("MAX_L1_LOOPS", "5")) # Number of L1 batches to process per cycle
    L1_BATCH_SIZE: int = int(os.getenv("L1_BATCH_SIZE", "30"))
    L2_BATCH_SIZE: int = int(os.getenv("L2_BATCH_SIZE", "20")) # Max items to send to L2 at once

    # Application Logic
    FETCH_INTERVAL_SECONDS: int = int(os.getenv("FETCH_INTERVAL_SECONDS", "600")) # 10 minutes
    GRAVITY: float = float(os.getenv("GRAVITY", "1.1")) # Gravity factor (Lower = less time decay, 0.8-1.2 recommended for 72h window)
    RANKING_WINDOW_HOURS: int = int(os.getenv("RANKING_WINDOW_HOURS", "72")) # Hours to look back for ranking
    DASHBOARD_OUTPUT_PATH: str = os.getenv("DASHBOARD_OUTPUT_PATH", "dashboard.json")
    
    # Sources
    RSS_FEEDS: List[str] = [
        "https://spaceflightnow.com/feed/",
        "https://hnrss.org/newest?points=100",
    ]

    def __init__(self):
        rss_env = os.getenv("RSS_FEEDS")
        if rss_env:
            try:
                import json
                self.RSS_FEEDS = json.loads(rss_env)
            except Exception as e:
                print(f"Warning: Failed to parse RSS_FEEDS from environment: {e}")
    
    # Proxy
    HTTP_PROXY: Optional[str] = os.getenv("HTTP_PROXY")
    HTTPS_PROXY: Optional[str] = os.getenv("HTTPS_PROXY")

config = AppConfig()
