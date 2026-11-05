# Sales Mama UI — agentic, chat-driven

Sales Mama has two front doors. Both talk to the **same** repo, skills and rules.

| | Native (default) | Sales Mama Console (optional, Phase 9) |
|---|---|---|
| What it is | Claude Code or Codex, in the desktop app, CLI or IDE | A local web app that drives Claude Code (or Codex) headless and renders its work as live cards |
| Who it suits | Anyone, from day one | Reps and managers who want a colourful, one-glance cockpit |
| How it looks | Chat + markdown pages (books, account pages) | Chat + live agent lanes + interactive cards + a bento side rail |
| Extra setup | None | Node 20+, then `npm run console` from the repo |
| Rules and safety | AGENTS.md, hooks, permissions | Exactly the same: the console only *sends prompts* and *renders output* |

The console never adds capabilities. It cannot send email or WhatsApp, change permissions or bypass the guard: sending needs the permission prompt of `send.py --send`, which the console skips, so sending happens only in chat in Claude Code (ADR-0007). Anything it can do, a rep can also do by typing in Claude Code.

---

## 1. Interaction model

Everything starts in chat. A rep types a slash command or plain English. The agent plans, fans out subagents, and answers with **cards**. Buttons on a card are just pre-written prompts.

```
You ▸ /mama-day
Mama ▸ plan card            (5 steps, ticking live)
     ▸ agent lanes          (researcher ×5 · vam ×1, progress bars)
     ▸ day_summary card     (drafts · hot · at-risk · needs-you)
     ▸ draft cards ×8       ([Open in mailbox] [Shorter] [Different opener])
     ▸ quick replies        ("Show my book" · "Brief me on Harbourlight")
```

Design principles:
1. **Chat is the cockpit.** No menus to learn: every screen is a conversation, and every card has a "why".
2. **Show the agents working.** Live lanes show which subagent is doing what, so a 3-minute run never feels stuck.
3. **Cards over walls of text.** Numbers, chains and drafts render as compact, colourful cards. Prose stays short.
4. **Every card is grounded.** Each card carries `refs` (wiki or raw paths), and the UI shows them as source chips.
5. **Humans hold the pen.** Buttons prepare drafts and proposals; sending and approving stay explicit human acts.

---

## 2. The card protocol (`mama-card`)

When the system prompt contains `MAMA_CARDS=on`, skills end with one or more fenced blocks:

````
```mama-card
{"type":"draft","title":"First email · Harbourlight Foods", ...}
```
````

Common fields on every card:

| Field | Type | Notes |
|---|---|---|
| `type` | string | One of the types below |
| `title` | string | Short, human |
| `subtitle` | string? | One line of context |
| `agent` | string? | `mama` · `scout` · `researcher` · `vam` · `writer` · `allocator`; sets the colour |
| `refs` | string[]? | Repo paths backing the card (`wiki/accounts/x.md`, `raw/research/...`) |
| `actions` | `{label, prompt, style?}`[]? | `prompt` is sent as the next user turn; `style` is `primary` or `secondary` |

Card types (full JSON Schema in `console/cards.schema.json`):

| `type` | Key fields | Used by |
|---|---|---|
| `plan` | `steps[{label, status, agent}]` (status: pending, running, done, failed) | every multi-step skill |
| `agents` | `lanes[{agent, label, done, total, status}]` | mama-day, mama-scan, mama-vam, mama-nightly |
| `day_summary` | `drafts, send_window, hot[], at_risk, needs_you[]` | mama-day |
| `draft` | `account, to, channel, subject?, body, signal, pattern, checks[], send_window` | mama-draft |
| `reply` | `account, from, class, summary, response_ref?` | mama-replies |
| `book` | `rep, active, capacity, tiers{A,B,C}, meetings{done,target}, replies_7d{replies,sent}, today[], hot[], at_risk[]` | mama-book |
| `account` | `id, name, market, tier, score, score_parts{fit,intent,propensity,engagement}, stage, owner, signals[], recommendation{chain[], product, proof, talk_track}, next{action, due}` | mama-research, mama-recommend, mama-brief |
| `brief` | `subject, sections[{heading, bullets[]}]` | mama-brief |
| `allocation` | `total, spread, limit, rows[{rep, market, leads_a, leads_b, ev, currency, why}]` | mama-allocate, mama-manager |
| `review_queue` | `items[{n, text, source, candidate, confidence}]` | mama-manager |
| `run_status` | `ok, started, finished, markets[], items, linked, review, new_leads, errors` | mama-nightly, mama-manager |
| `team_book` | `rows[{rep, market, active, capacity, a, b, c, sent_7d, replies_7d, meetings, target, at_risk}], pool{a,b,c}` | mama-manager |
| `error` | `message, fix` | any |
| `stats` | `tiles[{label, value, unit?, note?, tone?: good\|warn\|risk\|neutral}]` | company-insights |
| `chart` | `kind: bar\|hbar\|donut\|line`, `series[{label, value}]`, `unit?`, `note?` | company-insights |
| `table` | `columns[{key, label, align?}]`, `rows[]` (max 25) | company-insights |
| `company` | `uen, status, verdict, score, facts{}, groups[{name, checks[{id, check, result, detail}]}]` | company-insights |
| `compare` | `companies[{uen, name, verdict, score}]` (2–5), `rows[{check, values[{result, text}]}]` | company-insights |

