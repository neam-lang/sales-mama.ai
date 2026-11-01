# Sales Mama v2 — Plan & Write-up

> Agentic, chat-driven harness for **sales reps and their manager** selling to SMBs in **Singapore, Malaysia and India**, running natively in **Claude Code** or **Codex**.
> It keeps everyone's book of accounts, scores leads from internal data and external events (news, tenders, registrations, trade events), recommends products, prepares outreach with subagents, gives each book a **virtual account manager**, and proposes an **optimal allocation** of new leads across the team.
> A simplified TrustBridge: no servers and no database. The repo is the system, the agent loop is the runtime, and an LLM-maintained **Knowledge Wiki** is the memory.

| | |
|---|---|
| Users | 1 manager + up to 5 sales reps |
| Markets | Singapore, Malaysia, India (rolled out in that order) |
| Runtime | Claude Code (desktop / CLI / IDE) or Codex (app / CLI / IDE) |
| State | One private git repo of markdown, YAML and CSV |
| Automation | One nightly headless run on a single "runner" machine |
| Setup | Done by the agent. A rep types one sentence; the agent does the rest |
| Companion file | `SETUP.md`: the bootstrap the agent executes |

**What's new in v2:** manager role and cockpit · rep and team **books** · external **signal scanning** with scout subagents · explainable **lead scoring** · **virtual account managers** (VAMs) · **lead allocation** engine · nightly orchestration · **three markets** (SG, MY, IN) with per-market sources, IDs, compliance, send windows and currency (§5). (The admin role formerly called "lead" is now **manager**, so "lead" only ever means a sales prospect.)

---

## 1. What it does

| Engine exhibit | Sales Mama component |
|---|---|
| 1. Data & sources | CRM export + **external sources** (`knowledge/sources.yaml`) → `/mama-ingest`, `/mama-scan` |
| 2. Targeting & lists | **Lead scoring** (`scripts/score.py`) + **allocation** (`/mama-allocate`) + `/mama-target` |
| 3. Research & hooks | `/mama-research` (cited signals) + `/mama-recommend` (product fit from signals) |
| 4. Messaging & send | `/mama-draft` → email **drafts only**; VAMs pre-draft follow-ups overnight |
| 5. Replies & meetings | `/mama-replies` (triage, objection answers) + `/mama-brief` (call and event briefs) |
| 6. Testing & insight | `/mama-weekly` (replies vs sent, score calibration, allocation review, proposed changes) |
| 7. Pipeline & handover | `/mama-handover` + **books** (`/mama-book`, `/mama-manager`) |
| One-command day | Reps: `/mama-day`. Manager: `/mama-manager`. Nightly: `/mama-nightly` |

### Design principles

1. **Native only.** Skills (SKILL.md), subagents, AGENTS.md/CLAUDE.md, MCP connectors, headless runs (`claude -p`, `codex exec`) and a few small Python helpers (Python 3.10+, PyYAML only). Nothing to host.
2. **The wiki is compiled, not retrieved.** Knowledge is processed once, when it arrives, into readable pages.
3. **Humans own the truth; the LLM owns the synthesis.** `knowledge/` changes only through the manager's review. `wiki/` is agent-maintained. `raw/` is never edited.
4. **Grounded or nothing.** Every signal and account fact cites a source snapshot. Only catalogued products and proof appear in messages.
5. **Math is deterministic; judgment is the LLM's.** Scores, allocation and recommendations are computed by scripts with explainable parts. The agent explains, drafts and decides what to ask a human.
6. **Humans decide the irreversible.** People press send and the manager approves allocations. VAMs advise; they never contact anyone or change ownership.
7. **Git is the database and audit trail.** That works at 5 reps (see §14 for limits).

---

## 2. Architecture

```
 EXTERNAL                         INTERNAL                    PEOPLE
 news · tenders · registry        CRM export · notes          manager · reps (≤5)
 events · company sites           replies (email MCP)              │
        │                               │                          │
        ▼  scout subagents              ▼  ingest                  │
 raw/signals/ ──resolve──▶ log/signals.csv ─┐   raw/crm, notes     │
                     │                      ▼                      │
                     └─review queue─▶  wiki/accounts ◀── research (researcher subagents)
                                            │  ▲
                        score.py ◀──────────┘  │ VAM notes, NBA, risk (vam subagents)
                            │                  │
                     tiers A/B/C        recommend.py ◀── knowledge/ (ontology, products,
                            │                                scoring, allocation, playbook)
                     allocate.py ──▶ proposal ──▶ manager approves ──▶ owner set
                                                                        │
                     books (rep + team) ◀──────── touches.csv ◀── drafts / replies / meetings
                            │
                     /mama-weekly ──▶ calibration + PR to knowledge/ and responses/
```

### Three layers (Knowledge Wiki pattern)

