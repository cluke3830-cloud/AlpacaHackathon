"""Every tunable in the agent, in one place, with provenance for each number.

RULE FOR THIS FILE: no number appears here without a comment saying where it
came from. A constant with no provenance is a fitted parameter in disguise, and
this fund has already paid for that lesson more than once.

Nothing here may be "tuned to taste" at deploy time. The constitution's bias #9
is explicit: an edge must deploy at the FILL AND PARAMETERS IT WAS TESTED AT.
If a value below needs to change, the backtest gets re-run first.
"""
from __future__ import annotations

import os

# --------------------------------------------------------------------------
# INSTRUMENT
# --------------------------------------------------------------------------
UNDERLYING = "SPY"
# Alpaca does not list SPX index options at all. The research ran on SPX chains
# (2018-2026, full regime coverage) and was then re-run end-to-end on SPY:
# blend +0.97 vs sleeve1 +0.53 over 2022-05..2026-06. It transfers.

# --------------------------------------------------------------------------
# CONTRACT SELECTION  (gex_source_check.py / option_blend_validate.py)
# --------------------------------------------------------------------------
TARGET_DELTA = 0.70     # deep ITM. Swept 0.60/0.70/0.80 x 5/7 DTE -- the blend
                        # beat sleeve 1 at ALL SIX settings, so 0.70 is a choice
                        # inside a flat region, not a peak that was fitted.
TARGET_DTE = 7          # weekly. NOT a free choice: the research chain data is
                        # DTE 1-8 by construction, so longer tenors are UNTESTED.
DTE_BAND = 3            # search window around TARGET_DTE
DTE_MIN, DTE_MAX = 1, 8
ROLL_FLOOR = 2          # roll out when <= 2 days remain

# --------------------------------------------------------------------------
# SIGNAL  (byte-identical to the certified T2 sleeve -- do not touch)
# --------------------------------------------------------------------------
GEX_DTE_MIN, GEX_DTE_MAX = 1, 8      # us_bear_lab.build_us_gex
GEX_MONEYNESS = 0.20                 # |log(K/S)| < 0.20, near-the-money only
MIN_GEX_CONTRACTS = 50
# Hard floor on how many contracts must survive the GEX filter before the agent
# will believe its own gamma number. Written after a real incident during build:
# Alpaca's snapshot endpoint caps at 100 symbols per request, the code asked for
# 400, every chunk failed, and dealer gamma was computed from the ONE contract
# that got through -- then printed a confident LONG. Nothing crashed. A checker,
# not a reminder, is the only thing that catches that class of bug.

MAX_VIX_STALENESS_DAYS = 4
# The MSAR filter reads VIX from outside Alpaca; if that feed silently stops
# updating, the regime signal freezes at its last value and the agent keeps
# trading on it. Refuse instead.

GEX_LAG_SESSIONS = 1
# Alpaca's open_interest_date is the PRIOR session -- OCC publishes date-d OI the
# next morning, so a live agent is structurally a lag-1 consumer whether it wants
# to be or not. This is the SAME configuration the causal test cleared (96% of
# Sharpe retained), so the deployment constraint and the honest-timing constraint
# are the same thing. Documented in gex_source_check.py.

# --------------------------------------------------------------------------
# SIZING  (option_sleeves.risk_blend, measured on the shipping config)
# --------------------------------------------------------------------------
RISK_WEIGHT_SLEEVE2 = 0.55
# Equal-RISK weight from the blend sweep. Converted to NOTIONAL weights using
# the realized daily vols of the shipping config (sleeve1 9.7%/yr, sleeve2
# 12.8%/yr): the risk weight is not the notional weight, and conflating them is
# how a "50/50" book ends up 65/35 in exposure.
NOTIONAL_W_SLEEVE1 = 0.5184
NOTIONAL_W_SLEEVE2 = 0.4816

