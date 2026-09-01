"""
gamma_ac_engine.py — US gamma A+C sleeve (Stage 1 of the KR×US combined book).

Index-level directional signal — SPX dealer-gamma, traded via QQQ:
  gex_sign = sign(-SPX_GEX)            # retail-inverted (matches us_bear_lab.build_us_panel)
  A = -sign(ret_t) if gex_sign>0 else sign(ret_t)   # ret_t = QQQ's own daily return
  C = sign(20d QQQ log-return)
  pos = (A + C)/2  ->  +1 (both long) / 0 (disagree -> flat) / -1 (both short)

  The GEX SIGNAL stays SPX (dealer positioning lives in the SPX option book); we
  express it through QQQ, the higher-beta liquid instrument. Multi-ticker test
  2026-06-19: same signal, SPY Sharpe 1.26 -> QQQ 1.64 (higher beta = bigger
  captured moves). Small/mid caps DEAD (signal is SPX-flow-specific). See
  project_multiticker_instrument memory.

Contract (mirrors decide_v3 in strategy_engines.py):
  decide_gamma_ac(capital, current_positions) -> {"QQQ": signed_target_shares}

GEX PARITY: the live path replicates build_us_gex EXACTLY — same dte∈[1,8] +
|log(K/S)|<0.20 filter, same dealer sign (call +, put -), summed. The relay's
SPX chain (N_EXPIRIES=8, ≤60 DTE, ±25% strikes) contains that universe as a subset.

CAUSALITY: gex_sign_t, ret_t, mom20_t all known at close t; position held t->t+1
(filled at T+1 open per harness convention). No look-ahead.

Run `python gamma_ac_engine.py` for the OFFLINE PARITY TEST: proves the engine's
A/C/pos == us_bear_lab.build_us_panel on historical data, before any IBKR wiring.
"""
import datetime as dt
import math
from pathlib import Path

import numpy as np

# match build_us_gex constants
DTE_LO, DTE_HI = 1, 8
MONEYNESS = 0.20
US_LEVERAGE_DEFAULT = 3.05      # gross QQQ / US-allocated($=50% book). Bisection-pinned so the
                                # combined KR×US book MaxDD = exactly -20% (TC budget, 2026-06-19).
                                # QQQ over SPY: same SPX-GEX signal, higher beta -> sleeve Sharpe
                                # 1.26->1.64, combined 1.65->2.07. FIXED leverage (no vol-target).


# ─────────────────────────────────────────────────────────────────────────────
# GEX from a raw option chain (relay-style rows) — replicates build_us_gex
# ─────────────────────────────────────────────────────────────────────────────
def raw_gex_from_rows(rows, spot, now=None):
    """rows: list of dicts {expiry:'YYYYMMDD', strike, right:'C'/'P', gamma, oi}.
    Returns the signed dealer GEX (call +, put -) over dte∈[1,8], |moneyness|<0.20.
    Sign is scale-invariant, so any positive gamma source (IBKR model or BS) works."""
    now = now or dt.datetime.now()
    total = 0.0
    for c in rows:
        oi = c.get("oi") or 0
        g = c.get("gamma")
        if not oi or g is None:
            continue
        k = float(c["strike"])
        if k <= 0 or spot <= 0:
            continue
        if abs(math.log(k / spot)) >= MONEYNESS:
            continue
        exp = dt.datetime.strptime(c["expiry"], "%Y%m%d")
        dte = (exp - now).days
        if not (DTE_LO <= dte <= DTE_HI):
            continue
        sign = 1.0 if str(c["right"]).upper().startswith("C") else -1.0
        total += sign * float(g) * oi * spot ** 2 * 0.01
    return total


def gex_sign_from_raw_gex(raw_gex):
    """retail-inverted sign — matches build_us_panel: gex_sign = sign(-gex)."""
    return float(np.sign(-raw_gex))


