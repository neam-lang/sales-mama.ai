---
type: account
id: northwind-kopitiam
name: Northwind Kopitiam Pte Ltd
market: SG
reg_type: uen
reg_id: 201090479C
alt_ids: {}
domain: northwindkopitiam.example
city: Singapore
group:
source: crm
owner:
allocated_on:
allocated_by:
claimed_on:
stage: researched
industry: fnb
employees: 183
region:
contract_end: 2026-12-29
signals: [contract_ending, hiring_ops_it]
pains: [renewal_window, it_stretch]
products_owned: [it-care]
recommended: []
propensity: 0.73
score: 0.87
tier: A
score_parts: {fit: 1.0, intent: 1.0, propensity: 0.73, engagement: 0.0}
score_updated: '2026-11-02'
risk: []
nba:
nba_reason:
vam_updated:
next_action:
next_action_due:
last_touch:
updated: '2026-11-02'
---
# Northwind Kopitiam Pte Ltd
## Snapshot
- CRM fields from [crm export](raw/crm/2026-11-01-demo-export-50.csv) (2026-11-01)
- Runs multiple outlets with POS terminals, outlet networks and staff laptops — [careers](raw/research/northwind-kopitiam/2026-11-02-careers.md) (2026-10-25)
- Number of outlets, locations beyond Singapore: unknown
## Signals
<!-- - signal_term — evidence (date) — [source](raw/...) -->
- contract_ending — contract ends 2026-12-29 (CRM export) (2026-11-01) — [source](raw/crm/2026-11-01-demo-export-50.csv)
- hiring_ops_it — job post for an IT Executive to support POS terminals, outlet networks and staff laptops across outlets (2026-10-25) — [source](raw/research/northwind-kopitiam/2026-11-02-careers.md)
## Pains & hypotheses
- renewal_window — implied by contract_ending (contract ends 2026-12-29) — [source](raw/crm/2026-11-01-demo-export-50.csv)
- it_stretch — implied by hiring_ops_it: hiring in-house IT to cover POS, outlet networks and laptops across outlets suggests IT support is stretched — [source](raw/research/northwind-kopitiam/2026-11-02-careers.md)
## Recommendation
No fit now: cloud-phone: solves none of the active pains; it-care: already owned; managed-wifi: solves none of the active pains
- What would change it: a new signal implying a different pain, e.g. new_branch_opened or office_move (Cloud Phone / Managed WiFi).
- Skipped cloud-phone: solves none of the active pains
- Skipped it-care: already owned
- Skipped managed-wifi: solves none of the active pains
## Contacts
- [[contacts/daniel-lim-northwind-kopitiam]] — Daniel Lim, Operations Manager (ops_head) — [source](raw/research/northwind-kopitiam/2026-11-02-careers.md)
## Touch history
## Open objections
## VAM notes
## Call brief
## Meeting log & handover
## Next step
