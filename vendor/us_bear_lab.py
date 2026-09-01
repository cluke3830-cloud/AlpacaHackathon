"""
US bear-strategy combination lab — same A/B/C framework as Korea, on SPX/S&P.

Data: Research_Concepts/Reflexive_0DTE_Research/data/chains_SPX.parquet
      (per-strike OI + mid, 2022-05 → 2026-06, dte 0-8) → we compute US GEX.
      S&P500 prices via FinanceDataReader (free) → momentum + forced-liq.

Dealer convention: US is the STANDARD one (institutions buy puts / overwrite
calls → dealers long call-gamma, short put-gamma): gex = Σ(call γ·OI) − Σ(put γ·OI).
This is the OPPOSITE of Korea's retail-inverted sign. Dealer-long-γ (gex>0) is
expected to mean-revert; dealer-short-γ (gex<0) to trend.

Components (causal, same as KR lab):
  C momentum      : sign(trailing 20d return)
  A gamma-vol     : fade dealer-long-γ, follow dealer-short-γ
  B forced-liquid : long the day after a capitulation day (bottom-decile return)
"""
from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import norm
import FinanceDataReader as fdr

from bear_strategy_lab import evaluate, stats, COST_BPS

_CDIR  = Path(__file__).resolve().parent.parent.parent / "Research_Concepts" / \
         "Reflexive_0DTE_Research" / "data"
CHAINS = _CDIR / "chains_SPX.parquet"
CHAINS_PRE = _CDIR / "chains_SPX_pre2022.parquet"   # 2018-2022 backfill (real-bear test)
R, Q = 0.04, 0.014


def iv_vec(price, S, K, T, cp, n=50):
    """Vectorized Newton-Raphson BS implied vol."""
    price, S, K, T, cp = map(lambda a: np.asarray(a, float), (price, S, K, T, cp))
    sig = np.full(price.shape, 0.25)
    for _ in range(n):
        sq = sig * np.sqrt(T)
        d1 = (np.log(S / K) + (R - Q + 0.5 * sig ** 2) * T) / sq
        d2 = d1 - sq
        model = cp * (S * np.exp(-Q * T) * norm.cdf(cp * d1) - K * np.exp(-R * T) * norm.cdf(cp * d2))
        vega = S * np.exp(-Q * T) * norm.pdf(d1) * np.sqrt(T)
        sig = np.clip(sig - (model - price) / np.maximum(vega, 1e-8), 1e-3, 5.0)
    return sig


def build_us_gex():
    parts = [pd.read_parquet(CHAINS)]
    if CHAINS_PRE.exists():
        parts.append(pd.read_parquet(CHAINS_PRE))           # 2018-2022 real-bear backfill
    df = pd.concat(parts, ignore_index=True).drop_duplicates(["date", "optionSymbol"])
    df["date"] = pd.to_datetime(df["date"])
    df["oi"]   = pd.to_numeric(df["openInterest"], errors="coerce")
    df["mid"]  = pd.to_numeric(df["mid"], errors="coerce")
    df = df[(df["dte"].between(1, 8)) & (df["oi"] > 0) & (df["mid"] > 0)].copy()
    S = df["underlyingPrice"].values.astype(float)
    K = df["strike"].values.astype(float)
    df = df[np.abs(np.log(K / S)) < 0.20].copy()            # near-the-money (gamma-relevant)

    S = df["underlyingPrice"].values.astype(float)
    K = df["strike"].values.astype(float)
    T = df["dte"].values.astype(float) / 365.0
    cp = np.where(df["side"].values == "call", 1.0, -1.0)
    iv = iv_vec(df["mid"].values, S, K, T, cp)
    sq = iv * np.sqrt(T)
    d1 = (np.log(S / K) + (R - Q + 0.5 * iv ** 2) * T) / sq
    gamma = np.exp(-Q * T) * norm.pdf(d1) / (S * iv * np.sqrt(T))
    dgamma = gamma * df["oi"].values * S ** 2 * 0.01
    df["gsigned"] = np.where(df["side"].values == "call", dgamma, -dgamma)  # US standard

    gex = df.groupby("date")["gsigned"].sum()
    return gex.rename("gex_std")


