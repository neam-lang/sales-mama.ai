---
type: account
id: copperleaf-retail
name: Copperleaf Retail Pte Ltd
market: SG
reg_type: uen
reg_id: 201185361E
alt_ids: {}
domain: copperleafretail.example
city: Singapore
group: Copperleaf Group
source: crm
owner:
allocated_on:
allocated_by:
claimed_on:
stage: researched
industry: retail
employees: 78
region:
contract_end: 2027-03-31
signals: [new_branch_opened]
pains: [branch_expansion]
products_owned: [managed-wifi]
recommended: [cloud-phone]
propensity: 0.21
score: 0.67
tier: B
score_parts: {fit: 1.0, intent: 0.7, propensity: 0.21, engagement: 0.0}
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
# Copperleaf Retail Pte Ltd
## Snapshot
- CRM fields from [crm export](raw/crm/2026-11-01-demo-export-50.csv) (2026-11-01)
- What they do: retail store operator in Singapore — [source](raw/research/copperleaf-retail/2026-11-02-news-outlet.md) (2026-10-22)
- Locations: four stores, the newest at Jewel Changi Airport; two more outlets planned for 2027 — [source](raw/research/copperleaf-retail/2026-11-02-news-outlet.md) (2026-10-22)
- Size: unknown beyond the CRM employee count
## Signals
<!-- - signal_term — evidence (date) — [source](raw/...) -->
- new_branch_opened — opened its fourth store at Jewel Changi Airport; plans two more outlets in 2027 (2026-10-22) — [source](raw/research/copperleaf-retail/2026-11-02-news-outlet.md)
## Pains & hypotheses
- branch_expansion — implied by new_branch_opened (2026-10-22): each new outlet needs connectivity and in-store IT set up, and two more are planned for 2027; existing managed-wifi footprint may need extending.
## Recommendation
1. **cloud-phone** (Cloud Phone, SGD 6,000/yr typical) — score 0.70
   - new_branch_opened (2026-10-22) → opened its fourth store at Jewel Changi Airport; plans two more outlets in 2027 [source](raw/research/copperleaf-retail/2026-11-02-news-outlet.md) → branch_expansion → cloud-phone → no proof yet
- Talk track: Congratulations on the fourth store at Jewel. Cloud Phone gives every new outlet business lines and a mobile app without new phone hardware at each site.
- Skipped it-care: solves none of the active pains
- Skipped managed-wifi: already owned
## Contacts
- unknown (no people named in sources)
## Touch history
## Open objections
## VAM notes
## Call brief
## Meeting log & handover
## Next step
