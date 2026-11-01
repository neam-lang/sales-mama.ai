---
name: mama-target
description: 'Work the rep''s allocated queue and, if allowed, self-claim tier C accounts from the pool. Use for "get my accounts", "what''s allocated to me".'
---
# mama-target

## When to use
- A rep asks "what's allocated to me?", "get my accounts", or `/mama-target`; also step 4 of mama-day.
- To claim a specific pool account ("claim acme-trading"), if it is tier C and self-claim is allowed.

## Before you start
- Who: a rep (or the manager for their own book). Assigning A/B leads to someone is mama-allocate, not this skill.
- Scripts: `find.py` (Phase 0) for the queue; `claim.py` (Phase 6) for self-claims.
- If a required script is missing, say which phase adds it and stop. (Without `claim.py` you can still list the queue; say claiming arrives in Phase 6.)
- Read `reps/<me>.md` (`markets`, `territory`, `max_active`, `daily_quota`) and `knowledge/allocation.yaml` (`self_claim`, `markets`, `territory`).
- Re-read each account page before claiming or quoting it (rule 17).

## Steps
1. Allocated queue: `python3 scripts/find.py --owner me --stage new --json`. Sort by tier (A, B, C), then score (high first). For each: `[[accounts/<id>]]`, name, market, tier, score, `allocated_on`, top `nba` if set.
2. Capacity: active accounts = `python3 scripts/find.py --owner me --json` minus closed stages (handed_over, nurture, closed_lost, do_not_contact). Free slots = `max_active` minus active.
3. If free slots > 0 and `allocation.yaml` has `self_claim: tier_c_only`:
   - `python3 scripts/find.py --owner none --tier C --json`, then keep only accounts whose `market` is in my `markets` and that fit my territory (industries, regions, employee range). Drop anything with `stage: do_not_contact` or a suppressed domain in `wiki/suppression.csv`.
   - Show the top 5 by score, with the reason each fits.
   - Claim only on request: `python3 scripts/claim.py <id> [<id>...]`. Never claim tier A or B; those go through the manager's allocation.
4. Read `claim.py` output. If an account was lost to another claim or is no longer tier C, report it plainly ("acme-trading was claimed by arun at 08:52").
5. Hand-off: offer to research and draft the new accounts (mama-research → mama-recommend → mama-draft), within quota.

## Never
- Self-claim tier A or B, or claim at all if `self_claim` is not `tier_c_only` (rule 6).
- Claim outside my markets or territory (rule 14; `allocation.yaml` hard constraints).
- Edit `owner`, `allocated_on` or `claimed_on` by hand; only `claim.py` sets them.
- Show other reps' allocated queues to a rep (rule 16).

## Finish
- Summary, 1–3 lines: "6 new allocated accounts (A 1, B 2, C 3). 4 free slots; claimed 2 tier C: lumen-clinic, sunrise-logistics. Next: research the tier A one?"
- Log (only if something was claimed; `claim.py` may log it too, so don't duplicate): `- [YYYY-MM-DD HH:MM] claim | <rep> | accounts/lumen-clinic | self-claimed tier C`
- Only when the session contains `MAMA_CARDS=on`: one `account` card per newly allocated tier A account, or an `error` card if claiming failed.
```mama-card
{"type":"account","title":"Sunrise Logistics","agent":"mama","id":"sunrise-logistics","name":"Sunrise Logistics","market":"SG","tier":"A","score":0.74,"stage":"new","owner":"mei","refs":["wiki/accounts/sunrise-logistics.md"],"actions":[{"label":"Research it","prompt":"/mama-research sunrise-logistics","style":"primary"}]}
```
