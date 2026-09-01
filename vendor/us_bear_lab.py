"""MINIMAL vendor extract of KoreanStatArb/scripts/us_bear_lab.py.

The agent imports exactly three names from that module: R, Q, iv_vec. The
first vendor attempt copied the WHOLE file — and the standalone-clone test
immediately failed on it, because the full module does
`from bear_strategy_lab import ...` at import time, dragging the research
import web (and ultimately its parquet data) into a repo whose entire point
is to run without the monorepo. A vendor copy that imports the monorepo is
not a vendor copy.

So this file carries a VERBATIM extract of just those three definitions
(source: us_bear_lab.py lines 31 and 34-45 as of 2026-09-01). If iv_vec or
the rate/dividend constants ever change upstream, re-extract here in the same
commit — the monorepo's parity suite (agent/test_parity.py, gex_parity at
1e-15 tolerance) is what proves the pair still agree, since inside the
monorepo the ORIGINAL module wins the import and this file is inert.
"""
import numpy as np
from scipy.stats import norm

# Risk-free rate and continuous dividend yield used by every IV/greek
# computation in this book -- same values the whole research line was
# validated with. Change upstream first, never here alone.
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
