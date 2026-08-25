"""THROWAWAY PROBE — what does the Alpaca stack actually serve?

Read-only. No orders. Answers three questions that decide the test design:
  1. Do the old paper keys still authenticate?
  2. How far back does Alpaca option history go? (drives regime-window validation)
  3. Is VIX reachable through Alpaca at all? (MSAR's only input is log(VIX))
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from alpaca_keys import API_KEY, SECRET_KEY  # noqa: E402
K = K_API = API_KEY
S = S_API = SECRET_KEY
import sys
from datetime import datetime, timedelta

KEYS = [("env", API_KEY, SECRET_KEY)]


def probe_auth():
    from alpaca.trading.client import TradingClient
    live = []
    for name, k, s in KEYS:
        try:
            acct = TradingClient(k, s, paper=True).get_account()
            print(f"  [OK]   {name}: status={acct.status} "
                  f"equity=${acct.equity} buying_power=${acct.buying_power} "
                  f"options_level={getattr(acct, 'options_trading_level', 'n/a')}")
            live.append((name, k, s))
        except Exception as e:
            print(f"  [DEAD] {name}: {type(e).__name__}: {str(e)[:120]}")
    return live


def probe_option_history(k, s):
    """Walk backwards year by year: where does option bar data stop existing?"""
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetOptionContractsRequest

    tc = TradingClient(k, s, paper=True)
    # Grab a real, currently-listed SPY contract to use as a probe symbol.
    try:
        res = tc.get_option_contracts(
            GetOptionContractsRequest(underlying_symbols=["SPY"], limit=5))
        contracts = res.option_contracts or []
        print(f"  live SPY contracts returned: {len(contracts)}")
        for c in contracts[:3]:
            print(f"    {c.symbol}  strike={c.strike_price} exp={c.expiration_date} "
                  f"type={c.type} oi={getattr(c, 'open_interest', None)}")
    except Exception as e:
        print(f"  [contract lookup FAILED] {type(e).__name__}: {str(e)[:200]}")
        contracts = []

    if not contracts:
        return
    sym = contracts[0].symbol
    dc = OptionHistoricalDataClient(k, s)
    print(f"\n  --- how far back do bars exist for {sym}? ---")
    for years_ago in (0, 1, 2, 3, 5, 8):
        end = datetime.now() - timedelta(days=365 * years_ago)
        start = end - timedelta(days=30)
        try:
            bars = dc.get_option_bars(OptionBarsRequest(
                symbol_or_symbols=sym, timeframe=TimeFrame.Day,
                start=start, end=end))
            df = bars.df
            n = 0 if df is None or df.empty else len(df)
            print(f"    {start:%Y-%m-%d}..{end:%Y-%m-%d}: {n} daily bars")
        except Exception as e:
            print(f"    {start:%Y-%m-%d}..{end:%Y-%m-%d}: "
                  f"{type(e).__name__}: {str(e)[:110]}")


def probe_vix(k, s):
    """MSAR eats log(VIX). Alpaca is an equities/options broker - is VIX there?"""
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    dc = StockHistoricalDataClient(k, s)
    end = datetime.now() - timedelta(days=2)
    start = end - timedelta(days=10)
    for sym in ("VIX", "^VIX", "$VIX", "VIXY", "VXX", "UVXY", "SPY"):
        try:
            df = dc.get_stock_bars(StockBarsRequest(
                symbol_or_symbols=sym, timeframe=TimeFrame.Day,
                start=start, end=end)).df
            n = 0 if df is None or df.empty else len(df)
            last = "" if not n else f" last_close={df['close'].iloc[-1]:.2f}"
            print(f"    {sym:6s}: {n} bars{last}")
        except Exception as e:
            print(f"    {sym:6s}: {type(e).__name__}: {str(e)[:90]}")


if __name__ == "__main__":
    print("=" * 70)
    print("1. AUTH")
    print("=" * 70)
    live = probe_auth()
    if not live:
        print("\nNo working keys -> need fresh ones from TC before probing data.")
        sys.exit(0)
    name, k, s = live[0]
    print(f"\n(using {name} for data probes)")
    print("\n" + "=" * 70)
    print("2. OPTION HISTORY DEPTH")
    print("=" * 70)
    probe_option_history(k, s)
    print("\n" + "=" * 70)
    print("3. VIX REACHABILITY (MSAR's only input)")
    print("=" * 70)
    probe_vix(k, s)
