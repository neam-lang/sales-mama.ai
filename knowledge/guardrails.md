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
- Channels: email and LinkedIn, both sent manually by the rep (`markets.yaml`).

## Compliance — Malaysia
<!-- PDPA 2010 as amended in 2024 (DPO and breach notification since 1 Jun 2025; cross-border regime
     changed 1 Apr 2025); honour direct-marketing opt-outs promptly; WhatsApp only to opted-in contacts. -->

## Compliance — India
<!-- DPDP Act 2023 + Rules 2025: notice/consent, security, breach and rights duties from May 2027 —
     decide notice/consent handling before scaling outreach; TRAI TCCCPR for commercial calls/SMS
     (never automated by Sales Mama); WhatsApp only to opted-in contacts. -->

## Do / don't
- Do: business contact details only; cite a source for every fact; drafts only.
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
<!-- Team decision: when does a first email count as bulk unsolicited commercial email in SG? -->
