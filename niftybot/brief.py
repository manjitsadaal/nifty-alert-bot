"""Formats the morning brief and other Telegram messages."""
from __future__ import annotations

from .levels import DayPlan
from .telegram import esc


def _f(x: float) -> str:
    return f"{x:,.0f}"


def morning_brief(plan: DayPlan, n: int, gift_note: str = "") -> str:
    p, c = plan.prev, plan.cpr
    ref = plan.reference
    pv = plan.pivots["P"]
    bias = ("Bullish: price above CPR" if ref > c["TC"] else
            "Bearish: price below CPR" if ref < c["BC"] else "Neutral: price inside CPR")
    lines = [
        f"<b>NIFTY 50 plan — {esc(plan.date)} → today</b>",
        f"Prev day: H {_f(p['high'])} · L {_f(p['low'])} · C {_f(p['close'])}",
        f"Reference price: <b>{_f(ref)}</b>{esc(gift_note)}",
        f"CPR {_f(c['BC'])}–{_f(c['TC'])} (pivot {_f(pv)}), {c['width_pct']:.2f}% wide → {esc(c['type'])}",
        f"Bias: {esc(bias)}",
    ]
    if plan.week:
        lines.append(f"Prev week: H {_f(plan.week['PWH'])} · L {_f(plan.week['PWL'])}")
    lines.append("\n<b>Resistance</b> (nearest first)")
    for z in plan.above(n):
        lines.append(f"🔴 {_f(z.price)}  {esc(z.label)}  {'★' * min(z.score // 2, 5)}")
    lines.append("\n<b>Support</b> (nearest first)")
    for z in plan.below(n):
        lines.append(f"🟢 {_f(z.price)}  {esc(z.label)}  {'★' * min(z.score // 2, 5)}")
    up, dn = plan.above(1), plan.below(1)
    if up and dn:
        lines += ["\n<b>Playbook</b>",
                  f"• 15m close above {_f(up[0].high)} → upside toward "
                  f"{_f(plan.above(2)[-1].price) if len(plan.above(2)) > 1 else 'next zone'}",
                  f"• 15m close below {_f(dn[0].low)} → downside toward "
                  f"{_f(plan.below(2)[-1].price) if len(plan.below(2)) > 1 else 'next zone'}",
                  f"• Between {_f(dn[0].price)}–{_f(up[0].price)}: chop zone, avoid buying options",
                  "• Mark the 9:15–9:45 range; first clean 15m close outside it = ORB signal"]
    lines.append("\n<i>Levels from Yahoo daily data. Not trade advice.</i>")
    return "\n".join(lines)
