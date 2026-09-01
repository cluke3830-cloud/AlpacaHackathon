"""T2-QLD sleeve — pure signal logic (no I/O, no IBKR). The live engine and
the integrity manifest BOTH import from here so the certified logic and the
executed logic are one file.

Book (OVERRIDE_t2_qld_2026-07-12.md, TC-ratified "OVERRIDE CONFIRMED"
2026-07-11; sizing changed to 100/100 per the 2026-07-15 addendum in that
same doc — TC's explicit, confirmed choice over the previously-agreed 70-80%
scale-down, backtest maxDD -28.8% vs the original 80/20 book's -22.7%):
  100% QLD, held long iff ALL of
    (1) MSAR-long OR gamma-A+C net-bullish            [OR gate]
    (2) NOT vol-era: 60d mean of MSAR p_high < 0.5    [regime switch]
    (3) QLD >= its own 200d MA                        [trend veto]
  else 100% cash (T-bill) — no GLD position is ever opened.
  LONG/FLAT ONLY — never short, never levered, one MOC decision per day.

Provenance of each layer (research: OptionDashboard/research/vix_drawdown/):
  OR gate       — or_smh_signal.or_gate (MSAR golden-tested vs statsmodels;
                  A+C formulas imported from the deployed gamma engine).
  regime switch — regime_switch_gate.py R2: the SLOW era state (60d mean,
                  min_periods=30) is what stayed lit through 2022; instant-p
                  vetoes whipsawed.
  trend veto    — trend_veto_test.py T2: close >= rolling(200).mean() on the
                  instrument's OWN history.
Golden parity: tests/test_t2_signal.py vs t2_qld_golden.parquet (independent
research-replica export) — full 2018-2026 panel, bit-for-bit.

CAUSALITY: every input (VIX close_t, gex_sign_t, ret_t, mom20_t, QLD close_t)
is known at close t; the position is held t -> t+1 (MOC fills). Fail-safe:
any missing input (NaN warm-up, short history) reads as FLAT, never long.
"""
from __future__ import annotations

import math

import pandas as pd

from or_smh_signal import ac_net_direction, or_gate

P_SLOW_WINDOW = 60      # one quarter of trading days
P_SLOW_MIN = 30         # rolling-mean warm-up floor
VOL_ERA_P = 0.5         # probability midpoint (pre-registered, no sweep)
TREND_WINDOW = 200      # canonical 200d MA

QLD_WEIGHT = 1.00       # growth sleeve target weight (2026-07-15: 100/100, no ballast)
GLD_WEIGHT = 0.00       # ballast target weight — 0 = no GLD ever bought; gate-off
                        # capital sits in cash, same as the gated 80% used to


def p_slow_series(p_high: pd.Series) -> pd.Series:
    """Slow regime state: trailing 60d mean of MSAR filtered P(high-vol),
    NaN until 30 observations (research semantics, regime_switch_gate.py)."""
    return p_high.rolling(P_SLOW_WINDOW, min_periods=P_SLOW_MIN).mean()


def trend_ok_series(closes: pd.Series) -> pd.Series:
    """Trend veto input: close >= its own 200d MA. NaN (not False) until the
    MA exists so the warm-up is visibly missing rather than silently vetoed;
    t2_gate fails safe on NaN either way."""
    sma = closes.rolling(TREND_WINDOW).mean()
    out = (closes >= sma).astype(float)   # 1.0/0.0; float so NaN can coexist
    out[sma.isna()] = float("nan")
    return out


def t2_gate(msar_long, ac_dir, p_slow, trend_ok) -> bool:
    """The locked daily decision. Long iff the OR gate is on AND we are not
    in a volatile era AND the trend veto passes. Any NaN input -> FLAT."""
    if p_slow is None or (isinstance(p_slow, float) and math.isnan(p_slow)):
        return False
    if trend_ok is None or (isinstance(trend_ok, float) and math.isnan(trend_ok)):
        return False
    if p_slow >= VOL_ERA_P:
        return False
    if not bool(trend_ok):
        return False
    return or_gate(msar_long, ac_dir)


def decide_t2_qld(capital_usd, *, msar_long, gex_sign, ret_t, mom20,
                  p_slow, trend_ok, qld_price, gld_price):
    """Daily target position. Returns fractional share counts (IBKR
    fractional orders) for the $-sized book:
      QLD: capital * 0.80 if the T2 gate is long, else 0
      GLD: capital * 0.20 always (quarterly true-up handled by the engine)
    """
    ac_dir = ac_net_direction(gex_sign, ret_t, mom20)
    long_ = t2_gate(msar_long, ac_dir, p_slow, trend_ok)
    qld_dollars = capital_usd * QLD_WEIGHT if long_ else 0.0
    gld_dollars = capital_usd * GLD_WEIGHT
    return {
        "QLD": round(qld_dollars / qld_price, 4) if qld_price else 0.0,
        "GLD": round(gld_dollars / gld_price, 4) if gld_price else 0.0,
        "_state": {"gate_long": long_, "msar_long": bool(msar_long),
                   "ac_dir": ac_dir, "p_slow": float(p_slow),
                   "vol_era": bool(p_slow >= VOL_ERA_P),
                   "trend_ok": bool(trend_ok)},
    }
