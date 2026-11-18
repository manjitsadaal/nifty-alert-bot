"""Commands: day, cloud, login, plan, alerts, monitor, eod, clear, chatid, test.

`day`   - runs on your own PC (browser login on the same machine)
`cloud` - runs on GitHub Actions; login happens from your iPad/phone via Telegram
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time as _time
from datetime import time

from . import data, telegram
from .brief import morning_brief
from .chart import render
from .config import SETTINGS, STATE_DIR
from .kite_api import (KiteAlerts, KiteError, get_token, interactive_login, load_token,
                       login_url, login_with_request_token)
from .levels import DayPlan, Zone, build_plan
from .signals import completed_today, scan

PLAN_FILE = STATE_DIR / "plan.json"
SIGNALS_FILE = STATE_DIR / "signals_sent.json"
ALERT_COUNTS_FILE = STATE_DIR / "alert_counts.json"
RUNTIME_FILE = STATE_DIR / "runtime.json"

MARKET_OPEN, MARKET_CLOSE = time(9, 15), time(15, 30)
ALERTS_AT = time(9, 17)
HELP = ("<b>Commands</b>\n/levels – resend today's levels\n/chart – chart with levels now\n/alerts – reset Kite alerts around current price\n"
        "/status – bot status\n/login – get the Kite login link\n/help – this list")


def _load(path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return default


def _save(path, obj) -> None:
    path.write_text(json.dumps(obj))


def _today() -> str:
    return data.now_ist().strftime("%Y-%m-%d")


# ------------------------------------------------------------------ plan
def make_plan(use_live: bool = False) -> DayPlan:
    daily = data.daily_completed()
    ref = None
    if use_live:
        try:
            ref = data.last_price()
        except Exception as e:  # noqa: BLE001
            print(f"Live price unavailable ({e}); using previous close")
    plan = build_plan(daily, reference=ref, merge_distance=SETTINGS.merge_distance,
                      max_distance_pct=SETTINGS.max_distance_pct)
    _save(PLAN_FILE, {"made_on": _today(), **plan.to_dict()})
    return plan


def load_zones() -> list[Zone]:
    d = _load(PLAN_FILE, {})
    if d.get("made_on") != _today():
        return []
    return [Zone(price=z["price"], tags=z["tags"], low=z["low"], high=z["high"])
            for z in d.get("zones", [])]


def send_chart(title: str, caption: str = "", zones: list[Zone] | None = None,
               reference: float | None = None, marker: dict | None = None, silent: bool = False) -> None:
    """Draws the 15m chart with levels and sends it to Telegram. Never raises."""
    try:
        if zones is None or reference is None:
            d = _load(PLAN_FILE, {})
            zones = zones if zones is not None else load_zones()
            reference = reference if reference is not None else float(d.get("reference") or 0)
        df = data.intraday("15m", 5)
        if not reference and not df.empty:
            reference = float(df["Close"].iloc[-1])
        png = render(df, zones, reference, title, marker=marker)
        telegram.send_photo(png, caption, silent=silent)
    except Exception as e:  # noqa: BLE001
        print(f"Chart failed: {e}")
        if caption:
            telegram.send(caption, silent=silent)


def cmd_plan(send: bool = True) -> DayPlan:
    live = data.now_ist().time() >= MARKET_OPEN
    plan = make_plan(use_live=live)
    note = " (live)" if live else " (prev close; check GIFT Nifty for gap)"
    msg = morning_brief(plan, SETTINGS.alerts_each_side + 1, note)
    if send:
        send_chart(f"NIFTY 50 levels for {_today()}", zones=plan.zones, reference=plan.reference)
        telegram.send(msg)
    else:
        print(msg)
    return plan


# ---------------------------------------------------------------- alerts
def cmd_alerts(plan: DayPlan | None = None, token: str | None = None) -> None:
    plan = plan or make_plan(use_live=True)
    kite = KiteAlerts(token or get_token())
    removed = kite.delete_bot_alerts()
    n = SETTINGS.alerts_each_side
    made, counts = [], {}
    for side, zones, op in (("R", plan.above(n), ">="), ("S", plan.below(n), "<=")):
        for z in zones:
            a = kite.create(f"{side} {z.price:.0f} {z.label}", op, z.price)
            made.append(f"{'↑' if side == 'R' else '↓'} {z.price:,.0f} {z.label}")
            counts[a["uuid"]] = {"count": a.get("alert_count", 0), "price": z.price,
                                 "label": z.label, "dir": "up" if side == "R" else "down"}
    _save(ALERT_COUNTS_FILE, counts)
    telegram.send(f"<b>Kite alerts set</b> (ref {plan.reference:,.0f}; removed {removed} old)\n"
                  + "\n".join(telegram.esc(m) for m in made)
                  + "\nKite app will push when each is crossed.", silent=True)


def _check_kite_triggers(kite: KiteAlerts) -> None:
    known = _load(ALERT_COUNTS_FILE, {})
    if not known:
        return
    for a in kite.bot_alerts():
        k = known.get(a["uuid"])
        if not k:
            continue
        cnt = int(a.get("alert_count") or 0)
        if cnt > int(k["count"]):
            k["count"] = cnt
            verb = "crossed ABOVE" if k["dir"] == "up" else "dropped BELOW"
            telegram.send(f"⚡ <b>Nifty {verb} {k['price']:,.0f}</b> [{telegram.esc(k['label'])}]\n"
                          "Touch only — wait for a 15m close beyond it to confirm, "
                          "or a rejection wick to fade it.")
    _save(ALERT_COUNTS_FILE, known)


# --------------------------------------------------------------- runtime
class Runtime:
    """One loop that handles login, alerts, signals and Telegram commands."""

    def __init__(self, telegram_login: bool):
        self.telegram_login = telegram_login
        st = _load(RUNTIME_FILE, {})
        if st.get("date") != _today():
            st = {"date": _today(), "alerts_set": False, "login_sent": False,
                  "holiday_checked": False, "midday_sent": False, "tg_offset": st.get("tg_offset")}
        self.st = st
        sent = _load(SIGNALS_FILE, {})
        self.sent = sent if sent.get("date") == _today() else {"date": _today(), "keys": []}
        self.zones = load_zones() or make_plan(use_live=data.now_ist().time() >= MARKET_OPEN).zones
        self.last_candle = None
        self.token = load_token()
        self.stop = False

    def persist(self) -> None:
        _save(RUNTIME_FILE, self.st)
        _save(SIGNALS_FILE, self.sent)

    # --- Kite login via Telegram ---
    def send_login_link(self) -> None:
        telegram.send("🔑 <b>Kite login needed for today's alerts</b>\n"
                      f"1. Tap: <a href=\"{html.escape(login_url(), quote=True)}\">Log in to Kite</a>\n"
                      "2. After login, tap <b>Send to bot</b> on the page that opens "
                      "(or paste that page's full URL here).")
        self.st["login_sent"] = True

    def try_login(self, text: str) -> bool:
        m = (re.search(r"request_token=([A-Za-z0-9]+)", text)
             or re.match(r"^/start\s+([A-Za-z0-9]{20,64})\s*$", text.strip())
             or re.match(r"^([A-Za-z0-9]{32})$", text.strip()))
        if not m:
            return False
        try:
            self.token = login_with_request_token(m.group(1))
            telegram.send("✅ Kite login OK.")
            if data.now_ist().time() >= ALERTS_AT:
                self.set_alerts()
        except KiteError as e:
            telegram.send(f"❌ Kite login failed: {telegram.esc(e)}\nSend /login for a fresh link.")
        return True

    def set_alerts(self) -> None:
        if not self.token:
            return
        try:
            plan = make_plan(use_live=True)
            self.zones = plan.zones
            cmd_alerts(plan, self.token)
            self.st["alerts_set"] = True
        except Exception as e:  # noqa: BLE001
            telegram.send(f"⚠️ Could not set Kite alerts: {telegram.esc(e)}")
            self.st["alerts_set"] = True  # don't retry in a loop; /alerts retries manually

    # --- Telegram commands ---
    def handle_messages(self) -> None:
        first_run = self.st.get("tg_offset") is None
        ups = telegram.get_updates(self.st.get("tg_offset"))
        if first_run and not ups:
            self.st["tg_offset"] = 0
        for u in ups:
            self.st["tg_offset"] = u["update_id"] + 1
            if first_run or not u["_mine"]:
                continue  # first run: skip old backlog; always ignore other chats
            text = u["_text"].strip()
            if self.try_login(text):
                continue
            cmd = text.split()[0].lower() if text else ""
            if cmd == "/levels":
                cmd_plan()
            elif cmd == "/chart":
                send_chart(f"NIFTY 50 · {data.now_ist():%d %b %H:%M}", zones=self.zones)
            elif cmd == "/alerts":
                self.set_alerts() if self.token else self.send_login_link()
            elif cmd == "/login":
                self.send_login_link()
            elif cmd == "/status":
                telegram.send(f"Running. Kite login: {'✅' if self.token else '❌'} · "
                              f"alerts set: {'✅' if self.st['alerts_set'] else '❌'} · "
                              f"signals today: {len(self.sent['keys'])}")
            elif cmd in ("/help", "/start"):
                telegram.send(HELP)

    # --- 15m price action ---
    def check_signals(self, now) -> None:
        try:
            df = data.intraday("15m", 2)
        except Exception as e:  # noqa: BLE001
            print(f"Data error: {e}")
            return
        if not self.st["holiday_checked"] and now.time() >= time(9, 40):
            self.st["holiday_checked"] = True
            if df.empty or not (df.index.date == now.date()).any():
                telegram.send("No Nifty candles today — market holiday? Bot stopping for the day.", silent=True)
                self.stop = True
                return
        today = completed_today(df, now)
        if not len(today) or today.index[-1] == self.last_candle:
            return
        self.last_candle = today.index[-1]
        new = [sig for sig in scan(today, self.zones, SETTINGS.break_buffer)
               if sig.key not in self.sent["keys"]]
        if not new:
            return
        self.sent["keys"] += [sig.key for sig in new]
        parts = [f"{'🟢' if sig.direction == 'up' else '🔴'} <b>{telegram.esc(sig.kind)}</b>\n"
                 f"{telegram.esc(sig.text)}" for sig in new]
        caption = "\n\n".join(parts) + "\n<i>Yahoo data, may lag 1–2 min. Confirm on Kite chart.</i>"
        main = new[0]
        send_chart(f"NIFTY 50 · {main.kind} · {data.now_ist():%H:%M}", caption, zones=self.zones,
                   marker={"price": main.price, "direction": main.direction, "text": main.kind})

    def run(self, until: time, max_seconds: float | None = None) -> None:
        started = _time.monotonic()
        while not self.stop:
            now = data.now_ist()
            if now.time() >= until or (max_seconds and _time.monotonic() - started > max_seconds):
                break
            if self.telegram_login and not self.token and not self.st["login_sent"]:
                self.send_login_link()
            self.handle_messages()
            if self.token and not self.st["alerts_set"] and now.time() >= ALERTS_AT:
                self.set_alerts()
            if MARKET_OPEN <= now.time() <= MARKET_CLOSE:
                if self.token and now.second < 20:
                    try:
                        _check_kite_triggers(KiteAlerts(self.token))
                    except Exception as e:  # noqa: BLE001
                        print(f"Kite check failed: {e}")
                m = now.minute % 15
                if (m == 0 and now.second >= 40) or m == 1:
                    self.check_signals(now)
                if not self.st.get("midday_sent") and now.time() >= time(12, 31):
                    self.st["midday_sent"] = True
                    send_chart(f"NIFTY 50 · midday update {now:%H:%M}", zones=self.zones, silent=True)
            self.persist()
            _time.sleep(20)
        self.persist()


# -------------------------------------------------------------------- eod
def cmd_eod() -> None:
    removed = 0
    token = load_token()
    if token:
        try:
            removed = KiteAlerts(token).delete_bot_alerts()
        except KiteError as e:
            print(f"Skip alert cleanup: {e}")
    msg = f"<b>Day closed.</b> Removed {removed} bot alerts."
    try:
        df = data.intraday("15m", 1)
        today = df[df.index.date == data.now_ist().date()]
        if len(today):
            o, h, l, c = (float(today["Open"].iloc[0]), float(today["High"].max()),
                          float(today["Low"].min()), float(today["Close"].iloc[-1]))
            msg += f"\nNifty O {o:,.0f} H {h:,.0f} L {l:,.0f} C {c:,.0f} ({c - o:+,.0f} from open)"
        hits = _load(SIGNALS_FILE, {}).get("keys", [])
        if hits:
            msg += f"\nSignals fired: {len(hits)} ({telegram.esc(', '.join(hits[:12]))})"
    except Exception as e:  # noqa: BLE001
        print(f"EOD summary error: {e}")
    telegram.send(msg, silent=True)


# ------------------------------------------------------------ day / cloud
def cmd_day() -> None:
    """Own-PC routine: start before 9:15 on a trading day."""
    if data.now_ist().weekday() >= 5:
        print("Weekend — nothing to do.")
        return
    try:
        get_token()  # browser login on this PC if needed
    except KiteError as e:
        telegram.send(f"⚠️ Kite login failed: {telegram.esc(e)}. Alerts skipped; signals still on.")
    cmd_plan()
    Runtime(telegram_login=False).run(until=MARKET_CLOSE)
    cmd_eod()


def cmd_cloud(part: str) -> None:
    """GitHub Actions routine. 'morning' runs ~08:30-14:10, 'afternoon' ~14:15-15:30."""
    if data.now_ist().weekday() >= 5:
        print("Weekend — nothing to do.")
        return
    if part == "morning":
        cmd_plan()
        rt = Runtime(telegram_login=True)
        # GitHub caps a job at 6h; stop by 14:10 IST or after 5h40m, whichever is first.
        rt.run(until=time(14, 10), max_seconds=5 * 3600 + 40 * 60)
        if rt.stop:
            cmd_eod()
    else:
        rt = Runtime(telegram_login=True)
        rt.run(until=time(15, 31))
        cmd_eod()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="run.py", description="Nifty level + alert bot")
    ap.add_argument("command", choices=["day", "cloud", "login", "plan", "alerts", "monitor",
                                        "eod", "clear", "chatid", "test"])
    ap.add_argument("part", nargs="?", default="morning", help="cloud: morning | afternoon")
    ap.add_argument("--print", action="store_true", help="plan: print instead of sending")
    a = ap.parse_args(argv)
    if a.command == "day":
        cmd_day()
    elif a.command == "cloud":
        cmd_cloud(a.part)
    elif a.command == "login":
        interactive_login()
        print("Kite login OK for today.")
    elif a.command == "plan":
        cmd_plan(send=not a.print)
    elif a.command == "alerts":
        cmd_alerts()
    elif a.command == "monitor":
        Runtime(telegram_login=False).run(until=MARKET_CLOSE)
    elif a.command == "eod":
        cmd_eod()
    elif a.command == "clear":
        print(f"Deleted {KiteAlerts(get_token()).delete_bot_alerts()} bot alerts.")
    elif a.command == "chatid":
        cid = telegram.find_chat_id()
        print(f"TELEGRAM_CHAT_ID={cid}" if cid else "Send any message to your bot first, then rerun.")
    elif a.command == "test":
        ok = telegram.send("✅ Nifty bot connected.")
        print("Telegram OK" if ok else "Telegram failed — check token/chat id.")


if __name__ == "__main__":
    sys.exit(main())
