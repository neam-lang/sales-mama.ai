# ADR-0002: Git and markdown are the database

- **Status:** accepted
- **Context:** Up to 5 reps and 1 manager; the harness must be Claude Code / Codex native. A database brings seeding, migrations and row-level security work that slowed a previous build.
- **Decision:** All state is markdown (frontmatter + body), YAML and CSV in one private repo. Append-only files use `merge=union`. Ownership is a frontmatter field, enforced by the guard hook and CODEOWNERS. Generated views (`wiki/index.md`, `wiki/books/`) are rebuilt locally and not committed.
- **Consequences:** a full audit trail for free; no hosting. Limits: about 5–8 concurrent users and about 5,000 active accounts (PLAN §14). Past that, migrate `knowledge/` and the wiki into a service.
