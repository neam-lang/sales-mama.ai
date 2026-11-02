---
type: account
id: fernhill-tutors
name: Fernhill Tutors Pte Ltd
market: SG
reg_type: uen
reg_id: 201365008A
alt_ids: {}
domain: fernhilltutors.example
city: Singapore
group:
source: crm
owner:
allocated_on:
allocated_by:
claimed_on:
stage: researched
industry: professional_services
employees: 55
region:
contract_end: 2027-09-29
signals: [contract_win, office_move]
pains: [scale_up, connectivity_reset]
products_owned: []
recommended: [cloud-phone, it-care]
propensity: 0.18
score: 0.67
tier: B
score_parts: {fit: 1.0, intent: 0.71, propensity: 0.18, engagement: 0.0}
score_updated: '2026-11-02'
risk: [hot]
nba:
nba_reason:
vam_updated:
next_action:
next_action_due:
last_touch:
updated: '2026-11-02'
---
# Fernhill Tutors Pte Ltd
## Snapshot
- CRM fields from [crm export](raw/crm/2026-11-01-demo-export-50.csv) (2026-11-01)
- Tuition and enrichment provider; appointed to run after-school enrichment classes for a cluster of five primary schools from January 2027 — [source](raw/research/fernhill-tutors/2026-11-02-site-contract.md) (2026-10-26)
- Main centre moved from Toa Payoh to a bigger unit in Bishan — [source](raw/research/fernhill-tutors/2026-11-02-news-move.md) (2026-06-01)
- Other locations: unknown
## Signals
<!-- - signal_term — evidence (date) — [source](raw/...) -->
- contract_win — appointed to run after-school enrichment classes for five primary schools from January 2027 (2026-10-26) — [source](raw/research/fernhill-tutors/2026-11-02-site-contract.md)
- office_move — moved main centre from Toa Payoh to a bigger unit in Bishan (2026-06-01) — [source](raw/research/fernhill-tutors/2026-11-02-news-move.md)
## Pains & hypotheses
- scale_up — from contract_win: delivering classes across five schools from January 2027 means more staff, devices and coordination to support on short notice.
- connectivity_reset — from office_move: the new, bigger Bishan centre (June 2026) may still be running on a rushed or interim network and phone setup; signal is ageing (past its 90-day window).
## Recommendation
1. **cloud-phone** (Cloud Phone, SGD 6,000/yr typical) — score 0.65
   - contract_win (2026-10-26) → appointed to run after-school enrichment classes for five primary schools from January 2027 [source](raw/research/fernhill-tutors/2026-11-02-site-contract.md) → scale_up → cloud-phone → no proof yet
2. **it-care** (IT Care, SGD 5,000/yr typical) — score 0.65
   - contract_win (2026-10-26) → appointed to run after-school enrichment classes for five primary schools from January 2027 [source](raw/research/fernhill-tutors/2026-11-02-site-contract.md) → scale_up → it-care → no proof yet
- Talk track: The new enrichment contract with five schools starts in January. Cloud Phone lets tutors and coordinators take and route calls from anywhere, and IT Care keeps the extra devices supported as the team grows.
- Skipped managed-wifi: solves none of the active pains
- Ignored signal: office_move (2026-06-01): older than 90 days
## Contacts
## Touch history
## Open objections
## VAM notes
## Call brief
## Meeting log & handover
## Next step