| Layer | Folder | Who writes | Purpose |
|---|---|---|---|
| Sources | `raw/` | Agent adds new files; never edits them | CRM exports, lists, web and news snapshots, dataset extracts, replies, call notes |
| Wiki | `wiki/` | Agent (owner rep's sessions, VAMs, nightly run) | Accounts, contacts, events, response library, books, index, log |
| Schema & truth | `AGENTS.md`, `knowledge/` | Manager only | Rules, ICP, ontology, products, proof, sources, scoring, allocation, playbook, guardrails |

### Three wiki operations

| Operation | Trigger | What the agent does |
|---|---|---|
| **Ingest** | New CRM export, list, reply, call note, signal snapshot | Reads the source → creates/updates pages → cross-links → rebuilds index and books → appends to log |
| **Query** | "What changed in my book overnight?", "Who should get the new F&B leads?" | Reads `wiki/index.md` and books first, filters with `scripts/find.py`, opens only needed pages, answers with links |
| **Lint** | Nightly and `/mama-weekly` | Mechanical checks (schema, links, staleness, retention, allocation constraints) + LLM checks (contradictions, unsourced claims, weak patterns) |

---

## 3. Roles and daily rhythm

| When | Who | Command | What happens |
|---|---|---|---|
| 02:00 | Runner (manager identity, unattended) | `/mama-nightly` | Scan sources → resolve entities → score → VAMs refresh every book → allocation proposal → manager brief → lint → sync |
| 08:30 | Manager | `/mama-manager` | Overnight hot accounts, approve or edit the allocation, clear the entity review queue, team book, risks |
| 09:00 | Each rep | `/mama-day` | Replies triaged, VAM-prepared follow-ups turned into mailbox drafts, allocated accounts researched and drafted |
| Any time | Rep | `/mama-book`, `/mama-brief`, `/mama-handover`, plain English | Book view, call or event prep, meeting log |
| Friday | Manager | `/mama-weekly` | Metrics, score calibration, allocation fairness, library promotions, PR |

The **runner** is one always-on machine (the manager's laptop left on, or a small office PC) that runs the nightly job. It is the only place unattended work happens, which keeps writes predictable. If the runner misses a night, the manager can run `/mama-nightly` by hand in the morning.

---

## 4. Repository layout

```
sales-mama/
├── AGENTS.md  CLAUDE.md  PLAN.md  SETUP.md  README.md
├── knowledge/                    # MANAGER-OWNED · changes via PR only
│   ├── company.md  icp.md  playbook.md  guardrails.md   # icp + guardrails have a section per market
│   ├── markets.yaml              # SG / MY / IN: IDs, time zones, currency, languages, channels, send windows, holidays
│   ├── ontology.yaml             # industries, signals, pains, personas + links
│   ├── products/<id>.yaml        # one file per product (incl. typical value)
│   ├── proof/<id>.md             # case studies & stats, each with a source
│   ├── sources.yaml              # external + internal signal sources, trust, caps
│   ├── scoring.yaml              # lead-score weights, decay, tiers
│   ├── allocation.yaml           # capacity, constraints, fairness, priors
│   └── crm_mapping.yaml          # CRM export columns → fields; import columns
├── raw/                          # IMMUTABLE inputs
│   ├── crm/  lists/  notes/  replies/
│   ├── research/<account>/<date>-<slug>.md
│   └── signals/<date>/<source>/<slug>.md      # headline + own-words summary + URL
├── wiki/                         # LLM-MAINTAINED
│   ├── index.md                  # generated (gitignored)
│   ├── books/<rep>.md  books/team.md          # generated (gitignored)
│   ├── log.md  suppression.csv   # append-only, union-merged
│   ├── accounts/<account>.md
│   ├── contacts/<person>.md
│   ├── events/<event>.md         # trade events with matched accounts and a plan
│   └── responses/{objections,patterns,faq}/<id>.md
├── reps/<rep>.md                 # role, territory, capacity, targets, tone, signature
├── log/
│   ├── touches.csv               # every draft / send / reply / meeting (union)
│   ├── signals.csv               # every external/internal signal + match status (union)
│   ├── review.csv                # uncertain entity matches for the manager (union)
│   ├── allocation/<date>.md|.csv # proposals and decisions
│   ├── briefs/<date>-manager.md  # nightly manager brief
│   ├── crm-updates/<date>.csv
│   └── weekly/<yyyy-Www>.md
├── evals/  templates/  scripts/
├── .agents/skills/mama-*/SKILL.md   # canonical skills (Codex reads here)
├── .claude/skills/mama-*/SKILL.md   # mirrored copy (Claude Code reads here)
├── .claude/agents/{scout,researcher,vam}.md      # Claude Code subagents
├── .codex/agents/{scout,researcher,vam}.toml     # Codex subagents (experimental)
├── .claude/settings.json  .mcp.json  .codex/config.toml
├── .gitattributes  .github/CODEOWNERS
└── runner/                       # nightly scripts for cron / launchd / Task Scheduler
```

---

## 5. Markets: Singapore, Malaysia and India

Sales Mama sells into three markets. Each account has `market: SG | MY | IN`, and each rep covers one or more markets. Everything market-specific lives in `knowledge/markets.yaml` and a per-country section of `knowledge/guardrails.md`, so skills stay the same across markets.

| | Singapore (SG) | Malaysia (MY) | India (IN) |
|---|---|---|---|
| **Company ID** | UEN (ACRA) | SSM registration no. (12 digits: year + entity type + running no.) | CIN / LLPIN (MCA); GSTIN or Udyam no. for proprietorships and MSMEs |
| **Registry signals** | ACRA entity data on data.gov.sg (open data) | SSM search products (fee-based): use to verify, not to scan in bulk | MCA company master data via data.gov.in (CIN, status, incorporation date, address) |
| **Gov procurement** | Government procurement awards on data.gov.sg (GeBIZ) | MyProcurement / ePerolehan (confirm which award data is public) | CPPP (eprocure.gov.in) tender results and GeM (confirm terms) |
| **News & filings** | Business Times, CNA, The Edge Singapore, SGX announcements | The Edge Malaysia, The Star, NST, Bernama, Bursa announcements | Economic Times, Business Standard, Mint, Inc42 / Entrackr (funding), BSE/NSE announcements |
| **Incentive hooks** | EDGE Grant (replaced PSG and EDG for new applications from 30 Sep 2026) | Budget 2026 digitalisation and automation funding | MSME schemes; April fiscal-year budget cycle |
| **Privacy law** | PDPA 2012 | PDPA 2010 as amended in 2024 (new cross-border regime from 1 Apr 2025; DPO and breach notification from 1 Jun 2025) | DPDP Act 2023 + DPDP Rules 2025: consent-manager rules from Nov 2026; notice, consent, security, breach and rights duties from May 2027 |
| **Outreach rules** | Spam Control Act (`<ADV>` + unsubscribe for bulk); DNC Registry for calls/SMS | Honour direct-marketing opt-outs (PDPA right to prevent processing for direct marketing) | TRAI TCCCPR (amended 2025) governs commercial calls/SMS: registration and customer preferences. No automated calls or SMS |
| **Channels** | Email, LinkedIn (manual) | Email, WhatsApp (manual, opted-in), LinkedIn | Email, WhatsApp (manual, opted-in), LinkedIn, phone (manual) |
| **Languages** | English (Chinese optional) | English, Bahasa Malaysia (Chinese optional) | English, Hindi (regional optional) |
| **Time zone · currency** | UTC+8 · SGD | UTC+8 · MYR | UTC+5:30 · INR |

**`knowledge/markets.yaml`** (manager-owned):

```yaml
base_currency: SGD
fx: {MYR: <rate>, INR: <rate>}   # updated monthly; used only to compare deal value in allocation
markets:
  SG:
    tz: Asia/Singapore
    currency: SGD
    languages: [en, zh]
    id_types: [uen]
    channels: [email, linkedin]
    send_windows: {days: [mon, tue, wed, thu], hours: "09:00-11:30"}
    holidays: []                  # filled each December for the next year
  MY:
    tz: Asia/Kuala_Lumpur
    currency: MYR
    languages: [en, ms, zh]
    id_types: [ssm]
    channels: [email, whatsapp, linkedin]
    send_windows: {days: [mon, tue, wed, thu], hours: "09:30-11:30"}
    holidays: []                  # national + state holidays (rep regions)
  IN:
    tz: Asia/Kolkata
    currency: INR
    languages: [en, hi]
    id_types: [cin, llpin, gstin, udyam]
    channels: [email, whatsapp, linkedin, phone]
    send_windows: {days: [mon, tue, wed, thu, fri], hours: "10:00-12:30"}
    fiscal_year_start: "04-01"
    holidays: []                  # national + state holidays (rep regions)
```

**What changes per market:**
- **Identity & dedupe:** match on market + registry ID first (UEN; SSM no.; CIN/LLPIN, then GSTIN/Udyam), then domain, then name + city. `lint.py` checks ID formats.
- **ICP & scoring:** `icp.md` has a fit section per market, since size bands and target industries differ. Scores are comparable across markets because fit is scored against that market's ICP.
- **Products:** each product lists `available_in` and price and `typical_value` per market currency, plus any incentive schemes it qualifies for.
- **Allocation:** market is a hard constraint. Deal value is converted to the base currency only for comparing expected value.
- **Drafting:** the market's send window and holidays (in the market's time zone), channels, language and guardrails section. Non-English drafts need an approved pattern in that language and are flagged for rep review.
- **WhatsApp and phone:** text and talk tracks for the rep to use manually, only for contacts who opted in or engaged. Sales Mama never sends WhatsApp messages, SMS or calls.

**Rollout order: Singapore → Malaysia → India.**
- Singapore has the best open data and is the simplest compliance case. Pilot there.
- Malaysia shares the time zone and adds WhatsApp and Bahasa Malaysia.
- India comes last. It has the highest lead volume (watch the §14 limits), the most language variety, and DPDP obligations from May 2027, so build notice and consent handling before scaling Indian outreach.

---

## 6. Knowledge layer: products, ontology, sources, scoring, allocation

**`knowledge/ontology.yaml`** is a closed vocabulary. External events become **signals**, signals imply **pains**, and products solve pains.

```yaml
industries: [retail, fnb, logistics, professional_services, clinics, education]
signals:
  new_branch_opened:   {implies: [branch_expansion],   weight: 1.0, decay_days: 120}
  contract_win:        {implies: [scale_up],           weight: 0.9, decay_days: 90}
  new_company:         {implies: [setup_needs],        weight: 0.7, decay_days: 60}
  hiring_ops_it:       {implies: [it_stretch],         weight: 0.6, decay_days: 60}
  office_move:         {implies: [connectivity_reset], weight: 0.8, decay_days: 90}
  exhibiting_at_event: {implies: [],                   weight: 0.5, decay_days: 30, hook: true}
  funding_round:       {implies: [scale_up],           weight: 0.8, decay_days: 90}
  incentive_window:    {implies: [],                   weight: 0.4, decay_days: 60, hook: true}  # e.g. SG EDGE, MY Budget 2026 schemes
  fiscal_year_start:   {implies: [],                   weight: 0.3, decay_days: 45, hook: true, markets: [IN]}
  contract_ending:     {implies: [renewal_window],     weight: 1.0, decay_days: 120}
  layoffs_or_closure:  {negative: true,                weight: -0.6, decay_days: 180}
pains:
  branch_expansion: {personas: [owner_md, ops_head]}
  scale_up:         {personas: [owner_md, finance_head]}
personas:
  owner_md: {title_patterns: ["owner", "founder", "managing director"]}
```

`hook: true` signals don't imply a pain. They give the message a reason to reach out, such as "see you at the expo".

**`knowledge/products/<id>.yaml`**: as in v1, plus `available_in: [SG, MY, IN]`, `price` and `typical_value` per market currency (e.g. `typical_value: {SG: 6000, MY: 15000, IN: 300000}`) for allocation, and optional `incentives:` it qualifies for per market.

**`knowledge/sources.yaml`**: where signals come from. Every source has a trust weight, a cap and a ToS check date.

```yaml
defaults: {max_items_per_run: 30, lookback_days: 2}
sources:
  - id: sg-news-sme
    market: SG
    type: news                  # headlines + link + own-words summary only
    access: search              # search | rss | dataset | page | internal
    query: 'Singapore SME "new outlet" OR expansion OR acquisition'
    trust: 0.9
    tos_checked: 2026-11-01
  - id: sg-gov-procurement
    market: SG
    type: gov_procurement       # awarded contracts → contract_win
    access: dataset             # data.gov.sg government procurement dataset
    trust: 1.0
  - id: sg-acra
    market: SG
    type: registry              # new registrations → new_company (ICP-filtered)
    access: dataset             # ACRA entity data on data.gov.sg
    trust: 1.0
  - id: my-news-sme
    market: MY
    type: news
    access: search
    query: 'Malaysia SME expansion OR "new branch" OR "secures contract"'
    trust: 0.9
  - id: my-bursa
    market: MY
    type: filings               # listed-company announcements
    access: page
    trust: 1.0
  - id: in-mca
    market: IN
    type: registry              # MCA company master data via data.gov.in
    access: dataset
    trust: 1.0
  - id: in-funding-news
    market: IN
    type: news                  # funding rounds → funding_round
    access: search
    query: 'India startup OR MSME raises funding Series'
    trust: 0.8
  - id: in-cppp-results
    market: IN
    type: gov_procurement       # tender results → contract_win (confirm terms)
    access: page
    trust: 1.0
  - id: trade-events
    market: [SG, MY, IN]
    type: events                # exhibitor lists → exhibiting_at_event
    access: page
    url: <event calendar or exhibitor list URL per market>
    trust: 0.8
  - id: crm-contracts
    market: [SG, MY, IN]
    type: internal              # contract end within 120 days → contract_ending
    access: internal
    trust: 1.0
```

**`knowledge/scoring.yaml`**: explainable lead score, from 0 to 1.

```yaml
weights: {fit: 0.35, intent: 0.40, propensity: 0.15, engagement: 0.10}
# fit is scored against the account's own market section in icp.md
fit:        {industry_match: 0.4, size_in_range: 0.3, region_match: 0.1, owns_prerequisite: 0.2}
intent:     # Σ signal.weight × source.trust × decay(age), capped at 1
  decay: exponential            # half-life = decay_days / 2
engagement: {replied: 0.6, meeting: 1.0, no_reply_after_3: -0.3}
tiers: {A: 0.70, B: 0.45}       # below B → C
hot_alert: {score_jump: 0.20}   # flag accounts whose score jumps overnight
```

`propensity` is optional: a next-product-to-buy or propensity score column from the CRM export, normalised to 0–1. Each account stores `score`, `tier` and `score_parts`, so anyone can see *why* it scored as it did.

**`knowledge/allocation.yaml`**: how new leads are split across reps.

```yaml
mode: manager_approves          # or auto_for_tier_c
markets: hard                   # reps only get leads in markets they cover
territory: hard                 # never assign outside a rep's territory
continuity: true                # same group / domain as an owned account → same rep
capacity_from: reps             # reps/<rep>.md max_active and daily_quota
fairness: {max_ev_spread: 0.20} # total expected value per rep within ±20%
prior_meeting_rate: {alpha: 2, beta: 18}   # ≈10% prior, smoothed per rep × industry
self_claim: tier_c_only         # reps may self-claim only tier C from the pool
```

---

## 7. External signals: scanning, resolution, events

`/mama-scan` runs nightly. It fans out **scout subagents**, one per source group (news, datasets, events, internal).

1. **Fetch.** Search queries or RSS for news; dataset downloads for government data; page reads for event exhibitor lists; the latest CRM export for contract dates. Stays within `max_items_per_run`.
2. **Snapshot.** Save `raw/signals/<date>/<source>/<slug>.md` with URL, date, headline, a ≤ 60-word summary **in our own words**, and the company names mentioned. Never store full article text; respect paywalls.
3. **Extract.** Map each item to ontology signals. Anything that doesn't map is logged as `unmapped`.
4. **Resolve** (`scripts/resolve.py`). Match company text to accounts in the same market by registry ID (UEN; SSM no.; CIN/LLPIN, then GSTIN/Udyam), then domain, then normalised name + city with fuzzy matching.
   - Confidence ≥ 0.90 → linked automatically.
   - 0.70–0.90 → `log/review.csv` for the manager.
   - < 0.70 → if it fits the ICP, a new `stage: new` lead page tagged `source: <id>`; otherwise dropped.
   - Every outcome goes to `log/signals.csv`. This is the guard against attaching news to the wrong company.
5. **Attach.** For linked accounts, add a cited bullet to `## Signals` and update the `signals:` frontmatter. Recommendations update automatically, because new signals flow through `recommend.py`.
6. **Events.** Each trade event gets `wiki/events/<id>.md` (dates, venue, link, matched accounts, owners). Reps can ask `/mama-brief <event>` for a meet-list with a one-line hook per account.

---

## 8. Lead scoring

`scripts/score.py` runs after every scan and every ingest. For each account it computes:

- **fit**: ICP and firmographic match from `icp.md` rules.
- **intent**: Σ signal weight × source trust × decay(age), capped at 1. Negative signals subtract.
- **propensity**: the optional CRM prior.
- **engagement**: replies and meetings from `touches.csv`.

The result is written as `score`, `tier`, `score_parts` and `score_updated`. Accounts whose score jumps ≥ `hot_alert.score_jump` are flagged as **hot** in the owner's book and the manager brief.

**Calibration** (weekly): `/mama-weekly` compares tiers with outcomes, i.e. reply and meeting rates by tier over the trailing 4–8 weeks. If tier A doesn't convert at least ~2× tier C, it proposes weight changes as a PR, with the lift table as evidence. Samples under 20 are labelled "insufficient data" and drive no changes.

---

## 9. Subagents and virtual account managers

| Subagent | Spawned by | One per | Does | Writes |
|---|---|---|---|---|
| `scout` | `/mama-scan` | source group | Fetch, snapshot, extract signals | `raw/signals/`, `log/signals.csv` (via resolve) |
| `researcher` | `/mama-day`, `/mama-research` | account | Deep research on one owned account | `raw/research/`, account Signals/Contacts |
| `vam` | `/mama-nightly`, `/mama-vam` | book (rep or house) | Account management for the whole book | `## VAM notes` + VAM frontmatter only |

Claude Code: `.claude/agents/*.md`, with a cheaper model for scouts. Codex: `.codex/agents/*.toml`. Codex subagents are experimental and must be enabled; without them the same skills run sequentially.

### Virtual account managers (VAMs)

Each rep's book gets a VAM. There is also a **house VAM** for the unallocated long tail, the pool no human has capacity for. Nightly, each VAM does the following for every account in its book:

1. Applies new signals and the refreshed score. Flags **hot** accounts and tier changes.
2. Sets **risk** flags: no touch in > 14 days on an active account, an unanswered reply, a negative signal, a claim lapsing, or a contract ending soon with no plan.
3. Sets the **next best action** (`nba` + `nba_reason`), e.g. "Follow-up 2 — reference the GeBIZ award from 28 Oct".
4. **Pre-drafts** due follow-ups and hooks as text in `## VAM notes`. The rep's `/mama-day` turns approved ones into mailbox drafts. Drafts need the rep's own mailbox connection, so VAMs never create mailbox drafts themselves.
5. Writes a 5-line book summary used by `/mama-book` and the manager brief.

The house VAM also surfaces **rising** pool accounts (tier C → B/A) to the allocation queue.

**VAM boundaries:** a VAM never contacts anyone, never changes `owner` or `stage`, and writes only to `## VAM notes` and the fields `score*`, `tier`, `risk`, `nba*` and `vam_updated`. Lint enforces this. The human rep remains the account owner.

---

## 10. Lead allocation

`/mama-allocate` (manager) runs `scripts/allocate.py` and turns the result into a proposal the manager can approve with one sentence.

**Inputs:** unowned accounts by tier (A first), each rep's markets and territory, capacity (`max_active` minus active accounts, plus today's quota), targets, current book value, and history from `touches.csv`.

