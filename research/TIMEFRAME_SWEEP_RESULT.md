# Timeframe sweep — RESULT

Pre-registration: `PREREGISTRATION_timeframe_sweep.md`. Run 2026-08-25.

## Verdict in one line

**The thesis PASSES the pre-registered statistical bar on real Alpaca prices, and
FAILS the Constitution's bias #5 (regime/sample-window).** The edge is real in the
2024–2026 sample and goes negative in a 2022-like regime. That makes the regime
gate the load-bearing component, not a nice-to-have — and the gate's bear behaviour
is exactly what Alpaca's 2.6-year history cannot test.

## Hypotheses vs outcome

| | stated before running | outcome |
|---|---|---|
| **H1** shorter DTE is WORSE (cost/premium) | | **WRONG.** Monotonic the other way: 7 DTE dominates, 30/45 DTE are negative. |
| **H2** 50%-profit-take improves risk-adjusted return | | **UNTESTABLE — data too noisy.** See "invalidated cells". |
| **H3** nothing clears the bar | | **WRONG** on the statistical bar; right on the regime bar. |

Getting H1 and H3 backwards is the point of pre-registering. Both are recorded as
stated.

## Invalidated cells — 50% profit-take (all of them)

Path-dependent exits were driven by `close(short leg) − close(long leg)` from daily
bars. Those are **last-trade prints from different moments** for two separately-traded
contracts. Diagnostic on 557 path-days:

- **2.3% of days give an impossible spread value** (long leg worth more than short)
- day-over-day |change| p90 = **$0.58** on a $5-wide spread — **more than 2x the
  ~$0.27 profit target** on a typical $0.55 credit

So the rule was scanning for whichever day the noise looked best. That is selection,
not profit-taking, and it produced the tell-tale 100% win rates, positive "worst"
trades, and Sharpe +9.9 / +14.3. **All 50%TP cells discarded.** Testing TC's chosen
exit rule properly needs intraday or quote data Alpaca does not serve historically.

## Trustworthy cells — hold-to-expiry, real prices, non-overlapping entries

| DTE | gate | n | E/share | win | Sharpe | t |
|---|---|---|---|---|---|---|
| 7 | ungated | 128 | +0.190 | 91.4% | **+1.34** | +2.09 |
| 7 | gated | 85 | +0.221 | 90.6% | **+1.80** | +2.30 |
| 14 | ungated | 61 | +0.187 | 93.4% | +0.82 | +1.25 |
| 14 | gated | 41 | +0.391 | 97.6% | +3.37 | +4.23 |
| 21 | ungated | 37 | +0.415 | 97.3% | +2.22 | +3.24 |
| 30 | ungated | 23 | +0.198 | 87.0% | +0.63 | +0.87 |
| 45 | ungated | 9 | — | — | — | n too small |

The 7-DTE row is the only one with a large, genuinely independent sample. 14/21/30
disagree with each other in no coherent pattern — small-sample noise.

## Strike-distance sweep — I was wrong once and corrected it

First read: "t swings 0.01→3.73, fragile." **That was wrong.** The sweep is smooth
and monotonic, plateauing at 2.4–2.8% OTM — the signature of a real effect, not noise.
Recording the error because labelling evidence to fit a prior conclusion is the
failure mode this whole exercise exists to prevent.

| OTM | E | win | Sharpe | t |
|---|---|---|---|---|
| 1.9% | +0.136 | 87.5% | +0.86 | +1.36 |
| 2.2% | +0.222 | 92.9% | +1.73 | +2.71 |
| 2.5% | +0.242 | 96.1% | **+2.39** | **+3.73** |
| 2.8% | +0.207 | 96.9% | +2.17 | +3.39 |

Clears the 58-cell multiple-testing threshold (E[max\|t\|] ≈ 2.85) at ≥2.4% OTM.

## Why it still cannot be certified — the tail

The improvement is driven by the **win rate climbing to 96.9%**, which concentrates
all risk into ~4 loss events inside a bull sample. Breach frequency, SPY falling >X%
over 5 trading days:

| era | −1.9% | −2.2% | −2.5% | −2.8% |
|---|---|---|---|---|
| **2024–2026 (test window)** | 12.48% | 9.98% | **7.18%** | 5.30% |
| 2016–2026 (full) | 13.00% | 10.97% | 8.76% | 7.38% |
| 2018 Fed pivot | 17.93% | 15.54% | 13.55% | 12.35% |
| 2020 COVID | 19.37% | 17.79% | 16.21% | 14.62% |
| **2022 tech bear** | 33.47% | 31.08% | **26.69%** | 23.11% |

**2022's breach rate is 3.7x the test window's.**

Re-priced at the full-history rate, Sharpe falls from +2.39 → **+1.54** at 2.5% OTM
(still above the 0.75 bar). But re-priced at a **2022-like** rate (loss frequency
3.9% → ~14.5%), expected P&L goes **negative, ≈ −0.23/share**.

So: **+0.24/trade in calm regimes, −0.23/trade in a 2022-type bear.** Full-cycle
expectancy is entirely a function of regime mix.

## What this means for the build

The gate stops being an optional overlay and becomes the load-bearing component —
its only job is standing down in exactly the regimes that make this negative. That
converges with the risk-control framing TC pre-authorised as the fallback: **the
edge claim is regime-conditional premium capture, and the gate is what makes it
survivable.**

Honest limits to state in the submission, unprompted:
- 2.6 years, zero bear markets, none of the Constitution's 4 named stress windows
- the gate's bear-regime behaviour is **untested on real option prices** — it cannot
  be tested on data Alpaca has
- the profit-take rule TC chose is untestable on this data (noise, above)
- ~73 cells examined tonight across model and real grids

## Artifacts
`strike_fragility.png` (superseded by the corrected read), `tail_reality_check.png`,
`_realgrid.csv`, `_strikesweep.csv`, `_tailadj.csv`, `_real7dte.csv`.
