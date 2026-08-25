"""TIMEFRAME SWEEP — pre-registered in PREREGISTRATION_timeframe_sweep.md.

20 cells: DTE {7,14,21,30,45} x exit {expiry, 50% profit-take} x {ungated, gated}.
Path-dependent, causal, laddered daily entries, daily mark-to-market equity curve.

Vol model (declared, per bias #3): IV/VIX ratio curve fitted to TODAY's live Alpaca
chain over (moneyness, dte), applied historically as IV = ratio x VIX_t. Alpaca has
no historical bid/ask so a model is unavoidable; this one is at least anchored to
real observed quotes.
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
OUT = f"{ROOT}/AlpacaHackathon/research"
SCR = ("/private/tmp/claude-501/-Users-lukecha-Library-Mobile-Documents-"
       "com-apple-CloudDocs-Trading-Folder/116dc565-8b15-4c83-be8b-92c502d3d8c2/scratchpad")
sys.path.insert(0, f"{ROOT}/mandatory_tests_for_deployment_2")



SHORT_DELTA = 0.15
WIDTH_PCT = 10.0 / 763.0        # $10 wing at today's spot, as a fraction
R = 0.04
DTES = [7, 14, 21, 30, 45]
COSTS = [0.04, 0.08]            # slippage as fraction of credit, each way


# ---------------- Black-Scholes ----------------
def _nd(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_put(S, Kk, T, r, sig):
    if T <= 1e-9 or sig <= 1e-9:
        return max(Kk - S, 0.0)
    d1 = (math.log(S / Kk) + (r + .5 * sig * sig) * T) / (sig * math.sqrt(T))
    d2 = d1 - sig * math.sqrt(T)
    return Kk * math.exp(-r * T) * _nd(-d2) - S * _nd(-d1)


def put_delta(S, Kk, T, r, sig):
    if T <= 1e-9 or sig <= 1e-9:
        return -1.0 if Kk > S else 0.0
    d1 = (math.log(S / Kk) + (r + .5 * sig * sig) * T) / (sig * math.sqrt(T))
    return _nd(d1) - 1.0


# ---------------- live chain -> IV/VIX ratio surface ----------------
def parse(sym):
    b = sym[-15:]
    return datetime.strptime(b[:6], "%y%m%d").date(), b[6], int(b[7:]) / 1000.0


def fit_iv_ratio(vix_today):
    """ratio(logmoneyness, dte) = IV / VIX, from today's real put quotes."""
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionChainRequest
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    sc = StockHistoricalDataClient(K_API, S_API)
    spot = float(sc.get_stock_bars(StockBarsRequest(
        symbol_or_symbols="SPY", timeframe=TimeFrame.Day,
        start=datetime.now() - timedelta(days=8),
        end=datetime.now())).df["close"].iloc[-1])
    ch = OptionHistoricalDataClient(K_API, S_API).get_option_chain(
        OptionChainRequest(underlying_symbol="SPY"))
    today = datetime.now().date()
    pts = []
    for sym, snap in ch.items():
        iv = getattr(snap, "implied_volatility", None)
        if not iv:
            continue
        try:
            exp, cp, strike = parse(sym)
        except Exception:
            continue
        if cp != "P":
            continue
        dte = (exp - today).days
        if not (3 <= dte <= 70):
            continue
        m = math.log(strike / spot)
        if abs(m) > .15:
            continue
        pts.append((m, dte, iv / vix_today * 100.0))
    arr = np.array(pts)
    # quadratic in moneyness + linear in sqrt(dte): ratio ~ a + b*m + c*m^2 + d*sqrt(dte)
    M, D, Y = arr[:, 0], arr[:, 1], arr[:, 2]
    X = np.column_stack([np.ones_like(M), M, M ** 2, np.sqrt(D)])
    coef, *_ = np.linalg.lstsq(X, Y, rcond=None)
    resid = Y - X @ coef
    print(f"  IV/VIX surface fit on {len(arr)} live put quotes; "
          f"R^2={1 - resid.var() / Y.var():.3f}  spot={spot:.2f}")
    return coef, spot


def iv_of(coef, m, dte, vix):
    r = coef[0] + coef[1] * m + coef[2] * m * m + coef[3] * math.sqrt(max(dte, 1))
    return max(0.02, r * vix / 100.0)


# ---------------- data ----------------
def load():
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    import FinanceDataReader as fdr
    df = StockHistoricalDataClient(K_API, S_API).get_stock_bars(StockBarsRequest(
        symbol_or_symbols="SPY", timeframe=TimeFrame.Day,
        start=datetime(2015, 1, 1),
        end=datetime.now() - timedelta(days=1))).df.reset_index()
    df["date"] = pd.to_datetime([str(x)[:10] for x in df["timestamp"]])
    spy = df.set_index("date")[["close"]]
    vix = fdr.DataReader("^VIX", "2014-01-01")["Close"].dropna()
    vix.index = pd.to_datetime(vix.index)
    return spy, vix


def solve_strike(S, dte_cal, vix, coef, target_delta):
    """Find the strike whose BS put delta ~= -target_delta."""
    T = dte_cal / 365.0
    lo, hi = S * 0.70, S * 1.02
    for _ in range(40):
        mid = (lo + hi) / 2
        sig = iv_of(coef, math.log(mid / S), dte_cal, vix)
        d = put_delta(S, mid, T, R, sig)
        if abs(d) > target_delta:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def spread_val(S, ks, kl, dte_cal, vix, coef):
    T = max(dte_cal, 0) / 365.0
    sig_s = iv_of(coef, math.log(ks / S), max(dte_cal, 1), vix)
    sig_l = iv_of(coef, math.log(kl / S), max(dte_cal, 1), vix)
    return bs_put(S, ks, T, R, sig_s) - bs_put(S, kl, T, R, sig_l)


