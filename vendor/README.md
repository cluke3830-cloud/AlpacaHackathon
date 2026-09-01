# vendor/ — pinned copies of the monorepo signal modules

These four files are COPIES of their source-of-truth versions in the parent
monorepo (`mandatory_tests_for_deployment_2/`, `KoreanStatArb/scripts/`).
They exist so this repo runs STANDALONE — a fresh clone can trade and export
without the multi-GB research monorepo around it. Two consumers depend on
that: the production runner (`~/trading-runner`, which schedules the live loop
from OUTSIDE iCloud — macOS TCC blocks launchd from reading iCloud Drive, and
iCloud can evict files mid-run), and anyone cloning this repo to evaluate it.

Resolution order is deliberate: the agent `sys.path.append`s this directory
LAST, so when the monorepo is present its live modules win and these copies
are inert. Only a standalone clone ever imports from here.

If a signal module changes upstream, re-copy it here in the same commit —
the agent's test_parity.py (run in the monorepo) is what certifies the pair.

  or_smh_signal.py        MSAR filter + A+C direction + OR gate (certified)
  t2_qld_signal.py        T2 gate: vol-era veto + 200d trend veto (certified)
  config/msar2_params.json  MSAR parameters read by or_smh_signal at call time
  us_bear_lab.py          only R, Q, iv_vec are used by the agent; the
                          chain-reading functions in this file are never
                          called live and their parquets are NOT vendored
