<p align="center">
  <img src="docs/assets/hero.png" alt="Sales Mama: the AI sales teammate that drafts, never sends" width="100%">
</p>

<p align="center">
  <a href="#-quick-start-end-to-end-with-claude-code"><img alt="Claude Code native" src="https://img.shields.io/badge/Claude%20Code-native-6D28D9?style=flat-square"></a>
  <a href="#using-codex"><img alt="Codex compatible" src="https://img.shields.io/badge/Codex-compatible-16131F?style=flat-square"></a>
  <a href="#%EF%B8%8F-safety-by-design"><img alt="Drafts only, never sends" src="https://img.shields.io/badge/email-drafts%20only-C2410C?style=flat-square"></a>
  <a href="#-quality-you-can-check"><img alt="Self-test 135 of 135 passing" src="https://img.shields.io/badge/self--test-135%2F135-15803D?style=flat-square"></a>
  <a href="#-quality-you-can-check"><img alt="Evals 13 pass, 0 fail" src="https://img.shields.io/badge/evals-13%20pass%20%C2%B7%200%20fail-15803D?style=flat-square"></a>
  <a href="LICENSE"><img alt="Apache 2.0 licence" src="https://img.shields.io/badge/licence-Apache%202.0-5B5670?style=flat-square"></a>
</p>

<p align="center">
  <b>An agentic sales assistant for small B2B sales teams in Singapore, Malaysia and India.</b><br>
  It watches the market overnight, researches and scores every lead, and writes the first email.<br>
  People press send.
</p>

<p align="center">
  <a href="#-the-sales-problem">Why</a> ·
  <a href="#-how-it-works">How it works</a> ·
  <a href="#%EF%B8%8F-see-it-working">Screens</a> ·
  <a href="#-quick-start-end-to-end-with-claude-code">Quick start</a> ·
  <a href="#%EF%B8%8F-operating-it-day-to-day">Daily use</a> ·
  <a href="#%EF%B8%8F-roadmap">Roadmap</a>
</p>

<br>

<p align="center">
  <img src="docs/assets/demo.gif" alt="Sales Mama console tour: manager cockpit, allocation proposal, a rep's book, a cited account page and the morning run" width="92%">
  <br><sub>The optional console replaying recorded runs. All companies are fictional demo data. <a href="docs/assets/demo.mp4">MP4</a></sub>
</p>

<br>

## 🎯 The sales problem

A small B2B team (one manager and a handful of reps) sells to thousands of SMBs with no SDRs, no RevOps and no data team. Every week the same things go wrong.

| The problem | What Sales Mama does |
|---|---|
| **Leads go cold in the CRM** | Scans news, tenders, registries and trade events every night, then links each signal to the right account |
| **Research eats the selling hours** | Researches accounts in parallel. Every fact links to a saved source, or it says "unknown" |
| **Leads handed out by gut feel** | Scores every lead in parts you can explain, proposes a fair split, and waits for the manager to approve |
| **Follow-ups slip** | A virtual account manager watches every book each night and sets the next best action |
| **Generic emails nobody answers** | Each draft opens with a real signal, in the rep's tone, using only approved products and proof |
| **Compliance is an afterthought** | Per-market guardrails (PDPA SG, PDPA MY, DPDP IN), send windows, holidays and unsubscribe lines |

> **The result:** a rep types `/mama-day` and finds their replies triaged, new accounts researched and emails waiting as **drafts in their own mailbox**. Sales Mama never sends a message, and never assigns a lead without the manager's approval.

<br>

## ✨ What it does

<table>
<tr>
<td width="50%" valign="top">

**For reps**

- `/mama-day` runs the whole morning
- Replies triaged, unsubscribes suppressed
- Cited research on every new account
- What to pitch, as signal → pain → product → proof
- Emails and follow-ups saved as drafts
- Briefs before calls and trade events
- Handover notes plus a CRM update row

</td>
<td width="50%" valign="top">

**For the manager**

- `/mama-manager` is the morning cockpit
- Last night's run, hot accounts, risks by rep
- Allocation proposals, approved in one sentence
- A review queue for uncertain company matches
- The team book: capacity, tiers, meetings
- `/mama-weekly`: funnel, calibration and fairness, delivered as a PR

</td>
</tr>
</table>

<br>

