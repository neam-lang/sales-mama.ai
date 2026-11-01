@AGENTS.md

## Claude Code specifics
- Hooks in `.claude/settings.json` run session start, session stop (sync) and the write guard. Run those scripts by hand only if a hook reported an error.
- Subagents live in `.claude/agents/`: `scout` (one per source group), `researcher` (one per account), `vam` (one per book). Run at most 5 in parallel.
- Use plan mode before changing anything under `knowledge/`, `scripts/`, `.agents/skills/` or `.claude/agents/`.
- Skills are edited in `.agents/skills/` (canonical, shared with Codex) and mirrored with `python3 scripts/sync_skills.py`. Never edit `.claude/skills/` directly.
- Building the kit itself: follow the phase prompts in `GUIDE.md` §6 and run `python3 scripts/selftest.py` and `python3 scripts/eval.py` (once it exists) before calling a phase done.
