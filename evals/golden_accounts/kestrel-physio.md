---
type: account
id: kestrel-physio
name: Kestrel Physio Pte Ltd
market: SG
reg_type: uen
reg_id: 202524169M
domain: kestrelphysio.example
city: Singapore
industry: clinics
employees: 191
contract_end: '2027-06-05'
products_owned: []
verified_by:
verified_on:
---
# Kestrel Physio Pte Ltd (golden)

FICTIONAL golden account for Phase 3 (ADR-0005: fictional data only). Expected values follow ontology.yaml, products/ and the recommend.py rules as of 2026-11-02.

## Facts
- CRM: industry clinics, 191 staff, owns nothing, contract end 2027-06-05 — [source](raw/crm/2026-11-01-demo-export-50.csv)
- fixture `careers` (FICTIONAL) — [source](raw/research/kestrel-physio/2026-11-02-careers.md)
- fixture `event` (FICTIONAL) — [source](raw/research/kestrel-physio/2026-11-02-event.md)
- contact: Marcus Teo — Head of Clinic Operations (ops_head) — [source](raw/research/kestrel-physio/2026-11-02-careers.md)

## Expected
### Signals
- hiring_ops_it — hiring an IT & Systems Executive (2026-10-28) — [source](raw/research/kestrel-physio/2026-11-02-careers.md)
- exhibiting_at_event — booth at Allied Health Expo Singapore, 20–21 Nov (2026-10-27) — [source](raw/research/kestrel-physio/2026-11-02-event.md)
### Pains
- it_stretch
### Recommendation
- it-care — hiring_ops_it → it_stretch → it-care; exhibiting_at_event is a hook only (no pain)
### Must not
- (nothing extra)
