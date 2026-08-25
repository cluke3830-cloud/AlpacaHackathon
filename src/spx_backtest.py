"""Canonical backtest — REAL SPX option quotes, 2018-2026, 8.4 years.

This is the deepest honest dataset available for this book: our own
`chains_SPX{,_pre2022}.parquet` carry real bid/ask at 5-9 DTE and cover
Fed-Pivot-2018, COVID-2020, Tech-Bear-2022 and SVB-2023 — the four stress
windows the Constitution's bias #5 requires. Alpaca's option history begins
2024-01-18 and contains none of them, which is exactly why a 2.6-year Alpaca
backtest reported Sharpe +1.54 for a book that is flat over the full record.

Structure/gate logic is imported from `option_premium_signal` — the same module
the integrity manifest imports, so there is one source of truth.

Returns a tidy DataFrame; no plotting, no printing, no file writes. Callers
(research scripts, the manifest, the tests) decide what to do with it.
"""
from __future__ import annotations

import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "mandatory_tests_for_deployment_2"))

import option_premium_signal as ops   # noqa: E402

CHAIN_DIR = ROOT / "U.S._gamma_strategy" / "Reflexive_0DTE_Research" / "data"
_COLS = ["date", "expiration", "side", "strike", "dte", "bid", "ask", "underlyingPrice"]


def load_put_chains(dte_lo: int = 6, dte_hi: int = 8) -> pd.DataFrame:
    """Real SPX put quotes near the target tenor, both parquet vintages."""
    parts = []
    for f in ("chains_SPX_pre2022.parquet", "chains_SPX.parquet"):
        p = CHAIN_DIR / f
        if not p.exists():
            continue
        parts.append(pd.read_parquet(p, columns=_COLS))
    if not parts:
        raise FileNotFoundError(f"no SPX chain parquet under {CHAIN_DIR}")
    df = pd.concat(parts, ignore_index=True)
    df = df[(df["side"] == "put") & df["dte"].between(dte_lo, dte_hi)].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["exp"] = pd.to_datetime(df["expiration"], unit="s").dt.normalize()
    return df


def gate_series(index_dates: pd.DatetimeIndex):
    """(p_slow, trend_ok) aligned to `index_dates` — the DEPLOYED T2-QLD
    functions, reused verbatim so this sleeve adds no new degrees of freedom.

    Both inputs are computed on their OWN full history and only then reindexed
    onto the trade dates. Computing the 200d MA on the chain's date index instead
    would burn the first 200 sessions as warm-up and silently force all of 2018 —
    a stress window we specifically need — to read FLAT.
    """
    import FinanceDataReader as fdr
    import or_smh_signal as sig
    import t2_qld_signal as t2

    vix = fdr.DataReader("^VIX", "2014-01-01")["Close"].dropna()
    vix.index = pd.to_datetime(vix.index)
    p_high = pd.Series(sig.msar_filtered_p_high(vix.values.tolist()), index=vix.index)
    p_slow = t2.p_slow_series(p_high).reindex(index_dates).ffill()

    spx = fdr.DataReader("US500", "2016-01-01")["Close"].dropna()
    spx.index = pd.to_datetime(spx.index)
    trend = t2.trend_ok_series(spx).reindex(index_dates).ffill()
    return p_slow, trend


def run(otm: float = ops.OTM_SHORT, cost_frac: float = ops.COST_FRAC) -> pd.DataFrame:
    """One row per weekly, NON-OVERLAPPING trade.

    Non-overlap matters: it is what makes the reported t-stats honest without an
    overlap correction. Entries are spaced so a new one never opens before the
    previous expires.

    Columns include both a NATURAL fill (short bid / long ask — what we would
    actually get) and a MID fill, so the gate's fill_price checker has a real
    alternate-fill series rather than a fabricated one.
    """
    ch = load_put_chains()
    spot = ch.groupby("date")["underlyingPrice"].first().sort_index()
    p_slow, trend = gate_series(spot.index)

    rows, last_exp = [], None
    for d in spot.index:
        if last_exp is not None and d <= last_exp:
            continue
        sub = ch[ch["date"] == d]
        if sub.empty:
            continue
        exp = sub.iloc[(sub["dte"] - ops.DTE_TARGET).abs().argsort()]["exp"].iloc[0]
        if exp not in spot.index:
            continue
        leg = sub[sub["exp"] == exp]
        if leg.empty:
            continue

        S0, ST = float(spot.loc[d]), float(spot.loc[exp])
        k_short_t, k_long_t = ops.strikes_for(S0, otm)
        si = (leg["strike"] - k_short_t).abs().idxmin()
        srow = leg.loc[si]
        li = (leg["strike"] - k_long_t).abs().idxmin()
        lrow = leg.loc[li]
        ks, kl = float(srow["strike"]), float(lrow["strike"])
        if ks - kl <= 0:
            continue

        credit_nat = ops.credit_from_quotes(float(srow["bid"]), float(lrow["ask"]))
        credit_mid = ((float(srow["bid"]) + float(srow["ask"])) / 2
                      - (float(lrow["bid"]) + float(lrow["ask"])) / 2)
        if credit_nat <= 0.01 or credit_nat >= (ks - kl):
            continue

        rows.append(dict(
            entry=d, exp=exp, spot=S0, settle=ST, k_short=ks, k_long=kl,
            width=ks - kl, credit_natural=credit_nat, credit_mid=credit_mid,
            gate=1.0 if ops.gate_long(p_slow.get(d, np.nan), trend.get(d, np.nan)) else 0.0,
            pnl_natural=ops.pnl_per_width(credit_nat, ks, kl, ST, cost_frac),
            pnl_mid=ops.pnl_per_width(credit_mid, ks, kl, ST, cost_frac),
            move=ST / S0 - 1.0,
        ))
        last_exp = exp

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["year"] = df["entry"].dt.year
    return df.reset_index(drop=True)


def sharpe_weekly(pnl) -> float:
    p = pd.Series(pnl).dropna().to_numpy()
    if len(p) < 8 or p.std() == 0:
        return float("nan")
    return float(p.mean() / p.std() * math.sqrt(52))


def tstat(pnl) -> float:
    p = pd.Series(pnl).dropna().to_numpy()
    if len(p) < 8 or p.std() == 0:
        return float("nan")
    return float(p.mean() / (p.std() / math.sqrt(len(p))))