## 🧭 How it works

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/architecture-dark.svg">
    <img src="docs/assets/architecture-light.svg" alt="How Sales Mama works: overnight, scouts find signals, resolve.py links them, score.py tiers them, VAMs set next steps and allocate.py proposes a split. The manager approves at 08:30. Each rep runs /mama-day at 08:45: research, recommend, draft into their own mailbox. In the send window a person presses send, and replies, handover and the weekly review calibrate tomorrow's scores." width="100%">
  </picture>
</p>

Three ideas hold it together:

- **The repo is the system.** There is no server and no database. State is Markdown, YAML and CSV in one private git repo, and a hook commits and pushes after every session.
- **Maths in scripts, judgement in the LLM.** Scores, allocation and product fit come from small Python scripts with parts you can explain. The agent researches, explains and drafts.
- **People hold the pen.** Reps press send and the manager approves allocations. Agents prepare everything up to that point.

<details>
<summary><b>The four layers of the repo</b></summary>
<br>

| Layer | Folder | Who writes it | What's in it |
|---|---|---|---|
| Truth | `knowledge/` | Manager only, by PR | Company, ICP per market, ontology, products, proof, sources, scoring, allocation, playbook, guardrails |
| Sources | `raw/` | Added, never edited | CRM exports, lead lists, call notes, replies, source snapshots (headline and summary only) |
| Memory | `wiki/` | Agents, within ownership rules | Accounts, contacts, events, response library, books, index, an append-only log |
| Activity | `log/` | Append-only | Touches, signals, review queue, allocation proposals, briefs, CRM updates, weekly reports |

</details>

<details>
<summary><b>The agents and their limits</b></summary>
<br>

| Agent | Job | Limits |
|---|---|---|
| Scout | Scans one source group and saves headline-and-summary snapshots | Never edits wiki pages; no scraping behind logins |
| Researcher | Researches one owned account: cited signals, pains, contacts | Only that account's page and its contacts |
| VAM | Watches one book: risk, next best action, text pre-drafts | Never contacts anyone; never changes owner or stage |
| Writer | Writes drafts from approved patterns | Drafts only; checks suppression and names first |
| Allocator | Proposes who gets which lead | Nothing is assigned until the manager approves |

At most five subagents run in parallel.

</details>

<br>

## 🖥️ See it working

<table>
<tr>
<td width="50%"><img src="docs/assets/screens/manager-run.jpg" alt="Manager cockpit: nightly run status and allocation proposal"><br><sub><b>Manager cockpit.</b> Last night's run and an allocation proposal. Nothing is assigned until the manager approves it.</sub></td>
<td width="50%"><img src="docs/assets/screens/book.jpg" alt="A rep's book card"><br><sub><b>A rep's book.</b> Capacity, meetings against target, tier mix, hot accounts and one-click next steps.</sub></td>
</tr>
<tr>
<td width="50%"><img src="docs/assets/screens/source.jpg" alt="Source drawer showing an account page"><br><sub><b>Grounded, always.</b> Source chips open the real wiki page behind a card, with its score parts and signals.</sub></td>
<td width="50%" align="center">
<img src="docs/assets/screens/mobile-day.jpg" alt="Mobile morning summary" width="44%">&nbsp;
<img src="docs/assets/screens/mobile-manager.jpg" alt="Mobile allocation proposal" width="44%">
<br><sub><b>On the go.</b> The same cards at phone width.</sub></td>
</tr>
</table>

<details>
<summary><b>More screens</b></summary>
<br>

| | |
|---|---|
| <img src="docs/assets/screens/manager-brief.jpg" alt="Manager morning brief"><br><sub><b>Morning brief.</b> Runner status, soft errors and hot accounts, each linked to its source.</sub> | <img src="docs/assets/screens/day-plan.jpg" alt="The mama-day plan card"><br><sub><b>The morning run.</b> <code>/mama-day</code> as a live plan.</sub> |

</details>

The console is optional. Everything works the same as plain chat in Claude Code, whether in the desktop app, the CLI or an IDE.

<br>

## 🚀 Quick start: end to end with Claude Code

**You need:** Claude Code, git and Python 3.10+ (the manager); repo access and a Claude plan with Claude Code (each rep); an email connector with **drafts-only** scope (IT); one machine that stays on overnight (the runner); and Node 20+ if you want the console.