Rules for skills:
- Cards come **after** a one-line plain summary, never instead of it.
- Never put anything in a card that isn't in the wiki, `raw/` or `knowledge/`. Cards are views, not new facts.
- Without `MAMA_CARDS=on`, never print card JSON. Use plain markdown tables instead.

---

## 3. Console architecture (Phase 9)

```
browser (localhost:4173) ──WebSocket── console server (Node) ──spawn── claude -p … --output-format stream-json
                                              │                         (or: codex exec --json)
                                              └── reads repo files for source chips and the bento rail
```

- **Engine:** spawn the local CLI in the repo folder, using each user's own sign-in on their own machine:
  `claude -p "<prompt>" --output-format stream-json --verbose --include-partial-messages --append-system-prompt "MAMA_CARDS=on" --resume <session>`.
  For Codex: `codex exec --json "<prompt>"`. Alternatively use the Agent SDK (TypeScript or Python) with an API key.
- **Event mapping:**
  - Text deltas → the streaming chat bubble.
  - Tool calls → small tool chips ("Reading wiki/accounts/…", "Running scripts/score.py").
  - Subagent messages (their `parent_tool_use_id`) → one **agent lane** each.
  - Task-list updates → the **plan** card.
  - `mama-card` blocks → rendered cards.
  - Errors → an `error` card with the fix.
- **Permissions:** the console runs with the project's `.claude/settings.json`. It never passes flags that widen permissions, and never offers a send button.
- **Side rail (bento):** a live read of `wiki/books/<rep>.md` (or `team.md` for the manager). It shows the meetings ring, tier mix, hot list and send window, and refreshes after each sync.
- **Stack:** Node 20 + TypeScript, React + Vite, a WebSocket bridge, no database. It runs on localhost only. Before offering it beyond your own team, check the current Anthropic and OpenAI terms on authentication.

---

## 4. Visual language (2026)

| Token | Value | Use |
|---|---|---|
| Ground | `#F6F4FF` | page background |
| Surface | `#FFFFFF` | cards |
| Ink | `#16131F` | text, dark hero panels |
| Muted | `#5B5670` | secondary text (≥ 4.5:1 on white) |
| Lime | `#C8F031` | highlights on dark panels, "live" pulses |
| Mama (violet) | `#6D28D9` / tint `#EFE8FF` | primary actions, Sales Mama |
| Scout (blue) | `#1D4ED8` / `#E5EDFF` | signal scanning |
| Researcher (teal) | `#0F766E` / `#DDF5F1` | account research |
| VAM (magenta) | `#BE185D` / `#FFE6F1` | virtual account managers |
| Writer (orange) | `#C2410C` / `#FFEDE0` | drafts |
| Allocator (green) | `#15803D` / `#E2F6E8` | allocation |
| Risk | `#B91C1C` | at-risk counts |

- **Type:** Bricolage Grotesque for display numbers and headings; Geist for UI text; Geist Mono for commands and paths.
- **Shape:** 20–28 px card radius, 999 px chips, 44 px minimum touch targets.
- **Motion:** live lanes pulse lime while running; cards slide in as they stream. Respect `prefers-reduced-motion`.
- **No** gradient washes, emoji or left-border callout cards. Colour comes from solid agent tints and bold numbers.
- **Mobile:** the chat column first, with the bento rail collapsing to a swipeable row of tiles; quick replies stay at the thumb zone.

The design canvas "Sales Mama UI" shows the target screens: rep morning run, ask-my-book, account brief, manager cockpit, and the mobile view.
