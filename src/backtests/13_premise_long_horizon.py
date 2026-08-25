"""PREMISE TEST (free) — does the slow signal have MULTI-MONTH power?

Tonight's diagnosis: MSAR p_slow is a 60d mean and the trend veto a 200d MA, so the
signal describes MONTH-scale regimes. We pointed it at 7-day options; being 5 days
late wrecked 71% of the position's life. The proposed fix is horizon matching.

Before building anything long-dated, test the premise on deep free data (no option
data needed). Three questions, in increasing order of what actually matters:

  Q1 direction: does the gate predict forward RETURNS at 3/6/12m?
  Q2 vol:       does p_slow predict forward REALIZED VOL at 3/6/12m?
  Q3 THE ONE THAT MATTERS: does p_slow predict forward RV *after controlling for
     VIX*, i.e. beyond what options already price? And does it predict the VRP
     (VIX - forward RV), which is the thing a vol seller actually harvests?

Q3 is where this fund's signals have died four times (VIX subsumption). If p_slow
adds nothing over VIX at these horizons, horizon-matching cannot rescue the thesis
and we stop.

Overlap handled two ways: Newey-West t-stats on the overlapping series, AND a
phase-averaged NON-OVERLAPPING estimate (every h-th observation, averaged over all
h possible phase offsets) as the honest check.
"""
import math

import numpy as np
import pandas as pd
import sys

ROOT = "/Users/lukecha/Library/Mobile Documents/com~apple~CloudDocs/Trading Folder"
OUT = f"{ROOT}/AlpacaHackathon/research"
SCR = ("/private/tmp/claude-501/-Users-lukecha-Library-Mobile-Documents-"
       "com-apple-CloudDocs-Trading-Folder/116dc565-8b15-4c83-be8b-92c502d3d8c2/scratchpad")
sys.path.insert(0, f"{ROOT}/mandatory_tests_for_deployment_2")
HORIZONS = [63, 126, 252]


def nw_tstat(y, X, lags):
    """OLS with Newey-West HAC standard errors. X includes the constant."""
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    resid = y - X @ beta
    n, k = X.shape
    S = (X * resid[:, None]).T @ (X * resid[:, None])
    for L in range(1, lags + 1):
        w = 1.0 - L / (lags + 1.0)
        u = X[L:] * resid[L:, None]
        v = X[:-L] * resid[:-L, None]
        G = u.T @ v
        S += w * (G + G.T)
    cov = XtX_inv @ S @ XtX_inv
    se = np.sqrt(np.maximum(np.diag(cov), 1e-18))
    return beta, beta / se


def phase_avg(mask_on, mask_off, series, h):
    """Non-overlapping estimate averaged over all h phase offsets."""
    diffs = []
    for p in range(h):
        idx = np.arange(p, len(series), h)
        on = series[idx][mask_on[idx]]
        off = series[idx][mask_off[idx]]
        if len(on) >= 3 and len(off) >= 3:
            diffs.append(on.mean() - off.mean())
    if not diffs:
        return np.nan, np.nan, 0
    d = np.array(diffs)
    return d.mean(), d.std(), len(d)


