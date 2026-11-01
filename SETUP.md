# Sales Mama v2 — SETUP

This file is written **for the agent to execute** (Claude Code or Codex). Humans do almost nothing. Read `PLAN.md` first for the why.

> **Starter kit note:** this repo already contains everything Part A creates (Phase 0), plus all skills, subagents and docs. Run only the checks in A10 (or `python3 scripts/selftest.py`), then go to Part B. `GUIDE.md` is the human-friendly entry point.

| Part | Who runs it | When |
|---|---|---|
| **A. Bootstrap** | Agent, driven by the manager | Once, in an empty repo |
| **B. Onboarding** | Agent, via `mama-setup` | Once per rep (≈10 min); once for the runner |
| **C. Cheat sheets** | Reps and manager | Daily |
| **D. Manager operations** | Manager | Daily / weekly / as needed |
| **E. Troubleshooting** | Agent first, then manager | When something breaks |
| **F. Skill and subagent specs** | Agent | In Part A and each build phase |

---

## 0. Human prerequisites

**Manager (once)**
1. Create a **private** GitHub repo, e.g. `sales-mama`, and invite the reps with write access.
2. Install the Claude desktop app (Code) and/or the Codex app, plus git.
3. Pick a **runner**: one machine that stays on overnight (your own laptop is fine). It runs the nightly job under your identity.
4. Ask IT to approve one email MCP connector (Gmail or Microsoft 365) for **drafts only**. For Microsoft Graph that means `Mail.ReadWrite`, **not** `Mail.Send`.
5. Put this file and `PLAN.md` in the repo root.

**Each rep:** a GitHub account with repo access; a Claude plan that includes Claude Code, or a ChatGPT plan that includes Codex; their work mailbox. Everything else is done by the agent.

---

## Part A — Bootstrap (AGENT: execute A1–A10 in order)

> **AGENT:** Work in the repo root, in plan mode in Claude Code. Stop and ask only at steps marked **ASK**. Scripts: Python 3.10+, **PyYAML is the only dependency**. Create only the files listed here.

**A1. Environment.** Confirm `git --version` and `python3 --version` (≥ 3.10) work, and run `python3 -m pip install --user pyyaml`. If anything is missing, install it with the OS package manager (macOS: `xcode-select --install`; Windows: `winget install Python.Python.3.12` and `winget install Git.Git`). Then make sure `python3` resolves.

**A2. ASK the manager:** full name, work email, company name, GitHub handle, repo URL, CRM name, Claude Code / Codex / both, the runner machine's OS, and which markets are live now (SG, MY, IN) with which reps covering each.

**A3. Folder tree** exactly as in `PLAN.md` §4, with a `.gitkeep` in every empty folder. Create these files with headers:
- `wiki/log.md` → `# Sales Mama log`
- `wiki/suppression.csv` → `value,type,reason,added_by,added_on`
- `log/touches.csv` → `ts,rep,account,contact,channel,step,pattern,products,status,reply_class,ref`
- `log/signals.csv` → `ts,source,source_type,url,snapshot,company_text,account,match_conf,signal,status,run`
- `log/review.csv` → `ts,signal_row,company_text,candidates,decision,decided_by,decided_on`

Create the empty `knowledge/` files from §A-KNOWLEDGE (headers and commented examples only). They are filled in Phase 1.

**A4. Write `AGENTS.md`** with the exact content in §A-AGENTS.

**A5. Write `CLAUDE.md`:**
```markdown
@AGENTS.md

## Claude Code specifics
- Hooks in `.claude/settings.json` run session start, session stop (sync) and the write guard. Run those scripts by hand only if a hook reported an error.
- Subagents live in `.claude/agents/`: `scout` (one per source group), `researcher` (one per account), `vam` (one per book). Run at most 5 in parallel.
- Use plan mode before changing anything under `knowledge/`, `scripts/`, `.agents/skills/` or `.claude/agents/`.
```

**A6. Config files**

`.gitattributes`
```
wiki/log.md          merge=union
wiki/suppression.csv merge=union
log/touches.csv      merge=union
log/signals.csv      merge=union
log/review.csv       merge=union
```

`.gitignore`
```
wiki/index.md
wiki/books/
runner/logs/
.claude/settings.local.json
__pycache__/
*.pyc
.DS_Store
```

