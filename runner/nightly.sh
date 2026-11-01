#!/usr/bin/env bash
# Sales Mama nightly run (macOS / Linux). Scheduled by `mama-setup --runner`.
# Runs under the manager's own Claude Code sign-in on the runner machine.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
mkdir -p runner/logs
TS=$(date +%Y%m%d-%H%M)

claude -p "/mama-nightly" \
  --permission-mode acceptEdits \
  --permission-prompts none \
  --allowedTools "Bash(python3 scripts/*),Bash(git pull *),Bash(git add *),Bash(git commit *),Bash(git push),Bash(git status *),WebSearch,WebFetch,Read,Edit,Write,Agent" \
  --output-format json > "runner/logs/$TS.json" 2>&1

# Codex alternative (enable network / web search for the sandbox in your Codex config first):
# codex exec --sandbox workspace-write "Run the mama-nightly skill" > "runner/logs/$TS.log" 2>&1
