# Sales Mama nightly run (Windows). Scheduled by `mama-setup --runner` with schtasks.
# Runs under the manager's own Claude Code sign-in on the runner machine.
# Usage: nightly.ps1 ["/mama-nightly dry-run"]   (default prompt: /mama-nightly)
param([string]$Prompt = "/mama-nightly")
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")
New-Item -ItemType Directory -Force -Path "runner\logs" | Out-Null
$ts = Get-Date -Format "yyyyMMdd-HHmm"
$suffix = if ($Prompt -like "*dry-run*") { "-dry-run" } else { "" }
$lock = "runner\logs\.lock"
if (Test-Path $lock) {
  Add-Content "runner\logs\runs.log" "$ts skipped: another run holds $lock"
  exit 1
}
New-Item -ItemType Directory -Path $lock | Out-Null
# The runner never sends (ADR-0007): send.py refuses under MAMA_RUNNER, and the CLI may not call it.
$env:MAMA_RUNNER = "1"
try {
  claude -p $Prompt `
    --permission-mode acceptEdits `
    --permission-prompts none `
    --allowedTools "Bash(python3 scripts/*),Bash(git pull *),Bash(git add *),Bash(git commit *),Bash(git push),Bash(git status *),WebSearch,WebFetch,Read,Edit,Write,Agent,Skill" `
    --disallowedTools "Bash(python3 scripts/send.py *),Bash(python3 scripts/connect.py *)" `
    --output-format json *> "runner\logs\$ts$suffix.json"
  $code = $LASTEXITCODE
  Add-Content "runner\logs\runs.log" "$ts prompt=`"$Prompt`" exit=$code log=runner\logs\$ts$suffix.json"
} finally {
  Remove-Item $lock -Force
}
exit $code

# Codex alternative:
# codex exec --sandbox workspace-write "Run the mama-nightly skill" *> "runner\logs\$ts.log"
