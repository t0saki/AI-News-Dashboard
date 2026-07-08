import os
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

class ContactConfig(BaseModel):
    name: str = "Assistant"

class AppConfig:
    # Database
    DB_PATH: str = "data/news.db"
    
    # AI Provider
    AI_BASE_URL: str = os.getenv("AI_BASE_URL", "https://api.openai.com/v1")
    AI_API_KEY: str = os.getenv("AI_API_KEY", "")
    AI_MODEL_L1: str = os.getenv("AI_MODEL_L1", "gpt-4o-mini") # Fast model for L1
    AI_MODEL_L2: str = os.getenv("AI_MODEL_L2", "gpt-4o") # Strong model for L2
    # Hard safety caps on how many L1/L2 batches a single cycle may run. The
    # processors always drain each batch they touch, so these are normally not
    # reached; they exist purely to bound the loop if a batch ever fails to make
    # progress, so the pipeline can never hammer the LLM indefinitely.
    MAX_L1_LOOPS: int = int(os.getenv("MAX_L1_LOOPS", "40")) # Max L1 batches per cycle
    MAX_L2_LOOPS: int = int(os.getenv("MAX_L2_LOOPS", "40")) # Max L2 batches per cycle
    L1_BATCH_SIZE: int = int(os.getenv("L1_BATCH_SIZE", "30"))
    L2_BATCH_SIZE: int = int(os.getenv("L2_BATCH_SIZE", "20")) # Max items to send to L2 at once
    AI_MAX_RETRIES: int = int(os.getenv("AI_MAX_RETRIES", "2"))
    AI_RETRY_DELAY_SECONDS: float = float(os.getenv("AI_RETRY_DELAY_SECONDS", "1.0"))
    AI_TIMEOUT_SECONDS: float = float(os.getenv("AI_TIMEOUT_SECONDS", "600"))
    # How to handle response_format=json_object. Some OpenAI-compatible models
    # (e.g. Volc Ark / Doubao) reject it with HTTP 400. "auto" sends it and, on
    # such a 400, transparently retries without it and remembers the model;
    # "on" always sends it; "off" never sends it.
    AI_RESPONSE_FORMAT_MODE: str = os.getenv("AI_RESPONSE_FORMAT_MODE", "auto").lower()

    # Application Logic
    FETCH_INTERVAL_SECONDS: int = int(os.getenv("FETCH_INTERVAL_SECONDS", "600")) # 10 minutes
    GRAVITY: float = float(os.getenv("GRAVITY", "1.1")) # Gravity factor (Lower = less time decay, 0.8-1.2 recommended for 72h window)
    RANKING_WINDOW_HOURS: int = int(os.getenv("RANKING_WINDOW_HOURS", "72")) # Hours to look back for ranking
    DASHBOARD_OUTPUT_PATH: str = os.getenv("DASHBOARD_OUTPUT_PATH", "data/dashboard.json")
    TOP_N_ITEMS: int = int(os.getenv("TOP_N_ITEMS", "5")) # Number of items to output in top5.json

    # Quiet Hours (reduce update frequency during nighttime)
    QUIET_HOURS_ENABLED: bool = os.getenv("QUIET_HOURS_ENABLED", "true").lower() in ("true", "1", "yes")
    QUIET_HOURS_TZ_OFFSET: int = int(os.getenv("QUIET_HOURS_TZ_OFFSET", "8"))
    QUIET_HOURS_START: int = int(os.getenv("QUIET_HOURS_START", "22"))
    QUIET_HOURS_END: int = int(os.getenv("QUIET_HOURS_END", "10"))
    QUIET_HOURS_MULTIPLIER: int = int(os.getenv("QUIET_HOURS_MULTIPLIER", "4"))
    
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
