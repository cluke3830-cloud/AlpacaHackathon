"""THE DECISIVE QUESTION — is the 2024-2026 sample's tail representative?

The strike sweep is smooth and monotonic (not noise). Further OTM scores better,
via a win rate climbing to 96.9%. But at 96.9% on n=127 the entire downside rests
on ~4 loss events, inside a 2.6-year window with no bear market.

So: measure how often SPY actually breaches these strikes over 7 days, in the
2024-2026 test window vs the full 2016-2026 history that includes 2018, COVID and
2022. Then re-price the strategy at the LONGER history's breach rate.

If the test window under-samples the tail, the headline Sharpe is a bull-market
artifact and bias #5 (regime/sample-window) is the binding constraint.
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


WIDTH = 5.0
BG, PANEL, FG = "#0a0a0f", "#10131a", "#e6e6ee"
CYAN, GREEN, AMBER, RED, GREY = "#00E7FD", "#00FF7F", "#FFBB00", "#FF6B6B", "#8a8a99"


def spy_long():
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    df = StockHistoricalDataClient(K_API, S_API).get_stock_bars(StockBarsRequest(
        symbol_or_symbols="SPY", timeframe=TimeFrame.Day, start=datetime(2015, 1, 1),
        end=datetime.now() - timedelta(days=1))).df.reset_index()
    df["date"] = pd.to_datetime([str(x)[:10] for x in df["timestamp"]])
    return df.set_index("date")["close"]


if __name__ == "__main__":
    spy = spy_long()
    px, idx = spy.to_numpy(), spy.index
    H = 5                                     # ~7 calendar days = 5 trading days
    r = px[H:] / px[:-H] - 1.0
    d = idx[:-H]
    test = (d >= pd.Timestamp("2024-01-26"))
    full = np.ones(len(d), bool)
    eras = {
        "2024-2026 (the test window)": test,
        "2016-2026 (full)": full,
        "2018 (Fed pivot)": (d.year == 2018),
        "2020 (COVID)": (d.year == 2020),
        "2022 (tech bear)": (d.year == 2022),
    }

    sweep = pd.read_csv(f"{SCR}/_strikesweep.csv")
    print(f"P(SPY falls more than X% over {H} trading days)\n")
    otms = [1.9, 2.2, 2.5, 2.8]
    hdr = f"{'era':<30}" + "".join([f"{'-'+str(o)+'%':>10}" for o in otms]) + f"{'n':>8}"
    print(hdr); print("-" * len(hdr))
    rates = {}
    for name, m in eras.items():
        rr = r[m]
        row = [float((rr < -o / 100).mean()) for o in otms]
        rates[name] = row
        print(f"{name:<30}" + "".join([f"{100*v:>9.2f}%" for v in row]) + f"{len(rr):>8}")

    print("\n\nRe-pricing the strategy at the FULL-history breach rate")
    print("(same credits actually collected; only the loss FREQUENCY corrected)\n")
    hdr2 = (f"{'OTM':>6}{'as-tested':>12}{'full-hist':>12}{'ratio':>8}"
            f"{'E tested':>11}{'E adj':>11}{'Sharpe tested':>15}{'Sharpe adj':>12}")
    print(hdr2); print("-" * len(hdr2))
    out = []
    for _, s in sweep.iterrows():
        o = s["otm"]
        p_test = float((r[test] < -o / 100).mean())
        p_full = float((r[full] < -o / 100).mean())
        if p_test <= 0:
            continue
        # decompose tested E into win/loss legs, then re-weight by the full-history rate
        win_rate = s["win"]
        loss_rate = 1 - win_rate
        if loss_rate <= 0:
            avg_win = s["E"]; avg_loss = s["worst"]
        else:
            avg_loss = s["worst"] * 0.85       # losses cluster near max; conservative
            avg_win = (s["E"] - loss_rate * avg_loss) / win_rate
        p_adj = min(0.99, loss_rate * (p_full / p_test) if p_test > 0 else loss_rate)
        E_adj = (1 - p_adj) * avg_win + p_adj * avg_loss
        var_adj = ((1 - p_adj) * (avg_win - E_adj) ** 2 + p_adj * (avg_loss - E_adj) ** 2)
        sh_adj = E_adj / math.sqrt(var_adj) * math.sqrt(52) if var_adj > 0 else np.nan
        out.append(dict(otm=o, p_test=p_test, p_full=p_full, E=s["E"], E_adj=E_adj,
                        sh=s["sharpe"], sh_adj=sh_adj))
        print(f"{o:>6.2f}{100*p_test:>11.2f}%{100*p_full:>11.2f}%"
              f"{p_full/p_test:>8.2f}{s['E']:>+11.4f}{E_adj:>+11.4f}"
              f"{s['sharpe']:>+15.2f}{sh_adj:>+12.2f}")
    O = pd.DataFrame(out)

    # ---- corrected viz ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(1, 3, figsize=(19, 6.2), facecolor=BG)
    for a in ax:
        a.set_facecolor(PANEL); a.tick_params(colors=FG, labelsize=8.5)
        for s_ in a.spines.values():
            s_.set_color("#333")
        a.grid(alpha=.13, color=FG, lw=.5)

    ax[0].plot(sweep["otm"], sweep["t"], "o-", color=CYAN, lw=2, ms=6)
    ax[0].axhline(2.0, color=AMBER, ls="--", lw=1.2)
    ax[0].axhline(2.85, color=RED, ls="--", lw=1.3)
    ax[0].text(1.42, 2.05, "pre-reg bar t=2.0", color=AMBER, fontsize=8)
    ax[0].text(1.42, 2.90, "multiple-testing threshold 2.85 (58 cells)", color=RED, fontsize=8)
    ax[0].axhline(0, color=FG, lw=.8)
    ax[0].set_xlabel("short-strike distance (% OTM)", color=FG)
    ax[0].set_ylabel("t-stat (n≈128 independent weekly trades)", color=FG)
    ax[0].set_title("A. the sweep is SMOOTH and MONOTONIC, not noise\n"
                    "(I called this 'fragile' first — that was wrong)", color=FG, fontsize=11)

    w = .35
    xs = np.arange(len(otms))
    ax[1].bar(xs - w / 2, [100 * rates["2024-2026 (the test window)"][i] for i in range(len(otms))],
              w, color=CYAN, label="2024–2026 (test window)")
    ax[1].bar(xs + w / 2, [100 * rates["2016-2026 (full)"][i] for i in range(len(otms))],
              w, color=GREY, label="2016–2026 (incl. 2018/COVID/2022)")
    ax[1].set_xticks(xs); ax[1].set_xticklabels([f"-{o}%" for o in otms])
    ax[1].set_xlabel(f"SPY move over {H} trading days", color=FG)
    ax[1].set_ylabel("% of windows breaching", color=FG)
    ax[1].set_title("B. THE TEST WINDOW UNDER-SAMPLES THE TAIL\n"
                    "the losses live exactly where 2024–26 is quietest", color=FG, fontsize=11)
    ax[1].legend(facecolor=PANEL, edgecolor="#333", labelcolor=FG, fontsize=8.5)

    ax[2].plot(O["otm"], O["sh"], "o-", color=GREEN, lw=2, ms=6, label="as tested (2024–26)")
    ax[2].plot(O["otm"], O["sh_adj"], "o-", color=RED, lw=2, ms=6,
               label="re-priced at full-history tail")
    ax[2].axhline(0.75, color=AMBER, ls="--", lw=1.2)
    ax[2].axhline(0, color=FG, lw=.8)
    ax[2].set_xlabel("short-strike distance (% OTM)", color=FG)
    ax[2].set_ylabel("annualized Sharpe", color=FG)
    ax[2].set_title("C. correct the tail frequency and the edge goes\n"
                    "bias #5 is the binding constraint, not significance", color=FG, fontsize=11)
    ax[2].legend(facecolor=PANEL, edgecolor="#333", labelcolor=FG, fontsize=8.5)

    fig.suptitle("7-DTE SPY put spread, REAL Alpaca prices — the result is real in-sample "
                 "and unfalsifiable out-of-sample: its risk lives in a tail 2024–2026 barely contains",
                 color=FG, fontsize=12.5)
    fig.tight_layout(rect=[0, 0, 1, .93])
    p = f"{OUT}/tail_reality_check.png"
    fig.savefig(p, dpi=115, facecolor=BG)
    print(f"\nsaved {p}")
    O.to_csv(f"{SCR}/_tailadj.csv", index=False)
