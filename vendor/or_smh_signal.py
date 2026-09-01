"""OR x SMH sleeve — pure signal logic (no I/O, no IBKR). The live engine and
the integrity manifest BOTH import from here so the certified logic and the
executed logic are one file.

Book (locked 2026-07-12 after the exhaustive 585-book grid + overlay kills):
  80% SMH, held long iff (MSAR-long OR gamma-A+C net-bullish), else cash
  20% GLD, buy-and-hold, quarterly rebalance to target weights
  LONG/FLAT ONLY — never short, never levered, one MOC decision per day.

Components:
  MSAR  — 2-regime Markov-switching AR(1) on log(VIX), frozen params
          (config/msar2_params.json, refit each January), Hamilton filter
          over the JOINT (s_t, s_{t-1}) because the mean-adjusted AR's
          conditional density needs both regimes. Ported from the
          statsmodels-parity-verified web/lib/msarRegime.ts; golden-tested
          against statsmodels' own .filter() output below.
  A+C   — the deployed gamma engine's signal (SPX dealer-gamma sign +
          QQQ's own ret_t / mom20); formulas imported from
          gamma_ac_engine.compute_signal so the two sleeves can never drift.

CAUSALITY: every input (VIX close_t, gex_sign_t, ret_t, mom20_t) is known at
close t; the position is held t -> t+1. Backtest convention == deployment
convention (MOC fills).
"""
from __future__ import annotations

import json
import math
import os

import numpy as np

from gamma_ac_engine import compute_signal          # A/C formulas, single source

_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "config", "msar2_params.json")

SELL_P = 0.7        # de-risk when filtered P(high-vol) >= SELL_P
BUY_P = 0.3         # re-enter when it falls back to <= BUY_P
MIN_BARS = 30       # filter warm-up guard

SMH_WEIGHT = 0.80   # growth sleeve target weight
GLD_WEIGHT = 0.20   # ballast target weight


def load_msar_params(path=None) -> dict:
    with open(path or _CONFIG) as f:
        return json.load(f)["params"]


def _norm_pdf(x, mean, var):
    return math.exp(-0.5 * (x - mean) * (x - mean) / var) / math.sqrt(2.0 * math.pi * var)


def msar_filtered_p_high(vix_closes, params=None):
    """Filtered P(high-vol regime | closes[0..t]) for each t (index 0 = NaN:
    the AR(1) needs a previous observation). Hamilton filter over the joint
    (s_t, s_{t-1}); uniform init (memory washes out in ~20 obs — verified
    against statsmodels to 7e-6 after burn-in)."""
    p = params or load_msar_params()
    a = [[p["p00"], 1.0 - p["p00"]], [p["p10"], 1.0 - p["p10"]]]
    mu, ar, s2 = p["mu"], p["ar"], p["sigma2"]
    hi = p["hi_state"]
    y = [math.log(v) for v in vix_closes]
    n = len(y)
    out = np.full(n, np.nan)
    if n < 2:
        return out
    filt = [0.5, 0.5]
    for t in range(1, n):
        joint = [0.0, 0.0]
        total = 0.0
        for i in range(2):
            for j in range(2):
                mean = mu[j] + ar[j] * (y[t - 1] - mu[i])
                w = filt[i] * a[i][j] * _norm_pdf(y[t], mean, s2[j])
                joint[j] += w
                total += w
        if total > 0:
            filt = [joint[0] / total, joint[1] / total]
        else:
            filt = [0.5, 0.5]
        out[t] = filt[hi]
    return out


def msar_positions(vix_closes, params=None, sell_p=SELL_P, buy_p=BUY_P):
    """Full causal long/flat hysteresis series (1.0 long / 0.0 flat) over a
    VIX close history. Starts long; day t uses only closes[0..t]."""
    probs = msar_filtered_p_high(vix_closes, params)
    pos = np.ones(len(probs))
    is_long = True
    for i, p in enumerate(probs):
        if not np.isnan(p):
            if is_long and p >= sell_p:
                is_long = False
            elif (not is_long) and p <= buy_p:
                is_long = True
        pos[i] = 1.0 if is_long else 0.0
    return pos


def ac_net_direction(gex_sign, ret_t, mom20) -> float:
    """sign((A+C)/2) from the deployed gamma engine's own formulas."""
    sig = compute_signal(gex_sign, ret_t, mom20)
    return float(np.sign(sig["pos"]))


def or_gate(msar_long, ac_dir) -> bool:
    """The locked entry/exit rule: long iff MSAR says risk-on OR the gamma
    A+C signal is net-bullish. Long/flat only — a bearish A+C never shorts."""
    return bool(msar_long) or ac_dir > 0


def decide_or_smh(capital_usd, *, msar_long, gex_sign, ret_t, mom20,
                  smh_price, gld_price):
    """Daily target position. Returns whole-dollar targets and fractional
    share counts (IBKR fractional orders) for the $-sized book:
      SMH: capital * 0.80 if the OR gate is long, else 0
      GLD: capital * 0.20 always (quarterly true-up handled by the engine)
    """
    ac_dir = ac_net_direction(gex_sign, ret_t, mom20)
    long_ = or_gate(msar_long, ac_dir)
    smh_dollars = capital_usd * SMH_WEIGHT if long_ else 0.0
    gld_dollars = capital_usd * GLD_WEIGHT
    return {
        "SMH": round(smh_dollars / smh_price, 4) if smh_price else 0.0,
        "GLD": round(gld_dollars / gld_price, 4) if gld_price else 0.0,
        "_state": {"gate_long": long_, "msar_long": bool(msar_long),
                   "ac_dir": ac_dir},
    }


def _golden_test():
    """Verify the Python filter against statsmodels' own .filter() output
    (goldens stored beside the frozen params)."""
    with open(_CONFIG) as f:
        doc = json.load(f)
    vix_tail = doc["golden"]["vix_tail"]
    expected = doc["golden"]["p_high_last5"]
    probs = msar_filtered_p_high(vix_tail, doc["params"])
    got = [round(float(x), 6) for x in probs[-5:]]
    err = max(abs(g - e) for g, e in zip(got, expected))
    assert err < 1e-4, f"golden mismatch: {got} vs {expected} (err {err})"
    print(f"golden PASS: last5 filtered P(high) match statsmodels to {err:.1e}")


if __name__ == "__main__":
    _golden_test()
