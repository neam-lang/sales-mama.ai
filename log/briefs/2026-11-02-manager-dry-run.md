---
type: brief
kind: manager
date: 2026-11-02
run: 2026-11-02-1700
dry_run: true
created_by: praveen
---
# Manager brief · 2026-11-02 · DRY RUN

Dry run: scan, snapshot, resolve and score ran in memory. No account or event pages were written, no VAMs ran, and no allocation proposal was made.

## run_status
- ok: true
- started: 2026-11-02 17:00
- finished: 2026-11-02 17:12
- markets: SG
- items: 39
- linked: 0
- review: 0
- new_leads: 14 (logged only, no pages created)
- errors: 0 hard, 4 soft

Steps:
1. pull: ok (already up to date)
2. scan: ok, with soft errors. 39 items: 23 already seen, 14 new_lead, 2 events, 0 linked, 0 review, 0 dropped
   - sg-acra-new-cos: 30 items (capped at 30)
   - sg-gebiz-awards: 0 items (dataset ends 2026-03-31, stale)
   - sg-crm-contract-ends: 7 items (all already seen)
   - sg-news-sme: 0 items (nothing in the 7-day window)
   - sg-grants-news: 0 items (EDGE consolidation news predates the window)
   - sg-events-calendar: 2 events (Singapore EXPO page); EnterpriseSG PDF unreadable
   - sg-events-exhibitors: 0 (no exhibitors_url configured)
3. score: ok (`score.py --dry-run`). 80 accounts: A 8 · B 5 · C 67 · 0 changed · no hot jumps
4. VAMs: skipped (dry-run)
5. allocation: skipped (dry-run)
6. brief: ok (this file)
7. lint: ok (0 errors, 0 warnings)
8. books: skipped (dry-run writes no wiki pages)
9. log + sync: see wiki/log.md

Soft errors and the fix to try:
- sg-acra-new-cos capped at 30. Raise `max_items_per_run` for this source, or shorten `lookback_days` (45).
- sg-gebiz-awards returned 0 because the MOF dataset ends 2026-03-31. Pause the source until MOF refreshes it.
- sg-events-calendar: WebFetch could not read the EnterpriseSG trade-fair PDF (no text layer came back). Add a text-extraction step to `fetch_dataset.py` for PDFs, or check the list by hand.
- The events scout and the news scout had no Bash access in this session. The nightly runner ran `fetch_dataset.py` for the events scout. Allow `python3 scripts/fetch_dataset.py` for the scout agent so it can run the fetch itself.

Check: this dry run wrote 14 `new_lead` rows to `log/signals.csv` but created no pages. The next real run will mark those items `seen` and skip them, so the pages may never be created. Check whether `resolve.py --attach` creates pages for rows that are logged but not attached. If it does not, remove these 14 rows before the first real run, or re-run without dry-run.

Event classification needs a human check: "Asia Pacific Food Expo" was classed as B2B from its name only, and it may be a consumer fair.

## Hot accounts
No score jumps this run (0 changed). Current tier A, all SG:

| Account | Owner | Score | Signal |
|---|---|---|---|
| [[accounts/pebble-bay-couriers]] | none | 0.88 | contract_ending 2027-01-07 — [source](../../raw/crm/2026-11-01-demo-export-50.csv) |
| [[accounts/harbourlight-foods]] | none | 0.87 | contract_ending 2027-02-15 — [source](../../raw/crm/2026-11-01-demo-export-50.csv) |
| [[accounts/northwind-kopitiam]] | none | 0.87 | contract_ending 2026-12-29 — [source](../../raw/crm/2026-11-01-demo-export-50.csv) |
| [[accounts/nimbus-clinics]] | praveen | 0.86 | contract_ending 2026-12-31 — [source](../../raw/crm/2026-11-01-demo-export-50.csv) |
| [[accounts/beacon-hardware]] | none | 0.85 | contract_ending 2027-02-24 — [source](../../raw/crm/2026-11-01-demo-export-50.csv) |
| [[accounts/rivet-studio-interiors]] | none | 0.84 | contract_ending 2027-02-20 — [source](../../raw/crm/2026-11-01-demo-export-50.csv) |
| [[accounts/dovetail-movers]] | none | 0.82 | contract_ending 2026-11-29 — [source](../../raw/crm/2026-11-01-demo-export-50.csv) |
| [[accounts/tidewater-supplies]] | none | 0.72 | see account page |

Dovetail Movers' contract ends 2026-11-29, the soonest of these, and the account has no owner.

## At risk
- praveen: 0 at risk (3 active: nimbus-clinics, kestrel-physio, lotus-learning-hub). VAMs did not run in dry-run, so risk flags were not refreshed.

## Allocation proposal
Skipped in dry-run. Existing proposal: [log/allocation/2026-11-02.md](../allocation/2026-11-02.md): 15 leads to praveen, EV spread 0% (limit 20%). Awaiting manager approval.

## Review queue
0 undecided rows in `log/review.csv`.

## Book summaries
No VAM summaries this run (dry-run; `log/briefs/2026-11-02-books.md` not written).

## Lint
0 errors, 0 warnings.

## New leads (logged, not created)
Atlas Energy Capital (professional_services), Aetherstone (retail), Avis World College (education), Aestral Learning Hub (Hougang) (education; closest is lotus-learning-hub at 0.53, not linked), Mawkoon (retail), Karubi CR 478 (fnb), Kai Personal Training (education), Revora Motors (retail), RSD Global Solution (logistics), Rezeki 631 (fnb), The Creator's Atelier (professional_services), Tip Top Fashion (retail), Turbulence Xpress (logistics), Taifeng Xpress (logistics). All from sg-acra-new-cos, signal new_company.

## Events
- Asia Pacific Food Expo 2026: 6–9 Nov, Singapore EXPO (fnb, retail) — [source](../../raw/signals/2026-11-02/sg-events-calendar/asia-pacific-food-expo-2026.md)
- IntraLogisteX Singapore 2026: 2–3 Dec, Singapore EXPO (logistics) — [source](../../raw/signals/2026-11-02/sg-events-calendar/intralogistex-singapore-2026.md)
