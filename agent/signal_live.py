"""Today's two sleeve directions, computed live from Alpaca + VIX.

The decision functions themselves are IMPORTED from the certified modules
(or_smh_signal.ac_net_direction, t2_qld_signal.t2_gate) rather than reimplemented
here. A live agent that re-types its own signal logic is a live agent that will
eventually disagree with its own backtest -- so the only thing this file does is
assemble inputs and hand them to code that is already golden-tested.

DEALER GAMMA is rebuilt with the exact formula in us_bear_lab.build_us_gex:
near-the-money (|log K/S| < 0.20) contracts at 1-8 DTE, IV inverted from the
mid, gamma * OI * S^2 * 0.01, calls positive and puts negative. Any deviation
here is a deviation from the thing that was validated.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mandatory_tests_for_deployment_2"))
sys.path.insert(0, str(ROOT / "KoreanStatArb" / "scripts"))
sys.path.append(str(Path(__file__).resolve().parents[1] / "vendor"))  # standalone fallback

import config as C                                      # noqa: E402
import market                                           # noqa: E402
import or_smh_signal as sigmod                          # noqa: E402
import t2_qld_signal as t2                              # noqa: E402
from us_bear_lab import R, Q, iv_vec                    # noqa: E402


def dealer_gex(contracts: pd.DataFrame, snaps: pd.DataFrame) -> dict:
    """Signed dealer gamma exposure, us_bear_lab.build_us_gex formula verbatim."""
    df = contracts.merge(snaps, on="symbol", how="inner")
    n_all = len(df)
    df = df[(df["dte"].between(C.GEX_DTE_MIN, C.GEX_DTE_MAX)) &
            (df["oi"] > 0) & (df["mid"] > 0)].copy()
    S = df["underlyingPrice"].values.astype(float)
    K = df["strike"].values.astype(float)
    df = df[np.abs(np.log(K / S)) < C.GEX_MONEYNESS].copy()
    if len(df) < C.MIN_GEX_CONTRACTS:
        raise RuntimeError(
            f"only {len(df)} contracts survived the GEX filter (floor is "
            f"{C.MIN_GEX_CONTRACTS}, fetched {n_all}) -- a dealer-gamma number "
            f"built from a handful of strikes is noise wearing a signal's "
            f"clothes. Refusing to trade.")

    S = df["underlyingPrice"].values.astype(float)
    K = df["strike"].values.astype(float)
    T = df["dte"].values.astype(float) / 365.0
    cp = np.where(df["side"].values == "call", 1.0, -1.0)
    iv = iv_vec(df["mid"].values.astype(float), S, K, T, cp)
    sq = iv * np.sqrt(T)
    d1 = (np.log(S / K) + (R - Q + 0.5 * iv ** 2) * T) / sq
    gamma = np.exp(-Q * T) * norm.pdf(d1) / (S * iv * np.sqrt(T))
    dg = gamma * df["oi"].values * S ** 2 * 0.01
    gsigned = np.where(df["side"].values == "call", dg, -dg)
    gex = float(np.nansum(gsigned))

    # cross-check against Alpaca's own gamma. Not used for the decision -- it is
    # a tripwire: a large disagreement means one of the two is wrong and the
    # agent should not be trading on either.
    alt = np.nan
    m = df["gamma_alpaca"].notna().values
    if m.sum() > 20:
        dga = df["gamma_alpaca"].values[m] * df["oi"].values[m] * S[m] ** 2 * 0.01
        alt = float(np.nansum(np.where(df["side"].values[m] == "call", dga, -dga)))

    oi_dates = pd.to_datetime(pd.Series(df["oi_date"].dropna().unique()))
    return dict(gex=gex, gex_alpaca=alt, n_used=len(df), n_fetched=n_all,
                oi_date=oi_dates.max() if len(oi_dates) else None,
                agree=bool(np.isnan(alt) or np.sign(alt) == np.sign(gex)))


def todays_signal(verbose: bool = True) -> dict:
    """Everything the book needs for one decision, plus the evidence behind it."""
    S = market.spot()
    contracts = market.option_contracts(spot_px=S)
    if contracts.empty:
        raise RuntimeError("Alpaca returned no contracts in the GEX window")
    snaps = market.snapshots(contracts["symbol"].tolist())
    g = dealer_gex(contracts, snaps)

    vix = market.vix_history()
    qqq = market.qqq_history()
    und = market.underlying_history()

    stale = (und.index[-1] - vix.index[-1]).days
    if stale > C.MAX_VIX_STALENESS_DAYS:
        raise RuntimeError(
            f"VIX is {stale}d behind the price feed (VIX {vix.index[-1].date()}, "
            f"price {und.index[-1].date()}). The MSAR regime signal would be "
            f"frozen. Refusing to trade on a stale regime.")

    p_high = pd.Series(sigmod.msar_filtered_p_high(vix.values.tolist()), index=vix.index)
    msar_pos = pd.Series(sigmod.msar_positions(vix.values.tolist()), index=vix.index)
    p_slow = t2.p_slow_series(p_high)
    trend = t2.trend_ok_series(und)

    ret_q = np.log(qqq / qqq.shift(1))
    ret_t = float(ret_q.iloc[-1])
    mom20 = float(ret_q.rolling(20).sum().iloc[-1])

    gex_sign = float(np.sign(-g["gex"]))            # retail inversion, as deployed
    ac_dir = sigmod.ac_net_direction(gex_sign, ret_t, mom20)
    msar_long = bool(msar_pos.iloc[-1] > 0)
    p_slow_now = float(p_slow.iloc[-1])
    trend_ok = float(trend.iloc[-1])
    gate = bool(t2.t2_gate(msar_long, ac_dir, p_slow_now, trend_ok))

    out = dict(spot=S, gex=g["gex"], gex_sign=gex_sign, gex_meta=g,
               ret_t=ret_t, mom20=mom20, ac_dir=float(ac_dir),
               msar_long=msar_long, p_high=float(p_high.iloc[-1]),
               p_slow=p_slow_now, trend_ok=trend_ok, gate=gate,
               vix=float(vix.iloc[-1]), vix_asof=str(vix.index[-1].date()),
               und_asof=str(und.index[-1].date()),
               sleeve1_dir=1.0 if gate else 0.0, sleeve2_dir=float(ac_dir))

    if verbose:
        print(f"  spot {C.UNDERLYING} ${S:,.2f}   VIX {out['vix']:.2f} "
              f"(as of {out['vix_asof']})")
        print(f"  dealer GEX  {g['gex']/1e9:+.3f} $bn from {g['n_used']} contracts"
              f"   OI as of {str(g['oi_date'])[:10]}"
              f"   alpaca-gamma cross-check {'AGREES' if g['agree'] else '*** DISAGREES ***'}")
        print(f"  MSAR p_high {out['p_high']:.3f}  p_slow {out['p_slow']:.3f} "
              f"(vol-era if >= {t2.VOL_ERA_P})   msar_long={msar_long}")
        print(f"  QQQ ret_t {ret_t:+.4f}  mom20 {mom20:+.4f}  ->  A+C dir {ac_dir:+.0f}")
        print(f"  trend_ok {trend_ok:.0f} (200d MA veto)")
        print(f"  SLEEVE 1 (T2 gate)      -> {'LONG CALL' if gate else 'FLAT'}")
        print(f"  SLEEVE 2 (gamma A+C)    -> "
              f"{'LONG CALL' if ac_dir > 0 else ('LONG PUT' if ac_dir < 0 else 'FLAT')}")
    return out


if __name__ == "__main__":
    import json
    s = todays_signal()
    print("\n" + json.dumps({k: v for k, v in s.items() if k != "gex_meta"},
                            indent=2, default=str))
