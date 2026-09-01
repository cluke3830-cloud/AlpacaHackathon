#!/bin/zsh
# Daily close job — the autonomous loop.
#   15:45 ET Mon–Fri via launchd (com.alpaca.hackathon.agent).
#
# The AGENT decides whether today is tradeable, not the scheduler: run_agent's
# step 1 is a real exchange-calendar gate (holidays, half-days), so this script
# fires blindly on weekdays and lets the agent refuse. A timer has no holiday
# awareness on its own — the constitution's universal calendar rule.
#
# AGENT_DRY_RUN=false is EXPLICIT here by TC's go-live decision 2026-08-31
# (first live trade: 8x SPY260908C00761000 @ 8.58). Remove it and the agent
# reverts to dry-run — that is the kill path if you ever want the loop armed
# but not trading.
#
# After the trading decision, the two DAILY exporters refresh so the dashboard
# stays live without a human: signal.json (the agent's market read) and
# market.json (SPY/VIX/surface/timing). backtest.json is NOT here on purpose —
# its inputs are the static 2018–2026 chain history; regenerate manually when
# the config changes, not nightly (a nightly rerun would only reroll the MC
# seed and make the "generated" timestamp lie about freshness).

set -uo pipefail
DIR="${0:A:h}"
# ABSOLUTE interpreter: launchd's PATH is the bare system one, where `python3`
# is Apple's interpreter without alpaca-py. This bit during the runner move.
PY="/opt/miniconda3/bin/python3"
LOG="$DIR/logs/agent_$(date +%Y%m%d).log"
mkdir -p "$DIR/logs"

{
  echo "================ $(date '+%Y-%m-%d %H:%M:%S %Z') ================"
  cd "$DIR"
  AGENT_DRY_RUN=false "$PY" -u run_agent.py
  rc=$?
  echo "--- agent exit: $rc ---"
  cd "$DIR/.."
  "$PY" -u scripts/export_signal_json.py && echo "--- signal.json refreshed ---"
  "$PY" -u scripts/export_market_json.py && echo "--- market.json refreshed ---"
  echo "================ done $(date '+%H:%M:%S') ================"
} >> "$LOG" 2>&1