**Expected value of giving lead *L* to rep *R*:**
`EV(R, L) = score(L) × p_meet(R, segment(L)) × value(top recommended product of L)`, with value converted to the base currency using `markets.yaml` FX rates

`p_meet` is the rep's meeting rate for that industry, smoothed with a beta prior, so a rep with 1 meeting out of 2 touches isn't treated as a 50% closer. It falls back to the rep's overall rate, then to the team rate.

**Algorithm** (explainable, near-optimal at 5 reps × hundreds of leads):
1. **Hard constraints.** Market, territory, capacity, suppression, `do_not_contact`. Continuity forces a lead to the rep who owns its group or domain.
2. **Greedy pass.** Sort feasible (rep, lead) pairs by EV and assign while capacity remains.
3. **Fairness pass.** If the spread of total EV across reps exceeds `max_ev_spread`, swap the lowest-margin assignments between the top and bottom reps.
4. **Explain.** Each assignment gets a reason, e.g. *"Mei: F&B meeting rate 14% vs team 9%; 6 slots free; same group as Kopi Co."*.
5. **Output.** `log/allocation/<date>.md` (readable) and `.csv` (machine).

The manager approves everything, some of it, or edits it ("give the logistics ones to Arun"). `scripts/claim.py --assign` then sets `owner`, `allocated_on` and `allocated_by`. **Rebalancing** happens in the same pass: lapsed claims (21 days without a touch) and overloaded reps are flagged and proposed for reassignment.

