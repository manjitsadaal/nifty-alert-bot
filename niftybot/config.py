"""Loads settings from the .env file next to the project root."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(exist_ok=True)


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(ROOT / ".env")


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    kite_api_key: str = _get("KITE_API_KEY")
    kite_api_secret: str = _get("KITE_API_SECRET")
    kite_redirect_port: int = int(_get("KITE_REDIRECT_PORT", "8765"))

    telegram_token: str = _get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = _get("TELEGRAM_CHAT_ID")
    telegram_bot_username: str = _get("TELEGRAM_BOT_USERNAME").lstrip("@")

    yahoo_symbol: str = _get("YAHOO_SYMBOL", "^NSEI")
    kite_exchange: str = _get("KITE_EXCHANGE", "INDICES")
    kite_symbol: str = _get("KITE_SYMBOL", "NIFTY 50")

    # How many Kite alerts to place above and below the reference price.
    alerts_each_side: int = int(_get("ALERTS_EACH_SIDE", "4"))
    # Levels closer than this (points) are merged into one zone.
    merge_distance: float = float(_get("MERGE_DISTANCE", "15"))
    # Only levels within this % of the reference price are used.
    max_distance_pct: float = float(_get("MAX_DISTANCE_PCT", "2.0"))
    # Buffer (points) a 15m close must clear a level by to count as a break.
    break_buffer: float = float(_get("BREAK_BUFFER", "5"))

    timezone: str = "Asia/Kolkata"


SETTINGS = Settings()
