"""CORE CHEAP TEST — does the iron condor have positive expectancy at all?

Cost is survivable (probe 4: 1-7% of credit). So the question becomes the one
that actually decides Sharpe: the structure is priced off IMPLIED vol, but it
pays off against REALIZED vol. The gap (VRP) is the entire edge.

Method, deliberately model-light:
  1. Build the real condor from live Alpaca quotes (as probe 4).
  2. Price its terminal P&L under a lognormal at IMPLIED vol   -> should be ~0
     (that is what "fairly priced" means; it is the sanity check on the math).
  3. Re-price under REALIZED vol (trailing 20/60d on SPY)      -> that is the edge.
  4. Sweep realized vol to find the break-even RV: above it the condor loses.
Then plot the thing that could KILL this: how little RV has to rise before the
edge is gone, with the actual historical RV distribution overlaid.
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
WING = 10.0


def get_chain(u="SPY"):
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionChainRequest
    return OptionHistoricalDataClient(K, S).get_option_chain(
        OptionChainRequest(underlying_symbol=u))


def get_spy_history(days=800):
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    dc = StockHistoricalDataClient(K, S)
    end = datetime.now() - timedelta(days=1)
    df = dc.get_stock_bars(StockBarsRequest(
        symbol_or_symbols="SPY", timeframe=TimeFrame.Day,
        start=end - timedelta(days=days), end=end)).df
    return df.reset_index()


def parse(sym):
    b = sym[-15:]
    return datetime.strptime(b[:6], "%y%m%d").date(), b[6], int(b[7:]) / 1000.0


def build_condor(chain, spot, today):
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
        if not (21 <= dte <= 45):
            continue
        legs.append(dict(sym=sym, dte=dte, cp=cp, strike=strike, delta=g.delta,
                         bid=q.bid_price, ask=q.ask_price,
                         mid=(q.bid_price + q.ask_price) / 2,
                         iv=getattr(snap, "implied_volatility", None)))
    if not legs:
        return None
    dte = min(l["dte"] for l in legs)
    leg = [l for l in legs if l["dte"] == dte]
    calls = [l for l in leg if l["cp"] == "C"]
    puts = [l for l in leg if l["cp"] == "P"]
    sc = min(calls, key=lambda x: abs(x["delta"] - TARGET_DELTA))
    sp = min(puts, key=lambda x: abs(abs(x["delta"]) - TARGET_DELTA))
    lc = min([c for c in calls if c["strike"] >= sc["strike"] + WING - 0.5],
             key=lambda x: x["strike"], default=None)
    lp = min([p for p in puts if p["strike"] <= sp["strike"] - WING + 0.5],
             key=lambda x: -x["strike"], default=None)
    if not lc or not lp:
        return None
    return dict(dte=dte, sc=sc, sp=sp, lc=lc, lp=lp,
                credit_mid=(sc["mid"] + sp["mid"]) - (lc["mid"] + lp["mid"]),
                credit_nat=(sc["bid"] + sp["bid"]) - (lc["ask"] + lp["ask"]),
                width=min(lc["strike"] - sc["strike"], sp["strike"] - lp["strike"]))


def terminal_pnl(ST, c, credit):
    """Iron condor P&L at expiry, per share."""
    call_loss = max(0.0, min(ST - c["sc"]["strike"], c["lc"]["strike"] - c["sc"]["strike"]))
    put_loss = max(0.0, min(c["sp"]["strike"] - ST, c["sp"]["strike"] - c["lp"]["strike"]))
    return credit - call_loss - put_loss


def expected_pnl(c, credit, spot, vol, dte, n=400_000, seed=7):
    """MC expected P&L under lognormal(vol) over dte calendar days."""
    rng = np.random.default_rng(seed)
    T = dte / 365.0
    z = rng.standard_normal(n)
    ST = spot * np.exp(-0.5 * vol * vol * T + vol * math.sqrt(T) * z)
    pnl = np.array([terminal_pnl(s, c, credit) for s in ST])
    return pnl.mean(), pnl.std(), (pnl > 0).mean(), np.percentile(pnl, 5)


def realized_vol(df, w):
    px = df["close"].to_numpy()
    r = np.diff(np.log(px))
    return float(np.std(r[-w:], ddof=1) * math.sqrt(252))


if __name__ == "__main__":
    today = datetime.now().date()
    chain = get_chain("SPY")
    hist = get_spy_history()
    spot = float(hist["close"].iloc[-1])
    c = build_condor(chain, spot, today)
    if not c:
        raise SystemExit("no condor buildable")

    rv20, rv60, rv252 = (realized_vol(hist, w) for w in (20, 60, 252))
    atm_iv = (c["sc"]["iv"] + c["sp"]["iv"]) / 2
    credit = c["credit_nat"]                      # honest: what we'd actually get

    print(f"spot={spot:.2f}  dte={c['dte']}  width={c['width']:.0f}")
    print(f"  short call {c['sc']['strike']:.0f} (d={c['sc']['delta']:+.3f}, iv={c['sc']['iv']:.4f})")
    print(f"  short put  {c['sp']['strike']:.0f} (d={c['sp']['delta']:+.3f}, iv={c['sp']['iv']:.4f})")
    print(f"  credit mid={c['credit_mid']:.2f}  natural={c['credit_nat']:.2f}")
    print(f"\n  avg short-strike IV = {atm_iv:6.2%}")
    print(f"  realized vol  20d = {rv20:6.2%}   60d = {rv60:6.2%}   252d = {rv252:6.2%}")
    print(f"  VRP (IV - RV20)   = {atm_iv - rv20:+6.2%}")

    print("\n  --- expected P&L per condor (per share; x100 per contract) ---")
    for label, vol in [("priced IV", atm_iv), ("RV 20d", rv20),
                       ("RV 60d", rv60), ("RV 252d", rv252)]:
        m, sd, wr, p5 = expected_pnl(c, credit, spot, vol, c["dte"])
        print(f"    {label:10s} vol={vol:6.2%}  E[pnl]={m:+6.3f}  sd={sd:5.2f}  "
              f"win={wr:5.1%}  p5={p5:+6.2f}")

    print("\n  --- break-even: how high can realized vol go before edge dies? ---")
    lo, hi = 0.01, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        m, *_ = expected_pnl(c, credit, spot, mid, c["dte"], n=120_000)
        if m > 0:
            lo = mid
        else:
            hi = mid
    print(f"    break-even realized vol = {lo:.2%}  "
          f"(vs RV20 {rv20:.2%}, headroom {lo - rv20:+.2%})")

    np.save("/private/tmp/claude-501/-Users-lukecha-Library-Mobile-Documents-com-apple-CloudDocs-Trading-Folder/116dc565-8b15-4c83-be8b-92c502d3d8c2/scratchpad/_condor_ctx.npy",
            np.array([spot, c["dte"], c["width"], credit, atm_iv, rv20, rv60, rv252, lo,
                      c["sc"]["strike"], c["sp"]["strike"],
                      c["lc"]["strike"], c["lp"]["strike"]]))
    print("\n  (context saved for viz)")