Reps can still self-claim, but only tier C from the pool (`self_claim: tier_c_only`). A and B leads always go through allocation.

---

## 11. Books: account management for reps and the manager

`scripts/build_books.py` regenerates the books at every session start and every nightly run.

**Rep book** (`wiki/books/<rep>.md`, shown by `/mama-book`):
- Active accounts vs capacity, by tier and stage.
- Today: due actions, hot accounts, at-risk accounts, VAM pre-drafts waiting.
- Meetings this month vs target; replies and meetings in the last 7 days.
- Pipeline handed over this month.

**Team book** (`wiki/books/team.md`, used by `/mama-manager`):
- Per rep: active / capacity, A/B/C mix, touches, replies, meetings, conversion, at-risk count.
- Pool: size by tier, rising accounts, allocation backlog.
- Signals this week by source and industry; review-queue size.
- Funnel: new → researched → contacted → replied → meeting → handed over.

The account page itself (`wiki/accounts/<id>.md`) is unchanged from v1, plus the score, VAM and allocation fields, a `contract_end` field from the CRM, and a `## VAM notes` section.

---

## 12. Response management (unchanged in substance)

- **Inbound replies:** `/mama-replies` snapshots each reply, classifies it (`interested · meeting_request · objection · not_now · referral · wrong_person · unsubscribe · out_of_office · bounce`), updates the account, suppresses unsubscribes immediately, and drafts the answer from the library.
- **Response library** (`wiki/responses/`): objection, pattern and FAQ pages with outcome stats. Reps' sessions can propose pages (`status: draft`). Only `/mama-weekly` (manager) approves pages or updates stats. Drafts use approved content only.
- **New in v2:** objection and pattern stats are also cut **by score tier** and **by signal type**, so the weekly review can tell whether e.g. contract-win openers outperform branch-opening openers.

