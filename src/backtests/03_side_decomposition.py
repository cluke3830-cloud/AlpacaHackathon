"""DECOMPOSITION — which side of the condor is losing the money?

v2 showed a symmetric SPY condor is negative-expectancy empirically, and the
worst draws were mostly SPY RALLIES (+4.1/+4.8/+6.5%), not crashes. Hypothesis:
the equity risk premium (SPY 200 -> 763 over the sample) runs over the short
CALL, while the short PUT is paid for a risk that drift works against.

If true, the fix is structural, not a better signal: stop selling the call side.
That also matches the signal we actually have - MSAR/gamma/200d-MA is a RISK-ON
gate, which is the right conditioner for a put-side seller and the wrong one
for a symmetric premium seller.

Prints per-side economics + a gated cut, and dumps arrays for the viz.
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from alpaca_keys import API_KEY, SECRET_KEY  # noqa: E402
K = K_API = API_KEY
S = S_API = SECRET_KEY
import math
from datetime import datetime, timedelta

import numpy as np



SCRATCH = ("/private/tmp/claude-501/-Users-lukecha-Library-Mobile-Documents-"
           "com-apple-CloudDocs-Trading-Folder/116dc565-8b15-4c83-be8b-92c502d3d8c2/scratchpad")
TARGET_DELTA = 0.15
WING = 10.0


def parse(sym):
    b = sym[-15:]
    return datetime.strptime(b[:6], "%y%m%d").date(), b[6], int(b[7:]) / 1000.0


def get_legs(today):
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionChainRequest
    chain = OptionHistoricalDataClient(K, S).get_option_chain(
        OptionChainRequest(underlying_symbol="SPY"))
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
            out.append(dict(dte=dte, cp=cp, strike=strike, delta=g.delta,
                            bid=q.bid_price, ask=q.ask_price,
                            mid=(q.bid_price + q.ask_price) / 2,
                            iv=getattr(snap, "implied_volatility", None)))
    return out


def spy_hist():
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    df = StockHistoricalDataClient(K, S).get_stock_bars(StockBarsRequest(
        symbol_or_symbols="SPY", timeframe=TimeFrame.Day,
        start=datetime(2015, 1, 1),
        end=datetime.now() - timedelta(days=1))).df.reset_index()
    return df


if __name__ == "__main__":
    today = datetime.now().date()
    legs = get_legs(today)
    hist = spy_hist()
    px = hist["close"].to_numpy()
    dates = [str(x)[:10] for x in hist["timestamp"]]
    spot = float(px[-1])

    dte = min(l["dte"] for l in legs)
    leg = [l for l in legs if l["dte"] == dte]
    calls = [l for l in leg if l["cp"] == "C"]
    puts = [l for l in leg if l["cp"] == "P"]
    sc = min(calls, key=lambda x: abs(x["delta"] - TARGET_DELTA))
    sp = min(puts, key=lambda x: abs(abs(x["delta"]) - TARGET_DELTA))
    lc = min([c for c in calls if c["strike"] >= sc["strike"] + WING - 0.5],
             key=lambda x: x["strike"])
    lp = max([p for p in puts if p["strike"] <= sp["strike"] - WING + 0.5],
             key=lambda x: x["strike"])

    call_credit = sc["bid"] - lc["ask"]          # bear call spread, sold
    put_credit = sp["bid"] - lp["ask"]           # bull put spread, sold
    cw = lc["strike"] - sc["strike"]
    pw = sp["strike"] - lp["strike"]

    N = int(round(dte * 252 / 365))
    lr = np.log(px[N:] / px[:-N])
    wdates = dates[N:]
    ST = spot * np.exp(lr)

    call_pnl = np.array([call_credit - max(0.0, min(s - sc["strike"], cw)) for s in ST])
    put_pnl = np.array([put_credit - max(0.0, min(sp["strike"] - s, pw)) for s in ST])
    both = call_pnl + put_pnl

    print(f"spot={spot:.2f}  dte={dte} (~{N}td)  draws={len(lr)}")
    print(f"  sample {wdates[0]} .. {wdates[-1]}   "
          f"SPY {px[0]:.0f} -> {px[-1]:.0f}  "
          f"(ann. drift {100*(math.log(px[-1]/px[0])/(len(px)/252)):.1f}%)")
    print()
    hdr = f"{'side':<22}{'credit':>8}{'width':>7}{'E[pnl]':>9}{'win%':>8}{'sd':>7}{'per-trade Sh':>14}"
    print(hdr); print("-" * len(hdr))
    for name, pnl, cr, w in [
            (f"SHORT CALL spr {sc['strike']:.0f}/{lc['strike']:.0f}", call_pnl, call_credit, cw),
            (f"SHORT PUT  spr {sp['strike']:.0f}/{lp['strike']:.0f}", put_pnl, put_credit, pw),
            ("BOTH (iron condor)", both, call_credit + put_credit, WING)]:
        sh = pnl.mean() / pnl.std() if pnl.std() else float("nan")
        print(f"{name:<22}{cr:>8.2f}{w:>7.0f}{pnl.mean():>+9.3f}"
              f"{100*(pnl>0).mean():>8.1f}{pnl.std():>7.2f}{sh:>+14.3f}")

    # How much of the damage is bull-drift? Compare rally vs selloff windows.
    up = lr > 0
    print(f"\n  windows up: {up.mean():.1%}   "
          f"call-side E in UP windows: {call_pnl[up].mean():+.3f}   "
          f"put-side E in UP windows: {put_pnl[up].mean():+.3f}")
    print(f"  windows dn: {(~up).mean():.1%}   "
          f"call-side E in DN windows: {call_pnl[~up].mean():+.3f}   "
          f"put-side E in DN windows: {put_pnl[~up].mean():+.3f}")

    np.savez(f"{SCRATCH}/_decomp.npz", call_pnl=call_pnl, put_pnl=put_pnl,
             both=both, lr=lr, spot=spot, dte=dte,
             strikes=np.array([lp["strike"], sp["strike"], sc["strike"], lc["strike"]]),
             credits=np.array([call_credit, put_credit]),
             dates=np.array(wdates))
    print(f"\n  saved -> {SCRATCH}/_decomp.npz")
