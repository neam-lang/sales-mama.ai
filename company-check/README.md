# Company check

Is this Singapore company real and active? `/company-check <UEN or name>` answers with a verdict, a score and the reason for every check. It uses free open data from data.gov.sg plus web evidence gathered by parallel `verifier` subagents. It's a separate feature: it reads accounts but never edits them.

```bash
python3 scripts/registry_data.py refresh            # first time: ~1 GB download, then monthly
python3 scripts/registry_data.py stats              # freshness, counts, cross-check
python3 scripts/company_check.py check 202012345K   # registry checks only
```
In Claude Code: `/company-check 202012345K`, `/company-check "Brightpath Logistics"`, `/company-check batch`.

## Data
| Dataset (data.gov.sg) | Used for |
|---|---|
| ACRA Information on Corporate Entities (collection 2, 27 CSVs, updated mid-month) | status, entity type, registration date, annual return date, accounts due, address, SSIC, officers, former names, auditors |
| ACRA entities with UEN (`d_3f960c10…`, ~2.12M rows) | every UEN ever issued, Registered or Deregistered |
| BCA registered contractors | workhead, grade, expiry by UEN |
| GeBIZ awards (no UEN; matched by name) | government contracts in the last 3 years |
| HDB property information | home-based detection (HDB residential blocks) |

Only `Live Company` and `Live` count as live (about 624K). Everything sits in `company-check/data/` (git-ignored): the CSVs, `registry.sqlite` (a rebuildable index, ADR-0008) and `manifest.json`. Reports (`reports/`) and web evidence (`evidence/`) are committed so the team sees them.

**Monthly refresh** (ACRA updates mid-month), e.g. cron on the 16th at 07:00:
```
0 7 16 * * cd /path/to/sales-mama.ai && python3 scripts/registry_data.py refresh >> company-check/data/refresh.log 2>&1
```
An optional data.gov.sg API key raises rate limits: `DATAGOV_API_KEY` or `~/.config/sales-mama/datagov.json` `{"key": "…"}`.

## Checks
| | Check | Rule (defaults in `knowledge/company_check.yaml`) |
|---|---|---|
| G1–G2 | Found, live | in ACRA and `Live Company` / `Live` |
| C1 | Annual return | filed in the last 13 months; n/a for companies under 19 months and for sole proprietors, partnerships, LLPs |
| C2–C3 | Accounts, age | accounts not 30+ days overdue; warn under 12 months old |
| P1–P2 | Physical or virtual | address on record; 20+ live entities at the same postal code and unit = shared registered address (corporate secretary or virtual office) |
| P3–P4 | Home-based, premises | HDB residential block; premises seen on the web |
| E1–E2 | Employees > 3 | only from evidence (CRM, website, job postings); ACRA has no headcount, so otherwise unknown |
| A1–A4 | Outside signals | BCA contractor, GeBIZ supplier, website shows name or UEN, activity in 12 months |
| R1–R3 | Red flags | adverse media or MAS alert; shell-like (holding/consultancy SSIC at a shared address, no web); 3+ name changes |

Verdicts: **Not found · Not active · Red flag · Verified · Likely legitimate · Registry OK – needs web check · Caution**.

## Licence and privacy
Contains information from ACRA, BCA, MOF (GeBIZ) and HDB datasets accessed from data.gov.sg, made available under the terms of the [Singapore Open Data Licence v1.0](https://data.gov.sg/open-data-licence). Results are indicative, not legal or credit advice. Reports never show the address of a home-based business (AGENTS.md rule 8).