GROSS_LEVERAGE = float(os.environ.get("AGENT_GROSS_LEVERAGE", "4.0"))
# Delta-notional as a multiple of account equity. 1.0 = exactly what the
# backtest measured (returns are normalized to spot-equivalent exposure).
#
# SET TO 4.0 BY TC's EXPLICIT DECISION, 2026-08-31, for the hackathon ONLY.
# Measured consequences at 4.0x, stated so nobody rediscovers them by surprise:
#   CAGR +42.7%   maxDD -34.5%   ann vol 35.1%   Sharpe +1.19 (UNCHANGED)
#   1-week P&L:  P(win) 51%, P5 -6.4%, P95 +9.5%, worst 1% -9.3%
# Sharpe is FLAT in leverage -- this buys tail width, not edge. The rationale
# is competition-specific: P&L is a judged criterion, the median 1-week
# outcome is ~flat at every leverage, so variance is the only way to place on
# that criterion, and the capital is paper.
#
# THIS IS NOT A REAL-MONEY SETTING. For live capital the same analysis says
# 1.0x or below (leverage_optimize.py): at 4x, P(drawdown worse than 6%) --
# the level at which the live gamma book was actually halted -- is ~100%
# within a year. Override with AGENT_GROSS_LEVERAGE before ever pointing this
# at a funded account.

# --------------------------------------------------------------------------
# EXECUTION
# --------------------------------------------------------------------------
LIMIT_COST_FRAC = 0.5
# Marketable limit at mid +/- half the half-spread. The headline backtest charged
# cost_frac=1.0 (pay the FULL quoted spread every trade), so if these limits fill
# we do strictly better than the tested number. That direction of error is the
# only acceptable one.
MAX_SPREAD_FRAC = 0.15   # skip a contract quoting wider than 15% of mid --
                         # a stale/absent market, not a price we want to cross.

# --------------------------------------------------------------------------
# RISK
# --------------------------------------------------------------------------
_BACKTEST_MAXDD_1X = 0.099        # measured, shipping config at 1.0x leverage

MAX_DRAWDOWN_HALT = float(os.environ.get("AGENT_MAX_DD", "0")) or min(
    0.25, 1.5 * _BACKTEST_MAXDD_1X * GROSS_LEVERAGE)
# Hard halt on drawdown from the agent's own high-water equity.
#
# MUST scale with leverage or it is meaningless. A fixed 15% was correct at
# 1.0x (1.5x the tested -9.9% maxDD) but at 4.0x the book's own historical
# maxDD is -34.5%, so a 15% halt would fire on ORDINARY variance and kill the
# agent mid-competition -- a circuit breaker that trips on normal operation is
# worse than none, because it trains you to raise it.
#
# Formula: 1.5x the tested maxDD at the CONFIGURED leverage, capped at 25%.
# The 25% cap is the binding constraint at 4.0x and is deliberate: the
# competition deployment is ~1 week, where the measured worst-1% outcome at
# 4.0x is -9.3%. A 25% loss inside a week is ~2.7 weekly sigma -- far more
# likely a BUG (runaway sizing, duplicate orders, bad fill loop) than a market
# move, which is exactly what a kill switch should be catching.
# Set AGENT_MAX_DD to override explicitly.
WARN_DRAWDOWN = min(0.15, MAX_DRAWDOWN_HALT * 0.55)

DRY_RUN = os.environ.get("AGENT_DRY_RUN", "true").lower() != "false"
# Defaults to TRUE and must be flipped deliberately by a human. Paper money does
# not change the discipline; it only changes the blast radius.

# --------------------------------------------------------------------------
# SCHEDULE
# --------------------------------------------------------------------------
DECIDE_MINUTES_BEFORE_CLOSE = 15
# The backtest convention is decide-at-close-t / execute-at-close-t. Running 15
# minutes before the bell is the closest live approximation that still leaves
# time for a limit order to fill.
CALENDAR = "XNYS"
