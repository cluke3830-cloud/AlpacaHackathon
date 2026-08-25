"""FRAGILITY CHECK + FINAL VIZ.

The 7-DTE hold-to-expiry cell is the only one with a large, genuinely
non-overlapping sample (n=128). But its t moved 1.36 -> 2.09 on a 0.12% change in
strike distance. If a trivial strike change swings significance that much, the
result is fragile regardless of its headline number.

Sweep the short-strike distance and plot t / Sharpe against it. A real edge is a
plateau; an artifact is a spike.
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

ROOT = "/Users/lukecha/Library/Mobile Documents/com~apple~CloudDocs/Trading Folder"
OUT = f"{ROOT}/AlpacaHackathon/research"
SCR = ("/private/tmp/claude-501/-Users-lukecha-Library-Mobile-Documents-"
       "com-apple-CloudDocs-Trading-Folder/116dc565-8b15-4c83-be8b-92c502d3d8c2/scratchpad")


WIDTH, COST = 5.0, 0.04
BG, PANEL, FG = "#0a0a0f", "#10131a", "#e6e6ee"
CYAN, GREEN, MAG, AMBER, RED, GREY = "#00E7FD", "#00FF7F", "#FF00FF", "#FFBB00", "#FF6B6B", "#8a8a99"


def occ(exp, k):
    return f"SPY{exp:%y%m%d}P{int(round(k*1000)):08d}"


def spy_daily():
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    df = StockHistoricalDataClient(K_API, S_API).get_stock_bars(StockBarsRequest(
        symbol_or_symbols="SPY", timeframe=TimeFrame.Day, start=datetime(2023, 12, 1),
        end=datetime.now() - timedelta(days=1))).df.reset_index()
    df["date"] = pd.to_datetime([str(x)[:10] for x in df["timestamp"]])
    return df.set_index("date")["close"]


def fetch(syms):
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionBarsRequest
    from alpaca.data.timeframe import TimeFrame
    dc = OptionHistoricalDataClient(K_API, S_API)
    out = {}
    for i in range(0, len(syms), 100):
        try:
            df = dc.get_option_bars(OptionBarsRequest(
                symbol_or_symbols=syms[i:i + 100], timeframe=TimeFrame.Day,
                start=datetime(2024, 1, 1), end=datetime.now() - timedelta(days=1))).df
        except Exception:
            continue
        if df is None or df.empty:
            continue
        for s, sub in df.groupby(level=0):
            x = sub.reset_index()
            x["d"] = pd.to_datetime([str(v)[:10] for v in x["timestamp"]])
            out[s] = x.set_index("d")["close"]
    return out


if __name__ == "__main__":
    spy = spy_daily()
    td = spy.index
    fri = [d for d in td if d.weekday() == 4 and d >= pd.Timestamp("2024-01-26")]
    entries = []
    for exp in fri:
        prior = td[td <= exp - pd.Timedelta(days=7)]
        if len(prior):
            entries.append((prior[-1], exp, float(spy.loc[prior[-1]])))

    OTMS = np.arange(0.014, 0.0285, 0.001)
    need = set()
    for otm in OTMS:
        for ent, exp, S0 in entries:
            ks = float(round(S0 * (1 - otm)))
            need |= {occ(exp, ks), occ(exp, ks - WIDTH)}
    print(f"fetching {len(need)} contracts for the strike sweep ...")
    bars = fetch(sorted(need))
    print(f"  got {len(bars)}\n")

    res = []
    for otm in OTMS:
        pn = []
        for ent, exp, S0 in entries:
            ks = float(round(S0 * (1 - otm)))
            a, b = bars.get(occ(exp, ks)), bars.get(occ(exp, ks - WIDTH))
            if a is None or b is None or ent not in a.index or ent not in b.index:
                continue
            cr = float(a.loc[ent]) - float(b.loc[ent])
            if cr <= 0.01 or cr >= WIDTH or exp not in spy.index:
                continue
            ST = float(spy.loc[exp])
            pn.append(cr * (1 - COST) - max(0.0, min(ks - ST, WIDTH)))
        pn = np.array(pn)
        if len(pn) < 20 or pn.std() == 0:
            continue
        res.append(dict(otm=100 * otm, n=len(pn), E=pn.mean(), win=(pn > 0).mean(),
                        sharpe=pn.mean() / pn.std() * math.sqrt(52),
                        t=pn.mean() / (pn.std() / math.sqrt(len(pn))),
                        worst=pn.min(), eq=np.cumsum(pn)))
    R = pd.DataFrame([{k: v for k, v in r.items() if k != "eq"} for r in res])
    print(R.to_string(index=False,
                      formatters={"otm": "{:.2f}".format, "E": "{:+.4f}".format,
                                  "win": "{:.3f}".format, "sharpe": "{:+.2f}".format,
                                  "t": "{:+.2f}".format, "worst": "{:+.2f}".format}))

    N_CELLS = 58
    null_max = math.sqrt(2 * math.log(N_CELLS))
    print(f"\nmultiple-testing threshold across {N_CELLS} cells tested tonight: "
          f"E[max|t|] under null = {null_max:.2f}")
    print(f"strike sweep t range: {R['t'].min():+.2f} .. {R['t'].max():+.2f}  "
          f"(spread {R['t'].max()-R['t'].min():.2f} from a {100*(OTMS[-1]-OTMS[0]):.1f}pp strike change)")
    print(f"cells in the sweep clearing {null_max:.2f}: {int((R['t']>null_max).sum())}/{len(R)}")

    # ---- viz ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 3, figsize=(19, 6.2), facecolor=BG)
    for a in ax:
        a.set_facecolor(PANEL); a.tick_params(colors=FG, labelsize=8.5)
        for s_ in a.spines.values():
            s_.set_color("#333")
        a.grid(alpha=.13, color=FG, lw=.5)

    ax[0].plot(R["otm"], R["t"], "o-", color=CYAN, lw=2, ms=6)
    ax[0].axhline(2.0, color=AMBER, ls="--", lw=1.3)
    ax[0].text(R["otm"].iloc[0], 2.04, "pre-registered bar t=2.0", color=AMBER, fontsize=8.5)
    ax[0].axhline(null_max, color=RED, ls="--", lw=1.4)
    ax[0].text(R["otm"].iloc[0], null_max + .04,
               f"multiple-testing threshold {null_max:.2f} ({N_CELLS} cells)", color=RED, fontsize=8.5)
    ax[0].axhline(0, color=FG, lw=.8)
    ax[0].set_xlabel("short-strike distance (% OTM)", color=FG)
    ax[0].set_ylabel("t-stat (n≈128 independent weekly trades)", color=FG)
    ax[0].set_title("A. FRAGILITY — t swings wildly with a trivial strike change\n"
                    "a real edge is a plateau; this is not", color=FG, fontsize=11)

    ax[1].plot(R["otm"], R["sharpe"], "o-", color=GREEN, lw=2, ms=6)
    ax[1].axhline(0.75, color=AMBER, ls="--", lw=1.3)
    ax[1].text(R["otm"].iloc[0], .78, "pre-reg Sharpe bar 0.75", color=AMBER, fontsize=8.5)
    ax[1].axhline(0, color=FG, lw=.8)
    ax[1].set_xlabel("short-strike distance (% OTM)", color=FG)
    ax[1].set_ylabel("annualized Sharpe", color=FG)
    ax[1].set_title("B. same instability in Sharpe\n"
                    "real 2024–2026 Alpaca prices, hold-to-expiry", color=FG, fontsize=11)

    for r in res:
        col = CYAN if abs(r["otm"] - 1.9) < .06 else GREY
        ax[2].plot(r["eq"], lw=2.0 if col == CYAN else .8, color=col,
                   alpha=1.0 if col == CYAN else .45)
    ax[2].axhline(0, color=FG, lw=.8)
    ax[2].set_xlabel("trade # (weekly, non-overlapping)", color=FG)
    ax[2].set_ylabel("cumulative P&L per share ($)", color=FG)
    ax[2].set_title("C. every strike's equity curve\n"
                    "all rise — but 2024–2026 contains NO bear market (bias #5)",
                    color=FG, fontsize=11)

    fig.suptitle("7-DTE SPY put spread on REAL Alpaca option prices — robustness check: "
                 "the result does not survive a strike-distance sweep",
                 color=FG, fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, .93])
    p = f"{OUT}/strike_fragility.png"
    fig.savefig(p, dpi=115, facecolor=BG)
    print(f"\nsaved {p}")
    R.to_csv(f"{SCR}/_strikesweep.csv", index=False)
