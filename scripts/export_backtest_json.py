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
Risk-of-Ruin probabilities -- emitted PER LOOKBACK PERIOD (1Y default, plus
3Y / 5Y / 10Y).

The Monte Carlo is COUNTERFACTUAL, not a forward projection: each of the 10,000
paths is an alternative history of the SAME length as the selected period,
block-resampled from that period's own returns, with the actual realized curve
overlaid. The question it answers is "was the backtest a typical outcome of
this process, or a lucky draw?" -- which is what you want from a backtest, and
is answered by the percentile rank of the real path inside the simulated cloud.

INSTRUMENT: SPX, not the deployed SPY. Two reasons, and the tradeoff is stated
in the UI rather than hidden: (1) SPX chain history runs 2018-2026 (8.4y) vs
SPY's 2022-2026 (4.1y), and a 5Y lookback is simply not computable on SPY;
(2) SPX is the instrument the audit stack itself ran on. The two were verified
equivalent over their shared window (SPY blend +0.97 vs SPX +0.96), so this
buys history without changing what is being measured.

10Y is emitted as UNAVAILABLE rather than silently truncated to whatever exists
-- a "10Y" label over 8.4 years of data would be a quiet lie about the sample.

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

INSTRUMENT = "SPX"
N_PATHS, BLOCK = 10_000, 21
SPAGHETTI = 200          # sample paths shipped for spaghetti texture, per period
MAX_POINTS = 400         # x-resolution cap for shipped curves (file-size guard)
RISK_LEVELS = [10, 20, 25, 50]
PERIODS = {"1Y": 252, "3Y": 756, "5Y": 1260, "10Y": 2520}
DEFAULT_PERIOD = "1Y"
RNG = np.random.default_rng(20260831)


def mc_for(r: pd.Series) -> dict:
    """COUNTERFACTUAL Monte Carlo: what could this same period have looked like?

    This is NOT a forward projection. The horizon is the LENGTH OF THE PERIOD
    ITSELF, and every simulated path is an alternative history of exactly that
    span, block-resampled from the period's own realized returns. The actual
    realized equity curve is shipped alongside so the reader can see where
    reality landed among the alternatives -- which is the whole question: was
    the backtest's outcome typical of this process, or a lucky draw?

    Block (not iid) resampling because an option position is held across days.
    iid draws would destroy the autocorrelation and the skew and manufacture a
    tighter, friendlier distribution than the strategy actually has.

    Percentile bands are computed over ALL N_PATHS; only a sample of individual
    curves is shipped, purely for visual texture.
    """
    v = r.values
    N = len(v)
    horizon = N                      # an alternative history of the SAME length
    nb = int(np.ceil(horizon / BLOCK))
    starts = RNG.integers(0, max(N - BLOCK, 1), size=(N_PATHS, nb))
    idx = (starts[:, :, None] + np.arange(BLOCK)[None, None, :]).reshape(N_PATHS, -1)[:, :horizon]
    idx = np.clip(idx, 0, N - 1)
    paths = v[idx]

    curves = np.cumprod(1 + paths, axis=1) * 100.0
    actual = np.cumprod(1 + v) * 100.0

    terminal = (curves[:, -1] / 100.0 - 1.0) * 100.0
    actual_terminal = float((actual[-1] / 100.0 - 1.0) * 100.0)
    dd = (curves / np.maximum.accumulate(curves, axis=1) - 1).min(axis=1) * -100.0
    actual_dd = float(-(actual / np.maximum.accumulate(actual) - 1).min() * 100.0)
    final_eq = curves[:, -1]

    # Where did reality land? The percentile rank of the ACTUAL outcome inside
    # the simulated distribution -- the single most useful number on the panel.
    rank_ret = float((terminal < actual_terminal).mean() * 100)
    rank_dd = float((dd < actual_dd).mean() * 100)

    # Downsample the x-axis for shipped series only (stats above use full res).
    step = max(1, int(np.ceil(horizon / MAX_POINTS)))
    sl = slice(None, None, step)

    band = lambda q: [round(float(x), 2) for x in np.percentile(curves, q, axis=0)[sl]]

    pct = lambda a, q: float(np.percentile(a, q))
    return dict(
        horizon=horizon,
        step=step,
        curves=[[round(float(x), 2) for x in c[sl]] for c in curves[:SPAGHETTI]],
        bands=dict(p5=band(5), p25=band(25), p50=band(50), p75=band(75), p95=band(95)),
        actual=[round(float(x), 2) for x in actual[sl]],
        actual_terminal=round(actual_terminal, 3),
        actual_maxdd=round(actual_dd, 3),
        rank_return=round(rank_ret, 1),
        rank_maxdd=round(rank_dd, 1),
        returns=[round(float(x), 3) for x in terminal],
        percentiles=[
            dict(metric="Final Equity", p5=pct(final_eq, 5), p50=pct(final_eq, 50),
                 p95=pct(final_eq, 95), actual=round(float(actual[-1]), 2), fmt="usd"),
            dict(metric="Total Return", p5=pct(terminal, 5), p50=pct(terminal, 50),
                 p95=pct(terminal, 95), actual=round(actual_terminal, 2), fmt="pct"),
            dict(metric="Max Drawdown", p5=pct(dd, 5), p50=pct(dd, 50),
                 p95=pct(dd, 95), actual=round(actual_dd, 2), fmt="pct"),
        ],
        risk_of_ruin=[dict(level=L, prob=float((dd >= L).mean() * 100)) for L in RISK_LEVELS],
        p_loss=float((terminal < 0).mean() * 100),
    )


