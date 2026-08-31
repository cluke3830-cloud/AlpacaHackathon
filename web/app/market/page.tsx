"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import TabNav from "@/components/TabNav";
import MarketChart from "@/components/MarketChart";
import VixTermChart from "@/components/VixTermChart";
import VixPulse from "@/components/VixPulse";
import FragilityBadge from "@/components/FragilityBadge";
import RegimeStack from "@/components/RegimeStack";
import BacktestPanel from "@/components/BacktestPanel";
import { type SurfaceData } from "@/components/VolSurface";
import GammaProfile from "@/components/GammaProfile";
import { C } from "@/lib/theme";
import { buildVixTermStructure } from "@/lib/vixTermStructure";
import { regimeProbs, currentRegime } from "@/lib/hmmRegime";
import { computeVixMeanRev } from "@/lib/vixMeanRev";
import { computeMsarSignal } from "@/lib/msarRegime";
import { readFragility, type FragilityRead } from "@/lib/gammaRegime";
import { HISTORICAL_ELEVATED_RISK_DAYS, HISTORICAL_FIRE_DAYS,
         HISTORICAL_STRONG_FIRE_DAYS } from "@/lib/historicalFragility";
import { isoDay } from "@/lib/dateAxis";
// Bar here is the OptionDashboard shape ({t: epoch seconds}), which the copied
// market components and their isoDay/monthlyTicks helpers all assume.
import type { Bar } from "@/lib/heikinashi";

/**
 * MARKET — a full port of OptionDashboard's market tab, re-sourced.
 *
 * Same panels, same signals, same captions: SPY heikin-ashi with stress bands
 * and crisis-onset dots, the SMA-vs-MSAR-vs-buy&hold signal backtest, VIX term
 * structure, and the 3-state HMM vol-regime nowcast. The lib and component
 * files are copied verbatim from that app rather than reimplemented, so the two
 * terminals cannot drift apart in what they compute.
 *
 * WHAT CHANGED, and why: the data no longer comes from an EC2/IBKR relay.
 *   SPY      -> Alpaca (the sponsor's own feed)
 *   VIX/3M/9D-> CBOE's public daily archive (not on Alpaca at all; Yahoo has
 *               stopped serving VIX3M/VIX9D history, verified before choosing)
 *   dealer γ -> Alpaca open interest, via the agent's own signal exporter
 * One panel is genuinely new: the S&P volatility surface, ported from
 * Volatility_Surface.py.
 *
 * One honest downgrade, stated rather than hidden: VIX here is a DAILY close,
 * not the relay's intraday tick. Panels label their as-of date accordingly.
 */

const WINDOWS: Record<string, number> = {
  "3M": 63, "6M": 126, "1Y": 252, "2Y": 504, "5Y": 1260, "8Y": 2160,
};
const WINDOW_KEYS = ["3M", "6M", "1Y", "2Y", "5Y", "8Y"] as const;
const POLL_MS = 60_000;
// FIRE_VIX: the dot-gate tier (short gamma AND VIX >= 22). OptionDashboard also
// carries a STRESS_VIX=20 tier, used only by its rolling net-GEX log merge --
// dropped here rather than kept as an unused constant, since this app has no
// such log yet (see riskDays below).
const FIRE_VIX = 22;

type Signal = {
  generated: string; spot: number; vix: number; gex: number; gex_sign: number;
  oi_date: string; n_contracts: number; cross_check: boolean;
  msar_long: boolean; p_high: number; p_slow: number; vol_era_threshold: number;
  trend_ok: number; ac_dir: number; gate: boolean; sleeve1: string; sleeve2: string;
  gamma_flip: number | null;
  expected_move: number | null;
  gamma_profile: { strike: number; gex: number }[];
};

type MarketDoc = {
  generated: string;
  spy: Bar[]; vix: Bar[]; vix3m: Bar[]; vix9d: Bar[];
  surface: SurfaceData;
  option_timing?: {
    calls_on: string[]; calls_off: string[];
    puts_on: string[]; puts_off: string[];
    coverage_start: string; coverage_end: string; config: string;
  };
  option_backtest?: {
    times: string[]; equity: number[]; in_market: number[];
    stats: { cagr: number; sharpe: number; maxdd: number };
    leverage: number; fill: string; config: string; coverage_end: string;
  };
  sources: Record<string, string>;
};