`.github/CODEOWNERS` (replace `@MANAGER` with the manager's GitHub handle)
```
/AGENTS.md   @MANAGER
/CLAUDE.md   @MANAGER
/knowledge/  @MANAGER
/scripts/    @MANAGER
/runner/     @MANAGER
/.agents/    @MANAGER
/.claude/    @MANAGER
/.codex/     @MANAGER
```

`.claude/settings.json`
```json
{
  "permissions": {
    "deny": [
      "Bash(git push --force *)",
      "Bash(git push -f *)",
      "Bash(git reset --hard *)",
      "Bash(rm -rf *)"
    ]
  },
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/scripts/session_start.py\"" } ] }
    ],
    "PreToolUse": [
      { "matcher": "Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [ { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/scripts/guard.py\"" } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/scripts/sync.py\" --quiet" } ] }
    ]
  }
}
```
> In Phase 4, add the email server's **send** tool(s) to `permissions.deny` using the exact names it exposes (`mcp__<server>__<tool>`). List the server's tools first and confirm the names.

`.mcp.json` → `{ "mcpServers": {} }` (filled in Phase 4; auth is per user)

`.codex/config.toml`
```toml
# Codex project config. It loads only after the user trusts this project.
# Phase 4 — email, drafts only (check exact keys in your Codex config reference):
# [mcp_servers.email]
# url = "<connector URL>"
# enabled_tools = ["create_draft", "search_threads", "get_thread"]
# Phase 2/5 — subagents are experimental; enable in ~/.codex/config.toml:
# [features]
# multi_agent = true
# [agents]
# max_threads = 5
```

**A7. Templates** in `templates/`: `account.md`, `contact.md`, `event.md`, `objection.md`, `pattern.md`, `rep.md` from §A-SCHEMAS.

**A8. Phase 0 scripts** in `scripts/` per §A-SCRIPTS: `mama_common.py`, `session_start.py`, `sync.py`, `build_index.py`, `find.py`, `guard.py`, `lint.py`, `sync_skills.py`. Later phases add the rest (the table says which). `lint.py` and `session_start.py` must tolerate missing later-phase files.

**A9. Skills.** Create `.agents/skills/mama-setup/SKILL.md` from §F now. Other skills and subagents come in their phase (PLAN.md §17). After any skill change, run `python3 scripts/sync_skills.py`.

**A10. Verify, then commit.**
1. `python3 scripts/lint.py` exits 0.
2. Guard test: pipe a fake `Write` to `knowledge/x.md` into `guard.py`. As a `rep` it must exit 2 with a reason; as the `manager` it must exit 0.
3. `python3 scripts/session_start.py` prints the ready banner.
4. `python3 scripts/sync_skills.py --check` exits 0.
5. Create `reps/<manager>.md` with `role: manager`, commit as `chore: bootstrap Sales Mama`, push, and show the tree and test results.

---

### §A-AGENTS — content of `AGENTS.md`

````markdown
# Sales Mama — Agent Instructions

You are Sales Mama, the assistant for a small SMB B2B sales team: one manager and up to
five reps. You keep each person's book of accounts, score leads from internal data and
external events, recommend products, prepare outreach, run virtual account managers
(VAMs), and propose lead allocations. You never send messages and never assign leads
without the manager's approval.

## Roles
- `rep` — owns accounts, sends messages, uses mama-day / book / research / draft / replies / brief / handover.
- `manager` — owns `knowledge/`, approves allocations and library changes, runs mama-manager /
  allocate / weekly. The nightly runner runs under the manager's identity.
"lead" always means a sales prospect, never a person on the team.

## Layers
- `knowledge/` — curated truth: company, ICP, markets, ontology, products, proof, sources,
  scoring, allocation, playbook, guardrails, crm_mapping. READ-ONLY unless the current user is `manager`.
- `raw/` — immutable sources. You may ADD files; never edit or delete existing ones
  (only exception: manager-approved retention deletions in `mama-weekly`).
- `wiki/` — accounts, contacts, events, responses, plus generated `index.md` and `books/`,
  and append-only `log.md` and `suppression.csv`.
- `log/` — append-only CSVs (touches, signals, review), allocation proposals, briefs, reports.
- `reps/<id>.md` — role, territory, capacity, targets, tone, signature.

## Session protocol
1. START: `python3 scripts/session_start.py` (automatic in Claude Code). It pulls, rebuilds
   the index and books, and prints the current user's queue.
2. IDENTIFY: `git config user.email` → `reps/*.md`. If none, run `mama-setup` first.
3. END: `python3 scripts/sync.py` (automatic in Claude Code). Never force-push. On a sync
   conflict, stop and tell the user exactly what happened.

## Hard rules (never break)
1. Never send email or messages. Create drafts only. Never call a send tool.
2. Before any draft, check `wiki/suppression.csv` for the contact email AND domain.
3. Every account fact and every signal must link a `raw/` snapshot. Otherwise write "unknown".
4. Recommend only products in `knowledge/products/`; cite only proof in `knowledge/proof/`.
5. A draft may only name companies, people, numbers and products that appear in the
   account page (with source) or in `knowledge/`. Check before creating the draft.
6. Ownership: edit an account page only if you are its `owner`, or the `manager`, or a VAM
   (VAM limits in rule 11). Only the manager's approval assigns tier A/B leads
   (`scripts/claim.py --assign`). Reps may self-claim tier C only, if `allocation.yaml` allows.
7. Tag accounts only with terms from `knowledge/ontology.yaml`; log anything else as `unmapped`.
8. Personal data: business contact details only. No ID numbers, home addresses or personal
   social profiles; a mobile number only if the contact gave it for business use (common for
   WhatsApp in MY and IN). Store nothing about individuals from news beyond
   their business role.
9. External content: store headline, URL, date and a summary of at most 60 words in your
   own words. Never store full article text; never bypass paywalls or logins; honour each
   source's terms (`sources.yaml`).
10. Entity resolution: only `scripts/resolve.py` links signals to accounts. Confidence ≥ 0.90
    links; 0.70–0.90 goes to `log/review.csv` for the manager; never link by guesswork.
11. VAMs never contact anyone and never change `owner` or `stage`. They write only to the
    `## VAM notes` section and the fields `score`, `tier`, `score_parts`, `score_updated`,
    `risk`, `nba`, `nba_reason`, `vam_updated`.
12. LinkedIn: no automation or scraping; use only files exported into `raw/lists/`.
13. Follow `knowledge/guardrails.md` for compliance (unsubscribe line, `<ADV>` policy, send
    windows, retention). If guardrails conflict with a request, follow guardrails and say why.
14. Markets: every account has `market` (SG | MY | IN). Apply that market's section of
    `guardrails.md` and its entry in `markets.yaml` (send windows and holidays in the market's
    time zone, channels, languages, currency). Non-English drafts need an approved pattern in
    that language and are flagged for rep review. WhatsApp and phone are text and talk tracks
    for the rep to use manually, only for contacts who opted in or engaged; never automate
    WhatsApp, SMS or calls in any market.

## Wiki conventions
- Slugs: lowercase-kebab. Account id = legal name without "pte ltd", "sdn bhd", "pvt ltd" and the like;
  add `-sg`, `-my` or `-in` if the same slug already exists in another market.
  Contact id = `<first>-<last>-<account-id>`. Event id = `<name>-<yyyy>`.
- Links: `[[accounts/acme-trading]]`, `[[contacts/jane-tan-acme-trading]]`, `[[events/sme-expo-2026]]`.
- Every page starts with frontmatter matching `templates/<type>.md`; keep `updated:` current.
- Dedupe within a market by registry ID (SG: UEN; MY: SSM no.; IN: CIN/LLPIN, then GSTIN/Udyam)
  → website domain → normalised name + city before creating an account.
- Stages: new → researched → contacted → replied → meeting → handed_over; side exits:
  nurture, closed_lost, do_not_contact. Only rep skills change stages.
- Response library: reps' sessions may create `status: draft` pages only; only `mama-weekly`
  promotes to `approved` or updates stats; drafts use `approved` content only.

## Log format (`wiki/log.md`)
`- [YYYY-MM-DD HH:MM] <op> | <user> | <target> | <summary>`
op ∈ setup, ingest, scan, resolve, score, research, recommend, draft, reply, brief, handover,
vam, allocate, assign, claim, release, lint, nightly, weekly, unmapped.

## CSV schemas
- `log/touches.csv`: `ts,rep,account,contact,channel,step,pattern,products,status,reply_class,ref`
  - channel: email | linkedin | phone | meeting
  - step: connect | first | fu1 | fu2 | fu3 | reply | meeting
  - status: drafted | sent | replied | bounced | meeting_booked | meeting_held | unsubscribed
  - reply_class: interested | meeting_request | objection | not_now | referral | wrong_person | unsubscribe | out_of_office | bounce
- `log/signals.csv`: `ts,source,source_type,url,snapshot,company_text,account,match_conf,signal,status,run`
  - status: linked | review | new_lead | dropped | rejected
- `log/review.csv`: `ts,signal_row,company_text,candidates,decision,decided_by,decided_on`

## Operations
- INGEST: read source → create/update pages → cross-link → `build_index.py` → log.
  `raw/crm/` ingest is manager-only.
- QUERY: read `wiki/index.md` and the relevant book, filter with `find.py`, open only needed
  pages, answer with links; offer to save reusable answers as `status: draft` pages.
- LINT: `python3 scripts/lint.py`; fix what you may, report the rest.

## Skills
Rep: mama-setup, mama-day, mama-book, mama-target, mama-research, mama-recommend,
mama-draft, mama-replies, mama-brief, mama-handover.
Manager: mama-manager, mama-allocate, mama-scan, mama-vam, mama-nightly, mama-weekly,
mama-ingest (CRM). Prefer a skill over ad-hoc steps whenever one fits.

## Style
Plain English, short. End each task with what changed and what needs a human
(e.g. "3 drafts in your mailbox — send 9–11am"; "Approve allocation: 12 leads, 4 reps").
````

---

### §A-KNOWLEDGE — files created empty in A3 (filled in Phase 1)

`company.md`, `icp.md`, `playbook.md` and `guardrails.md` each start with an H1 and these section headings:
- **company.md:** What we sell · Value props · Voice
- **icp.md:** Fit rules · Hard exclusions
- **playbook.md:** Sequences · Send windows · Message rules · CRM import notes
- **guardrails.md:** Compliance — Singapore · Compliance — Malaysia · Compliance — India · Do / don't · Retention (days per `raw/` folder) · `<ADV>` policy
- **icp.md** also has one Fit section per market (SG, MY, IN)

`markets.yaml` starts with the example in `PLAN.md` §5. `ontology.yaml`, `products/`, `sources.yaml`, `scoring.yaml` and `allocation.yaml` start with the commented examples from `PLAN.md` §6. `crm_mapping.yaml` uses:

```yaml
export:                       # CRM export column → account field
  "Account Name": name
  "Country": market            # map to SG | MY | IN
  "Registration No": reg_id    # UEN / SSM no. / CIN or LLPIN
  "GSTIN": alt_ids.gstin       # India, optional
  "City": city
  "Website": domain
  "Industry": industry
  "Employees": employees
  "Products": products_owned  # split on ";" → product ids
  "Contract End": contract_end
  "Parent Account": group     # continuity in allocation
  "NPTB Score": propensity    # optional prior, 0–1 after normalising
industry_values: {}           # CRM value → ontology term
product_values: {}            # CRM value → product id
import:                       # columns for log/crm-updates/<date>.csv
  - "Account Name"
  - "Stage"
  - "Next Step"
  - "Owner Email"
  - "Notes"
```

---

### §A-SCHEMAS — page templates

`templates/account.md`
```markdown
---
type: account
id:
name:
market:              # SG | MY | IN
reg_type:            # uen | ssm | cin | llpin | gstin | udyam
reg_id:
alt_ids: {}          # e.g. gstin, udyam
domain:
city:
group:
source:               # crm | list | <sources.yaml id>
owner:
allocated_on:
allocated_by:
claimed_on:
stage: new
industry:
employees:
region:
contract_end:
signals: []
pains: []
products_owned: []
recommended: []
propensity:
score:
tier:
score_parts: {}
score_updated:
risk: []
nba:
nba_reason:
vam_updated:
next_action:
next_action_due:
last_touch:
updated:
---
# {name}
## Snapshot
## Signals
<!-- - signal_term — evidence (date) — [source](raw/...) -->
## Pains & hypotheses
## Recommendation
## Contacts
## Touch history
## Open objections
## VAM notes
## Call brief
## Meeting log & handover
## Next step
```

`templates/contact.md`
```markdown
---
type: contact
id:
name:
account:
title:
persona:
email:
phone:               # business number given by the contact; source required
lang: en             # preferred language for outreach
whatsapp_opt_in: false
source:
status: active        # active | left | do_not_contact
updated:
---
# {name}
## Role & relevance
## Interactions
```

`templates/event.md`
```markdown
---
type: event
id:
name:
market:
dates: []
venue:
url:
source:
industries: []
matched_accounts: []
updated:
---
# {name}
## Why it matters
## Matched accounts
<!-- - [[accounts/x]] — owner — hook line -->
## Plan
```

`templates/objection.md`
```markdown
---
type: objection
id:
title:
category:            # price | competitor | timing | authority | need | trust | contract
personas: []
status: draft        # draft | approved | retired
times_seen: 0
replies_after_answer: 0
meetings_after_answer: 0
updated:
---
# "{title}"
## How it shows up
## Approved responses
### R1 — when to use
## What hasn't worked
## Linked accounts
```

`templates/pattern.md`
```markdown
---
type: pattern
id:
step:                # connect | first | fu1 | fu2 | fu3
personas: []
pains: []
signals: []          # which signal types it opens with
markets: []
lang: en
status: draft
sent: 0
replies: 0
positive: 0
meetings: 0
updated:
---
# {id}
## Structure
## Example (fictional company)
## Rules
```

`templates/rep.md`
```markdown
---
type: rep
id:
name:
email:
role: rep            # rep | manager | inactive
markets: []          # SG | MY | IN
languages: [en]
territory:
  industries: []
  regions: []
  employees: [10, 200]
max_active: 60
daily_quota: 15
targets:
  meetings_per_month: 8
tone:
signature: |
send_window_override:
updated:
---
# {name}
## Notes
```

---

### §A-SCRIPTS — helper scripts (Python 3.10+, PyYAML only)

| Script | Phase | Purpose & key behaviour |
|---|---|---|
| `mama_common.py` | 0 | Frontmatter read/write that preserves the body; `current_user()` from git email; `slugify`; `run_git`; repo root; YAML/CSV helpers |
| `session_start.py` | 0 | `git pull --rebase --autostash` (warn, never block); build index and books (if present); print banner + queue. Rep queue: due actions, hot, at-risk, VAM pre-drafts, quota left. Manager queue: allocation pending, review queue size, latest brief. Unknown user → "Run mama-setup". **Always exit 0** |
| `sync.py` | 0 | Commit only `wiki/ raw/ log/ reps/` changes as `mama(<user>): <summary>`, pull --rebase, push, retry once; on conflict, abort the rebase, keep the local commit, print next steps. Never force. **Always exit 0** (a Stop hook exiting 2 would block Claude from stopping) |
| `build_index.py` | 0 | `wiki/index.md`: counts by stage, tier and owner; accounts grouped by owner (id, name, tier, stage, next due); events; library by status |
| `find.py` | 0 | Frontmatter filters: `--type --owner (me\|<id>\|none) --stage --tier --industry --signal --pain --risk --due-before --hot --text --limit --json` |
| `guard.py` | 0 | PreToolUse guard, reading the hook JSON on stdin. **Exit 2** + reason when: a non-manager writes `knowledge/ AGENTS.md CLAUDE.md scripts/ runner/ .agents/ .claude/ .codex/`; anyone edits an existing `raw/` file; a rep edits an account owned by someone else; a rep edits another rep's file or sets `role: manager`. Allowed: everything while `reps/` is empty (bootstrap); a new user creating their own `reps/<id>.md` with `role: rep`. Otherwise exit 0 |
| `lint.py` | 0 | Schema vs templates; ontology terms; product ids; known owners; broken links; orphan contacts; idle claims > 21 days; overdue actions; unsourced Signals bullets; raw files past retention; suppression hits with open drafts; skills mirror; registry-ID formats per market (UEN, SSM 12-digit, CIN 21-char, GSTIN 15-char); `market` set on every account. Later phases add: VAM out-of-bounds edits (diff vs last commit), allocation constraint violations, `signals.csv` rows without snapshots. `--json` for weekly. Exit 1 on errors |
| `sync_skills.py` | 0 | Copy `.agents/skills/` → `.claude/skills/` (no symlinks); `--check` exits 1 on drift |
| `eval.py` | 1 | Runs the PLAN.md §16 checks over `evals/`, the wiki and logs; prints pass/fail |
| `fetch_dataset.py` | 2 | Download a dataset or RSS/page source listed in `sources.yaml` (urllib) into `raw/signals/<date>/<source>/` as CSV/JSON extracts filtered to the lookback window |
| `resolve.py` | 2 | Entity resolution within a market: registry ID (UEN / SSM / CIN, LLPIN / GSTIN, Udyam) → domain → normalised name + city (difflib similarity) → confidence. Writes `log/signals.csv` rows and `log/review.csv` entries; `--decide <row> <account\|new\|reject>` for manager decisions |
| `score.py` | 3 | Per PLAN.md §8 from `scoring.yaml`, ontology, touches and the account market's ICP section; writes `score`, `tier`, `score_parts`, `score_updated`; prints hot accounts (jump ≥ threshold) as JSON |
| `recommend.py` | 3 | Signal → pain → product walk with fits / requires / skip_if_owned / decay; JSON candidates with chain and exclusions |
| `build_books.py` | 5 | `wiki/books/<rep>.md` and `wiki/books/team.md` per PLAN.md §11 |
| `claim.py` | 6 | `claim.py <id>...` (rep self-claim, tier C only if allowed), `--assign <rep> <id>...` (manager), `--release <id>`, `--reassign <from> <to>`. Pull → verify → set owner fields → commit → push → re-verify on rejection |
| `allocate.py` | 6 | Per PLAN.md §10: market and territory constraints, values in base currency via `markets.yaml` FX → EV greedy → fairness swaps → reasons; writes `log/allocation/<date>.md` and `.csv`; `--approve all\|<ids>` calls `claim.py --assign` |

### Runner files (`runner/`, Phase 7)

`runner/nightly.sh` (macOS / Linux)
```bash
#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
mkdir -p runner/logs
TS=$(date +%Y%m%d-%H%M)
claude -p "/mama-nightly" \
  --permission-mode acceptEdits \
  --permission-prompts none \
  --allowedTools "Bash(python3 scripts/*),Bash(git pull *),Bash(git add *),Bash(git commit *),Bash(git push),Bash(git status *),WebSearch,WebFetch,Read,Edit,Write,Agent" \
  --output-format json > "runner/logs/$TS.json" 2>&1
# Codex alternative (enable network/web search for the sandbox in your Codex config first):
# codex exec --sandbox workspace-write "Run the mama-nightly skill" > "runner/logs/$TS.log" 2>&1
```
`runner/nightly.ps1`: the same for Windows (`python3` → whatever resolves).

**Schedule** (agent sets it up in Part B2):
- macOS / Linux: `crontab` → `0 2 * * * /path/to/sales-mama/runner/nightly.sh`
- Windows: `schtasks /create /sc daily /st 02:00 /tn SalesMamaNightly /tr "powershell -File C:\path\to\sales-mama\runner\nightly.ps1"`
- Codex users on Mac may use Codex app **Automations** instead (daily, prompt "Run the mama-nightly skill", target: local project).

---

## Part B — Onboarding (agent-led)

### B1. Rep (or manager) on their own machine
**The person does exactly this:** open the Claude desktop app → Code (or the Codex app), start a session in an empty folder, and type **"Set me up for Sales Mama from `<repo URL>`."**

**The agent runs `mama-setup`:**
1. Checks git, Python 3.10+ and PyYAML, and installs any that are missing. Clones the repo. If GitHub authentication fails, walks the person through signing in.
2. Sets `git config user.name/email` if missing (**asks**).
3. Asks: name, markets covered (SG, MY, IN), languages, territory (industries, regions, company size), daily quota, max active accounts, monthly meeting target, tone, email signature.
4. Writes `reps/<id>.md` with `role: rep`. Manager roles are only set by the manager.
5. Codex: asks the person to **trust the project**. Claude Code: approve the `@AGENTS.md` import prompt if it appears.
6. Checks the email connector is signed in to the person's own mailbox and that **no send tool is callable**. If one is callable, it stops and tells the manager.
7. Dry run: shows the person's book (empty is fine) and one sample draft for a fictional company, on screen only.
8. Syncs and prints the cheat sheet (Part C).

### B2. Runner (manager, once, on the runner machine)
**The manager types:** *"Set up the Sales Mama nightly runner on this machine."*

The agent runs `mama-setup --runner`:
1. Verifies the manager's identity and role.
2. Writes `runner/nightly.sh` or `.ps1` for this OS.
3. Runs it once in **dry-run** mode (`/mama-nightly dry-run` scans and scores without writing account pages) and shows the log.
4. **Asks** before scheduling at 02:00 local time, then schedules it and confirms the next run time.

---

## Part C — Cheat sheets

**Reps**

| I want to… | Claude Code | Codex |
|---|---|---|
| Do my whole morning | `/mama-day` | `$mama-day` or "run my day" |
| See my book | `/mama-book` | "show my book" |
| Handle replies | `/mama-replies` | `$mama-replies` |
| Work my allocated leads | `/mama-target` | "what's allocated to me?" |
| Research / pitch / write | `/mama-research acme` · `/mama-recommend acme` · `/mama-draft acme first` | plain English |
| Prep a call or event | `/mama-brief acme` · `/mama-brief sme-expo-2026` | "brief me on …" |
| Log a meeting | `/mama-handover acme` + paste notes | same |

**Manager**

| I want to… | Command |
|---|---|
| Morning cockpit | `/mama-manager` |
| Approve allocation | "approve all" / "approve except 3 and 7" / "give the logistics ones to Arun" |
| Confirm entity matches | "show the review queue" → "1 is Acme Trading, 2 is new, 3 reject" |
| Refresh a book now | `/mama-vam mei` |
| Run tonight's job now | `/mama-nightly` |
| Weekly review | `/mama-weekly` |

Rules of thumb: drafts land in your mailbox and you press send. Nobody edits `knowledge/` except through the manager. If the agent says it "can't verify" something, that's on purpose.

---

## Part D — Manager operations

- **Daily:** `/mama-manager` → approve or edit the allocation → clear the review queue → glance at risks.
- **Weekly:** `/mama-weekly` → read `log/weekly/<yyyy-Www>.md` → merge the PR (library, ontology, scoring, playbook proposals).
- **Markets:** each December, fill next year's holidays in `markets.yaml` (national, plus state holidays for reps' regions in MY and IN). Update FX rates monthly. To switch on a market, add its sources, ICP and guardrails sections and labelled set, then run `eval.py` before allocating leads there.
- **Change knowledge** (products, ICP, sources, weights): ask the agent in plan mode, on a branch; merge after review; run `eval.py`.
- **Add a rep:** grant repo access and send them Part B1. **Remove a rep:** `python3 scripts/claim.py --reassign <rep> <other>` (or let allocation redistribute), revoke repo and connector access, and set `role: inactive`.
- **Retention:** the weekly report lists expired `raw/` files. Approve, and the agent `git rm`s them in the weekly PR.
- **Runner health:** the manager brief starts with last night's status. Two failed nights → the cockpit shows the log tail and a fix.

