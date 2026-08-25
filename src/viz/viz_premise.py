"""VIZ — the premise test. Plot the seduction, then the two things that kill it."""
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

P = pd.read_csv(f"{SCR}/_premise.csv")
labs = ["3 months", "6 months", "12 months"]
x = np.arange(3); w = .36

fig, ax = plt.subplots(1, 3, figsize=(19.5, 6.4), facecolor=BG)
for a in ax:
    a.set_facecolor(PANEL); a.tick_params(colors=FG, labelsize=8.5)
    for s in a.spines.values():
        s.set_color("#333")
    a.grid(alpha=.13, color=FG, lw=.5)

# A. the seduction — gate predicts forward vol, hugely
ax[0].bar(x - w / 2, 100 * P["rv_on"], w, color=GREEN, label="gate ON", alpha=.9)
ax[0].bar(x + w / 2, 100 * P["rv_off"], w, color=RED, label="gate OFF", alpha=.9)
for i in range(3):
    ax[0].text(i - w / 2, 100 * P["rv_on"][i] + .3, f"{100*P['rv_on'][i]:.1f}%",
               ha="center", color=FG, fontsize=9)
    ax[0].text(i + w / 2, 100 * P["rv_off"][i] + .3, f"{100*P['rv_off'][i]:.1f}%",
               ha="center", color=FG, fontsize=9)
    ax[0].text(i, 2.0, f"z={P['rv_z'][i]:+.1f}", ha="center", color=CYAN,
               fontsize=10, fontweight="bold")
ax[0].set_xticks(x); ax[0].set_xticklabels(labs)
ax[0].set_ylabel("forward realized vol (%)", color=FG)
ax[0].set_title("A. THE SEDUCTION — the gate predicts forward vol beautifully\n"
                "13.8% vs 22.4% at 3m, z=−7.9. A genuinely good vol classifier.",
                color=FG, fontsize=11)
ax[0].legend(facecolor=PANEL, edgecolor="#333", labelcolor=FG, fontsize=8.5)

# B. but VIX already knows
ax[1].bar(x, P["t_pslow_rv"], .5, color=GREY, alpha=.9)
ax[1].axhline(2.0, color=AMBER, ls="--", lw=1.4)
ax[1].text(-.42, 2.08, "significance bar t=2.0", color=AMBER, fontsize=9)
ax[1].axhline(0, color=FG, lw=1)
for i in range(3):
    ax[1].text(i, P["t_pslow_rv"][i] + .07, f"t={P['t_pslow_rv'][i]:+.2f}\nΔR²={P['dR2'][i]:+.4f}",
               ha="center", color=FG, fontsize=9)
ax[1].set_ylim(-0.3, 2.6)
ax[1].set_xticks(x); ax[1].set_xticklabels(labs)
ax[1].set_ylabel("t-stat of p_slow on forward RV, AFTER controlling for VIX", color=FG)
ax[1].set_title("B. BUT VIX ALREADY KNOWS — control for VIX and p_slow adds nothing\n"
                "ΔR² ≈ 0.000–0.007. Fifth VIX-subsumption in this fund.",
                color=FG, fontsize=11)

# C. and the VRP points the WRONG WAY
ax[2].bar(x - w / 2, 100 * P["vrp_on"], w, color=GREEN, label="gate ON", alpha=.9)
ax[2].bar(x + w / 2, 100 * P["vrp_off"], w, color=RED, label="gate OFF", alpha=.9)
ax[2].axhline(0, color=FG, lw=1)
for i in range(3):
    ax[2].text(i - w / 2, 100 * P["vrp_on"][i] + .12, f"{100*P['vrp_on'][i]:+.2f}",
               ha="center", color=FG, fontsize=9)
    ax[2].text(i + w / 2, 100 * P["vrp_off"][i] + .12, f"{100*P['vrp_off'][i]:+.2f}",
               ha="center", color=FG, fontsize=9)
    ax[2].annotate("", xy=(i + w / 2, 100 * P["vrp_off"][i]),
                   xytext=(i - w / 2, 100 * P["vrp_on"][i]),
                   arrowprops=dict(arrowstyle="->", color=AMBER, lw=1.6))
ax[2].set_xticks(x); ax[2].set_xticklabels(labs)
ax[2].set_ylabel("VRP = VIX − forward realized vol (pp)", color=FG)
ax[2].set_title("C. AND IT POINTS THE WRONG WAY — premium is RICHER when gate is OFF\n"
                "the gate steers a vol seller INTO the low-premium regime",
                color=FG, fontsize=11)
ax[2].legend(facecolor=PANEL, edgecolor="#333", labelcolor=FG, fontsize=8.5)

fig.suptitle("PREMISE TEST — horizon matching does NOT rescue the thesis. "
             "36 years of SPX+VIX, causal, Newey-West + phase-averaged non-overlapping checks.",
             color=FG, fontsize=12.5)
fig.tight_layout(rect=[0, 0, 1, .92])
p = f"{OUT}/premise_test.png"
fig.savefig(p, dpi=115, facecolor=BG)
print("saved", p)
print(P.to_string(index=False))
