# ADR-0005: Data residency and model provider

- **Status:** proposed — pending DPO (recorded 2026-11-01 by the manager). Not legal advice: every point below is for the DPO or legal adviser in each country to confirm. Flip to `accepted` once the checklist at the end is signed off.
- **Context:** Account data passes through two processors: the model provider (every page an agent reads in a session) and GitHub (the whole repo, including `wiki/`, `raw/` and `log/`). Under all three laws we stay accountable for what our processors do with it. A previous build ran inference in a different country from the data and left the privacy assessment until late.
- **What each market expects:**
  - **Singapore (PDPA 2012), the live pilot market:**
    - *Transfer Limitation Obligation:* personal data may leave Singapore only if the recipient is bound by legally enforceable obligations (contract, DPA, binding corporate rules) to protect it to a standard comparable to the PDPA. Keep a record of that basis.
    - *Business contact information:* name, title, work email and work phone given for business purposes are largely outside the PDPA's main obligations. Most Sales Mama account and contact data may fall here; reply text and call notes may go beyond it.
    - *Data intermediaries:* processors must still protect and not over-retain the data, and we remain responsible for them.
    - *Breach:* notify the PDPC within 3 calendar days of assessing a breach as notifiable, and affected individuals where required.
    - *Contact rules, not residency:* the Spam Control Act (`<ADV>` prefix for bulk unsolicited commercial email, working unsubscribe, opt-outs honoured within 10 working days) and DNC Registry checks for SG numbers.
  - **Malaysia (PDPA 2010, amended 2024):**
    - Since 1 Apr 2025 the whitelist is gone: transfer where the destination has a substantially similar law or the data gets an equivalent level of protection, or on another basis such as consent or contract necessity (s129).
    - DPO appointment and breach notification since 1 Jun 2025; processors now carry their own security duty.
  - **India (DPDP Act 2023 + Rules 2025):**
    - Transfers abroad are allowed except to countries the government restricts by notification.
    - Core duties from May 2027: notice and consent (or a legitimate use), security safeguards, breach notice to the Board and individuals, erasure when the purpose is served, and accountability for processors.
- **Options:** (a) business terms whose data protection meets all three markets; (b) restrict India data until DPDP handling is ready; (c) keep raw replies and notes minimal and short-lived. Chosen: all three.
- **Decision:**
  - **Model provider:** Anthropic API / Console (Claude Code billed by API usage) under Anthropic's Commercial Terms and Data Processing Addendum. No consumer plans (Claude Pro/Max) for real customer data. API inputs and outputs are not used for training by default; retention follows Anthropic's current API policy, and zero-data-retention is requested if the DPO requires it.
  - **GitHub:** private repo `neam-lang/sales-mama.ai` on GitHub.com under GitHub's DPA (hosted mainly in the US).
  - **Markets:** Singapore first (`live: [SG]`). Malaysia only after its checklist items below. **India: no real data** (accounts, contacts, replies, notes) until a DPDP notice/consent approach is signed off; IN stays out of `live` until then.
  - **Retention (days per `raw/` folder, in `knowledge/guardrails.md`):** signals 180 · research 180 · lists 90 · replies 180 · notes 180 · crm 365. `mama-weekly` proposes deletions; the manager approves them.
  - **Minimisation:** AGENTS.md rules 8–9: business contact details only; external content as headline, link and a summary of at most 60 words.
- **Consequences:**
  - Deleting a `raw/` file does not remove it from git history, clones or forks. True erasure needs a history rewrite, which is a manager task outside the agent's reach; keep personal content out of `raw/` where possible.
  - Every session sends what it reads to the Anthropic API; scoping (rule 16) keeps that to the rep's own accounts.
  - The India rollout is blocked on the DPDP decision.
- **DPO must confirm:**
  1. Anthropic's Commercial Terms and DPA are accepted for the organisation and satisfy the SG Transfer Limitation Obligation and MY s129.
  2. Anthropic API data-retention period and training setting; whether zero-data-retention is needed.
  3. GitHub plan and DPA cover the private repo; US hosting is acceptable for SG and MY data; GitHub data residency is not required.
  4. How far the SG business contact information exclusion covers Sales Mama data, especially reply text and call notes.
  5. The retention days above, and the approach to erasing data from git history.
  6. Breach process: PDPC (SG, 3 days once notifiable), the Personal Data Protection Commissioner (MY), and later the Data Protection Board (IN).
  7. MY: DPO appointed and transfer basis recorded before MY goes live.
  8. IN: notice/consent or legitimate-use approach before any IN data and before May 2027; restricted-country list checked.
  9. Sign-off: name, role and date; then set the status to `accepted`.
