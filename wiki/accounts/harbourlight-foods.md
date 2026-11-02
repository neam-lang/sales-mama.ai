---
type: account
id: harbourlight-foods
name: Harbourlight Foods
market: SG
reg_type:
reg_id:
alt_ids: {}
domain: harbourlightfoods.example
city: Singapore
group:
source: crm
owner:
allocated_on:
allocated_by:
claimed_on:
stage: researched
industry: fnb
employees: 90
region:
contract_end: 2027-02-15
signals: [contract_ending, new_branch_opened]
pains: [renewal_window, branch_expansion]
products_owned: []
recommended: [it-care, cloud-phone]
propensity: 0.71
score: 0.87
tier: A
score_parts: {fit: 1.0, intent: 1.0, propensity: 0.71, engagement: 0.0}
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
# Harbourlight Foods
## Snapshot
- CRM fields from [crm export](raw/crm/2026-11-01-demo-export-50.csv) (2026-11-01)
- Runs central kitchen(s) producing daily meals; a second central kitchen in Tampines is due to open in early 2027, doubling daily meal capacity — [source](raw/research/harbourlight-foods/2026-11-02-site-news.md) (2026-10-20)
- Registry ID (UEN): unknown
## Signals
<!-- - signal_term — evidence (date) — [source](raw/...) -->
- contract_ending — contract ends 2027-02-15 (CRM export) (2026-11-01) — [source](raw/crm/2026-11-01-demo-export-50.csv)
- new_branch_opened — announced second central kitchen in Tampines, opening early 2027, doubling daily meal capacity (2026-10-20) — [source](raw/research/harbourlight-foods/2026-11-02-site-news.md)
## Pains & hypotheses
- renewal_window — from contract_ending: current contract ends 2027-02-15, so a decision window is open now (CRM export).
- branch_expansion — from new_branch_opened: a second central kitchen (Tampines, early 2027) needs fit-out of connectivity and systems before opening; timing overlaps the renewal window.
## Recommendation
1. **it-care** (IT Care, SGD 5,000/yr typical) — score 0.99
   - contract_ending (2026-11-01) → contract ends 2027-02-15 (CRM export) [source](raw/crm/2026-11-01-demo-export-50.csv) → renewal_window → it-care → no proof yet
2. **cloud-phone** (Cloud Phone, SGD 6,000/yr typical) — score 0.69
   - new_branch_opened (2026-10-20) → announced second central kitchen in Tampines, opening early 2027, doubling daily meal capacity [source](raw/research/harbourlight-foods/2026-11-02-site-news.md) → branch_expansion → cloud-phone → no proof yet
- Talk track: Your current contract ends on 15 Feb 2027, so now is a good time to settle IT support for the next term. With a second central kitchen coming in Tampines, IT Care can cover device setup and backups at both kitchens from day one.
## Contacts
- [[contacts/rachel-goh-harbourlight-foods]] — Managing Director (owner_md) — [source](raw/research/harbourlight-foods/2026-11-02-site-news.md)
## Touch history
## Open objections
## VAM notes
## Call brief
## Meeting log & handover
## Next step
