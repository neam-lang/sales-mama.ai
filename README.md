# Sales Mama

An agentic sales assistant for small SMB sales teams in Singapore, Malaysia and India, running natively in **Claude Code** or **Codex**.

Sales Mama:
- keeps each rep's book of accounts
- scores leads from internal data and external events (news, tenders, registries, trade events)
- recommends products with a traceable reasoning chain
- prepares outreach with parallel subagents
- runs a virtual account manager for every book
- proposes how to allocate new leads across the team

It never sends messages and never assigns leads without the manager's approval.

**Start here:** [GUIDE.md](GUIDE.md)

| Doc | For |
|---|---|
| [GUIDE.md](GUIDE.md) | Everyone: setup, daily use, the phase-by-phase build with Claude Code |
| [PLAN.md](PLAN.md) | The design and its reasons |
| [SETUP.md](SETUP.md) | Agent-executable setup, cheat sheets, troubleshooting, skill specs |
| [AGENTS.md](AGENTS.md) | The rules every agent follows |
| [docs/UI.md](docs/UI.md) | Chat-driven UI and the `mama-card` protocol |
| [docs/LEARNINGS.md](docs/LEARNINGS.md) | Lessons carried over from TrustBridge |
| [docs/SECURITY.md](docs/SECURITY.md) | Security on one page |

Quick check after cloning:

```bash
python3 -m pip install pyyaml
python3 scripts/selftest.py
```

Then open the folder in Claude Code and type: **"Set me up for Sales Mama."**
