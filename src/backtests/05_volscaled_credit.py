"""FIXING THE TEST'S OWN FLAW — vol-scaled credit AND strikes.

Panel D showed the killer limitation: every window was charged today's credit
($0.68 at VIX 15.4), including COVID (VIX 82) and 2022 (VIX 25-35). Real
premium scales with vol, so that biases the whole test NEGATIVE exactly where
the losses are. Correcting it could flip the verdict, so it must be corrected
before concluding anything.

Apples-to-apples correction = hold the structure at CONSTANT DELTA, not
constant strike distance. When vol is higher a 0.15-delta strike sits further
OTM AND pays more premium. So scale BOTH by k = VIX_entry / VIX_today:
    strike distance  ->  k * (today's distance)
    credit           ->  k * (today's credit)
Width scales too (the spread is k*$10 wide), so credit/width stays constant and
the structure is genuinely the same trade priced in its own vol environment.

Everything stays CAUSAL: k uses VIX at ENTRY only.
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
OUT = f"{ROOT}/AlpacaHackathon/research"
sys.path.insert(0, f"{ROOT}/mandatory_tests_for_deployment_2")


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
    calls, puts = [l for l in leg if l["cp"] == "C"], [l for l in leg if l["cp"] == "P"]
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


def stat(p, hold=17):
    if len(p) == 0:
        return None
    s = p.mean() / p.std() if p.std() else float("nan")
    return dict(n=len(p), E=p.mean(), win=(p > 0).mean(), sd=p.std(),
                sh=s, ann=s * np.sqrt(252 / hold), worst=p.min())


def row(lab, st, tot):
    if st is None:
        return f"{lab:<40}   (none)"
    return (f"{lab:<40}{st['n']:>6}{100*st['n']/tot:>7.0f}%{st['E']:>+9.3f}"
            f"{100*st['win']:>7.1f}%{st['sd']:>7.2f}{st['sh']:>+9.3f}{st['ann']:>+8.2f}{st['worst']:>8.2f}")


if __name__ == "__main__":
    import or_smh_signal as sig
    import t2_qld_signal as t2
    import FinanceDataReader as fdr

    today = datetime.now().date()
    c = get_structure(today)
    spy = spy_hist()
    px, idx = spy["close"].to_numpy(), spy.index
    spot = float(px[-1])
    N = int(round(c["dte"] * 252 / 365))
    entry = idx[:-N]
    ratio = px[N:] / px[:-N]

    vix = fdr.DataReader("^VIX", "2014-01-01")["Close"].dropna()
    vix.index = pd.to_datetime(vix.index)
    vix_today = float(vix.iloc[-1])
    v_entry = vix.reindex(pd.DatetimeIndex(entry)).ffill().to_numpy()
    k = v_entry / vix_today                       # vol-scaling factor, causal

    # today's structure expressed as fractions of spot
    put_dist = (spot - c["sp"]["strike"]) / spot          # short put distance
    call_dist = (c["sc"]["strike"] - spot) / spot
    put_cr, call_cr = c["put_credit"], c["call_credit"]

    move = ratio - 1.0                            # realized fractional move

    # --- STATIC (the flawed version) ---
    put_static = np.array([put_cr - max(0.0, min((put_dist + m) * -1 * spot if False else
                                                 (put_dist * spot) - (m * spot) * -1 * 0, WING))
                           for m in move])  # placeholder, replaced below
    put_static = np.array([
        put_cr - max(0.0, min((-m - put_dist) * spot, WING)) for m in move])
    call_static = np.array([
        call_cr - max(0.0, min((m - call_dist) * spot, WING)) for m in move])

    # --- VOL-SCALED (constant delta) ---
    put_scaled = np.array([
        kk * put_cr - max(0.0, min((-m - kk * put_dist) * spot, kk * WING))
        for m, kk in zip(move, k)])
    call_scaled = np.array([
        kk * call_cr - max(0.0, min((m - kk * call_dist) * spot, kk * WING))
        for m, kk in zip(move, k)])
    both_scaled = put_scaled + call_scaled

    # --- gate, causal at entry ---
    p_high = pd.Series(sig.msar_filtered_p_high(vix.values.tolist()), index=vix.index)
    p_slow = t2.p_slow_series(p_high).reindex(pd.DatetimeIndex(entry)).ffill().to_numpy()
    trend = t2.trend_ok_series(spy["close"]).reindex(pd.DatetimeIndex(entry)).ffill().to_numpy()
    ok = (~np.isnan(p_slow)) & (~np.isnan(trend))
    gate = ok & (p_slow < t2.VOL_ERA_P) & (trend > 0)

    hdr = (f"{'arm':<40}{'n':>6}{'freq':>8}{'E[pnl]':>9}{'win':>8}{'sd':>7}"
           f"{'Sh/tr':>9}{'Sh~ann':>8}{'worst':>8}")
    tot = int(ok.sum())
    print(f"VIX today {vix_today:.1f}; scaling k median {np.median(k[ok]):.2f} "
          f"(p10 {np.percentile(k[ok],10):.2f}, p90 {np.percentile(k[ok],90):.2f})")
    print(f"structure today: short put {c['sp']['strike']:.0f} "
          f"({100*put_dist:.1f}% OTM) credit {put_cr:.2f} | "
          f"short call {c['sc']['strike']:.0f} ({100*call_dist:.1f}% OTM) credit {call_cr:.2f}\n")
    print(hdr); print("-" * len(hdr))
    print(row("put spread STATIC credit, ungated", stat(put_static[ok]), tot))
    print(row("put spread VOL-SCALED, ungated", stat(put_scaled[ok]), tot))
    print(row("put spread VOL-SCALED, GATED", stat(put_scaled[gate]), tot))
    print("-" * len(hdr))
    print(row("call spread VOL-SCALED, ungated", stat(call_scaled[ok]), tot))
    print(row("iron condor VOL-SCALED, ungated", stat(both_scaled[ok]), tot))
    print(row("iron condor VOL-SCALED, GATED", stat(both_scaled[gate]), tot))

    yrs = pd.DatetimeIndex(entry).year
    print("\nper-year, VOL-SCALED put spread (gated / ungated E):")
    for y in sorted(set(yrs)):
        m = (yrs == y) & ok
        if m.sum() == 0:
            continue
        gp = put_scaled[(yrs == y) & gate]
        gs = f"{gp.mean():+.3f} (n={len(gp):3d})" if len(gp) else "   FLAT      "
        print(f"  {y}: gated {gs}   ungated {put_scaled[m].mean():+.3f}")

    mid = entry[int(ok.sum()) // 2]
    h1 = (pd.DatetimeIndex(entry) <= mid)
    print(f"\nhalf-split at {mid:%Y-%m}:")
    print(row("  H1 vol-scaled put GATED", stat(put_scaled[gate & h1]), max(1, (gate & h1).sum())))
    print(row("  H2 vol-scaled put GATED", stat(put_scaled[gate & ~h1]), max(1, (gate & ~h1).sum())))

    np.savez(f"/private/tmp/claude-501/-Users-lukecha-Library-Mobile-Documents-com-apple-CloudDocs-Trading-Folder/116dc565-8b15-4c83-be8b-92c502d3d8c2/scratchpad/_scaled.npz",
             put_static=put_static, put_scaled=put_scaled, call_scaled=call_scaled,
             both_scaled=both_scaled, gate=gate, ok=ok, k=k,
             dates=np.array([f"{x:%Y-%m-%d}" for x in entry]))
