"""Export the MARKET tab's data: VIX family + the S&P volatility surface.

TWO THINGS ALPACA CANNOT GIVE US, hence this exporter:

1. THE VIX FAMILY (VIX / VIX3M / VIX9D). `^VIX` is not an Alpaca symbol, and
   VIXY/VXX are decaying roll ETFs whose LEVEL is not a volatility reading --
   substituting one is the RV-for-IV anti-pattern this fund has a standing rule
   against. OptionDashboard gets these from its IBKR relay; here they come from
   CBOE's own public daily archive -- free, no key, no entitlement gate, and
   the primary source the data vendors resell. (FinanceDataReader was the first
   choice and was REJECTED after testing: it and yfinance both now return a
   single day for ^VIX3M/^VIX9D, which would have drawn a flat line that looks
   like data.)

2. THE VOLATILITY SURFACE across many names. Port of
   Past Strategies/Alpaca/Volatility_Surface.py -- rolling realized vol per
   symbol, rendered as a 3D surface (symbol x time x vol%). That script used a
   15-name tech basket on 1-minute bars; this uses a broader S&P 500 mega-cap
   cross-section on daily bars, because the panel sits on a terminal that is
   read across weeks rather than watched intraday, and daily bars are what the
   free Alpaca IEX feed serves reliably.

Everything is precomputed here and drawn in the browser -- same split as the
backtest and signal exporters.

Run:  python3 AlpacaHackathon/scripts/export_market_json.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "agent"))
OUT = HERE.parent / "web" / "public" / "market.json"

# VIX complex. VIX9D = 9-day (front), VIX = 30-day, VIX3M = 93-day.
# The term structure panel needs all three to show backwardation.
VIX_SYMBOLS = ["VIX", "VIX3M", "VIX9D"]   # CBOE archive file names

# S&P 500 cross-section for the surface. Deliberately spans SECTORS, not just
# mega-cap tech: a vol surface built only from correlated tech names shows one
# ridge moving together and teaches nothing. Sector spread is what makes the
# dispersion visible.
SURFACE_BASKET = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA",   # tech/comm
    "JPM", "BAC", "GS",                                                # financials
    "UNH", "LLY", "JNJ",                                               # healthcare
    "XOM", "CVX",                                                      # energy
    "WMT", "COST", "HD",                                               # consumer
    "CAT", "BA",                                                       # industrials
]
SURFACE_DAYS = 120        # trailing window shown on the time axis
VOL_WINDOW = 10           # rolling stdev window, matching Volatility_Surface.py
HISTORY_DAYS = 3000       # ~8 trading years, matching the dashboard's 8Y lookback


def fetch_vix() -> dict:
    """VIX / VIX3M / VIX9D daily closes, straight from CBOE's public archive.

    NOT FinanceDataReader or yfinance: both now return only a SINGLE day for
    ^VIX3M and ^VIX9D (Yahoo dropped history for those indices; ^VIX itself
    still works). Verified empirically before switching -- a term-structure
    panel fed one point per series would have rendered a flat line that looks
    like data. CBOE publishes the full history as a free CSV (VIX to 1990,
    VIX3M to 2009, VIX9D to 2011) with no key and no entitlement gate, which is
    also the primary source those vendors were reselling."""
    import csv
    import io
    import urllib.request

    out = {}
    for name in VIX_SYMBOLS:
        url = f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{name}_History.csv"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                rows = list(csv.reader(io.StringIO(r.read().decode())))
            idx, vals = [], []
            for row in rows[1:]:
                if len(row) < 5:
                    continue
                try:
                    idx.append(pd.Timestamp(row[0]))
                    vals.append(float(row[4]))          # CLOSE
                except (ValueError, TypeError):
                    continue                            # header variants / blank rows
            s = pd.Series(vals, index=pd.DatetimeIndex(idx)).sort_index()
            s = s[~s.index.duplicated(keep="last")]
            cutoff = pd.Timestamp.today().normalize() - pd.Timedelta(days=int(HISTORY_DAYS * 1.5))
            s = s[s.index >= cutoff]
            out[name] = s
            print(f"  {name:<6} {len(s):>5}d  {s.index.min().date()} -> {s.index.max().date()}"
                  f"  last {s.iloc[-1]:.2f}")
        except Exception as e:                                    # noqa: BLE001
            print(f"  {name:<6} FAILED: {e}")
            out[name] = pd.Series(dtype=float)

    short = [k for k, v in out.items() if len(v) < 250]
    if short:
        raise RuntimeError(
            f"VIX series too short to be real: {short}. A term-structure panel "
            f"built on this would render a flat line that looks like data. "
            f"Fix the source rather than shipping it.")
    return out


def fetch_spy_daily() -> pd.DataFrame:
    """SPY OHLC from Alpaca -- the chart itself stays on the sponsor's data."""
    import market as agent_market
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=int(HISTORY_DAYS * 1.5))
    bars = agent_market._stock.get_stock_bars(StockBarsRequest(
        symbol_or_symbols="SPY", timeframe=TimeFrame.Day, start=start, feed="iex")).df
    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs("SPY", level=0)
    bars.index = pd.to_datetime(bars.index).tz_localize(None).normalize()
    print(f"  SPY    {len(bars):>5}d  {bars.index.min().date()} -> {bars.index.max().date()}")
    return bars


