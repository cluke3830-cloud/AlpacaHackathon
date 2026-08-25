"""FINAL VERDICT VIZ — the complete, honest scorecard of tonight's probe."""
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

ROOT = "/Users/lukecha/Library/Mobile Documents/com~apple~CloudDocs/Trading Folder"
OUT = f"{ROOT}/AlpacaHackathon/research"
SCR = ("/private/tmp/claude-501/-Users-lukecha-Library-Mobile-Documents-"
       "com-apple-CloudDocs-Trading-Folder/116dc565-8b15-4c83-be8b-92c502d3d8c2/scratchpad")
sys.path.insert(0, f"{ROOT}/mandatory_tests_for_deployment_2")

BG, PANEL, FG = "#0a0a0f", "#10131a", "#e6e6ee"
CYAN, GREEN, MAG, AMBER, RED, GREY = "#00E7FD", "#00FF7F", "#FF00FF", "#FFBB00", "#FF6B6B", "#8a8a99"

sc = np.load(f"{SCR}/_scaled.npz", allow_pickle=True)
lg = np.load(f"{SCR}/_long.npz", allow_pickle=True)
ok, gate = sc["ok"], sc["gate"]
dates = pd.DatetimeIndex([str(x) for x in sc["dates"]])
put_s, cond_s = sc["put_scaled"], sc["both_scaled"]
call_d = lg["call_dbt"]

HOLD = 17
N_EFF = int(ok.sum() / HOLD)          # overlapping windows -> effective independent n


def sh(p):
    return p.mean() / p.std() if len(p) and p.std() else float("nan")


def ann(p):
    return sh(p) * np.sqrt(252 / HOLD)


def tstat(p):
    """t on the mean, using EFFECTIVE (non-overlapping) sample size."""
    if len(p) < 2 or p.std() == 0:
        return float("nan")
    n_eff = max(2, int(len(p) / HOLD))
    return p.mean() / (p.std() / np.sqrt(n_eff))


rows = [
    ("short put spread", put_s, GREEN),
    ("iron condor", cond_s, CYAN),
    ("long call spread", call_d, MAG),
]

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig, ax = plt.subplots(1, 3, figsize=(19.5, 6.6), facecolor=BG)
for a in ax:
    a.set_facecolor(PANEL); a.tick_params(colors=FG, labelsize=8.5)
    for s_ in a.spines.values():
        s_.set_color("#333")
    a.grid(alpha=.13, color=FG, lw=.5)

# --- A. annualized Sharpe, ungated vs gated, every structure ---
labs = [r[0] for r in rows]
ung = [ann(r[1][ok]) for r in rows]
gat = [ann(r[1][gate]) for r in rows]
x = np.arange(len(rows)); w = .36
ax[0].bar(x - w / 2, ung, w, color=GREY, label="ungated", alpha=.9)
ax[0].bar(x + w / 2, gat, w, color=CYAN, label="MSAR+trend gated (causal)", alpha=.92)
ax[0].axhline(0, color=FG, lw=.9)
ax[0].axhspan(-0.25, 0.25, color=AMBER, alpha=.10)
ax[0].text(len(rows) - .5, .27, "indistinguishable from zero", color=AMBER,
           fontsize=8.5, ha="right")
for i, (u, g) in enumerate(zip(ung, gat)):
    ax[0].text(i - w / 2, u + .02, f"{u:+.2f}", ha="center", color=FG, fontsize=9)
    ax[0].text(i + w / 2, g + .02, f"{g:+.2f}", ha="center", color=FG, fontsize=9)
ax[0].set_xticks(x); ax[0].set_xticklabels(labs, fontsize=9)
ax[0].set_ylabel("annualized Sharpe", color=FG)
ax[0].set_title("A. EVERY structure lands near zero\n"
                "vol-scaled credit, causal gate, real Alpaca quotes",
                color=FG, fontsize=11)
ax[0].legend(facecolor=PANEL, edgecolor="#333", labelcolor=FG, fontsize=8.5)

