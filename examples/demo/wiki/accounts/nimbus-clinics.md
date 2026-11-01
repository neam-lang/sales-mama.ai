---
type: account
id: nimbus-clinics
name: Nimbus Clinics Pte Ltd
market: SG              # SG | MY | IN
reg_type: uen           # uen | ssm | cin | llpin | gstin | udyam
reg_id: 53312345A
alt_ids: {}             # e.g. gstin, udyam
domain: nimbusclinics.example
city: Singapore
group:
source: crm             # crm | list | <sources.yaml id>
owner: mei
allocated_on: 2026-10-20
allocated_by: grace
claimed_on:
stage: contacted
industry: clinics
employees: 40
region: central
contract_end: 2026-12-31
signals: [contract_ending]
pains: []
products_owned: []
recommended: []
propensity:
score: 0.52
tier: B
score_parts: {fit: 0.7, intent: 0.5, propensity: 0, engagement: 0}
score_updated: 2026-11-01
risk: [contract_ending_no_plan]
nba: Follow-up 1 — mention the December contract end
nba_reason: No reply to the first email; renewal window is open
vam_updated: 2026-11-01
next_action: Send follow-up 1
next_action_due: 2026-11-02
last_touch: 2026-10-30
updated: 2026-11-01
---
# Nimbus Clinics Pte Ltd
## Snapshot
Fictional group of three GP clinics in central Singapore (demo data).
## Signals
<!-- - signal_term — evidence (date) — [source](raw/...) -->
- contract_ending — current contract ends 2026-12-31 (2026-10-20) — [source](raw/crm/2026-10-20-demo-export.csv)
## Pains & hypotheses
## Recommendation
## Contacts
## Touch history
- 2026-10-30 first email sent
## Open objections
## VAM notes
## Call brief
## Meeting log & handover
## Next step
Follow-up 1.
