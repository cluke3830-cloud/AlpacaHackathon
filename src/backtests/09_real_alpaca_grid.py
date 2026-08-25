"""THE PRE-REGISTERED GRID, ON REAL ALPACA OPTION PRICES.

No Black-Scholes anywhere in the P&L path. Entries are spaced >= the holding
period so every trade is INDEPENDENT and the t-stats need no overlap correction.

Grid (locked in PREREGISTRATION_timeframe_sweep.md):
    DTE {7,14,21,30,45} x exit {expiry, 50%TP} x gate {ungated, gated}
Pass bar (locked): Sharpe>=0.75 AND positive both halves AND t>=2.0 AND survives
multiple-testing correction across all cells.
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from alpaca_keys import API_KEY, SECRET_KEY  # noqa: E402
K = K_API = API_KEY
S = S_API = SECRET_KEY
import math
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

ROOT = "/Users/lukecha/Library/Mobile Documents/com~apple~CloudDocs/Trading Folder"
SCR = ("/private/tmp/claude-501/-Users-lukecha-Library-Mobile-Documents-"
       "com-apple-CloudDocs-Trading-Folder/116dc565-8b15-4c83-be8b-92c502d3d8c2/scratchpad")
sys.path.insert(0, f"{ROOT}/mandatory_tests_for_deployment_2")


DTES = [7, 14, 21, 30, 45]
WIDTH = 5.0
COST = 0.04
IV_GUESS = 0.14


def occ(exp, cp, strike):
    return f"SPY{exp:%y%m%d}{cp}{int(round(strike*1000)):08d}"


def otm_for(dte):
    """~0.15-delta distance: 1.04 sigma over the holding period."""
    return 1.04 * IV_GUESS * math.sqrt(dte / 365.0)


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
        except Exception as e:
            print(f"   batch {i}: {type(e).__name__}"); continue
        if df is None or df.empty:
            continue
        for sym, sub in df.groupby(level=0):
            s = sub.reset_index()
            s["d"] = pd.to_datetime([str(x)[:10] for x in s["timestamp"]])
            out[sym] = s.set_index("d")["close"]
    return out


def build_plan(spy, dte, gate_map):
    tdays = spy.index
    fridays = [d for d in tdays if d.weekday() == 4 and d >= pd.Timestamp("2024-01-26")]
    step = max(1, int(round(dte / 7)))          # space entries >= holding period
    plan, last_exit = [], None
    for exp in fridays:
        prior = tdays[tdays <= exp - pd.Timedelta(days=dte)]
        if len(prior) == 0:
            continue
        ent = prior[-1]
        if last_exit is not None and ent < last_exit:
            continue                             # enforce non-overlap
        S0 = float(spy.loc[ent])
        ks = float(round(S0 * (1 - otm_for(dte))))
        plan.append(dict(entry=ent, exp=exp, S0=S0, ks=ks, kl=ks - WIDTH,
                         ss=occ(exp, "P", ks), sl=occ(exp, "P", ks - WIDTH),
                         gate=bool(gate_map.get(ent, False))))
        last_exit = exp
    return plan


def evaluate(plan, bars, spy, take_profit):
    rows = []
    for p in plan:
        bs_, bl_ = bars.get(p["ss"]), bars.get(p["sl"])
        if bs_ is None or bl_ is None or p["entry"] not in bs_.index or p["entry"] not in bl_.index:
            continue
        credit = float(bs_.loc[p["entry"]]) - float(bl_.loc[p["entry"]])
        if credit <= 0.01 or credit >= WIDTH:
            continue
        net = credit * (1 - COST)
        pnl, exited = None, False
        if take_profit:
            path = [d for d in bs_.index if p["entry"] < d < p["exp"] and d in bl_.index]
            for d in path:
                val = float(bs_.loc[d]) - float(bl_.loc[d])
                if val < 0:
                    continue
                cur = net - val
                if cur >= 0.5 * credit:
                    pnl = cur - val * COST
                    exited = True
                    break
        if not exited:
            if p["exp"] not in spy.index:
                continue
            ST = float(spy.loc[p["exp"]])
            pnl = net - max(0.0, min(p["ks"] - ST, WIDTH))
        rows.append(dict(entry=p["entry"], gate=p["gate"], pnl=pnl, credit=credit))
    return pd.DataFrame(rows)


def stats(pnl, per_year):
    if len(pnl) < 8 or pnl.std() == 0:
        return None
    t = pnl.mean() / (pnl.std() / math.sqrt(len(pnl)))
    return dict(n=len(pnl), E=pnl.mean(), win=(pnl > 0).mean(),
                sharpe=pnl.mean() / pnl.std() * math.sqrt(per_year),
                t=t, worst=pnl.min())


if __name__ == "__main__":
    import or_smh_signal as sig
    import t2_qld_signal as t2
    import FinanceDataReader as fdr

    spy = spy_daily()
    vix = fdr.DataReader("^VIX", "2014-01-01")["Close"].dropna()
    vix.index = pd.to_datetime(vix.index)
    p_high = pd.Series(sig.msar_filtered_p_high(vix.values.tolist()), index=vix.index)
    p_slow = t2.p_slow_series(p_high).reindex(spy.index).ffill()
    trend = t2.trend_ok_series(spy).reindex(spy.index).ffill()
    gate_map = {d: (not np.isnan(p_slow[d])) and (not np.isnan(trend[d]))
                and p_slow[d] < t2.VOL_ERA_P and trend[d] > 0 for d in spy.index}

    plans, allsyms = {}, set()
    for dte in DTES:
        pl = build_plan(spy, dte, gate_map)
        plans[dte] = pl
        allsyms |= {p["ss"] for p in pl} | {p["sl"] for p in pl}
    print(f"fetching {len(allsyms)} real contracts ...")
    bars = fetch(sorted(allsyms))
    print(f"  got {len(bars)}\n")

    hdr = (f"{'DTE':>4} {'exit':<8} {'gate':<8} {'n':>5} {'E':>9} {'win':>7} "
           f"{'Sharpe':>8} {'t':>7} {'worst':>8}  verdict")
    print(hdr); print("-" * (len(hdr) + 8))
    res = []
    for dte in DTES:
        per_year = 365 / dte
        for tp_lab, tp in [("expiry", False), ("50%TP", True)]:
            df = evaluate(plans[dte], bars, spy, tp)
            if df.empty:
                continue
            for gl in ("ungated", "gated"):
                d = df if gl == "ungated" else df[df["gate"]]
                st = stats(d["pnl"].to_numpy(), per_year)
                if st is None:
                    print(f"{dte:>4} {tp_lab:<8} {gl:<8} {len(d):>5}   (too few)")
                    continue
                half = d["entry"].median()
                h1 = stats(d[d["entry"] <= half]["pnl"].to_numpy(), per_year)
                h2 = stats(d[d["entry"] > half]["pnl"].to_numpy(), per_year)
                both_pos = (h1 and h2 and h1["E"] > 0 and h2["E"] > 0)
                ok = st["sharpe"] >= .75 and both_pos and st["t"] >= 2.0
                res.append(dict(dte=dte, exit=tp_lab, gate=gl, **st,
                                h1=h1["E"] if h1 else np.nan, h2=h2["E"] if h2 else np.nan,
                                pass_pre=ok))
                print(f"{dte:>4} {tp_lab:<8} {gl:<8} {st['n']:>5} {st['E']:>+9.4f} "
                      f"{100*st['win']:>6.1f}% {st['sharpe']:>+8.2f} {st['t']:>+7.2f} "
                      f"{st['worst']:>+8.2f}  {'PASS' if ok else 'fail'}"
                      f"{'' if both_pos else ' (half-split)'}")
    R = pd.DataFrame(res)
    R.to_csv(f"{SCR}/_realgrid.csv", index=False)
    print("\n" + "=" * 70)
    n_cells = len(R)
    best = R.loc[R["t"].idxmax()]
    # Multiple-testing: expected max |t| under the null across n independent-ish cells
    exp_max_t = math.sqrt(2 * math.log(max(n_cells, 2)))
    print(f"cells tested this grid: {n_cells}   (plus 40 model cells earlier)")
    print(f"best cell: DTE {best['dte']} {best['exit']} {best['gate']}  "
          f"Sharpe {best['sharpe']:+.2f}  t={best['t']:+.2f}")
    print(f"expected max |t| under the NULL across {n_cells} cells ~ "
          f"sqrt(2*ln n) = {exp_max_t:.2f}")
    print(f"  -> best t {best['t']:+.2f} vs null-max {exp_max_t:.2f}: "
          f"{'EXCEEDS' if best['t'] > exp_max_t else 'DOES NOT EXCEED'}")
    print(f"cells passing the full pre-registered bar: {int(R['pass_pre'].sum())}")
    print(f"\nsaved {SCR}/_realgrid.csv")
