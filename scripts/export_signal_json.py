"""Export the agent's current market read to web/public/signal.json.

The MARKET tab shows the market AS THE AGENT SEES IT -- dealer gamma, the A+C
direction, the MSAR regime read, the trend veto -- not a generic quote screen.
That is the honest thing to display on a terminal for THIS strategy, and it is
the part a judge cannot get from any other dashboard.

Same "Python computes, JSON carries, browser draws" split as the backtest
export: the signal is defined once, in the code the agent actually trades.

Run:  python3 AlpacaHackathon/scripts/export_signal_json.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "agent"))
OUT = HERE.parent / "web" / "public" / "signal.json"


def main():
    import config as C
    import market
    import signal_live
    from scipy.stats import norm
    from us_bear_lab import R, Q, iv_vec

    sig = signal_live.todays_signal(verbose=True)

    # per-strike gamma profile, same filter the GEX aggregate uses
    S = sig["spot"]
    con = market.option_contracts(spot_px=S)
    snaps = market.snapshots(con["symbol"].tolist())
    df = con.merge(snaps, on="symbol", how="inner")
    df = df[(df["dte"].between(C.GEX_DTE_MIN, C.GEX_DTE_MAX)) & (df["oi"] > 0) & (df["mid"] > 0)].copy()
    Sv = df["underlyingPrice"].values.astype(float)
    K = df["strike"].values.astype(float)
    df = df[np.abs(np.log(K / Sv)) < C.GEX_MONEYNESS].copy()
    Sv = df["underlyingPrice"].values.astype(float)
    K = df["strike"].values.astype(float)
    T = df["dte"].values.astype(float) / 365.0
    cp = np.where(df["side"].values == "call", 1.0, -1.0)
    iv = iv_vec(df["mid"].values.astype(float), Sv, K, T, cp)
    d1 = (np.log(Sv / K) + (R - Q + 0.5 * iv ** 2) * T) / (iv * np.sqrt(T))
    gamma = np.exp(-Q * T) * norm.pdf(d1) / (Sv * iv * np.sqrt(T))
    dg = gamma * df["oi"].values * Sv ** 2 * 0.01
    df["gsigned"] = np.where(df["side"].values == "call", dg, -dg)
    prof = df.groupby("strike")["gsigned"].sum().sort_index()

    doc = dict(
        generated=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        underlying=C.UNDERLYING,
        spot=float(S),
        vix=float(sig["vix"]), vix_asof=sig["vix_asof"],
        gex=float(sig["gex"]),
        gex_sign=float(sig["gex_sign"]),
        oi_date=str(sig["gex_meta"]["oi_date"])[:10],
        n_contracts=int(sig["gex_meta"]["n_used"]),
        cross_check=bool(sig["gex_meta"]["agree"]),
        msar_long=bool(sig["msar_long"]),
        p_high=float(sig["p_high"]), p_slow=float(sig["p_slow"]),
        vol_era_threshold=0.5,
        trend_ok=float(sig["trend_ok"]),
        ret_t=float(sig["ret_t"]), mom20=float(sig["mom20"]),
        ac_dir=float(sig["ac_dir"]),
        gate=bool(sig["gate"]),
        sleeve1=("LONG CALL" if sig["gate"] else "FLAT"),
        sleeve2=("LONG CALL" if sig["ac_dir"] > 0 else "LONG PUT" if sig["ac_dir"] < 0 else "FLAT"),
        gamma_profile=[dict(strike=float(k), gex=float(v)) for k, v in prof.items()],
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc))
    print(f"\nwrote {OUT} ({OUT.stat().st_size/1024:.0f} KB, "
          f"{len(doc['gamma_profile'])} strikes)")


if __name__ == "__main__":
    main()
