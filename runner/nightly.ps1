# Sales Mama nightly run (Windows). Scheduled by `mama-setup --runner` with schtasks.
# Runs under the manager's own Claude Code sign-in on the runner machine.
$ErrorActionPreference = "Continue"
Set-Location (Join-Path $PSScriptRoot "..")
New-Item -ItemType Directory -Force -Path "runner\logs" | Out-Null
$ts = Get-Date -Format "yyyyMMdd-HHmm"

claude -p "/mama-nightly" `
  --permission-mode acceptEdits `
  --permission-prompts none `
  --allowedTools "Bash(python3 scripts/*),Bash(git pull *),Bash(git add *),Bash(git commit *),Bash(git push),Bash(git status *),WebSearch,WebFetch,Read,Edit,Write,Agent" `
  --output-format json *> "runner\logs\$ts.json"

# Codex alternative:
# codex exec --sandbox workspace-write "Run the mama-nightly skill" *> "runner\logs\$ts.log"
