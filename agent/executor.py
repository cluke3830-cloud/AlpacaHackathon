"""Reconcile the held book to the target book, and persist what we hold.

WHY A STATE FILE AT ALL. Alpaca reports positions, not INTENT -- if both sleeves
happen to want the same contract, the broker shows one line and the agent can no
longer tell which sleeve owns what. Sleeve attribution is the whole point of a
two-sleeve book, so it is tracked locally and reconciled against the broker every
run. When they disagree, the BROKER wins and the discrepancy is printed loudly:
local state is a convenience, never a source of truth about what we own.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C          # noqa: E402
import market               # noqa: E402
import book as bk           # noqa: E402

STATE = Path(__file__).resolve().parent / "state.json"


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return dict(high_water_equity=None, halted=False, halt_reason=None,
                sleeves={}, history=[])


def save_state(s: dict):
    STATE.write_text(json.dumps(s, indent=2, default=str))


def reconcile_state(state: dict, held: dict) -> list[str]:
    """Drop any sleeve whose contract the broker does not actually show."""
    notes = []
    for name, rec in list(state.get("sleeves", {}).items()):
        sym = rec.get("symbol")
        if sym and sym not in held:
            notes.append(f"state claimed {name}={sym} but the broker shows no such "
                         f"position -- clearing (expired, or filled/closed elsewhere)")
            state["sleeves"].pop(name)
    for sym, pos in held.items():
        owned = any(r.get("symbol") == sym for r in state.get("sleeves", {}).values())
        if not owned:
            notes.append(f"broker holds {sym} x{pos['qty']} that no sleeve claims "
                         f"-- NOT auto-liquidating; a human should look at it")
    return notes


def risk_check(state: dict, equity: float) -> tuple[bool, str]:
    hw = state.get("high_water_equity") or equity
    hw = max(hw, equity)
    state["high_water_equity"] = hw
    dd = (equity - hw) / hw if hw else 0.0
    state["drawdown"] = dd
    if state.get("halted"):
        return False, f"HALTED: {state.get('halt_reason')}"
    if dd <= -C.MAX_DRAWDOWN_HALT:
        state["halted"] = True
        state["halt_reason"] = (f"drawdown {100*dd:.1f}% breached the "
                                f"{100*C.MAX_DRAWDOWN_HALT:.0f}% limit on "
                                f"{dt.date.today()}")
        return False, state["halt_reason"]
    if dd <= -C.WARN_DRAWDOWN:
        return True, f"WARNING: drawdown {100*dd:.1f}% (halt at {100*C.MAX_DRAWDOWN_HALT:.0f}%)"
    return True, f"drawdown {100*dd:.1f}%, high-water ${hw:,.0f}"


def plan(state: dict, target: dict, held: dict, chain: pd.DataFrame) -> list[dict]:
    """The exact orders needed to move held -> target. Closes come first so the
    freed buying power is available to the opens in the same pass."""
    closes, opens = [], []
    today = pd.Timestamp(dt.date.today())

    for name in ("sleeve1", "sleeve2"):
        cur = state.get("sleeves", {}).get(name)
        tgt = target.get(name, {})
        want_dir = tgt.get("direction", 0.0)

        if cur and cur.get("symbol") in held:
            exp = pd.Timestamp(cur["expiration"])
            dte_left = (exp - today).days
            flip = want_dir != cur.get("direction")
            roll = dte_left <= C.ROLL_FLOOR
            if flip or roll:
                row = chain[chain["symbol"] == cur["symbol"]]
                if len(row):
                    px = bk.limit_price(row.iloc[0].to_dict(), "sell")
                else:                       # no live quote: fall back to broker mark
                    px = abs(held[cur["symbol"]]["market_value"]) / (100 * abs(held[cur["symbol"]]["qty"]))
                # Sell THIS SLEEVE's own quantity, not the broker's total for the
                # symbol. When both sleeves are long they often select the SAME
                # contract, and the broker then shows one merged line -- closing
                # on that total would flatten the other sleeve too. Capped at
                # what the broker actually holds in case of a partial fill.
                qty = min(int(cur.get("qty", held[cur["symbol"]]["qty"])),
                          int(held[cur["symbol"]]["qty"]))
                if qty <= 0:
                    continue
                closes.append(dict(sleeve=name, action="sell", symbol=cur["symbol"],
                                   qty=qty, limit=px,
                                   why="direction flip" if flip else f"roll ({dte_left}d left)"))
            else:
                continue                    # hold: right direction, enough tenor

        if want_dir != 0 and tgt.get("symbol"):
            already = cur and cur.get("symbol") in held and \
                want_dir == cur.get("direction") and \
                (pd.Timestamp(cur["expiration"]) - today).days > C.ROLL_FLOOR
            if not already:
                opens.append(dict(sleeve=name, action="buy", symbol=tgt["symbol"],
                                  qty=tgt["qty"], limit=bk.limit_price(tgt, "buy"),
                                  why=f"open {'call' if want_dir > 0 else 'put'}",
                                  meta=tgt))
    return closes + opens


def execute(orders: list[dict], state: dict, dry_run: bool = True) -> list[dict]:
    done = []
    for o in orders:
        tag = "[DRY RUN]" if dry_run else "[LIVE]"
        notional = o["qty"] * o["limit"] * 100
        print(f"  {tag} {o['action'].upper():4} {o['qty']:>3} x {o['symbol']} "
              f"@ ${o['limit']:.2f} limit  (${notional:,.0f})  — {o['why']}")
        if dry_run:
            o["status"] = "dry_run"
        else:
            try:
                res = market.submit_limit(o["symbol"], o["qty"], o["action"], o["limit"])
                o["status"] = str(res.status)
                o["order_id"] = str(res.id)
                print(f"         submitted id={res.id} status={res.status}")
            except Exception as e:                              # noqa: BLE001
                o["status"] = f"ERROR: {e}"
                print(f"         *** ORDER REJECTED: {e}")
                done.append(o)
                continue

        # A DRY RUN MUST NOT WRITE HOLDINGS IT DOES NOT HAVE. reconcile_state
        # would clear the fiction on the next run anyway (broker is truth), but
        # a state file that claims positions we never opened is exactly the kind
        # of thing that survives into a live session and gets believed.
        if dry_run:
            done.append(o)
            continue

        # local intent tracking mirrors what we just asked for
        if o["action"] == "sell":
            state.setdefault("sleeves", {}).pop(o["sleeve"], None)
        else:
            m = o["meta"]
            state.setdefault("sleeves", {})[o["sleeve"]] = dict(
                symbol=o["symbol"], qty=o["qty"], direction=m["direction"],
                expiration=str(pd.Timestamp(m["expiration"]).date()),
                strike=m["strike"], side=m["side"],
                opened=dt.datetime.now(dt.timezone.utc).isoformat(),
                entry_limit=o["limit"])
        done.append(o)
    return done


def await_fills(orders: list[dict], chain: pd.DataFrame, state: dict,
                timeout_s: int = 90, poll_s: int = 10, chase: bool = True) -> dict:
    """Confirm the orders actually filled, and chase the ones that didn't.

    WHY CHASING IS BACKTEST-CONSISTENT, NOT A DEVIATION: the headline backtest
    charged cost_frac=1.0, i.e. it assumed we pay the FULL quoted spread --
    buying at the ask, selling at the bid -- on every single trade. The agent
    opens with a marketable limit at half that (LIMIT_COST_FRAC=0.5) purely as
    an attempt to do better. If that limit does not fill, walking it to the ask
    lands exactly on what the backtest already assumed. The genuinely dangerous
    outcome is the opposite one: an unfilled order leaves us FLAT while the
    backtest was positioned, which is a different strategy than the one
    validated -- silently, with no error.

    Only meaningful when orders were actually submitted (not a dry run)."""
    import time

    live = [o for o in orders if o.get("order_id")]
    if not live:
        return {}
    deadline = time.time() + timeout_s
    pending = {o["order_id"]: o for o in live}
    filled, unfilled = {}, {}

    while pending and time.time() < deadline:
        time.sleep(poll_s)
        for oid in list(pending):
            try:
                st = market.get_order(oid)
            except Exception as e:                                  # noqa: BLE001
                print(f"    [warn] status {oid}: {e}")
                continue
            status = str(st.status).lower()
            fq = int(float(st.filled_qty or 0))
            if "filled" in status and fq >= pending[oid]["qty"]:
                o = pending.pop(oid)
                o["filled_qty"] = fq
                o["fill_price"] = float(st.filled_avg_price or 0)
                filled[oid] = o
                print(f"    FILLED {o['action']} {fq} x {o['symbol']} "
                      f"@ ${o['fill_price']:.2f}")
            elif status in ("canceled", "expired", "rejected"):
                o = pending.pop(oid)
                o["filled_qty"] = fq
                unfilled[oid] = o
                print(f"    {status.upper()} {o['action']} {o['symbol']} "
                      f"(filled {fq}/{o['qty']})")

    for oid, o in pending.items():
        unfilled[oid] = o
        print(f"    STILL OPEN after {timeout_s}s: {o['action']} {o['symbol']}")

    if chase and unfilled:
        print(f"  chasing {len(unfilled)} unfilled order(s) to the far side "
              f"(= the backtest's own cost assumption)")
        for oid, o in unfilled.items():
            done = int(o.get("filled_qty", 0) or 0)
            remaining = o["qty"] - done
            if remaining <= 0:
                continue
            market.cancel_order(oid)
            row = chain[chain["symbol"] == o["symbol"]]
            if not len(row):
                print(f"    [warn] no quote to chase {o['symbol']}; leaving flat")
                continue
            r = row.iloc[0]
            px = float(r["ask"]) if o["action"] == "buy" else float(r["bid"])
            try:
                res = market.submit_limit(o["symbol"], remaining, o["action"], px)
                print(f"    RE-SENT {o['action']} {remaining} x {o['symbol']} "
                      f"@ ${px:.2f} (far side) id={res.id}")
                o["chase_order_id"] = str(res.id)
            except Exception as e:                                  # noqa: BLE001
                print(f"    *** chase rejected: {e}")

    return dict(filled=len(filled), unfilled=len(unfilled))
