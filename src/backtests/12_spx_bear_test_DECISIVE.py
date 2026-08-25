"""THE BEAR TEST — does the MSAR+trend gate actually stand down when it must?

This is the one thing Alpaca's 2.6 years cannot answer, and it is the load-bearing
component of the whole design: on real Alpaca prices the structure makes ~+0.24/trade
in calm regimes and ~-0.23/trade at a 2022-like tail. Everything rests on the gate
being flat in the bad regimes.

Data: our own chains_SPX{,_pre2022}.parquet - 2018-01-02..2026-06-12, REAL bid/ask,
5-9 DTE, covering Fed-Pivot-2018, COVID-2020, Tech-Bear-2022, SVB-2023. That satisfies
the Constitution's bias #5 sample requirement, which Alpaca's history cannot.

Structure mirrors the Alpaca-validated one, scaled to SPX:
  weekly non-overlapping entries, ~7 DTE, short put ~2.2%/2.5% OTM,
  wing 0.65% of spot (the $5/$765 SPY ratio), credit = short BID - long ASK.
Settlement: SPXW is PM-settled, so expiry close is correct.
Gate: MSAR p_slow < 0.5 AND spot >= its own 200d MA, evaluated at ENTRY (causal).
"""
import math
import sys
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = "/Users/lukecha/Library/Mobile Documents/com~apple~CloudDocs/Trading Folder"
OUT = f"{ROOT}/AlpacaHackathon/research"
SCR = ("/private/tmp/claude-501/-Users-lukecha-Library-Mobile-Documents-"
       "com-apple-CloudDocs-Trading-Folder/116dc565-8b15-4c83-be8b-92c502d3d8c2/scratchpad")
sys.path.insert(0, f"{ROOT}/mandatory_tests_for_deployment_2")
DATA = f"{ROOT}/U.S._gamma_strategy/Reflexive_0DTE_Research/data"

OTMS = [0.019, 0.022, 0.025, 0.028]
WING_PCT = 5.0 / 765.0          # the SPY structure's wing as a fraction of spot
COST = 0.04
STRESS = {
    "Fed-Pivot-2018": ("2018-10-01", "2018-12-31"),
    "COVID-2020": ("2020-02-15", "2020-04-30"),
    "Tech-Bear-2022": ("2022-01-01", "2022-12-31"),
    "SVB-2023": ("2023-03-01", "2023-03-31"),
}


def load_chains():
    cols = ["date", "expiration", "side", "strike", "dte", "bid", "ask", "underlyingPrice"]
    a = pd.read_parquet(f"{DATA}/chains_SPX_pre2022.parquet", columns=cols)
    b = pd.read_parquet(f"{DATA}/chains_SPX.parquet", columns=cols)
    df = pd.concat([a, b], ignore_index=True)
    df = df[(df["side"] == "put") & df["dte"].between(6, 8)]
    df["date"] = pd.to_datetime(df["date"])
    df["exp"] = pd.to_datetime(df["expiration"], unit="s").dt.normalize()
    return df


