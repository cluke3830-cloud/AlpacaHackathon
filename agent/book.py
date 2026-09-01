"""Turn today's two sleeve directions into concrete option positions.

SIZING NOTE THAT MATTERS. The backtest normalizes every option return to
SPOT-EQUIVALENT exposure: notional = spot * target_delta * 100 per contract, so
a +1% index move on a perfectly delta-matched call reads as ~+1%. Sizing live to
PREMIUM instead of to delta-notional would produce a book with the same names
and completely different risk -- roughly 20x levered at these tenors, because a
7-DTE 0.70-delta call costs ~3% of the notional it controls. Everything here
sizes to delta-notional for that reason.

"Deep ITM" is a DELTA statement, not a strike statement. At 7 DTE with SPY IV
near 12%, delta 0.70 sits under 1% in the money. That is expected and is what
the backtest actually traded -- the tight spread is the reason this wrapper is
cheap, and the short extrinsic is the reason it is not a vol bet.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "KoreanStatArb" / "scripts"))
sys.path.append(str(Path(__file__).resolve().parents[1] / "vendor"))  # standalone fallback

import config as C          # noqa: E402
import market               # noqa: E402
from us_bear_lab import R, Q, iv_vec    # noqa: E402


def tradable_chain(spot_px: float) -> pd.DataFrame:
    """Contracts in the TRADING window (not the GEX window) with our own IV and
    delta computed from the mid -- the same inversion the backtest used, so the
    delta we select on is the delta that was validated. Alpaca's own greeks are
    carried alongside purely as a cross-check."""
    lo = max(C.DTE_MIN, C.TARGET_DTE - C.DTE_BAND)
    hi = min(C.DTE_MAX, C.TARGET_DTE + C.DTE_BAND)
    con = market.option_contracts(dte_min=lo, dte_max=hi, moneyness=0.10, spot_px=spot_px)
    if con.empty:
        raise RuntimeError(f"no listed contracts at {lo}-{hi} DTE")
    snaps = market.snapshots(con["symbol"].tolist())
    df = con.merge(snaps, on="symbol", how="inner")
    df = df[(df["bid"] > 0) & (df["ask"] > df["bid"]) & (df["mid"] > 0) &
            df["tradable"]].copy()
    if df.empty:
        raise RuntimeError("no two-sided markets in the trading window")

    S = df["underlyingPrice"].values.astype(float)
    K = df["strike"].values.astype(float)
    T = df["dte"].values.astype(float) / 365.0
    cp = np.where(df["side"].values == "call", 1.0, -1.0)
    iv = iv_vec(df["mid"].values.astype(float), S, K, T, cp)
    ok = np.isfinite(iv) & (iv > 0.02) & (iv < 3.0)
    df, S, K, T, cp, iv = df[ok].copy(), S[ok], K[ok], T[ok], cp[ok], iv[ok]
    d1 = (np.log(S / K) + (R - Q + 0.5 * iv ** 2) * T) / (iv * np.sqrt(T))
    df["iv"] = iv
    df["delta"] = np.exp(-Q * T) * np.where(cp > 0, norm.cdf(d1), norm.cdf(d1) - 1.0)
    df["abs_delta"] = np.abs(df["delta"])
    return df


def pick_contract(chain: pd.DataFrame, direction: float) -> pd.Series | None:
    """|delta| nearest TARGET_DELTA on the side that expresses `direction`,
    skipping anything quoting a spread wide enough to eat the edge."""
    side = "call" if direction > 0 else "put"
    c = chain[(chain["side"] == side) & (chain["spread_frac"] <= C.MAX_SPREAD_FRAC)]
    if c.empty:
        c = chain[chain["side"] == side]
        if c.empty:
            return None
        print(f"  [warn] every {side} quotes wider than "
              f"{100*C.MAX_SPREAD_FRAC:.0f}% of mid; taking the tightest anyway")
        c = c.nsmallest(5, "spread_frac")
    i = int(np.argmin(np.abs(c["abs_delta"].values - C.TARGET_DELTA)))
    return c.iloc[i]


def target_book(signal: dict, equity: float, chain: pd.DataFrame | None = None) -> dict:
    """The book the agent WANTS to hold at this moment, sleeve by sleeve."""
    spot_px = signal["spot"]
    chain = tradable_chain(spot_px) if chain is None else chain
    out = {}
    for name, direction, wt in (("sleeve1", signal["sleeve1_dir"], C.NOTIONAL_W_SLEEVE1),
                                ("sleeve2", signal["sleeve2_dir"], C.NOTIONAL_W_SLEEVE2)):
        if direction == 0:
            out[name] = dict(direction=0.0, symbol=None, qty=0, reason="signal flat")
            continue
        pick = pick_contract(chain, direction)
        if pick is None:
            out[name] = dict(direction=direction, symbol=None, qty=0,
                             reason="no acceptable contract")
            continue
        target_notional = equity * C.GROSS_LEVERAGE * wt
        per_contract = spot_px * float(pick["abs_delta"]) * 100.0
        qty = int(round(target_notional / per_contract))
        qty = max(qty, 1)
        out[name] = dict(direction=direction, symbol=pick["symbol"],
                         side=pick["side"], strike=float(pick["strike"]),
                         expiration=pd.Timestamp(pick["expiration"]),
                         dte=int(pick["dte"]), delta=float(pick["delta"]),
                         iv=float(pick["iv"]), bid=float(pick["bid"]),
                         ask=float(pick["ask"]), mid=float(pick["mid"]),
                         spread_frac=float(pick["spread_frac"]), qty=qty,
                         target_notional=target_notional,
                         actual_notional=qty * per_contract,
                         premium_cost=qty * float(pick["ask"]) * 100.0,
                         reason="ok")
    return out


def limit_price(row: dict, action: str) -> float:
    """Marketable limit at mid +/- LIMIT_COST_FRAC * half-spread.

    The backtest charged the FULL quoted spread on every trade, so a fill here is
    strictly better than what was tested. Erring in the other direction -- an
    optimistic mid-fill assumption -- is what flattered an option vertical by
    ~0.8 Sharpe in this fund's own earlier work."""
    mid = (row["bid"] + row["ask"]) / 2.0
    half = (row["ask"] - row["bid"]) / 2.0 * C.LIMIT_COST_FRAC
    return mid + half if action == "buy" else mid - half


def describe(book: dict) -> str:
    lines = []
    for name, b in book.items():
        if not b.get("symbol"):
            lines.append(f"  {name}: FLAT ({b['reason']})")
            continue
        lines.append(
            f"  {name}: {b['qty']}x {b['symbol']}  "
            f"{'CALL' if b['side'] == 'call' else 'PUT'} K={b['strike']:.0f} "
            f"{b['dte']}dte  Δ={b['delta']:+.2f} IV={100*b['iv']:.1f}%  "
            f"mid ${b['mid']:.2f} (spread {100*b['spread_frac']:.1f}%)")
        lines.append(
            f"           notional ${b['actual_notional']:,.0f} "
            f"(target ${b['target_notional']:,.0f})  premium at risk "
            f"${b['premium_cost']:,.0f}")
    return "\n".join(lines)
