"""Free price data from Yahoo Finance (^NSEI = NIFTY 50).

Daily candles are reliable for level calculation. Intraday 15m candles are
free but can lag the exchange by a minute or two, so price-action alerts
from them are "heads-up" signals: confirm on the Kite chart before acting.
"""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from .config import SETTINGS

IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    return datetime.now(IST)


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[["Open", "High", "Low", "Close"] + (["Volume"] if "Volume" in df else [])].dropna(
        subset=["Open", "High", "Low", "Close"])


def daily_completed(days: int = 90) -> pd.DataFrame:
    """Daily candles, excluding today's candle while the market is still open."""
    df = yf.download(SETTINGS.yahoo_symbol, period=f"{days}d", interval="1d",
                     progress=False, auto_adjust=False)
    df = _clean(df)
    if df.empty:
        raise RuntimeError("No daily data from Yahoo Finance")
    idx = pd.to_datetime(df.index)
    df.index = idx.tz_localize(None) if idx.tz is not None else idx
    now = now_ist()
    if df.index[-1].date() == now.date() and now.time() < time(15, 31):
        df = df.iloc[:-1]
    return df


def intraday(interval: str = "15m", days: int = 2) -> pd.DataFrame:
    """Today's (and yesterday's) intraday candles in IST, last row may be forming."""
    df = yf.download(SETTINGS.yahoo_symbol, period=f"{days}d", interval=interval,
                     progress=False, auto_adjust=False)
    df = _clean(df)
    if df.empty:
        return df
    idx = pd.to_datetime(df.index)
    df.index = (idx.tz_localize("UTC") if idx.tz is None else idx).tz_convert(IST)
    return df


def last_price() -> float | None:
    df = intraday("1m", 1)
    return float(df["Close"].iloc[-1]) if not df.empty else None
