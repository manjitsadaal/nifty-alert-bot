"""Builds the day's support/resistance map from daily OHLC candles.

Sources of levels (each tagged so you know why a level exists):
  * Previous day high / low / close (PDH, PDL, PDC)
  * Classic floor pivots: P, R1-R3, S1-S3
  * CPR (central pivot range): TC / BC, plus a narrow/wide CPR read
  * Camarilla H3/H4/L3/L4 (intraday reversal / breakout levels)
  * Previous week high / low (PWH, PWL)
  * Recent swing highs / lows (fractals over the last ~30 sessions)
  * Round numbers (every 100 points)

Nearby levels are merged into zones; a zone made of several sources scores
higher ("confluence"), and the strongest zones closest to price get alerts.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# Weight of each source when scoring confluence.
WEIGHTS = {
    "PDH": 3, "PDL": 3, "PDC": 2,
    "P": 2, "R1": 2, "S1": 2, "R2": 1, "S2": 1, "R3": 1, "S3": 1,
    "TC": 1, "BC": 1,
    "H3": 1, "L3": 1, "H4": 2, "L4": 2,
    "PWH": 3, "PWL": 3,
    "SWING_H": 2, "SWING_L": 2,
    "ROUND": 1, "ROUND500": 2,
}


@dataclass
class Zone:
    price: float
    tags: list[str] = field(default_factory=list)
    low: float = 0.0
    high: float = 0.0

    @property
    def score(self) -> int:
        return sum(WEIGHTS.get(t.split("@")[0], 1) for t in self.tags)

    @property
    def label(self) -> str:
        return "/".join(dict.fromkeys(t.split("@")[0] for t in self.tags))

    def to_dict(self) -> dict:
        return {"price": round(self.price, 2), "low": round(self.low, 2),
                "high": round(self.high, 2), "tags": self.tags,
                "label": self.label, "score": self.score}


@dataclass
class DayPlan:
    date: str
    prev: dict
    pivots: dict
    cpr: dict
    camarilla: dict
    week: dict
    zones: list[Zone]
    reference: float

    def above(self, n: int) -> list[Zone]:
        z = [x for x in self.zones if x.price > self.reference]
        return sorted(z, key=lambda x: x.price)[:n]

    def below(self, n: int) -> list[Zone]:
        z = [x for x in self.zones if x.price < self.reference]
        return sorted(z, key=lambda x: -x.price)[:n]

    def to_dict(self) -> dict:
        return {"date": self.date, "prev": self.prev, "pivots": self.pivots,
                "cpr": self.cpr, "camarilla": self.camarilla, "week": self.week,
                "reference": self.reference,
                "zones": [z.to_dict() for z in self.zones]}


def _swings(daily: pd.DataFrame, lookback: int = 30, k: int = 2) -> list[tuple[str, float]]:
    """Fractal swing points: a high higher than k bars each side (same for lows)."""
    d = daily.tail(lookback)
    out: list[tuple[str, float]] = []
    highs, lows = d["High"].to_numpy(), d["Low"].to_numpy()
    for i in range(k, len(d) - k):
        if highs[i] == max(highs[i - k:i + k + 1]):
            out.append(("SWING_H", float(highs[i])))
        if lows[i] == min(lows[i - k:i + k + 1]):
            out.append(("SWING_L", float(lows[i])))
    return out


def build_plan(daily: pd.DataFrame, reference: float | None = None,
               merge_distance: float = 15.0, max_distance_pct: float = 2.0) -> DayPlan:
    """`daily` must hold completed sessions only, last row = previous trading day."""
    daily = daily.dropna(subset=["Open", "High", "Low", "Close"])
    last = daily.iloc[-1]
    H, L, C = float(last["High"]), float(last["Low"]), float(last["Close"])
    ref = float(reference) if reference else C

    P = (H + L + C) / 3
    rng = H - L
    pivots = {"P": P, "R1": 2 * P - L, "S1": 2 * P - H,
              "R2": P + rng, "S2": P - rng,
              "R3": H + 2 * (P - L), "S3": L - 2 * (H - P)}

    bc = (H + L) / 2
    tc = 2 * P - bc
    tc, bc = max(tc, bc), min(tc, bc)
    width_pct = (tc - bc) / P * 100
    cpr = {"TC": tc, "BC": bc, "width_pct": width_pct,
           "type": "narrow (trend day likely)" if width_pct < 0.15
           else "wide (range day likely)" if width_pct > 0.35 else "normal"}

    cam = {"H4": C + rng * 1.1 / 2, "H3": C + rng * 1.1 / 4,
           "L3": C - rng * 1.1 / 4, "L4": C - rng * 1.1 / 2}

    idx = pd.to_datetime(daily.index)
    wk = daily.copy()
    wk["wk"] = idx.to_period("W-FRI")
    this_week = wk["wk"].iloc[-1]
    prev_weeks = wk[wk["wk"] < this_week]
    if len(prev_weeks):
        pw = prev_weeks[prev_weeks["wk"] == prev_weeks["wk"].iloc[-1]]
        week = {"PWH": float(pw["High"].max()), "PWL": float(pw["Low"].min())}
    else:
        week = {}

    raw: list[tuple[str, float]] = [("PDH", H), ("PDL", L), ("PDC", C)]
    raw += [(k, v) for k, v in pivots.items()]
    raw += [("TC", tc), ("BC", bc)]
    raw += [(k, v) for k, v in cam.items()]
    raw += [(k, v) for k, v in week.items()]
    raw += _swings(daily)
    base = int(ref // 100) * 100
    for r in range(base - 600, base + 700, 100):
        raw.append(("ROUND500" if r % 500 == 0 else "ROUND", float(r)))

    limit = ref * max_distance_pct / 100
    raw = [(t, p) for t, p in raw if abs(p - ref) <= limit]

    zones: list[Zone] = []
    for tag, price in sorted(raw, key=lambda x: x[1]):
        if (zones and price - zones[-1].high <= merge_distance
                and price - zones[-1].low <= 2 * merge_distance):
            z = zones[-1]
            z.tags.append(f"{tag}@{price:.0f}")
            z.high = max(z.high, price)
        else:
            zones.append(Zone(price=price, tags=[f"{tag}@{price:.0f}"], low=price, high=price))
    for z in zones:
        # Alert price: strongest member's price, else the zone midpoint.
        members = [(WEIGHTS.get(t.split("@")[0], 1), float(t.split("@")[1])) for t in z.tags]
        best = max(members)[0]
        z.price = sum(p for w, p in members if w == best) / sum(1 for w, _ in members if w == best)

    # Drop weak lone round numbers if a stronger zone is near; keep everything else.
    zones = [z for z in zones if not (z.label == "ROUND" and z.score <= 1
                                      and any(abs(o.price - z.price) < 40 and o.score >= 3 for o in zones))]

    return DayPlan(date=str(idx[-1].date()), prev={"high": H, "low": L, "close": C},
                   pivots=pivots, cpr=cpr, camarilla=cam, week=week,
                   zones=zones, reference=ref)