### 1 · Bootstrap the kit (manager, about 15 minutes)

```bash
git clone https://github.com/neam-lang/sales-mama.ai.git && cd sales-mama.ai
python3 -m pip install --user pyyaml
python3 scripts/selftest.py        # expect: 135/135 passed — all good
claude                             # or open the folder in the Claude desktop app → Code
```

Then type **"Set me up for Sales Mama."** It asks a few questions, one at a time, and writes your profile in `reps/`. The first profile becomes the manager. Approve the `@AGENTS.md` import prompt if Claude Code shows one.

<details>
<summary>What the hooks do from here on</summary>
<br>

| Hook | Runs | Does |
|---|---|---|
| `SessionStart` | `scripts/session_start.py` | Pulls, rebuilds the index and books, and prints your queue |
| `PreToolUse` (Edit/Write) | `scripts/guard.py` | Blocks writes to `knowledge/`, edits to `raw/` and edits to other reps' accounts |
| `Stop` | `scripts/sync.py` | Commits and pushes your work, and never force-pushes |

</details>

### 2 · Connect email, drafts only

Connect Gmail or Microsoft 365 in **claude.ai → Settings → Connectors** and grant the draft permissions. Send, reply and forward are already denied in `.claude/settings.json`. Running "Set me up for Sales Mama" again checks that drafts work and that no send tool can be called.

### 3 · Teach it your business