def main():
    import config as C
    from leverage_optimize import build
    from option_sleeves import stats as ostats

    lev = C.GROSS_LEVERAGE
    print(f"building {INSTRUMENT} shipping config (marketable-limit fill) at {lev:.2f}x ...")
    bl = build(INSTRUMENT, 0.5, 1)
    r_full = bl.dropna() * lev
    print(f"  {len(r_full)}d = {len(r_full)/252:.2f}y  "
          f"({r_full.index.min().date()} -> {r_full.index.max().date()})")

    periods = {}
    for label, n in PERIODS.items():
        if len(r_full) < n:
            periods[label] = dict(
                available=False,
                reason=(f"needs {n} sessions ({n//252}y), {len(r_full)} available "
                        f"({len(r_full)/252:.1f}y) — {INSTRUMENT} option chain history "
                        f"starts {r_full.index.min().date()}"),
            )
            print(f"  {label:>4}: UNAVAILABLE ({len(r_full)}d < {n}d)")
            continue

        r = r_full.iloc[-n:]
        eq = (1 + r).cumprod()
        st = ostats(r)
        m = mc_for(r)
        periods[label] = dict(
            available=True,
            n_days=len(r),
            start=str(r.index.min().date()),
            end=str(r.index.max().date()),
            historical=dict(
                times=[d.strftime("%Y-%m-%d") for d in eq.index],
                equity=[round(float(x) * 100, 4) for x in eq],
            ),
            mc=dict(curves=m["curves"], bands=m["bands"], actual=m["actual"],
                    returns=m["returns"], horizon=m["horizon"], step=m["step"],
                    actual_terminal=m["actual_terminal"], actual_maxdd=m["actual_maxdd"],
                    rank_return=m["rank_return"], rank_maxdd=m["rank_maxdd"]),
            percentiles=m["percentiles"],
            risk_of_ruin=m["risk_of_ruin"],
            p_loss=m["p_loss"],
            stats={k: (None if v is None or (isinstance(v, float) and not np.isfinite(v))
                       else round(float(v), 6)) for k, v in st.items()},
        )
        print(f"  {label:>4}: {len(r)}d  Sharpe {st['sharpe']:+.2f}  "
              f"CAGR {100*st['cagr']:+.1f}%  maxDD {100*st['maxdd']:.1f}%  "
              f"| MC P50 {m['percentiles'][1]['p50']:+.1f}% vs ACTUAL "
              f"{m['actual_terminal']:+.1f}% (rank {m['rank_return']:.0f}th pct)")

    audit = [
        dict(label="Walk-forward OOS Sharpe", value="+0.93", ok=True),
        dict(label="OOS DSR @1 trial", value="0.961", ok=True),
        dict(label="Permutation null (400)", value="p<0.0025", ok=True),
        dict(label="Stress windows positive", value="4 / 4", ok=True),
        dict(label="Cost survives 2x spread", value="yes", ok=True),
        dict(label="DSR @140 (full ledger)", value="0.580", ok=False),
        dict(label="Sleeve-2 gain significance", value="p=0.06–0.14", ok=False),
    ]

    doc = dict(
        meta=dict(
            strategy="TWO-SLEEVE OPTIONS BOOK",
            instrument=f"{INSTRUMENT} options · Δ0.70 · 7DTE",
            instrument_note=("SPX is the research instrument — 8.4y of chain history vs SPY's "
                             "4.1y, which is what makes a 5Y lookback computable at all. The "
                             "deployed book trades SPY; the two were verified equivalent over "
                             "their shared window (SPY +0.97 vs SPX +0.96)."),
            fill="marketable-limit (half spread)",
            leverage=float(lev),
            full_start=str(r_full.index.min().date()),
            full_end=str(r_full.index.max().date()),
            full_days=len(r_full),
            n_paths=N_PATHS, block=BLOCK,
            generated=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        ),
        default_period=DEFAULT_PERIOD,
        period_order=list(PERIODS.keys()),
        periods=periods,
        audit=audit,
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc))
    print(f"\nwrote {OUT}  ({OUT.stat().st_size/1024:.0f} KB)  default={DEFAULT_PERIOD}")


if __name__ == "__main__":
    main()
