"""Draws a Nifty 15m candle chart with the day's levels as a PNG (for Telegram)."""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .levels import Zone  # noqa: E402

UP, DOWN = "#26a69a", "#ef5350"
RES, SUP = "#d32f2f", "#1565c0"


def render(df: pd.DataFrame, zones: list[Zone], reference: float, title: str,
           sessions: int = 3, marker: dict | None = None) -> bytes:
    """df: 15m candles (IST index). marker: {"price": float, "direction": "up"/"down", "text": str}."""
    if df is not None and not df.empty:
        days = sorted(set(df.index.date))[-sessions:]
        df = df[pd.Index(df.index.date).isin(days)]
    fig, ax = plt.subplots(figsize=(11, 6.2), dpi=110)
    fig.patch.set_facecolor("white")

    lo = hi = reference
    n = 0
    if df is not None and not df.empty:
        n = len(df)
        for i, (_, r) in enumerate(df.iterrows()):
            o, h, l, c = r["Open"], r["High"], r["Low"], r["Close"]
            col = UP if c >= o else DOWN
            ax.vlines(i, l, h, color=col, linewidth=1)
            ax.add_patch(plt.Rectangle((i - 0.35, min(o, c)), 0.7, max(abs(c - o), 0.5),
                                       color=col, linewidth=0))
        lo, hi = float(df["Low"].min()), float(df["High"].max())
        # Session separators + date labels
        dates = pd.Index(df.index.date)
        starts = [i for i in range(n) if i == 0 or dates[i] != dates[i - 1]]
        for s in starts[1:]:
            ax.axvline(s - 0.5, color="#bbbbbb", linewidth=0.8, linestyle=":")
        ax.set_xticks(starts)
        ax.set_xticklabels([df.index[s].strftime("%d %b") for s in starts], fontsize=9)
        last = float(df["Close"].iloc[-1])
        ax.axhline(last, color="#555555", linewidth=0.8, linestyle="--")
        ax.annotate(f"{last:,.0f}", xy=(n - 0.5, last), xytext=(n + 0.6, last), va="center",
                    fontsize=9, color="white",
                    bbox=dict(boxstyle="round,pad=0.25", fc="#555555", ec="none"))

    # Show levels within a sensible window around the candles.
    pad = max((hi - lo) * 0.35, reference * 0.004)
    view_lo, view_hi = lo - pad, hi + pad
    visible = [z for z in zones if view_lo <= z.price <= view_hi]
    for z in visible:
        col = RES if z.price > reference else SUP
        width = 1.0 + min(z.score, 8) * 0.3
        if z.high - z.low >= 2:
            ax.axhspan(z.low, z.high, color=col, alpha=0.08)
        ax.axhline(z.price, color=col, linewidth=width, alpha=0.85)
        stars = "★" * min(z.score // 2, 5)
        name = "/".join(z.label.split("/")[:3])
        ax.text(max(n, 1) + 0.6, z.price, f"{z.price:,.0f} {name} {stars}", va="bottom",
                fontsize=8.5, color=col, fontweight="bold" if z.score >= 4 else "normal",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.9))

    if marker and n:
        y = marker["price"]
        up = marker.get("direction") == "up"
        ax.annotate(marker.get("text", ""), xy=(n - 1, y),
                    xytext=(n - 1 - max(n * 0.25, 4), y + (1 if up else -1) * pad * 0.6),
                    fontsize=9, color=UP if up else DOWN, fontweight="bold",
                    arrowprops=dict(arrowstyle="->", color=UP if up else DOWN, lw=1.5))

    ax.set_ylim(view_lo, view_hi)
    ax.set_xlim(-1, max(n, 1) + 14)
    ax.yaxis.tick_right()
    ax.grid(axis="y", color="#eeeeee")
    for s in ("top", "left"):
        ax.spines[s].set_visible(False)
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold")
    fig.text(0.01, 0.01, "NIFTY 50 · 15m · levels auto-calculated · not trade advice",
             fontsize=7.5, color="#888888")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()
