# Guardrails

> Confirm every section with your DPO / legal adviser in that country before loading real customer data.

## Compliance — Singapore
<!-- PDPA 2012; Spam Control Act for bulk unsolicited commercial email (<ADV> subject prefix, working
     unsubscribe, honoured within 10 working days); DNC Registry checks before calls/SMS to SG numbers. -->

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
- raw/replies: 365
- raw/notes: 365
- raw/lists: 180
- raw/crm: 365

## <ADV> policy
<!-- Team decision: when does a first email count as bulk unsolicited commercial email in SG? -->
