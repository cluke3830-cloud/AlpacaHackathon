"""Alpaca-hackathon option sleeve — pure signal + structure logic (no I/O).

The research backtest AND the integrity manifest both import from here, so the
certified logic and the executed logic are one file. Same rule as
`t2_qld_signal.py`; it is why the two can never drift apart.

THE BOOK (as tested, 2026-08-25):
  Weekly, non-overlapping. Enter a defined-risk SHORT PUT VERTICAL on the index
  ~7 calendar days to expiry, short strike ~2.5% OTM, wing 0.65% of spot.
  Held to expiry (the only exit rule that could be honestly backtested — see
  BEAR_TEST_VERDICT.md for why 50%-profit-take is untestable on this data).
  Gate: long iff  MSAR p_slow < 0.5  AND  index >= its own 200d MA.
  LONG-PREMIUM-ONLY, defined risk: max loss is the wing width minus credit.

PROVENANCE of the gate: identical to the deployed T2-QLD gate
(`mandatory_tests_for_deployment_2/t2_qld_signal.py`) — MSAR-2-regime filtered
P(high-vol) on log(VIX), frozen params, plus the 200d trend veto. Reused, not
re-fitted: no new degrees of freedom were introduced for this sleeve.

CAUSALITY: every input (VIX close_t, index close_t) is known at the entry close;
the position is held entry -> expiry. Any missing input reads as FLAT, never long.

★ HONEST STATUS: this book does NOT pass the integrity gate and is NOT deployable.
It is retained as the certified-honest record of a falsified thesis. See
`mandatory_tests_for_deployment/strategies/alpaca_option/strategy_integrity.py`
for the full FAIL ledger.
"""
from __future__ import annotations

import math

OTM_SHORT = 0.025        # short strike distance below spot
WING_PCT = 5.0 / 765.0   # wing width as a fraction of spot (the SPY $5/$765 ratio)
DTE_TARGET = 7           # calendar days to expiry at entry
COST_FRAC = 0.04         # slippage as a fraction of credit, measured on live quotes
VOL_ERA_P = 0.5          # MSAR slow-state midpoint (inherited, not tuned)


def strikes_for(spot: float, otm: float = OTM_SHORT, wing_pct: float = WING_PCT):
    """Short/long strike pair for a put vertical at `otm` below `spot`."""
    short_k = spot * (1.0 - otm)
    return short_k, short_k - wing_pct * spot


def gate_long(p_slow, trend_ok) -> bool:
    """The locked daily decision. Long iff not a vol-era AND trend intact.
    Any NaN input -> FLAT (fail-safe), never long."""
    for v in (p_slow, trend_ok):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return False
    return bool(p_slow < VOL_ERA_P) and bool(trend_ok)


def credit_from_quotes(short_bid: float, long_ask: float) -> float:
    """Entry credit taken CONSERVATIVELY: sell the short leg at its BID, buy the
    wing at its ASK. Never mid — mid is the number that flatters a backtest."""
    return short_bid - long_ask


def spread_pnl(credit: float, short_k: float, long_k: float, settle: float,
               cost_frac: float = COST_FRAC) -> float:
    """P&L per share of a short put vertical held to expiry, net of entry cost."""
    width = short_k - long_k
    if width <= 0:
        return float("nan")
    intrinsic = max(0.0, min(short_k - settle, width))
    return credit * (1.0 - cost_frac) - intrinsic


def pnl_per_width(credit: float, short_k: float, long_k: float, settle: float,
                  cost_frac: float = COST_FRAC) -> float:
    """Same, normalised by width so results are comparable across spot levels
    and across eras. This is the unit the manifest reports."""
    width = short_k - long_k
    if width <= 0:
        return float("nan")
    return spread_pnl(credit, short_k, long_k, settle, cost_frac) / width