def run_cell(spy, vix, coef, gate_arr, dte, take_profit, cost):
    """Laddered daily entries. Returns daily portfolio P&L series (per $1 of width)."""
    px = spy["close"].to_numpy()
    idx = spy.index
    vx = vix.reindex(idx).ffill().to_numpy()
    n = len(px)
    hold_td = int(round(dte * 252 / 365))
    daily = np.zeros(n)
    trades = []
    for i in range(250, n - hold_td - 1):
        if not gate_arr[i]:
            continue
        S0, v0 = px[i], vx[i]
        if not np.isfinite(v0):
            continue
        ks = solve_strike(S0, dte, v0, coef, SHORT_DELTA)
        kl = ks - WIDTH_PCT * S0
        credit0 = spread_val(S0, ks, kl, dte, v0, coef)
        if credit0 <= 0.01:
            continue
        credit_net = credit0 * (1 - cost)
        width = ks - kl
        prev = 0.0
        exited = False
        for j in range(1, hold_td + 1):
            t = i + j
            rem = dte * (1 - j / hold_td)
            val = (spread_val(px[t], ks, kl, rem, vx[t], coef) if rem > 0.5
                   else max(0.0, min(ks - px[t], width)))
            pnl = credit_net - val
            if not exited and (pnl >= 0.5 * credit0 or j == hold_td):
                if take_profit and pnl >= 0.5 * credit0 and j < hold_td:
                    pnl -= val * cost           # exit slippage on the buy-back
                    daily[t] += pnl - prev
                    trades.append(pnl / width)
                    exited = True
                    break
            daily[t] += pnl - prev
            prev = pnl
        if not exited:
            trades.append(prev / width)
    return daily, np.array(trades), hold_td


def metrics(daily, trades, start=250):
    d = daily[start:]
    d = d[np.isfinite(d)]
    if len(d) < 50 or d.std() == 0:
        return None
    shp = d.mean() / d.std() * math.sqrt(252)
    eq = np.cumsum(d)
    dd = float((eq - np.maximum.accumulate(eq)).min())
    n_eff = max(2, len(trades))
    t = trades.mean() / (trades.std() / math.sqrt(n_eff)) if len(trades) > 1 and trades.std() else float("nan")
    return dict(sharpe=shp, dd=dd, n=len(trades), E=trades.mean() if len(trades) else np.nan,
                win=(trades > 0).mean() if len(trades) else np.nan, t=t, eq=eq)


if __name__ == "__main__":
    import or_smh_signal as sig
    import t2_qld_signal as t2

    spy, vix = load()
    vix_today = float(vix.iloc[-1])
    print(f"VIX today {vix_today:.2f}")
    coef, _ = fit_iv_ratio(vix_today)

    p_high = pd.Series(sig.msar_filtered_p_high(vix.values.tolist()), index=vix.index)
    p_slow = t2.p_slow_series(p_high).reindex(spy.index).ffill().to_numpy()
    trend = t2.trend_ok_series(spy["close"]).reindex(spy.index).ffill().to_numpy()
    ok = (~np.isnan(p_slow)) & (~np.isnan(trend))
    gated = ok & (p_slow < t2.VOL_ERA_P) & (trend > 0)
    ungated = ok.copy()

    print(f"sample {spy.index[0]:%Y-%m-%d}..{spy.index[-1]:%Y-%m-%d}  "
          f"gate on {100*gated[ok].mean():.0f}% of valid days\n")

    results = []
    hdr = (f"{'DTE':>4} {'exit':<10} {'gate':<8} {'cost':>5} "
           f"{'n':>5} {'E/width':>9} {'win':>7} {'Sharpe':>8} {'maxDD':>8} {'t':>7}")
    print(hdr); print("-" * len(hdr))
    for dte in DTES:
        for tp_label, tp in [("expiry", False), ("50%TP", True)]:
            for gl, garr in [("ungated", ungated), ("gated", gated)]:
                for cost in COSTS:
                    daily, trades, hold = run_cell(spy, vix, coef, garr, dte, tp, cost)
                    m = metrics(daily, trades)
                    if m is None:
                        print(f"{dte:>4} {tp_label:<10} {gl:<8} {cost:>5.0%}    (insufficient)")
                        continue
                    results.append(dict(dte=dte, exit=tp_label, gate=gl, cost=cost, **m))
                    print(f"{dte:>4} {tp_label:<10} {gl:<8} {cost:>5.0%} "
                          f"{m['n']:>5} {m['E']:>+9.4f} {100*m['win']:>6.1f}% "
                          f"{m['sharpe']:>+8.2f} {m['dd']:>+8.2f} {m['t']:>+7.2f}")
    df = pd.DataFrame([{k: v for k, v in r.items() if k != "eq"} for r in results])
    df.to_csv(f"{SCR}/_sweep.csv", index=False)
    np.save(f"{SCR}/_sweep_eq.npy",
            np.array([r["eq"] for r in results], dtype=object), allow_pickle=True)
    print(f"\nsaved {SCR}/_sweep.csv   ({len(df)} cells)")