---

## 13. Skills

The canonical copies live in `.agents/skills/`, mirrored to `.claude/skills/`. Claude Code: `/mama-x`. Codex: `$mama-x` or plain English.

| Skill | Who | Purpose |
|---|---|---|
| `mama-setup` | anyone | Agent-led onboarding and health check |
| `mama-day` | rep | Replies → VAM pre-drafts → allocated accounts → research → recommend → draft |
| `mama-book` | rep | Show my book: due, hot, at-risk, targets |
| `mama-target` | rep | Work my allocated queue; self-claim tier C if allowed |
| `mama-research` | rep | Cited research on one owned account |
| `mama-recommend` | rep | Product fit from signals via `recommend.py` |
| `mama-draft` | rep | Connection note / first / follow-up as a mailbox draft |
| `mama-replies` | rep | Triage replies and draft answers from the library |
| `mama-brief` | rep | Call brief, or event meet-list |
| `mama-handover` | rep | Meeting log, handover notes, CRM update row |
| `mama-ingest` | manager (CRM) / rep (notes) | Load raw files into the wiki |
| `mama-scan` | manager / nightly | Scout subagents → signals → resolve → attach |
| `mama-vam` | manager / nightly | Run VAMs for one or all books |
| `mama-allocate` | manager | Allocation proposal, approval, rebalancing |
| `mama-manager` | manager | Morning cockpit: brief, approvals, review queue, team book |
| `mama-nightly` | runner | scan → score → VAMs → allocate (proposal) → brief → lint → sync |
| `mama-weekly` | manager | Metrics, calibration, fairness, library promotions, PR |

