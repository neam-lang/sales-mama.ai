---
name: mama-brief
description: 'Prepare a one-page brief for a call with an owned account, or a meet-list for a trade event. Use before a call, meeting or event ("brief me on <company|event>").'
---
# mama-brief

## When to use
- Before a call or meeting: "brief me on <company>" or `/mama-brief <account-id>`.
- Before a trade event: "brief me on <event>" or `/mama-brief <event-id>` (e.g. `sme-expo-2026`).
- If the name matches both an account and an event, ask which.

## Before you start
- Who: the account's `owner` (or the manager) for account briefs; any rep for event briefs, but the meet-list shows only their own accounts.
- Scripts: `find.py` (Phase 0). Score and recommendation fields come from `score.py` / `recommend.py` (Phase 3); if they're empty, say "not scored yet" rather than stopping.
- If a required script is missing, say which phase adds it and stop.
- Re-read the account page (or event page and each matched account page) and frontmatter now (rule 17).

## Steps: account brief
1. Check `owner` = me, or I'm the manager (rules 6, 16).
2. Gather from the page and linked files only: contacts (`## Contacts` → contact pages), `## Signals`, `## Pains & hypotheses`, `## Recommendation`, `## Touch history`, `## Open objections`, `## VAM notes` (nba, risk), and my rows in `log/touches.csv` for this account.
3. Write the brief, one page, in this order:
   - **Who**: company one-liner, market, size, contacts on the call with title and persona.
   - **Why now**: dated signals, each with its source link (rule 3).
   - **What we believe**: pains and the recommendation chain (signal → pain → product → proof), price in the market's currency.
   - **History**: touches so far and what they said.
   - **Likely objections**: each with the matching `approved` response from `wiki/responses/objections/`; "no approved answer yet" if none.
   - **Questions**: 3–5 open questions that test the pains.
   - **Goal and next step**: the call goal and the next step to propose.
4. Write it into the account page as `## Call brief (<YYYY-MM-DD>)`, replacing the template's empty `## Call brief` heading or an older brief. Set `updated:` today. Don't change `stage`.

## Steps: event brief
1. Open `wiki/events/<id>.md` (dates, venue, `matched_accounts`, `## Matched accounts`).
2. Keep only matched accounts I own (manager: all, grouped by owner). Re-read each.
3. Sort by tier (A, B, C), then score. For each: `[[accounts/<id>]]`, tier, a one-line hook from a cited signal (e.g. "exhibiting at booth B12; contract_win 28 Oct"), and the open `next_action`.
4. Write the list into the event page under `## Plan`, in a sub-block headed `### <rep> (<YYYY-MM-DD>)` so reps don't overwrite each other. Set `updated:` today.
5. Offer pre-event drafts (step `first` or a `hook` follow-up) through mama-draft, within quota and the market's send window.

## Never
- Put anything in a brief that isn't on the account page with a source, or in `knowledge/` (rules 3, 5).
- Suggest objection answers from draft or retired library pages.
- Include accounts owned by other reps in a rep's event list (rule 16).
- Add personal details about contacts beyond their business role (rule 8).

## Finish
- Summary, 1–3 lines: "Call brief for Harbourlight Foods saved (Thu 10:00 with Jane Tan). Goal: agree a 2-site pilot." or "SME Expo 2026 meet-list: 7 of your accounts (A 2, B 3, C 2), saved to the event plan."
- Log: `- [YYYY-MM-DD HH:MM] brief | <user> | accounts/<id> | call brief for 2026-11-05` (event: target `events/<id>`, summary `meet-list, 7 accounts`).
- Only when the session contains `MAMA_CARDS=on`: one `brief` card (account briefs may add an `account` card).
```mama-card
{"type":"brief","title":"Call brief · Harbourlight Foods","agent":"mama","subject":"Thu 5 Nov 10:00 with Jane Tan","sections":[{"heading":"Why now","bullets":["contract_win: catering contract, 28 Oct"]},{"heading":"Questions","bullets":["How many new sites go live by March?"]}],"refs":["wiki/accounts/harbourlight-foods.md"]}
```