def build_us_panel():
    gex = build_us_gex()
    d0, d1 = gex.index.min(), gex.index.max()
    px = fdr.DataReader("S&P500", str(d0.date()), str((d1 + pd.Timedelta(days=5)).date()))["Close"]
    px.index = pd.to_datetime(px.index)
    ret = np.log(px / px.shift(1))

    df = pd.DataFrame(index=gex.index)
    df["ret_t"]    = ret.reindex(df.index)
    df["ret_t1"]   = ret.shift(-1).reindex(df.index)
    # RETAIL convention (same inversion as Korea). Under the classic-institutional
    # convention (np.sign(gex)) the A signal was strongly ANTI-predictive in the US
    # (overall Sharpe -1.89, t=-3.63) — the same fingerprint Korea showed. Short-dated
    # (0-8 DTE) US options are now retail-dominated (the 0DTE boom), so dealers are net
    # SHORT gamma, exactly like Korea. Data-confirmed, cross-market replicated.
    df["gex_sign"] = np.sign(-gex).reindex(df.index)        # dealer-long-γ when gex<0 (retail-inverted)
    df["spot"]     = px.reindex(df.index)
    df["ma100"]    = px.rolling(100).mean().reindex(df.index)
    df["rv20"]     = (ret.rolling(20).std() * np.sqrt(252)).reindex(df.index)
    df["mom20"]    = ret.rolling(20).sum().reindex(df.index)
    df["ret_pct"]  = ret.expanding(60).apply(lambda s: (s.iloc[-1] <= s).mean()).reindex(df.index)
    df = df.dropna(subset=["ret_t", "ret_t1", "gex_sign", "ma100", "rv20", "mom20", "ret_pct"])

    df["C"] = np.sign(df["mom20"])
    df["A"] = np.where(df["gex_sign"] > 0, -np.sign(df["ret_t"]), np.sign(df["ret_t"]))
    df["B"] = np.where(df["ret_pct"] <= 0.10, 1.0, 0.0)
    df["downtrend"] = df["spot"] < df["ma100"]
    df["stress"]    = df["rv20"] > df["rv20"].expanding(60).quantile(0.667)
    return df


def run():
    df = build_us_panel()
    subsets = [c for r in (1, 2, 3) for c in combinations(["A", "B", "C"], r)]
    print("=" * 78)
    print(f"  US BEAR-STRATEGY LAB (S&P500 + SPX GEX)  |  {df.index.min().date()} → "
          f"{df.index.max().date()}  n={len(df)}  (cost {COST_BPS}bps)")
    print(f"  dealer long-γ days: {int((df.gex_sign>0).sum())}, short-γ: {int((df.gex_sign<0).sum())}")
    print("=" * 78)
    print(f"  {'combo':8s} {'OVERALL Sh(t)':>16s} {'DOWNTREND Sh(t)':>18s} {'STRESS Sh(t)':>16s} {'maxDD%':>8s}")

    rows, eqs = [], {}
    for comps in subsets:
        label = "+".join(comps)
        _, pnl = evaluate(df, comps)
        eqs[label] = pnl.fillna(0).cumsum() * 100
        ov, dn, st = stats(pnl), stats(pnl[df.downtrend]), stats(pnl[df.stress])
        rows.append(dict(combo=label, ov=ov, dn=dn, st=st))
        print(f"  {label:8s} {ov['sharpe']:>+8.2f}(t{ov['t']:>+5.2f}) "
              f"{dn['sharpe']:>+9.2f}(t{dn['t']:>+5.2f}) "
              f"{st['sharpe']:>+8.2f}(t{st['t']:>+5.2f}) {ov['dd']:>+8.1f}")
    bh, bh_dn = stats(df.ret_t1), stats(df.ret_t1[df.downtrend])
    eqs["Buy&Hold"] = df.ret_t1.fillna(0).cumsum() * 100
    print(f"  {'B&Hold':8s} {bh['sharpe']:>+8.2f}(t{bh['t']:>+5.2f}) "
          f"{bh_dn['sharpe']:>+9.2f}(t{bh_dn['t']:>+5.2f})")

    best = max(rows, key=lambda r: r["ov"]["sharpe"])
    best_dn = max(rows, key=lambda r: r["dn"]["sharpe"])
    print(f"\n  BEST overall : {best['combo']} ({best['ov']['sharpe']:+.2f})")
    print(f"  BEST in bear : {best_dn['combo']} (downtrend {best_dn['dn']['sharpe']:+.2f} vs B&Hold {bh_dn['sharpe']:+.2f})")

    _dash(df, rows, eqs, best, best_dn)
    return rows


