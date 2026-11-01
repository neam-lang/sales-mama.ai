# Sales Mama Console (Phase 9)

An optional, local, chat-driven cockpit that drives Claude Code (or Codex) headless and renders its work as live agent lanes and colourful cards. Design and protocol: [`docs/UI.md`](../docs/UI.md). Visual target: the "Sales Mama UI" design canvas (sources in [`design/`](../design/)).

This folder holds the contract the console is built against:
- `cards.schema.json`: JSON Schema for `mama-card` blocks.

The console code itself is built in Phase 9 with the prompt in `GUIDE.md` §6. Until then, everything works in plain Claude Code or Codex.

Ground rules (ADR-0006):
- It runs on `localhost` under each user's own Claude Code or Codex sign-in.
- It never widens permissions and never offers a send button.
- Every card shows its source chips (`refs`).