def main():
    import or_smh_signal as sig
    import t2_qld_signal as t2
    import FinanceDataReader as fdr

    ch = load_chains()
    # spot per date (any row)
    spot = ch.groupby("date")["underlyingPrice"].first().sort_index()
    print(f"chain dates {spot.index.min():%Y-%m-%d} .. {spot.index.max():%Y-%m-%d}  "
          f"({len(spot)} sessions)")

    # --- gate inputs, causal ---
    vix = fdr.DataReader("^VIX", "2014-01-01")["Close"].dropna()
    vix.index = pd.to_datetime(vix.index)
    p_high = pd.Series(sig.msar_filtered_p_high(vix.values.tolist()), index=vix.index)
    p_slow = t2.p_slow_series(p_high)
    spx = fdr.DataReader("US500", "2016-01-01")["Close"].dropna()
    spx.index = pd.to_datetime(spx.index)
    trend = t2.trend_ok_series(spx)

    ps = p_slow.reindex(spot.index).ffill()
    tr = trend.reindex(spot.index).ffill()

    # --- weekly, non-overlapping entries ---
    entries, last_exp = [], None
    for d in spot.index:
        if last_exp is not None and d <= last_exp:
            continue
        sub = ch[ch["date"] == d]
        if sub.empty:
            continue
        # expiry with dte closest to 7
        e = sub.iloc[(sub["dte"] - 7).abs().argsort()]["exp"].iloc[0]
        if e not in spot.index:
            continue
        entries.append((d, e))
        last_exp = e
    print(f"weekly non-overlapping entries: {len(entries)}\n")

    rows = []
    for d, e in entries:
        sub = ch[(ch["date"] == d) & (ch["exp"] == e)]
        if sub.empty:
            continue
        S0, ST = float(spot.loc[d]), float(spot.loc[e])
        wing = WING_PCT * S0
        g_ps, g_tr = ps.get(d, np.nan), tr.get(d, np.nan)
        gate = (not pd.isna(g_ps)) and (not pd.isna(g_tr)) and g_ps < t2.VOL_ERA_P and g_tr > 0
        for otm in OTMS:
            tgt = S0 * (1 - otm)
            si = (sub["strike"] - tgt).abs().idxmin()
            srow = sub.loc[si]
            li = (sub["strike"] - (srow["strike"] - wing)).abs().idxmin()
            lrow = sub.loc[li]
            w = float(srow["strike"] - lrow["strike"])
            if w <= 0:
                continue
            credit = float(srow["bid"]) - float(lrow["ask"])
            if credit <= 0.01 or credit >= w:
                continue
            pnl = credit * (1 - COST) - max(0.0, min(float(srow["strike"]) - ST, w))
            rows.append(dict(date=d, exp=e, otm=otm, gate=gate, S0=S0, ST=ST,
                             K=float(srow["strike"]), width=w, credit=credit,
                             pnl=pnl, pnl_pct=pnl / w,
                             move=100 * (ST / S0 - 1)))
    R = pd.DataFrame(rows)
    R.to_csv(f"{SCR}/_spxbear.csv", index=False)
    print(f"trades built: {len(R)}   (per OTM: {len(R)//len(OTMS)})\n")

    def st(p):
        if len(p) < 8 or p.std() == 0:
            return None
        return dict(n=len(p), E=p.mean(), win=float((p > 0).mean()),
                    sharpe=p.mean() / p.std() * math.sqrt(52),
                    t=p.mean() / (p.std() / math.sqrt(len(p))), worst=p.min())

    hdr = (f"{'OTM':>5} {'arm':<9} {'n':>5} {'E/width':>9} {'win':>7} "
           f"{'Sharpe':>8} {'t':>7} {'worst':>8}")
    print("FULL SAMPLE 2018-2026 (8.4y, real SPX bid/ask)")
    print(hdr); print("-" * len(hdr))
    for otm in OTMS:
        g = R[R["otm"] == otm]
        for lab, d_ in [("ungated", g), ("gated", g[g["gate"]])]:
            s = st(d_["pnl_pct"].to_numpy())
            if s is None:
                continue
            print(f"{100*otm:>5.1f} {lab:<9} {s['n']:>5} {s['E']:>+9.4f} "
                  f"{100*s['win']:>6.1f}% {s['sharpe']:>+8.2f} {s['t']:>+7.2f} {s['worst']:>+8.3f}")

    print("\n\nPER-STRESS-WINDOW (the whole question) — E/width")
    h2 = f"{'window':<18}" + "".join(f"{f'{100*o:.1f}% u/g':>16}" for o in OTMS)
    print(h2); print("-" * len(h2))
    for name, (a_, b_) in STRESS.items():
        line = f"{name:<18}"
        for otm in OTMS:
            g = R[(R["otm"] == otm) & (R["date"] >= a_) & (R["date"] <= b_)]
            u = g["pnl_pct"].mean() if len(g) else np.nan
            gg = g[g["gate"]]["pnl_pct"]
            gv = gg.mean() if len(gg) else np.nan
            ng = len(gg)
            line += f"{u:>+7.3f}/{'FLAT' if ng == 0 else f'{gv:+.3f}'}".rjust(16)
        print(line)
    print("\n  (u = ungated, g = gated; FLAT = gate stood down entirely)")

    print("\n\nPER-YEAR at 2.5% OTM — E/width and how often the gate was on")
    print(f"  {'yr':<6}{'n_ung':>7}{'E ung':>9}{'n_gat':>7}{'E gat':>9}{'gate on':>9}")
    g25 = R[R["otm"] == 0.025].copy()
    g25["yr"] = g25["date"].dt.year
    for y, gg in g25.groupby("yr"):
        gt = gg[gg["gate"]]
        eg = f"{gt['pnl_pct'].mean():+.4f}" if len(gt) else "  FLAT"
        print(f"  {y:<6}{len(gg):>7}{gg['pnl_pct'].mean():>+9.4f}{len(gt):>7}{eg:>9}"
              f"{100*len(gt)/len(gg):>8.0f}%")

    # equity curves for the viz
    np.savez(f"{SCR}/_spxbear.npz",
             dates=np.array([f"{d:%Y-%m-%d}" for d in g25["date"]]),
             pnl=g25["pnl_pct"].to_numpy(), gate=g25["gate"].to_numpy())
    print(f"\nsaved {SCR}/_spxbear.csv + .npz")


if __name__ == "__main__":
    main()
