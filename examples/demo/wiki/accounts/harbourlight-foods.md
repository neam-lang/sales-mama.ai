---
type: account
id: harbourlight-foods
name: Harbourlight Foods Pte Ltd
market: SG              # SG | MY | IN
reg_type: uen           # uen | ssm | cin | llpin | gstin | udyam
reg_id: 201912345K
alt_ids: {}             # e.g. gstin, udyam
domain: harbourlightfoods.example
city: Singapore
group:
source: sg-gov-procurement  # crm | list | <sources.yaml id>
owner: mei
allocated_on: 2026-10-15
allocated_by: grace
claimed_on:
stage: meeting
industry: fnb
employees: 85
region: east
contract_end:
signals: [contract_win, new_branch_opened]
pains: [scale_up, branch_expansion]
products_owned: []
recommended: []
propensity: 0.62
score: 0.78
tier: A
score_parts: {fit: 0.8, intent: 0.85, propensity: 0.62, engagement: 0.6}
score_updated: 2026-11-02
risk: [hot]
nba: Prep the call brief for the 5 Nov meeting
nba_reason: Meeting booked after a positive reply to follow-up 1
vam_updated: 2026-11-02
next_action: Prepare call brief
next_action_due: 2026-11-03
last_touch: 2026-11-02
updated: 2026-11-02
---
# Harbourlight Foods Pte Ltd
## Snapshot
Fictional central-kitchen caterer in eastern Singapore, about 85 staff (demo data).
## Signals
<!-- - signal_term — evidence (date) — [source](raw/...) -->
- contract_win — awarded a school-canteen supply contract (2026-10-28) — [source](raw/signals/2026-10-28/sg-gov-procurement/harbourlight-foods-award.md)
- new_branch_opened — second kitchen opening in Tampines announced (2026-10-20) — [source](raw/research/harbourlight-foods/2026-10-20-site.md)
## Pains & hypotheses
- scale_up: a new contract means more orders to run with the same back office.
## Recommendation
No fit computed yet (demo data; recommend.py arrives in Phase 3).
## Contacts
- [[contacts/rachel-goh-harbourlight-foods]] — Managing Director
## Touch history
- 2026-10-20 first email sent · 2026-10-28 follow-up 1 sent · 2026-11-01 reply (interested) · 2026-11-02 meeting booked
## Open objections
- [[responses/objections/already-have-provider]] raised in the 1 Nov reply.
## VAM notes
- 2026-11-02 pre-draft (call confirmation): "Hi Rachel, looking forward to Thursday. I'll bring a one-page plan for the new Tampines kitchen..."
## Call brief
## Meeting log & handover
## Next step
Prepare the call brief before 5 Nov.
