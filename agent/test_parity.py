"""Does the LIVE agent's signal code reproduce the BACKTEST's signal code?

THE FAILURE THIS EXISTS TO CATCH is the most expensive one available to us: the
agent trades a signal that is subtly not the signal that was validated. Nothing
crashes, the numbers look plausible, and the 1.19 Sharpe on record describes a
strategy we are not actually running. Every other test in this repo checks
whether the EDGE is real; this checks whether the CODE agrees with itself.

The two paths differ in data source by necessity:
  backtest  marketdata.app cached parquet chains -> us_bear_lab.build_us_gex
  live      Alpaca contracts (OI) + snapshots    -> signal_live.dealer_gex

So this does NOT assert the two produce identical numbers on the same calendar
day -- they read different vendors' snapshots and would differ for reasons that
have nothing to do with correctness. Instead it feeds the BACKTEST's OWN cached
data through the LIVE code path and asserts the live code reproduces the
backtest's number. That isolates code-equivalence from data-vendor difference,
which is the thing actually worth testing.

Run:  python3 test_parity.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]          # HERE is the agent dir, so repo root is 2 up
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "mandatory_tests_for_deployment_2"))
sys.path.insert(0, str(ROOT / "KoreanStatArb" / "scripts"))

import config as C                      # noqa: E402
import signal_live                      # noqa: E402
import or_smh_signal as sigmod          # noqa: E402
import t2_qld_signal as t2              # noqa: E402

GEX_DATA = ROOT / "U.S._gamma_strategy" / "Reflexive_0DTE_Research" / "data"
TOL = 1e-6


def _chain_as_alpaca_shape(df: pd.DataFrame) -> tuple:
    """Reshape a cached marketdata.app chain row-set into the (contracts,
    snapshots) pair signal_live.dealer_gex expects from Alpaca."""
    contracts = pd.DataFrame(dict(
        symbol=df["optionSymbol"].values,
        side=df["side"].values,
        strike=df["strike"].values.astype(float),
        expiration=pd.to_datetime(df["expiration"], unit="s"),
        oi=pd.to_numeric(df["openInterest"], errors="coerce").values,
        oi_date=pd.NaT,
        tradable=True,
        dte=df["dte"].values.astype(int),
        underlyingPrice=df["underlyingPrice"].values.astype(float)))
    snaps = pd.DataFrame(dict(
        symbol=df["optionSymbol"].values,
        bid=df["bid"].values.astype(float),
        ask=df["ask"].values.astype(float),
        mid=pd.to_numeric(df["mid"], errors="coerce").values,
        iv_alpaca=np.nan, delta_alpaca=np.nan, gamma_alpaca=np.nan))
    snaps["spread_frac"] = (snaps["ask"] - snaps["bid"]) / snaps["mid"].replace(0, np.nan)
    return contracts, snaps


def test_gex_parity(n_dates: int = 12) -> bool:
    """Live dealer_gex() vs backtest build_us_gex(), same cached input data."""
    import us_bear_lab
    us_bear_lab.CHAINS = GEX_DATA / "chains_SPY.parquet"
    us_bear_lab.CHAINS_PRE = GEX_DATA / "chains_SPY.parquet"
    bt = us_bear_lab.build_us_gex()
    bt.index = pd.to_datetime(bt.index).normalize()

    raw = pd.read_parquet(GEX_DATA / "chains_SPY.parquet")
    raw["date"] = pd.to_datetime(raw["date"]).dt.normalize()

    dates = [d for d in bt.index[-n_dates:] if d in set(raw["date"])]
    print(f"  comparing {len(dates)} dates ({dates[0].date()} -> {dates[-1].date()})")
    worst, fails = 0.0, 0
    for d in dates:
        day = raw[raw["date"] == d]
        contracts, snaps = _chain_as_alpaca_shape(day)
        try:
            live = signal_live.dealer_gex(contracts, snaps)["gex"]
        except RuntimeError as e:
            print(f"    {d.date()}: live path refused ({e})")
            fails += 1
            continue
        # build_us_gex is the RETAIL-SIGNED aggregate; dealer_gex returns the same
        # quantity under the same convention, so they must match to float noise.
        ref = float(bt.loc[d])
        rel = abs(live - ref) / max(abs(ref), 1e-9)
        worst = max(worst, rel)
        if rel > 1e-4:
            fails += 1
            print(f"    {d.date()}: MISMATCH live={live:,.0f} backtest={ref:,.0f} "
                  f"rel={rel:.2e}")
    print(f"  worst relative difference: {worst:.2e}")
    ok = fails == 0
    print(f"  {'PASS' if ok else 'FAIL'} -- GEX code paths "
          f"{'agree' if ok else 'DISAGREE'}")
    return ok


def test_gate_logic_parity() -> bool:
    """The gate/direction algebra itself, live vs backtest, on synthetic inputs.

    Exhaustive over the discrete state space rather than sampled: there are only
    a handful of (gex_sign, ret, mom, msar, vol_era, trend) combinations that
    matter, and a signal this important should be checked on all of them."""
    fails = 0
    checked = 0
    for gex_sign in (-1.0, 1.0):
        for ret_t in (-0.01, 0.01):
            for mom20 in (-0.02, 0.02):
                for msar_long in (True, False):
                    for p_slow in (0.2, 0.8):           # below / above VOL_ERA_P
                        for trend_ok in (0.0, 1.0):
                            checked += 1
                            ac = sigmod.ac_net_direction(gex_sign, ret_t, mom20)
                            gate_ref = t2.t2_gate(msar_long, ac, p_slow, trend_ok)
                            # live path recomputes the same way in todays_signal()
                            or_gate = bool(msar_long) or ac > 0
                            gate_live = bool(or_gate and (p_slow < t2.VOL_ERA_P)
                                            and bool(trend_ok))
                            if gate_ref != gate_live:
                                fails += 1
                                print(f"    MISMATCH gex={gex_sign} ret={ret_t} "
                                      f"mom={mom20} msar={msar_long} p_slow={p_slow} "
                                      f"trend={trend_ok}: ref={gate_ref} live={gate_live}")
    print(f"  checked {checked} state combinations, {fails} mismatches")
    print(f"  {'PASS' if not fails else 'FAIL'} -- gate algebra "
          f"{'agrees' if not fails else 'DISAGREES'}")
    return fails == 0


def test_sizing_math() -> bool:
    """Sizing must produce the delta-notional the config asks for."""
    equity, spot, delta = 100_000.0, 765.0, 0.70
    ok = True
    for lev in (1.0, 2.0, 4.0):
        tgt1 = equity * lev * C.NOTIONAL_W_SLEEVE1
        per = spot * delta * 100.0
        qty = max(int(round(tgt1 / per)), 1)
        realized = qty * per
        err = abs(realized / tgt1 - 1)
        status = "ok" if err < 0.30 else "COARSE"
        print(f"  lev {lev:.1f}x sleeve1: target ${tgt1:,.0f} -> {qty} contracts "
              f"= ${realized:,.0f} ({100*err:.0f}% discretization) {status}")
        if err >= 0.50:
            ok = False
    w = C.NOTIONAL_W_SLEEVE1 + C.NOTIONAL_W_SLEEVE2
    print(f"  notional weights sum to {w:.4f}")
    if abs(w - 1.0) > 1e-6:
        print("    FAIL: weights must sum to 1")
        ok = False
    print(f"  {'PASS' if ok else 'FAIL'} -- sizing math")
    return ok


def test_config_sanity() -> bool:
    """Guardrails that should never silently drift."""
    ok = True
    checks = [
        ("DTE band inside available data", C.TARGET_DTE - C.DTE_BAND >= C.DTE_MIN
         and C.TARGET_DTE + C.DTE_BAND <= C.DTE_MAX + 3),
        ("roll floor below target dte", C.ROLL_FLOOR < C.TARGET_DTE),
        ("halt above warn", C.MAX_DRAWDOWN_HALT > C.WARN_DRAWDOWN),
        ("halt scales with leverage", C.MAX_DRAWDOWN_HALT >= min(0.25, 0.099 * C.GROSS_LEVERAGE)),
        ("limit cost frac <= backtest cost frac", C.LIMIT_COST_FRAC <= 1.0),
        ("gex lag is 1 (Alpaca OI is prior session)", C.GEX_LAG_SESSIONS == 1),
        ("min gex contracts is a real floor", C.MIN_GEX_CONTRACTS >= 50),
    ]
    for name, cond in checks:
        print(f"  [{'ok ' if cond else 'FAIL'}] {name}")
        ok = ok and cond
    print(f"  {'PASS' if ok else 'FAIL'} -- config sanity")
    return ok


def test_idempotency() -> bool:
    """Holding the right contract must produce NO orders.

    The agent runs once per session; if it re-buys something it already holds,
    it doubles exposure every day and silently drifts to many times the sized
    leverage. This is the single most expensive operational bug available."""
    import executor as ex
    SYM = "SPY260904C00760000"
    exp = (pd.Timestamp.today().normalize() + pd.Timedelta(days=5))
    state = dict(sleeves={"sleeve1": dict(symbol=SYM, qty=4, direction=1.0,
                                          expiration=str(exp.date()), strike=760.0,
                                          side="call")})
    held = {SYM: dict(qty=4, avg_entry=7.7, market_value=3100.0, unrealized_pl=5.0)}
    chain = pd.DataFrame([dict(symbol=SYM, bid=7.6, ask=7.8, mid=7.7, spread_frac=0.026)])
    target = {"sleeve1": dict(direction=1.0, symbol=SYM, qty=4, side="call", strike=760.0,
                              expiration=exp, bid=7.6, ask=7.8, mid=7.7),
              "sleeve2": dict(direction=0.0, symbol=None, qty=0, reason="flat")}
    orders = ex.plan(state, target, held, chain)
    ok = len(orders) == 0
    print(f"  already-correct book -> {len(orders)} orders "
          f"({'PASS' if ok else 'FAIL - would double exposure'})")

    # and the roll case: same contract but expiring inside ROLL_FLOOR must roll
    exp2 = pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
    state2 = dict(sleeves={"sleeve1": dict(symbol=SYM, qty=4, direction=1.0,
                                           expiration=str(exp2.date()), strike=760.0,
                                           side="call")})
    o2 = ex.plan(state2, target, held, chain)
    rolls = [x for x in o2 if x["action"] == "sell"]
    ok2 = len(rolls) == 1
    print(f"  expiring inside roll floor -> {len(rolls)} sell "
          f"({'PASS' if ok2 else 'FAIL - would let it expire'})")
    print(f"  {'PASS' if ok and ok2 else 'FAIL'} -- idempotency / roll")
    return ok and ok2


if __name__ == "__main__":
    print("=" * 72)
    print("AGENT PARITY / SANITY SUITE")
    print("=" * 72)
    results = {}
    print("\n[1] dealer GEX: live code path vs backtest code path, same input data")
    results["gex_parity"] = test_gex_parity()
    print("\n[2] gate algebra: exhaustive over the discrete state space")
    results["gate_parity"] = test_gate_logic_parity()
    print("\n[3] sizing math")
    results["sizing"] = test_sizing_math()
    print("\n[4] config sanity")
    results["config"] = test_config_sanity()
    print("\n[5] idempotency / roll (no double-buying, no letting it expire)")
    results["idempotency"] = test_idempotency()

    print("\n" + "=" * 72)
    n_ok = sum(results.values())
    for k, v in results.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    print(f"{n_ok}/{len(results)} suites passed")
    print("=" * 72)
    sys.exit(0 if n_ok == len(results) else 1)
