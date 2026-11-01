# Security — one page

Sales Mama runs inside Claude Code or Codex on each user's machine, reads and writes one private git repo, and uses vendor-hosted connectors (email drafts; later a CRM). There is no server of our own.

## Controls mapped to the OWASP Top 10 for LLM Applications (2025)

| Risk | How it shows up here | Control |
|---|---|---|
| LLM01 Prompt injection | Instructions hidden in web pages, news, replies or CRM notes | AGENTS.md rule 15: external text is data. Skills never follow links or actions from content. Suspicious instructions are reported in one line |
| LLM02 Sensitive information disclosure | Personal data in the wiki or in drafts | Business contact data only (rule 8); a private repo; retention per `raw/` folder; drafts limited to facts on the account page (rule 5) |
| LLM03 Supply chain | Untrusted skills, plugins or MCP servers | Only the repo's own skills; vendor-hosted connectors; CODEOWNERS on `.agents/`, `.claude/`, `.codex/`, `scripts/` |
| LLM04 Data and model poisoning | A planted page that skews scores or recommendations | Closed ontology, trust weights per source, and a manager review band for uncertain matches. Scores are explainable (`score_parts`) |
| LLM05 Improper output handling | Model output executed or sent unchecked | Drafts only; no auto-send; scripts parse frontmatter with a YAML loader, never `eval` |
| LLM06 Excessive agency | The agent sends, assigns or deletes on its own | Send tools denied; allocation needs the manager's approval; the guard hook blocks protected paths; force-push and `rm -rf` are denied |
| LLM07 System prompt leakage | Rules or playbook exposed | Nothing secret is kept in prompts; no credentials in the repo (`.env` is gitignored) |
| LLM08 Vector and embedding weaknesses | (no vector store) | The wiki is plain files; retrieval is index + file reads |
| LLM09 Misinformation | Fabricated companies, people or numbers | Source links required; entity check before drafts; evals count fabrications (target 0) |
| LLM10 Unbounded consumption | Runaway scans or subagent fan-out | Source caps, at most 5 parallel subagents, a cheaper model for scouts; VAMs touch only changed accounts |

## Operational rules
- **Repo:** private; branch protection on `main` where your GitHub plan allows it; CODEOWNERS review for `knowledge/` and the harness.
- **Identity:** each user works under their own git identity and their own Claude or Codex login. No shared accounts.
- **Connectors:** each user signs in to their own mailbox; drafts-only scopes. Revoke access when someone leaves (`GUIDE.md` §9).
- **Runner:** one machine, the manager's identity, permissions narrowed with `--allowedTools`, logs kept locally in `runner/logs/`.
- **Secrets:** never committed. If a key is needed (e.g. Agent SDK for the console), it comes from the environment.
- **Incidents:** if a draft or signal was wrong, add the case to `evals/` first, then fix. If personal data was mishandled, follow the market's breach rules in `knowledge/guardrails.md`.

The guard hook and AGENTS.md rules prevent *mistakes*; they are not a security boundary against someone with repo write access. GitHub permissions are.
