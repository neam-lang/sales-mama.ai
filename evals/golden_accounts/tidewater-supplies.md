---
type: account
id: tidewater-supplies
name: Tidewater Supplies Pte Ltd
market: SG
reg_type: uen
reg_id: 202556837D
domain: tidewatersupplies.example
city: Singapore
industry: fnb
employees: 16
contract_end: '2027-04-29'
products_owned: [cloud-phone, it-care]
verified_by:
verified_on:
---
# Tidewater Supplies Pte Ltd (golden)

FICTIONAL golden account for Phase 3 (ADR-0005: fictional data only). Expected values follow ontology.yaml, products/ and the recommend.py rules as of 2026-11-02.

## Facts
- CRM: industry fnb, 16 staff, owns cloud-phone, it-care, contract end 2027-04-29 — [source](raw/crm/2026-11-01-demo-export-50.csv)
- fixture `site-outlet` (FICTIONAL) — [source](raw/research/tidewater-supplies/2026-11-02-site-outlet.md)

## Expected
### Signals
- new_branch_opened — second outlet in Tanjong Pagar opened (2026-10-15) — [source](raw/research/tidewater-supplies/2026-11-02-site-outlet.md)
### Pains
- branch_expansion
### Recommendation
- managed-wifi — new_branch_opened → branch_expansion; cloud-phone and it-care already owned → managed-wifi
### Must not
- cloud-phone — excluded (owned, out of fit, or no fit now)
- it-care — excluded (owned, out of fit, or no fit now)
