---
name: mama-recommend
description: 'Recommend best-fit products for an owned account from its signals using the ontology and catalog, with a traceable chain. Use for "what should I pitch" or from mama-day.'
---
# mama-recommend

## When to use
- A rep asks "what should I pitch to <company>?" or `/mama-recommend <id>`; mama-day runs it after research.
- Re-run it after new signals arrive or the account's market or products owned change.

## Before you start
- Who: the account's `owner`, or the manager.
- Scripts: `recommend.py` (Phase 3).
- If a required script is missing, say which phase adds it and stop.
- Re-read `wiki/accounts/<id>.md` and its frontmatter now (rule 17). If `owner` is not me (and I'm not the manager), stop (rules 6, 16).
- The account must have `market` set (rule 14). If it has no cited signals, suggest mama-research first.

## Steps
1. Run `python3 scripts/recommend.py <id> --json`. It walks signal → pain → product using `knowledge/ontology.yaml` and `knowledge/products/*.yaml` (fits, requires, skip_if_owned, decay) and returns candidates with their chain and exclusions.
2. Keep only candidates whose product file has the account's `market` in `available_in` (rule 14). Treat the script's ranking as final; don't re-rank by feel.
3. For the top 1–2 candidates, build the chain from the output and the page:
   `signal (date) → evidence [source](raw/...) → pain → product → proof`.
   - The signal and evidence must be a cited bullet in `## Signals` (rule 3).
   - The product must be a file in `knowledge/products/` (rule 4). Price and value in the market's currency, from the product file.
   - Proof only from `knowledge/proof/` (rule 4), preferring proof from the same market or industry. If none fits, write "no proof yet".
   - Note any incentive the product qualifies for in that market (e.g. SG EDGE Grant), only if the product file lists it.
4. Write a 2–3 sentence talk track in the rep's `tone`, naming only things in the chain.
5. Update the page: replace `## Recommendation` with the chain(s), talk track and the script's main exclusions (e.g. "skipped <product>: already owned"). Set `recommended: [<product ids>]` and `updated:` today. Don't change `stage`.
6. No candidates: write "No fit now: <reason from the script>" in `## Recommendation`, set `recommended: []`, and suggest what would change it (e.g. "a new signal such as office_move").

## Never
- Recommend a product outside `knowledge/products/`, or one not available in the account's market (rules 4, 14).
- Cite proof outside `knowledge/proof/`, or invent numbers (rules 4, 5).
- Use an uncited signal in the chain (rule 3).
- Edit an account you don't own (rule 6).

## Finish
- Summary, 1–3 lines: "Harbourlight Foods → Branch Connect (SGD 6,000/yr), via contract_win 28 Oct → scale_up. Proof: Kopi Co case. Next: /mama-draft harbourlight-foods first."
- Log: `- [YYYY-MM-DD HH:MM] recommend | <user> | accounts/<id> | branch-connect (contract_win → scale_up)`
- Only when the session contains `MAMA_CARDS=on`: one `account` card with `recommendation` filled.
```mama-card
{"type":"account","title":"Harbourlight Foods","agent":"mama","id":"harbourlight-foods","name":"Harbourlight Foods","market":"SG","tier":"A","score":0.76,"stage":"researched","owner":"mei","recommendation":{"chain":["contract_win (2026-10-28)","Awarded catering contract","scale_up","branch-connect"],"product":"branch-connect","proof":"kopi-co-case","talk_track":"New contract means more sites to bring online fast."},"refs":["wiki/accounts/harbourlight-foods.md","knowledge/products/branch-connect.yaml"],"actions":[{"label":"Draft first email","prompt":"/mama-draft harbourlight-foods first","style":"primary"}]}
```