In plan mode, ask Claude Code to interview you and fill `knowledge/`: products, ICP, markets, sources, scoring and guardrails. Then drop your CRM export into `raw/crm/` and run **`/mama-ingest`**. The full phase prompts are in [GUIDE.md §6](GUIDE.md#6-build-sales-mama-with-claude-code-phase-by-phase).

### 4 · Invite your reps (about 10 minutes each)

Give each rep repo access. They open Claude Code in an empty folder and type:

> **Set me up for Sales Mama from https://github.com/neam-lang/sales-mama.ai**

### 5 · Schedule the nightly run

On the machine that stays on: **"Set up the Sales Mama nightly runner on this machine."** It does a dry run first, then schedules 02:00 (launchd, cron or Task Scheduler) only after you say yes.

### 6 · Optional: open the console

```bash
npm run console          # → http://localhost:4173
```

It drives Claude Code headless and shows live agent lanes and cards, with the same permissions and no send button. Add `?replay=mama-day,mama-manager` to the URL to see recorded runs. More: [console/README.md](console/README.md).

<a id="using-codex"></a>
<details>
<summary><b>Using Codex instead of, or alongside, Claude Code</b></summary>
<br>

- Codex reads `AGENTS.md` and `.agents/skills/`. Invoke skills as `$mama-day` or in plain English.
- There are no hooks, so the agent runs `scripts/session_start.py` at the start and `scripts/sync.py` at the end.
- Subagents need `multi_agent = true` in `~/.codex/config.toml`; without it, steps run one after another.
- Trust the project so `.codex/config.toml` loads, and limit email `enabled_tools` to drafts.
- Nightly: `codex exec --sandbox workspace-write "Run the mama-nightly skill"`.

</details>

<br>

## 🗓️ Operating it day to day

| When (SGT) | Who | What |
|---|---|---|
| **02:00** | Runner | `/mama-nightly`: scan, resolve, score, VAMs, allocation proposal, brief, sync |
| **08:30** | Manager | `/mama-manager`: "approve all" or "approve except …", then clear the review queue |
| **08:45** | Each rep | `/mama-day`: replies, follow-ups, new accounts researched, drafts in the mailbox |
| **09:00–11:30** Mon–Thu | Each rep | **Send window.** Read, edit, press send |
| After a call | Rep | `/mama-handover acme`, paste notes: handover page plus CRM row |
| **Friday** | Manager | `/mama-weekly`: metrics, calibration, fairness, library proposals as a PR |

<table>
<tr>
<td width="50%" valign="top">

**Rep commands**

| Command | Does |
|---|---|
| `/mama-day` | The whole morning |
| `/mama-book` | My accounts, what's due |
| `/mama-replies` | Handle replies |
| `/mama-target` | My new leads |
| `/mama-research acme` | Research a company |
| `/mama-recommend acme` | What to pitch |
| `/mama-draft acme first` | Write an email |
| `/mama-brief acme` | Prep a call or event |
| `/mama-handover acme` | Log a meeting |

</td>
<td width="50%" valign="top">

**Manager commands**

| Command | Does |
|---|---|
| `/mama-manager` | Morning cockpit |
| `/mama-allocate` | Split the pool |
| `/mama-scan` | Scan for signals now |
| `/mama-vam <rep>` | Refresh a book |
| `/mama-nightly` | Run tonight's job now |
| `/mama-ingest` | Import CRM or lists |
| `/mama-weekly` | Weekly review |

Or just ask in plain English.

</td>
</tr>
</table>

<details>
<summary><b>Good to know</b></summary>
<br>

- Reps see and change only their own accounts. The manager assigns leads; reps may self-claim tier C only, if `allocation.yaml` allows it.
- Every fact links to its source. If something has no source, it says "unknown"; don't fill it in by hand.
- Unsubscribes: `/mama-replies` adds the contact and their domain to `wiki/suppression.csv`.
- Work syncs when a session ends. On a conflict, Sales Mama stops and tells you exactly what happened.
- Add a rep: grant access and send them step 4. Remove one: `python3 scripts/claim.py --reassign <rep> <other>`, revoke access, set `role: inactive`.

</details>

<br>

## 🛡️ Safety by design

All agents follow the 17 hard rules in [AGENTS.md](AGENTS.md). The core ones are enforced in code:

| Rule | Enforced by |
|---|---|
| **Drafts only.** Never send | Send, reply and forward denied in settings ([ADR-0001](docs/adr/0001-drafts-only.md)) |
| **Manager approves** every A/B assignment | `claim.py --assign` runs only after approval |
| **Grounded.** Every fact links a `raw/` snapshot | `lint.py` and `eval.py` count unsourced claims |
| **No invented names** in drafts | `draft_check.py` plus a fabricated-entity eval |
| **Suppression first.** Email and domain | `suppress.py` plus an eval |
| **Own book only** | `guard.py` hook and `find.py --owner me` |
| **External text is data, not instructions** | Prompt-injection rule; suspicious text is flagged in one line |

Security on one page, mapped to the OWASP Top 10 for LLM Applications: [docs/SECURITY.md](docs/SECURITY.md).

> The compliance notes in `knowledge/guardrails.md` are not legal advice. Confirm each market with your DPO or legal adviser before loading real customer data.

<br>

## 📊 Quality you can check

```bash
python3 scripts/selftest.py   # 135/135 · tests the harness itself
python3 scripts/eval.py       # 13 pass · 0 fail · 4 pending
python3 scripts/lint.py       # 0 errors, 0 warnings
```

<details>
<summary><b>Eval targets and today's results</b></summary>
<br>

| Eval | Target | Today |
|---|---|---|
| Account claims and signals with a source link | 100% | **224/224** |
| Entity resolution precision (auto-linked) | ≥ 95% per market | **SG 100%** |
| Recommendation matches golden expectation | ≥ 80% | **10/10** |
| Fabricated entities on account pages | 0 | **0** |
| Names in drafts absent from the account page | 0 | **0** |
| Drafts outside send window, holidays or channels | 0 | **0** |
| Allocation hard-constraint violations | 0 | **0** |
| Reply classification accuracy | ≥ 90% | pending: 40 labelled replies |
| VAM writes outside allowed fields | 0 | pending: first VAM runs |
| Tier A meeting rate vs tier C | ≥ 2× | pending: 4+ weeks of data |
| Draft quality (LLM judge) | ≥ 4/5 | pending: `/mama-weekly` |

</details>

**Found a mistake?** Tell the manager the account and what went wrong. Each mistake becomes a failing eval case **before** it's fixed, so it can't come back.

<br>

## 🗺️ Roadmap

**Now: Singapore pilot (started 2 Nov 2026)**
- Drafts straight into Gmail or Microsoft 365 for every rep
- Reply classification at 90% or better on 40 labelled replies
- VAMs on every book nightly, with zero out-of-bounds writes
- Five unattended nights, then the first weekly report and PR

**Next: Malaysia, then India**
- **Malaysia:** SSM IDs, WhatsApp talk tracks for opted-in contacts, Bahasa Malaysia patterns, MYR
- **India:** CIN, GSTIN and Udyam IDs; DPDP notice and consent settled before May 2027; INR
- Each market gets its own sources, ICP, guardrails, labelled sets and the same eval gates

**Later**
- Score calibration from real meetings (tier A should book at least 2× tier C)
- LLM-judge scoring of draft quality in the weekly review
- Codex in the console, via a `codex exec --json` reducer
- A vendor-hosted CRM connector for handover write-back

<details>
<summary><b>Build phases and status</b></summary>
<br>

| Phase | What | Status |
|---|---|---|
| 0 · Skeleton | Rules, hooks, guard, templates, `mama-setup` | ✅ Done |
| 1 · Knowledge + ingest | `knowledge/` by interview, CRM ingest, eval scaffold | ✅ Done |
| 2 · External signals | `mama-scan`, scouts, `resolve.py` | ✅ Done for SG |
| 3 · Score + research + recommend | `score.py`, `recommend.py`, researchers | ✅ Done |
| 4 · Outreach + responses | Drafts, replies, briefs, response library | 🟡 Mailbox and reply labels to go |
| 5 · Books + VAMs | `mama-book`, `mama-vam`, house VAM | 🟡 First VAM runs to go |
| 6 · Allocation + cockpit | `allocate.py`, `claim.py --assign`, `mama-manager` | ✅ Done |
| 7 · Nightly + weekly + handover | Runner, `mama-weekly`, `mama-handover` | 🟡 Schedule and 5 nights to go |
| 8 · Codex parity + pilot | Codex run-through, 2-rep SG pilot | 🟡 In progress |
| 9 · Console | Localhost cockpit with agent lanes and cards | ✅ Done for Claude Code |

Each phase has a "done when" gate in [PLAN.md §17](PLAN.md#17-build-plan-with-claude-code).

</details>

<br>

## 📣 Meetup talk

<table>
<tr>
<td width="36%"><a href="docs/assets/poster.png"><img src="docs/assets/poster.png" alt="Sales Mama meetup poster"></a></td>
<td valign="top">

**Sales Mama: your sales team's morning, done before coffee**<br>
Wednesday 4 November 2026 · Praveen Govindaraj

1. The small-team sales problem in Southeast Asia and India
2. Why the repo is the system: skills, subagents, hooks and a git wiki
3. Live: approve an allocation, then run `/mama-day`
4. Guardrails that hold: drafts only, cited facts, eval-first fixes
5. From a Singapore pilot to three markets

[Poster (print-ready PNG)](docs/assets/poster.png)

</td>
</tr>
</table>

<br>

## 📚 Docs

| Doc | For |
|---|---|
| [GUIDE.md](GUIDE.md) | Setup, daily use and the phase-by-phase build with Claude Code |
| [PLAN.md](PLAN.md) | The design and its reasons |
| [SETUP.md](SETUP.md) | Agent-executable setup, cheat sheets, troubleshooting, skill specs |
| [AGENTS.md](AGENTS.md) | The rules every agent follows |
| [docs/UI.md](docs/UI.md) | The chat UI and the `mama-card` protocol |
| [docs/SECURITY.md](docs/SECURITY.md) · [docs/adr/](docs/adr/) | Security on one page and the design decisions |

<details>
<summary><b>Repo map</b></summary>
<br>

```
knowledge/   company · icp · markets · ontology · products · proof · sources · scoring · allocation · playbook · guardrails
raw/         crm · lists · notes · replies · research · signals      (immutable inputs)
wiki/        accounts · contacts · events · responses · books · index · log · suppression
log/         touches · signals · review · allocation · briefs · crm-updates · weekly
reps/        one profile per person
scripts/     score · recommend · resolve · allocate · claim · guard · lint · sync · eval · selftest …
.agents/skills/ → .claude/skills/    17 mama-* skills
.claude/agents/ .codex/agents/       scout · researcher · vam
runner/      nightly job (macOS/Linux, Windows)
console/     optional localhost cockpit (Node 20, Vite, React)
evals/       labelled sets and golden accounts
docs/        UI · SECURITY · LEARNINGS · adr · assets
```

</details>

<br>

<p align="center">
  <sub>Built with <a href="https://claude.com/claude-code">Claude Code</a> · Apache 2.0 · All companies in screenshots are fictional demo data</sub>
</p>