---

## 14. Team mode, safety and limits

| Concern | Mechanism |
|---|---|
| Identity & role | `git config user.email` → `reps/<rep>.md` (`role: rep` or `manager`) |
| Fresh state | Session start: pull, rebuild index and books, print queue |
| Saving work | Session stop: commit `wiki/ raw/ log/ reps/`, push, retry once |
| Concurrent appends | `merge=union` for `wiki/log.md`, `wiki/suppression.csv`, `log/touches.csv`, `log/signals.csv`, `log/review.csv` |
| Ownership | Allocation (manager-approved) + `claim.py`; VAMs and the runner never change `owner` |
| Protecting the truth | Guard hook + AGENTS.md rule + CODEOWNERS on `knowledge/` |
| Never auto-send | Email send tool denied in permissions; M365 `Mail.ReadWrite` only. VAMs write text, not drafts |
| Unattended runs | Only the runner; Claude `claude -p "/mama-nightly" --permission-mode acceptEdits` with a narrow `--allowedTools` list and `--permission-prompts none`; Codex `codex exec --sandbox workspace-write` or Codex app Automations |
| Cost control | Source caps, cheaper model for scouts, VAMs only touch accounts with changes since `vam_updated` |

The guard and AGENTS.md rules prevent *mistakes*; they are not a security boundary. Real controls are GitHub-side: private repo, CODEOWNERS review, and branch protection where your plan supports it.