function ToggleChip({ label, on, onToggle, color }: {
  label: string; on: boolean; onToggle: () => void; color: string;
}) {
  return (
    <button onClick={onToggle} aria-pressed={on}
      className={`flex items-center gap-1 px-2 py-0.5 text-[10px] border transition-colors ${
        on ? "border-label text-label" : "border-grid text-dim hover:border-label"}`}>
      <span className="inline-block h-2 w-2 rounded-full" style={{
        backgroundColor: on ? color : "transparent", border: `1px solid ${on ? color : "#555"}` }} />
      {label}
    </button>
  );
}

export default function MarketPage() {
  const [win, setWin] = useState<string>("1Y");
  const [showBands, setShowBands] = useState(true);
  const [showDots, setShowDots] = useState(true);
  const [showTiming, setShowTiming] = useState(true);
  const [showMsar, setShowMsar] = useState(true);
  const [showOpt, setShowOpt] = useState(true);   // OUR AGENT's option timing
  const [doc, setDoc] = useState<MarketDoc | null>(null);
  const [sig, setSig] = useState<Signal | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [m, s] = await Promise.all([
        fetch("/api/market").then((r) => r.json()),
        fetch("/signal.json").then((r) => (r.ok ? r.json() : null)).catch(() => null),
      ]);
      if (m.error) throw new Error(m.error);
      setDoc(m);
      if (s) setSig(s);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "fetch failed");
    }
  }, []);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;
    const start = () => { if (!timer) timer = setInterval(load, POLL_MS); };
    const stop = () => { if (timer) { clearInterval(timer); timer = null; } };
    const onVis = () => { if (document.hidden) stop(); else { load(); start(); } };
    if (!document.hidden) { load(); start(); }
    document.addEventListener("visibilitychange", onVis);
    return () => { stop(); document.removeEventListener("visibilitychange", onVis); };
  }, [load]);

  const limit = WINDOWS[win];
  // Displayed slice. Signals below are computed on FULL history and only then
  // sliced — a timing signal re-seeded at the left edge of whatever window the
  // user picked would misstate its own position.
  const spy = useMemo(() => (doc?.spy ?? []).slice(-limit), [doc, limit]);
  const vix = useMemo(() => (doc?.vix ?? []).slice(-limit), [doc, limit]);
  const vix3m = useMemo(() => (doc?.vix3m ?? []).slice(-limit), [doc, limit]);
  const vix9d = useMemo(() => (doc?.vix9d ?? []).slice(-limit), [doc, limit]);

  const meanRev = useMemo(() => computeVixMeanRev(doc?.vix ?? []), [doc]);
  const msar = useMemo(() => computeMsarSignal(doc?.vix ?? []), [doc]);
  const term = buildVixTermStructure(vix, vix3m, vix9d);
  const loading = !doc && !error;

  const regimeNow = useMemo(
    () => (vix.length >= 10 ? currentRegime(regimeProbs(vix.map((b) => b.c))) : null), [vix]);

  const vixByDay = useMemo(
    () => Object.fromEntries((doc?.vix ?? []).map((b) => [isoDay(b.t), b.c])) as Record<string, number>,
    [doc]);

  const latestVix = doc?.vix?.length ? doc.vix[doc.vix.length - 1].c : null;
  const prevVix = doc?.vix && doc.vix.length > 1 ? doc.vix[doc.vix.length - 2].c : null;
  const fragility: FragilityRead | null =
    sig != null ? readFragility(sig.gex, latestVix) : null;

  // Historical onset sets + today's live read. OptionDashboard also merges a
  // rolling net-GEX log it has been accumulating; this app has no such log yet,
  // so it uses the backtested history plus today rather than inventing one.
  const riskDays = useMemo(() => {
    const d = new Set<string>(HISTORICAL_ELEVATED_RISK_DAYS);
    if (fragility?.elevatedRisk && spy.length) d.add(isoDay(spy[spy.length - 1].t));
    return Array.from(d);
  }, [fragility, spy]);

  const fireDays = useMemo(() => {
    const d = new Set<string>(HISTORICAL_FIRE_DAYS);
    if (fragility?.regime === "trapdoor" && (latestVix ?? 0) >= FIRE_VIX && spy.length) {
      d.add(isoDay(spy[spy.length - 1].t));
    }
    return Array.from(d);
  }, [fragility, latestVix, spy]);

  const strongDays = useMemo(() => Array.from(new Set(HISTORICAL_STRONG_FIRE_DAYS)), []);

  return (
    <main className="min-h-screen bg-bg">
      <TabNav active="/market" />

      <div className="flex flex-wrap items-center gap-3 border-b border-headerline
        bg-gradient-to-r from-[#0A1628] to-[#051020] px-4 py-2">
        <span className="text-xs tracking-[0.08em] text-label">MARKET · REGIME</span>
        <div className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-[0.06em] text-label">Lookback</span>
          <nav className="flex gap-1">
            {WINDOW_KEYS.map((k) => (
              <button key={k} onClick={() => setWin(k)}
                className={`px-2 py-0.5 text-xs border ${k === win
                  ? "border-cyan text-cyan" : "border-grid text-label hover:border-label"}`}>
                {k}
              </button>
            ))}
          </nav>
        </div>
        <div className="ml-auto flex items-center gap-4">
          {error && <span className="text-xs text-neg">data error: {error}</span>}
          <FragilityBadge read={fragility} />
          <VixPulse vix={latestVix} prev={prevVix}
            asOf={doc?.vix?.length ? isoDay(doc.vix[doc.vix.length - 1].t) : undefined} />
        </div>
      </div>

      {/* ---- live agent state: what this terminal is actually trading ---- */}
      {sig && (
        <section className="m-2 border border-grid">
          <div className="px-3 pt-2 text-[10px] uppercase tracking-[0.06em] text-label">
            Live agent state — two-sleeve options book · Δ0.70 · 7DTE
            <span className="text-dim"> — dealer γ from Alpaca open interest
              ({sig.n_contracts} contracts, OI {sig.oi_date}
              {sig.cross_check ? ", cross-check OK" : ", ⚠ CROSS-CHECK MISMATCH"})</span>
          </div>
          <div className="grid grid-cols-2 gap-px bg-grid p-px md:grid-cols-4 lg:grid-cols-7">
            {[
              ["SPOT", `$${sig.spot.toFixed(2)}`, undefined],
              ["DEALER GEX", `${(sig.gex / 1e9).toFixed(3)} $bn`, sig.gex_sign > 0 ? C.pos : C.neg],
              ["MSAR", sig.msar_long ? "RISK-ON" : "RISK-OFF", sig.msar_long ? C.pos : C.neg],
              ["p_slow", `${sig.p_slow.toFixed(3)} / ${sig.vol_era_threshold}`,
                sig.p_slow >= sig.vol_era_threshold ? C.neg : undefined],
              ["TREND VETO", sig.trend_ok > 0 ? "PASS" : "BLOCK", sig.trend_ok > 0 ? C.pos : C.neg],
              ["SLEEVE 1", sig.sleeve1, sig.gate ? C.pos : C.label],
              ["SLEEVE 2", sig.sleeve2, sig.ac_dir > 0 ? C.pos : sig.ac_dir < 0 ? C.neg : C.label],
            ].map(([label, value, tone]) => (
              <div key={label as string} className="bg-bg px-3 py-2">
                <div className="text-[9px] tracking-[0.08em] text-label">{label}</div>
                <div className="text-sm tabular-nums"
                     style={tone ? { color: tone as string } : undefined}>{value}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ---- SPY chart with regime overlays ---- */}
      <section className="m-2 border border-grid">
        <div className="px-3 pt-2 text-[10px] uppercase tracking-[0.06em] text-label">
          S&amp;P 500 (SPY) — daily heikin-ashi · <span style={{ color: C.red2 }}>red = VIX ≥ 25 (acute)</span>
          {" · "}<span style={{ color: "#FFB000" }}>amber = elevated risk (short γ + VIX ≥ 20)</span>
          {" · "}dots = firings (short γ + VIX ≥ 22, 20d window): <span style={{ color: C.neg }}>★ CRISIS ≥10%</span>
          {" "}<span style={{ color: C.gold }}>◆ dip ≥5%</span>
          {" "}<span className="text-dim">✕ miss</span>{" "}
          <span style={{ color: C.cyan }}>◇ pending (live)</span>
          <span className="text-dim"> — crisis lift 2.2× base; 6/7 crises since 2018 had the gate lit
          before the −10% breach. Still 91% of fires see no crisis — a risk gauge, not a forecast</span>
        </div>
        <div className="px-3 pb-1 text-[10px] uppercase tracking-[0.06em] text-label">
          Risk-managed timing — two independent causal signals:
          {" "}<span style={{ color: C.pos }}>▲</span><span style={{ color: C.neg }}>▼ SMA</span>
          {" "}(VIX vs 1.5×/1.0× of its 252d mean)
          {" · "}<span style={{ color: C.cyan }}>▲</span><span style={{ color: "#FF9500" }}>▼ MSAR</span>
          {" "}(2-regime Markov-switching AR filter on vol-of-vol)
          {meanRev.ready && (
            <span className="font-bold" style={{ color: meanRev.position === "long" ? C.pos : "#FFB000" }}>
              {" "}· SMA NOW: {meanRev.position === "long" ? "LONG" : "FLAT"}
            </span>
          )}
          {msar.ready && msar.pHigh != null && (
            <span className="font-bold" style={{ color: msar.position === "long" ? C.cyan : "#FF9500" }}>
              {" "}· MSAR NOW: {msar.position === "long" ? "LONG" : "FLAT"} (P
              {(100 * msar.pHigh).toFixed(0)}%)
            </span>
          )}
          <span className="text-dim"> — drawdown-defense overlays, not oracles.</span>
        </div>
        <div className="px-3 pb-1 text-[10px] uppercase tracking-[0.06em] text-label">
          Option trading timing — what OUR AGENT did (two-sleeve book, backtested):
          {" "}<span style={{ color: C.gold }}>▲ calls on</span>
          {" · "}<span style={{ color: "#BB86FC" }}>▼ calls off</span>
          {" · "}<span style={{ color: C.magenta }}>▼ puts on / ▲ puts off</span>
          {sig && (
            <span className="font-bold" style={{ color: sig.gate ? C.gold : "#BB86FC" }}>
              {" "}· NOW: {sig.sleeve1}{sig.ac_dir < 0 ? " + PUTS" : ""}
            </span>
          )}
          {doc?.option_timing && (
            <span className="text-dim"> — markers through {doc.option_timing.coverage_end}
            {" "}(chain-history end); the live read continues in the strip above</span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-1.5 px-3 py-1.5">
          <span className="mr-0.5 text-[9px] uppercase tracking-[0.08em] text-dim">show</span>
          <ToggleChip label="Stress bands" on={showBands} onToggle={() => setShowBands((v) => !v)} color="#FFB000" />
          <ToggleChip label="Crisis dots" on={showDots} onToggle={() => setShowDots((v) => !v)} color={C.neg} />
          <ToggleChip label="SMA timing" on={showTiming} onToggle={() => setShowTiming((v) => !v)} color={C.pos} />
          <ToggleChip label="MSAR timing" on={showMsar} onToggle={() => setShowMsar((v) => !v)} color="#FF9500" />
          <ToggleChip label="Option timing (ours)" on={showOpt} onToggle={() => setShowOpt((v) => !v)} color={C.gold} />
        </div>
        <MarketChart bars={spy}
          vixByDay={showBands ? vixByDay : undefined}
          riskDays={showBands ? riskDays : undefined}
          fireDays={showDots ? fireDays : undefined}
          strongDays={showDots ? strongDays : undefined}
          buyDays={showTiming ? meanRev.buyDays : undefined}
          sellDays={showTiming ? meanRev.sellDays : undefined}
          msarBuyDays={showMsar ? msar.buyDays : undefined}
          msarSellDays={showMsar ? msar.sellDays : undefined}
          optCallOnDays={showOpt ? doc?.option_timing?.calls_on : undefined}
          optCallOffDays={showOpt ? doc?.option_timing?.calls_off : undefined}
          optPutOnDays={showOpt ? doc?.option_timing?.puts_on : undefined}
          optPutOffDays={showOpt ? doc?.option_timing?.puts_off : undefined}
          loading={loading} />
      </section>

      {/* ---- signal backtest ---- */}
      <section className="m-2 border border-grid">
        <div className="px-3 pt-2 text-[10px] uppercase tracking-[0.06em] text-label">
          Signal backtest — SMA vs MSAR vs buy &amp; hold vs{" "}
          <span style={{ color: C.gold }}>OUR OPTION BOOK</span>, full available history
          (independent of the lookback selector above — a timing signal&apos;s record isn&apos;t
          meaningful sliced to 3 months)
          <span className="text-dim"> — SMA/MSAR/B&amp;H are client-side and frictionless (no cost
          model); ours is the REAL two-sleeve options backtest, cost-charged at real bid/ask,
          shown at 1.0x on purpose — this panel compares signal quality, and levering our line 4x
          would win the chart by construction while proving nothing. Curve ends
          {" "}{doc?.option_backtest?.coverage_end ?? "at chain-history end"}; the BACKTESTED tab
          carries the audited numbers and is the source of truth</span>
        </div>
        <BacktestPanel bars={doc?.spy ?? []}
          smaBuyDays={meanRev.buyDays} smaSellDays={meanRev.sellDays}
          msarBuyDays={msar.buyDays} msarSellDays={msar.sellDays}
          optionCurve={doc?.option_backtest ?? null}
          loading={loading} />
      </section>

      {/* ---- dealer gamma profile ---- */}
      <section className="m-2 border border-grid">
        <div className="px-3 pt-2 text-[10px] uppercase tracking-[0.06em] text-label">
          Dealer gamma profile — per strike, from Alpaca open interest ·{" "}
          <span style={{ color: C.pos }}>green = long γ (pinning)</span> ·{" "}
          <span style={{ color: C.neg }}>red = short γ (amplifying)</span>
          <span className="text-dim"> — cyan dashed = spot · gold = γ-flip (the level where dealer
          gamma changes sign) · shaded = ±1σ expected move · ◆ = dealer clusters. This is the
          surface sleeve 2 reads its direction from</span>
        </div>
        <GammaProfile chain={sig ? {
          spot: sig.spot,
          expected_move: sig.expected_move,
          gamma_flip: sig.gamma_flip,
          gex_profile: sig.gamma_profile,
        } : null} />
      </section>

      {/* ---- VIX term structure ---- */}
      <section className="m-2 border border-grid">
        <div className="px-3 pt-2 text-[10px] uppercase tracking-[0.06em] text-label">
          VIX term structure (VIX9D · VIX · VIX3M) — red band = backwardation (VIX3M &lt; VIX).
          Watch VIX9D cross up through VIX for the earliest stress tell.
          <span className="text-dim"> — CBOE daily closes</span>
        </div>
        <VixTermChart data={term} loading={loading} />
      </section>

      {/* ---- HMM vol regime ---- */}
      <section className="m-2 mb-6 border border-grid">
        <div className="px-3 pt-2 text-[10px] uppercase tracking-[0.06em] text-label">
          Vol regime nowcast — 3-state HMM on VIX, filtered (causal), live ·{" "}
          <span style={{ color: C.pos }}>calm ≈12.8</span> ·{" "}
          <span style={{ color: C.text }}>neutral ≈17.2</span> ·{" "}
          <span style={{ color: C.neg }}>volatile ≈25.7</span>
          {regimeNow && (
            <span className="font-bold" style={{ color:
              regimeNow.state === "calm" ? C.pos
              : regimeNow.state === "volatile" ? C.neg : C.text }}>
              {" "}· NOW: {regimeNow.state.toUpperCase()} {(100 * regimeNow.p).toFixed(0)}%
            </span>
          )}
          <span className="text-dim"> — context (where we are), not a forecast</span>
        </div>
        <RegimeStack vixBars={vix} loading={loading} />
      </section>
      {/* The S&P volatility surface was removed from THIS tab at TC's request
          (2026-08-31, caption first, then the chart too). It still renders on
          the Portfolio tab, and market.json keeps shipping `surface` for it. */}
    </main>
  );
}
