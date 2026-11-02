---
type: account
id:                  # same id as wiki/accounts/<id>.md
name:
market:              # SG | MY | IN
reg_type:
reg_id:
domain:
city:
industry:            # ontology term
employees:
contract_end:
products_owned: []
verified_by:         # who hand-checked this page
verified_on:         # YYYY-MM-DD
---
# {name} (golden)

Copy this file to `evals/golden_accounts/<id>.md` for each golden account (10 per live
market by Phase 3). Hand-verify every fact against its source. Fictional or anonymised
accounts only until ADR-0005 is accepted.

## Facts
<!-- - fact — [source](raw/...) ; every fact needs a raw/ snapshot (rule 3) -->

## Expected
### Signals
<!-- - signal_term (ontology.yaml) — evidence — [source](raw/...) -->
### Pains
<!-- - pain_term (ontology.yaml) -->
### Recommendation
<!-- - product-id (knowledge/products/) — why, via signal → pain → product -->
### Must not
<!-- - products to exclude (owned, unavailable in market) or names that must never appear -->
