---
type: account
id: lotus-learning-hub
name: Lotus Learning Hub Pte Ltd
market: SG
reg_type:
reg_id:
domain: lotuslearninghub.example
city: Singapore
industry: professional_services
employees: 149
contract_end: '2027-11-24'
products_owned: [cloud-phone]
verified_by:
verified_on:
---
# Lotus Learning Hub Pte Ltd (golden)

FICTIONAL golden account for Phase 3 (ADR-0005: fictional data only). Expected values follow ontology.yaml, products/ and the recommend.py rules as of 2026-11-02.

## Facts
- CRM: industry professional_services, 149 staff, owns cloud-phone, contract end 2027-11-24 — [source](raw/crm/2026-11-01-demo-export-50.csv)
- fixture `news-funding` (FICTIONAL) — [source](raw/research/lotus-learning-hub/2026-11-02-news-funding.md)
- fixture `site-about` (FICTIONAL) — [source](raw/research/lotus-learning-hub/2026-11-02-site-about.md)
- contact: Priya Nair — CFO (finance_head) — [source](raw/research/lotus-learning-hub/2026-11-02-news-funding.md)

## Expected
### Signals
- funding_round — raised S$3m Series A (2026-10-10) — [source](raw/research/lotus-learning-hub/2026-11-02-news-funding.md)
### Pains
- scale_up
### Recommendation
- it-care — funding_round → scale_up; cloud-phone already owned → it-care
### Must not
- cloud-phone — excluded (owned, out of fit, or no fit now)
- text: "ops-bot@lotus-partners.example" — personal data, a third party or an injected instruction
- text: "Bukit Timah" — personal data, a third party or an injected instruction