**When to graduate to a TrustBridge-style service:** more than about 5–8 reps, more than about 5,000 active accounts (India alone can get there quickly, so keep the IN ICP tight), nightly scans that no longer finish in an hour, real-time dashboards, or role-based access to subsets of the data. `knowledge/`, the ontology, scoring weights and the response library migrate as-is.

---

## 15. Compliance & data handling (confirm with your DPO / legal in each country)

| | Singapore | Malaysia | India |
|---|---|---|---|
| Privacy law | PDPA 2012 | PDPA 2010, amended 2024 (DPO and breach notification since 1 Jun 2025) | DPDP Act 2023 + Rules 2025 (core duties from May 2027) |
| Email outreach | Spam Control Act for bulk unsolicited commercial email: `<ADV>`, unsubscribe, honoured within 10 working days | Honour opt-outs from direct marketing promptly; keep an unsubscribe line | Plan for DPDP notice/consent or a valid basis before May 2027; keep an unsubscribe line |
| Calls / SMS | DNC Registry checks for Singapore numbers | Honour opt-outs | TRAI TCCCPR rules for commercial calls/SMS; Sales Mama never automates them |
| Cross-border | PDPA transfer limitation | Transfers where the destination has substantially similar law or equivalent protection | DPDP cross-border rules from May 2027 |

Rules that apply in every market:
- **Data minimisation.** Business contact details only. No personal mobiles unless the contact gave them for business, no ID numbers, nothing about individuals from news beyond their business role. Retention is set per `raw/` folder in `guardrails.md`.
- **News and copyright.** Store headline, link and an own-words summary of ≤ 60 words. Never store full text or bypass paywalls. Re-check each source's terms (`tos_checked`).
- **Open data.** Follow dataset licences (data.gov.sg, data.gov.in).
- **WhatsApp and LinkedIn.** Manual sending only. WhatsApp only to contacts who opted in or engaged. No LinkedIn automation or scraping.
- **Event lists.** Use only lists the organiser publishes or shares lawfully.
- **Processors.** Account data passes through the model provider and GitHub. Confirm both meet each country's transfer and processor rules before loading real customer data.

---

## 16. Quality: evals

| Check | Target |
|---|---|
| Account claims and signals with a source link | 100% |
| Entity resolution precision on 50 labelled items per market (auto-linked only) | ≥ 95% each |
| Drafts outside the market's send window, holidays or channels | 0 |
| Non-English drafts without an approved pattern in that language | 0 |
| Products or proof outside `knowledge/` in drafts | 0 |
| Names in drafts absent from the account page (fabrication check) | 0 |
| Suppressed contact drafted | 0 |
| Reply classification accuracy (≈40 labelled replies) | ≥ 90% |
| Recommendation matches golden expectation (10 accounts) | ≥ 80% |
| Allocation hard-constraint violations (territory, capacity, suppression) | 0 |
| VAM writes outside allowed fields and sections | 0 |
| Score calibration after 4+ weeks: tier A meeting rate vs tier C | ≥ 2× |
| Draft quality (LLM-judge rubric) | ≥ 4/5 |

`python3 scripts/eval.py` runs after every phase and any change to AGENTS.md, a skill or `knowledge/`.

---

## 17. Build plan with Claude Code

For each phase: open Claude Code in the repo, switch to **plan mode**, paste the phase prompt, review the plan, build, then run evals.

| Phase | Goal | Main deliverables | Done when |
|---|---|---|---|
| **0. Skeleton** | Repo runs, rules in place | Tree, AGENTS.md, CLAUDE.md, templates, configs, hooks, Phase 0 scripts, `mama-setup` | Lint passes on the empty wiki; guard blocks a rep write to `knowledge/` |
| **1. Knowledge + ingest** | The business is described; accounts exist | All `knowledge/` files incl. markets, sources, scoring, allocation; per-market ICP and guardrails; `mama-ingest`; evals scaffold | 50 accounts from a CRM export; contract dates mapped; lint clean |
| **2. External signals** | Overnight intelligence | `mama-scan`, `scout` subagent, `resolve.py`, `fetch_dataset.py`, events pages | ≥ 2 sources per market scanned; resolution precision ≥ 95% per market |
| **3. Score + research + recommend** | Explainable priorities | `score.py`, `recommend.py`, `mama-research`, `mama-recommend`, `researcher` | Tiers on all accounts; golden set 100% cited, ≥ 80% match |
| **4. Outreach + responses** | Drafts in, replies handled | Email MCP (drafts only), `mama-draft`, `mama-replies`, `mama-brief`, library seeded | Drafts in the mailbox; send denied; replies ≥ 90% |
| **5. Books + VAMs** | Every book managed | `build_books.py`, `mama-book`, `mama-vam`, `vam` subagent, house VAM | VAM run on 2 books: zero out-of-bounds writes; NBA on every active account |
| **6. Allocation + manager cockpit** | Leads go to the right rep | `allocate.py`, `mama-allocate`, `mama-manager`, `claim.py --assign`, review-queue flow | 0 constraint violations; manager approves a proposal in one message |
| **7. Nightly + weekly + handover** | It runs and learns | `mama-nightly`, `runner/` scripts, `mama-weekly` (with calibration), `mama-handover` | 5 consecutive unattended nights; first weekly report + PR |
| **8. Codex parity + pilot** | Works in both tools, with real users | `.codex/` agents and config, Codex run-through, README for reps, 2-rep pilot | All evals pass in Codex; SG pilot week → MY → IN rollout |
| **9. Console (optional)** | Colourful, chat-driven cockpit | `console/` per `docs/UI.md`: stream-json bridge, agent lanes, `mama-card` rendering, bento rail | Renders every card type from recorded streams; no permission widening (ADR-0006) |

