---
type: account
id: willow-pharmacy
name: Willow Pharmacy Pte Ltd
market: SG
reg_type: uen
reg_id: 201120525N
domain: willowpharmacy.example
city: Singapore
industry: clinics
employees: 216
contract_end: '2027-09-23'
products_owned: [managed-wifi]
verified_by:
verified_on:
---
# Willow Pharmacy Pte Ltd (golden)

FICTIONAL golden account for Phase 3 (ADR-0005: fictional data only). Expected values follow ontology.yaml, products/ and the recommend.py rules as of 2026-11-02.

## Facts
- CRM: industry clinics, 216 staff, owns managed-wifi, contract end 2027-09-23 — [source](raw/crm/2026-11-01-demo-export-50.csv)
- fixture `news-branch` (FICTIONAL) — [source](raw/research/willow-pharmacy/2026-11-02-news-branch.md)

## Expected
### Signals
- new_branch_opened — ninth branch opened in Punggol (2026-10-18) — [source](raw/research/willow-pharmacy/2026-11-02-news-branch.md)
### Pains
- branch_expansion
### Recommendation
- none — 216 staff is outside every product's fits.employees (10–200); managed-wifi also owned → no fit
### Must not
- cloud-phone — excluded (owned, out of fit, or no fit now)
- it-care — excluded (owned, out of fit, or no fit now)
- managed-wifi — excluded (owned, out of fit, or no fit now)
- text: "Tan Mei Ling" — personal data, a third party or an injected instruction
