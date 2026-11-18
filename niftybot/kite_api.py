"""Zerodha Kite Connect (free Personal plan): daily login + alerts.

The Personal plan has no market data, but it can create, list and delete
Kite alerts. Kite then sends its normal push notification / email when an
alert triggers, on web and on the phone app.
"""
from __future__ import annotations

import hashlib
import http.server
import json
import threading
import urllib.parse
import webbrowser
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from .config import SETTINGS, STATE_DIR
from .secure import decrypt, encrypt

API = "https://api.kite.trade"
LOGIN_URL = "https://kite.zerodha.com/connect/login?v=3&api_key={key}"
TOKEN_FILE = STATE_DIR / "kite_token.json"
BOT_PREFIX = "NB"  # every alert this bot creates starts with this, so cleanup never touches yours


class KiteError(RuntimeError):
    pass


# ---------------------------------------------------------------- login
def _ist_date() -> str:
    return datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")


def _save_token(token: str) -> None:
    # Stored encrypted (key derived from your API secret), so the cloud cache never holds it in plain text.
    TOKEN_FILE.write_text(json.dumps({"token": encrypt(token), "date": _ist_date()}))


def load_token() -> str | None:
    """Kite tokens expire every morning (~6 AM), so only today's token is valid."""
    if not TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(TOKEN_FILE.read_text())
        if data.get("date") != _ist_date():
            return None
        return decrypt(data["token"])
    except Exception:  # noqa: BLE001 - corrupt/old file: treat as logged out
        return None


def login_url() -> str:
    url = LOGIN_URL.format(key=SETTINGS.kite_api_key)
    if SETTINGS.telegram_bot_username:
        # Kite passes these back to the redirect page, which uses them to open your bot.
        url += "&redirect_params=" + urllib.parse.quote(f"bot={SETTINGS.telegram_bot_username}")
    return url


def login_with_request_token(request_token: str) -> str:
    token = _exchange(request_token)
    _save_token(token)
    return token


def _exchange(request_token: str) -> str:
    s = SETTINGS
    checksum = hashlib.sha256((s.kite_api_key + request_token + s.kite_api_secret).encode()).hexdigest()
    r = requests.post(f"{API}/session/token", headers={"X-Kite-Version": "3"}, timeout=20,
                      data={"api_key": s.kite_api_key, "request_token": request_token,
                            "checksum": checksum})
    body = r.json()
    if r.status_code != 200 or body.get("status") != "success":
        raise KiteError(f"Login failed: {body.get('message', r.text)}")
    return body["data"]["access_token"]


def interactive_login(timeout_sec: int = 600) -> str:
    """Opens the Kite login page in your browser and catches the redirect locally.

    In the Kite developer console the app's Redirect URL must be
    http://127.0.0.1:<KITE_REDIRECT_PORT>/callback (default port 8765).
    """
    s = SETTINGS
    if not s.kite_api_key or not s.kite_api_secret:
        raise KiteError("KITE_API_KEY / KITE_API_SECRET missing in .env")
    got: dict = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            ok = got.get("status") == "success" and "request_token" in got
            msg = "Login captured. You can close this tab." if ok else "Login failed, check the terminal."
            self.wfile.write(f"<h2>Nifty bot: {msg}</h2>".encode())
            done.set()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", s.kite_redirect_port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = LOGIN_URL.format(key=s.kite_api_key)
    print(f"Opening Kite login: {url}")
    webbrowser.open(url)
    finished = done.wait(timeout_sec)
    server.shutdown()
    if not finished or "request_token" not in got:
        raise KiteError("No login received (timed out or cancelled).")
    token = _exchange(got["request_token"])
    _save_token(token)
    return token


def get_token(allow_interactive: bool = True) -> str:
    token = load_token()
    if token:
        return token
    if not allow_interactive:
        raise KiteError("No Kite token for today. Run: python run.py login")
    return interactive_login()


# ---------------------------------------------------------------- alerts
class KiteAlerts:
    def __init__(self, token: str):
        self.h = {"X-Kite-Version": "3",
                  "Authorization": f"token {SETTINGS.kite_api_key}:{token}"}

    def _call(self, method: str, path: str, **kw):
        r = requests.request(method, f"{API}{path}", headers=self.h, timeout=20, **kw)
        try:
            body = r.json()
        except ValueError:
            raise KiteError(f"{method} {path}: HTTP {r.status_code} {r.text[:200]}")
        if body.get("status") != "success":
            raise KiteError(f"{method} {path}: {body.get('message')} ({body.get('error_type')})")
        return body.get("data")

    def list(self) -> list[dict]:
        return self._call("GET", "/alerts") or []

    def bot_alerts(self) -> list[dict]:
        return [a for a in self.list() if str(a.get("name", "")).startswith(BOT_PREFIX)]

    def create(self, name: str, operator: str, price: float) -> dict:
        assert operator in (">=", "<=")
        return self._call("POST", "/alerts", data={
            "name": f"{BOT_PREFIX} {name}"[:50],
            "type": "simple",
            "lhs_exchange": SETTINGS.kite_exchange,
            "lhs_tradingsymbol": SETTINGS.kite_symbol,
            "lhs_attribute": "LastTradedPrice",
            "operator": operator,
            "rhs_type": "constant",
            "rhs_constant": f"{price:.2f}",
        })

    def delete(self, uuids: list[str]) -> None:
        if uuids:
            self._call("DELETE", "/alerts", params=[("uuid", u) for u in uuids])

    def delete_bot_alerts(self) -> int:
        ids = [a["uuid"] for a in self.bot_alerts()]
        for i in range(0, len(ids), 20):
            self.delete(ids[i:i + 20])
        return len(ids)