Indicative pace at part-time effort: about 6–7 weeks to a Singapore pilot, then 1–2 weeks each to switch on Malaysia and India (sources, ICP, guardrails, labelled sets).

### Phase prompts (paste into Claude Code)

**Phase 0**
> Read PLAN.md and SETUP.md. Execute SETUP.md Part A exactly. Create every listed file, write the Phase 0 scripts (Python 3.10+, PyYAML only), run lint and the guard test, and show me the tree and results. Create only the `mama-setup` skill.

**Phase 1**
> Implement `mama-ingest`. Interview me, one topic at a time, to fill every `knowledge/` file including `markets.yaml` (SG, MY, IN), per-market sections of `icp.md` and `guardrails.md`, `sources.yaml`, `scoring.yaml` and `allocation.yaml`. Map my CRM export (including contract end dates) in `crm_mapping.yaml`, ingest `raw/crm/`, and scaffold `evals/` and `scripts/eval.py`.

**Phase 2**
> Implement `mama-scan`, the `scout` subagent (Claude and Codex versions), `scripts/resolve.py` and `scripts/fetch_dataset.py`. Validate registry-ID formats per market (UEN, SSM, CIN/LLPIN, GSTIN, Udyam). Scan the Singapore sources for the last 7 days, build a labelled set of 50 items in `evals/` with my help, and tune resolution until auto-link precision ≥ 95%. Repeat for Malaysia and India when we switch them on.

**Phase 3**
> Implement `scripts/score.py` and `scripts/recommend.py` from `scoring.yaml` and the ontology, then `mama-research`, `mama-recommend` and the `researcher` subagent. Score all accounts, research the 10 golden accounts, and fix failures until §16 targets pass.

**Phase 4**
> Connect the email MCP in drafts-only mode (deny send tools; restrict Codex `enabled_tools`). Implement `mama-draft`, `mama-replies` and `mama-brief` (including event meet-lists). Interview me for 10–15 objections and seed the library as drafts for my approval.

**Phase 5**
> Implement `scripts/build_books.py`, `mama-book`, `mama-vam` and the `vam` subagent, plus the house VAM for the pool. Run VAMs on two books, show me the NBA and risk flags, and prove with lint that VAMs wrote only allowed fields and sections.

**Phase 6**
> Implement `scripts/allocate.py` per PLAN.md §10, `claim.py --assign`, `mama-allocate` and `mama-manager`. Generate a proposal for the current pool, explain each assignment, and show that hard constraints hold and the EV spread is within `allocation.yaml`.

**Phase 7**
> Implement `mama-nightly`, the `runner/` scripts for my OS (Claude `claude -p` and Codex `codex exec` variants), `mama-weekly` with score calibration and allocation-fairness sections, and `mama-handover`. Schedule the nightly run and show me five nights of logs.

**Phase 8**
> Make Codex parity real: `.codex/agents/*.toml`, `.codex/config.toml`, a mirror check in lint, and a Codex run-through of every skill with differences recorded in README. Write the one-page README for reps. Then run a 2-rep Singapore pilot week, and switch on Malaysia, then India, one at a time.


**Phase 9 (optional console)** — see `GUIDE.md` §6 for the full prompt; design in `docs/UI.md` and `design/`.

---

## 18. What each person experiences

**Rep:**
- **Day 0:** "Set me up for Sales Mama from `<repo URL>`." About 10 minutes, agent-led.
- **Every morning:** `/mama-day`. Overnight changes in the book, replies handled, VAM follow-ups and new allocated accounts drafted into the mailbox. Review and press send.
- **Any time:** `/mama-book`, `/mama-brief acme`, `/mama-brief sme-expo-2026`, `/mama-handover acme`, or plain English.

**Manager:**
- **Every morning:** `/mama-manager`. What moved overnight, who is at risk, an allocation proposal ("approve", or edit in a sentence), and entity matches to confirm.
- **Fridays:** `/mama-weekly`. Funnel, score calibration, allocation fairness, library promotions, then merge the PR.
