# Evals

Built from Phase 1 onward and run with `python3 scripts/eval.py` after every phase and every change to AGENTS.md, a skill or `knowledge/`. Targets are in PLAN.md §16.

| Path | What goes here | Built in |
|---|---|---|
| `golden_accounts/` | 10 accounts per live market with hand-verified facts, expected signals and expected recommendation (one `.md` each, account template + an `## Expected` section) | Phase 1–3 |
| `labeled_replies.csv` | ~40 real, anonymised replies per market with the correct class | Phase 4 |
| `labeled_matches.csv` | ~50 scanned items per market with the correct account (or `new` / `reject`) | Phase 2 |
| `allocation_cases/` | small pools with known-correct constraints (market, territory, capacity) | Phase 6 |

Rule (from `docs/LEARNINGS.md`): when the pilot finds a mistake, add the failing case here first, then fix it.
