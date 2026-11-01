# ADR-0005: Data residency and model provider (decide in Phase 1)

- **Status:** proposed — decide with your DPO before loading real customer data
- **Context:** Account data passes through the model provider (Claude or OpenAI) and GitHub. A previous build ran inference in a different country from the data and left the privacy assessment until late. Singapore (PDPA transfer limitation), Malaysia (cross-border regime since 1 Apr 2025) and India (DPDP cross-border rules from May 2027) each have transfer rules.
- **Options:** (a) business plans whose data terms meet all three markets; (b) restrict India data until DPDP handling is ready; (c) keep raw replies and notes minimal and short-lived.
- **Decision:** _to be recorded_ — provider, plan, data terms reviewed, retention settings, who signed off, date.
