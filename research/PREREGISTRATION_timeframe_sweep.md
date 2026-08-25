# PRE-REGISTRATION — timeframe / holding-period sweep

Written BEFORE running the sweep, 2026-08-25. TC's call after the first probe
returned "fairly priced, no edge" at a single DTE: test the same thesis across
timeframes before falling back to the risk-control framing.

## Why this is a legitimate re-test, not goalpost-moving

The first probe tested exactly ONE cell on this axis: 24 DTE, held to expiry.
`FINDINGS_2026-08-25.md` §5 listed that as a known, deliberate limitation
("one delta / one DTE / one underlying, deliberately unswept to avoid p-hacking").
So this is testing a pre-identified gap, not re-slicing a dead result.

There is also a real mechanism, not just hope: a short put spread's tail risk is
concentrated in the final days before expiry, when gamma is largest. Closing at
50% of max profit removes that window entirely. That is a structural reason the
holding rule could matter independent of any alpha claim.

## Hypotheses (stated before seeing results)

- **H1** Shorter DTE is WORSE. Cost/premium ratio degrades at short tenor — this is
  the regime where the 0DTE VRP test found the spread ate the whole premium.
- **H2** 50%-profit-take IMPROVES risk-adjusted return vs hold-to-expiry, by cutting
  end-of-life gamma exposure — even if it lowers gross E[pnl] per trade.
- **H3** Nothing clears the significance bar. Prior is unchanged: SPY options are
  fairly priced (5 independent confirmations in this fund).

## The grid (locked — no additions after seeing results)

| axis | values | n |
|---|---|---|
| DTE at entry | 7, 14, 21, 30, 45 | 5 |
| exit rule | hold-to-expiry, 50%-profit-take | 2 |
| gate | ungated, MSAR+trend gated | 2 |

= **20 cells.** Structure fixed at the already-chosen short put spread, 0.15-delta
short, $10-equivalent width (vol-scaled). No delta sweep, no underlying sweep, no
width sweep. Adding axes later = a new pre-registration.

## Pass bar (locked)

A cell counts as a survivor ONLY if ALL hold:
1. annualized Sharpe ≥ **0.75** on the full sample (a real "steady Sharpe" claim),
2. **positive in BOTH halves** (the fund's standing both-halves protocol),
3. t-stat ≥ **2.0** on the mean, computed at EFFECTIVE (non-overlapping) sample size,
4. survives the **multiple-testing correction** across all 20 cells (deflated for
   n_configs — the same discipline `effective_trials.py` applies).

Failing any one ⇒ the thesis is dead and we move to the risk-control framing.
No renegotiation of these numbers after results are in.

## Method

- Path-dependent, causal. Entry at close t; walk the SPY path daily to expiry.
- Spread priced by Black-Scholes at each step. Vol model: an IV/VIX ratio curve
  fitted to TODAY's live Alpaca chain as a function of (moneyness, DTE), then applied
  historically as `IV(m, dte, t) = ratio(m, dte) x VIX_t`. Declared as a model —
  Alpaca has no historical bid/ask, so some model is unavoidable (bias #3: declare it).
- American-exercise effects ignored (OTM put verticals; early exercise immaterial).
- Costs: slippage charged BOTH on entry and exit, calibrated to the live measurement
  (4.3% of credit at $10 wing). Swept at 4% / 8% for sensitivity — 8% is deliberately
  pessimistic.
- Portfolio: laddered daily entries, equal size, daily mark-to-market equity curve →
  Sharpe and max drawdown computed from the DAILY series, not annualized per-trade.

## Result

Filled in after the run — see `TIMEFRAME_SWEEP_RESULT.md`.
