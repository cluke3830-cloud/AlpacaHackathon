"""THROWAWAY PROBE 3 — pin the history start date, and see what live data carries.

alpaca-py 0.43.2 exposes NO historical option quote endpoint (bars/trades only;
quotes+snapshot+chain are live-only). So this checks:
  A. exactly when option bar history begins  -> how much validation window exists
  B. what historical TRADES carry            -> can we infer spread for costing?
  C. what the live chain snapshot carries    -> greeks/IV for the agent + live spread
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from alpaca_keys import API_KEY, SECRET_KEY  # noqa: E402
K = K_API = API_KEY
S = S_API = SECRET_KEY
from datetime import datetime, timedelta



def occ(root, expiry_iso, cp, strike):
    y, m, d = expiry_iso.split("-")
    return f"{root}{y[2:]}{m}{d}{cp}{int(round(strike * 1000)):08d}"


def probe_start():
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionBarsRequest
    from alpaca.data.timeframe import TimeFrame
    dc = OptionHistoricalDataClient(K, S)
    sym = occ("SPY", "2024-02-16", "C", 500)
    df = dc.get_option_bars(OptionBarsRequest(
        symbol_or_symbols=sym, timeframe=TimeFrame.Day,
        start=datetime(2023, 11, 1), end=datetime(2024, 2, 15))).df
    if df is None or df.empty:
        print("  no bars")
        return
    idx = df.index.get_level_values(-1)
    print(f"  {sym}: {len(df)} bars, FIRST={idx.min()}  LAST={idx.max()}")
    print(f"  columns: {list(df.columns)}")
    print(df.head(3).to_string()[:500])


def probe_trades():
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionTradesRequest
    dc = OptionHistoricalDataClient(K, S)
    sym = occ("SPY", "2024-06-21", "C", 540)
    try:
        df = dc.get_option_trades(OptionTradesRequest(
            symbol_or_symbols=sym, start=datetime(2024, 5, 20),
            end=datetime(2024, 5, 21), limit=8)).df
        if df is None or df.empty:
            print("  0 trades")
        else:
            print(f"  {len(df)} trades; cols={list(df.columns)}")
            print(df.head(5).to_string()[:500])
    except Exception as e:
        print(f"  {type(e).__name__}: {str(e)[:180]}")


def probe_chain():
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionChainRequest
    dc = OptionHistoricalDataClient(K, S)
    try:
        chain = dc.get_option_chain(OptionChainRequest(underlying_symbol="SPY"))
        print(f"  chain entries: {len(chain)}")
        shown = 0
        wides = []
        for sym, snap in chain.items():
            g = getattr(snap, "greeks", None)
            iv = getattr(snap, "implied_volatility", None)
            q = getattr(snap, "latest_quote", None)
            if q and q.bid_price and q.ask_price:
                mid = (q.bid_price + q.ask_price) / 2
                if mid > 0:
                    wides.append((q.ask_price - q.bid_price) / mid)
            if shown < 3 and g:
                print(f"    {sym}: iv={iv}")
                print(f"       delta={g.delta} gamma={g.gamma} theta={g.theta} vega={g.vega}")
                if q:
                    print(f"       bid={q.bid_price} ask={q.ask_price}")
                shown += 1
        if wides:
            wides.sort()
            n = len(wides)
            print(f"\n  live relative spread (ask-bid)/mid over {n} quoted contracts:")
            print(f"    median={wides[n//2]:.3f}  p25={wides[n//4]:.3f}  p75={wides[3*n//4]:.3f}")
        n_greeks = sum(1 for _, s in chain.items() if getattr(s, "greeks", None))
        print(f"  contracts carrying greeks: {n_greeks}/{len(chain)}")
    except Exception as e:
        print(f"  {type(e).__name__}: {str(e)[:250]}")


if __name__ == "__main__":
    print("=" * 70); print("A. WHERE OPTION HISTORY BEGINS"); print("=" * 70)
    probe_start()
    print("\n" + "=" * 70); print("B. HISTORICAL TRADES"); print("=" * 70)
    probe_trades()
    print("\n" + "=" * 70); print("C. LIVE CHAIN: greeks/IV/spread"); print("=" * 70)
    probe_chain()
