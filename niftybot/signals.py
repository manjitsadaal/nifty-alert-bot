"""Price-action signals on completed 15-minute candles.

Signals (each fires at most once per level/direction per day):
  * ORB break      - 15m close outside the 9:15-9:45 opening range
  * Level break    - 15m close through a zone after closing on the other side
  * Rejection      - wick pierces a zone but the candle closes back, wick >= 50% of range
  * Momentum bar   - candle range >= 1.8x the average of the previous 20 candles
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import pandas as pd

from .levels import Zone


@dataclass
class Signal:
    key: str
    kind: str
    direction: str  # "up" / "down"
    price: float
    text: str


def _fmt(x: float) -> str:
    return f"{x:,.0f}"


def completed_today(df15: pd.DataFrame, now) -> pd.DataFrame:
    if df15.empty:
        return df15
    today = df15[df15.index.date == now.date()]
    # A 15m candle stamped 10:00 is complete at 10:15.
    return today[today.index + pd.Timedelta(minutes=15) <= now]


def opening_range(today: pd.DataFrame) -> tuple[float, float] | None:
    orb = today[(today.index.time >= time(9, 15)) & (today.index.time < time(9, 45))]
    if len(orb) < 2:
        return None
    return float(orb["High"].max()), float(orb["Low"].min())


def scan(today: pd.DataFrame, zones: list[Zone], buffer: float) -> list[Signal]:
    """Look at the latest completed candle (and the one before it)."""
    out: list[Signal] = []
    if len(today) < 1:
        return out
    c = today.iloc[-1]
    o, h, l, cl = (float(c[k]) for k in ("Open", "High", "Low", "Close"))
    prev_close = float(today.iloc[-2]["Close"]) if len(today) > 1 else o
    stamp = today.index[-1].strftime("%H:%M")
    rng = max(h - l, 0.01)

    # ORB
    orng = opening_range(today)
    if orng and today.index[-1].time() >= time(9, 45):
        oh, ol = orng
        if cl > oh + buffer:
            out.append(Signal("ORB_UP", "ORB break", "up", cl,
                              f"15m close {_fmt(cl)} above opening range high {_fmt(oh)} "
                              f"(range {_fmt(ol)}-{_fmt(oh)}). Bullish ORB; invalid back below {_fmt(oh)}."))
        elif cl < ol - buffer:
            out.append(Signal("ORB_DOWN", "ORB break", "down", cl,
                              f"15m close {_fmt(cl)} below opening range low {_fmt(ol)} "
                              f"(range {_fmt(ol)}-{_fmt(oh)}). Bearish ORB; invalid back above {_fmt(ol)}."))

    for z in zones:
        name = f"{_fmt(z.price)} [{z.label}]"
        # Breaks
        if prev_close <= z.high and cl > z.high + buffer:
            out.append(Signal(f"BRK_UP_{z.price:.0f}", "Level break", "up", cl,
                              f"15m candle ({stamp}) closed {_fmt(cl)} ABOVE {name}. "
                              f"Next: watch a retest of {_fmt(z.high)} holding as support."))
        elif prev_close >= z.low and cl < z.low - buffer:
            out.append(Signal(f"BRK_DN_{z.price:.0f}", "Level break", "down", cl,
                              f"15m candle ({stamp}) closed {_fmt(cl)} BELOW {name}. "
                              f"Next: watch a retest of {_fmt(z.low)} failing as resistance."))
        # Rejections
        upper_wick = h - max(o, cl)
        lower_wick = min(o, cl) - l
        if h >= z.low and cl < z.low and upper_wick / rng >= 0.5:
            out.append(Signal(f"REJ_DN_{z.price:.0f}", "Rejection", "down", cl,
                              f"Sellers rejected {name}: high {_fmt(h)}, close {_fmt(cl)} "
                              f"(upper wick {upper_wick / rng:.0%} of candle). Bearish while below {_fmt(h)}."))
        if l <= z.high and cl > z.high and lower_wick / rng >= 0.5:
            out.append(Signal(f"REJ_UP_{z.price:.0f}", "Rejection", "up", cl,
                              f"Buyers defended {name}: low {_fmt(l)}, close {_fmt(cl)} "
                              f"(lower wick {lower_wick / rng:.0%} of candle). Bullish while above {_fmt(l)}."))

    # Momentum candle
    if len(today) >= 6:
        avg = float((today["High"] - today["Low"]).iloc[:-1].tail(20).mean())
        if avg > 0 and rng >= 1.8 * avg:
            d = "up" if cl > o else "down"
            out.append(Signal(f"MOM_{stamp}", "Momentum candle", d, cl,
                              f"{stamp} candle range {rng:.0f} pts = {rng / avg:.1f}x average, "
                              f"closed {'green' if d == 'up' else 'red'} at {_fmt(cl)}."))
    return out
