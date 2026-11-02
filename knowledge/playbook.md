# Playbook

## Sequences
- Default: connect (LinkedIn, sent manually by the rep) → first email → fu1 (+4 working days) →
  fu2 (+7 working days) → nurture.
- A reply of any kind stops the sequence; `mama-replies` decides the next step.
- `contract_ending` accounts: first email 90–60 days before `contract_end`, not earlier.
- Event hooks (`exhibiting_at_event`): first touch 10–3 working days before the event; fu1 after it.

## Send windows
Defaults live in `markets.yaml` (SG: Mon–Thu 09:00–11:30 SGT, skipping SG public holidays). No team-wide exceptions.

## Message rules
- At most 120 words. One call to action (a 15-minute call or a yes/no question).
- The opener uses one cited signal from the account page. No signal means no first email (research first).
- No attachments and no links other than our own site on the first touch.
- Name only companies, people, numbers and products from the account page or `knowledge/` (AGENTS.md rule 5).
- Products only from `knowledge/products/`; proof only from `knowledge/proof/` (empty for now, so cite none).
- Sign off with the rep's `signature` from `reps/<id>.md`. Every email ends with the unsubscribe line.

## CRM import notes
The manager imports `log/crm-updates/<date>.csv` into the CRM weekly; columns follow `crm_mapping.yaml` `import:`.