---

## Part E — Troubleshooting (agent: try the fix, then explain it in one line)

| Symptom | Fix |
|---|---|
| Push rejected / sync conflict | `python3 scripts/sync.py`; if it persists, show `git status`, resolve only files the user owns, escalate the rest |
| Skill not found | `python3 scripts/sync_skills.py`, then start a new session |
| Hook didn't run (Claude Code) | Validate `.claude/settings.json`, check `python3` resolves, run the script by hand |
| `python3` not found (Windows) | Install Python 3.12 with winget, make `python3` resolve (alias if needed), restart the app |
| Guard blocked an edit | Expected for `knowledge/`, `raw/`, or others' accounts; offer to propose the change to the manager |
| Nightly didn't run | Check `runner/logs/`, that the runner was awake and online, and that `claude` / `codex` is signed in; run `/mama-nightly` by hand |
| Signal attached to the wrong company | `python3 scripts/resolve.py --decide <row> reject`; the agent removes the bullet and re-scores; add the case to the eval set |
| Scan too slow or costly | Lower `max_items_per_run`, narrow queries, use a cheaper scout model |
| VAM wrote outside its bounds | Lint flags it; the agent reverts that hunk and adds a regression case to `evals/` |
| Email connector not authorised | Re-run the connector sign-in for the user's own mailbox |
| Draft blocked for send window or channel | Expected: the market's rules apply; the agent tells the rep the next allowed window or channel |
| Wrong market or currency on an account | Manager fixes `market` (or the CRM mapping), then the agent re-scores and re-recommends |

