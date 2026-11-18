"""Minimal Telegram sender (HTML formatting)."""
from __future__ import annotations

import html

import requests

from .config import SETTINGS


def esc(text: str) -> str:
    return html.escape(str(text), quote=False)


def send(text: str, silent: bool = False) -> bool:
    s = SETTINGS
    if not s.telegram_token or not s.telegram_chat_id:
        print("[telegram disabled]\n" + text)
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{s.telegram_token}/sendMessage", timeout=15,
                          data={"chat_id": s.telegram_chat_id, "text": text[:4000],
                                "parse_mode": "HTML", "disable_notification": silent,
                                "disable_web_page_preview": True})
        if r.status_code != 200:
            print(f"Telegram error {r.status_code}: {r.text[:200]}")
        return r.status_code == 200
    except requests.RequestException as e:
        print(f"Telegram send failed: {e}")
        return False


def send_photo(png: bytes, caption: str = "", silent: bool = False) -> bool:
    s = SETTINGS
    if not s.telegram_token or not s.telegram_chat_id:
        print("[telegram disabled] photo:", caption[:200])
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{s.telegram_token}/sendPhoto", timeout=30,
                          data={"chat_id": s.telegram_chat_id, "caption": caption[:1000],
                                "parse_mode": "HTML", "disable_notification": silent},
                          files={"photo": ("nifty.png", png, "image/png")})
        if r.status_code != 200:
            print(f"Telegram photo error {r.status_code}: {r.text[:200]}")
        return r.status_code == 200
    except requests.RequestException as e:
        print(f"Telegram photo failed: {e}")
        return False


def get_updates(offset: int | None) -> list[dict]:
    """New messages since `offset`. Only messages from YOUR chat id are returned."""
    s = SETTINGS
    if not s.telegram_token:
        return []
    params = {"timeout": 0, "allowed_updates": '["message"]'}
    if offset is not None:
        params["offset"] = offset
    try:
        r = requests.get(f"https://api.telegram.org/bot{s.telegram_token}/getUpdates",
                         params=params, timeout=20)
        res = r.json().get("result", [])
    except (requests.RequestException, ValueError):
        return []
    for u in res:
        chat = (u.get("message") or {}).get("chat", {})
        u["_mine"] = str(chat.get("id")) == str(s.telegram_chat_id)
        u["_text"] = (u.get("message") or {}).get("text", "") or ""
    return res


def find_chat_id() -> str | None:
    """After you send any message to your bot, this returns your chat id."""
    r = requests.get(f"https://api.telegram.org/bot{SETTINGS.telegram_token}/getUpdates", timeout=15)
    for upd in reversed(r.json().get("result", [])):
        chat = (upd.get("message") or upd.get("channel_post") or {}).get("chat")
        if chat:
            return str(chat["id"])
    return None
