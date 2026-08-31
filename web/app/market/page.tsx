"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import TabNav from "@/components/TabNav";
import Plot from "@/components/Plot";
import VolGraph from "@/components/VolGraph";
import { LAYOUT, CONFIG, C } from "@/lib/plotTheme";
import type { Bar } from "@/lib/alpaca";

/**
 * MARKET — the same shape as OptionDashboard's market section (chart + regime
 * strip + a volatility panel), but sourced entirely from Alpaca.
 *
 * ONE DELIBERATE DEVIATION, flagged rather than papered over: OptionDashboard's
 * VIX panels cannot be reproduced here. `^VIX` is not an Alpaca symbol, and
 * VIXY/VXX are decaying roll ETFs whose level is not a volatility reading --
 * substituting one would be the RV-for-IV anti-pattern this fund has an
 * explicit rule against. So the VIX *level* is shown as a number (fetched
 * server-side by the Python exporter, which can reach a real VIX source), and
 * the chart panel shows SPY REALIZED vol, labeled as realized.
 *
 * In exchange this tab shows something OptionDashboard cannot: the live dealer
 * gamma profile the agent actually trades on, straight from Alpaca open
 * interest.
 */

const TFS = [
  { k: "1Min", label: "1m" }, { k: "5Min", label: "5m" }, { k: "15Min", label: "15m" },
  { k: "30Min", label: "30m" }, { k: "1Hour", label: "1h" }, { k: "4Hour", label: "4h" },
  { k: "1Day", label: "1D" },
] as const;
const KINDS = ["candle", "ha", "line"] as const;
type Kind = (typeof KINDS)[number];
const POLL_MS = 60_000;

type Signal = {
  generated: string; underlying: string; spot: number; vix: number; vix_asof: string;
  gex: number; gex_sign: number; oi_date: string; n_contracts: number; cross_check: boolean;
  msar_long: boolean; p_high: number; p_slow: number; vol_era_threshold: number;
  trend_ok: number; ret_t: number; mom20: number; ac_dir: number; gate: boolean;
  sleeve1: string; sleeve2: string;
  gamma_profile: { strike: number; gex: number }[];
};

/** Heikin-Ashi, same definition the OptionDashboard chart uses. */
function toHA(bars: Bar[]): Bar[] {
  const out: Bar[] = [];
  for (let i = 0; i < bars.length; i++) {
    const b = bars[i];
    const c = (b.o + b.h + b.l + b.c) / 4;
    const o = i === 0 ? (b.o + b.c) / 2 : (out[i - 1].o + out[i - 1].c) / 2;
    out.push({ t: b.t, o, h: Math.max(b.h, o, c), l: Math.min(b.l, o, c), c, v: b.v });
  }
  return out;
}

function sma(v: number[], n: number): (number | null)[] {
  const out: (number | null)[] = [];
  let s = 0;
  for (let i = 0; i < v.length; i++) {
    s += v[i];
    if (i >= n) s -= v[i - n];
    out.push(i >= n - 1 ? s / n : null);
  }
  return out;
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick}
      className={`px-2 py-[2px] text-[10px] border transition-colors ${
        on ? "border-cyan text-cyan" : "border-grid text-label hover:border-label"}`}>
      {children}
    </button>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="border border-grid bg-panel/40 px-3 py-2">
      <div className="text-[9px] tracking-[0.08em] text-label">{label}</div>
      <div className="text-sm tabular-nums" style={tone ? { color: tone } : undefined}>{value}</div>
    </div>
  );
}

