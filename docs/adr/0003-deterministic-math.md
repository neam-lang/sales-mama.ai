# ADR-0003: Scores, recommendations and allocation are scripts

- **Status:** accepted
- **Context:** Numbers produced by a model drift between runs and are hard to audit or calibrate.
- **Decision:** `score.py`, `recommend.py` and `allocate.py` compute results from `knowledge/` files with explainable parts (`score_parts`, chains, per-assignment reasons). The model explains results, drafts messages and asks humans; it does not invent numbers.
- **Consequences:** weekly calibration can change weights through a PR; evals can check exact expectations.