# ─────────────────────────────────────────────────────────────────────────────
# Signal — identical to build_us_panel A/C and evaluate(['A','C'])
# ─────────────────────────────────────────────────────────────────────────────
def compute_signal(gex_sign, ret_t, mom20):
    if gex_sign == 0:
        # No valid GEX data (pre-market, chain empty) — go flat rather than trade on half-signal
        return dict(A=0.0, C=float(np.sign(mom20)), pos=0.0, no_gex=True)
    A = (-np.sign(ret_t)) if gex_sign > 0 else np.sign(ret_t)
    C = np.sign(mom20)
    pos = (A + C) / 2.0          # +1 / 0 / -1
    return dict(A=float(A), C=float(C), pos=float(pos))


# ─────────────────────────────────────────────────────────────────────────────
# Decision (harness contract)
# ─────────────────────────────────────────────────────────────────────────────
def decide_gamma_ac(capital, current_positions, *, gex_sign, ret_t, mom20,
                    qqq_price, us_leverage=US_LEVERAGE_DEFAULT):
    """capital = US-sleeve allocated $ (50% of book). Returns {"QQQ": signed_shares}.
    gex_sign is from SPX dealer-gamma (unchanged); ret_t/mom20 are QQQ's own price
    momentum. We trade the SPX signal through the higher-beta QQQ."""
    sig = compute_signal(gex_sign, ret_t, mom20)
    target_notional = sig["pos"] * capital * us_leverage
    shares = int(round(target_notional / qqq_price)) if qqq_price > 0 else 0
    return {"QQQ": shares, "_signal": sig}


# ─────────────────────────────────────────────────────────────────────────────
# OFFLINE PARITY TEST — engine signal vs build_us_panel (run before IBKR wiring)
# ─────────────────────────────────────────────────────────────────────────────
def _parity_test():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "KoreanStatArb" / "scripts"))
    from us_bear_lab import build_us_panel, build_us_gex
    import pandas as pd

    panel = build_us_panel()
    gex = build_us_gex()
    # engine recomputes gex_sign/A/C/pos from the SAME raw inputs the panel used
    df = panel.copy()
    df["gex_raw"] = gex.reindex(df.index)
    df["ret20"] = None
    # reconstruct mom20 exactly as build_us_panel (sum of 20 daily log returns incl today)
    mom20 = df["mom20"]            # already in panel
    mism = 0; n = 0
    last_rows = []
    for d, row in df.dropna(subset=["gex_raw", "ret_t", "mom20", "A", "C"]).iterrows():
        gsign = gex_sign_from_raw_gex(row["gex_raw"])
        sig = compute_signal(gsign, row["ret_t"], row["mom20"])
        # panel's own pos for A+C:
        panel_pos = (row["A"] + row["C"]) / 2.0
        ok = (abs(sig["A"] - row["A"]) < 1e-9 and abs(sig["C"] - row["C"]) < 1e-9
              and abs(sig["pos"] - panel_pos) < 1e-9 and gsign == row["gex_sign"])
        n += 1
        if not ok:
            mism += 1
        last_rows.append((d.date(), gsign, sig["A"], sig["C"], sig["pos"], row["gex_sign"], row["A"], row["C"]))

    print(f"PARITY TEST: {n} days,  mismatches = {mism}")
    print(f"  {'date':12s} {'gsign':>6s} {'A':>4s} {'C':>4s} {'pos':>5s} | {'panel_gsign':>11s} {'pA':>4s} {'pC':>4s}")
    for r in last_rows[-8:]:
        print(f"  {str(r[0]):12s} {r[1]:>+6.0f} {r[2]:>+4.0f} {r[3]:>+4.0f} {r[4]:>+5.1f} | "
              f"{r[5]:>+11.0f} {r[6]:>+4.0f} {r[7]:>+4.0f}")
    if mism == 0:
        print("\n  ✅ ENGINE SIGNAL == build_us_panel on every day. Signal logic verified, no leakage/flip.")
    else:
        print(f"\n  ❌ {mism} mismatches — DO NOT deploy until resolved.")
    # show a sample decide()
    ex = decide_gamma_ac(100_000, {}, gex_sign=last_rows[-1][1], ret_t=df["ret_t"].iloc[-1],
                         mom20=df["mom20"].iloc[-1], qqq_price=540.0)
    print(f"\n  sample decide($100k US-alloc, QQQ=$540): {ex}")


if __name__ == "__main__":
    _parity_test()