export default function MarketPage() {
  const [tf, setTf] = useState<(typeof TFS)[number]["k"]>("1Day");
  const [kind, setKind] = useState<Kind>("candle");
  const [bars, setBars] = useState<Bar[]>([]);
  const [daily, setDaily] = useState<Bar[]>([]);
  const [sig, setSig] = useState<Signal | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [b, d, s] = await Promise.all([
        fetch(`/api/bars?symbol=SPY&timeframe=${tf}&limit=500`).then((r) => r.json()),
        fetch("/api/bars?symbol=SPY&timeframe=1Day&limit=800").then((r) => r.json()),
        fetch("/signal.json").then((r) => (r.ok ? r.json() : null)).catch(() => null),
      ]);
      if (b.error) throw new Error(b.error);
      setBars(b.bars ?? []);
      setDaily(d.bars ?? []);
      if (s) setSig(s);
      setErr(null);
    } catch (e: any) {
      setErr(String(e?.message ?? e));
    }
  }, [tf]);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const priceTraces = useMemo(() => {
    if (!bars.length) return [];
    const src = kind === "ha" ? toHA(bars) : bars;
    const x = src.map((b) => b.t);
    if (kind === "line") {
      return [{ x, y: src.map((b) => b.c), type: "scatter", mode: "lines",
                name: "SPY", line: { color: C.cyan, width: 1.6 } }];
    }
    const t: any[] = [{
      x, open: src.map((b) => b.o), high: src.map((b) => b.h),
      low: src.map((b) => b.l), close: src.map((b) => b.c),
      type: "candlestick", name: kind === "ha" ? "SPY (HA)" : "SPY",
      increasing: { line: { color: C.pos }, fillcolor: C.pos },
      decreasing: { line: { color: C.neg }, fillcolor: C.neg },
    }];
    const closes = src.map((b) => b.c);
    for (const [n, col] of [[20, C.gold], [50, "#3B9EFF"]] as const) {
      if (closes.length > n) {
        t.push({ x, y: sma(closes, n), type: "scatter", mode: "lines",
                 name: `SMA${n}`, line: { color: col, width: 1 } });
      }
    }
    return t;
  }, [bars, kind]);

  const gammaTrace = useMemo(() => {
    if (!sig?.gamma_profile?.length) return null;
    const p = sig.gamma_profile;
    return [{
      x: p.map((g) => g.gex / 1e9), y: p.map((g) => g.strike),
      type: "bar", orientation: "h", name: "GEX",
      marker: { color: p.map((g) => (g.gex >= 0 ? C.pos : C.neg)) },
      hovertemplate: "%{y} · %{x:.3f} $bn<extra></extra>",
    }];
  }, [sig]);

  return (
    <main className="min-h-screen">
      <TabNav active="/market" />

      {err && (
        <div className="mx-4 mt-3 border border-neg/60 bg-neg/10 px-3 py-2 text-xs text-neg">{err}</div>
      )}

      {sig && (
        <div className="grid grid-cols-2 gap-2 px-4 py-3 md:grid-cols-4 lg:grid-cols-7">
          <Stat label="SPOT" value={`$${sig.spot.toFixed(2)}`} />
          <Stat label="VIX" value={sig.vix.toFixed(2)} tone={sig.vix > 20 ? C.neg : undefined} />
          <Stat label="DEALER GEX" value={`${(sig.gex / 1e9).toFixed(3)} $bn`}
                tone={sig.gex_sign > 0 ? C.pos : C.neg} />
          <Stat label="MSAR REGIME" value={sig.msar_long ? "RISK-ON" : "RISK-OFF"}
                tone={sig.msar_long ? C.pos : C.neg} />
          <Stat label="p_slow" value={`${sig.p_slow.toFixed(3)} / ${sig.vol_era_threshold}`}
                tone={sig.p_slow >= sig.vol_era_threshold ? C.neg : undefined} />
          <Stat label="SLEEVE 1" value={sig.sleeve1} tone={sig.gate ? C.pos : C.label} />
          <Stat label="SLEEVE 2" value={sig.sleeve2}
                tone={sig.ac_dir > 0 ? C.pos : sig.ac_dir < 0 ? C.neg : C.label} />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 px-4 pb-2">
        <div className="flex gap-1">
          {TFS.map((t) => <Chip key={t.k} on={t.k === tf} onClick={() => setTf(t.k)}>{t.label}</Chip>)}
        </div>
        <div className="flex gap-1">
          {KINDS.map((k) => <Chip key={k} on={k === kind} onClick={() => setKind(k)}>{k.toUpperCase()}</Chip>)}
        </div>
        {sig && (
          <span className="ml-auto text-[10px] text-label">
            OI {sig.oi_date} · {sig.n_contracts} contracts ·{" "}
            {sig.cross_check ? "cross-check OK" : "CROSS-CHECK MISMATCH"}
          </span>
        )}
      </div>

      <div className="grid gap-3 px-4 pb-4 lg:grid-cols-[1fr_320px]">
        <section className="border border-grid bg-panel/40 p-2">
          <div className="px-1 pb-1 text-[11px] tracking-[0.14em] text-cyan">SPY</div>
          {bars.length ? (
            <Plot data={priceTraces}
              layout={{ ...LAYOUT, height: 420, xaxis: { ...LAYOUT.xaxis, rangeslider: { visible: false } } }}
              config={CONFIG} style={{ width: "100%" }} />
          ) : (
            <div className="flex h-[420px] items-center justify-center text-xs text-label">loading bars…</div>
          )}
        </section>

        <section className="border border-grid bg-panel/40 p-2">
          <div className="px-1 pb-1 text-[11px] tracking-[0.14em] text-cyan">
            DEALER GAMMA PROFILE <span className="text-label">· per strike</span>
          </div>
          {gammaTrace ? (
            <Plot data={gammaTrace}
              layout={{ ...LAYOUT, height: 420, showlegend: false,
                margin: { l: 52, r: 10, t: 10, b: 34 },
                xaxis: { ...LAYOUT.xaxis, title: { text: "$bn", font: { size: 9, color: C.label } } },
                yaxis: { ...LAYOUT.yaxis, title: { text: "STRIKE", font: { size: 9, color: C.label } } },
                shapes: sig ? [{ type: "line", xref: "paper", x0: 0, x1: 1,
                                 y0: sig.spot, y1: sig.spot,
                                 line: { color: C.gold, width: 1, dash: "dot" } }] : [] }}
              config={CONFIG} style={{ width: "100%" }} />
          ) : (
            <div className="flex h-[420px] items-center justify-center px-4 text-center text-xs text-label">
              no signal.json — run
              <br />
              <code className="text-body">export_signal_json.py</code>
            </div>
          )}
        </section>
      </div>

      <div className="px-4 pb-8">
        <section className="border border-grid bg-panel/40 p-2">
          <div className="px-1 pb-1 text-[11px] tracking-[0.14em] text-cyan">
            S&amp;P 500 REALIZED VOLATILITY
            <span className="ml-2 text-label">
              · 21d annualized · realized, not implied (VIX is not an Alpaca symbol)
            </span>
          </div>
          <VolGraph times={daily.map((b) => b.t)} closes={daily.map((b) => b.c)} height={220} />
        </section>
      </div>
    </main>
  );
}