def build_surface() -> dict:
    """Rolling realized vol per symbol -> the 3D surface grid.

    Volatility_Surface.py's formula kept verbatim: rolling stdev of log returns,
    expressed in percent. Only the bar size and universe differ, both stated in
    the module docstring."""
    import market as agent_market
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=int(SURFACE_DAYS * 2.2))
    df = agent_market._stock.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=SURFACE_BASKET, timeframe=TimeFrame.Day,
        start=start, feed="iex")).df
    if df is None or df.empty:
        raise RuntimeError("no bars returned for the surface basket")

    px = df.reset_index().pivot_table(
        index="timestamp", columns="symbol", values="close", aggfunc="last")
    px.index = pd.to_datetime(px.index).tz_localize(None).normalize()

    # Drop names the feed could not fill; a column of forward-filled constants
    # would render as a fake zero-vol trench across the surface.
    keep = [c for c in px.columns if px[c].notna().mean() > 0.9]
    dropped = sorted(set(px.columns) - set(keep))
    px = px[keep].ffill()

    logret = np.log(px / px.shift(1))
    vol = logret.rolling(VOL_WINDOW).std() * np.sqrt(252) * 100     # annualized %
    vol = vol.dropna(how="all").tail(SURFACE_DAYS)

    # Order symbols by current vol so the surface reads as a ranked ridge rather
    # than alphabetical noise.
    order = vol.iloc[-1].sort_values().index.tolist()
    vol = vol[order]

    print(f"  surface {vol.shape[0]}d x {vol.shape[1]} symbols"
          + (f"  (dropped sparse: {', '.join(dropped)})" if dropped else ""))
    return dict(
        symbols=order,
        dates=[d.strftime("%Y-%m-%d") for d in vol.index],
        z=[[None if not np.isfinite(v) else round(float(v), 3) for v in row]
           for row in vol.values],
        window=VOL_WINDOW,
        current={s: round(float(vol[s].iloc[-1]), 2) for s in order},
    )


def build_option_timing() -> dict:
    """OUR AGENT's historical trading timing, for the SPY chart's marker rows.

    Same construction the audit stack validated (SPX dealer gamma at gex_lag=1,
    the shipping-honest config), reusing gex_source_check.signals_from_gex
    rather than re-deriving the gate here -- a hand-rolled copy is exactly how a
    chart ends up showing a signal the agent doesn't actually trade.

      calls_on  / calls_off : sleeve-1 T2 gate opens (buy deep-ITM calls) / closes
      puts_on   / puts_off  : sleeve-2 A+C direction enters / leaves bearish

    Coverage note carried into the JSON: the chain history ends 2026-06-12, so
    markers stop there. The LIVE read continues in the signal strip above the
    chart (signal.json, recomputed from Alpaca each run) -- stated in the UI
    caption rather than letting the marker gap look like the agent went quiet."""
    sys.path.insert(0, str(HERE.parents[1] / "Researched_Concepts" / "CrossSectionalArb" / "src"))
    from gex_source_check import gex_from, signals_from_gex, GEX_DATA

    g = pd.concat([gex_from(GEX_DATA / "chains_SPX_pre2022.parquet"),
                   gex_from(GEX_DATA / "chains_SPX.parquet")]).groupby(level=0).sum()
    sig = signals_from_gex(g, "SPX", 1)
    gate, ac = sig["gate"], sig["ac_dir"]

    day = lambda ix: [d.strftime("%Y-%m-%d") for d in ix]
    timing = dict(
        calls_on=day(gate[gate.diff() == 1].index),
        calls_off=day(gate[gate.diff() == -1].index),
        puts_on=day(ac[(ac == -1) & (ac.shift() != -1)].index),
        puts_off=day(ac[(ac != -1) & (ac.shift() == -1)].index),
        coverage_start=str(sig.index.min().date()),
        coverage_end=str(sig.index.max().date()),
        config="SPX dealer-gamma, gex_lag=1 (shipping-honest), T2 gate + A+C",
    )
    print(f"  option timing: {len(timing['calls_on'])} call entries, "
          f"{len(timing['puts_on'])} put entries, through {timing['coverage_end']}")
    return timing


def main():
    print("=== VIX family (FinanceDataReader) ===")
    vix = fetch_vix()
    print("=== SPY daily (Alpaca) ===")
    spy = fetch_spy_daily()
    print("=== S&P volatility surface (Alpaca) ===")
    surface = build_surface()
    print("=== option trading timing (our agent, historical) ===")
    timing = build_option_timing()

    # `t` is EPOCH SECONDS, not an ISO string. The market tab's components are
    # copied verbatim from OptionDashboard, whose Bar type is {t:number,...} and
    # whose isoDay()/monthlyTicks() helpers do their own UTC formatting. Emitting
    # the shape they already expect is cheaper and less error-prone than
    # converting in three places in the browser.
    def epoch(d) -> int:
        return int(pd.Timestamp(d).tz_localize("UTC").timestamp())

    def ser(s: pd.Series) -> list:
        return [dict(t=epoch(d), c=round(float(v), 4)) for d, v in s.items()]

    doc = dict(
        generated=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        spy=[dict(t=epoch(d), o=round(float(r.open), 4),
                  h=round(float(r.high), 4), l=round(float(r.low), 4),
                  c=round(float(r.close), 4), v=float(r.volume))
             for d, r in spy.iterrows()],
        vix=ser(vix["VIX"]), vix3m=ser(vix["VIX3M"]), vix9d=ser(vix["VIX9D"]),
        surface=surface,
        option_timing=timing,
        sources=dict(
            spy="Alpaca IEX daily",
            vix="CBOE public daily archive — not available on Alpaca",
            surface=f"Alpaca IEX daily, {len(surface['symbols'])} S&P names, "
                    f"{VOL_WINDOW}d rolling realized vol annualized",
        ),
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc))
    print(f"\nwrote {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")
    print(f"  spy {len(doc['spy'])}d · vix {len(doc['vix'])}d · "
          f"vix3m {len(doc['vix3m'])}d · vix9d {len(doc['vix9d'])}d")


if __name__ == "__main__":
    main()