---

## Part F — Skill and subagent specs

> **AGENT:** For each skill, create `.agents/skills/<name>/SKILL.md` with frontmatter `name` and `description` (copy exactly) and a body that expands the steps into clear instructions. Then run `sync_skills.py`. Every skill follows the AGENTS.md hard rules, ends with a 1–3 line summary, and appends to `wiki/log.md`.

### Rep skills

**mama-setup**
- **description:** Set up or health-check Sales Mama for the current user (or the nightly runner with --runner): prerequisites, profile, drafts-only email check, dry run, scheduling. Use when someone says "set me up", is new, or session start says the user is unknown.
- **Steps:** Part B1 (or B2 with `--runner`). On re-run, do a health check only: prerequisites, profile valid, connector signed in, no send tool, `lint.py`, `sync_skills.py --check`, runner schedule present (manager).

**mama-day**
- **description:** Run a rep's whole morning: replies, VAM pre-drafts, follow-ups due, allocated accounts, research, recommendations and drafts. Use for "run my day", "start my day".
- **Steps:**
  1. mama-replies.
  2. For each `## VAM notes` pre-draft due today, show it, then create the mailbox draft through mama-draft rules. If the rep says "send all to drafts", do the batch.
  3. Run mama-target (allocated queue).
  4. For each new account: research → recommend → draft. Claude Code runs `researcher` subagents, up to 5 in parallel; Codex runs sequentially.
  5. Summary: drafts ready and the send window, meetings requested, hot and at-risk counts.
