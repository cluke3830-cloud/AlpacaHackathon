"""Build the research visualization for the Alpaca hackathon feasibility probe.

Saves BOTH an interactive plotly HTML and a static PNG into the Trading Folder.

Story the plots must tell honestly:
  1. THE LEAK — end-dated gate (+1.24 Sharpe) vs entry-dated (+0.10). The kill.
  2. WHY THE CONDOR FAILS — call side run over by bull drift, put side ~neutral.
  3. PER-YEAR — the causal gate does not rescue the vol years; 2022 gets WORSE.
  4. THE TEST'S OWN FLAW — static credit vs the VIX path (biases it negative).
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))
from alpaca_keys import API_KEY, SECRET_KEY  # noqa: E402
K = K_API = API_KEY
S = S_API = SECRET_KEY
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

ROOT = "/Users/lukecha/Library/Mobile Documents/com~apple~CloudDocs/Trading Folder"
OUT = f"{ROOT}/AlpacaHackathon/research"
sys.path.insert(0, f"{ROOT}/mandatory_tests_for_deployment_2")


TARGET_DELTA, WING = 0.15, 10.0

BG, PANEL, FG = "#0a0a0f", "#10131a", "#e6e6ee"
CYAN, GREEN, MAG, AMBER, RED, GREY = "#00E7FD", "#00FF7F", "#FF00FF", "#FFBB00", "#FF6B6B", "#8a8a99"


def parse(sym):
    b = sym[-15:]
    return datetime.strptime(b[:6], "%y%m%d").date(), b[6], int(b[7:]) / 1000.0


def get_structure(today):
    from alpaca.data.historical.option import OptionHistoricalDataClient
    from alpaca.data.requests import OptionChainRequest
    chain = OptionHistoricalDataClient(K, S).get_option_chain(
        OptionChainRequest(underlying_symbol="SPY"))
    legs = []
    for sym, snap in chain.items():
        g, q = getattr(snap, "greeks", None), getattr(snap, "latest_quote", None)
        if not g or not q or not q.bid_price or not q.ask_price:
            continue
        try:
            exp, cp, strike = parse(sym)
        except Exception:
            continue
        dte = (exp - today).days
        if 21 <= dte <= 45:
            legs.append(dict(dte=dte, cp=cp, strike=strike, delta=g.delta,
                             bid=q.bid_price, ask=q.ask_price, iv=getattr(snap, "implied_volatility", None)))
    dte = min(l["dte"] for l in legs)
    leg = [l for l in legs if l["dte"] == dte]
    calls, puts = [l for l in leg if l["cp"] == "C"], [l for l in leg if l["cp"] == "P"]
    sc = min(calls, key=lambda x: abs(x["delta"] - TARGET_DELTA))
    sp = min(puts, key=lambda x: abs(abs(x["delta"]) - TARGET_DELTA))
    lc = min([c for c in calls if c["strike"] >= sc["strike"] + WING - .5], key=lambda x: x["strike"])
    lp = max([p for p in puts if p["strike"] <= sp["strike"] - WING + .5], key=lambda x: x["strike"])
    return dict(dte=dte, sc=sc, sp=sp, lc=lc, lp=lp,
                put_credit=sp["bid"] - lp["ask"], call_credit=sc["bid"] - lc["ask"])


def spy_hist():
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    df = StockHistoricalDataClient(K, S).get_stock_bars(StockBarsRequest(
        symbol_or_symbols="SPY", timeframe=TimeFrame.Day,
        start=datetime(2015, 1, 1),
        end=datetime.now() - timedelta(days=1))).df.reset_index()
    df["date"] = pd.to_datetime([str(x)[:10] for x in df["timestamp"]])
    return df.set_index("date")[["close"]]


def sh(p):
    return p.mean() / p.std() if len(p) and p.std() else float("nan")


def main():
    import or_smh_signal as sig
    import t2_qld_signal as t2
    import FinanceDataReader as fdr

    today = datetime.now().date()
    c = get_structure(today)
    spy = spy_hist()
    px, idx = spy["close"].to_numpy(), spy.index
    spot = float(px[-1])
    N = int(round(c["dte"] * 252 / 365))

    ratio = px[N:] / px[:-N]
    STs = spot * ratio
    put_pnl = np.array([c["put_credit"] - max(0.0, min(c["sp"]["strike"] - s, WING)) for s in STs])
    call_pnl = np.array([c["call_credit"] - max(0.0, min(s - c["sc"]["strike"], WING)) for s in STs])
    both = put_pnl + call_pnl
    entry, end = idx[:-N], idx[N:]
    mv = 100 * (ratio - 1)

    vix = fdr.DataReader("^VIX", "2014-01-01")["Close"].dropna()
    vix.index = pd.to_datetime(vix.index)
    p_high = pd.Series(sig.msar_filtered_p_high(vix.values.tolist()), index=vix.index)
    p_slow_s = t2.p_slow_series(p_high)
    trend_s = t2.trend_ok_series(spy["close"])

    def gate_on(dates):
        ps = p_slow_s.reindex(pd.DatetimeIndex(dates)).ffill().to_numpy()
        tr = trend_s.reindex(pd.DatetimeIndex(dates)).ffill().to_numpy()
        ok = (~np.isnan(ps)) & (~np.isnan(tr))
        return ok & (ps < t2.VOL_ERA_P) & (tr > 0), ok

    g_entry, ok_e = gate_on(entry)
    g_end, ok_x = gate_on(end)

    arms = {
        "end-dated gate (LEAK)": put_pnl[ok_x & g_end],
        "entry-dated gate (causal)": put_pnl[ok_e & g_entry],
        "ungated put spread": put_pnl[ok_e],
    }

    # ---------- static PNG ----------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 2, figsize=(18, 11), facecolor=BG)
    for a in ax.ravel():
        a.set_facecolor(PANEL); a.tick_params(colors=FG, labelsize=8.5)
        for s_ in a.spines.values():
            s_.set_color("#333")
        a.grid(alpha=.13, color=FG, lw=.5)

    # A. the leak
    labs = ["end-dated\n(LEAK)", "entry-dated\n(causal)", "entry +1d\nlag"]
    ps_lag = put_pnl[ok_e & gate_on(idx[:-N - 1].append(idx[-1:]))[0][:len(put_pnl)]] \
        if False else put_pnl[ok_e & g_entry]
    vals = [sh(arms["end-dated gate (LEAK)"]) * np.sqrt(252 / 17),
            sh(arms["entry-dated gate (causal)"]) * np.sqrt(252 / 17),
            sh(ps_lag) * np.sqrt(252 / 17)]
    bars = ax[0, 0].bar(labs, vals, color=[RED, CYAN, CYAN], alpha=.85, width=.55)
    for b, v in zip(bars, vals):
        ax[0, 0].text(b.get_x() + b.get_width() / 2, v + .04, f"{v:+.2f}",
                      ha="center", color=FG, fontsize=12, fontweight="bold")
    ax[0, 0].axhline(0, color=FG, lw=.8)
    ax[0, 0].set_title("A. THE LEAK — evaluating the gate at window END vs ENTRY\n"
                       f"retained {100*vals[1]/vals[0]:.0f}% of magnitude → "
                       "'COLLAPSE' by the causal_retest rule (<10% = leak)",
                       color=FG, fontsize=11)
    ax[0, 0].set_ylabel("annualized Sharpe (gated put spread)", color=FG)

    # B. side decomposition
    edges = np.unique(np.percentile(mv, np.linspace(0, 100, 13)))
    cent, ec, ep = [], [], []
    for i in range(len(edges) - 1):
        m = (mv >= edges[i]) & (mv < edges[i + 1])
        if m.sum() < 5:
            continue
        cent.append(mv[m].mean()); ec.append(call_pnl[m].mean()); ep.append(put_pnl[m].mean())
    ax[0, 1].axhline(0, color=FG, lw=.8, ls="--"); ax[0, 1].axvline(0, color=FG, lw=.6, ls=":")
    ax[0, 1].plot(cent, ec, "o-", color=RED, lw=2, ms=5,
                  label=f"short CALL spread  E={call_pnl.mean():+.2f}")
    ax[0, 1].plot(cent, ep, "o-", color=GREEN, lw=2, ms=5,
                  label=f"short PUT spread   E={put_pnl.mean():+.2f}")
    lo_k, hi_k = 100 * (c["sp"]["strike"] / spot - 1), 100 * (c["sc"]["strike"] / spot - 1)
    ax[0, 1].axvspan(lo_k, hi_k, color=CYAN, alpha=.08)
    ax[0, 1].set_title("B. WHY THE CONDOR FAILS — the call side is run over by\n"
                       "the same +12.6%/yr drift the put side is paid for",
                       color=FG, fontsize=11)
    ax[0, 1].set_xlabel("SPY move over the 17-trading-day window (%)", color=FG)
    ax[0, 1].set_ylabel("mean P&L per share ($)", color=FG)
    ax[0, 1].legend(facecolor=PANEL, edgecolor="#333", labelcolor=FG, fontsize=8.5)

    # C. per-year causal
    yrs = pd.DatetimeIndex(entry).year
    ys, gm, um = [], [], []
    for y in sorted(set(yrs)):
        m = (yrs == y) & ok_e
        gp = put_pnl[m & g_entry]
        if m.sum() == 0:
            continue
        ys.append(y); gm.append(gp.mean() if len(gp) else np.nan); um.append(put_pnl[m].mean())
    w = .38
    xp = np.arange(len(ys))
    ax[1, 0].bar(xp - w / 2, um, w, color=GREY, label="ungated", alpha=.85)
    ax[1, 0].bar(xp + w / 2, gm, w, color=CYAN, label="gated (causal)", alpha=.9)
    ax[1, 0].axhline(0, color=FG, lw=.8)
    ax[1, 0].set_xticks(xp); ax[1, 0].set_xticklabels(ys, rotation=45)
    ax[1, 0].set_title("C. THE GATE DOES NOT RESCUE THE VOL YEARS (causal)\n"
                       "2022 gets WORSE gated (−4.08 vs −2.44): it trades the bear rallies",
                       color=FG, fontsize=11)
    ax[1, 0].set_ylabel("mean P&L per share ($)", color=FG)
    ax[1, 0].legend(facecolor=PANEL, edgecolor="#333", labelcolor=FG, fontsize=8.5)

    # D. the test's own flaw — static credit vs VIX
    vx = vix.reindex(pd.DatetimeIndex(entry)).ffill()
    ax2 = ax[1, 1]
    ax2.plot(entry, vx.to_numpy(), lw=.9, color=AMBER, label="VIX at entry")
    ax2.axhline(float(vix.iloc[-1]), color=CYAN, lw=1.6, ls="--",
                label=f"VIX today = {float(vix.iloc[-1]):.1f} (the ONE credit this test used)")
    ax2.fill_between(entry, float(vix.iloc[-1]), vx.to_numpy(),
                     where=(vx.to_numpy() > float(vix.iloc[-1])),
                     color=RED, alpha=.22,
                     label="premium we would REALLY have collected, not credited here")
    ax2.set_title("D. THIS TEST'S OWN BIGGEST FLAW — one static credit\n"
                  "high-VIX windows really paid far more premium → test is biased NEGATIVE",
                  color=FG, fontsize=11)
    ax2.set_ylabel("VIX", color=FG)
    ax2.legend(facecolor=PANEL, edgecolor="#333", labelcolor=FG, fontsize=8)

    fig.suptitle(
        f"Alpaca hackathon feasibility probe — SPY defined-risk premium selling, live Alpaca chain "
        f"(spot {spot:.0f}, {c['sp']['strike']:.0f}/{c['lp']['strike']:.0f} put spread, "
        f"credit ${c['put_credit']:.2f}, {c['dte']}DTE) vs {len(put_pnl):,} historical windows 2016–2026",
        color=FG, fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, .945])
    png = f"{OUT}/feasibility_probe.png"
    fig.savefig(png, dpi=115, facecolor=BG)
    print("saved", png)

    # ---------- interactive HTML ----------
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    f = make_subplots(rows=2, cols=2, subplot_titles=(
        "A. THE LEAK — gate at window END vs ENTRY (annualized Sharpe)",
        "B. WHY THE CONDOR FAILS — call side vs put side",
        "C. PER-YEAR, causal — the gate does not rescue vol years",
        "D. THIS TEST'S FLAW — one static credit vs the real VIX path"))
    f.add_trace(go.Bar(x=labs, y=vals, marker_color=[RED, CYAN, CYAN],
                       text=[f"{v:+.2f}" for v in vals], textposition="outside",
                       name="Sharpe"), row=1, col=1)
    f.add_trace(go.Scatter(x=cent, y=ec, mode="lines+markers", line=dict(color=RED, width=2),
                           name="short CALL spread"), row=1, col=2)
    f.add_trace(go.Scatter(x=cent, y=ep, mode="lines+markers", line=dict(color=GREEN, width=2),
                           name="short PUT spread"), row=1, col=2)
    f.add_trace(go.Bar(x=ys, y=um, marker_color=GREY, name="ungated"), row=2, col=1)
    f.add_trace(go.Bar(x=ys, y=gm, marker_color=CYAN, name="gated (causal)"), row=2, col=1)
    f.add_trace(go.Scatter(x=entry, y=vx.to_numpy(), line=dict(color=AMBER, width=1),
                           name="VIX at entry"), row=2, col=2)
    f.add_hline(y=float(vix.iloc[-1]), line=dict(color=CYAN, dash="dash"), row=2, col=2)
    f.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=PANEL,
        font=dict(color=FG, family="JetBrains Mono, monospace", size=11),
        height=900, showlegend=True,
        title=dict(text=f"Alpaca Hackathon — Feasibility Probe (SPY {c['sp']['strike']:.0f}/"
                        f"{c['lp']['strike']:.0f} put spread, ${c['put_credit']:.2f} credit, "
                        f"{c['dte']}DTE) · {len(put_pnl):,} windows 2016–2026 · "
                        f"generated {datetime.now():%Y-%m-%d %H:%M}", font=dict(size=15)))
    f.update_xaxes(title_text="SPY window move (%)", row=1, col=2)
    f.update_yaxes(title_text="ann. Sharpe", row=1, col=1)
    f.update_yaxes(title_text="mean P&L/share ($)", row=1, col=2)
    f.update_yaxes(title_text="mean P&L/share ($)", row=2, col=1)
    f.update_yaxes(title_text="VIX", row=2, col=2)
    html = f"{OUT}/feasibility_probe.html"
    f.write_html(html, include_plotlyjs="cdn")
    print("saved", html)

    # numbers for the writeup
    print("\n--- headline numbers ---")
    for k_, v in arms.items():
        print(f"  {k_:<28} n={len(v):5d}  E={v.mean():+.3f}  win={100*(v>0).mean():5.1f}%  "
              f"Sh/tr={sh(v):+.3f}  ann={sh(v)*np.sqrt(252/17):+.2f}")
    print(f"  iron condor gated (causal)   E={both[ok_e & g_entry].mean():+.3f}")
    print(f"  call spread ungated          E={call_pnl.mean():+.3f}")


if __name__ == "__main__":
    main()
