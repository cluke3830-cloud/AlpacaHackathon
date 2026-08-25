"""CORE CHEAP TEST v2 — model-free.

v1 assumed one lognormal at average IV. Its own sanity check failed (E[pnl] at
the priced vol came out -0.54 when it must be ~-0.08 = the spread we pay), because
SPY's smile is steep (call IV 10.3% vs put IV 17.2%) and a flat-vol lognormal
does not reproduce the prices being traded. Reporting that -0.54 as "negative
expectancy" would have been a gamma-VRP-style proxy lie.

So: drop the model. Take SPY's ACTUAL historical N-day log returns, apply them to
today's spot, and run them through the real condor payoff at today's real credit.
Fat tails, skew and all - whatever the market actually did.

Question answered: if the next 24 days resemble a random draw from history,
does today's condor pay? And which historical episodes break it?
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from alpaca_keys import API_KEY, SECRET_KEY  # noqa: E402
K = K_API = API_KEY
S = S_API = SECRET_KEY
import math
from datetime import datetime, timedelta

import numpy as np



TARGET_DELTA = 0.15
WINGS = [5.0, 10.0, 20.0]


def parse(sym):
    b = sym[-15:]
    return datetime.strptime(b[:6], "%y%m%d").date(), b[6], int(b[7:]) / 1000.0


def get_chain(u="SPY"):
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionChainRequest
    return OptionHistoricalDataClient(K, S).get_option_chain(
        OptionChainRequest(underlying_symbol=u))


def spy_history():
    """Long daily history. Alpaca first (TC's chosen stack); FDR only if short."""
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    dc = StockHistoricalDataClient(K, S)
    end = datetime.now() - timedelta(days=1)
    df = dc.get_stock_bars(StockBarsRequest(
        symbol_or_symbols="SPY", timeframe=TimeFrame.Day,
        start=datetime(2015, 1, 1), end=end)).df.reset_index()
    src = "alpaca"
    if len(df) < 2000:
        try:
            import FinanceDataReader as fdr
            f = fdr.DataReader("SPY", "2007-01-01")
            df = f.reset_index().rename(columns={"Close": "close", "Date": "timestamp"})
            src = "FDR"
        except Exception:
            pass
    return df, src


def legs_for(chain, today):
    out = []
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
            out.append(dict(sym=sym, dte=dte, cp=cp, strike=strike, delta=g.delta,
                            bid=q.bid_price, ask=q.ask_price,
                            mid=(q.bid_price + q.ask_price) / 2,
                            iv=getattr(snap, "implied_volatility", None)))
    return out


def build(legs, wing):
    dte = min(l["dte"] for l in legs)
    leg = [l for l in legs if l["dte"] == dte]
    calls, puts = [l for l in leg if l["cp"] == "C"], [l for l in leg if l["cp"] == "P"]
    sc = min(calls, key=lambda x: abs(x["delta"] - TARGET_DELTA))
    sp = min(puts, key=lambda x: abs(abs(x["delta"]) - TARGET_DELTA))
    lcs = [c for c in calls if c["strike"] >= sc["strike"] + wing - 0.5]
    lps = [p for p in puts if p["strike"] <= sp["strike"] - wing + 0.5]
    if not lcs or not lps:
        return None
    lc, lp = min(lcs, key=lambda x: x["strike"]), max(lps, key=lambda x: x["strike"])
    return dict(dte=dte, sc=sc, sp=sp, lc=lc, lp=lp, wing=wing,
                credit=(sc["bid"] + sp["bid"]) - (lc["ask"] + lp["ask"]),
                credit_mid=(sc["mid"] + sp["mid"]) - (lc["mid"] + lp["mid"]))


def payoff(ST, c):
    cl = max(0.0, min(ST - c["sc"]["strike"], c["lc"]["strike"] - c["sc"]["strike"]))
    pl = max(0.0, min(c["sp"]["strike"] - ST, c["sp"]["strike"] - c["lp"]["strike"]))
    return c["credit"] - cl - pl


def run(c, spot, rets, dates):
    ST = spot * np.exp(rets)
    pnl = np.array([payoff(s, c) for s in ST])
    maxloss = c["wing"] - c["credit"]
    order = np.argsort(pnl)
    worst = [(dates[i], float(pnl[i]), float(100 * (np.exp(rets[i]) - 1))) for i in order[:3]]
    return dict(mean=pnl.mean(), median=float(np.median(pnl)), sd=pnl.std(),
                win=(pnl > 0).mean(), p5=float(np.percentile(pnl, 5)),
                maxloss=maxloss, worst=worst,
                sharpe_per_trade=pnl.mean() / pnl.std() if pnl.std() else float("nan"),
                pnl=pnl)


if __name__ == "__main__":
    today = datetime.now().date()
    chain, (hist, src) = get_chain("SPY"), spy_history()
    spot = float(hist["close"].iloc[-1])
    legs = legs_for(chain, today)
    px = hist["close"].to_numpy()
    ts = hist["timestamp"] if "timestamp" in hist else hist.iloc[:, 0]
    dates = [str(x)[:10] for x in ts]

    print(f"SPY history: {len(px)} bars from {dates[0]} to {dates[-1]}  (src={src})")
    print(f"spot={spot:.2f}\n")

    for wing in WINGS:
        c = build(legs, wing)
        if not c:
            print(f"wing ${wing:.0f}: not quotable\n")
            continue
        N = int(round(c["dte"] * 252 / 365))          # trading days in the window
        lr = np.log(px[N:] / px[:-N])                  # overlapping N-day log returns
        wd = dates[N:]
        r = run(c, spot, lr, wd)
        print("=" * 74)
        print(f"WING ${wing:.0f}  dte={c['dte']} (~{N} trading days)  "
              f"shorts {c['sp']['strike']:.0f}/{c['sc']['strike']:.0f}  "
              f"credit={c['credit']:.2f} (mid {c['credit_mid']:.2f})  maxloss={r['maxloss']:.2f}")
        print(f"  empirical draws: {len(lr)}   "
              f"breakeven winrate needed = {r['maxloss'] / wing:.1%}")
        print(f"  E[pnl]={r['mean']:+.3f}  median={r['median']:+.2f}  sd={r['sd']:.2f}  "
              f"win={r['win']:.1%}  p5={r['p5']:+.2f}")
        print(f"  per-trade Sharpe (unannualized) = {r['sharpe_per_trade']:+.3f}")
        print(f"  worst historical draws:")
        for d, p, mv in r["worst"]:
            print(f"    {d}: SPY {mv:+6.1f}% over window -> pnl {p:+.2f}")
        print()
        np.save(f"/private/tmp/claude-501/-Users-lukecha-Library-Mobile-Documents-com-apple-CloudDocs-Trading-Folder/116dc565-8b15-4c83-be8b-92c502d3d8c2/scratchpad/_pnl_w{int(wing)}.npy", r["pnl"])
    np.save("/private/tmp/claude-501/-Users-lukecha-Library-Mobile-Documents-com-apple-CloudDocs-Trading-Folder/116dc565-8b15-4c83-be8b-92c502d3d8c2/scratchpad/_meta.npy",
            np.array([spot, legs[0]["dte"] if legs else 0]))