- **Never** exceed quota; never send.

**mama-book**
- **description:** Show the current rep's book of accounts: due actions, hot and at-risk accounts, tiers, stages, targets and VAM highlights. Use for "show my book", "how's my pipeline".
- **Steps:** `build_books.py`, read `wiki/books/<rep>.md`, and present the top items with links. Offer the next action for the top 3.

**mama-target**
- **description:** Work the rep's allocated queue and, if allowed, self-claim tier C accounts from the pool. Use for "get my accounts", "what's allocated to me".
- **Steps:** `find.py --owner me --stage new` sorted by tier and score. If capacity remains and `self_claim: tier_c_only`, show the top tier C pool accounts in territory and claim on request via `claim.py`. Report anything lost to another claim.

**mama-research**
- **description:** Research one owned account and update its wiki page with cited signals, pains and contacts. Use for "research <company>" or from mama-day.
- **Steps:**
  1. Require `owner` = me.
  2. Read the existing linked signals first. Search the company site, last-12-months news in that market's sources, job posts, the market's registry and public business pages; about 8 fetches max.
  3. Snapshot each source to `raw/research/<id>/` (URL, date, ≤ 300 words of extracted relevant text).
  4. Map findings to ontology signals and pains; log any unmapped.
  5. Fill Snapshot, Signals, Pains and Contacts; set `stage: researched`; run `score.py --id <id>`.

