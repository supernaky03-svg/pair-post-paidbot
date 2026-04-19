
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Set

from dotenv import load_dotenv

load_dotenv()


def _split_ints(value: str) -> Set[int]:
    result: Set[int] = set()
    for item in (value or "").split(","):
        item = item.strip()
        if not item:
            continue
        result.add(int(item))
    return result


@dataclass(slots=True)
class Settings:
    bot_token: str
    api_id: int
    api_hash: str
    telethon_session_string: str
    database_url: str
    admin_ids: Set[int]
    log_level: str
    host: str
    port: int
    delay_min_seconds: int
    delay_max_seconds: int
    poll_interval_seconds: int
    latest_recheck_limit: int
    default_scan_count: int
    recent_ids_limit: int
    default_pair_limit: int
    health_path: str


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    settings = Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        api_id=int(os.getenv("API_ID", "0")),
        api_hash=os.getenv("API_HASH", "").strip(),
        telethon_session_string=os.getenv("TELETHON_SESSION_STRING", "").strip(),
        database_url=os.getenv("DATABASE_URL", "").strip(),
        admin_ids=_split_ints(os.getenv("ADMIN_IDS", "")),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "10000")),
        delay_min_seconds=int(os.getenv("DELAY_MIN_SECONDS", "20")),
        delay_max_seconds=int(os.getenv("DELAY_MAX_SECONDS", "50")),
        poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "180")),
        latest_recheck_limit=int(os.getenv("LATEST_RECHECK_LIMIT", "10")),
        default_scan_count=int(os.getenv("DEFAULT_SCAN_COUNT", "100")),
        recent_ids_limit=int(os.getenv("RECENT_IDS_LIMIT", "100")),
        default_pair_limit=int(os.getenv("DEFAULT_PAIR_LIMIT", "20")),
        health_path=os.getenv("HEALTH_PATH", "/health"),
    )
    if not settings.bot_token:
        raise ValueError("BOT_TOKEN is required")
    if not settings.api_id or not settings.api_hash:
        raise ValueError("API_ID and API_HASH are required")
    if not settings.database_url:
        raise ValueError("DATABASE_URL is required")
    return settings
