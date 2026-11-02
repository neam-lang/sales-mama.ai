#!/usr/bin/env bash
# Sales Mama nightly run (macOS / Linux). Scheduled by `mama-setup --runner`.
# Runs under the manager's own Claude Code sign-in on the runner machine.
# Usage: runner/nightly.sh ["/mama-nightly dry-run"]   (default prompt: /mama-nightly)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
# cron and launchd start with a bare PATH; add the usual install locations.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
# The runner never sends (ADR-0007): send.py refuses under MAMA_RUNNER, and the CLI may not call it.
export MAMA_RUNNER=1
mkdir -p runner/logs
TS=$(date +%Y%m%d-%H%M)
PROMPT="${1:-/mama-nightly}"
SUFFIX=""; [[ "$PROMPT" == *dry-run* ]] && SUFFIX="-dry-run"
if ! mkdir runner/logs/.lock 2>/dev/null; then
  echo "$TS skipped: another run holds runner/logs/.lock" >> runner/logs/runs.log
  exit 1
fi
trap 'rmdir runner/logs/.lock' EXIT

claude -p "$PROMPT" \
  --permission-mode acceptEdits \
  --permission-prompts none \
  --allowedTools "Bash(python3 scripts/*),Bash(git pull *),Bash(git add *),Bash(git commit *),Bash(git push),Bash(git status *),WebSearch,WebFetch,Read,Edit,Write,Agent,Skill" \
  --disallowedTools "Bash(python3 scripts/send.py *),Bash(python3 scripts/connect.py *)" \
  --output-format json > "runner/logs/$TS$SUFFIX.json" 2>&1
CODE=$?
echo "$TS prompt=\"$PROMPT\" exit=$CODE log=runner/logs/$TS$SUFFIX.json" >> runner/logs/runs.log
exit $CODE

# Codex alternative (enable network / web search for the sandbox in your Codex config first):
# codex exec --sandbox workspace-write "Run the mama-nightly skill" > "runner/logs/$TS.log" 2>&1