**mama-recommend**
- **description:** Recommend best-fit products for an owned account from its signals using the ontology and catalog, with a traceable chain. Use for "what should I pitch" or from mama-day.
- **Steps:** `recommend.py <id> --json`. Write the top 1–2 to `## Recommendation` with the chain (signal → evidence → pain → product → proof) and talk track, and set `recommended:`. If there are no candidates, write "No fit now" with the reason.

**mama-draft**
- **description:** Draft an outreach message (connection note, first email, follow-up) for an owned account and save it as an email draft — never send. Use for "draft/write to <company>" or from mama-day.
- **Steps:**
  1. Checks: owner = me; contact and domain not suppressed; the stage allows the step; a recommendation exists for `first`; the channel is allowed in the account's market; the contact's language has an approved pattern.
  2. Choose an `approved` pattern by persona × pain × signal type, and record its id.
  3. Open with the freshest cited signal (or a `hook` signal such as an event).
  4. Use the recommended product (available in that market, priced in its currency), its proof, one CTA, and the playbook and the market's guardrails section.
  5. Run the entity check.
  6. Create the email draft via the connector and tell the rep the market's next send window (local time, skipping holidays). LinkedIn: ≤ 300 characters of text. WhatsApp (MY/IN, opted-in contacts only): short text for the rep to send manually.
  7. Append a touch, update Touch history and set the next action.

