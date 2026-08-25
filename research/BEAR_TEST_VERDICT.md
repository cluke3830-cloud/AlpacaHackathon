# Bear test — VERDICT: thesis dead as alpha, gate survives as risk control

Run 2026-08-25, on TC's call to validate the load-bearing component before building.

Data: our own `chains_SPX.parquet` + `chains_SPX_pre2022.parquet` —
**2018-01-02 → 2026-06-12, 8.4 years, REAL bid/ask, 5–9 DTE**, covering
Fed-Pivot-2018, COVID-2020, Tech-Bear-2022, SVB-2023. This satisfies the
Constitution's bias #5 sample requirement, which Alpaca's 2.6 years cannot.

Structure mirrors the Alpaca-validated one: weekly non-overlapping entries, ~7 DTE,
short put 1.9–2.8% OTM, wing 0.65% of spot, credit = short BID − long ASK, 4% cost,
PM settlement (SPXW). Gate evaluated at ENTRY (causal).

## Headline

| era | ungated Sharpe | gated Sharpe |
|---|---|---|
| **2018–2026 FULL (8.4y)** | −0.32 | **+0.04** |
| 2024–2026 (all Alpaca can see) | +0.86 | **+1.54** |
| bear windows only | −2.54 | −5.94 |

**Same strategy, same code. Alpaca's window says +1.54. The full record says +0.04
(t = +0.09).** The 2.6-year sample was not a small sample of the truth — it was the
one benign stretch.

Full-sample E per unit width, 2.5% OTM: ungated **−0.0119**, gated **+0.0012**.

## What the gate actually does — corrected

My first chart claimed "the gate makes every stress window worse." That is true
per-trade and **false in total**, because the gate takes far fewer trades. Both
numbers matter; showing only one overstated the kill. Corrected:

| window | ungated TOTAL | gated TOTAL | trades taken | per-trade (gated) |
|---|---|---|---|---|
| Fed-Pivot 2018 | −4.54 | **−3.78** | 36% | −0.95 |
| COVID 2020 | −2.51 | **−0.96** | 10% | −0.96 |
| Tech-Bear 2022 | −5.01 | **−1.10** | 16% | −0.16 |
| SVB 2023 | +0.60 | +0.22 | 50% | +0.11 |

So the gate **does** work as designed — it stands down and cuts aggregate stress
damage substantially (2022: −5.01 → −1.10). Over the full sample it converts a
clearly-losing book (−4.6 units) into a flat one (+0.4 units).

**But the trades it does take in stress are near-max losses (−0.95, −0.96).** The
gate is *late*, not early: MSAR's `p_slow` is a 60-day mean and the 200d MA breaks
well after a drawdown starts. For a daily-rebalanced long/flat equity book that
lateness costs a few percent — which is what it was built and validated for. For a
weekly short-premium book, one late week loses ~95% of max loss. **The gate is
structurally too slow for this instrument.**

## Verdict against the pre-registered bar

| criterion | result |
|---|---|
| Sharpe ≥ 0.75 full sample | **FAIL** (+0.04) |
| positive both halves | fails on any honest full-sample split |
| t ≥ 2.0 | **FAIL** (+0.09) |
| survives multiple testing | moot |

**The thesis is dead as an alpha source.** No renegotiation — the bar was written
down before the run.

## What survives, and it is not nothing

The gate is a **validated risk control on real bear data**: it converts a losing
premium book into a flat one and cuts COVID damage by 62% and 2022 damage by 78%.
That is the same identity every gate in this fund has landed on
([[project_korea_iv_risklayer]]: "gate value = risk control";
[[project_market_tab_vix_termstructure]]: "risk gauge, not direction signal").

Per TC's pre-authorised fallback, the build now moves to the **risk-control framing**
with existing infrastructure maximised.

## Methodological note — two mislabels caught in one session

1. Called the strike sweep "fragile" when it was smooth and monotonic (a real effect).
2. Called the gate's stress-window behaviour uniformly "worse" when it was worse
   per-trade but better in total.

Both were corrections *against* the direction I was arguing at the time. Recording
them because the failure mode this whole exercise exists to prevent is fitting the
label to the conclusion.

## Artifacts
`bear_test_kill.png` (corrected), `_spxbear.csv`, `spx_bear_test.py`,
`viz_bear_final.py`.
