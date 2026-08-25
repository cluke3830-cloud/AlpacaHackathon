# Premise test — horizon matching does NOT rescue the thesis

Run 2026-08-25. Free test (SPY/SPX + VIX only, no option data), per
validate-hypothesis-before-building. 36 years, 1990–2026, ~8,900 usable
observations per horizon. Causal throughout.

## The hypothesis being tested

Tonight's diagnosis was a **horizon mismatch**: MSAR `p_slow` is a 60-day mean and
the trend veto a 200-day MA, so the signal describes month-scale regimes — but we
pointed it at 7-day options, where being 5 days late corrupts 71% of the position's
life. Proposed fix: match the instrument's life to the signal's timescale (3–12
months). Before building anything long-dated, test whether the signal has real
multi-month power.

## Results

| horizon | fwd return ON/OFF | z | fwd RV ON/OFF | z | **t(p_slow \| VIX)** | ΔR² | VRP ON/OFF |
|---|---|---|---|---|---|---|---|
| 3 mo | +2.53% / +1.26% | +1.10 | 13.77% / 22.39% | **−7.89** | **+0.28** | +0.0001 | +3.12 / +4.88 |
| 6 mo | +5.12% / +1.85% | +1.07 | 14.43% / 21.69% | **−4.43** | **+0.90** | +0.0033 | +2.44 / +5.59 |
| 12 mo | +9.84% / +4.46% | +1.07 | 15.21% / 20.77% | **−2.76** | **+1.03** | +0.0066 | +1.65 / +6.51 |

Overlap handled two ways: Newey-West HAC t-stats on the overlapping series, and a
phase-averaged **non-overlapping** estimate (every h-th observation, averaged across
all h phase offsets) as the honest cross-check. Both agree.

## Verdict: FAILS, on two independent grounds

**1. Direction is real in magnitude but not significant.** Gate-ON forward returns
beat gate-OFF at every horizon, and the gap scales sensibly with horizon
(+1.3/+3.3/+5.4pp). But z ≈ +1.07–1.10 throughout — the phase-to-phase dispersion is
as large as the effect. Consistent, not demonstrable.

**2. Vol prediction is spectacular — and entirely owned by VIX.** The gate separates
forward realized vol enormously (13.8% vs 22.4% at 3 months, z = −7.9). It is a
genuinely good vol-regime classifier. **But controlling for VIX, `p_slow` adds
nothing: t = +0.28 / +0.90 / +1.03, ΔR² = 0.0001 / 0.0033 / 0.0066.** Options are
priced off implied vol, so information the market already holds cannot be an edge.
This is the **fifth VIX-subsumption** in this fund (after IV-concentration, IV-curve
shape, gamma-sign, and the credit channel).

**3. The decisive one — the VRP points the WRONG WAY.** The variance risk premium
(VIX − forward realized vol) is what a premium seller actually harvests. It is
**LOWER when the gate is ON**: +3.12 vs +4.88pp at 3 months, widening to +1.65 vs
+6.51pp at 12 months. So the gate systematically steers a vol seller **into the
low-premium regime** and away from the rich one.

That single fact retro-explains the entire night: it is *why* the gated put-spread
book came out flat over 8.4 years of real SPX prices. The gate was selecting the
cheapest premium available.

## What this closes

The signal has **no options-relevant edge at any horizon from 7 days to 12 months**.
Horizon-matching was a correct diagnosis of the 7-DTE failure and still does not
produce a tradeable thesis, because the underlying information is VIX's, not ours.

Combined with the earlier results, premium selling on SPY/SPX is now closed from
every direction tried tonight: structure (condor / put / call / long call), tenor
(7 / 14 / 21 / 30 / 45 DTE, then 3 / 6 / 12 months), gating (ungated / MSAR / trend /
both), and dataset (Alpaca 2024–26 real prices, SPX 2018–26 real bid/ask, SPX+VIX
1990–2026).

## What survives — stated precisely, not generously

- MSAR is an **excellent vol-regime classifier** (z = −7.9 on forward RV). Its
  failure here is not inaccuracy; it is redundancy with a public number.
- The gate is a **validated risk control** (bear test: converts a losing book to
  flat, cuts COVID damage 62% and 2022 damage 78%).
- Neither of those is an options alpha, and neither should be sold as one.

## Remaining untested candidates (from the brainstorm)

- **B. Covered-call ETF forced flow** — JEPI/JEPQ/QYLD complex mechanically selling
  index calls on a published schedule. Untested here; fits the forced-flow framework;
  the 2023–24 growth of the complex means Alpaca's short history is the right window
  rather than a handicap.
- **C. Term-structure / calendar trades** — wholly untested in this fund.
- **D. Risk transformation** — long-dated ITM calls to structurally cap T2-QLD's
  drawdown. Not alpha; solves a problem TC actually has.

## Artifacts
`premise_test.png`, `_premise.csv`, `premise_longhorizon.py`, `viz_premise.py`.