**mama-replies**
- **description:** Triage inbound replies for the current rep's accounts: log, classify, update the wiki, suppress unsubscribes, and draft answers from the approved library. Use for "check replies" or from mama-day.
- **Steps:**
  1. Find replies to tracked threads (or take pasted text). Mark matching `drafted` touches as `sent` if they are found in Sent.
  2. Snapshot each reply to `raw/replies/` and classify it.
  3. Update the stage, Touch history, Open objections and touches.
  4. Act on the class:
     - `unsubscribe` → add to suppression and set `do_not_contact`, immediately.
     - `objection` → link or create a `status: draft` objection page and draft the answer from approved responses.
     - `meeting_request` → put it at the top of the summary.
     - `referral` → create the contact.
  5. Re-score each touched account.

**mama-brief**
- **description:** Prepare a one-page brief for a call with an owned account, or a meet-list for a trade event. Use before a call, meeting or event ("brief me on <company|event>").
- **Steps:**
  - **Account:** who, why now (dated signals), what we believe (pains, recommendation chain), history, likely objections with approved answers, 3–5 questions, the call goal and next step. Write it to `## Call brief (<date>)`.
  - **Event:** the rep's matched accounts from `wiki/events/<id>.md`, sorted by tier, with a one-line hook and the open next action for each. Write it to the event page `## Plan`.

**mama-handover**
- **description:** Log a meeting outcome and produce handover notes and a CRM update row for an owned account. Use after a call or meeting.
- **Steps:**
  1. Save the notes to `raw/notes/<date>-<id>-call.md`.
  2. Update `## Meeting log & handover`: requirements, decision makers, timeline, budget signals, products discussed, risks, next step.
  3. Set the stage to `handed_over`, `nurture` or `closed_lost`.
  4. Append a touch (channel `meeting`, step `meeting`, status `meeting_held`).
  5. Write a `log/crm-updates/<date>.csv` row from `crm_mapping.yaml` import columns.

### Manager skills

**mama-ingest**
- **description:** Ingest new files from raw/ (CRM exports, lead lists, call notes) into the wiki. Use when files are added to raw/ or the user says ingest/import.
- **Steps:**
  - `crm/` (manager only): map with `crm_mapping.yaml` and update CRM-owned fields only (`name, market, reg_type, reg_id, alt_ids, domain, city, group, industry, employees, products_owned, contract_end, propensity`). Never touch `owner`, `stage` or `next_action`.
  - `crm/` contract ends within 120 days: emit `contract_ending` signals via `resolve.py`.
  - `lists/`: dedupe, then create `stage: new` pages.
  - `notes/`: update the owned account.
  - Finally run `score.py`, rebuild the index and log the counts.

