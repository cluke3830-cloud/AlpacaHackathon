"""CORRECTED bear-test viz.

First version's panel B said "the gate makes EVERY stress window WORSE". That is
true PER TRADE but false in TOTAL: the gate takes far fewer trades in stress
(COVID 1/10, 2022 7/45), so aggregate damage falls a lot. Both facts are needed;
showing only the per-trade one overstates the kill. Fixed here.

The real verdict is narrower and stands on its own: the gate IS a working risk
control (it converts a clearly-losing book into a flat one) but there is NO alpha
- 8.4 years of real SPX bid/ask gives Sharpe +0.04, t=+0.09.
"""
import math

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = "/Users/lukecha/Library/Mobile Documents/com~apple~CloudDocs/Trading Folder"
OUT = f"{ROOT}/AlpacaHackathon/research"
SCR = ("/private/tmp/claude-501/-Users-lukecha-Library-Mobile-Documents-"
       "com-apple-CloudDocs-Trading-Folder/116dc565-8b15-4c83-be8b-92c502d3d8c2/scratchpad")
BG, PANEL, FG = "#0a0a0f", "#10131a", "#e6e6ee"
CYAN, GREEN, AMBER, RED, GREY = "#00E7FD", "#00FF7F", "#FFBB00", "#FF6B6B", "#8a8a99"

R = pd.read_csv(f"{SCR}/_spxbear.csv", parse_dates=["date", "exp"])
S = R[R.otm == .025].sort_values("date")
STRESS = {"Fed-Pivot 2018": ("2018-10-01", "2018-12-31"),
          "COVID 2020": ("2020-02-15", "2020-04-30"),
          "Tech-Bear 2022": ("2022-01-01", "2022-12-31"),
          "SVB 2023": ("2023-03-01", "2023-03-31")}

fig, ax = plt.subplots(1, 3, figsize=(19.5, 6.4), facecolor=BG)
for a in ax:
    a.set_facecolor(PANEL); a.tick_params(colors=FG, labelsize=8.5)
    for s in a.spines.values():
        s.set_color("#333")
    a.grid(alpha=.13, color=FG, lw=.5)

# A. equity curve
eq_u = np.cumsum(S["pnl_pct"].to_numpy())
sg = S.copy(); sg.loc[~sg["gate"], "pnl_pct"] = 0.0
eq_g = np.cumsum(sg["pnl_pct"].to_numpy())
d = S["date"].to_numpy()
ax[0].plot(d, eq_u, lw=1.7, color=GREY, label=f"ungated  (ends {eq_u[-1]:+.1f})")
ax[0].plot(d, eq_g, lw=2.1, color=CYAN, label=f"gated    (ends {eq_g[-1]:+.1f})")
ax[0].axhline(0, color=FG, lw=.9)
for a_, b_ in STRESS.values():
    ax[0].axvspan(pd.Timestamp(a_), pd.Timestamp(b_), color=RED, alpha=.14)
ax[0].axvspan(pd.Timestamp("2024-01-18"), d[-1], color=GREEN, alpha=.10)
ax[0].text(pd.Timestamp("2024-02-05"), eq_u.min() * .9,
           "← ALL Alpaca history\n   lives in this green strip", color=GREEN, fontsize=9)
ax[0].set_ylabel("cumulative P&L (units of width)", color=FG)
ax[0].set_title("A. 8.4 YEARS, real SPX bid/ask\n"
                "gate turns a losing book FLAT — flat is not an edge", color=FG, fontsize=11)
ax[0].legend(facecolor=PANEL, edgecolor="#333", labelcolor=FG, fontsize=8.5, loc="upper left")

# B. per-trade vs total  (the correction)
names = list(STRESS)
xs = np.arange(len(names))
per_u, per_g, tot_u, tot_g, frac = [], [], [], [], []
for a_, b_ in STRESS.values():
    w = S[(S.date >= a_) & (S.date <= b_)]
    wg = w[w.gate]
    per_u.append(w["pnl_pct"].mean()); per_g.append(wg["pnl_pct"].mean() if len(wg) else 0)
    tot_u.append(w["pnl_pct"].sum()); tot_g.append(wg["pnl_pct"].sum() if len(wg) else 0)
    frac.append(len(wg) / max(len(w), 1))