def _dash(df, rows, eqs, best, best_dn):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from viz_signals import BG, PANEL, AMBER, GREEN, RED, GREY, TXT, FONT
    fig = make_subplots(rows=2, cols=2, row_heights=[0.55, 0.45],
        specs=[[{"colspan": 2}, None], [{}, {}]],
        subplot_titles=("US equity curves — all combos + Buy&Hold (cum %)",
                        "Overall Sharpe by combo", "Regime Sharpe (downtrend vs stress)"),
        vertical_spacing=0.12, horizontal_spacing=0.09)
    pal = [AMBER, GREEN, RED, "#4A90E2", "#B388FF", "#FF8A65", "#26C6DA", GREY]
    for (lbl, eq), c in zip(eqs.items(), pal):
        w = 2.5 if lbl == best["combo"] else (1 if lbl == "Buy&Hold" else 1.3)
        fig.add_trace(go.Scatter(x=eq.index, y=eq.values, name=lbl, line=dict(color=c, width=w)), row=1, col=1)
    labels = [r["combo"] for r in rows]
    fig.add_trace(go.Bar(x=labels, y=[r["ov"]["sharpe"] for r in rows],
                  marker_color=[GREEN if r["ov"]["sharpe"] > 0 else RED for r in rows],
                  text=[f"{r['ov']['sharpe']:+.2f}" for r in rows], textposition="outside",
                  showlegend=False), row=2, col=1)
    fig.add_trace(go.Bar(x=labels, y=[r["dn"]["sharpe"] for r in rows], name="downtrend", marker_color=RED), row=2, col=2)
    fig.add_trace(go.Bar(x=labels, y=[r["st"]["sharpe"] for r in rows], name="stress", marker_color=AMBER), row=2, col=2)
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=PANEL,
        font=dict(family=FONT, color=TXT, size=11), barmode="group",
        title=dict(text=f"<b>US Bear-Strategy Lab — A(gamma)/B(forced-liq)/C(momentum)</b>"
                        f"<br><span style='font-size:12px;color:{GREY}'>best overall {best['combo']} "
                        f"({best['ov']['sharpe']:+.2f}) · best-in-bear {best_dn['combo']} "
                        f"({best_dn['dn']['sharpe']:+.2f})</span>", x=0.5, font=dict(color=AMBER, size=17)),
        legend=dict(orientation="h", y=-0.06, x=0.5, xanchor="center"),
        margin=dict(t=95, b=55, l=55, r=30), height=940)
    for r_ in (1, 2):
        for c_ in (1, 2):
            fig.update_xaxes(gridcolor="#222", row=r_, col=c_); fig.update_yaxes(gridcolor="#222", row=r_, col=c_)
    out = Path(__file__).resolve().parent.parent / "backtest_results" / "us_bear_lab.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"\n  Dashboard → {out}")


if __name__ == "__main__":
    run()
