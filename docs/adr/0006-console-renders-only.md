# ADR-0006: The console renders; it never widens permissions

- **Status:** accepted
- **Context:** Reps want a colourful, chat-driven cockpit, but the harness must stay Claude Code / Codex native.
- **Decision:** The optional Sales Mama Console (Phase 9) drives the local `claude` CLI (or `codex exec`) headless, appends `MAMA_CARDS=on`, and renders `mama-card` blocks, agent lanes and tool chips (`docs/UI.md`). It runs on localhost under each user's own login, uses the project's permission settings unchanged, and has no send button.
- **Consequences:** anything done in the console can also be done by typing in Claude Code; the console can be dropped without losing data or features.
