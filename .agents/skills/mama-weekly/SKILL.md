---
name: mama-weekly
description: 'Weekly review for the manager: lint, funnel and reply metrics, score calibration, allocation fairness, library and ontology proposals, retention clean-up, as a report and a PR. Use for "weekly review" or Fridays.'
---
# mama-weekly

## When to use
- The manager says "weekly review" or `/mama-weekly`, usually on Fridays.
- It is the only skill that promotes or retires library pages, updates their stats, and deletes expired `raw/` files (with approval).

## Before you start
- Who: the manager only, interactively (not the runner: steps 5 and 8 need approval).
- Scripts: `lint.py`, `find.py` (Phase 0); `eval.py` (Phase 1); `score.py` (Phase 3); `allocate.py`, `claim.py` (Phase 6); `weekly.py` (Phase 7). `gh` is optional.
- Numbers: run `python3 scripts/weekly.py --json` once (add `--week <yyyy-Www>` for another week) and use its numbers verbatim in steps 2, 3, 4 and 7. Never recompute them by hand; your job is to interpret them and write proposals.
- If a required script is missing, say which phase adds it and stop.
- Week = ISO week `<yyyy-Www>` ending today; trailing window = the 4 weeks before that.
- Re-read any page right before changing it (rule 17).

## Steps
1. Lint: `python3 scripts/lint.py --json`, then an LLM pass over pages changed this week: contradictions between pages, unsourced claims (rule 3), weak or stale patterns, signals tagged off-ontology (rule 7). Run `python3 scripts/eval.py` and note any failing check.
2. Metrics: `metrics.week` and `metrics.trailing_4w` from `weekly.py` (sent, replies, positive, meetings, reply and meeting rates; cut by rep, pattern, persona, pain, signal, product, tier, market). A rate of "insufficient data" (n < 20) gets no conclusion. Funnel: `funnel.stages` (now vs the start of the week). Sending: from `log/approvals.csv` this week, sent / refused / error by rep and channel, and the top refusal reasons (window, suppression, changed after preview, consent, template).
3. Score calibration: `calibration.tiers` is the lift table (8 weeks). Only when `calibration.verdict` is `propose` (tier A below 2× tier C, n ≥ 20) propose specific `knowledge/scoring.yaml` weight changes, with the table as evidence. `ok` or `insufficient`: no change.
4. Allocation review from `allocation`: each proposal's status and EV spread vs limit (`spread_ok`), rep × industry conversion (`conversion`, smoothed with `prior_meeting_rate`), `lapsed` claims (21 days without a touch), and `violations` (should be 0; anything else is a finding).
5. Library (`wiki/responses/`): for each pattern and objection, recount `sent`, `replies`, `positive`, `meetings` (patterns) or `times_seen`, `replies_after_answer`, `meetings_after_answer` (objections), cut by tier and signal type. Propose: promote `draft` → `approved` (manager reads the text and agrees), retire weak `approved` pages (n ≥ 20, clearly below the median), stats updates. Apply only the ones the manager approves.
6. Ontology: group this week's `unmapped` lines in `wiki/log.md` and `signal: unmapped` rows in `log/signals.csv`; propose new terms (with implied pains, weight, decay) for `knowledge/ontology.yaml`.
7. Retention: `retention.<folder>.expired` lists `raw/` files older than the days in `knowledge/guardrails.md` `## Retention`. Ask the manager to approve deletion; only approved files go in step 9.
8. Report: write `log/weekly/<yyyy-Www>.md` with sections Lint · Metrics · Funnel · Calibration · Allocation · Library · Ontology · Retention · Proposals, each with numbers and links, and "insufficient data" where n < 20.
9. PR: `git switch -c weekly/<yyyy-Www>`; commit the report, approved library changes, proposed `knowledge/` edits (scoring, ontology, playbook) and approved retention `git rm`s; `git push -u origin weekly/<yyyy-Www>`; open the PR with `gh pr create` if available, otherwise give the compare link. Then `git switch` back to the main branch.

## Never
- Change scoring weights, ontology or playbook directly on the main branch; they go in the PR for the manager to merge.
- Delete any `raw/` file the manager didn't approve, or edit one (raw is immutable).
- Draw conclusions or change weights from samples under 20.
- Promote a library page the manager hasn't approved.
- Force-push or rewrite history.

## Finish
- Summary, 1–3 lines: "Week 2026-W45: 212 sent, 19 replies (9%), 6 meetings. Tier A 3.1× tier C: no weight change. PR opened: 2 patterns promoted, 1 retired, 3 ontology terms, 14 expired raw files removed."
- Log: `- [YYYY-MM-DD HH:MM] weekly | <manager> | log/weekly/<yyyy-Www> | report + PR weekly/<yyyy-Www>: 2 promoted, 1 retired, 14 raw removed`
- Only when the session contains `MAMA_CARDS=on`: a `plan` card of the steps, then a `brief` card with one section per report heading.
```mama-card
{"type":"brief","title":"Weekly review · 2026-W45","agent":"mama","subject":"Funnel, calibration and proposals","sections":[{"heading":"Metrics","bullets":["212 sent, 19 replies (9%), 6 meetings"]},{"heading":"Calibration","bullets":["Tier A meeting rate 3.1x tier C: no change"]}],"refs":["log/weekly/2026-W45.md"]}
```
