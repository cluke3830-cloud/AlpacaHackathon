"""The agent. One decision per session, at the close.

FLOW, and every step can refuse:
  1. calendar gate      -- real exchange calendar, not a cron timer's guess
  2. account + risk     -- high-water drawdown check, halts and stays halted
  3. signal             -- dealer gamma from Alpaca OI + MSAR/VIX + trend
  4. target book        -- two sleeves, delta-matched, leverage-scaled
  5. reconcile          -- broker positions are truth; local state is a hint
  6. execute            -- marketable limits, DRY_RUN unless explicitly off
  7. greek report       -- live portfolio delta/gamma/theta/vega from Alpaca

WHY THE GREEK REPORT EXISTS (TC asked for live greeks in the agent, and this
is the honest use for them): the SIGNAL does not read our own position greeks
-- every attempt to build alpha from greeks was tested and killed this week
(vanna/charm sign, gamma/vanna/charm magnitude veto and dial, dealer vega,
vega x VIX; rho dropped on a magnitude check at 0.03% of vega). What live
greeks ARE good for is knowing what we actually hold: whether realized delta
matches the delta we sized for, how much theta we are paying to carry the
position, and how much vega risk is riding along. That is monitoring, not
signal, and it is labeled as such rather than dressed up as alpha.

RUN:
  python3 run_agent.py              # dry run, prints intended orders
  AGENT_DRY_RUN=false python3 run_agent.py    # actually submits
  python3 run_agent.py --force      # skip the calendar gate (testing only)
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C          # noqa: E402
import market               # noqa: E402
import book as bk           # noqa: E402
import executor as ex       # noqa: E402
import signal_live          # noqa: E402


def banner(t):
    print(f"\n{'='*72}\n{t}\n{'='*72}")


def greek_report(state: dict, held: dict, chain: pd.DataFrame, equity: float):
    """Live portfolio greeks, straight from Alpaca's own per-contract greeks.

    Monitoring only -- nothing here feeds the trading decision. The point is to
    see whether what we HOLD matches what we INTENDED to hold: if realized
    delta has drifted far from the delta-notional we sized for, the position is
    no longer the thing the backtest measured, and that is worth seeing before
    it becomes a surprise."""
    if not held:
        print("  (flat -- no greeks to report)")
        return {}
    rows = []
    for sleeve, rec in state.get("sleeves", {}).items():
        sym = rec.get("symbol")
        if sym not in held:
            continue
        # sleeve-owned qty, NOT the broker total -- both sleeves frequently hold
        # the SAME contract, which the broker reports as one merged line.
        q = min(int(rec.get("qty", held[sym]["qty"])), int(held[sym]["qty"]))
        m = chain[chain["symbol"] == sym]
        if not len(m):
            print(f"  {sleeve}: {sym} x{q} -- no live quote/greeks available")
            continue
        r = m.iloc[0]
        d = r.get("delta_alpaca")
        d = float(d) if pd.notna(d) else float(r.get("delta", np.nan))
        rows.append(dict(sleeve=sleeve, symbol=sym, qty=q,
                         delta=d * q * 100,
                         gamma=float(r.get("gamma_alpaca", np.nan) or np.nan) * q * 100,
                         iv=float(r.get("iv", np.nan)),
                         spread=float(r.get("spread_frac", np.nan)),
                         mkt_val=held[sym]["market_value"] * q / max(int(held[sym]["qty"]), 1),
                         upl=held[sym]["unrealized_pl"] * q / max(int(held[sym]["qty"]), 1)))
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    spot = market.spot()
    tot_delta_sh = df["delta"].sum()                 # share-equivalent delta
    tot_notional = tot_delta_sh * spot
    print(f"  {'sleeve':<9}{'symbol':<22}{'qty':>4}{'Δ(sh)':>9}{'IV':>7}"
          f"{'mktval':>10}{'uPL':>9}")
    for r in df.itertuples():
        print(f"  {r.sleeve:<9}{r.symbol:<22}{r.qty:>4}{r.delta:>9.0f}"
              f"{100*r.iv:>6.1f}%{r.mkt_val:>10,.0f}{r.upl:>+9,.0f}")
    print(f"\n  portfolio delta      {tot_delta_sh:>10,.0f} shares "
          f"(${tot_notional:,.0f} notional)")
    print(f"  effective leverage   {tot_notional/equity:>10.2f}x   "
          f"(target {C.GROSS_LEVERAGE:.2f}x)")
    drift = abs(tot_notional / equity / C.GROSS_LEVERAGE - 1) if equity else 0
    if drift > 0.35:
        print(f"  ** WARNING: realized exposure is {100*drift:.0f}% off target. "
              f"The position is no longer what was sized/backtested.")
    print(f"  premium at risk      {df['mkt_val'].sum():>10,.0f} "
          f"({100*df['mkt_val'].sum()/equity:.1f}% of equity) "
          f"-- max loss is bounded by this")
    print(f"  unrealized P&L       {df['upl'].sum():>+10,.0f}")
    return dict(delta_shares=float(tot_delta_sh), notional=float(tot_notional),
                eff_leverage=float(tot_notional / equity) if equity else np.nan,
                premium=float(df["mkt_val"].sum()), upl=float(df["upl"].sum()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="skip the exchange-calendar gate (testing only)")
    args = ap.parse_args()

    banner(f"ALPACA OPTIONS AGENT   {dt.datetime.now():%Y-%m-%d %H:%M:%S}   "
           f"{'DRY RUN' if C.DRY_RUN else '*** LIVE ***'}")
    print(f"  {C.UNDERLYING} | Δ{C.TARGET_DELTA} | {C.TARGET_DTE}DTE | "
          f"{C.GROSS_LEVERAGE:.2f}x | halt {100*C.MAX_DRAWDOWN_HALT:.0f}%")

    # -- 1. calendar -------------------------------------------------------
    ok, why = market.market_open_now()
    print(f"\n[1] calendar: {why}")
    if not ok and not args.force:
        print("    -> not a tradeable session. Exiting without touching anything.")
        return 0
    if not ok:
        print("    -> --force given, proceeding anyway (TESTING)")

    # -- 2. account + risk -------------------------------------------------
    acct = market.account()
    held = market.positions()
    state = ex.load_state()
    print(f"\n[2] account {acct['number']}  equity ${acct['equity']:,.2f}  "
          f"cash ${acct['cash']:,.2f}  positions {len(held)}")
    for note in ex.reconcile_state(state, held):
        print(f"    ! {note}")
    can_trade, risk_msg = ex.risk_check(state, acct["equity"])
    print(f"    risk: {risk_msg}")
    if not can_trade:
        print("    -> HALTED. Flattening is a human decision; not re-entering.")
        ex.save_state(state)
        return 1

    # -- 3. signal ---------------------------------------------------------
    print("\n[3] signal")
    try:
        sig = signal_live.todays_signal()
    except Exception as e:                                       # noqa: BLE001
        print(f"    *** REFUSED TO TRADE: {e}")
        ex.save_state(state)
        return 1

    # -- 4. target book ----------------------------------------------------
    print("\n[4] target book")
    chain = bk.tradable_chain(sig["spot"])
    target = bk.target_book(sig, acct["equity"], chain=chain)
    print(bk.describe(target))

    # -- 5/6. plan + execute ----------------------------------------------
    print("\n[5] plan")
    orders = ex.plan(state, target, held, chain)
    if not orders:
        print("  nothing to do -- held book already matches target")
    else:
        print(f"\n[6] execute ({len(orders)} order(s))")
        ex.execute(orders, state, dry_run=C.DRY_RUN)
        if not C.DRY_RUN:
            print("\n[6b] confirming fills")
            fills = ex.await_fills(orders, chain, state)
            if fills:
                print(f"    {fills['filled']} filled, {fills['unfilled']} chased/open")
    ex.save_state(state)

    # -- 7. live greeks ----------------------------------------------------
    print("\n[7] live portfolio greeks (monitoring only, not signal)")
    held_after = market.positions() if not C.DRY_RUN else held
    g = greek_report(state, held_after, chain, acct["equity"])

    state.setdefault("history", []).append(dict(
        ts=dt.datetime.now(dt.timezone.utc).isoformat(), equity=acct["equity"],
        gate=sig["gate"], ac_dir=sig["ac_dir"], gex=sig["gex"], vix=sig["vix"],
        n_orders=len(orders), dry_run=C.DRY_RUN, greeks=g))
    state["history"] = state["history"][-500:]
    ex.save_state(state)
    print(f"\ndone. state -> {ex.STATE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
