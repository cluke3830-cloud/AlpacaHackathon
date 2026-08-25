# Alpaca Hackathon — options research record

**Open [`index.html`](index.html) in a browser for the full illustrated record.**

Research for the Alpaca AI Trading Agents Hackathon (Aug 28 – Sep 4, 2026),
Options Alpha Agents track. This folder is the honest record of a thesis that was
tested properly and **falsified**.

---

## The one-line result

Selling defined-risk index option premium, gated by the deployed MSAR + 200d-trend
signal, has **no validated edge**. It scores Sharpe **+1.54** on the 2.6 years of
option history Alpaca serves, and **+0.27** across the full 8.4-year record with
real bid/ask. Run through this fund's own mechanical deploy gate it comes back
**FAIL → DEPLOY BLOCKED**.

```
python3 mandatory_tests_for_deployment/certify.py alpaca_option
```

```
=== alpaca_option : FAIL -> BLOCKED ===
  [PASS] lookahead     edge survives +1 bar lag (0.52 -> 0.23, keeps 44%, same sign)
  [PASS] survivorship  cash-settled index only — no constituent selection possible
  [PASS] fill_price    deployed(natural)=-0.27 alts={'mid': 0.53} swing=0.81
  [PASS] cost_realism  44.0bps, calibrated to live Alpaca quotes, real instrument
  [FAIL] regime        loses money in Fed-Pivot-2018 -3.09, COVID-2020 -2.28, Tech-Bear-2022 -1.12
  [FAIL] overfitting   DSR=0.042 < 0.95 (n_configs=90)
  [PASS] shortability  listed index option — no borrow, no short-ban exposure
  [PASS] liquidity     $5M book immaterial to SPXW weekly volume
  [PASS] pit_vintage   point-in-time chain snapshots
```

---

## What was actually learned

**1. Costs are not the obstacle.** SPY condor entry slippage is 1–7% of credit —
genuinely cheap, unlike the single-name and 0DTE cost walls that killed earlier
work in this fund. The instrument is tradeable; the edge is what's missing.

**2. A look-ahead leak was caught in our own work.** A gated put-spread book showed
annualized Sharpe **+1.24** at a 96% win rate. The gate was being evaluated at each
window's *end* date rather than at entry. Corrected: **+0.10** — retaining 8% of its
magnitude, which `causal_retest` classifies as *collapse, i.e. a leak*.

**3. Index options are fairly priced.** Ungated premium selling prices out at
E ≈ +0.007 to +0.027 per share. Sixth independent confirmation in this fund.

**4. The gate is a real risk control but it is late, not early.** Over 8.4 years it
converts a losing book (−4.6 units) into a flat one (+0.4), cutting COVID damage 62%
and 2022 damage 78% by standing down. But the few trades it *does* take in stress are
near-max losses (−0.95, −0.96). `p_slow` is a 60-day mean and the 200d MA breaks after
a drawdown starts — fine for the daily long/flat equity book it was validated on,
structurally too slow for a weekly short-premium book.

**5. Horizon matching does not rescue it.** Across 36 years, the gate predicts forward
realized vol beautifully (13.8% vs 22.4% at 3 months, z = −7.9) — but controlling for
VIX it adds nothing (ΔR² ≈ 0.0001–0.0066). And the **variance risk premium points the
wrong way**: premium is *richer* when the gate is OFF. The gate systematically steers
a vol seller into the cheapest premium available. That single fact explains everything.

**6. Mid-fill flatters this book by ~0.8 Sharpe** (+0.53 mid vs −0.27 natural). Every
P&L reported here uses the natural fill: sell the short leg at its bid, buy the wing at
its ask.

---

## Alpaca stack — verified, not assumed

| capability | finding |
|---|---|
| paper account | active, options level 3, multi-leg `OrderClass.MLEG` native |
| live chain | 13,316 SPY contracts, greeks + IV on 10,736 |
| spread cost | 1–7% of credit — cheap |
| option history | **starts 2024-01-18** — contains none of the four stress windows |
| historical bid/ask | **does not exist** — bars and trades only |
| VIX | **not available** — MSAR's input must come from FMP/FDR |
| data feed | `indicative` (derived BBO); `opra` requires signing the agreement |

---

## Layout

```
AlpacaHackathon/
├── index.html                    ← START HERE (illustrated record)
├── README.md
├── .env.example                  ← copy to .env; .env is gitignored
├── src/
│   ├── alpaca_keys.py            single credential source; no key literals anywhere else
│   ├── option_premium_signal.py  structure + gate logic, no I/O  ─┐ imported by BOTH the
│   ├── spx_backtest.py           canonical 8.4y backtest         ─┘ research and the manifest
│   ├── probes/                   5 capability / cost / data-quality probes
│   ├── backtests/                13 runs, numbered in execution order
│   └── viz/                      6 plotting scripts
├── research/                     5 write-ups + 7 charts + 2 interactive HTML
└── data/                         result CSVs from every run
```

Certified logic lives in `src/option_premium_signal.py` and `src/spx_backtest.py`, and
**both the research and the integrity manifest import from them** — so certified logic
and executed logic cannot drift. Same rule as `t2_qld_signal.py`.

Two backtests are marked `_ARTIFACT`: they produced results that turned out to be model
artifacts. They are kept as the record of that, and excluded from every conclusion.

---

## Reproducing

```bash
cp AlpacaHackathon/.env.example AlpacaHackathon/.env   # add your Alpaca paper keys
cd AlpacaHackathon/src

python3 probes/04_condor_cost.py                 # real condor cost from the live chain
python3 backtests/12_spx_bear_test_DECISIVE.py   # the 8.4-year kill
python3 backtests/13_premise_long_horizon.py     # the VRP-points-the-wrong-way finding
python3 viz/viz_gate_verdict.py                  # regenerate the gate chart

cd ../.. && python3 -m pytest mandatory_tests_for_deployment/tests/test_integrity_alpaca_option.py -q
```

The scripts hit the live Alpaca API and read
`U.S._gamma_strategy/Reflexive_0DTE_Research/data/chains_SPX*.parquet`. The integrity
test skips cleanly if those parquets have been evicted by iCloud.

---

## Honest limits

- 2024–2026 Alpaca history contains **no bear market** — that is precisely what made it lie.
- The 50%-profit-take exit rule is **untestable** on this data: exits priced from
  `close(short) − close(long)` on daily bars use last-trade prints from different moments;
  2.3% of path-days give an impossible (negative) spread value and the p90 daily jump is
  $0.58 against a ~$0.27 profit target. The rule was selecting noise. Live, with real-time
  quotes, it is implementable — it just cannot be backtested here.
- ~90 configurations were examined in total. That ledger is declared in the manifest
  (`n_configs_tried=90`) and is what drives the DSR failure. It is not hidden.
- A paper key is committed elsewhere in this repo at
  `Past Strategies/Alpaca/Option_Session/Session_5.py` and **should be rotated**. No new
  file here contains a key literal.