wd = .36
ax[1].bar(xs - wd / 2, tot_u, wd, color=GREY, label="ungated TOTAL", alpha=.9)
ax[1].bar(xs + wd / 2, tot_g, wd, color=CYAN, label="gated TOTAL", alpha=.92)
ax[1].axhline(0, color=FG, lw=1)
for i in range(len(names)):
    ax[1].text(i - wd / 2, tot_u[i] - .25, f"{tot_u[i]:+.1f}", ha="center", color=FG, fontsize=8.5)
    ax[1].text(i + wd / 2, tot_g[i] - .25, f"{tot_g[i]:+.1f}", ha="center", color=CYAN, fontsize=8.5)
    ax[1].text(i, .35, f"took {100*frac[i]:.0f}%\nper-trade {per_g[i]:+.2f}",
               ha="center", color=AMBER, fontsize=8)
ax[1].set_xticks(xs); ax[1].set_xticklabels(names, fontsize=9)
ax[1].set_ylabel("TOTAL P&L in window (units of width)", color=FG)
ax[1].set_title("B. CORRECTED — gate cuts TOTAL stress damage by standing down\n"
                "but the few trades it takes are near-max losses (it is late, not early)",
                color=FG, fontsize=11)
ax[1].legend(facecolor=PANEL, edgecolor="#333", labelcolor=FG, fontsize=8.5, loc="lower left")

# C. the verdict — Sharpe by era
eras = [("2018-2026\nFULL (8.4y)", S),
        ("2024-2026\n(Alpaca's view)", S[S.date >= "2024-01-18"]),
        ("bear windows\nonly", S[np.logical_or.reduce(
            [((S.date >= a_) & (S.date <= b_)).to_numpy() for a_, b_ in STRESS.values()])])]
lab, sh_u, sh_g = [], [], []
for nm, sub in eras:
    lab.append(nm)
    p = sub["pnl_pct"].to_numpy()
    q = sub[sub.gate]["pnl_pct"].to_numpy()
    sh_u.append(p.mean() / p.std() * math.sqrt(52) if len(p) > 3 and p.std() else 0)
    sh_g.append(q.mean() / q.std() * math.sqrt(52) if len(q) > 3 and q.std() else 0)
xs = np.arange(len(lab))
ax[2].bar(xs - wd / 2, sh_u, wd, color=GREY, label="ungated", alpha=.9)
ax[2].bar(xs + wd / 2, sh_g, wd, color=CYAN, label="gated", alpha=.92)
ax[2].axhline(0, color=FG, lw=1)
ax[2].axhline(0.75, color=AMBER, ls="--", lw=1.3)
ax[2].text(-.45, .82, "pre-registered bar 0.75", color=AMBER, fontsize=8.5)
for i in range(len(lab)):
    ax[2].text(i - wd / 2, sh_u[i] + (.06 if sh_u[i] >= 0 else -.2), f"{sh_u[i]:+.2f}",
               ha="center", color=FG, fontsize=9)
    ax[2].text(i + wd / 2, sh_g[i] + (.06 if sh_g[i] >= 0 else -.2), f"{sh_g[i]:+.2f}",
               ha="center", color=CYAN, fontsize=9)
ax[2].set_xticks(xs); ax[2].set_xticklabels(lab, fontsize=9)
ax[2].set_ylabel("annualized Sharpe", color=FG)
ax[2].set_title("C. THE VERDICT — Alpaca's 2.6y showed +2.4;\n"
                "the full 8.4y shows +0.04. Same strategy, same code.",
                color=FG, fontsize=11)
ax[2].legend(facecolor=PANEL, edgecolor="#333", labelcolor=FG, fontsize=8.5)

fig.suptitle("BEAR TEST (decisive) — 7-DTE SPX put spreads, our own 2018–2026 chains, REAL bid/ask: "
             "the gate is a working RISK CONTROL, but there is no alpha",
             color=FG, fontsize=12.5)
fig.tight_layout(rect=[0, 0, 1, .92])
p = f"{OUT}/bear_test_kill.png"
fig.savefig(p, dpi=115, facecolor=BG)
print("saved", p)
for nm, u_, g_ in zip(lab, sh_u, sh_g):
    print(f"  {nm.replace(chr(10),' '):<26} ungated {u_:+.2f}   gated {g_:+.2f}")
print()
for n, tu, tg, f_, pg in zip(names, tot_u, tot_g, frac, per_g):
    print(f"  {n:<16} total {tu:+6.2f} -> {tg:+6.2f}   "
          f"(gate took {100*f_:>3.0f}% of trades, per-trade {pg:+.2f})")