def main():
    import or_smh_signal as sig
    import t2_qld_signal as t2
    import FinanceDataReader as fdr

    vix = fdr.DataReader("^VIX", "1990-01-01")["Close"].dropna()
    vix.index = pd.to_datetime(vix.index)
    spx = fdr.DataReader("US500", "1990-01-01")["Close"].dropna()
    spx.index = pd.to_datetime(spx.index)

    idx = vix.index.intersection(spx.index)
    vix, spx = vix.reindex(idx).ffill(), spx.reindex(idx).ffill()
    print(f"sample {idx.min():%Y-%m-%d} .. {idx.max():%Y-%m-%d}  ({len(idx)} sessions, "
          f"{len(idx)/252:.1f} years)")

    p_high = pd.Series(sig.msar_filtered_p_high(vix.values.tolist()), index=idx)
    p_slow = t2.p_slow_series(p_high)
    trend = t2.trend_ok_series(spx)

    lr = np.log(spx).diff()
    px = spx.to_numpy()
    n = len(idx)

    print(f"MSAR p_slow: mean {p_slow.mean():.3f}, "
          f"frac >= 0.5 (vol-era) {100*(p_slow>=t2.VOL_ERA_P).mean():.1f}%")
    print(f"trend ok: {100*(trend>0).mean():.1f}% of days\n")

    rows = []
    for h in HORIZONS:
        fwd_ret = np.full(n, np.nan)
        fwd_rv = np.full(n, np.nan)
        r = lr.to_numpy()
        for i in range(n - h):
            fwd_ret[i] = math.log(px[i + h] / px[i])
            seg = r[i + 1:i + h + 1]
            seg = seg[np.isfinite(seg)]
            if len(seg) > 5:
                fwd_rv[i] = seg.std(ddof=1) * math.sqrt(252)
        ps = p_slow.to_numpy()
        tr = trend.to_numpy()
        vx = vix.to_numpy() / 100.0
        ok = (np.isfinite(fwd_ret) & np.isfinite(fwd_rv) & np.isfinite(ps)
              & np.isfinite(tr) & np.isfinite(vx))
        gate = ok & (ps < t2.VOL_ERA_P) & (tr > 0)
        offg = ok & ~((ps < t2.VOL_ERA_P) & (tr > 0))

        vrp = vx - fwd_rv                       # what a vol seller actually harvests

        print("=" * 88)
        print(f"HORIZON {h} trading days (~{h/21:.0f} months)   usable n={int(ok.sum())}")
        print("-" * 88)

        # Q1 direction
        a, b = fwd_ret[gate].mean(), fwd_ret[offg].mean()
        d_m, d_sd, npha = phase_avg(gate, offg, np.nan_to_num(fwd_ret), h)
        print(f" Q1 DIRECTION  fwd return: gate-ON {100*a:+6.2f}%  gate-OFF {100*b:+6.2f}%  "
              f"diff {100*(a-b):+6.2f}%")
        print(f"               non-overlap phase-avg diff {100*d_m:+6.2f}%  "
              f"(sd across {npha} phases {100*d_sd:.2f}%)  "
              f"z~{d_m/d_sd if d_sd else float('nan'):+.2f}")

        # Q2 vol
        a2, b2 = fwd_rv[gate].mean(), fwd_rv[offg].mean()
        d2, sd2, np2 = phase_avg(gate, offg, np.nan_to_num(fwd_rv), h)
        print(f" Q2 VOL        fwd realized vol: gate-ON {100*a2:5.2f}%  "
              f"gate-OFF {100*b2:5.2f}%  diff {100*(a2-b2):+5.2f}pp")
        print(f"               non-overlap phase-avg diff {100*d2:+5.2f}pp  "
              f"z~{d2/sd2 if sd2 else float('nan'):+.2f}")

        # Q3 the decisive one — incremental over VIX
        m = ok
        y = fwd_rv[m]
        X1 = np.column_stack([np.ones(m.sum()), vx[m]])                    # VIX only
        X2 = np.column_stack([np.ones(m.sum()), vx[m], ps[m]])             # VIX + p_slow
        b1, t1 = nw_tstat(y, X1, lags=h)
        b2_, t2_ = nw_tstat(y, X2, lags=h)
        r2_1 = 1 - ((y - X1 @ b1).var() / y.var())
        r2_2 = 1 - ((y - X2 @ b2_).var() / y.var())
        print(f" Q3 INCREMENTAL fwd_RV ~ VIX            : R2={r2_1:.3f}  "
              f"t(VIX)={t1[1]:+.2f}")
        print(f"                fwd_RV ~ VIX + p_slow   : R2={r2_2:.3f}  "
              f"t(VIX)={t2_[1]:+.2f}  **t(p_slow)={t2_[2]:+.2f}**  "
              f"dR2={r2_2-r2_1:+.4f}")

        # VRP: does the gate tell us when selling vol is paid?
        yv = vrp[m]
        Xv = np.column_stack([np.ones(m.sum()), vx[m], ps[m]])
        bv, tv = nw_tstat(yv, Xv, lags=h)
        av, bvv = vrp[gate].mean(), vrp[offg].mean()
        dv, sdv, npv = phase_avg(gate, offg, np.nan_to_num(vrp), h)
        print(f" Q3b VRP (VIX - fwd RV): gate-ON {100*av:+5.2f}pp  gate-OFF {100*bvv:+5.2f}pp  "
              f"diff {100*(av-bvv):+5.2f}pp")
        print(f"                non-overlap phase-avg diff {100*dv:+5.2f}pp  "
              f"z~{dv/sdv if sdv else float('nan'):+.2f}   "
              f"regression t(p_slow on VRP)={tv[2]:+.2f}")
        rows.append(dict(h=h, ret_on=a, ret_off=b, ret_z=d_m / d_sd if d_sd else np.nan,
                         rv_on=a2, rv_off=b2, rv_z=d2 / sd2 if sd2 else np.nan,
                         t_pslow_rv=t2_[2], dR2=r2_2 - r2_1,
                         vrp_on=av, vrp_off=bvv,
                         vrp_z=dv / sdv if sdv else np.nan, t_pslow_vrp=tv[2]))
        print()
    pd.DataFrame(rows).to_csv(f"{SCR}/_premise.csv", index=False)
    print(f"saved {SCR}/_premise.csv")


if __name__ == "__main__":
    main()
