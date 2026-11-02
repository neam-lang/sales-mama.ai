---
type: account
id: copperleaf-retail
name: Copperleaf Retail Pte Ltd
market: SG
reg_type: uen
reg_id: 201185361E
domain: copperleafretail.example
city: Singapore
industry: retail
employees: 78
contract_end: '2027-03-31'
products_owned: [managed-wifi]
verified_by:
verified_on:
---
# Copperleaf Retail Pte Ltd (golden)

FICTIONAL golden account for Phase 3 (ADR-0005: fictional data only). Expected values follow ontology.yaml, products/ and the recommend.py rules as of 2026-11-02.

## Facts
- CRM: industry retail, 78 staff, owns managed-wifi, contract end 2027-03-31 — [source](raw/crm/2026-11-01-demo-export-50.csv)
- fixture `news-outlet` (FICTIONAL) — [source](raw/research/copperleaf-retail/2026-11-02-news-outlet.md)

## Expected
### Signals
- new_branch_opened — fourth outlet opened at Jewel (2026-10-22) — [source](raw/research/copperleaf-retail/2026-11-02-news-outlet.md)
### Pains
- branch_expansion
### Recommendation
- cloud-phone — new_branch_opened → branch_expansion → cloud-phone; managed-wifi already owned
### Must not
- managed-wifi — excluded (owned, out of fit, or no fit now)
