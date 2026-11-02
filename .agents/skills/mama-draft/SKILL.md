---
name: mama-draft
description: 'Draft an outreach message (connection note, first email, WhatsApp, follow-up) for an owned account and save it as a draft — it goes out only after the rep approves it in mama-send. Use for "draft/write to <company>" or from mama-day.'
---
# mama-draft

## When to use
- A rep says "draft / write to <company>" or `/mama-draft <id> <step>` (step: connect, first, fu1, fu2, fu3). mama-day and mama-replies (step `reply`) use it for every draft.
- The output is a draft: in the rep's own mailbox (email), in `log/drafts/` (WhatsApp), or text for the rep to send by hand (LinkedIn, phone). Never a sent message: sending is `/mama-send`, after the rep approves (rule 1, ADR-0007).

## Before you start
- Who: the account's `owner` only, in their own session, with their own mailbox connector. Not the runner, not a VAM.
- Needs: the email connector in drafts-only mode (Claude Code: `mcp__claude_ai_Gmail__create_draft`; its send tools are denied in `.claude/settings.json`), `scripts/draft_check.py` (Phase 4), `find.py` (Phase 0).
- If a required script is missing, say which phase adds it and stop. Connector missing or refused (e.g. "Insufficient scope"): show the draft on screen, keep the saved `log/drafts/` file, log the touch with `ref` = `pending-mailbox`, and tell the rep to reconnect the mailbox with draft (compose) permission.
- Re-read `wiki/accounts/<id>.md`, its frontmatter and the contact page now (rule 17). Never draft from facts remembered from earlier in the chat.
- Read: `reps/<me>.md` (tone, signature, `send_window_override`), `knowledge/markets.yaml` (the account's market), the market's section of `knowledge/guardrails.md` plus `<ADV> policy`, and `knowledge/playbook.md` (Sequences, Message rules).

## Steps
1. Checks. All must pass; on any fail, stop and tell the rep which and why. Step 5 runs them all in one go with `draft_check.py`; read them here so the draft is right first time.
   - `owner` = me (rules 6, 16).
   - Suppression: grep `wiki/suppression.csv` (`value,type,reason,added_by,added_on`) for the contact's email AND its domain (rule 2). Also stop if the contact has `status: do_not_contact` or `left`, or the account has `stage: do_not_contact`.
   - Stage allows the step: `connect` and `first` need `new` or `researched`; `first` also needs `recommended:` set and a `## Recommendation`. `fu1`/`fu2`/`fu3` need `contacted`, with the previous step `sent` in `log/touches.csv` and no reply since. `reply` needs `replied` or `meeting`. `nurture` only on explicit request with a new cited signal. No drafts for `handed_over` or `closed_lost`.
   - Channel allowed in the market (`markets.yaml` `channels`): SG and MY email, whatsapp, linkedin; IN adds phone. WhatsApp only with a +E.164 `whatsapp:` (or `phone:`) and recorded consent: `whatsapp_opt_in: true`, `whatsapp_opt_in_date` and a `whatsapp_opt_in_source` that is an existing `raw/` file (rule 14). Outside 24 h after the contact's last WhatsApp reply, WhatsApp needs an approved template from `knowledge/whatsapp_templates.yaml` whose `markets`, `steps` and `lang` fit, and whose `signals` (if any) are on the account page: a template must never state something untrue about the account.
   - Language: the contact's `lang`. If not `en`, an `approved` pattern in that language for this market must exist, else draft in English or stop and ask (rule 14).
2. Pattern: in `wiki/responses/patterns/`, pick a `status: approved` page whose `step` matches and whose `markets` includes the account's market and `lang` matches, best fit on contact persona × account pains × opening signal type. Record its `id`. If none fits, stop and say so: drafts use approved content only.
3. Opener: the freshest cited bullet in `## Signals`, or a `hook` signal (e.g. `exhibiting_at_event`, `incentive_window`) if fresher. Quote its date.
4. Body: the recommended product (available in that market, price in its currency), one proof from `knowledge/proof/`, exactly one CTA, the rep's tone and signature. Follow playbook Message rules and the market's guardrails section: unsubscribe line; SG `<ADV>` subject prefix when the `<ADV> policy` says so.
5. Check the draft: write the body (no subject) to a temp file and run
   `python3 scripts/draft_check.py --account <id> --contact <contact-id> --step <step> --channel <channel> --pattern <pattern-id> --products <id;id> --subject "<subject>" --file <tmp> --save`.
   WhatsApp with a template: no `--file`; add `--channel whatsapp --wa-template <key> --wa-params "<value 1>|<value 2>"` (values only from the account or contact page, rule 5); the script renders the body from the approved text. WhatsApp free text (inside the 24 h window): `--channel whatsapp --file <tmp>`.
   It runs every step-1 check plus pattern, products, length, unsubscribe line, signature, `<ADV>`, links, one CTA and the entity check (rule 5: every name, number and date must be on the account/contact page or in `knowledge/`), and prints the next send window. Fix each failing check and run again. Only `"ok": true` may go on; `--save` then writes `log/drafts/<date>-<id>-<step>.md` for eval. Spelled-out numbers ("three") aren't caught by the script: check them yourself.
6. Deliver:
   - Email: create the draft with the connector's create-draft tool (subject and body exactly as checked), addressed to the contact's business email. Never call a send tool (`send_message`, `reply`, `forward` all send). Then record the draft id: `python3 scripts/draft_check.py --set-ref <saved file> <draft id>`.
   - LinkedIn: at most 300 characters, shown on screen for the rep to paste by hand (rule 12).
   - WhatsApp (opted-in only): nothing more to do; `--save` wrote the draft (`ref: whatsapp`). Show the rendered text. It goes out only through `/mama-send` (rule 14).
   - Phone (IN): a talk track on screen for the rep. Never automate calls or SMS (rule 14).
   - Non-English: mark it "check before sending" for the rep.
   - Next send window: `draft_check.py` prints it (`markets.yaml` `send_windows` or `send_window_override`, market time zone, skipping `holidays`), e.g. "Tue 3 Nov, 09:00–11:30 SGT".
7. Record:
   - Append to `log/touches.csv`: `ts` (`YYYY-MM-DD HH:MM`), `rep`, `account`, `contact`, `channel`, `step`, `pattern`, `products` (ids joined by `;`), `status` = `drafted`, `reply_class` empty, `ref` (mailbox draft id; `whatsapp` for a WhatsApp draft; `manual` for LinkedIn/phone).
   - Account page: a line in `## Touch history` (date, step, channel, pattern, "drafted"); set `next_action` and `next_action_due` from playbook Sequences (e.g. fu1 after 4 working days); `updated:` today. Don't change `stage`: `send.py` moves it to `contacted` when it sends, and mama-replies does it for a draft the rep sent by hand from their mailbox.

## Never
- Send, schedule-send or forward anything; call any MCP send, reply or forward tool. Sending is only `/mama-send`, after the rep approves (rule 1).
- Draft to a suppressed email or domain (rule 2), or name anything that fails the entity check (rule 5).
- Use a product or proof outside `knowledge/` (rule 4), a draft or retired pattern, or a channel the market doesn't allow (rules 13, 14).
- Automate LinkedIn, SMS or calls; send WhatsApp any way but `send.py` (rules 12, 14).
- Draft for an account you don't own (rules 6, 16).

## Finish
- Summary, 1–3 lines: "Draft in your mailbox: first email to Jane Tan, Harbourlight Foods (pattern first-contract-win). Ready to send Tue 3 Nov, 09:00–11:30 SGT: run /mama-send."
- Log: `- [YYYY-MM-DD HH:MM] draft | <rep> | accounts/<id> | first email to jane-tan-<id>, pattern first-contract-win`
- Only when the session contains `MAMA_CARDS=on`: one `draft` card per draft, listing the checks that passed.
```mama-card
{"type":"draft","title":"First email · Harbourlight Foods","agent":"writer","account":"harbourlight-foods","to":"jane.tan@harbourlight.example","channel":"email","subject":"Your new catering contract","body":"Hi Jane, congratulations on the catering contract announced on 28 Oct...","signal":"contract_win (2026-10-28)","pattern":"first-contract-win","checks":["owner ok","not suppressed","entity check ok","SG channel ok"],"send_window":"Tue 3 Nov, 09:00-11:30 SGT","refs":["wiki/accounts/harbourlight-foods.md"],"actions":[{"label":"Shorter","prompt":"Make the Harbourlight draft shorter","style":"secondary"}]}
```
