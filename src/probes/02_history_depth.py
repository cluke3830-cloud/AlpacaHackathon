"""THROWAWAY PROBE 2 — real option-history depth + what fields we get.

Probe 1 was flawed: it asked a contract expiring 2026-08-25 for 2018 bars.
A contract only has bars over its own listed life, so that measured nothing.

Correct method: construct OCC symbols for SPY contracts that were near-the-money
AT past dates, and ask each for bars around its own expiry. Where the data
actually starts is where Alpaca's options history begins.

Also probes: historical QUOTES (bid/ask -> cost realism, Constitution bias #3)
and live SNAPSHOT (greeks/IV -> what the agent reasons over).
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from alpaca_keys import API_KEY, SECRET_KEY  # noqa: E402
K = K_API = API_KEY
S = S_API = SECRET_KEY
from datetime import datetime, timedelta



# (expiry, approx ATM strike for SPY at that time) — third Fridays
HIST = [
    ("2018-06-15", 275), ("2020-03-20", 250), ("2021-06-18", 425),
    ("2022-06-17", 380), ("2023-06-16", 440), ("2024-01-19", 475),
    ("2024-02-16", 500), ("2024-06-21", 540), ("2024-12-20", 600),
    ("2025-06-20", 600), ("2026-06-19", 700),
]


def occ(root, expiry_iso, cp, strike):
    y, m, d = expiry_iso.split("-")
    return f"{root}{y[2:]}{m}{d}{cp}{int(round(strike * 1000)):08d}"


def probe_bars():
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionBarsRequest
    from alpaca.data.timeframe import TimeFrame
    dc = OptionHistoricalDataClient(K, S)
    print(f"{'expiry':<12} {'occ symbol':<22} {'bars':>6}   window")
    print("-" * 70)
    for exp, strike in HIST:
        sym = occ("SPY", exp, "C", strike)
        e = datetime.fromisoformat(exp)
        start, end = e - timedelta(days=45), e - timedelta(days=1)
        try:
            df = dc.get_option_bars(OptionBarsRequest(
                symbol_or_symbols=sym, timeframe=TimeFrame.Day,
                start=start, end=end)).df
            n = 0 if df is None or df.empty else len(df)
            print(f"{exp:<12} {sym:<22} {n:>6}   {start:%Y-%m-%d}..{end:%Y-%m-%d}")
        except Exception as ex:
            print(f"{exp:<12} {sym:<22} {'ERR':>6}   {type(ex).__name__}: {str(ex)[:60]}")


def probe_quotes():
    """Bid/ask history = whether we can cost a spread honestly."""
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionQuotesRequest
    dc = OptionHistoricalDataClient(K, S)
    for exp, strike in [("2024-06-21", 540), ("2025-06-20", 600)]:
        sym = occ("SPY", exp, "C", strike)
        e = datetime.fromisoformat(exp)
        start = e - timedelta(days=30)
        try:
            q = dc.get_option_quotes(OptionQuotesRequest(
                symbol_or_symbols=sym, start=start,
                end=start + timedelta(days=1), limit=5))
            df = q.df
            if df is None or df.empty:
                print(f"  {sym}: 0 quotes")
            else:
                print(f"  {sym}: {len(df)} quotes; cols={list(df.columns)}")
                print(df.head(3).to_string()[:400])
        except Exception as ex:
            print(f"  {sym}: {type(ex).__name__}: {str(ex)[:150]}")


def probe_snapshot():
    """Live chain snapshot: does it carry greeks + IV (Layer 3's inputs)?"""
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionChainRequest
    dc = OptionHistoricalDataClient(K, S)
    try:
        chain = dc.get_option_chain(OptionChainRequest(underlying_symbol="SPY"))
        print(f"  chain entries: {len(chain)}")
        for i, (sym, snap) in enumerate(chain.items()):
            if i >= 3:
                break
            g = getattr(snap, "greeks", None)
            iv = getattr(snap, "implied_volatility", None)
            q = getattr(snap, "latest_quote", None)
            print(f"    {sym}: iv={iv} greeks={'YES' if g else 'None'} "
                  f"quote={'bid=%s ask=%s' % (q.bid_price, q.ask_price) if q else 'None'}")
            if g:
                print(f"       delta={g.delta} gamma={g.gamma} theta={g.theta} vega={g.vega}")
    except Exception as ex:
        print(f"  {type(ex).__name__}: {str(ex)[:200]}")


if __name__ == "__main__":
    print("=" * 70); print("A. OPTION BAR HISTORY — where does it actually start?"); print("=" * 70)
    probe_bars()
    print("\n" + "=" * 70); print("B. HISTORICAL QUOTES (bid/ask -> honest spread costing)"); print("=" * 70)
    probe_quotes()
    print("\n" + "=" * 70); print("C. LIVE CHAIN SNAPSHOT (greeks + IV for the agent)"); print("=" * 70)
    probe_snapshot()
