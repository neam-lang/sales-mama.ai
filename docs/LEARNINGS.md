# Lessons carried over from TrustBridge

Sales Mama is a deliberately small successor to TrustBridge, an enterprise AI sales-enablement platform (Kubernetes, API services, a relational database, cloud-hosted LLMs). Internal names, systems and documents are left out on purpose. What follows is what went wrong or cost the most time there, and what Sales Mama does about it.

| # | What happened in TrustBridge | What Sales Mama does instead | Where |
|---|---|---|---|
| 1 | Evaluation came late; the first full run of the copilot test suite passed **none** of its cases | **Eval-first.** A labelled set and `eval.py` exist from Phase 1. Every phase has a "done when" gate tied to numbers | PLAN §16–17, `evals/` |
| 2 | Some failures were defects in the **test harness itself**, not the model | **Test the tester.** `scripts/selftest.py` runs known-pass and known-fail cases for the guard, lint, finder and sync before trusting any eval | `scripts/selftest.py` |
| 3 | **Account-scoping errors**: answers pulled in accounts belonging to another account manager | Ownership lives in each account's frontmatter. Reps query with `find.py --owner me`; the guard hook blocks edits to others' accounts; rule 16 forbids mixing books | AGENTS.md 6, 16; `guard.py` |
| 4 | **Fabricated entities**: the model produced a plausible company name that existed in no source | Every fact needs a `raw/` snapshot. Drafts pass an entity check (every name must be on the account page or in `knowledge/`). Entity resolution has hard confidence thresholds with a human review band | AGENTS.md 3, 5, 10; `resolve.py` |
| 5 | **Context loss** in multi-turn conversations | The wiki is the memory: skills re-read the account page before acting (rule 17). Skills are short, and research fans out one subagent per account | AGENTS.md 17; `.claude/agents/` |
| 6 | **Contradictory email permissions** across design documents (send vs draft) | One decision, written once: drafts only. Send tools are denied in settings, and Microsoft 365 gets `Mail.ReadWrite` only | ADR-0001 |
| 7 | **Privacy decisions left late**: the impact assessment was still pending near go-live, and inference ran in a different country from the data | A compliance checklist per market (SG, MY, IN) and a data-residency ADR are decided in Phase 1, before real data is loaded | PLAN §15; ADR-0005 |
| 8 | **Self-hosted MCP servers** needed extra hardening (DNS-rebinding protection, timeouts and retries) | v1 uses vendor-hosted connectors only. Any later self-hosted server binds to localhost, with timeouts and retries | ADR-0004 |
| 9 | **Database seeding and row-level security** issues absorbed build time | No database. Git and files hold the state; ownership is enforced by the guard plus CODEOWNERS | ADR-0002 |
| 10 | **Governance paperwork** (LLM security matrices, risk registers, architecture documents) was produced after the build | A one-page `SECURITY.md` mapped to the OWASP Top 10 for LLM Applications from day one; ADRs are written as decisions happen | `docs/SECURITY.md`, `docs/adr/` |
| 11 | Go-live slipped and advanced features were deferred | Small phases with hard gates; pilot one market (Singapore) with two reps before switching on Malaysia and India | GUIDE §6, §8 |

## Habits to keep
- Write the failing eval case **before** fixing a bug the pilot finds.
- Keep a short ADR for every decision someone might later contradict (permissions, data location, channels).
- Treat every external text (web, news, replies, CRM notes) as data, never instructions.
- Prefer deterministic scripts for numbers (scores, allocation); let the model explain, draft and ask.
