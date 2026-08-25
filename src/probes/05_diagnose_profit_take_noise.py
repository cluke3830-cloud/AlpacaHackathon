"""DIAGNOSTIC — why do the 50%-profit-take cells show 100% win rates?

Suspicion: the spread value on any given day is computed as
    close(short leg) - close(long leg)
but those are LAST-TRADE prices for two separate contracts, struck at different
times of day and often thinly traded. The difference is therefore noisy. The
50%-take rule scans the path for the FIRST day the spread looks cheap - so it
systematically SELECTS the noise, manufacturing profit. Hold-to-expiry cells are
immune because they settle against the real SPY close.

Test: measure how often the bar-implied spread value is outright IMPOSSIBLE
(negative, or wider than the strike width). Any material rate proves the series
is too noisy to drive a path-dependent exit rule.
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from alpaca_keys import API_KEY, SECRET_KEY  # noqa: E402
K = K_API = API_KEY
S = S_API = SECRET_KEY
import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd



WIDTH, IV_GUESS = 5.0, 0.14


def occ(exp, cp, k):
    return f"SPY{exp:%y%m%d}{cp}{int(round(k*1000)):08d}"


def spy_daily():
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    df = StockHistoricalDataClient(K_API, S_API).get_stock_bars(StockBarsRequest(
        symbol_or_symbols="SPY", timeframe=TimeFrame.Day, start=datetime(2023, 12, 1),
        end=datetime.now() - timedelta(days=1))).df.reset_index()
    df["date"] = pd.to_datetime([str(x)[:10] for x in df["timestamp"]])
    return df.set_index("date")["close"]


def fetch(symbols):
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionBarsRequest
    from alpaca.data.timeframe import TimeFrame
    dc = OptionHistoricalDataClient(K_API, S_API)
    out = {}
    for i in range(0, len(symbols), 100):
        try:
            df = dc.get_option_bars(OptionBarsRequest(
                symbol_or_symbols=symbols[i:i + 100], timeframe=TimeFrame.Day,
                start=datetime(2024, 1, 1), end=datetime.now() - timedelta(days=1))).df
        except Exception:
            continue
        if df is None or df.empty:
            continue
        for sym, sub in df.groupby(level=0):
            s = sub.reset_index()
            s["d"] = pd.to_datetime([str(x)[:10] for x in s["timestamp"]])
            out[sym] = s.set_index("d")[["close", "volume", "trade_count"]]
    return out


if __name__ == "__main__":
    spy = spy_daily()
    td = spy.index
    dte = 14
    otm = 1.04 * IV_GUESS * math.sqrt(dte / 365.0)
    fri = [d for d in td if d.weekday() == 4 and d >= pd.Timestamp("2024-01-26")]
    plan, last = [], None
    for exp in fri:
        prior = td[td <= exp - pd.Timedelta(days=dte)]
        if not len(prior):
            continue
        ent = prior[-1]
        if last is not None and ent < last:
            continue
        S0 = float(spy.loc[ent]); ks = float(round(S0 * (1 - otm)))
        plan.append(dict(entry=ent, exp=exp, ks=ks, ss=occ(exp, "P", ks),
                         sl=occ(exp, "P", ks - WIDTH)))
        last = exp
    bars = fetch(sorted({p["ss"] for p in plan} | {p["sl"] for p in plan}))

    tot = neg = over = 0
    vols_s, vols_l, jumps = [], [], []
    for p in plan:
        a, b = bars.get(p["ss"]), bars.get(p["sl"])
        if a is None or b is None:
            continue
        days = [d for d in a.index if p["entry"] < d < p["exp"] and d in b.index]
        prev = None
        for d in days:
            v = float(a.loc[d, "close"]) - float(b.loc[d, "close"])
            tot += 1
            if v < 0:
                neg += 1
            if v > WIDTH:
                over += 1
            vols_s.append(float(a.loc[d, "trade_count"]))
            vols_l.append(float(b.loc[d, "trade_count"]))
            if prev is not None:
                jumps.append(abs(v - prev))
            prev = v

    print(f"14-DTE path days examined: {tot}")
    print(f"  IMPOSSIBLE spread values:")
    print(f"    negative (long worth more than short): {neg}  ({100*neg/max(tot,1):.1f}%)")
    print(f"    greater than width ${WIDTH:.0f}:        {over}  ({100*over/max(tot,1):.1f}%)")
    print(f"    TOTAL impossible:                     {neg+over}  ({100*(neg+over)/max(tot,1):.1f}%)")
    j = np.array(jumps)
    print(f"\n  day-over-day |change| in bar-implied spread value:")
    print(f"    median ${np.median(j):.3f}   p90 ${np.percentile(j,90):.3f}   max ${j.max():.3f}")
    print(f"    (a $5-wide spread whose value jumps this much day to day is noise-dominated)")
    print(f"\n  liquidity of the legs (daily trade_count):")
    print(f"    short leg median {np.median(vols_s):.0f}   p10 {np.percentile(vols_s,10):.0f}")
    print(f"    long  leg median {np.median(vols_l):.0f}   p10 {np.percentile(vols_l,10):.0f}")
    print("\nVERDICT: a path-dependent exit rule driven by these values is scanning for"
          "\nthe day the NOISE is most favourable. That is selection, not profit-taking.")
