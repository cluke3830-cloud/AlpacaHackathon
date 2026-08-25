"""THROWAWAY PROBE 4 — THE decisive cost test, per Constitution bias #3.

gamma-VRP's carry proxy said Sharpe 4.02; the real short straddle was 0.21.
The lesson: price the ACTUAL structure at REAL quotes before believing anything.

So: build the real iron condor this agent would trade (~0.15-delta shorts,
21-45 DTE, defined wings) from the LIVE Alpaca chain, and measure
   spread cost as a fraction of the credit collected.
If crossing the spread eats most of the premium, no signal can save it.
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from alpaca_keys import API_KEY, SECRET_KEY  # noqa: E402
K = K_API = API_KEY
S = S_API = SECRET_KEY
from datetime import datetime, timedelta



TARGET_DELTA = 0.15
WING_WIDTHS = [5, 10, 20]


def load_chain(underlying="SPY"):
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionChainRequest
    dc = OptionHistoricalDataClient(K, S)
    return dc.get_option_chain(OptionChainRequest(underlying_symbol=underlying))


def parse(sym):
    """OCC: ROOT + YYMMDD + C/P + strike*1000."""
    body = sym[-15:]
    exp = datetime.strptime(body[:6], "%y%m%d").date()
    return exp, body[6], int(body[7:]) / 1000.0


def rows(chain):
    out = []
    for sym, snap in chain.items():
        g = getattr(snap, "greeks", None)
        q = getattr(snap, "latest_quote", None)
        if not g or not q or q.bid_price is None or q.ask_price is None:
            continue
        if q.bid_price <= 0 or q.ask_price <= 0:
            continue
        try:
            exp, cp, strike = parse(sym)
        except Exception:
            continue
        out.append(dict(sym=sym, exp=exp, cp=cp, strike=strike,
                        delta=g.delta, bid=q.bid_price, ask=q.ask_price,
                        mid=(q.bid_price + q.ask_price) / 2,
                        iv=getattr(snap, "implied_volatility", None)))
    return out


def pick(cands, key):
    return min(cands, key=key) if cands else None


def main():
    chain = load_chain("SPY")
    r = rows(chain)
    today = datetime.now().date()
    for x in r:
        x["dte"] = (x["exp"] - today).days

    # Candidate expiries in the plan's 21-45 DTE window.
    dtes = sorted({x["dte"] for x in r if 21 <= x["dte"] <= 45})
    print(f"chain contracts w/ greeks+2-sided quotes: {len(r)}")
    print(f"expiries in 21-45 DTE window: {dtes}\n")

    for dte in dtes[:3]:
        leg = [x for x in r if x["dte"] == dte]
        calls = [x for x in leg if x["cp"] == "C"]
        puts = [x for x in leg if x["cp"] == "P"]
        sc = pick(calls, lambda x: abs(x["delta"] - TARGET_DELTA))
        sp = pick(puts, lambda x: abs(abs(x["delta"]) - TARGET_DELTA))
        if not sc or not sp:
            continue
        print("=" * 72)
        print(f"DTE={dte}  expiry={sc['exp']}")
        print(f"  short call {sc['strike']:.0f} d={sc['delta']:+.3f} "
              f"bid={sc['bid']:.2f} ask={sc['ask']:.2f} iv={sc['iv']}")
        print(f"  short put  {sp['strike']:.0f} d={sp['delta']:+.3f} "
              f"bid={sp['bid']:.2f} ask={sp['ask']:.2f} iv={sp['iv']}")
        for w in WING_WIDTHS:
            lc = pick([x for x in calls if abs(x["strike"] - (sc["strike"] + w)) < 0.51],
                      lambda x: abs(x["strike"] - (sc["strike"] + w)))
            lp = pick([x for x in puts if abs(x["strike"] - (sp["strike"] - w)) < 0.51],
                      lambda x: abs(x["strike"] - (sp["strike"] - w)))
            if not lc or not lp:
                print(f"  wing ${w}: wing strike not quoted")
                continue
            # Credit at MID (theoretical) vs at NATURAL (sell bid, buy ask).
            cred_mid = (sc["mid"] + sp["mid"]) - (lc["mid"] + lp["mid"])
            cred_nat = (sc["bid"] + sp["bid"]) - (lc["ask"] + lp["ask"])
            slip_in = cred_mid - cred_nat          # cost of crossing on entry
            width = w
            maxloss_mid = width - cred_mid
            print(f"  wing ${w:<3}: credit_mid={cred_mid:6.2f}  credit_natural={cred_nat:6.2f}"
                  f"  entry_slippage={slip_in:5.2f} "
                  f"({100 * slip_in / cred_mid if cred_mid > 0 else float('nan'):5.1f}% of credit)")
            print(f"            max_loss={maxloss_mid:6.2f}  "
                  f"credit/width={100 * cred_mid / width:4.1f}%  "
                  f"wing quotes: C {lc['bid']:.2f}/{lc['ask']:.2f}  P {lp['bid']:.2f}/{lp['ask']:.2f}")
        print()


if __name__ == "__main__":
    main()
