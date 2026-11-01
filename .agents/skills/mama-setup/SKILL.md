---
name: mama-setup
description: 'Set up or health-check Sales Mama for the current user (or the nightly runner with --runner): prerequisites, profile, drafts-only email check, dry run, scheduling. Use when someone says "set me up", is new, or session start says the user is unknown.'
---
# mama-setup

## When to use
- Someone says "Set me up for Sales Mama from <repo URL>", or session start prints "Run mama-setup" (SETUP.md Part B1).
- The manager says "Set up the Sales Mama nightly runner on this machine": run with `--runner` (Part B2).
- The user already has a `reps/<id>.md`: run the health check only (last section).

## Before you start
- Who: anyone for B1 and the health check. `--runner` is manager only (`role: manager` in their `reps/<id>.md`).
- Scripts: `session_start.py`, `sync.py`, `find.py`, `lint.py`, `sync_skills.py` (Phase 0). `--runner` also needs `runner/nightly.sh` / `.ps1` (Phase 7) and what `mama-nightly` runs: `fetch_dataset.py`, `resolve.py` (Phase 2), `score.py` (Phase 3), `build_books.py` (Phase 5), `allocate.py` (Phase 6).
- If a required script is missing, say which phase adds it and stop.
- Setup edits no account pages. If you show one, re-read it first (rule 17).
- Ask one question at a time. At steps marked ASK, wait for the answer; never guess it.

## Steps: B1, a rep or the manager on their own machine
1. Prerequisites: `git --version`, `python3 --version` (3.10+), `python3 -c "import yaml"`. Install what's missing: `python3 -m pip install --user pyyaml`; macOS `xcode-select --install`; Windows `winget install Python.Python.3.12` and `winget install Git.Git`, then make `python3` resolve (alias if needed).
2. If you are not in the repo yet, `git clone <repo URL>` and work inside it. If GitHub auth fails, walk them through `gh auth login` (or their OS credential manager) and retry.
3. ASK: if `git config user.name` or `user.email` is empty, ask for their name and work email and set both. The email is their identity.
4. ASK, one at a time: full name; markets (SG, MY, IN); languages (only codes listed for those markets in `knowledge/markets.yaml`); territory: industries (terms from `knowledge/ontology.yaml` only, rule 7), regions, company size range; daily quota; max active accounts; monthly meeting target; tone; email signature.
5. Write `reps/<id>.md` from `templates/rep.md`: `id` = lowercase first name (add a last-name initial if taken), `email` = git email, `updated:` today. Role: `role: rep`. Only exception: if `reps/` has no profiles yet, this is the manager bootstrapping the kit; confirm that, then write `role: manager`. Never set `manager` otherwise; the manager promotes people.
6. Codex: ask them to trust the project. Claude Code: tell them to approve the `@AGENTS.md` import prompt if it appears.
7. Email check: confirm the connector is signed in to their own mailbox (e.g. list drafts). List the server's tools; no send or forward tool may be callable (Claude Code: denied in `.claude/settings.json`; Codex: absent from `enabled_tools`). If one is callable, stop and tell them to alert the manager. Before Phase 4 there is no connector: say so and go on.
8. Dry run, on screen only: their book (`python3 scripts/find.py --owner me`; empty is fine) and one sample first email for a fictional company. Never create a mailbox draft here.
9. Append the log line (Finish), run `python3 scripts/sync.py`, then print the Part C cheat sheet for their role.

## Steps: B2, `--runner` (manager, on the runner machine)
1. Confirm git email → `reps/<id>.md` with `role: manager`. Otherwise stop.
2. Check the CLI is installed and signed in: `claude --version` (2.1.259+, needed for `--permission-prompts`) or `codex --version`.
3. Make sure `runner/nightly.sh` (macOS/Linux, then `chmod +x`) or `runner/nightly.ps1` (Windows) matches SETUP.md "Runner files"; write it if missing. On Windows, if `python3` doesn't resolve, use the command that does, in the `--allowedTools` pattern too. If you changed it: `git add runner/`, `git commit -m "chore: nightly runner"`, `git push` (`sync.py` does not commit `runner/`).
4. Dry run: run the script's `claude -p` command once by hand with the prompt `"/mama-nightly dry-run"` and output to `runner/logs/<YYYYMMDD-HHMM>-dry-run.json` (Codex: `codex exec --sandbox workspace-write "Run the mama-nightly skill in dry-run mode"`). It can take many minutes: run it in the background and wait. Show the log tail and the `run_status` it reports.
5. ASK: "Schedule the nightly run daily at 02:00 local time?" Only on an explicit yes:
   - macOS / Linux: add `0 2 * * * <repo>/runner/nightly.sh` to `crontab`.
   - Windows: `schtasks /create /sc daily /st 02:00 /tn SalesMamaNightly /tr "powershell -File <repo>\runner\nightly.ps1"`.
   - Codex on Mac: a Codex app Automation instead (daily, prompt "Run the mama-nightly skill", target: local project).
6. Confirm the next run time (`crontab -l`, or `schtasks /query /tn SalesMamaNightly`), and remind them the machine must be awake and online at 02:00.

## Health check (re-run)
Report each as ok or fix: prerequisites · `reps/<id>.md` matches `templates/rep.md`, with valid markets and ontology terms · connector signed in · no send tool callable · `python3 scripts/lint.py` · `python3 scripts/sync_skills.py --check` (on drift run `sync_skills.py`, then start a new session) · manager only: runner schedule present. Fix what this user may fix; hand the rest to the manager.

## Never
- Send anything, or create a real mailbox draft during setup (rule 1).
- Set `role: manager` outside bootstrap, or edit another person's `reps/` file (rule 6; the guard blocks it).
- Schedule the runner without an explicit yes, or for a non-manager.
- Carry on past a callable send tool.

## Finish
- Summary: "Set up Mei (SG). Email: drafts-only ok. Next: /mama-day." Runner: "Runner scheduled 02:00 local; next run Tue 3 Nov 02:00."
- Log: `- [YYYY-MM-DD HH:MM] setup | <user> | reps/<id> | profile created; email drafts-only ok` (runner: target `runner`, summary `dry run ok; scheduled 02:00`).
- Only when the session contains `MAMA_CARDS=on`: a `plan` card of the steps, plus an `error` card for any blocker.
```mama-card
{"type":"plan","title":"Setting up Mei","agent":"mama","steps":[{"label":"Prerequisites","status":"done","agent":"mama"},{"label":"Profile","status":"done","agent":"mama"},{"label":"Email drafts-only check","status":"running","agent":"mama"}],"refs":["reps/mei.md"]}
```
