---
name: mama-allocate
description: 'Propose an allocation of unowned leads across reps using scores, capacity, territory, continuity and smoothed meeting rates; explain each assignment; apply the manager''s approval or edits. Use for "allocate leads", "who should get these", or from mama-manager.'
---
# mama-allocate

## When to use
- The manager says "allocate leads", "who should get these?", or `/mama-allocate`; mama-manager hands off here for approvals.
- mama-nightly runs only step 1 (the proposal), never the approval.

## Before you start
- Who: the manager. Approval needs the manager in the conversation. The runner may create a proposal but never approves.
- Scripts: `allocate.py`, `claim.py` (Phase 6); `find.py` (Phase 0).
- If a required script is missing, say which phase adds it and stop.
- Read `knowledge/allocation.yaml` (mode, hard constraints, `max_ev_spread`, priors, `self_claim`) and `knowledge/markets.yaml` (`base_currency`, `fx`). If an FX rate needed for a live market is empty, say so: EV can't be compared across markets until the manager fills it.
- Re-read an account page before quoting it or assigning it by hand (rule 17).

## Steps
1. Proposal: if today's `log/allocation/<YYYY-MM-DD>.md` exists with no `status`, use it; otherwise run `python3 scripts/allocate.py`. It applies market, territory, capacity, suppression and `do_not_contact` constraints and continuity, assigns by EV greedily, runs fairness swaps, and writes `log/allocation/<date>.md` and `.csv`.
2. Present it by market:
   - Per rep: leads (A / B count), total EV in the base currency, and the script's reason ("Mei: F&B meeting rate 14% vs team 9%; 6 slots free; same group as Kopi Co").
   - The numbered rows the manager will refer to, the EV spread vs `max_ev_spread`, and anything left unassigned with why.
   - Rebalancing: lapsed claims (21 days without a touch) and overloaded reps, each with a proposed `claim.py --release` or `--reassign`.
3. Take the manager's decision in plain words:
   - "approve all" → `python3 scripts/allocate.py --approve all`.
   - "approve except 3 and 7" → `--approve` with the remaining row ids.
   - An edit ("give the logistics ones to Arun", "nothing for Mei this week") → re-run `allocate.py` with that as a constraint, using the options `python3 scripts/allocate.py --help` lists. If it has none for this, check market, territory and capacity yourself, apply the manager's explicit picks with `python3 scripts/claim.py --assign <rep> <id>...`, then re-run `allocate.py` for the rest. Show the new proposal and wait for approval again.
   - Rebalancing → `python3 scripts/claim.py --release <id>` or `--reassign <from> <to>`, only once the manager says yes.
4. `--approve` calls `claim.py --assign`, which sets `owner`, `allocated_on`, `allocated_by` and pushes. Read its output; report anything rejected (e.g. claimed meanwhile) and re-verify.
5. If `allocate.py` didn't, set the proposal's frontmatter `status:` to `applied` (or `rejected`), listing partial decisions under `## Decisions`.
6. Sync: `python3 scripts/sync.py`.

## Never
- Apply any assignment without the manager's explicit approval in this conversation (rule 6; PLAN.md §10).
- Assign across markets or outside a rep's territory, or over capacity (rule 14; `allocation.yaml` hard constraints).
- Assign a suppressed or `do_not_contact` lead (rule 2).
- Set `owner` by editing pages; only `claim.py` does it (rule 6).

## Finish
- Summary, 1–3 lines: "Approved 12 leads to 4 reps (EV spread 14%, limit 20%). 2 rejected: already claimed. 1 lapsed claim released to the pool."
- Log: `- [YYYY-MM-DD HH:MM] allocate | <manager> | log/allocation/<date> | proposal: 14 leads, 4 reps, spread 14%` and, after approval, `- [YYYY-MM-DD HH:MM] assign | <manager> | log/allocation/<date> | 12 assigned (A 4, B 8), 2 rejected`
- Only when the session contains `MAMA_CARDS=on`: one `allocation` card.
```mama-card
{"type":"allocation","title":"Allocation proposal · 3 Nov","agent":"allocator","total":14,"spread":0.14,"limit":0.2,"rows":[{"rep":"mei","market":"SG","leads_a":2,"leads_b":3,"ev":4100,"currency":"SGD","why":"F&B meeting rate 14% vs team 9%; 6 slots free"}],"refs":["log/allocation/2026-11-03.md"],"actions":[{"label":"Approve all","prompt":"approve all","style":"primary"}]}
```
