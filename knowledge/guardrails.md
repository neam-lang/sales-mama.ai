# Guardrails

> Confirm every section with your DPO / legal adviser in that country before loading real customer data.

## Compliance — Singapore
<!-- Not legal advice; confirm with your DPO (see docs/adr/0005-data-residency.md). -->
- PDPA 2012: business contact details only, for the purpose of B2B outreach. Account data leaves
  Singapore only through processors under a contract or DPA (ADR-0005: Anthropic API, GitHub).
- Spam Control Act: a bulk unsolicited commercial email gets the `<ADV>` subject prefix (see `<ADV>`
  policy); every email carries a working unsubscribe line; opt-outs are honoured within 10 working
  days and added to `wiki/suppression.csv` at once.
- DNC Registry: check before any call or SMS to an SG number. Sales Mama never automates them.
- Breach: tell the manager at once; the manager assesses PDPC notification (within 3 days of
  assessing it as notifiable).
- Channels: email (sent by `send.py` after the rep approves the batch, ADR-0007), WhatsApp (below) and
  LinkedIn (sent manually by the rep).
- WhatsApp: only to contacts with `whatsapp_opt_in: true`, an opt-in date and a `raw/` source recording how
  they opted in; first contact only with an approved template from `knowledge/whatsapp_templates.yaml`;
  every template carries an opt-out line ("Reply STOP to opt out"), and STOP goes to `wiki/suppression.csv`
  at once. Sent through the WhatsApp Business Cloud API inside the send window, never automated without the
  rep's approval, never from a personal number.
  <!-- DPO: confirm whether the DNC Registry check applies to WhatsApp messages to SG numbers, and the
  consent wording, before knowledge/sending.yaml `enabled: true`. -->

## Compliance — Malaysia
<!-- Not live. Not legal advice; confirm with your DPO before switching MY on (ADR-0005). -->
- PDPA 2010 as amended in 2024: DPO appointment and breach notification since 1 Jun 2025; cross-border
  transfers since 1 Apr 2025 need a substantially similar law, equivalent protection, or another s129 basis.
- Direct marketing: honour opt-outs at once (`wiki/suppression.csv`); every email carries an unsubscribe line.
- WhatsApp only to contacts with recorded opt-in (as in Singapore), sent through the Cloud API after the rep
  approves the batch (ADR-0007). Phone calls are made by the rep; never automated.

## Compliance — India
<!-- Not live, no real Indian data (ADR-0005). Not legal advice; confirm with your DPO before switching IN on. -->
- DPDP Act 2023 + Rules 2025: notice/consent (or a legitimate use), security, breach notice and erasure duties
  from May 2027. Decide notice/consent handling before any outreach at scale.
- TRAI TCCCPR for commercial calls and SMS; Sales Mama never automates them.
- WhatsApp only to contacts with recorded opt-in, sent through the Cloud API after the rep approves the
  batch (ADR-0007).

## Do / don't
- Do: business contact details only; cite a source for every fact; send only what the rep approved (ADR-0007).
- Don't: scrape LinkedIn; store full article text; message suppressed contacts or domains.

## Retention
<!-- days per raw/ folder; lint.py reads lines in exactly this form -->
- raw/signals: 180
- raw/research: 180
- raw/replies: 180
- raw/notes: 180
- raw/lists: 90
- raw/crm: 365

## <ADV> policy
<!-- Team decision (Phase 1 interview, 2026-11-01); confirm with the DPO. -->
- A first email written for one researched account (cited signal, named contact) is a 1:1 business email:
  no `<ADV>` prefix.
- Any templated message sent by one rep to 10 or more contacts in a day counts as bulk: every one of those
  emails gets the `<ADV>` subject prefix.
- When in doubt, add `<ADV>`. Every email, prefixed or not, carries the unsubscribe line.
