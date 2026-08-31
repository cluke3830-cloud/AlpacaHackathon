Two separate things were going on:

1. Your cd failed because my command was relative to the Trading Folder root. Use the absolute path (quotes matter — spaces in the path):

cd "/Users/lukecha/Library/Mobile Documents/com~apple~CloudDocs/Trading Folder/AlpacaHackathon/web" && npm run dev

2. The 500 on / was my fault — an orphaned next-server from my earlier smoke test was still squatting port 3000 serving a stale build. My pkill -f "next dev" killed the parent process but not the child. Cleared it, wiped .next, restarted clean.

All three tabs verified rendering real content:

Tab	Status	Confirmed rendering
/ Portfolio: 	200	PORTFOLIO vs SPY · VOLATILITY SURFACE · TRADEBOOK
/market:       	200	MARKET · REGIME + all panels
/backtest:  	200	Monte Carlo + percentiles

All four API routes returning live data. Server's up — just open the browser.

One note for later: if you ever hit a 500 on every route again, it's almost always the same cause — a stale next-server orphan, or running npm run build while next dev is live (that's the Next build/dev collision in your notes). Fix is the same both times:

pkill -f next-server; rm -rf .next; npm run dev

Portfolio will show $100k / flat / no trades until you flip the agent off DRY_RUN — the wiring is live, there's just nothing to draw yet.
LocalHost link:  http://localhost:3000 