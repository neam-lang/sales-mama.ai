---
type: account
id: nimbus-clinics
name: Nimbus Clinics Pte. Ltd.
market: SG
reg_type: uen
reg_id: 53312345A
alt_ids: {}
domain: nimbusclinics.example
city: Singapore
group:
source: crm
owner:
allocated_on:
allocated_by:
claimed_on:
stage: researched
industry: clinics
employees: 42
region:
contract_end: 2026-12-31
signals: [contract_ending, office_move]
pains: [renewal_window, connectivity_reset]
products_owned: [cloud-phone]
recommended: [it-care, managed-wifi]
propensity: 0.64
score: 0.86
tier: A
score_parts: {fit: 1.0, intent: 1.0, propensity: 0.64, engagement: 0.0}
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
# Nimbus Clinics Pte. Ltd.
## Snapshot
- CRM fields from [crm export](raw/crm/2026-11-01-demo-export-50.csv) (2026-11-01)
- Runs a clinic in Novena, moving to a larger nearby unit with more consultation rooms from 1 December — [source](raw/research/nimbus-clinics/2026-11-02-news-move.md) (2026-10-12)
- Other locations: unknown
## Signals
<!-- - signal_term — evidence (date) — [source](raw/...) -->
- contract_ending — contract ends 2026-12-31 (CRM export) (2026-11-01) — [source](raw/crm/2026-11-01-demo-export-50.csv)
- office_move — Novena clinic relocating to a larger unit nearby from 1 December (2026-10-12) — [source](raw/research/nimbus-clinics/2026-11-02-news-move.md)
## Pains & hypotheses
- renewal_window — from contract_ending: current contract ends 2026-12-31, a natural review point — [source](raw/crm/2026-11-01-demo-export-50.csv)
- connectivity_reset — from office_move: new Novena premises with added consultation rooms will need phones and connectivity set up before 1 December — [source](raw/research/nimbus-clinics/2026-11-02-news-move.md)
## Recommendation
1. **it-care** (IT Care, SGD 5,000/yr typical) — score 0.99
   - contract_ending (2026-11-01) → contract ends 2026-12-31 (CRM export) [source](raw/crm/2026-11-01-demo-export-50.csv) → renewal_window → it-care → no proof yet
2. **managed-wifi** (Managed WiFi, SGD 4,000/yr typical) — score 0.46
   - office_move (2026-10-12) → Novena clinic relocating to a larger unit nearby from 1 December [source](raw/research/nimbus-clinics/2026-11-02-news-move.md) → connectivity_reset → managed-wifi → no proof yet
- Talk track: Your contract ends on 31 Dec, just as the Novena clinic moves to its larger unit. IT Care can carry support through the renewal, and Managed WiFi can be ready in the new premises before patients arrive.
- Skipped cloud-phone: already owned
## Contacts
- [[contacts/sarah-wong-nimbus-clinics]] — Medical Director (owner_md) — [source](raw/research/nimbus-clinics/2026-11-02-news-move.md)
## Touch history
## Open objections
## VAM notes
## Call brief
## Meeting log & handover
## Next step
