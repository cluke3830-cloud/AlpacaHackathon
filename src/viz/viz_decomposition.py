"""VIZ — plot the thing that could KILL the put-spread thesis.

Not the happy path. Three kill-angles:
  A. the payoff distribution's NEGATIVE SKEW (high win rate hiding fat left tail)
  B. E[pnl] vs realized window move - where exactly each side earns and dies
  C. the tail through TIME - when the put side got hurt, on the SPY path
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SCRATCH = ("/private/tmp/claude-501/-Users-lukecha-Library-Mobile-Documents-"
           "com-apple-CloudDocs-Trading-Folder/116dc565-8b15-4c83-be8b-92c502d3d8c2/scratchpad")

d = np.load(f"{SCRATCH}/_decomp.npz", allow_pickle=True)
call_pnl, put_pnl, both = d["call_pnl"], d["put_pnl"], d["both"]
lr, spot = d["lr"], float(d["spot"])
lp_k, sp_k, sc_k, lc_k = d["strikes"]
dates = [str(x) for x in d["dates"]]
mv = 100 * (np.exp(lr) - 1)

BG, FG = "#0a0a0f", "#e6e6ee"
CYAN, GREEN, MAG, AMBER, RED = "#00E7FD", "#00FF7F", "#FF00FF", "#FFBB00", "#FF6B6B"
fig, ax = plt.subplots(1, 3, figsize=(19, 6), facecolor=BG)
for a in ax:
    a.set_facecolor("#10131a")
    a.tick_params(colors=FG, labelsize=8)
    for s in a.spines.values():
        s.set_color("#333")
    a.grid(alpha=.13, color=FG, lw=.5)

# ---- A. distribution: the negative skew ----
bins = np.linspace(min(both.min(), put_pnl.min()), max(both.max(), put_pnl.max()), 70)
ax[0].hist(call_pnl, bins=bins, color=RED, alpha=.55, label=f"short CALL spr  E={call_pnl.mean():+.2f}")
ax[0].hist(put_pnl, bins=bins, color=GREEN, alpha=.55, label=f"short PUT spr   E={put_pnl.mean():+.2f}")
ax[0].axvline(0, color=FG, lw=.8, ls="--")
ax[0].axvline(call_pnl.mean(), color=RED, lw=2)
ax[0].axvline(put_pnl.mean(), color=GREEN, lw=2)
ax[0].set_title("A. payoff distribution — high win rate, fat left tail\n"
                "(both sides are negatively skewed; that is the risk Sharpe hides)",
                color=FG, fontsize=10)
ax[0].set_xlabel("P&L per share ($)", color=FG)
ax[0].set_ylabel("count of 17-trading-day windows", color=FG)
ax[0].legend(facecolor="#10131a", edgecolor="#333", labelcolor=FG, fontsize=8)

# ---- B. E[pnl] vs realized move — the mechanism ----
edges = np.percentile(mv, np.linspace(0, 100, 13))
edges = np.unique(edges)
cent, ec, ep = [], [], []
for i in range(len(edges) - 1):
    m = (mv >= edges[i]) & (mv < edges[i + 1])
    if m.sum() < 5:
        continue
    cent.append(mv[m].mean()); ec.append(call_pnl[m].mean()); ep.append(put_pnl[m].mean())
ax[1].axhline(0, color=FG, lw=.8, ls="--")
ax[1].axvline(0, color=FG, lw=.6, ls=":")
ax[1].plot(cent, ec, "o-", color=RED, lw=2, ms=5, label="short CALL spread")
ax[1].plot(cent, ep, "o-", color=GREEN, lw=2, ms=5, label="short PUT spread")
lo_k, hi_k = 100 * (sp_k / spot - 1), 100 * (sc_k / spot - 1)
ax[1].axvspan(lo_k, hi_k, color=CYAN, alpha=.08)
ax[1].text((lo_k + hi_k) / 2, ax[1].get_ylim()[1] * .82, "both shorts safe",
           ha="center", color=CYAN, fontsize=8)
ax[1].set_title("B. where each side earns and dies\n"
                "call side is run over by the SAME bull drift the put side is paid for",
                color=FG, fontsize=10)
ax[1].set_xlabel("SPY move over the 17-day window (%)", color=FG)
ax[1].set_ylabel("mean P&L per share ($)", color=FG)
ax[1].legend(facecolor="#10131a", edgecolor="#333", labelcolor=FG, fontsize=8)

# ---- C. the tail through time ----
yrs = np.array([int(s[:4]) for s in dates])
ax[2].axhline(0, color=FG, lw=.8, ls="--")
ax[2].plot(yrs + np.linspace(0, .99, len(yrs)) % 1, put_pnl, lw=.7, color=GREEN, alpha=.75)
hurt = put_pnl < -1.0
ax[2].scatter((yrs + np.linspace(0, .99, len(yrs)) % 1)[hurt], put_pnl[hurt],
              s=14, color=RED, zorder=5, label=f"put-side loss > $1  (n={hurt.sum()}, "
                                               f"{100*hurt.mean():.1f}% of windows)")
ax[2].set_title("C. WHEN the put side gets hurt\n"
                "losses cluster in known stress episodes — that is what the gate must dodge",
                color=FG, fontsize=10)
ax[2].set_xlabel("year", color=FG)
ax[2].set_ylabel("put-spread P&L per share ($)", color=FG)
ax[2].legend(facecolor="#10131a", edgecolor="#333", labelcolor=FG, fontsize=8, loc="lower left")

fig.suptitle(
    f"SPY iron condor decomposed — live Alpaca quotes {spot:.0f} spot, "
    f"strikes {lp_k:.0f}/{sp_k:.0f}/{sc_k:.0f}/{lc_k:.0f}, "
    f"today's credit vs 2,658 historical 17-day windows (2016-2026, +12.6%/yr drift)",
    color=FG, fontsize=11.5)
fig.tight_layout(rect=[0, 0, 1, .93])
out = f"{SCRATCH}/condor_decomposition.png"
fig.savefig(out, dpi=115, facecolor=BG)
print("saved", out)
print(f"put-side losses >$1: {hurt.sum()} of {len(put_pnl)} ({100*hurt.mean():.1f}%)")
yr_hurt = {}
for y, h in zip(yrs, hurt):
    yr_hurt.setdefault(y, [0, 0])
    yr_hurt[y][1] += 1
    yr_hurt[y][0] += int(h)
print("put-side hurt rate by year:")
for y in sorted(yr_hurt):
    n, tot = yr_hurt[y]
    print(f"  {y}: {n:3d}/{tot:3d}  {100*n/tot:5.1f}%")
