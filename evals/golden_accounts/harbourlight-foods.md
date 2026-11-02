---
type: account
id: harbourlight-foods
name: Harbourlight Foods
market: SG
reg_type:
reg_id:
domain: harbourlightfoods.example
city: Singapore
industry: fnb
employees: 90
contract_end: '2027-02-15'
products_owned: []
verified_by:
verified_on:
---
# Harbourlight Foods (golden)

FICTIONAL golden account for Phase 3 (ADR-0005: fictional data only). Expected values follow ontology.yaml, products/ and the recommend.py rules as of 2026-11-02.

## Facts
- CRM: industry fnb, 90 staff, owns nothing, contract end 2027-02-15 — [source](raw/crm/2026-11-01-demo-export-50.csv)
- fixture `site-news` (FICTIONAL) — [source](raw/research/harbourlight-foods/2026-11-02-site-news.md)
- contact: Rachel Goh — Managing Director (owner_md) — [source](raw/research/harbourlight-foods/2026-11-02-site-news.md)

## Expected
### Signals
- new_branch_opened — second central kitchen in Tampines (2026-10-20) — [source](raw/research/harbourlight-foods/2026-11-02-site-news.md)
- contract_ending — CRM contract ends 2027-02-15 — [source](raw/crm/2026-11-01-demo-export-50.csv)
### Pains
- branch_expansion
- renewal_window
### Recommendation
- it-care — contract_ending → renewal_window (strongest, fresh CRM signal); cloud-phone / managed-wifi follow via new_branch_opened → branch_expansion
### Must not
- text: "9123 4567" — personal data, a third party or an injected instruction
