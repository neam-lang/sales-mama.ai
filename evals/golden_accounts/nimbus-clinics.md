---
type: account
id: nimbus-clinics
name: Nimbus Clinics Pte. Ltd.
market: SG
reg_type: uen
reg_id: 53312345A
domain: nimbusclinics.example
city: Singapore
industry: clinics
employees: 42
contract_end: '2026-12-31'
products_owned: [cloud-phone]
verified_by:
verified_on:
---
# Nimbus Clinics Pte. Ltd. (golden)

FICTIONAL golden account for Phase 3 (ADR-0005: fictional data only). Expected values follow ontology.yaml, products/ and the recommend.py rules as of 2026-11-02.

## Facts
- CRM: industry clinics, 42 staff, owns cloud-phone, contract end 2026-12-31 — [source](raw/crm/2026-11-01-demo-export-50.csv)
- fixture `news-move` (FICTIONAL) — [source](raw/research/nimbus-clinics/2026-11-02-news-move.md)
- contact: Sarah Wong — Medical Director (owner_md) — [source](raw/research/nimbus-clinics/2026-11-02-news-move.md)

## Expected
### Signals
- office_move — Novena clinic relocating to larger premises from 1 Dec (2026-10-12) — [source](raw/research/nimbus-clinics/2026-11-02-news-move.md)
- contract_ending — CRM contract ends 2026-12-31 — [source](raw/crm/2026-11-01-demo-export-50.csv)
### Pains
- connectivity_reset
- renewal_window
### Recommendation
- it-care — contract_ending → renewal_window outranks office_move → connectivity_reset (managed-wifi second); cloud-phone owned
### Must not
- cloud-phone — excluded (owned, out of fit, or no fit now)
