---
name: mama-draft
description: 'Draft an outreach message (connection note, first email, follow-up) for an owned account and save it as an email draft — never send. Use for "draft/write to <company>" or from mama-day.'
---
# mama-draft

## When to use
- A rep says "draft / write to <company>" or `/mama-draft <id> <step>` (step: connect, first, fu1, fu2, fu3). mama-day and mama-replies (step `reply`) use it for every draft.
- The output is a draft in the rep's own mailbox, or text for the rep to send by hand. Never a sent message.

## Before you start
- Who: the account's `owner` only, in their own session, with their own mailbox connector. Not the runner, not a VAM.
- Needs: the email connector in drafts-only mode (Phase 4), `find.py` (Phase 0). No other script.
- If a required script is missing, say which phase adds it and stop. No connector: show the draft on screen and say Phase 4 connects the mailbox.
- Re-read `wiki/accounts/<id>.md`, its frontmatter and the contact page now (rule 17). Never draft from facts remembered from earlier in the chat.
- Read: `reps/<me>.md` (tone, signature, `send_window_override`), `knowledge/markets.yaml` (the account's market), the market's section of `knowledge/guardrails.md` plus `<ADV> policy`, and `knowledge/playbook.md` (Sequences, Message rules).

## Steps
1. Checks. All must pass; on any fail, stop and tell the rep which and why.
   - `owner` = me (rules 6, 16).
   - Suppression: grep `wiki/suppression.csv` (`value,type,reason,added_by,added_on`) for the contact's email AND its domain (rule 2). Also stop if the contact has `status: do_not_contact` or `left`, or the account has `stage: do_not_contact`.
   - Stage allows the step: `connect` and `first` need `new` or `researched`; `first` also needs `recommended:` set and a `## Recommendation`. `fu1`/`fu2`/`fu3` need `contacted`, with the previous step `sent` in `log/touches.csv` and no reply since. `reply` needs `replied` or `meeting`. `nurture` only on explicit request with a new cited signal. No drafts for `handed_over` or `closed_lost`.
   - Channel allowed in the market (`markets.yaml` `channels`): SG email, linkedin; MY adds whatsapp; IN adds whatsapp and phone. WhatsApp only if the contact has `whatsapp_opt_in: true` or has replied (rule 14).
   - Language: the contact's `lang`. If not `en`, an `approved` pattern in that language for this market must exist, else draft in English or stop and ask (rule 14).
2. Pattern: in `wiki/responses/patterns/`, pick a `status: approved` page whose `step` matches and whose `markets` includes the account's market and `lang` matches, best fit on contact persona × account pains × opening signal type. Record its `id`. If none fits, stop and say so: drafts use approved content only.
3. Opener: the freshest cited bullet in `## Signals`, or a `hook` signal (e.g. `exhibiting_at_event`, `incentive_window`) if fresher. Quote its date.
4. Body: the recommended product (available in that market, price in its currency), one proof from `knowledge/proof/`, exactly one CTA, the rep's tone and signature. Follow playbook Message rules and the market's guardrails section: unsubscribe line; SG `<ADV>` subject prefix when the `<ADV> policy` says so.
5. Entity check (rule 5): list every company, person, number, date and product in the draft. Each must appear on the account page (with a source) or in `knowledge/`. Remove or fix anything that doesn't, then check again.
6. Deliver:
   - Email: create the draft with the connector's create-draft tool, addressed to the contact's business email. Never call a send tool.
   - LinkedIn: at most 300 characters, shown on screen for the rep to paste by hand (rule 12).
   - WhatsApp (MY/IN, opted-in only) or phone (IN): a short text or talk track on screen for the rep to use by hand. Never automate them (rule 14).
   - Non-English: mark it "check before sending" for the rep.
   - Next send window: from `markets.yaml` `send_windows` (or `send_window_override`) in the market's time zone, skipping `holidays`, e.g. "Tue 3 Nov, 09:00–11:30 SGT".
7. Record:
   - Append to `log/touches.csv`: `ts` (`YYYY-MM-DD HH:MM`), `rep`, `account`, `contact`, `channel`, `step`, `pattern`, `products` (ids joined by `;`), `status` = `drafted`, `reply_class` empty, `ref` (mailbox draft id, or `manual` for LinkedIn/WhatsApp/phone).
   - Account page: a line in `## Touch history` (date, step, channel, pattern, "drafted"); set `next_action` and `next_action_due` from playbook Sequences (e.g. fu1 after 4 working days); `updated:` today. Don't change `stage`; mama-replies moves it to `contacted` once the draft is found in Sent.

## Never
- Send, schedule-send or forward anything; call any send tool (rule 1).
- Draft to a suppressed email or domain (rule 2), or name anything that fails the entity check (rule 5).
- Use a product or proof outside `knowledge/` (rule 4), a draft or retired pattern, or a channel the market doesn't allow (rules 13, 14).
- Automate LinkedIn, WhatsApp, SMS or calls (rules 12, 14).
- Draft for an account you don't own (rules 6, 16).

## Finish
- Summary, 1–3 lines: "Draft in your mailbox: first email to Jane Tan, Harbourlight Foods (pattern first-contract-win). Send Tue 3 Nov, 09:00–11:30 SGT."
- Log: `- [YYYY-MM-DD HH:MM] draft | <rep> | accounts/<id> | first email to jane-tan-<id>, pattern first-contract-win`
- Only when the session contains `MAMA_CARDS=on`: one `draft` card per draft, listing the checks that passed.
```mama-card
{"type":"draft","title":"First email · Harbourlight Foods","agent":"writer","account":"harbourlight-foods","to":"jane.tan@harbourlight.example","channel":"email","subject":"Your new catering contract","body":"Hi Jane, congratulations on the catering contract announced on 28 Oct...","signal":"contract_win (2026-10-28)","pattern":"first-contract-win","checks":["owner ok","not suppressed","entity check ok","SG channel ok"],"send_window":"Tue 3 Nov, 09:00-11:30 SGT","refs":["wiki/accounts/harbourlight-foods.md"],"actions":[{"label":"Shorter","prompt":"Make the Harbourlight draft shorter","style":"secondary"}]}
```
