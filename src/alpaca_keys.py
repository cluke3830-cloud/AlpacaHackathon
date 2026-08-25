"""Single source for Alpaca credentials. Nothing else in this project should
contain a key literal.

Resolution order:
  1. environment  ALPACA_API_KEY / ALPACA_SECRET_KEY
  2. AlpacaHackathon/.env         (gitignored — see .env.example)

NOTE: a paper key is currently committed in the repo at
`Past Strategies/Alpaca/Option_Session/Session_5.py`. That key should be rotated
in the Alpaca dashboard; this module exists so no NEW file ever hardcodes one.
"""
from __future__ import annotations

import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def _from_env_file(key: str):
    if not _ENV_FILE.exists():
        return None
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return None


def _get(name: str) -> str:
    val = os.environ.get(name) or _from_env_file(name)
    if not val:
        raise RuntimeError(
            f"{name} not set. Put it in AlpacaHackathon/.env (see .env.example) "
            f"or export it. No key literals in source."
        )
    return val


API_KEY = _get("ALPACA_API_KEY")
SECRET_KEY = _get("ALPACA_SECRET_KEY")

# Back-compat aliases for the research scripts.
K = K_API = API_KEY
S = S_API = SECRET_KEY
