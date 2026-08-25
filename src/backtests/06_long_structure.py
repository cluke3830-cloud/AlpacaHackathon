"""ONE pre-specified test, motivated by theory not by cell-hunting.

Everything so far says SPY premium is FAIRLY PRICED (E ~ 0.00-0.03 ungated) and
that the +12.6%/yr equity risk premium is the dominant force in the data - it is
what ran over the short call side.

The signal we actually own (MSAR / 200d-trend / gamma) is a risk-ON-or-OFF EQUITY
signal. T2-QLD literally says "hold 2x NDX when the gate is on." Its natural
options expression is therefore a LONG defined-risk structure that is PAID by the
drift, not a short-premium structure that is run over by it.

So: call DEBIT spread (buy the ~0.35d call, sell ~0.15d) when the gate is on,
flat otherwise. Compared against the same gate applied to premium selling.

Costs charged honestly: a debit spread PAYS the spread on entry (buy ask / sell
bid), which is the conservative direction. Vol-scaled + causal throughout.

This is ONE test. If it looks good it needs fresh pre-registration before it is
believed - the multiple-testing budget on this session is already large.
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


def parse(sym):
    b = sym[-15:]
    return datetime.strptime(b[:6], "%y%m%d").date(), b[6], int(b[7:]) / 1000.0


def chain_legs(today):
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionChainRequest
    ch = OptionHistoricalDataClient(K, S).get_option_chain(
        OptionChainRequest(underlying_symbol="SPY"))
    legs = []
    for sym, snap in ch.items():
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
    return legs


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
        return f"{lab:<42}   (none)"
    return (f"{lab:<42}{st['n']:>6}{100*st['n']/tot:>7.0f}%{st['E']:>+9.3f}"
            f"{100*st['win']:>7.1f}%{st['sd']:>7.2f}{st['sh']:>+9.3f}"
            f"{st['ann']:>+8.2f}{st['worst']:>9.2f}")


if __name__ == "__main__":
    import or_smh_signal as sig
    import t2_qld_signal as t2
    import FinanceDataReader as fdr

    today = datetime.now().date()
    legs = chain_legs(today)
    dte = min(l["dte"] for l in legs)
    leg = [l for l in legs if l["dte"] == dte]
    calls = [l for l in leg if l["cp"] == "C"]
    puts = [l for l in leg if l["cp"] == "P"]

    spy = spy_hist()
    px, idx = spy["close"].to_numpy(), spy.index
    spot = float(px[-1])
    N = int(round(dte * 252 / 365))
    entry = idx[:-N]
    move = px[N:] / px[:-N] - 1.0

    # LONG call debit spread: buy ~0.35 delta, sell ~0.15 delta
    lcb = min(calls, key=lambda x: abs(x["delta"] - 0.35))     # bought
    scs = min(calls, key=lambda x: abs(x["delta"] - 0.15))     # sold
    debit = lcb["ask"] - scs["bid"]                            # pay the spread
    w_call = scs["strike"] - lcb["strike"]
    d_long = (lcb["strike"] - spot) / spot
    d_short = (scs["strike"] - spot) / spot

    # short PUT spread for comparison (0.15d short, $10 wing)
    sp = min(puts, key=lambda x: abs(abs(x["delta"]) - 0.15))
    lp = max([p for p in puts if p["strike"] <= sp["strike"] - 9.5], key=lambda x: x["strike"])
    put_cr = sp["bid"] - lp["ask"]
    put_dist = (spot - sp["strike"]) / spot
    put_w = sp["strike"] - lp["strike"]

    vix = fdr.DataReader("^VIX", "2014-01-01")["Close"].dropna()
    vix.index = pd.to_datetime(vix.index)
    vix_today = float(vix.iloc[-1])
    k = vix.reindex(pd.DatetimeIndex(entry)).ffill().to_numpy() / vix_today

    call_dbt = np.array([
        min(max((m - kk * d_long) * spot, 0.0), kk * w_call) - kk * debit
        for m, kk in zip(move, k)])
    put_sprd = np.array([
        kk * put_cr - max(0.0, min((-m - kk * put_dist) * spot, kk * put_w))
        for m, kk in zip(move, k)])

    p_high = pd.Series(sig.msar_filtered_p_high(vix.values.tolist()), index=vix.index)
    p_slow = t2.p_slow_series(p_high).reindex(pd.DatetimeIndex(entry)).ffill().to_numpy()
    trend = t2.trend_ok_series(spy["close"]).reindex(pd.DatetimeIndex(entry)).ffill().to_numpy()
    ok = (~np.isnan(p_slow)) & (~np.isnan(trend))
    gate = ok & (p_slow < t2.VOL_ERA_P) & (trend > 0)

    hdr = (f"{'arm':<42}{'n':>6}{'freq':>8}{'E[pnl]':>9}{'win':>8}{'sd':>7}"
           f"{'Sh/tr':>9}{'Sh~ann':>8}{'worst':>9}")
    tot = int(ok.sum())
    print(f"LONG call debit spread: buy {lcb['strike']:.0f} (d={lcb['delta']:.2f}) / "
          f"sell {scs['strike']:.0f} (d={scs['delta']:.2f})  debit ${debit:.2f}  width ${w_call:.0f}")
    print(f"   max gain ${w_call - debit:.2f}  max loss ${debit:.2f}  "
          f"breakeven move {100*(d_long + debit/spot):.2f}%\n")
    print(hdr); print("-" * len(hdr))
    print(row("LONG call spread  ungated", stat(call_dbt[ok]), tot))
    print(row("LONG call spread  GATED", stat(call_dbt[gate]), tot))
    print("-" * len(hdr))
    print(row("short put spread  ungated", stat(put_sprd[ok]), tot))
    print(row("short put spread  GATED", stat(put_sprd[gate]), tot))

    ent = pd.DatetimeIndex(entry)
    mid = ent[ok][int(ok.sum()) // 2]
    h1 = ent <= mid
    print(f"\nhalf-split at {mid:%Y-%m} — the robustness bar:")
    print(hdr); print("-" * len(hdr))
    print(row("  H1 LONG call spread GATED", stat(call_dbt[gate & h1]), max(1, (gate & h1).sum())))
    print(row("  H2 LONG call spread GATED", stat(call_dbt[gate & ~h1]), max(1, (gate & ~h1).sum())))
    print(row("  H1 short put spread GATED", stat(put_sprd[gate & h1]), max(1, (gate & h1).sum())))
    print(row("  H2 short put spread GATED", stat(put_sprd[gate & ~h1]), max(1, (gate & ~h1).sum())))

    yrs = ent.year
    print("\nper-year LONG call spread (gated / ungated):")
    for y in sorted(set(yrs)):
        m = (yrs == y) & ok
        if m.sum() == 0:
            continue
        gp = call_dbt[(yrs == y) & gate]
        gs = f"{gp.mean():+.3f} (n={len(gp):3d})" if len(gp) else "   FLAT      "
        print(f"  {y}: gated {gs}   ungated {call_dbt[m].mean():+.3f}")

    np.savez("/private/tmp/claude-501/-Users-lukecha-Library-Mobile-Documents-com-apple-CloudDocs-Trading-Folder/116dc565-8b15-4c83-be8b-92c502d3d8c2/scratchpad/_long.npz",
             call_dbt=call_dbt, put_sprd=put_sprd, gate=gate, ok=ok,
             dates=np.array([f"{x:%Y-%m-%d}" for x in entry]))
