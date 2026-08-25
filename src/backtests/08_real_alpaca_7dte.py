"""GROUND TRUTH — real Alpaca option bars, no pricing model.

The sweep said 7 DTE scores Sharpe ~+1.9 with t>13. That is not credible: nothing
in this fund's history clears t~5, it contradicts the pre-registered H1, and the
P&L was measured against the SAME Black-Scholes model that set the entry price.
A model that both sells and marks the option can manufacture any edge it likes.

So: drop the model entirely. Use REAL traded option prices from Alpaca
(2024-01-18 onward, the full available history) for actual weekly SPY put spreads.

Method:
  - every weekly expiry in range, enter ~7 calendar days before
  - short strike ~1.9% OTM (~0.15 delta at 7dte, 13% IV), long strike $5 below
  - entry credit  = real short bar close - real long bar close on the entry date
  - exit          = real intrinsic at expiry (settled vs real SPY close)
  - costs charged on the real credit
No Black-Scholes anywhere in the P&L path.
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



SCR = ("/private/tmp/claude-501/-Users-lukecha-Library-Mobile-Documents-"
       "com-apple-CloudDocs-Trading-Folder/116dc565-8b15-4c83-be8b-92c502d3d8c2/scratchpad")
OTM_PCT = 0.019
WIDTH = 5.0
COST = 0.04


def occ(exp, cp, strike):
    return f"SPY{exp:%y%m%d}{cp}{int(round(strike*1000)):08d}"


def spy_daily():
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    df = StockHistoricalDataClient(K_API, S_API).get_stock_bars(StockBarsRequest(
        symbol_or_symbols="SPY", timeframe=TimeFrame.Day,
        start=datetime(2023, 12, 1),
        end=datetime.now() - timedelta(days=1))).df.reset_index()
    df["date"] = pd.to_datetime([str(x)[:10] for x in df["timestamp"]])
    return df.set_index("date")["close"]


def fetch_bars(symbols, start, end):
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionBarsRequest
    from alpaca.data.timeframe import TimeFrame
    dc = OptionHistoricalDataClient(K_API, S_API)
    out = {}
    B = 100
    for i in range(0, len(symbols), B):
        chunk = symbols[i:i + B]
        try:
            df = dc.get_option_bars(OptionBarsRequest(
                symbol_or_symbols=chunk, timeframe=TimeFrame.Day,
                start=start, end=end)).df
        except Exception as e:
            print(f"  batch {i}: {type(e).__name__}: {str(e)[:80]}")
            continue
        if df is None or df.empty:
            continue
        for sym, sub in df.groupby(level=0):
            s = sub.reset_index()
            s["d"] = pd.to_datetime([str(x)[:10] for x in s["timestamp"]])
            out[sym] = s.set_index("d")["close"]
    return out


if __name__ == "__main__":
    spy = spy_daily()
    tdays = spy.index

    # every Friday with data on/after 2024-01-18
    fridays = [d for d in tdays if d.weekday() == 4 and d >= pd.Timestamp("2024-01-26")]
    plan = []
    for exp in fridays:
        prior = tdays[tdays <= exp - pd.Timedelta(days=7)]
        if len(prior) == 0:
            continue
        ent = prior[-1]
        S0 = float(spy.loc[ent])
        ks = round(S0 * (1 - OTM_PCT))
        kl = ks - WIDTH
        plan.append(dict(entry=ent, exp=exp, S0=S0, ks=float(ks), kl=float(kl),
                         ss=occ(exp, "P", ks), sl=occ(exp, "P", kl)))
    print(f"planned {len(plan)} weekly trades, "
          f"{plan[0]['entry']:%Y-%m-%d} .. {plan[-1]['entry']:%Y-%m-%d}")

    syms = sorted({p["ss"] for p in plan} | {p["sl"] for p in plan})
    print(f"fetching {len(syms)} real contracts from Alpaca ...")
    bars = fetch_bars(syms, datetime(2024, 1, 1), datetime.now() - timedelta(days=1))
    print(f"  got bars for {len(bars)} contracts")

    rows = []
    for p in plan:
        bs_, bl_ = bars.get(p["ss"]), bars.get(p["sl"])
        if bs_ is None or bl_ is None:
            continue
        if p["entry"] not in bs_.index or p["entry"] not in bl_.index:
            continue
        credit = float(bs_.loc[p["entry"]]) - float(bl_.loc[p["entry"]])
        if credit <= 0.01 or credit >= WIDTH:
            continue
        if p["exp"] not in spy.index:
            continue
        ST = float(spy.loc[p["exp"]])
        intrinsic = max(0.0, min(p["ks"] - ST, WIDTH))
        pnl = credit * (1 - COST) - intrinsic
        rows.append(dict(entry=p["entry"], exp=p["exp"], S0=p["S0"], ST=ST,
                         ks=p["ks"], credit=credit, intrinsic=intrinsic, pnl=pnl,
                         move=100 * (ST / p["S0"] - 1)))
    df = pd.DataFrame(rows)
    print(f"\nusable REAL trades: {len(df)}")
    if df.empty:
        raise SystemExit("no usable real trades")

    pnl = df["pnl"].to_numpy()
    n = len(pnl)
    t = pnl.mean() / (pnl.std() / math.sqrt(n)) if pnl.std() else float("nan")
    sharpe_ann = pnl.mean() / pnl.std() * math.sqrt(52) if pnl.std() else float("nan")
    print(f"  mean credit ${df['credit'].mean():.3f}  (width ${WIDTH:.0f}, "
          f"credit/width {100*df['credit'].mean()/WIDTH:.1f}%)")
    print(f"  E[pnl] = {pnl.mean():+.4f}/share   win = {100*(pnl>0).mean():.1f}%   "
          f"sd = {pnl.std():.3f}")
    print(f"  weekly Sharpe (non-overlapping!) = {pnl.mean()/pnl.std():+.3f}  "
          f"-> annualized {sharpe_ann:+.2f}")
    print(f"  t = {t:+.2f}  (n={n} INDEPENDENT weekly trades, no overlap)")
    print(f"  worst = {pnl.min():+.3f}   best = {pnl.max():+.3f}")
    eq = np.cumsum(pnl)
    print(f"  total = {eq[-1]:+.2f}/share   maxDD = {float((eq-np.maximum.accumulate(eq)).min()):+.2f}")

    df["yr"] = df["entry"].dt.year
    print("\n  per-year:")
    for y, g in df.groupby("yr"):
        print(f"    {y}: n={len(g):3d}  E={g['pnl'].mean():+.4f}  "
              f"win={100*(g['pnl']>0).mean():5.1f}%  worst={g['pnl'].min():+.3f}")

    print("\n  worst 5 real trades:")
    for _, r in df.nsmallest(5, "pnl").iterrows():
        print(f"    entry {r['entry']:%Y-%m-%d} exp {r['exp']:%Y-%m-%d}  "
              f"SPY {r['S0']:.0f}->{r['ST']:.0f} ({r['move']:+.1f}%)  "
              f"credit {r['credit']:.2f}  pnl {r['pnl']:+.2f}")
    df.to_csv(f"{SCR}/_real7dte.csv", index=False)
    print(f"\nsaved {SCR}/_real7dte.csv")
