"""Export the audited backtest to web/public/backtest.json for the BACKTESTED tab.

WHY AN EXPORT AND NOT A TS REIMPLEMENTATION: the numbers on that tab are the
ones the whole submission rests on, and they have already been through the
audit stack (walk-forward OOS, permutation null, block-bootstrap Monte Carlo,
cost sweep, regime windows). Re-deriving them in TypeScript would create a
second, unvalidated source of truth that can silently disagree with the
research -- the exact failure the agent's own test_parity.py exists to prevent.
So Python computes, JSON carries, the browser only draws.

Output format mirrors Partner_Strategy_2_Backtesting.py: MC spaghetti + median,
historical equity, return distribution, a P5/P50/P95 percentile table, and
Risk-of-Ruin probabilities.

Run:  python3 AlpacaHackathon/scripts/export_backtest_json.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RESEARCH = ROOT / "Researched_Concepts" / "CrossSectionalArb" / "src"
sys.path.insert(0, str(RESEARCH))
sys.path.insert(0, str(ROOT / "mandatory_tests_for_deployment"))
sys.path.insert(0, str(ROOT / "AlpacaHackathon" / "agent"))

OUT = HERE.parent / "web" / "public" / "backtest.json"

N_PATHS, HORIZON, BLOCK = 2000, 252, 21
SPAGHETTI = 200          # how many curves to actually ship to the browser
RISK_LEVELS = [10, 20, 25, 50]
RNG = np.random.default_rng(20260831)


def main():
    import config as C                                     # the agent's own config
    from leverage_optimize import build                    # shipping-config builder
    from option_sleeves import stats as ostats

    lev = C.GROSS_LEVERAGE
    print(f"building shipping config (SPY, marketable-limit fill) at {lev:.2f}x ...")
    bl = build("SPY", 0.5, 1)                              # realistic fill, gex_lag=1
    r = bl.dropna() * lev
    eq = (1 + r).cumprod()

    st = ostats(r)
    print(f"  {len(r)}d  Sharpe {st['sharpe']:+.2f}  CAGR {100*st['cagr']:+.1f}%  "
          f"maxDD {100*st['maxdd']:.1f}%")

    # ---- Monte Carlo: same block bootstrap as option_monte_carlo.py ----------
    v = r.values
    N = len(v)
    nb = int(np.ceil(HORIZON / BLOCK))
    starts = RNG.integers(0, N - BLOCK, size=(N_PATHS, nb))
    idx = (starts[:, :, None] + np.arange(BLOCK)[None, None, :]).reshape(N_PATHS, -1)[:, :HORIZON]
    paths = v[idx]
    curves = np.cumprod(1 + paths, axis=1) * 100.0         # indexed to 100
    terminal_ret = (curves[:, -1] / 100.0 - 1.0) * 100.0   # percent
    dd = (curves / np.maximum.accumulate(curves, axis=1) - 1).min(axis=1) * -100.0  # positive %
    final_eq = curves[:, -1]
    median = np.median(curves, axis=0)

    pct = lambda a, q: float(np.percentile(a, q))
    percentiles = [
        dict(metric="Final Equity", p5=pct(final_eq, 5), p50=pct(final_eq, 50),
             p95=pct(final_eq, 95), fmt="usd"),
        dict(metric="Total Return", p5=pct(terminal_ret, 5), p50=pct(terminal_ret, 50),
             p95=pct(terminal_ret, 95), fmt="pct"),
        dict(metric="Max Drawdown", p5=pct(dd, 5), p50=pct(dd, 50), p95=pct(dd, 95), fmt="pct"),
    ]
    ruin = [dict(level=L, prob=float((dd >= L).mean() * 100)) for L in RISK_LEVELS]

    # ---- audit facts, carried verbatim from the research that produced them --
    audit = [
        dict(label="Sharpe (this fill)", value=f"{st['sharpe']:+.2f}", pass_=None),
        dict(label="Walk-forward OOS Sharpe", value="+0.93", pass_=True),
        dict(label="OOS DSR @1 trial", value="0.961", pass_=True),
        dict(label="Permutation null (400)", value="p<0.0025", pass_=True),
        dict(label="Stress windows positive", value="4 / 4", pass_=True),
        dict(label="Cost survives 2x spread", value="yes", pass_=True),
        dict(label="DSR @140 (full ledger)", value="0.580", pass_=False),
        dict(label="Sleeve-2 gain significance", value="p=0.06–0.14", pass_=False),
    ]

    doc = dict(
        meta=dict(
            strategy="TWO-SLEEVE OPTIONS BOOK",
            instrument="SPY options · Δ0.70 · 7DTE",
            fill="marketable-limit (half spread)",
            leverage=float(lev),
            start=str(r.index.min().date()),
            end=str(r.index.max().date()),
            n_paths=N_PATHS, horizon=HORIZON,
            generated=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        ),
        historical=dict(
            times=[d.strftime("%Y-%m-%d") for d in eq.index],
            equity=[round(float(x) * 100, 4) for x in eq],   # indexed to 100
        ),
        mc=dict(
            curves=[[round(float(x), 3) for x in c] for c in curves[:SPAGHETTI]],
            median=[round(float(x), 3) for x in median],
            returns=[round(float(x), 4) for x in terminal_ret],
        ),
        stats={k: (None if v is None or (isinstance(v, float) and not np.isfinite(v))
                   else round(float(v), 6)) for k, v in st.items()},
        percentiles=percentiles,
        risk_of_ruin=ruin,
        audit=[dict(label=a["label"], value=a["value"], **{"pass": a["pass_"]}) for a in audit],
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc))
    kb = OUT.stat().st_size / 1024
    print(f"\nwrote {OUT}  ({kb:.0f} KB)")
    print(f"  historical {len(eq)}d, {SPAGHETTI} spaghetti curves, {N_PATHS} MC paths")
    print(f"  terminal return P5/P50/P95 = {percentiles[1]['p5']:+.1f}% / "
          f"{percentiles[1]['p50']:+.1f}% / {percentiles[1]['p95']:+.1f}%")
    for r_ in ruin:
        print(f"  P(DD > {r_['level']}%) = {r_['prob']:.1f}%")


if __name__ == "__main__":
    main()
