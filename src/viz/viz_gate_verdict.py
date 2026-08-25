"""VIZ — the integrity gate's verdict on our own sleeve, plus the two numbers
that decided it. This is the deliverable chart: a mechanical gate refusing a
strategy its own authors built.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "AlpacaHackathon" / "research"
sys.path.insert(0, str(ROOT / "mandatory_tests_for_deployment"))
sys.path.insert(0, str(ROOT / "AlpacaHackathon" / "src"))

BG, PANEL, FG = "#0a0a0f", "#10131a", "#e6e6ee"
CYAN, GREEN, AMBER, RED, GREY = "#00E7FD", "#00FF7F", "#FFBB00", "#FF6B6B", "#8a8a99"


def main():
    from integrity_gate.gate import run_gate
    from strategies.alpaca_option.strategy_integrity import build
    import spx_backtest as bt

    m = build()
    rep = run_gate(m, m.source_files, gate_dir=str(Path("/tmp/_viz_gate")))
    df = bt.run()
    g = df[df.gate > 0]

    fig = plt.figure(figsize=(19.5, 9.2), facecolor=BG)
    gs = fig.add_gridspec(2, 3, height_ratios=[1.15, 1.0], hspace=.42, wspace=.24)

    # ---- top: the 9-checker ledger ----
    axl = fig.add_subplot(gs[0, :])
    axl.set_facecolor(PANEL)
    axl.set_xlim(0, 1); axl.set_ylim(0, 1); axl.axis("off")
    axl.set_title("INTEGRITY GATE VERDICT — alpaca_option  →  FAIL, DEPLOY BLOCKED\n"
                  "the same mechanical gate that guards this fund's live capital, "
                  "run against a strategy we built ourselves",
                  color=FG, fontsize=13, pad=14)
    y = .90
    for v in rep["verdicts"]:
        ok = v["status"] == "PASS"
        col = GREEN if ok else RED
        axl.text(.012, y, "PASS" if ok else "FAIL", color=col, fontsize=11,
                 fontweight="bold", family="monospace")
        axl.text(.062, y, v["checker"], color=FG, fontsize=11, family="monospace")
        # escape $ — matplotlib parses it as mathtext and mangles the dollar figures
        ev = v["evidence"].replace("$", r"\$")
        axl.text(.185, y, ev[:118] + ("…" if len(ev) > 118 else ""),
                 color=FG if ok else col, fontsize=9.2, family="monospace",
                 alpha=1.0 if not ok else .72)
        y -= .098
    axl.add_patch(plt.Rectangle((.005, .02), .99, .97, fill=False, ec="#333", lw=1))

    # ---- bottom-left: equity, gated vs ungated ----
    ax0 = fig.add_subplot(gs[1, 0]); ax0.set_facecolor(PANEL)
    d = df["entry"].to_numpy()
    ax0.plot(d, np.cumsum(df["pnl_natural"]), lw=1.6, color=GREY, label="ungated")
    sg = df["pnl_natural"].where(df["gate"] > 0, 0.0)
    ax0.plot(d, np.cumsum(sg), lw=2.0, color=CYAN, label="gated")
    ax0.axhline(0, color=FG, lw=.9)
    for a_, b_ in [("2018-10-01", "2018-12-31"), ("2020-02-15", "2020-04-30"),
                   ("2022-01-01", "2022-12-31"), ("2023-03-01", "2023-03-31")]:
        ax0.axvspan(pd.Timestamp(a_), pd.Timestamp(b_), color=RED, alpha=.13)
    ax0.axvspan(pd.Timestamp("2024-01-18"), d[-1], color=GREEN, alpha=.09)
    ax0.set_title("8.4 years, REAL SPX bid/ask\n(red = stress windows, green = all Alpaca history)",
                  color=FG, fontsize=10)
    ax0.set_ylabel("cum P&L (units of width)", color=FG)
    ax0.legend(facecolor=PANEL, edgecolor="#333", labelcolor=FG, fontsize=8)

    # ---- bottom-middle: the regime FAIL ----
    ax1 = fig.add_subplot(gs[1, 1]); ax1.set_facecolor(PANEL)
    rs = {k: v for k, v in m.regime_sharpes.items() if not np.isnan(v)}
    ks, vs = list(rs), list(rs.values())
    ax1.barh(ks, vs, color=[RED if v <= 0 else GREEN for v in vs], alpha=.9, height=.55)
    ax1.axvline(0, color=FG, lw=1)
    # headroom so the leftmost label can't collide with the y-axis tick text
    ax1.set_xlim(min(vs) * 1.28, max(0.0, max(vs)) + .25)
    for i, v in enumerate(vs):
        ax1.text(v - .06 if v < 0 else v + .05, i, f"{v:+.2f}", va="center",
                 color=FG, fontsize=10, ha="right" if v < 0 else "left")
    ax1.set_title("WHY IT FAILED (1/2) — regime\nnegative in every real stress window",
                  color=FG, fontsize=10)
    ax1.set_xlabel("Sharpe in window", color=FG)

    # ---- bottom-right: the overfitting FAIL ----
    ax2 = fig.add_subplot(gs[1, 2]); ax2.set_facecolor(PANEL)
    dsr = float(next(v["evidence"].split("DSR=")[1].split(" ")[0]
                     for v in rep["verdicts"] if v["checker"] == "overfitting"))
    ax2.bar(["DSR achieved", "DSR required"], [dsr, 0.95],
            color=[RED, AMBER], alpha=.9, width=.5)
    ax2.text(0, dsr + .03, f"{dsr:.3f}", ha="center", color=RED, fontsize=13, fontweight="bold")
    ax2.text(1, .98, "0.95", ha="center", color=AMBER, fontsize=13, fontweight="bold")
    ax2.set_ylim(0, 1.12)
    ax2.set_title(f"WHY IT FAILED (2/2) — overfitting\nDeflated Sharpe at the honest "
                  f"n_configs={m.n_configs_tried} ledger", color=FG, fontsize=10)

    for a in (ax0, ax1, ax2):
        a.tick_params(colors=FG, labelsize=8.5)
        for s in a.spines.values():
            s.set_color("#333")
        a.grid(alpha=.13, color=FG, lw=.5)

    gated_sh = bt.sharpe_weekly(g["pnl_natural"])
    fig.suptitle(
        f"Alpaca Hackathon — option sleeve run through the fund's own deploy gate.  "
        f"gated Sharpe {gated_sh:+.2f} over 8.4y (vs +1.54 on Alpaca's 2.6y window)  ·  "
        f"OOS {m.oos_sharpe:+.2f}  ·  mid-fill flatters by ~0.8 Sharpe",
        color=FG, fontsize=12.5, y=.985)
    p = OUT / "gate_verdict.png"
    fig.savefig(p, dpi=112, facecolor=BG, bbox_inches="tight")
    print("saved", p)
    print(f"  gated Sharpe {gated_sh:+.2f}  |  DSR {dsr:.3f}  |  "
          f"regimes {m.regime_sharpes}")


if __name__ == "__main__":
    main()
