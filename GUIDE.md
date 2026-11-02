# Sales Mama — Complete Guide

Sales Mama is an agentic sales assistant for a small SMB sales team (1 manager + up to 5 reps) in **Singapore, Malaysia and India**. It runs natively in **Claude Code** or **Codex**: the repo is the system, skills are the features, and an LLM-maintained knowledge wiki is the memory.

This guide covers everything in order: what's in the kit, how to push it, how the manager and reps start, how to build each phase with Claude Code, and how to run it safely.

---

## 0. What's in this kit

| Path | What it is | Status |
|---|---|---|
| `AGENTS.md`, `CLAUDE.md` | The rules every agent follows (Claude Code reads CLAUDE.md, which imports AGENTS.md; Codex reads AGENTS.md) | Ready |
| `PLAN.md` | The design: architecture, markets, scoring, VAMs, allocation, compliance, build phases | Ready |
| `SETUP.md` | Agent-executable setup, onboarding, cheat sheets, troubleshooting, skill specs | Ready |
| `.agents/skills/` → `.claude/skills/` | 17 `mama-*` skills (canonical copy, plus the Claude Code mirror) | Ready; later-phase skills need their scripts |
| `.claude/agents/`, `.codex/agents/` | Subagents: `scout`, `researcher`, `vam` | Ready |
| `.claude/settings.json` | Hooks (session start, write guard, sync) and deny rules | Ready |
| `scripts/` | Phase 0 helpers + books + a self-test, all working | Ready |
| `templates/` | Page templates for accounts, contacts, events, objections, patterns, reps | Ready |
| `knowledge/` | Your business: markets, ICP, ontology, products, sources, scoring, allocation, playbook, guardrails | Stubs: filled in Phase 1 |
| `wiki/`, `raw/`, `log/`, `reps/` | Working data (empty) | Fills as you use it |
| `examples/demo/` | A fictional dataset used by the self-test | Ready |
| `evals/` | Eval scaffolding | Built from Phase 1 |
| `runner/` | Nightly job for macOS/Linux and Windows | Ready; scheduled by `mama-setup --runner` |
| `docs/` | `UI.md` (chat UI + card protocol), `LEARNINGS.md` (from TrustBridge), `SECURITY.md`, `adr/` | Ready |
| `design/` | Source of the UI design canvas | Ready |
| `console/` | Card schema for the optional console | The console itself is built in Phase 9 |
| `.github/` | CODEOWNERS and a CI workflow (self-test, lint, skills mirror) | Ready; set your handle in CODEOWNERS |

**Phase 0 is already done in this kit.** SETUP.md Part A describes what was built; you only run the checks in §4.

---

## 1. How it works in 60 seconds

```
Rep types /mama-day  ─▶  Claude Code / Codex reads AGENTS.md + the skill
                          ├─ subagents research accounts in parallel (cited sources only)
                          ├─ scripts score leads and recommend products (deterministic)
                          ├─ drafts land in the rep's own mailbox (never sent)
                          └─ the wiki, logs and books update; the hook commits and pushes
Nightly (02:00, one runner machine) ─▶ scan news / tenders / registries / events → score → VAMs → allocation proposal
Manager types /mama-manager ─▶ approves allocation, clears the review queue, sees the team book
```

---

## 2. Prerequisites

