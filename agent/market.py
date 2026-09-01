"""All outside-world reads: Alpaca (chain, OI, quotes, account) and VIX.

Deliberately the ONLY module that talks to a network. Everything downstream
takes plain dataframes, so the whole signal path can be replayed offline against
the research data and is testable without a broker connection.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(ROOT / "mandatory_tests_for_deployment_2"))
sys.path.insert(0, str(ROOT / "U.S._gamma_strategy" / "Reflexive_0DTE_Research"))
# vendor/ is APPENDED (not inserted) so it is a FALLBACK: inside the monorepo
# the live research modules above win; a standalone clone (the production
# runner outside iCloud, or a judge's checkout) resolves here instead.
sys.path.append(str(Path(__file__).resolve().parents[1] / "vendor"))

from alpaca_keys import API_KEY, SECRET_KEY          # noqa: E402
from alpaca.trading.client import TradingClient       # noqa: E402
from alpaca.trading.requests import GetOptionContractsRequest   # noqa: E402
from alpaca.data.historical.option import OptionHistoricalDataClient  # noqa: E402
from alpaca.data.historical.stock import StockHistoricalDataClient    # noqa: E402
from alpaca.data.requests import (OptionSnapshotRequest,              # noqa: E402
                                  StockBarsRequest, StockLatestQuoteRequest)
from alpaca.data.timeframe import TimeFrame           # noqa: E402

import config as C                                    # noqa: E402

_trading = TradingClient(API_KEY, SECRET_KEY, paper=True)
_opt = OptionHistoricalDataClient(API_KEY, SECRET_KEY)
_stock = StockHistoricalDataClient(API_KEY, SECRET_KEY)


# ---------------------------------------------------------------------------
def account() -> dict:
    a = _trading.get_account()
    return dict(number=a.account_number, equity=float(a.equity), cash=float(a.cash),
                options_bp=float(getattr(a, "options_buying_power", 0) or 0),
                status=str(a.status))


def positions() -> dict:
    """symbol -> dict(qty, avg_entry, market_value, unrealized_pl)."""
    out = {}
    for p in _trading.get_all_positions():
        out[p.symbol] = dict(qty=int(float(p.qty)), avg_entry=float(p.avg_entry_price),
                             market_value=float(p.market_value),
                             unrealized_pl=float(p.unrealized_pl))
    return out


def spot(symbol: str = None) -> float:
    symbol = symbol or C.UNDERLYING
    q = _stock.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=symbol))[symbol]
    bid, ask = float(q.bid_price or 0), float(q.ask_price or 0)
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    bars = _stock.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=symbol, timeframe=TimeFrame.Day,
        start=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7))).df
    return float(bars["close"].iloc[-1])


def underlying_history(symbol: str = None, days: int = 900) -> pd.Series:
    """Daily closes for the 200d trend veto and 20d momentum. Alpaca-native so
    the agent has one price source, not two that can silently disagree."""
    symbol = symbol or C.UNDERLYING
    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=int(days * 1.6))
    bars = _stock.get_stock_bars(StockBarsRequest(
        symbol_or_symbols=symbol, timeframe=TimeFrame.Day, start=start)).df
    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs(symbol, level=0)
    s = bars["close"].copy()
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    return s.sort_index()


def qqq_history(days: int = 400) -> pd.Series:
    """QQQ closes -- the A+C signal reads QQQ's own return and 20d momentum,
    exactly as the certified gamma sleeve does. Kept as QQQ (not the traded
    underlying) because that is what was validated; swapping it is a new test."""
    return underlying_history("QQQ", days)


def vix_history(days: int = 900) -> pd.Series:
    """VIX closes for the MSAR filter.

    NOT available on Alpaca (^VIX is an invalid symbol there, and VIXY/VXX are
    decaying roll ETFs -- substituting one would repeat the RV-for-IV
    anti-pattern this fund has an explicit rule against). So VIX is the one
    input that must come from outside Alpaca."""
    import FinanceDataReader as fdr
    start = (dt.date.today() - dt.timedelta(days=int(days * 1.6))).isoformat()
    v = fdr.DataReader("^VIX", start)["Close"]
    v.index = pd.to_datetime(v.index).normalize()
    return v.dropna().sort_index()


# ---------------------------------------------------------------------------
def option_contracts(underlying: str = None, dte_min: int = None, dte_max: int = None,
                     moneyness: float = None, spot_px: float = None) -> pd.DataFrame:
    """Listed contracts with OPEN INTEREST, filtered to the GEX window.

    open_interest_date is the prior session -- see config.GEX_LAG_SESSIONS."""
    underlying = underlying or C.UNDERLYING
    dte_min = C.GEX_DTE_MIN if dte_min is None else dte_min
    dte_max = C.GEX_DTE_MAX if dte_max is None else dte_max
    moneyness = C.GEX_MONEYNESS if moneyness is None else moneyness
    S = spot_px or spot(underlying)
    today = dt.date.today()

    req = GetOptionContractsRequest(
        underlying_symbols=[underlying],
        expiration_date_gte=today + dt.timedelta(days=dte_min),
        expiration_date_lte=today + dt.timedelta(days=dte_max),
        strike_price_gte=str(round(S * np.exp(-moneyness), 2)),
        strike_price_lte=str(round(S * np.exp(moneyness), 2)),
        limit=10000)
    rows, token = [], None
    while True:
        req.page_token = token
        resp = _trading.get_option_contracts(req)
        for c in resp.option_contracts:
            rows.append(dict(symbol=c.symbol, side="call" if str(c.type).endswith("CALL") else "put",
                             strike=float(c.strike_price),
                             expiration=pd.Timestamp(c.expiration_date),
                             oi=float(c.open_interest) if c.open_interest else np.nan,
                             oi_date=c.open_interest_date, tradable=bool(c.tradable)))
        token = getattr(resp, "next_page_token", None)
        if not token:
            break
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["dte"] = (df["expiration"].dt.date - today).map(lambda x: x.days)
    df["underlyingPrice"] = S
    return df


def snapshots(symbols: list[str], chunk: int = 100) -> pd.DataFrame:
    """Live NBBO + Alpaca greeks/IV for a set of option symbols.

    chunk=100 is Alpaca's hard per-request symbol limit, not a tuning choice.
    Discovered the expensive way: at 400 every request failed, and because the
    failure was only WARNED about, the agent happily computed dealer gamma from
    the single contract that survived and printed a confident signal. A partial
    fetch is not a smaller fetch, it is a WRONG one -- so failures are counted
    and raised, never shrugged off."""
    rows, failed = [], 0
    for i in range(0, len(symbols), chunk):
        part = symbols[i:i + chunk]
        try:
            snap = _opt.get_option_snapshot(OptionSnapshotRequest(symbol_or_symbols=part))
        except Exception as e:                                     # noqa: BLE001
            failed += 1
            print(f"  [warn] snapshot chunk failed ({len(part)} syms): {e}")
            continue
        for sym, s in snap.items():
            q = getattr(s, "latest_quote", None)
            g = getattr(s, "greeks", None)
            rows.append(dict(
                symbol=sym,
                bid=float(q.bid_price) if q and q.bid_price else np.nan,
                ask=float(q.ask_price) if q and q.ask_price else np.nan,
                bid_size=float(q.bid_size) if q and q.bid_size else np.nan,
                ask_size=float(q.ask_size) if q and q.ask_size else np.nan,
                iv_alpaca=float(s.implied_volatility) if getattr(s, "implied_volatility", None) else np.nan,
                delta_alpaca=float(g.delta) if g and g.delta is not None else np.nan,
                gamma_alpaca=float(g.gamma) if g and g.gamma is not None else np.nan))
    n_chunks = max(1, (len(symbols) + chunk - 1) // chunk)
    if failed:
        raise RuntimeError(
            f"{failed}/{n_chunks} snapshot chunks failed -- refusing to build a "
            f"signal from a partial chain. Fix the fetch, do not trade around it.")
    df = pd.DataFrame(rows)
    if not df.empty:
        df["mid"] = (df["bid"] + df["ask"]) / 2.0
        df["spread_frac"] = (df["ask"] - df["bid"]) / df["mid"].replace(0, np.nan)
    return df


def market_open_now() -> tuple[bool, str]:
    """Live exchange-calendar gate. A cron timer has no holiday awareness on its
    own -- the constitution requires the calendar check, not the timer."""
    try:
        import exchange_calendars as xcals
        cal = xcals.get_calendar(C.CALENDAR)
        now = pd.Timestamp.now(tz="UTC")
        if not cal.is_session(now.tz_convert("America/New_York").normalize().tz_localize(None)):
            return False, "not an exchange session (holiday/weekend)"
        close = cal.session_close(now.tz_convert("America/New_York").normalize().tz_localize(None))
        if now >= close:
            return False, f"session already closed at {close}"
        return True, f"session open, close {close}"
    except Exception as e:                                          # noqa: BLE001
        clock = _trading.get_clock()
        return bool(clock.is_open), f"exchange_calendars unavailable ({e}); Alpaca clock says open={clock.is_open}"


def get_order(order_id: str):
    return _trading.get_order_by_id(order_id)


def cancel_order(order_id: str):
    try:
        _trading.cancel_order_by_id(order_id)
        return True
    except Exception as e:                                          # noqa: BLE001
        print(f"    [warn] cancel {order_id} failed: {e}")
        return False


def submit_limit(symbol: str, qty: int, side: str, limit_price: float):
    from alpaca.trading.requests import LimitOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    req = LimitOrderRequest(
        symbol=symbol, qty=qty,
        side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY,          # options are DAY-only on Alpaca
        limit_price=round(float(limit_price), 2))
    return _trading.submit_order(req)
