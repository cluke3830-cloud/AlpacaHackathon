/**
 * Server-only Alpaca client.
 *
 * NEVER import this from a client component -- it holds the secret key. Every
 * consumer goes through an /api route, which is why the routes exist at all.
 *
 * Deliberately hand-rolled fetch rather than the alpaca-js SDK: we need exactly
 * five endpoints, and a dependency that ships its own auth/retry/websocket
 * machinery is more surface than this earns.
 */

const TRADING = "https://paper-api.alpaca.markets";
const DATA = "https://data.alpaca.markets";

function keys() {
  const k = process.env.ALPACA_API_KEY;
  const s = process.env.ALPACA_SECRET_KEY;
  if (!k || !s) {
    throw new Error(
      "ALPACA_API_KEY / ALPACA_SECRET_KEY not set. Copy .env.example to " +
        ".env.local and fill them in (same paper account the agent trades)."
    );
  }
  return { "APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s };
}

async function get(base: string, path: string, revalidate = 30) {
  const r = await fetch(`${base}${path}`, {
    headers: keys(),
    next: { revalidate },
  });
  if (!r.ok) {
    const body = await r.text().catch(() => "");
    throw new Error(`Alpaca ${r.status} on ${path}: ${body.slice(0, 200)}`);
  }
  return r.json();
}

export type Account = {
  equity: number;
  cash: number;
  last_equity: number;
  buying_power: number;
  account_number: string;
  status: string;
};

export async function account(): Promise<Account> {
  const a = await get(TRADING, "/v2/account", 15);
  return {
    equity: Number(a.equity),
    cash: Number(a.cash),
    last_equity: Number(a.last_equity),
    buying_power: Number(a.buying_power),
    account_number: a.account_number,
    status: a.status,
  };
}

export type Position = {
  symbol: string;
  qty: number;
  side: string;
  market_value: number;
  cost_basis: number;
  unrealized_pl: number;
  unrealized_plpc: number;
  asset_class: string;
  current_price: number;
};

export async function positions(): Promise<Position[]> {
  const p = await get(TRADING, "/v2/positions", 15);
  return (p as any[]).map((x) => ({
    symbol: x.symbol,
    qty: Number(x.qty),
    side: x.side,
    market_value: Number(x.market_value),
    cost_basis: Number(x.cost_basis),
    unrealized_pl: Number(x.unrealized_pl),
    unrealized_plpc: Number(x.unrealized_plpc),
    asset_class: x.asset_class,
    current_price: Number(x.current_price ?? 0),
  }));
}

/**
 * Account equity history. Alpaca's own curve -- authoritative for "what did
 * this account actually do", which is exactly what a P&L-judged competition
 * should be showing rather than a curve we reconstruct ourselves.
 */
export type PortfolioHistory = {
  timestamp: number[];
  equity: number[];
  profit_loss: number[];
  profit_loss_pct: number[];
  base_value: number;
};

export async function portfolioHistory(
  period = "1M",
  timeframe = "1D"
): Promise<PortfolioHistory> {
  const h = await get(
    TRADING,
    `/v2/account/portfolio/history?period=${period}&timeframe=${timeframe}&intraday_reporting=market_hours&pnl_reset=no_reset`,
    30
  );
  return {
    timestamp: h.timestamp ?? [],
    equity: (h.equity ?? []).map(Number),
    profit_loss: (h.profit_loss ?? []).map(Number),
    profit_loss_pct: (h.profit_loss_pct ?? []).map(Number),
    base_value: Number(h.base_value ?? 0),
  };
}

export type Order = {
  symbol: string;
  side: string;
  qty: number;
  filled_qty: number;
  filled_avg_price: number | null;
  status: string;
  submitted_at: string;
  filled_at: string | null;
  order_class: string;
  asset_class: string;
};

/** Closed orders, newest first -- the trade log at the bottom of the sketch. */
export async function orders(limit = 200): Promise<Order[]> {
  const o = await get(
    TRADING,
    `/v2/orders?status=all&limit=${limit}&direction=desc&nested=true`,
    20
  );
  return (o as any[]).map((x) => ({
    symbol: x.symbol,
    side: x.side,
    qty: Number(x.qty ?? 0),
    filled_qty: Number(x.filled_qty ?? 0),
    filled_avg_price: x.filled_avg_price ? Number(x.filled_avg_price) : null,
    status: x.status,
    submitted_at: x.submitted_at,
    filled_at: x.filled_at,
    order_class: x.order_class ?? "simple",
    asset_class: x.asset_class ?? "us_equity",
  }));
}

export type Bar = { t: string; o: number; h: number; l: number; c: number; v: number };

/**
 * Daily/intraday bars. Used for the SPY benchmark line and the market tab.
 * `feed=iex` because a paper/free plan has no SIP entitlement -- asking for
 * SIP returns 403 rather than degrading, so it is pinned explicitly.
 */
export async function bars(
  symbol: string,
  timeframe = "1Day",
  start?: string,
  limit = 1000
): Promise<Bar[]> {
  const s =
    start ??
    new Date(Date.now() - 400 * 864e5).toISOString().slice(0, 10);
  const q = `/v2/stocks/${symbol}/bars?timeframe=${timeframe}&start=${s}&limit=${limit}&adjustment=all&feed=iex`;
  const d = await get(DATA, q, 60);
  return (d.bars ?? []) as Bar[];
}