| Who | Needs |
|---|---|
| Manager | GitHub account with admin on the private repo; Claude desktop app (Code) or Codex app; git; Python 3.10+ |
| Each rep | GitHub access to the repo; a Claude plan that includes Claude Code, or a ChatGPT plan that includes Codex; their own work mailbox |
| IT | One Google OAuth client for Sales Mama (Workspace, type *Internal*, scopes `gmail.compose` + `gmail.readonly`) and, for WhatsApp, a verified Meta Business account with the company number and approved templates (SETUP.md · Connect channels) |
| Runner | One machine that stays on overnight (it can be the manager's laptop) |

`mama-setup` installs Python, PyYAML and git for reps if they're missing.

---

## 3. Push this kit to your repo

From the unzipped kit folder (it is already a git repo with its history):

```bash
git remote add origin https://github.com/neam-lang/sales-mama.ai.git
git push -u origin main
```

If the GitHub repo already has commits (for example a README), push to a new branch instead and merge it on GitHub:

```bash
git push -u origin main:kit/starter
```

Then on GitHub:
1. Set your handle in `.github/CODEOWNERS` (replace `@MANAGER`).
2. Turn on branch protection for `main` if your plan supports it.
3. Invite the reps.

---

## 4. Manager: the first hour

1. **Check the kit.** Open the repo in Claude Code (desktop app → Code, or `claude` in a terminal) and paste:
   > Read GUIDE.md. Run `python3 scripts/selftest.py`, `python3 scripts/lint.py`, `python3 scripts/session_start.py` and `python3 scripts/sync_skills.py --check`, show me the results, then run the mama-setup skill for me as the manager.

   `mama-setup` asks a few questions and writes `reps/<you>.md` with `role: manager`.
2. **Decide data residency** with your DPO (fill in `docs/adr/0005-data-residency.md`) before any real customer data goes in.
3. **Start Phase 1** (§6): describe your business, markets and products, and ingest your CRM export.
4. **Set up the runner** once you reach Phase 7: on the runner machine, say *"Set up the Sales Mama nightly runner on this machine."*

---

## 5. Reps: day 0 and every day

**Day 0 (about 10 minutes):** open the Claude desktop app → Code (or the Codex app), start a session in an empty folder, and type:

> Set me up for Sales Mama from https://github.com/neam-lang/sales-mama.ai

The agent:
1. Clones the repo and installs anything missing.
2. Asks for name, markets, territory, quota, targets, tone and signature.
3. Connects their Gmail (`connect.py gmail`, one click) and, if used, WhatsApp.
4. Shows a dry run.

**Every day:**

| I want to… | Claude Code | Codex |
|---|---|---|
| Run my whole morning | `/mama-day` | `$mama-day` or "run my day" |
| See my book | `/mama-book` | "show my book" |
| Handle replies | `/mama-replies` | `$mama-replies` |
| Work my allocated leads | `/mama-target` | "what's allocated to me?" |
| Research / pitch / write | `/mama-research acme` · `/mama-recommend acme` · `/mama-draft acme first` | plain English |
| Prep a call or an event | `/mama-brief acme` · `/mama-brief sme-expo-2026` | "brief me on …" |
| Log a meeting | `/mama-handover acme` + paste notes | same |
| Anything else | Ask in plain English | same |

Drafts are prepared for you; `/mama-send` shows the batch, you pick what goes, approve it, and Sales Mama sends and logs it. Nothing goes out without your approval (ADR-0007).

---

## 6. Build Sales Mama with Claude Code, phase by phase

For each phase:
1. Open the repo in Claude Code and switch to **plan mode**.
2. Paste the prompt and review the plan.
3. Let it build.
4. Run `python3 scripts/selftest.py` and (from Phase 1) `python3 scripts/eval.py`.
5. Merge when the "done when" gate in PLAN.md §17 passes.

Pilot in **Singapore** first (§8).

**Phase 1 — Knowledge + ingest**
> Implement `scripts/eval.py` and finish the `mama-ingest` skill. Interview me, one topic at a time, to fill every `knowledge/` file:
> - `company.md`
> - `icp.md`, with a section per market
> - `markets.yaml`
> - `ontology.yaml`
> - `products/`
> - `proof/`
> - `sources.yaml`
> - `scoring.yaml`
> - `allocation.yaml`
> - `playbook.md`
> - `guardrails.md`, with a section per market
>
> Map my CRM export in `crm_mapping.yaml` and ingest `raw/crm/`. Create the golden-accounts template in `evals/`.

**Phase 2 — External signals**
> Implement `scripts/resolve.py`, `scripts/fetch_dataset.py`, the `mama-scan` skill steps and the `scout` subagents.
> 1. Scan the Singapore sources in `sources.yaml` for the last 7 days.
> 2. Help me label 50 items in `evals/labeled_matches.csv`.
> 3. Tune resolution until auto-link precision is at least 95%.

**Phase 3 — Score + research + recommend**
> Implement `scripts/score.py` and `scripts/recommend.py` from `scoring.yaml`, `icp.md` and the ontology.
> 1. Score all accounts.
> 2. Research the 10 golden accounts with `researcher` subagents.
> 3. Fix failures until the PLAN.md §16 targets pass: 100% cited, recommendation match at least 80%, 0 fabricated entities.

**Phase 4 — Outreach + responses**
> Connect the email connector in drafts-only mode:
> - Add its send tools to `permissions.deny` in `.claude/settings.json`.
> - Restrict Codex `enabled_tools`.
>
> Then:
> 1. Make `mama-draft`, `mama-replies` and `mama-brief` work end to end.
> 2. Interview me for 10–15 objections and seed the response library as `status: draft`.
> 3. Label 40 replies and reach at least 90% classification accuracy.

**Phase 5 — Books + VAMs**
> Make `mama-book` and `mama-vam` work with the `vam` subagent and the house VAM.
> 1. Run VAMs on two books.
> 2. Prove with lint that they wrote only allowed fields and sections.

**Phase 6 — Allocation + manager cockpit**
> Implement `scripts/allocate.py` (PLAN.md §10) and `scripts/claim.py` (including `--assign`), then make `mama-allocate`, `mama-manager` and `mama-target` work.
> 1. Generate a proposal for the current pool.
> 2. Show that hard constraints hold and the expected-value spread is within limits.

**Phase 7 — Nightly + weekly + handover**
> 1. Make `mama-nightly`, `mama-weekly` (with score calibration and allocation fairness) and `mama-handover` work.
> 2. Set up the runner on this machine with `mama-setup --runner`.
> 3. Show me five nights of logs.

**Phase 8 — Codex parity + pilot**
> 1. Run every skill once in Codex and record differences in README.md.
> 2. Run a 2-rep Singapore pilot for a week.
> 3. Turn each pilot mistake into an eval case before fixing it.

**Phase 9 — Sales Mama Console (optional)**
> Build the console in `console/` per `docs/UI.md`, `console/cards.schema.json` and ADR-0006, matching the screens in `design/canvas/`.
> - **Stack:** Node 20 + TypeScript, Vite + React.
> - **Engine:** a localhost WebSocket bridge that spawns `claude -p … --output-format stream-json --verbose --include-partial-messages --append-system-prompt "MAMA_CARDS=on" --resume <session>` in this repo, with `codex exec --json` as an option.
> - **Rendering:**
>   - streaming text
>   - tool chips
>   - agent lanes, from subagent `parent_tool_use_id`
>   - the plan card
>   - validated `mama-card` blocks
>   - a bento rail from `wiki/books/`
> - **Behaviour:**
>   - Card actions send their prompt as the next turn.
>   - No send button; permissions unchanged.
>   - Responsive down to phone width.
> - **Tests:** the event parser, using recorded streams.

---

## 7. Using Codex instead of (or alongside) Claude Code

- Codex reads `AGENTS.md` and the skills in `.agents/skills/`. Invoke them as `$mama-day` or in plain English.
- There are no hooks by default, so AGENTS.md tells the agent to run `scripts/session_start.py` at the start and `scripts/sync.py` at the end.
- Subagents in `.codex/agents/*.toml` are experimental. Enable `multi_agent` in `~/.codex/config.toml`; without it, the skills run the same steps one after another.
- Trust the project in Codex so `.codex/config.toml` loads. Keep email tools limited to drafts there.
- For the nightly run, use `codex exec --sandbox workspace-write "Run the mama-nightly skill"` from the runner, or Codex app Automations on a Mac.

---

## 8. Markets: switch them on one at a time

`knowledge/markets.yaml` has `live: [SG]`. To add a market:
1. Fill its sections in `icp.md` and `guardrails.md` and confirm the guardrails with local counsel.
2. Add its sources to `sources.yaml` (PLAN.md §5–6 lists candidates).
3. Label about 50 matches and 40 replies for it in `evals/`, and reach the targets.
4. Fill in that year's holidays and the FX rate in `markets.yaml`.
5. Add it to `live`, give a rep the market in `reps/<id>.md`, and allocate.

Recommended order: **Singapore → Malaysia → India.**
- Malaysia shares the time zone and adds WhatsApp and Bahasa Malaysia.
- India has the most volume, and its DPDP duties start in May 2027, so settle notice and consent handling first.

---

## 9. Manager operations

- **Daily:** `/mama-manager`. Approve or edit the allocation in a sentence, clear the review queue, and check risks.
- **Weekly:** `/mama-weekly`. Read the report, then review and merge its PR.
- **Knowledge changes:** ask in plan mode, on a branch, and merge after review.
- **Add a rep:** grant repo access and send them §5.
- **Remove a rep:** `python3 scripts/claim.py --reassign <rep> <other>`, revoke repo and connector access, and set `role: inactive`.
- **Yearly:** fill next year's holidays in `markets.yaml`.
- **Monthly:** update FX rates.

More detail: SETUP.md Part D.

---

## 10. Safety, compliance and security

- **Rules:** AGENTS.md hard rules 1–17. They cover approve-then-send, sources required, untrusted content, scoping and markets.
- **Compliance by market:** PLAN.md §15 and `knowledge/guardrails.md`. Confirm with your DPO or legal adviser in each country.
- **Security:** `docs/SECURITY.md`, mapped to the OWASP Top 10 for LLM Applications.
- **Decisions:** `docs/adr/`. ADR-0005 (data residency) must be decided before real data is loaded.

---

## 11. Lessons from TrustBridge

`docs/LEARNINGS.md` lists what cost the most in the earlier platform and how this kit avoids it:
- eval-first development
- testing the test harness
- account scoping
- fabricated-entity checks
- context loss
- one permission decision instead of contradictory ones
- early privacy decisions
- no self-hosted MCP
- no database
- governance from day one

---

## 12. Troubleshooting

See SETUP.md Part E. The most common issues:
- **A sync conflict:** run `python3 scripts/sync.py` again.
- **A skill not found:** run `python3 scripts/sync_skills.py`, then start a new session.
- **The guard blocked an edit:** this is expected for `knowledge/`, `raw/` and other reps' accounts.

---

## 13. Repo map

```
AGENTS.md CLAUDE.md GUIDE.md PLAN.md SETUP.md README.md
knowledge/   markets · icp · ontology · products · proof · sources · scoring · allocation · playbook · guardrails · crm_mapping
raw/         crm · lists · notes · replies · research · signals            (immutable inputs)
wiki/        accounts · contacts · events · responses · books · index · log · suppression
log/         touches · signals · review · allocation · briefs · crm-updates · weekly
reps/        one file per person
scripts/     helpers + selftest
templates/   page templates
.agents/skills/  .claude/skills/  .claude/agents/  .codex/agents/
runner/      nightly jobs
evals/       labelled sets and golden accounts
docs/        UI · LEARNINGS · SECURITY · adr
design/      UI canvas sources
console/     card schema (console built in Phase 9)
examples/demo/  fictional data for the self-test
```
