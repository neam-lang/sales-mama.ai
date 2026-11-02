---
type: account
id: northwind-kopitiam
name: Northwind Kopitiam Pte Ltd
market: SG
reg_type: uen
reg_id: 201090479C
domain: northwindkopitiam.example
city: Singapore
industry: fnb
employees: 183
contract_end: '2026-12-29'
products_owned: [it-care]
verified_by:
verified_on:
---
# Northwind Kopitiam Pte Ltd (golden)

FICTIONAL golden account for Phase 3 (ADR-0005: fictional data only). Expected values follow ontology.yaml, products/ and the recommend.py rules as of 2026-11-02.

## Facts
- CRM: industry fnb, 183 staff, owns it-care, contract end 2026-12-29 — [source](raw/crm/2026-11-01-demo-export-50.csv)
- fixture `careers` (FICTIONAL) — [source](raw/research/northwind-kopitiam/2026-11-02-careers.md)
- contact: Daniel Lim — Operations Manager (ops_head) — [source](raw/research/northwind-kopitiam/2026-11-02-careers.md)

## Expected
### Signals
- hiring_ops_it — hiring an IT Executive for outlet systems (2026-10-25) — [source](raw/research/northwind-kopitiam/2026-11-02-careers.md)
- contract_ending — CRM contract ends 2026-12-29 — [source](raw/crm/2026-11-01-demo-export-50.csv)
### Pains
- it_stretch
- renewal_window
### Recommendation
- none — both pains are solved only by it-care, which is already owned (skip_if_owned) → no fit now
### Must not
- it-care — excluded (owned, out of fit, or no fit now)
