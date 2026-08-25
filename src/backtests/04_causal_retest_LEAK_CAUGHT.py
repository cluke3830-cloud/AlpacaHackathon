"""CORRECTED + CAUSAL RE-TEST.

BUG FOUND: condor_decompose.py saved `wdates = dates[N:]` = the window's END
date. gated_putspread.py then evaluated the regime gate on that date - i.e. it
decided whether to trade using data from the end of the very window it was
trading. Classic bias #1.

This rebuilds everything indexed on the ENTRY date and reports three arms:
   ENTRY-dated gate  (correct, causal)
   ENTRY-dated, +1 extra day of lag  (the Constitution's causal re-test:
                                      a real edge survives, a leak collapses)
   END-dated gate    (the bug, kept visible so the size of the error is on record)
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from alpaca_keys import API_KEY, SECRET_KEY  # noqa: E402
K = K_API = API_KEY
S = S_API = SECRET_KEY
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

ROOT = "/Users/lukecha/Library/Mobile Documents/com~apple~CloudDocs/Trading Folder"
sys.path.insert(0, f"{ROOT}/mandatory_tests_for_deployment_2")
SCRATCH = ("/private/tmp/claude-501/-Users-lukecha-Library-Mobile-Documents-"
           "com-apple-CloudDocs-Trading-Folder/116dc565-8b15-4c83-be8b-92c502d3d8c2/scratchpad")


TARGET_DELTA, WING = 0.15, 10.0


def parse(sym):
    b = sym[-15:]
    return datetime.strptime(b[:6], "%y%m%d").date(), b[6], int(b[7:]) / 1000.0


def get_structure(today):
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionChainRequest
    chain = OptionHistoricalDataClient(K, S).get_option_chain(
        OptionChainRequest(underlying_symbol="SPY"))
    legs = []
    for sym, snap in chain.items():
        g, q = getattr(snap, "greeks", None), getattr(snap, "latest_quote", None)
        if not g or not q or not q.bid_price or not q.ask_price:
            continue
        try:
            exp, cp, strike = parse(sym)
        except Exception:
            continue
        dte = (exp - today).days
        if 21 <= dte <= 45:
            legs.append(dict(dte=dte, cp=cp, strike=strike, delta=g.delta,
                             bid=q.bid_price, ask=q.ask_price))
    dte = min(l["dte"] for l in legs)
    leg = [l for l in legs if l["dte"] == dte]
    calls = [l for l in leg if l["cp"] == "C"]
    puts = [l for l in leg if l["cp"] == "P"]
    sc = min(calls, key=lambda x: abs(x["delta"] - TARGET_DELTA))
    sp = min(puts, key=lambda x: abs(abs(x["delta"]) - TARGET_DELTA))
    lc = min([c for c in calls if c["strike"] >= sc["strike"] + WING - .5], key=lambda x: x["strike"])
    lp = max([p for p in puts if p["strike"] <= sp["strike"] - WING + .5], key=lambda x: x["strike"])
    return dict(dte=dte, sc=sc, sp=sp, lc=lc, lp=lp,
                put_credit=sp["bid"] - lp["ask"], call_credit=sc["bid"] - lc["ask"])


def spy_hist():
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    df = StockHistoricalDataClient(K, S).get_stock_bars(StockBarsRequest(
        symbol_or_symbols="SPY", timeframe=TimeFrame.Day,
        start=datetime(2015, 1, 1),
        end=datetime.now() - timedelta(days=1))).df.reset_index()
    df["date"] = pd.to_datetime([str(x)[:10] for x in df["timestamp"]])
    return df.set_index("date")[["close"]]


def stats(pnl):
    if len(pnl) == 0:
        return None
    sh = pnl.mean() / pnl.std() if pnl.std() else float("nan")
    return dict(n=len(pnl), E=pnl.mean(), win=(pnl > 0).mean(), sd=pnl.std(),
                sh=sh, ann=sh * np.sqrt(252 / 17), worst=pnl.min())


def line(label, st, tot):
    if st is None:
        return f"{label:<38}      (no trades)"
    return (f"{label:<38}{st['n']:>6}{100*st['n']/tot:>7.0f}%{st['E']:>+9.3f}"
            f"{100*st['win']:>7.1f}%{st['sd']:>7.2f}{st['sh']:>+9.3f}"
            f"{st['ann']:>+8.2f}{st['worst']:>+8.2f}")


if __name__ == "__main__":
    import or_smh_signal as sig
    import t2_qld_signal as t2

    today = datetime.now().date()
    c = get_structure(today)
    spy = spy_hist()
    px = spy["close"].to_numpy()
    idx = spy.index
    spot = float(px[-1])
    N = int(round(c["dte"] * 252 / 365))

    # window i: ENTER at idx[i], EXIT at idx[i+N]
    entry = idx[:-N]
    ST = px[N:]
    put_pnl = np.array([c["put_credit"] - max(0.0, min(c["sp"]["strike"] - s * spot / px[i], WING))
                        for i, s in enumerate(ST)])
    # NOTE: scale each historical path to today's spot so strikes stay comparable
    ratio = px[N:] / px[:-N]
    STs = spot * ratio
    put_pnl = np.array([c["put_credit"] - max(0.0, min(c["sp"]["strike"] - s, WING)) for s in STs])
    call_pnl = np.array([c["call_credit"] - max(0.0, min(s - c["sc"]["strike"], WING)) for s in STs])
    both = put_pnl + call_pnl

    import FinanceDataReader as fdr
    vix = fdr.DataReader("^VIX", "2014-01-01")["Close"].dropna()
    vix.index = pd.to_datetime(vix.index)
    p_high = pd.Series(sig.msar_filtered_p_high(vix.values.tolist()), index=vix.index)
    p_slow_s = t2.p_slow_series(p_high)
    trend_s = t2.trend_ok_series(spy["close"])

    def build(gate_dates, lag_days=0):
        gd = pd.DatetimeIndex(gate_dates)
        if lag_days:
            pos = [max(0, idx.get_loc(x) - lag_days) for x in gd]
            gd = idx[pos]
        f = pd.DataFrame(index=range(len(gate_dates)))
        f["p_slow"] = p_slow_s.reindex(gd).ffill().to_numpy()
        f["trend"] = trend_s.reindex(gd).ffill().to_numpy()
        f["put"], f["call"], f["both"] = put_pnl, call_pnl, both
        f["date"] = pd.DatetimeIndex(entry)
        return f.dropna()

    hdr = (f"{'arm':<38}{'n':>6}{'freq':>8}{'E[pnl]':>9}{'win':>8}{'sd':>7}"
           f"{'Sh/tr':>9}{'Sh~ann':>8}{'worst':>8}")

    print(f"structure: short put {c['sp']['strike']:.0f}/{c['lp']['strike']:.0f} "
          f"credit {c['put_credit']:.2f} | short call {c['sc']['strike']:.0f}/"
          f"{c['lc']['strike']:.0f} credit {c['call_credit']:.2f} | dte {c['dte']} (~{N}td)")
    print(f"windows {len(entry)}   {entry[0]:%Y-%m-%d} .. {entry[-1]:%Y-%m-%d}\n")

    for tag, gdates, lag in [
            ("A. ENTRY-dated (CORRECT/causal)", entry, 0),
            ("B. ENTRY-dated, +1 day extra lag", entry, 1),
            ("C. END-dated  (the BUG)", idx[N:], 0)]:
        f = build(gdates, lag)
        gate = (f["p_slow"] < t2.VOL_ERA_P) & (f["trend"] > 0)
        tot = len(f)
        print("=" * len(hdr)); print(tag); print(hdr); print("-" * len(hdr))
        print(line("put spread UNGATED", stats(f["put"].to_numpy()), tot))
        print(line("put spread GATED", stats(f.loc[gate, "put"].to_numpy()), tot))
        print(line("  gate = trend veto only",
                   stats(f.loc[f["trend"] > 0, "put"].to_numpy()), tot))
        print(line("  gate = vol-era veto only",
                   stats(f.loc[f["p_slow"] < t2.VOL_ERA_P, "put"].to_numpy()), tot))
        print(line("iron condor GATED", stats(f.loc[gate, "both"].to_numpy()), tot))
        if tag.startswith("A"):
            mid = f["date"].iloc[len(f) // 2]
            print("-" * len(hdr))
            for lab, m in [("H1", f["date"] <= mid), ("H2", f["date"] > mid)]:
                sub, sg = f[m], gate[m]
                print(line(f"  {lab} put GATED (split {mid:%Y-%m})",
                           stats(sub.loc[sg, "put"].to_numpy()), m.sum()))
            np.savez(f"{SCRATCH}/_causal.npz",
                     put=f["put"].to_numpy(), both=f["both"].to_numpy(),
                     call=f["call"].to_numpy(), gate=gate.to_numpy(),
                     dates=np.array([f"{x:%Y-%m-%d}" for x in f["date"]]))
            years = f["date"].dt.year
            print("-" * len(hdr))
            print("  per-year (causal, gated / ungated E):")
            for y in sorted(years.unique()):
                m = years == y
                gp = f[m].loc[gate[m], "put"].to_numpy()
                up = f.loc[m, "put"].to_numpy()
                gs = f"{gp.mean():+.3f} (n={len(gp):3d})" if len(gp) else "  FLAT     "
                print(f"    {y}: gated {gs}   ungated {up.mean():+.3f}")
        print()
