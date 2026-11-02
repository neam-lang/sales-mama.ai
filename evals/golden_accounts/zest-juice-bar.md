---
type: account
id: zest-juice-bar
name: Zest Juice Bar Pte Ltd
market: SG
reg_type: uen
reg_id: 201577307D
domain: zestjuicebar.example
city: Singapore
industry: fnb
employees: 164
contract_end: '2026-10-15'
products_owned: []
verified_by:
verified_on:
---
# Zest Juice Bar Pte Ltd (golden)

FICTIONAL golden account for Phase 3 (ADR-0005: fictional data only). Expected values follow ontology.yaml, products/ and the recommend.py rules as of 2026-11-02.

## Facts
- CRM: industry fnb, 164 staff, owns nothing, contract end 2026-10-15 — [source](raw/crm/2026-11-01-demo-export-50.csv)
- fixture `news-closure` (FICTIONAL) — [source](raw/research/zest-juice-bar/2026-11-02-news-closure.md)

## Expected
### Signals
- layoffs_or_closure — closing three of seven outlets by year end (2026-10-20) — [source](raw/research/zest-juice-bar/2026-11-02-news-closure.md)
### Pains
- none (negative signal)
### Recommendation
- none — active negative signal layoffs_or_closure → no recommendation now
### Must not
- cloud-phone — excluded (owned, out of fit, or no fit now)
- it-care — excluded (owned, out of fit, or no fit now)
- managed-wifi — excluded (owned, out of fit, or no fit now)
- text: "Alan Koh" — personal data, a third party or an injected instruction
