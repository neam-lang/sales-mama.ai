# Sales Mama Console (Phase 9)

An optional, local, chat-driven cockpit that drives Claude Code headless and renders its work as live agent lanes and colourful cards. Design and protocol: [`docs/UI.md`](../docs/UI.md). Visual target: [`design/canvas/`](../design/). Rules: [ADR-0006](../docs/adr/0006-console-renders-only.md).

```bash
npm run console          # from the repo root → http://localhost:4173
```

Needs Node 20+ and a signed-in `claude` CLI. The first run installs dependencies.

## What it does
- **Engine:** for each prompt, spawns `claude -p --output-format stream-json --verbose --include-partial-messages --append-system-prompt MAMA_CARDS=on [--resume <session>] -- <prompt>` in the repo root. The `--` means a prompt can never be read as a flag. One run at a time, because each run ends with a git sync.
- **Rendering:** streaming text, tool chips ("Reading wiki/accounts/…", "Running scripts/score.py"), one agent lane per subagent (from `parent_tool_use_id` and `task_*` events), a live plan (TodoWrite / TaskCreate / TaskUpdate), `mama-card` blocks validated against `cards.schema.json`, and a bento rail from `wiki/books/<me>.md` (plus `team.md` for the manager).
- **Cards:** buttons send their `prompt` as the next turn. A card that fails the schema still renders, best-effort, with its issues listed under it. Every `refs` path is a source chip that opens the file read-only.
- **Permissions:** no permission flags. The run uses `.claude/settings.json` as-is, so anything that needs approval is skipped and listed in a "needed your approval" card. No send button: actions whose label says "send" are dropped, and `send.py --send` needs a permission prompt the console never shows, so sending stays in Claude Code chat (ADR-0007).
- **Localhost only:** binds 127.0.0.1, and refuses requests and WebSocket upgrades from any other Host or Origin. Source chips can read only `wiki/ raw/ knowledge/ log/ reps/ templates/ docs/`, and symlinks must stay inside those folders too.

## Layout
| Path | What |
|---|---|
| `server/engine.ts` | CLI args and process handling |
| `server/repo.ts` | who am I (`git config user.email` → `reps/*.md`), rail, source chips |
| `server/index.ts` | HTTP + Vite middleware + WebSocket bridge (`/mama`) |
| `shared/stream.ts` | stream-json → turn reducer (text, chips, lanes, plan) |
| `shared/cards.ts` | `mama-card` splitting and schema validation |
| `shared/book.ts`, `shared/window.ts` | book parsing, send-window status |
| `src/` | React UI |
| `test/fixtures/*.jsonl` | real recorded streams |

## Tests
```bash
npm run console:test               # from the repo root
cd console && npm run record -- mama-day   # re-record a fixture with the console's exact args
```
The parser is tested against real streams for `mama-book`, `mama-manager` and `mama-day`, plus a subagent probe. If a skill changes its cards, re-record its stream and update the expectations in `test/stream.test.ts`.

**Replay:** `http://localhost:4173/?replay=mama-day,mama-manager` renders recorded streams without running the CLI. Use it for design review.

## Codex
`codex exec --json` isn't wired up yet. Its event shapes differ, so it needs its own reducer next to `shared/stream.ts`.
