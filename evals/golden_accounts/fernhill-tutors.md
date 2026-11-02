---
type: account
id: fernhill-tutors
name: Fernhill Tutors Pte Ltd
market: SG
reg_type: uen
reg_id: 201365008A
domain: fernhilltutors.example
city: Singapore
industry: professional_services
employees: 55
contract_end: '2027-09-29'
products_owned: []
verified_by:
verified_on:
---
# Fernhill Tutors Pte Ltd (golden)

FICTIONAL golden account for Phase 3 (ADR-0005: fictional data only). Expected values follow ontology.yaml, products/ and the recommend.py rules as of 2026-11-02.

## Facts
- CRM: industry professional_services, 55 staff, owns nothing, contract end 2027-09-29 — [source](raw/crm/2026-11-01-demo-export-50.csv)
- fixture `news-move` (FICTIONAL) — [source](raw/research/fernhill-tutors/2026-11-02-news-move.md)
- fixture `site-contract` (FICTIONAL) — [source](raw/research/fernhill-tutors/2026-11-02-site-contract.md)

## Expected
### Signals
- office_move — moved main centre to Bishan (2026-06-01) — stale, older than 90 days — [source](raw/research/fernhill-tutors/2026-11-02-news-move.md)
- contract_win — appointed to run enrichment for five schools (2026-10-26) — [source](raw/research/fernhill-tutors/2026-11-02-site-contract.md)
### Pains
- scale_up
### Recommendation
- cloud-phone — contract_win → scale_up → cloud-phone and it-care tie; higher SG typical_value wins (cloud-phone). office_move is past decay_days, so no connectivity_reset
### Must not
- managed-wifi — excluded (owned, out of fit, or no fit now)