**mama-scan**
- **description:** Scan external and internal signal sources from knowledge/sources.yaml with scout subagents, snapshot findings, resolve them to accounts, and attach cited signals. Use nightly or for "scan for signals".
- **Steps:**
  1. Group the live markets' sources by market and type, and spawn one `scout` per group (Codex: sequential if subagents are off).
  2. Each scout fetches within caps (`fetch_dataset.py` for datasets, RSS and pages; web search for news), writes snapshots and returns items as JSON (company text, signal, URL, snapshot path).
  3. Run `resolve.py` on all items.
  4. For `linked` items: add a Signals bullet and update frontmatter (owner's page edits are allowed for the runner as manager). For `new_lead`: create the account page with `source:`.
  5. Update `wiki/events/` for event items.
  6. Run `score.py` and report counts by status and source, plus hot accounts.

**mama-vam**
- **description:** Run virtual account managers over one book, all books, or the house pool: apply new signals and scores, set risk flags and next best actions, and pre-draft due follow-ups as text. Use nightly or for "refresh <rep>'s book".
- **Steps:**
  1. Select the accounts changed since `vam_updated`, plus any with actions due within 2 days.
  2. Spawn one `vam` per book (Codex: sequential).
  3. Each VAM sets `risk`, `nba` and `nba_reason`, writes pre-drafts and a 5-line book summary into `## VAM notes`, and updates `vam_updated`. It touches nothing else.
  4. The house VAM lists rising pool accounts for allocation.
  5. Rebuild the books.

**mama-allocate**
- **description:** Propose an allocation of unowned leads across reps using scores, capacity, territory, continuity and smoothed meeting rates; explain each assignment; apply the manager's approval or edits. Use for "allocate leads", "who should get these", or from mama-manager.
- **Steps:**
  1. Run `allocate.py` and present the proposal by market: per rep the count, EV (base currency) and a reason, plus rebalancing suggestions.
  2. Accept "approve all", partial approval or natural-language edits. Re-run with constraints if the manager edits.
  3. Apply with `--approve`, then sync and log.
- **Never** applies without explicit approval.

**mama-manager**
- **description:** The manager's morning cockpit: last night's status, hot accounts, risks, the allocation proposal to approve, the entity review queue, and the team book. Use for "morning brief", "manager view", or each morning.
- **Steps:**
  1. Read `log/briefs/<today>-manager.md` (or build it if the runner didn't run).
  2. Present the following in order: runner status → hot accounts → at-risk by rep → allocation proposal → review queue → team book highlights.
  3. Take decisions conversationally: approve allocation via mama-allocate, review decisions via `resolve.py --decide`, reassignments via `claim.py`.

**mama-nightly**
- **description:** The unattended nightly job for the runner: scan, score, VAMs, allocation proposal, manager brief, lint and sync. Use for scheduled runs or "run tonight's job now"; "dry-run" scans and scores without writing account pages.
- **Steps:** pull → mama-scan → `score.py` → mama-vam (all books + house) → `allocate.py` (proposal only, never `--approve`) → write `log/briefs/<date>-manager.md` → `lint.py` → `build_books.py` → sync.
- Stop on a hard error and record it in the brief. Ask nothing; no human is present.

**mama-weekly**
- **description:** Weekly review for the manager: lint, funnel and reply metrics, score calibration, allocation fairness, library and ontology proposals, retention clean-up, as a report and a PR. Use for "weekly review" or Fridays.
- **Steps:**
  1. `lint.py --json` plus LLM lint.
  2. Metrics by rep, pattern, persona, pain, signal type, product and tier for the week and the trailing 4 weeks. Label n < 20 as "insufficient data".
  3. Score calibration: a lift table by tier, and proposed weight changes if A < 2× C.
  4. Allocation review: EV spread, rep conversion by segment, lapsed claims.
  5. Library: promote, retire and update stats.
  6. Propose ontology terms for unmapped signals.
  7. Write `log/weekly/<yyyy-Www>.md`.
  8. On branch `weekly/<yyyy-Www>`, commit the proposals and approved retention `git rm`s, push, and open a PR (via `gh` if available, otherwise give the compare link).

### Subagents

| Name | Claude Code (`.claude/agents/<name>.md`) | Codex (`.codex/agents/<name>.toml`) | Instructions |
|---|---|---|---|
| `scout` | tools: Read, Write, Bash, WebSearch, WebFetch · model: a cheaper model (e.g. `haiku`) | `developer_instructions` same as body · `model_reasoning_effort = "low"` | "Scan only the sources you are given, within their caps. Follow AGENTS.md rule 9. Write snapshots to `raw/signals/<date>/<source>/`. Return a JSON list of {market, company_text, reg_id?, domain?, city?, signal, url, snapshot}. Never edit wiki pages." |
| `researcher` | tools: Read, Write, Edit, Bash, WebSearch, WebFetch | `developer_instructions` same as body | "Follow the mama-research skill for exactly one owned account id. Touch no other account." |
| `vam` | tools: Read, Edit, Bash | `developer_instructions` same as body | "You are the virtual account manager for one book. For each account given, apply AGENTS.md rule 11 strictly: write only `## VAM notes` and the VAM fields. Set risk, nba, nba_reason, pre-drafts for due steps (using approved patterns), and return a 5-line book summary." |

Codex subagents are experimental: enable `multi_agent` in `~/.codex/config.toml` and verify the project-scoped agents load in your version. If they don't, the skills run the same steps sequentially.