# --- B. half-split robustness ---
mid = dates[ok][int(ok.sum()) // 2]
h1 = dates <= mid
ax[1].axhline(0, color=FG, lw=.9)
for i, (lab, p, col) in enumerate(rows):
    a_, b_ = ann(p[gate & h1]), ann(p[gate & ~h1])
    ax[1].plot([0, 1], [a_, b_], "o-", color=col, lw=2, ms=8, label=lab)
    ax[1].text(1.03, b_, f"{b_:+.2f}", color=col, fontsize=9, va="center")
    ax[1].text(-0.03, a_, f"{a_:+.2f}", color=col, fontsize=9, va="center", ha="right")
ax[1].set_xticks([0, 1])
ax[1].set_xticklabels([f"H1\n(→{mid:%Y-%m})", f"H2\n({mid:%Y-%m}→)"], fontsize=9)
ax[1].set_xlim(-.35, 1.35)
ax[1].set_ylabel("annualized Sharpe (gated)", color=FG)
ax[1].set_title("B. HALF-SPLIT — the fund's standing robustness bar\n"
                "put spread holds sign but at a trivial level; long call flips",
                color=FG, fontsize=11)
ax[1].legend(facecolor=PANEL, edgecolor="#333", labelcolor=FG, fontsize=8.5)

# --- C. significance with EFFECTIVE sample size ---
ts = [tstat(r[1][gate]) for r in rows]
cols = [GREEN, CYAN, MAG]
b = ax[2].barh(labs, ts, color=cols, alpha=.9, height=.5)
ax[2].axvline(0, color=FG, lw=.9)
for thr, c_, lab in [(2.0, AMBER, "|t|=2"), (2.5, RED, "pre-reg bar |t|=2.5")]:
    ax[2].axvline(thr, color=c_, ls="--", lw=1.3)
    ax[2].text(thr, 2.45, lab, color=c_, fontsize=8.5, rotation=90, va="top", ha="right")
for bb, t_ in zip(b, ts):
    ax[2].text(t_ + .03, bb.get_y() + bb.get_height() / 2, f"t={t_:+.2f}",
               color=FG, fontsize=10, va="center")
ax[2].set_xlim(-0.5, 3.0)
ax[2].set_xlabel(f"t-stat on mean P&L, EFFECTIVE n≈{N_EFF} "
                 f"(not the {int(ok.sum()):,} overlapping windows)", color=FG)
ax[2].set_title("C. NOTHING CLEARS THE BAR\n"
                "overlapping windows inflate n by ~17x; corrected, all are noise",
                color=FG, fontsize=11)

fig.suptitle("Alpaca hackathon probe — FINAL VERDICT: SPY defined-risk options are fairly priced, "
             "and the MSAR/trend gate does not change that\n"
             f"vol-scaled credits · causal (entry-dated) gate · {int(ok.sum()):,} windows 2016–2026 · "
             f"effective independent n≈{N_EFF}",
             color=FG, fontsize=12.5)
fig.tight_layout(rect=[0, 0, 1, .90])
png = f"{OUT}/final_verdict.png"
fig.savefig(png, dpi=115, facecolor=BG)
print("saved", png)

print(f"\nsplit date {mid:%Y-%m-%d}   effective n≈{N_EFF}")
hdr = f"{'structure':<22}{'ung ann':>9}{'gat ann':>9}{'H1':>8}{'H2':>8}{'t(gated)':>10}{'worst':>9}"
print(hdr); print("-" * len(hdr))
for lab, p, _ in rows:
    print(f"{lab:<22}{ann(p[ok]):>+9.2f}{ann(p[gate]):>+9.2f}"
          f"{ann(p[gate & h1]):>+8.2f}{ann(p[gate & ~h1]):>+8.2f}"
          f"{tstat(p[gate]):>+10.2f}{p[gate].min():>9.2f}")

# interactive
import plotly.graph_objects as go
from plotly.subplots import make_subplots
f = make_subplots(rows=1, cols=3, subplot_titles=(
    "A. every structure ≈ zero", "B. half-split robustness", "C. t-stat, effective n"))
f.add_trace(go.Bar(x=labs, y=ung, name="ungated", marker_color=GREY), 1, 1)
f.add_trace(go.Bar(x=labs, y=gat, name="gated", marker_color=CYAN), 1, 1)
for lab, p, col in rows:
    f.add_trace(go.Scatter(x=["H1", "H2"], y=[ann(p[gate & h1]), ann(p[gate & ~h1])],
                           mode="lines+markers", name=lab, line=dict(color=col, width=2)), 1, 2)
f.add_trace(go.Bar(y=labs, x=ts, orientation="h", marker_color=cols, name="t-stat"), 1, 3)
f.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=PANEL,
                font=dict(color=FG, family="JetBrains Mono, monospace", size=11), height=560,
                title=f"FINAL VERDICT — SPY options fairly priced; gate adds nothing significant "
                      f"(effective n≈{N_EFF}) · {datetime.now():%Y-%m-%d %H:%M}")
html = f"{OUT}/final_verdict.html"
f.write_html(html, include_plotlyjs="cdn")
print("saved", html)
